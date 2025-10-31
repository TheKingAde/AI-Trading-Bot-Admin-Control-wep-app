"""
FEATURE DIAGNOSTIC ANALYSIS
============================
Diagnoses predictive signal quality in the latest training dataset stored in SQLite.

Checks:
1) Feature-target correlations (which features actually predict wins?)
2) Feature distributions for wins vs losses
3) Constant/near-constant feature detection
4) Missing values and value ranges

This version automatically handles Outcome values including BE (breakeven).
"""

import pandas as pd
import numpy as np
import sqlite3
from pathlib import Path
from scipy import stats
import argparse
import warnings

warnings.filterwarnings('ignore')

print("=" * 80)
print("FEATURE DIAGNOSTIC ANALYSIS")
print("Investigating why the model can't predict wins")
print("=" * 80)

parser = argparse.ArgumentParser(description="Diagnose features vs target in training database")
parser.add_argument("--db", default=str(Path('data') / '1-training_data.db'), help="Path to SQLite DB")
parser.add_argument("--table", default='training_data', help="Table name containing training rows")
parser.add_argument("--target", default='Win', help="Target column: Win (default) or Profitable")
args, _ = parser.parse_known_args()

# Configuration (can be overridden via CLI)
DB_PATH = Path(args.db)
TABLE_NAME = args.table
TARGET = args.target

# ===================== LOAD DATA =====================
print(f"\n📂 Loading data from {DB_PATH}...")
conn = sqlite3.connect(DB_PATH)
df = pd.read_sql_query(f"SELECT * FROM {TABLE_NAME}", conn)
conn.close()
print(f"✅ Loaded {len(df):,} rows × {len(df.columns)} columns")

############################
# Column selection & typing
############################

# Prefer Win if present; else try Profitable; else derive from Outcome
if TARGET not in df.columns:
    fallback_targets = [c for c in ['Win', 'Profitable'] if c in df.columns]
    if fallback_targets:
        TARGET = fallback_targets[0]
    elif 'Outcome' in df.columns:
        # Only create numeric Win target for correlation analysis
        df['Win'] = np.where(df['Outcome'].astype(str).str.lower() == 'win', 1,
                    np.where(df['Outcome'].astype(str).str.lower() == 'loss', 0,
                    np.where(df['Outcome'].astype(str).str.lower() == 'be', 0.5, np.nan)))
        TARGET = 'Win'
    else:
        raise SystemExit("No suitable target column found (Win/Profitable/Outcome)")

# Columns that clearly leak or are identifiers (exclude from features)
LEAKAGE_OR_ID_COLS = set([
    'id','Win', 'Trade_Time', 'Exit_Price',
    'Profit', 'Profit_Pct', 'Outcome', TARGET
])

# Detect categorical string columns to encode
categorical_cols = [c for c in df.columns if df[c].dtype == 'object']

# Encode categoricals as codes (keeps NaNs as -1)
for col in categorical_cols:
    df[col] = pd.Categorical(df[col])
    df[col] = df[col].cat.codes.replace({-1: np.nan})

# Build feature list automatically: everything except leakage/id columns
candidate_cols = [c for c in df.columns if c not in LEAKAGE_OR_ID_COLS]

# Coerce all non-target columns to numeric where possible
for col in candidate_cols:
    df[col] = pd.to_numeric(df[col], errors='coerce')

# Final feature set: numeric columns with at least some variance
INPUT_FEATURES = []
for col in candidate_cols:
    if col == TARGET:
        continue
    series = df[col]
    if series.notna().sum() > 0 and series.std(skipna=True) > 0:
        INPUT_FEATURES.append(col)

# Ensure target is numeric binary
df[TARGET] = pd.to_numeric(df[TARGET], errors='coerce')

# If Outcome is numeric, map values to labels
outcome_map = {1: 'win', 0: 'loss', 2: 'be'}
df['Outcome_clean'] = df['Outcome'].map(outcome_map)

print("Unique Outcome values (raw):", df['Outcome'].unique())
print("Unique Outcome values (clean):", df['Outcome_clean'].unique())

wins = df[df['Outcome_clean'] == 'win'].copy()
losses = df[df['Outcome_clean'] == 'loss'].copy()
breakeven = df[df['Outcome_clean'] == 'be'].copy()


print(f"\n📊 Dataset split:")
print(f"   Wins:       {len(wins):,} ({len(wins)/len(df)*100:.1f}%)")
print(f"   Losses:     {len(losses):,} ({len(losses)/len(df)*100:.1f}%)")
print(f"   Breakevens: {len(breakeven):,} ({len(breakeven)/len(df)*100:.1f}%)")

# ======================== 1. FEATURE-TARGET CORRELATION ========================
print(f"\n{'=' * 80}")
print("1. FEATURE-TARGET CORRELATION ANALYSIS")
print("=" * 80)
print("\nWhich features actually correlate with winning?")
print("(Higher absolute correlation = stronger predictive power)\n")

correlations = []
for feature in INPUT_FEATURES:
    if feature in df.columns:
        clean_data = df[[feature, TARGET]].dropna()
        if len(clean_data) > 0 and clean_data[feature].std() > 0:
            # Pearson correlation (handles 3-class numeric targets)
            corr, p_value = stats.pearsonr(clean_data[TARGET], clean_data[feature])
            correlations.append({
                'Feature': feature,
                'Correlation': corr,
                'Abs_Correlation': abs(corr),
                'P_Value': p_value,
                'Significant': '✓' if p_value < 0.05 else '✗'
            })

corr_df = pd.DataFrame(correlations).sort_values('Abs_Correlation', ascending=False)

print("Top 10 Most Correlated Features:")
print("-" * 80)
for _, row in corr_df.head(10).iterrows():
    bar_len = int(abs(row['Correlation']) * 40)
    bar = '█' * bar_len
    sign = '+' if row['Correlation'] > 0 else '-'
    print(f"  {row['Feature']:30s} | {sign}{bar} {row['Correlation']:6.3f} (p={row['P_Value']:.4f}) {row['Significant']}")

print("\nBottom 5 (weakest correlation):")
print("-" * 80)
for _, row in corr_df.tail(5).iterrows():
    print(f"  {row['Feature']:30s} | {row['Correlation']:6.3f} (p={row['P_Value']:.4f}) {row['Significant']}")

# ======================== 2. FEATURE DISTRIBUTIONS ========================
print(f"\n{'=' * 80}")
print("2. FEATURE DISTRIBUTIONS: WINS vs LOSSES vs BE")
print("=" * 80)
print("\nAre feature values different between outcomes?")
print("(Large diff = feature helps distinguish outcomes)\n")

distributions = []
for feature in INPUT_FEATURES:
    if feature in df.columns:
        win_vals = wins[feature].dropna()
        loss_vals = losses[feature].dropna()
        be_vals = breakeven[feature].dropna()

        pairs = [
            ("Win vs Loss", win_vals, loss_vals),
            ("Win vs BE", win_vals, be_vals),
            ("BE vs Loss", be_vals, loss_vals),
        ]

        for label, group1, group2 in pairs:
            if len(group1) > 0 and len(group2) > 0:
                t_stat, p_value = stats.ttest_ind(group1, group2, equal_var=False)
                pooled_std = np.sqrt((group1.std()**2 + group2.std()**2) / 2)
                cohens_d = (group1.mean() - group2.mean()) / pooled_std if pooled_std > 0 else 0

                distributions.append({
                    'Feature': feature,
                    'Comparison': label,
                    'Mean_1': group1.mean(),
                    'Mean_2': group2.mean(),
                    'Diff': group1.mean() - group2.mean(),
                    'Cohens_D': abs(cohens_d),
                    'P_Value': p_value,
                    'Significant': '✓' if p_value < 0.05 else '✗'
                })

dist_df = pd.DataFrame(distributions).sort_values('Cohens_D', ascending=False)

print("Top 10 Features with Largest Effect Size (Cohen's D):")
print("-" * 100)
print(f"{'Feature':<30} {'Comparison':<15} {'Mean_1':>10} {'Mean_2':>10} {'Effect':>8} {'Sig':>5}")
print("-" * 100)
for _, row in dist_df.head(10).iterrows():
    print(f"{row['Feature']:<30} {row['Comparison']:<15} {row['Mean_1']:10.5f} {row['Mean_2']:10.5f} "
          f"{row['Cohens_D']:8.3f} {row['Significant']:>5}")

# ======================== 3. CONSTANT FEATURES ========================
print(f"\n{'=' * 80}")
print("3. CONSTANT OR NEAR-CONSTANT FEATURES")
print("=" * 80)
low_variance = []
for feature in INPUT_FEATURES:
    if feature in df.columns:
        unique_vals = df[feature].nunique()
        unique_pct = unique_vals / len(df) * 100
        std_dev = df[feature].std()
        if unique_vals <= 3 or unique_pct < 1.0:
            low_variance.append({
                'Feature': feature,
                'Unique_Values': unique_vals,
                'Unique_Pct': unique_pct,
                'Std_Dev': std_dev,
                'Most_Common': df[feature].mode()[0] if len(df[feature].mode()) > 0 else None,
                'Most_Common_Pct': (df[feature] == df[feature].mode()[0]).sum() / len(df) * 100 if len(df[feature].mode()) > 0 else 0
            })

if low_variance:
    lv_df = pd.DataFrame(low_variance)
    print(f"{'Feature':<30} {'Unique':>8} {'Unique %':>10} {'Most Common %':>15}")
    print("-" * 70)
    for _, row in lv_df.iterrows():
        print(f"{row['Feature']:<30} {row['Unique_Values']:8d} {row['Unique_Pct']:9.2f}% {row['Most_Common_Pct']:14.1f}%")
else:
    print("✅ No constant features detected")

# ======================== 4. MISSING VALUE ANALYSIS ========================
print(f"\n{'=' * 80}")
print("4. MISSING VALUE ANALYSIS")
print("=" * 80)
missing = df[INPUT_FEATURES].isna().sum()
missing = missing[missing > 0].sort_values(ascending=False)
if len(missing) > 0:
    print(f"\nFeatures with missing values:")
    print(f"{'Feature':<30} {'Missing':>10} {'Percent':>10}")
    print("-" * 52)
    for feat, count in missing.items():
        pct = count / len(df) * 100
        print(f"{feat:<30} {count:10,} {pct:9.2f}%")
else:
    print("\n✅ No missing values in feature set")

# ======================== 5. FEATURE VALUE RANGES ========================
print(f"\n{'=' * 80}")
print("5. FEATURE VALUE RANGES")
print("=" * 80)
print("\nWin vs Loss ranges for top correlated features:\n")

top_features = corr_df.head(5)['Feature'].tolist()
print(f"{'Feature':<30} {'Win Range':>25} {'Loss Range':>25}")
print("-" * 82)
for feature in top_features:
    if feature in df.columns:
        win_min = wins[feature].min()
        win_max = wins[feature].max()
        loss_min = losses[feature].min()
        loss_max = losses[feature].max()
        be_min = breakeven[feature].min()
        be_max = breakeven[feature].max()
        print(f"{feature:<30} [Win: {win_min:9.4f}, {win_max:9.4f}] [Loss: {loss_min:9.4f}, {loss_max:9.4f}] [BE: {be_min:9.4f}, {be_max:9.4f}]")

# ======================== 6. SUMMARY ========================
print(f"\n{'=' * 80}")
print("6. DIAGNOSTIC SUMMARY & RECOMMENDATIONS")
print("=" * 80)
strong_corr = corr_df[corr_df['Abs_Correlation'] > 0.1]
weak_features = len(corr_df) - len(strong_corr)
print(f"\n📊 Feature Quality Assessment:")
print(f"   Total features: {len(corr_df)}")
print(f"   Strong correlation (>0.1): {len(strong_corr)} features")
print(f"   Weak correlation (<0.1): {weak_features} features")
print(f"   Statistically significant (p<0.05): {(corr_df['P_Value'] < 0.05).sum()} features")

print(f"\n🎯 Recommendations:")
if len(strong_corr) == 0:
    print("   ⚠️  CRITICAL: NO features show strong correlation with winning!")
    print("   → Add new features (e.g., time-based, session, volatility clusters)")
    print("   → Check data labeling (is 'Outcome' correct?)")
else:
    print(f"   ✓ Focus on top {min(5, len(strong_corr))} correlated features:")
    for feat in strong_corr.head(5)['Feature']:
        print(f"     - {feat}")

if len(low_variance) > 0:
    print(f"\n   ⚠️  Remove {len(low_variance)} near-constant features:")
    for feat_dict in low_variance:
        print(f"     - {feat_dict['Feature']} ({feat_dict['Unique_Values']} unique values)")

if corr_df['Abs_Correlation'].max() < 0.05:
    print(f"\n   🚨 CRITICAL ISSUE: Maximum correlation is {corr_df['Abs_Correlation'].max():.4f}")
    print("   → Current features cannot distinguish outcomes")
    print("   → REQUIRED: Feature engineering or data quality fix")

print(f"\n{'=' * 80}")
print("Analysis complete. Use findings to improve feature engineering.")
print("=" * 80)

# Additional summary for BE trades
print("\nBreakeven (BE) trades summary:")
if len(breakeven) > 0:
    print(f"   BE trades detected: {len(breakeven):,} ({len(breakeven)/len(df)*100:.1f}%)")
    print("   Consider analyzing features that distinguish BE from Win/Loss.")
else:
    print("   No BE trades found in this dataset.")
