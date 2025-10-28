"""
ENTRY DECISION BINARY CLASSIFIER - Candlestick Breakout Regime
==============================================================
Objective: Predict whether a trade will Win (1) or Lose (0) at breakout time

Uses REAL outcomes from historical trades (Win=1/0).
Focuses on session/time and breakout strength features aligned to the breakout event.

Features (7):
    - Symbol (encoded)
    - Action (encoded)
    - Hour_of_Day
    - Is_NY_Session
    - Is_Asian_Session
    - Is_London_Session
    - Breakout_Strength

Target:
    - Win (1=Win, 0=Loss)

Output: Binary decision with probability and saved threshold for deployment.
"""

import pandas as pd
import numpy as np
import sqlite3
import lightgbm as lgb
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, confusion_matrix, classification_report, log_loss
)
from sklearn.preprocessing import RobustScaler
import joblib
import warnings
from pathlib import Path

warnings.filterwarnings('ignore')

print("=" * 80)
print("PRODUCTION-GRADE ENTRY DECISION CLASSIFIER (Breakout Regime)")
print("Objective: Predict Win vs Loss from session/time + breakout strength")
print("Learning from REAL trade outcomes—no synthetic rules")
print("=" * 80)

# ======================== Configuration ========================
DB_PATH = Path('data/training_data.db')
TABLE_NAME = 'training_data'
MODEL_OUTPUT = 'entry_decision_model.pkl'

# ======================== Training/Tuning Config (EDIT HERE) ========================
# >>> TUNE: Train/Val/Test split ratios (must sum to 1.0)
# For more validation data (smoother threshold tuning), increase VAL_RATIO slightly.
TRAIN_RATIO = 0.70  # e.g., 0.70
VAL_RATIO   = 0.15  # e.g., 0.15
TEST_RATIO  = 0.15  # e.g., 0.15

# >>> TUNE: Class imbalance handling
# By default we compute scale_pos_weight automatically as (negatives/positives) on train set.
# You can override it to make the model focus more on winners (positive class) which
# often improves high-threshold precision at the cost of recall. Typical useful range: 5.0–15.0.
# Set to None to use auto; set to a float to force. Example: 8.0 or 10.0
FORCE_SCALE_POS_WEIGHT: float | None = None

# >>> TUNE: Model complexity vs generalization
# Smaller trees + stronger regularization can reduce false positives (improves precision)
# but may miss some winners (reduces recall). Adjust within recommended ranges below.
LGBM_PARAMS = {
    'boosting_type': 'gbdt',
    'num_leaves': 31,     # [16–63] fewer leaves => simpler model => often higher precision
    'max_depth': 6,       # [4–10] limit tree depth to reduce overfit/false positives
    'learning_rate': 0.05,# [0.02–0.1] lower => more estimators needed, smoother fit
    'n_estimators': 500,  # [200–1500] with early stopping; higher if lowering learning_rate
    'feature_fraction': 0.9, # [0.6–1.0] subsample features per tree (regularization)
    'bagging_fraction': 0.8, # [0.6–1.0] subsample rows per iteration
    'bagging_freq': 5,
    'min_child_samples': 20, # [10–100] higher => smoother leaves, fewer spurious signals
    'reg_alpha': 0.1,     # [0–1] L1; increase to simplify model
    'reg_lambda': 0.1,    # [0–5] L2; increase to reduce overfitting
    'random_state': 42,
}

# >>> OPTIONAL: Auto threshold tuning on validation set (recommended for live use)
# When True, we scan thresholds to pick one that meets a target precision (win rate)
# and a minimum trade frequency. This selected threshold is saved into the model file
# and used for test-set classification metrics below.
ENABLE_AUTO_THRESHOLD = True   # Set to True to enable auto-tuning
THRESHOLD_TARGET_PRECISION = 0.50  # e.g., 0.50 = 50% win rate target
THRESHOLD_MIN_TRADE_FREQ   = 0.05  # e.g., 0.05 = at least 5% of samples become ENTER
THRESHOLD_SCAN_START = 0.05   # widen scan downwards so low-calibrated models can still trigger ENTER
THRESHOLD_SCAN_STOP  = 0.90
THRESHOLD_SCAN_STEP  = 0.01

# Features for prediction (21 features - EXCLUDE target variables)
INPUT_FEATURES = [
    'Symbol',
    'Action',
    'Hour_of_Day',
    'Is_NY_Session',
    'Is_Asian_Session',
    'Is_London_Session',
    'Breakout_Strength',
]

TARGET = 'Win'  # Binary: 1=Win, 0=Loss

# ======================== Load Data ========================
print(f"\n📂 Loading training data from SQLite database...")

if not DB_PATH.exists():
    print(f"❌ Database not found: {DB_PATH}")
    print("Please run 'python import_cleaned_merged_to_db.py' first.")
    exit(1)

conn = sqlite3.connect(DB_PATH)
df = pd.read_sql_query(f"SELECT * FROM {TABLE_NAME}", conn)
conn.close()

print(f"✅ Loaded {len(df):,} rows × {len(df.columns)} columns")


# Sort chronologically for time-series split (by Trade_Time if available)
if 'Trade_Time' in df.columns:
    df['Trade_Time'] = pd.to_datetime(df['Trade_Time'], errors='coerce')
    df = df.sort_values('Trade_Time').reset_index(drop=True)
    print("✅ Data sorted chronologically by Trade_Time")

# ======================== Validate Schema ========================
print(f"\n🔍 Validating required columns...")

required_cols = INPUT_FEATURES + [TARGET]
missing = [col for col in required_cols if col not in df.columns]

if missing:
    print(f"\n❌ MISSING COLUMNS: {missing}")
    print(f"\nAvailable columns ({len(df.columns)}):")
    for i, col in enumerate(df.columns, 1):
        print(f"  {i:2d}. {col}")
    exit(1)

print(f"✅ All {len(required_cols)} required columns present")

# ======================== Prepare Features & Target ========================
print(f"\n🔧 Preparing features and target...")

# ======================== Convert String Columns to Numeric ========================
print(f"🔄 Converting string columns to proper numeric types...")

# Columns that should be numeric (all features except categorical ones)
numeric_cols = [col for col in INPUT_FEATURES if col not in ['Symbol', 'Action']]

for col in numeric_cols:
    if col in df.columns:
        # Convert to numeric, coercing errors to NaN
        df[col] = pd.to_numeric(df[col], errors='coerce')

# Convert target column with fallback to Outcome (string)
if TARGET in df.columns:
    df[TARGET] = pd.to_numeric(df[TARGET], errors='coerce')
    # If Win is NaN or missing, derive from Outcome text
    if df[TARGET].isna().all():
        if 'Outcome' in df.columns:
            print(f"⚠️  Win column empty/invalid, deriving from Outcome string...")
            df[TARGET] = df['Outcome'].apply(lambda x: 1 if str(x).lower() == 'win' else 0)
            print(f"✅ Derived Win from Outcome")

print(f"✅ Type conversions complete")

# Extract features and target
X = df[INPUT_FEATURES].copy()
y = df[TARGET].copy()

# Check target distribution BEFORE any processing
print(f"\n📊 Raw target distribution:")
print(f"   Class 1 (Win):  {(y == 1).sum():,} ({(y == 1).mean()*100:.1f}%)")
print(f"   Class 0 (Loss): {(y == 0).sum():,} ({(y == 0).mean()*100:.1f}%)")

if (y == 1).sum() == 0 or (y == 0).sum() == 0:
    print("\n❌ ERROR: Imbalanced or missing target class!")
    print("   Check your 'Profitable' column values.")
    print(f"   Unique values in Profitable: {df[TARGET].unique()}")
    if 'Outcome_Category' in df.columns:
        print(f"   Unique values in Outcome_Category: {df['Outcome_Category'].unique()[:10]}")
    exit(1)

# Encode categorical features
categorical_features = []
for col in ['Symbol', 'Action']:
    if col in X.columns:
        if X[col].dtype == 'object' or X[col].dtype == 'bool':
            X[col] = pd.Categorical(X[col]).codes
            categorical_features.append(col)
            print(f"   Encoded: {col} ({X[col].nunique()} unique values)")

# Clean features: replace inf, fill NaN
X = X.replace([np.inf, -np.inf], np.nan)
nan_counts = X.isna().sum()
if nan_counts.sum() > 0:
    print(f"\n⚠️  Filling {nan_counts.sum()} NaN values with column medians")
    # Fill NaN with median for numeric columns only
    for col in X.columns:
        if X[col].isna().sum() > 0:
            if col in categorical_features:
                X[col] = X[col].fillna(-1)  # Use -1 for missing categorical
            else:
                X[col] = X[col].fillna(X[col].median())

# Ensure target is clean binary
y = y.fillna(0).astype(int)

print(f"\n✅ Feature matrix: {X.shape[0]:,} samples × {X.shape[1]} features")
print(f"✅ Target vector: {len(y):,} labels (binary: 0/1)")

# Show feature summary statistics
print(f"\n📈 Feature Summary Statistics:")
print(X.describe().T[['mean', 'std', 'min', 'max']])


# ======================== Time-Based Train/Val/Test Split ========================
print(f"\n📊 Creating time-based train/validation/test split...")
print("   (Respects chronological order—no data leakage)")

n_samples = len(df)

# Ratios safety check (EDIT HERE block above)
assert abs((TRAIN_RATIO + VAL_RATIO + TEST_RATIO) - 1.0) < 1e-6, "Train/Val/Test ratios must sum to 1.0"

train_end = int(TRAIN_RATIO * n_samples)              # e.g., 70% train
val_end = int((TRAIN_RATIO + VAL_RATIO) * n_samples)  # next 15% val, last 15% test

X_train = X.iloc[:train_end]
y_train = y.iloc[:train_end]
X_val = X.iloc[train_end:val_end]
y_val = y.iloc[train_end:val_end]
X_test = X.iloc[val_end:]
y_test = y.iloc[val_end:]

print(f"\n   Training:   {len(X_train):,} samples | Win: {(y_train==1).sum():,} ({(y_train==1).mean()*100:.1f}%)")
print(f"   Validation: {len(X_val):,} samples | Win: {(y_val==1).sum():,} ({(y_val==1).mean()*100:.1f}%)")
print(f"   Test:       {len(X_test):,} samples | Win: {(y_test==1).sum():,} ({(y_test==1).mean()*100:.1f}%)")

# ======================== Feature Scaling ========================
print(f"\n🔄 Scaling features with RobustScaler...")
scaler = RobustScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_val_scaled = scaler.transform(X_val)
X_test_scaled = scaler.transform(X_test)
print(f"✅ Features scaled (robust to outliers)")

# ======================== Train Binary Classifier ========================
print(f"\n🚀 Training LightGBM Binary Classifier...")

# Calculate class weight for imbalanced data (auto baseline)
class_weight = (y_train == 0).sum() / (y_train == 1).sum()
print(f"   Class imbalance ratio: {class_weight:.2f}:1 (loss:win)")

# >>> EDIT HERE: Force positive-class upweighting (if configured)
# Using a larger scale_pos_weight makes the model prioritize correctly classifying WINs,
# which typically raises precision at higher thresholds. If FORCE_SCALE_POS_WEIGHT is None,
# we use the auto-computed ratio above.
scale_pos = FORCE_SCALE_POS_WEIGHT if FORCE_SCALE_POS_WEIGHT is not None else class_weight
if FORCE_SCALE_POS_WEIGHT is not None:
    print(f"   Forcing scale_pos_weight={FORCE_SCALE_POS_WEIGHT} (recommended range 5–15 for sparse winners)")
else:
    print(f"   Using auto scale_pos_weight={scale_pos:.2f}")

model = lgb.LGBMClassifier(
    objective='binary',
    metric='auc',
    boosting_type=LGBM_PARAMS['boosting_type'],
    num_leaves=LGBM_PARAMS['num_leaves'],
    max_depth=LGBM_PARAMS['max_depth'],
    learning_rate=LGBM_PARAMS['learning_rate'],
    n_estimators=LGBM_PARAMS['n_estimators'],
    feature_fraction=LGBM_PARAMS['feature_fraction'],
    bagging_fraction=LGBM_PARAMS['bagging_fraction'],
    bagging_freq=LGBM_PARAMS['bagging_freq'],
    min_child_samples=LGBM_PARAMS['min_child_samples'],
    scale_pos_weight=scale_pos,  # Handle imbalance (auto or forced)
    reg_alpha=LGBM_PARAMS['reg_alpha'],
    reg_lambda=LGBM_PARAMS['reg_lambda'],
    verbose=-1,
    random_state=LGBM_PARAMS['random_state']
)

print(f"   Training with early stopping (50 rounds patience)...")
model.fit(
    X_train_scaled, y_train,
    eval_set=[(X_val_scaled, y_val)],
    eval_metric='auc',
    callbacks=[lgb.early_stopping(stopping_rounds=50, verbose=False)]
)

print(f"✅ Training complete | Best iteration: {model.best_iteration_} | Best score: {model.best_score_['valid_0']['auc']:.4f}")

# ======================== Smart Retrain Detection ========================
# Check if model has very low confidence (poor calibration)
y_val_pred_proba_initial = model.predict_proba(X_val_scaled)[:, 1]
max_val_prob = float(np.max(y_val_pred_proba_initial))
median_val_prob = float(np.median(y_val_pred_proba_initial))

# If max probability < 0.35 OR median < 0.20, model is under-confident on positive class
# This typically means it needs stronger positive class weighting
RETRAIN_THRESHOLD_MAX = 0.35
RETRAIN_THRESHOLD_MEDIAN = 0.20

if max_val_prob < RETRAIN_THRESHOLD_MAX or median_val_prob < RETRAIN_THRESHOLD_MEDIAN:
    print(f"\n⚠️  MODEL UNDER-CONFIDENCE DETECTED")
    print(f"   Validation probabilities: max={max_val_prob:.3f}, median={median_val_prob:.3f}")
    print(f"   Triggering RETRAIN with stronger positive class weighting...")
    
    # Increase scale_pos_weight significantly to force model to predict more wins
    boosted_scale_pos = scale_pos * 2.5  # 2.5x boost (e.g., 5.08 → 12.7)
    print(f"   New scale_pos_weight: {boosted_scale_pos:.2f} (was {scale_pos:.2f})")
    
    model = lgb.LGBMClassifier(
        objective='binary',
        metric='auc',
        boosting_type=LGBM_PARAMS['boosting_type'],
        num_leaves=LGBM_PARAMS['num_leaves'],
        max_depth=LGBM_PARAMS['max_depth'],
        learning_rate=LGBM_PARAMS['learning_rate'],
        n_estimators=LGBM_PARAMS['n_estimators'],
        feature_fraction=LGBM_PARAMS['feature_fraction'],
        bagging_fraction=LGBM_PARAMS['bagging_fraction'],
        bagging_freq=LGBM_PARAMS['bagging_freq'],
        min_child_samples=LGBM_PARAMS['min_child_samples'],
        scale_pos_weight=boosted_scale_pos,  # BOOSTED weight
        reg_alpha=LGBM_PARAMS['reg_alpha'],
        reg_lambda=LGBM_PARAMS['reg_lambda'],
        verbose=-1,
        random_state=LGBM_PARAMS['random_state']
    )
    
    model.fit(
        X_train_scaled, y_train,
        eval_set=[(X_val_scaled, y_val)],
        eval_metric='auc',
        callbacks=[lgb.early_stopping(stopping_rounds=50, verbose=False)]
    )
    
    print(f"   ✅ RETRAIN complete | Best iteration: {model.best_iteration_} | Best score: {model.best_score_['valid_0']['auc']:.4f}")
else:
    print(f"   Model confidence acceptable (max={max_val_prob:.3f}, median={median_val_prob:.3f})")

# ======================== Validation Metrics ========================
print(f"\n{'=' * 80}")
print(f"VALIDATION SET PERFORMANCE")
print(f"{'=' * 80}")

y_val_pred_proba = model.predict_proba(X_val_scaled)[:, 1]
y_val_pred = (y_val_pred_proba >= 0.5).astype(int)

# Probability diagnostics (helps understand calibration and thresholding)
print("\nValidation probability diagnostics:")
print(f"  min={float(np.min(y_val_pred_proba)):.3f} | p10={float(np.quantile(y_val_pred_proba, 0.10)):.3f} | "
    f"median={float(np.median(y_val_pred_proba)):.3f} | p90={float(np.quantile(y_val_pred_proba, 0.90)):.3f} | "
    f"max={float(np.max(y_val_pred_proba)):.3f}")

val_acc = accuracy_score(y_val, y_val_pred)
val_prec = precision_score(y_val, y_val_pred, zero_division=0)
val_rec = recall_score(y_val, y_val_pred, zero_division=0)
val_f1 = f1_score(y_val, y_val_pred, zero_division=0)
val_auc = roc_auc_score(y_val, y_val_pred_proba)
val_logloss = log_loss(y_val, y_val_pred_proba)

print(f"\nClassification Metrics:")
print(f"  Accuracy:   {val_acc:.4f}  (Overall correctness)")
print(f"  Precision:  {val_prec:.4f}  (Of predicted ENTERs, how many won?)")
print(f"  Recall:     {val_rec:.4f}  (Of actual winners, how many caught?)")
print(f"  F1-Score:   {val_f1:.4f}  (Harmonic mean of precision/recall)")
print(f"  ROC-AUC:    {val_auc:.4f}  (Discrimination ability)")
print(f"  Log Loss:   {val_logloss:.4f}  (Calibration quality)")

cm = confusion_matrix(y_val, y_val_pred)
print(f"\nConfusion Matrix:")
print(f"                  Predicted: STAY OUT | Predicted: ENTER")
print(f"  Actual LOSS:        {cm[0,0]:5d}        |     {cm[0,1]:5d}")
print(f"  Actual WIN:         {cm[1,0]:5d}        |     {cm[1,1]:5d}")
print(f"\n  True Negatives (correct stay-out):  {cm[0,0]:,}")
print(f"  False Positives (wrong entry):       {cm[0,1]:,}")
print(f"  False Negatives (missed opportunity): {cm[1,0]:,}")
print(f"  True Positives (correct entry):      {cm[1,1]:,}")

# ======================== (Optional) Threshold Tuning on Validation ========================
# Enable ENABLE_AUTO_THRESHOLD above to pick a threshold that meets your target precision and
# minimum trade frequency. This chosen threshold will be used for test metrics and saved.
chosen_threshold = 0.5  # default
if ENABLE_AUTO_THRESHOLD:
    print(f"\n{'=' * 80}")
    print("THRESHOLD TUNING (Validation Set)")
    print(f"{'=' * 80}")
    thresholds = np.arange(THRESHOLD_SCAN_START, THRESHOLD_SCAN_STOP + 1e-9, THRESHOLD_SCAN_STEP)
    best = None
    fallback_40 = None
    best_f1 = (0.0, 0.5)  # (f1, threshold)
    for t in thresholds:
        pred_t = (y_val_pred_proba >= t).astype(int)
        prec_t = precision_score(y_val, pred_t, zero_division=0)
        rec_t = recall_score(y_val, pred_t, zero_division=0)
        f1_t = f1_score(y_val, pred_t, zero_division=0)
        trade_freq_t = pred_t.mean()
        # Track max F1 for fallback
        if f1_t > best_f1[0]:
            best_f1 = (f1_t, t)
        # Candidate meeting main targets
        if prec_t >= THRESHOLD_TARGET_PRECISION and trade_freq_t >= THRESHOLD_MIN_TRADE_FREQ:
            if (best is None) or (trade_freq_t > best['trade_freq']):
                best = {'t': t, 'precision': prec_t, 'recall': rec_t, 'f1': f1_t, 'trade_freq': trade_freq_t}
        # Fallback candidate for 40% precision
        if prec_t >= 0.40:
            if (fallback_40 is None) or (f1_t > fallback_40['f1']):
                fallback_40 = {'t': t, 'precision': prec_t, 'recall': rec_t, 'f1': f1_t, 'trade_freq': trade_freq_t}

    if best is not None:
        chosen_threshold = float(best['t'])
        print(f"\n✅ Selected threshold {chosen_threshold:.2f} on validation:")
        print(f"   Precision: {best['precision']:.1%} | Recall: {best['recall']:.1%} | F1: {best['f1']:.4f} | Trade %: {best['trade_freq']:.1%}")
        print("   Rationale: Meets target precision and min trade frequency; chose highest trade % among candidates.")
    elif fallback_40 is not None:
        chosen_threshold = float(fallback_40['t'])
        print(f"\n⚠️  Falling back to threshold {chosen_threshold:.2f} (>=40% precision):")
        print(f"   Precision: {fallback_40['precision']:.1%} | Recall: {fallback_40['recall']:.1%} | F1: {fallback_40['f1']:.4f} | Trade %: {fallback_40['trade_freq']:.1%}")
    else:
        # If nothing met targets, use a quantile-based threshold to guarantee at least
        # THRESHOLD_MIN_TRADE_FREQ trade rate on validation. This avoids degenerate
        # "always STAY OUT" behavior on low-calibrated models.
        q = max(0.0, 1.0 - THRESHOLD_MIN_TRADE_FREQ)
        quant_thr = float(np.quantile(y_val_pred_proba, q))
        chosen_threshold = quant_thr
        print(f"\n⚠️  No threshold met targets. Using {int(THRESHOLD_MIN_TRADE_FREQ*100)}th-percentile threshold: {chosen_threshold:.3f} "
              f"(~{THRESHOLD_MIN_TRADE_FREQ:.0%} trade rate target).")

print(f"\nUsing classification threshold: {chosen_threshold:.2f} (set ENABLE_AUTO_THRESHOLD=True to auto-tune)")

# ======================== Test Set Evaluation ========================
print(f"\n{'=' * 80}")
print(f"TEST SET PERFORMANCE (Unseen Data)")
print(f"{'=' * 80}")

y_test_pred_proba = model.predict_proba(X_test_scaled)[:, 1]
# Use the chosen threshold (0.5 by default or auto-tuned on validation if enabled)
y_test_pred = (y_test_pred_proba >= chosen_threshold).astype(int)

test_acc = accuracy_score(y_test, y_test_pred)
test_prec = precision_score(y_test, y_test_pred, zero_division=0)
test_rec = recall_score(y_test, y_test_pred, zero_division=0)
test_f1 = f1_score(y_test, y_test_pred, zero_division=0)
test_auc = roc_auc_score(y_test, y_test_pred_proba)
test_logloss = log_loss(y_test, y_test_pred_proba)

print(f"\nClassification Metrics:")
print(f"  Accuracy:   {test_acc:.4f}")
print(f"  Precision:  {test_prec:.4f}  ← CRITICAL: Win rate when model says ENTER")
print(f"  Recall:     {test_rec:.4f}  ← Coverage: % of winners captured")
print(f"  F1-Score:   {test_f1:.4f}")
print(f"  ROC-AUC:    {test_auc:.4f}  ← Discrimination power")
print(f"  Log Loss:   {test_logloss:.4f}")

cm_test = confusion_matrix(y_test, y_test_pred)
print(f"\nConfusion Matrix:")
print(f"                  Predicted: STAY OUT | Predicted: ENTER")
print(f"  Actual LOSS:        {cm_test[0,0]:5d}        |     {cm_test[0,1]:5d}")
print(f"  Actual WIN:         {cm_test[1,0]:5d}        |     {cm_test[1,1]:5d}")

print(f"\nDetailed Classification Report:")
print(classification_report(y_test, y_test_pred, 
                          target_names=['STAY OUT (0)', 'ENTER (1)'],
                          zero_division=0))

# Professional trader metrics
if test_prec > 0:
    win_rate_when_entering = test_prec
    trade_frequency = y_test_pred.sum() / len(y_test)
    print(f"\n💼 Live Trading Implications:")
    print(f"  Expected win rate when entering: {win_rate_when_entering:.1%}")
    print(f"  Expected trade frequency: {trade_frequency:.1%} of signals")
    print(f"  If precision < 0.55, re-tune threshold or add features")

# ======================== Feature Importance ========================
print(f"\n{'=' * 80}")
print(f"FEATURE IMPORTANCE ANALYSIS")
print(f"{'=' * 80}")

importance_df = pd.DataFrame({
    'Feature': INPUT_FEATURES,
    'Importance': model.feature_importances_
}).sort_values('Importance', ascending=False)

print(f"\nTop Features:")
for i, row in importance_df.iterrows():
    bar_len = int(row['Importance'] / importance_df['Importance'].max() * 40)
    bar = '█' * bar_len
    print(f"  {row['Feature']:30s} | {bar} {row['Importance']:7.1f}")

# ======================== Sample Predictions ========================
print(f"\n{'=' * 80}")
print(f"SAMPLE PREDICTIONS (Test Set)")
print(f"{'=' * 80}")

np.random.seed(42)
sample_idx = np.random.choice(len(X_test), min(8, len(X_test)), replace=False)

for i, idx in enumerate(sample_idx):
    actual = y_test.iloc[idx]
    proba = y_test_pred_proba[idx]
    pred = y_test_pred[idx]
    
    decision = "✅ ENTER" if pred == 1 else "❌ STAY OUT"
    actual_outcome = "WIN" if actual == 1 else "LOSS"
    correct = "✓" if pred == actual else "✗"
    
    print(f"\nSample {i+1}: {decision} @ {proba:.1%} confidence | Actual: {actual_outcome} {correct}")
    # Show key feature values
    sample = X_test.iloc[idx]
    print(
        f"  Breakout_Strength={sample['Breakout_Strength']:.6f}, "
        f"Hour={int(sample['Hour_of_Day'])}, "
        f"NY={int(sample['Is_NY_Session'])}, London={int(sample['Is_London_Session'])}, Asian={int(sample['Is_Asian_Session'])}"
    )

# ======================== Save Model ========================
print(f"\n{'=' * 80}")
print(f"SAVING PRODUCTION MODEL")
print(f"{'=' * 80}")

model_package = {
    'model': model,
    'scaler': scaler,
    'features': INPUT_FEATURES,
    'feature_count': len(INPUT_FEATURES),
    'target': TARGET,
    # >>> Saved decision threshold
    # This is the classification cutoff your live system will use.
    # Set ENABLE_AUTO_THRESHOLD=True above to auto-select from validation.
    # Otherwise it remains 0.50 by default.
    'threshold': float(chosen_threshold),
    'categorical_features': categorical_features,
    'performance': {
        'test_accuracy': test_acc,
        'test_precision': test_prec,
        'test_recall': test_rec,
        'test_f1': test_f1,
        'test_auc': test_auc,
        'test_logloss': test_logloss
    },
    'data_stats': {
        'train_samples': len(X_train),
        'val_samples': len(X_val),
        'test_samples': len(X_test),
        'train_win_rate': (y_train == 1).mean(),
        'test_win_rate': (y_test == 1).mean()
    },
    'feature_importance': importance_df.to_dict('records'),
    'training_date': pd.Timestamp.now().isoformat()
}

joblib.dump(model_package, MODEL_OUTPUT)
print(f"\n✅ Model saved: {MODEL_OUTPUT}")
print(f"   Model type: LightGBM Binary Classifier")
print(f"   Features: {len(INPUT_FEATURES)}")
print(f"   Test AUC: {test_auc:.4f}")
print(f"   Test Precision: {test_prec:.4f} (live win rate estimate)")

# ======================== DLL-Ready Prediction Function ========================
def predict_entry(symbol,
                  action,
                  hour_of_day,
                  is_ny_session,
                  is_asian_session,
                  is_london_session,
                  breakout_strength):
    """
    Production-ready prediction function for live trading (breakout regime model).

    Args (must match INPUT_FEATURES order exactly):
        symbol (int): encoded symbol ID (same encoding as training)
        action (int): encoded action ID (e.g., 0=SELL, 1=BUY) or as trained
        hour_of_day (int)
        is_ny_session (int 0/1)
        is_asian_session (int 0/1)
        is_london_session (int 0/1)
        breakout_strength (float)

    Returns:
        tuple: (should_enter: bool, confidence: float, probability: float)
    """
    model_data = joblib.load(MODEL_OUTPUT)
    clf = model_data['model']
    scaler = model_data['scaler']

    # Build feature vector (ensure numeric types)
    feature_vec = np.array([[
        symbol if isinstance(symbol, (int, float)) else 0,
        action if isinstance(action, (int, float)) else 0,
        int(hour_of_day),
        int(is_ny_session),
        int(is_asian_session),
        int(is_london_session),
        float(breakout_strength),
    ]])

    # Scale and predict
    feature_scaled = scaler.transform(feature_vec)
    probability = clf.predict_proba(feature_scaled)[0, 1]

    threshold = model_data['threshold']
    should_enter = probability >= threshold
    confidence = abs(probability - threshold) * 2  # 0-1 scale

    return should_enter, confidence, probability

print(f"\n{'=' * 80}")
print(f"✅ PRODUCTION MODEL READY FOR DEPLOYMENT")
print(f"{'=' * 80}")
print(f"Model learns from REAL outcomes—no synthetic heuristics")
print(f"Test precision: {test_prec:.1%} (expected live win rate)")
print(f"Test AUC: {test_auc:.3f} (discrimination quality)")
print(f"Use predict_entry() for DLL integration")
print(f"{'=' * 80}\n")