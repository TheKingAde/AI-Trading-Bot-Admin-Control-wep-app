"""
Recommend Live Threshold (Confidence Level) for Breakout Model
==============================================================
Loads the trained model package, scores a dataset (feature_subset.db by default),
scans probability thresholds, and recommends a live classification threshold
("confidence level") based on your chosen objective and constraints.

Metrics per threshold:
- precision, recall, f1, trade_freq (ENTER rate)
- avg_profit and total_profit if Profit column is available

Usage (examples):
  python recommend_live_threshold.py \
    --model entry_decision_model.pkl \
    --db data/feature_subset.db --table feature_data --target Win \
    --opt precision --target-precision 0.55 --min-trade-freq 0.05

  python recommend_live_threshold.py --opt expected_value --min-trade-freq 0.03

  python recommend_live_threshold.py --write-back  # save selected threshold into model file
"""

import argparse
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from sklearn.metrics import precision_score, recall_score, f1_score, roc_auc_score, log_loss


def parse_args():
    p = argparse.ArgumentParser(description="Recommend probability threshold for live trading")
    p.add_argument("--model", default="entry_decision_model.pkl", help="Path to trained model package")
    p.add_argument("--db", default=str(Path("data")/"1-training_data_prod.db"), help="SQLite DB with evaluation data")
    p.add_argument("--table", default="training_data", help="Table name in DB")
    p.add_argument("--target", default="Win", help="Binary target column (Win or Profitable)")
    p.add_argument("--opt", default="precision", choices=["precision","f1","expected_value"], help="Optimization objective")
    p.add_argument("--target-precision", type=float, default=0.55, help="Minimum precision to accept (if opt!=precision, still enforced if >0)")
    p.add_argument("--min-trade-freq", type=float, default=0.05, help="Minimum ENTER rate to accept (0-1)")
    p.add_argument("--start", type=float, default=0.05, help="Threshold scan start")
    p.add_argument("--stop", type=float, default=0.95, help="Threshold scan stop")
    p.add_argument("--step", type=float, default=0.01, help="Threshold scan step")
    p.add_argument("--write-back", action="store_true", help="Write selected threshold back into model file")
    p.add_argument("--save-csv", default="", help="Optional path to save scored rows with probabilities and decisions")
    # Hour/session profitability analysis
    p.add_argument("--analyze-hour", action="store_true", help="Also print profitability by hour of day")
    p.add_argument("--hour-col", default="Hour_of_Day", help="Column name for hour of day")
    p.add_argument("--min-count", type=int, default=20, help="Minimum samples per bucket to display")
    p.add_argument("--analyze-session", action="store_true", help="Also print profitability by session flags")
    p.add_argument("--ny-col", default="Is_NY_Session", help="NY session flag column (0/1)")
    p.add_argument("--london-col", default="Is_London_Session", help="London session flag column (0/1)")
    p.add_argument("--asian-col", default="Is_Asian_Session", help="Asian session flag column (0/1)")
    return p.parse_args()


def load_data(db_path: str, table: str) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
    finally:
        conn.close()
    return df


def ensure_features(df: pd.DataFrame, features: list[str]) -> None:
    missing = [c for c in features if c not in df.columns]
    if missing:
        raise SystemExit(f"Missing required feature columns: {missing}")


def prepare_X(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    X = df[features].copy()
    # Encode any object dtypes like in training: simple categorical codes
    for col in X.columns:
        if X[col].dtype == "object" or str(X[col].dtype) == "category":
            X[col] = pd.Categorical(X[col]).codes
    # Coerce to numeric
    for col in X.columns:
        X[col] = pd.to_numeric(X[col], errors='coerce')
    # Fill missing: categorical with -1, numeric with median
    for col in X.columns:
        if X[col].isna().any():
            if X[col].dtype.kind in "iu":
                X[col] = X[col].fillna(-1)
            else:
                X[col] = X[col].fillna(X[col].median())
    return X


def score_model(model_pkg: dict, X: pd.DataFrame) -> np.ndarray:
    scaler = model_pkg.get('scaler')
    model = model_pkg['model']
    if scaler is not None:
        Xs = scaler.transform(X)
    else:
        Xs = X.values
    proba = model.predict_proba(Xs)[:, 1]
    return proba


def compute_metrics(y_true: pd.Series, proba: np.ndarray, thr: float, profits: pd.Series|None):
    pred = (proba >= thr).astype(int)
    tf = pred.mean()  # trade frequency
    if y_true is not None and not y_true.isna().all():
        prec = precision_score(y_true, pred, zero_division=0)
        rec = recall_score(y_true, pred, zero_division=0)
        f1 = f1_score(y_true, pred, zero_division=0)
        auc = roc_auc_score(y_true, proba) if y_true.nunique() == 2 else np.nan
        ll = log_loss(y_true, proba, labels=[0,1]) if set(y_true.dropna().unique()) <= {0,1} else np.nan
    else:
        prec = rec = f1 = auc = ll = np.nan
    avg_p = tot_p = np.nan
    if profits is not None:
        if len(profits) == len(pred):
            mask = pred == 1
            if mask.any():
                avg_p = float(profits[mask].mean())
                tot_p = float(profits[mask].sum())
            else:
                avg_p = 0.0
                tot_p = 0.0
    return {
        'threshold': thr,
        'precision': float(prec),
        'recall': float(rec),
        'f1': float(f1),
        'trade_freq': float(tf),
        'avg_profit': float(avg_p) if not np.isnan(avg_p) else np.nan,
        'total_profit': float(tot_p) if not np.isnan(tot_p) else np.nan,
        'auc': float(auc) if not np.isnan(auc) else np.nan,
        'logloss': float(ll) if not np.isnan(ll) else np.nan,
    }


def select_best(metrics: list[dict], opt: str, target_precision: float, min_trade_freq: float) -> dict | None:
    # Apply constraints first
    candidates = [m for m in metrics if (np.isnan(target_precision) or m['precision'] >= target_precision) and m['trade_freq'] >= min_trade_freq]
    if not candidates:
        # Relax precision if none met target
        candidates = [m for m in metrics if m['trade_freq'] >= min_trade_freq]
        if not candidates:
            # Fallback to any
            candidates = metrics
    if opt == 'precision':
        # Max precision, then higher trade_freq
        candidates.sort(key=lambda m: (m['precision'], m['trade_freq']), reverse=True)
    elif opt == 'f1':
        candidates.sort(key=lambda m: (m['f1'], m['precision'], m['trade_freq']), reverse=True)
    elif opt == 'expected_value':
        # Prefer higher avg_profit, then total_profit, then precision
        candidates.sort(key=lambda m: (m.get('avg_profit') if m.get('avg_profit') is not None else -1e9,
                                       m.get('total_profit') if m.get('total_profit') is not None else -1e9,
                                       m['precision']), reverse=True)
    return candidates[0] if candidates else None


def main():
    args = parse_args()

    print("="*80)
    print("LIVE THRESHOLD RECOMMENDER")
    print("="*80)

    # Load model package
    if not Path(args.model).exists():
        raise SystemExit(f"Model file not found: {args.model}")
    pkg = joblib.load(args.model)
    features = pkg['features']

    print(f"\n📦 Loaded model: {args.model}")
    print(f"   Features used: {features}")
    print(f"   Saved threshold: {pkg.get('threshold')}\n")

    # Load data
    if not Path(args.db).exists():
        raise SystemExit(f"Database not found: {args.db}")
    df = load_data(args.db, args.table)
    print(f"📂 Loaded {len(df):,} rows × {len(df.columns)} cols from {args.db}::{args.table}")

    # Convert all columns to numeric where possible (handles string data from SQLite)
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='ignore')
    
    # Verify and prepare
    ensure_features(df, features)
    X = prepare_X(df, features)

    # Target and profits (optional) - ensure numeric conversion
    y = None
    if args.target in df.columns:
        y = pd.to_numeric(df[args.target], errors='coerce').fillna(0).astype(int)
    profits = None
    if 'Profit' in df.columns:
        profits = pd.to_numeric(df['Profit'], errors='coerce')

    # Score probabilities
    proba = score_model(pkg, X)

    # Threshold scan
    thresholds = np.arange(args.start, args.stop + 1e-9, args.step)
    metrics = [compute_metrics(y, proba, t, profits) for t in thresholds]

    # Select best
    best = select_best(metrics, args.opt, args.target_precision, args.min_trade_freq)

    # Summaries
    dfm = pd.DataFrame(metrics)
    print("\nTop thresholds by precision (head 10):")
    print(dfm.sort_values(['precision','trade_freq'], ascending=[False, False]).head(10).to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    print("\nTop thresholds by F1 (head 10):")
    print(dfm.sort_values(['f1','precision','trade_freq'], ascending=[False, False, False]).head(10).to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    if 'avg_profit' in dfm.columns and not dfm['avg_profit'].isna().all():
        print("\nTop thresholds by avg_profit (head 10):")
        print(dfm.sort_values(['avg_profit','total_profit'], ascending=[False, False]).head(10).to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    if best:
        print("\n" + "="*80)
        print("RECOMMENDED LIVE THRESHOLD")
        print("="*80)
        print(f"Threshold: {best['threshold']:.2f}")
        print(f"Precision: {best['precision']:.3f} | Recall: {best['recall']:.3f} | F1: {best['f1']:.3f} | Trade %: {best['trade_freq']:.1%}")
        if 'avg_profit' in best and best['avg_profit'] is not None and not np.isnan(best['avg_profit']):
            print(f"Avg Profit per ENTER: {best['avg_profit']:.2f} | Total Profit (ENTER set): {best['total_profit']:.2f}")
    else:
        print("\n❌ No suitable threshold found (this should not happen).")

    # ================= Hour-of-day and session profitability analysis =================
    def _print_group_summary(df_in: pd.DataFrame, title: str, group_col: str):
        print("\n" + "="*80)
        print(title)
        print("="*80)
        grp = df_in.groupby(group_col)
        summary = pd.DataFrame({
            'count': grp.size(),
        })
        if y is not None:
            summary['win_rate'] = grp[args.target].mean()
            summary['loss_rate'] = 1 - summary['win_rate']
        if profits is not None:
            summary['avg_profit'] = grp['Profit'].mean()
            summary['total_profit'] = grp['Profit'].sum()
        summary = summary.reset_index()
        # filter by min count
        summary = summary[summary['count'] >= args.min_count]
        if len(summary) == 0:
            print(f"No groups with at least {args.min_count} samples.")
            return
        # Pretty prints
        cols = [group_col, 'count'] + ([ 'win_rate', 'loss_rate'] if 'win_rate' in summary.columns else []) + ([ 'avg_profit', 'total_profit'] if 'avg_profit' in summary.columns else [])
        
        print("\n🏆 BEST HOURS (Top by win_rate):")
        if 'win_rate' in summary.columns:
            best_hours = summary.sort_values('win_rate', ascending=False).head(10)
            print(best_hours[cols].to_string(index=False, float_format=lambda x: f"{x:.4f}"))
        else:
            print("(win_rate not available; target column missing)")
        
        print("\n💀 WORST HOURS (Top by loss_rate):")
        if 'loss_rate' in summary.columns:
            worst_hours = summary.sort_values('loss_rate', ascending=False).head(10)
            print(worst_hours[cols].to_string(index=False, float_format=lambda x: f"{x:.4f}"))
        
        # ALL HOURS RANKED
        print("\n📊 ALL HOURS RANKED (by win_rate):")
        if 'win_rate' in summary.columns:
            all_hours = summary.sort_values('win_rate', ascending=False)
            print(all_hours[cols].to_string(index=False, float_format=lambda x: f"{x:.4f}"))
        
        if 'avg_profit' in summary.columns:
            print("\n💰 Top by avg_profit:")
            print(summary.sort_values('avg_profit', ascending=False)[cols].head(10).to_string(index=False, float_format=lambda x: f"{x:.4f}"))
            print("\n💵 Top by total_profit:")
            print(summary.sort_values('total_profit', ascending=False)[cols].head(10).to_string(index=False, float_format=lambda x: f"{x:.4f}"))
            print("\n📉 Worst by avg_profit:")
            print(summary.sort_values('avg_profit', ascending=True)[cols].head(10).to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    if True:
        # Overall by hour
        _print_group_summary(df, "PROFITABILITY BY HOUR (All rows)", args.hour_col)
        # If best threshold exists, analyze only predicted ENTERs at that threshold
        if best is not None:
            df_pred = df.copy()
            df_pred['proba'] = proba
            df_pred['pred'] = (proba >= best['threshold']).astype(int)
            _print_group_summary(df_pred[df_pred['pred'] == 1], f"PROFITABILITY BY HOUR (Predicted ENTERs @ {best['threshold']:.2f})", args.hour_col)
    elif args.analyze_hour:
        print(f"\n⚠️ Hour analysis requested, but column '{args.hour_col}' not found.")

    if args.analyze_session:
        # For each session flag present, print profitability
        for sess_col in [args.ny_col, args.london_col, args.asian_col]:
            if sess_col in df.columns:
                # map 1/0 to strings for grouping clarity
                df_s = df.copy()
                df_s[sess_col] = df_s[sess_col].map({1: f"{sess_col}=1", 0: f"{sess_col}=0"}).fillna(f"{sess_col}=NA")
                _print_group_summary(df_s, f"PROFITABILITY BY SESSION FLAG: {sess_col} (All rows)", sess_col)
                if best is not None:
                    df_ps = df_s.copy()
                    df_ps['proba'] = proba
                    df_ps['pred'] = (proba >= best['threshold']).astype(int)
                    _print_group_summary(df_ps[df_ps['pred'] == 1], f"PROFITABILITY BY SESSION FLAG: {sess_col} (Predicted ENTERs)", sess_col)
            else:
                print(f"\n⚠️ Session analysis: column '{sess_col}' not found.")

    # Save CSV if requested
    if args.save_csv:
        out = df.copy()
        out['proba'] = proba
        if best:
            out['pred'] = (proba >= best['threshold']).astype(int)
        Path(args.save_csv).parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(args.save_csv, index=False)
        print(f"\n📝 Scored rows saved to: {args.save_csv}")

    # Optionally write back
    if args.write_back and best:
        pkg['threshold'] = float(best['threshold'])
        joblib.dump(pkg, args.model)
        print(f"\n💾 Updated model threshold saved back to: {args.model}")


if __name__ == "__main__":
    main()
