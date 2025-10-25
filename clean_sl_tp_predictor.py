"""
ENTRY DECISION BINARY CLASSIFIER - Production Grade
====================================================
Single objective: Predict whether to ENTER a trade or STAY OUT

Uses REAL outcomes from historical trades (Profitable=1/0 label)
NO synthetic scoring—the model learns directly from market reality

Features: 21 market context indicators
Target: Profitable (1=Win, 0=Loss)
Output: Binary decision with confidence score
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
print("PRODUCTION-GRADE ENTRY DECISION CLASSIFIER")
print("Objective: ENTER vs STAY OUT (Binary Classification)")
print("Learning from REAL trade outcomes—NO synthetic rules")
print("=" * 80)

# ======================== Configuration ========================
DB_PATH = Path('data/training_data.db')
TABLE_NAME = 'trades_dataset'
MODEL_OUTPUT = 'entry_decision_model.pkl'

# Features for prediction (21 features - EXCLUDE target variables)
INPUT_FEATURES = [
    'Symbol', 'Action', 'ATR_rel', 'EMA_diff', 'RSI14', 'Range_Ratio',
    'Pct_from_30h', 'Pct_from_30l', 'Breakout_level_atr_multiplier',
    'SL_ATR_Mult', 'TP_ATR_Mult', 'Use_BE', 'Risk_Reward_Ratio',
    'High_Volatility', 'Day_of_Week', 'Consecutive_Bullish',
    'Consecutive_Bearish', 'Avg_Body_Size', 'Avg_Range',
    'Trend_Score', 'Momentum_Strength'
]

TARGET = 'Profitable'  # Binary: 1=Win, 0=Loss

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


# Sort chronologically for time-series split
if 'Time' in df.columns:
    df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
    df = df.sort_values('Time').reset_index(drop=True)
    print("✅ Data sorted chronologically")

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
numeric_cols = [col for col in INPUT_FEATURES if col not in ['Symbol', 'Action', 'Use_BE']]

for col in numeric_cols:
    if col in df.columns:
        # Convert to numeric, coercing errors to NaN
        df[col] = pd.to_numeric(df[col], errors='coerce')

# Convert target column with fallback to Outcome_Category
if TARGET in df.columns:
    df[TARGET] = pd.to_numeric(df[TARGET], errors='coerce')
    
    # If Profitable is all NaN or all zeros, try to derive from Outcome_Category
    if df[TARGET].isna().all() or (df[TARGET] == 0).all():
        print(f"⚠️  Profitable column is empty/invalid, using Outcome_Category as fallback...")
        if 'Outcome_Category' in df.columns:
            # Map Outcome_Category: "Win" -> 1, anything else -> 0
            df[TARGET] = df['Outcome_Category'].apply(lambda x: 1 if str(x).lower() == 'win' else 0)
            print(f"✅ Derived Profitable from Outcome_Category")

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
for col in ['Symbol', 'Action', 'Use_BE']:
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
print(f"\n📈 Feature Summary Statistics (first 10):")
print(X.describe().iloc[:, :10].T[['mean', 'std', 'min', 'max']])


# ======================== Time-Based Train/Val/Test Split ========================
print(f"\n📊 Creating time-based train/validation/test split...")
print("   (Respects chronological order—no data leakage)")

n_samples = len(df)
train_end = int(0.70 * n_samples)  # 70% train
val_end = int(0.85 * n_samples)    # 15% val, 15% test

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

# Calculate class weight for imbalanced data
class_weight = (y_train == 0).sum() / (y_train == 1).sum()
print(f"   Class imbalance ratio: {class_weight:.2f}:1 (loss:win)")

model = lgb.LGBMClassifier(
    objective='binary',
    metric='auc',
    boosting_type='gbdt',
    num_leaves=31,
    max_depth=6,
    learning_rate=0.05,
    n_estimators=500,
    feature_fraction=0.9,
    bagging_fraction=0.8,
    bagging_freq=5,
    min_child_samples=20,
    scale_pos_weight=class_weight,  # Handle imbalance
    reg_alpha=0.1,
    reg_lambda=0.1,
    verbose=-1,
    random_state=42
)

print(f"   Training with early stopping (50 rounds patience)...")
model.fit(
    X_train_scaled, y_train,
    eval_set=[(X_val_scaled, y_val)],
    eval_metric='auc',
    callbacks=[lgb.early_stopping(stopping_rounds=50, verbose=False)]
)

print(f"✅ Training complete | Best iteration: {model.best_iteration_} | Best score: {model.best_score_['valid_0']['auc']:.4f}")

# ======================== Validation Metrics ========================
print(f"\n{'=' * 80}")
print(f"VALIDATION SET PERFORMANCE")
print(f"{'=' * 80}")

y_val_pred_proba = model.predict_proba(X_val_scaled)[:, 1]
y_val_pred = (y_val_pred_proba >= 0.5).astype(int)

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

# ======================== Test Set Evaluation ========================
print(f"\n{'=' * 80}")
print(f"TEST SET PERFORMANCE (Unseen Data)")
print(f"{'=' * 80}")

y_test_pred_proba = model.predict_proba(X_test_scaled)[:, 1]
y_test_pred = (y_test_pred_proba >= 0.5).astype(int)

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

print(f"\nTop 15 Most Important Features:")
for i, row in importance_df.head(15).iterrows():
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
    print(f"  RSI14={sample['RSI14']:.1f}, EMA_diff={sample['EMA_diff']:.5f}, "
          f"Range_Ratio={sample['Range_Ratio']:.2f}, RR={sample['Risk_Reward_Ratio']:.2f}")

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
    'threshold': 0.5,
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
def predict_entry(symbol, action, atr_rel, ema_diff, rsi14, range_ratio,
                  pct_from_30h, pct_from_30l, breakout_atr_mult,
                  sl_atr_mult, tp_atr_mult, use_be, risk_reward_ratio,
                  high_volatility, day_of_week, consecutive_bullish,
                  consecutive_bearish, avg_body_size, avg_range,
                  trend_score, momentum_strength):
    """
    Production-ready prediction function for live trading.
    
    Args:
        21 feature parameters matching INPUT_FEATURES order
    
    Returns:
        tuple: (should_enter: bool, confidence: float, probability: float)
            - should_enter: True = Enter trade, False = Stay out
            - confidence: 0-1 how confident (distance from threshold)
            - probability: Raw model probability of winning
    """
    model_data = joblib.load(MODEL_OUTPUT)
    clf = model_data['model']
    scaler = model_data['scaler']
    
    # Build feature vector (must match training order exactly)
    feature_vec = np.array([[
        symbol if isinstance(symbol, (int, float)) else 0,  # Encoded
        action if isinstance(action, (int, float)) else 0,  # Encoded
        atr_rel, ema_diff, rsi14, range_ratio,
        pct_from_30h, pct_from_30l, breakout_atr_mult,
        sl_atr_mult, tp_atr_mult,
        1 if use_be else 0,
        risk_reward_ratio, high_volatility, day_of_week,
        consecutive_bullish, consecutive_bearish,
        avg_body_size, avg_range, trend_score, momentum_strength
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