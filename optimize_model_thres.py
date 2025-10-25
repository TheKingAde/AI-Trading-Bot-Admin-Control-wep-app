"""
THRESHOLD OPTIMIZATION FOR PARAMETER FILTER
===========================================
Find optimal probability threshold for adaptive SL/TP parameter filtering

Your use case: Filter bad parameter combinations before entering trades
Goal: Find threshold that gives 50%+ win rate while maintaining reasonable trade frequency

Model's job: Predict if current SL/TP multipliers + market conditions = profitable setup
"""

import pandas as pd
import numpy as np
import joblib
import matplotlib.pyplot as plt
from sklearn.metrics import precision_score, recall_score, f1_score, roc_curve, precision_recall_curve

print("=" * 80)
print("THRESHOLD OPTIMIZATION - ADAPTIVE PARAMETER FILTER")
print("Finding optimal cutoff for live trading parameter selection")
print("=" * 80)

# ======================== Load Trained Model ========================
print("\n📂 Loading trained model...")

MODEL_PATH = 'entry_decision_model.pkl'
model_data = joblib.load(MODEL_PATH)

model = model_data['model']
scaler = model_data['scaler']
features = model_data['features']

print(f"✅ Loaded model: {MODEL_PATH}")
print(f"   Trained: {model_data['training_date']}")
print(f"   Features: {len(features)}")
print(f"   Current threshold: {model_data['threshold']}")

# Load test data (already scaled in training script, but we'll reload for clarity)
import sqlite3
from pathlib import Path

DB_PATH = Path('data/training_data.db')
TABLE_NAME = 'trades_dataset'

conn = sqlite3.connect(DB_PATH)
df = pd.read_sql_query(f"SELECT * FROM {TABLE_NAME}", conn)
conn.close()

# Sort by time
if 'Time' in df.columns:
    df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
    df = df.sort_values('Time').reset_index(drop=True)

# Get test set (last 15%)
n_samples = len(df)
test_start = int(0.85 * n_samples)

# Convert numeric columns
numeric_cols = [col for col in features if col not in ['Symbol', 'Action', 'Use_BE']]
for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

# Convert target
df['Profitable'] = pd.to_numeric(df['Profitable'], errors='coerce')
if df['Profitable'].isna().all() or (df['Profitable'] == 0).all():
    if 'Outcome_Category' in df.columns:
        df['Profitable'] = df['Outcome_Category'].apply(lambda x: 1 if str(x).lower() == 'win' else 0)

X_test = df[features].iloc[test_start:].copy()
y_test = df['Profitable'].iloc[test_start:].copy()

# Encode categorical
for col in ['Symbol', 'Action', 'Use_BE']:
    if col in X_test.columns:
        if X_test[col].dtype == 'object' or X_test[col].dtype == 'bool':
            X_test[col] = pd.Categorical(X_test[col]).codes

# Clean and scale
X_test = X_test.replace([np.inf, -np.inf], np.nan)
for col in X_test.columns:
    if X_test[col].isna().sum() > 0:
        X_test[col] = X_test[col].fillna(X_test[col].median())

X_test_scaled = scaler.transform(X_test)
y_test = y_test.fillna(0).astype(int)

print(f"\n✅ Test set loaded: {len(X_test):,} samples")
print(f"   Win rate: {y_test.mean()*100:.1f}%")

# ======================== Get Predictions ========================
print("\n🔮 Generating probability predictions...")

y_proba = model.predict_proba(X_test_scaled)[:, 1]

print(f"✅ Predictions generated")
print(f"   Min probability: {y_proba.min():.3f}")
print(f"   Max probability: {y_proba.max():.3f}")
print(f"   Mean probability: {y_proba.mean():.3f}")

# ======================== Threshold Scan ========================
print("\n" + "=" * 80)
print("THRESHOLD OPTIMIZATION SCAN")
print("=" * 80)

thresholds_to_test = np.arange(0.35, 0.90, 0.05)
results = []

print(f"\n{'Threshold':<12} {'Precision':<12} {'Recall':<12} {'F1-Score':<12} {'Trade %':<12} {'Status':<15}")
print("-" * 80)

for threshold in thresholds_to_test:
    y_pred = (y_proba >= threshold).astype(int)
    
    precision = precision_score(y_test, y_pred, zero_division=0)
    recall = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    trade_freq = y_pred.sum() / len(y_pred)
    
    # Status indicators
    status = ""
    if precision >= 0.50:
        status += "✅ Good Win Rate"
    elif precision >= 0.40:
        status += "⚠️  Marginal"
    else:
        status += "❌ Too Low"
    
    if trade_freq < 0.05:
        status = "❌ Too Few Trades"
    
    results.append({
        'threshold': threshold,
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'trade_freq': trade_freq,
        'n_trades': int(y_pred.sum()),
        'status': status
    })
    
    print(f"{threshold:<12.2f} {precision:<12.2%} {recall:<12.2%} {f1:<12.4f} {trade_freq:<12.1%} {status:<15}")

results_df = pd.DataFrame(results)

# ======================== Find Optimal Thresholds ========================
print("\n" + "=" * 80)
print("RECOMMENDED THRESHOLDS FOR LIVE TRADING")
print("=" * 80)

# Conservative: 50%+ win rate
conservative = results_df[results_df['precision'] >= 0.50].sort_values('trade_freq', ascending=False).head(1)
if not conservative.empty:
    c = conservative.iloc[0]
    print(f"\n🎯 CONSERVATIVE (Recommended for Live)")
    print(f"   Threshold: {c['threshold']:.2f}")
    print(f"   Win Rate: {c['precision']:.1%} (when model says ENTER)")
    print(f"   Coverage: {c['recall']:.1%} (of all winning parameter combos)")
    print(f"   Trade Frequency: {c['trade_freq']:.1%} ({c['n_trades']:.0f} trades)")
    print(f"   Use Case: High confidence filter - only enter best setups")
else:
    print("\n⚠️  No threshold achieves 50%+ precision")
    print("   Model may need retraining with better class balancing")

# Balanced: 40%+ win rate with decent frequency
balanced = results_df[results_df['precision'] >= 0.40].sort_values('f1', ascending=False).head(1)
if not balanced.empty:
    b = balanced.iloc[0]
    print(f"\n⚖️  BALANCED")
    print(f"   Threshold: {b['threshold']:.2f}")
    print(f"   Win Rate: {b['precision']:.1%}")
    print(f"   Coverage: {b['recall']:.1%}")
    print(f"   Trade Frequency: {b['trade_freq']:.1%} ({b['n_trades']:.0f} trades)")
    print(f"   Use Case: Moderate filtering - balance quality vs quantity")

# Maximum F1: Best precision-recall balance
max_f1 = results_df.sort_values('f1', ascending=False).head(1)
if not max_f1.empty:
    m = max_f1.iloc[0]
    print(f"\n📊 MAXIMUM F1-SCORE")
    print(f"   Threshold: {m['threshold']:.2f}")
    print(f"   Win Rate: {m['precision']:.1%}")
    print(f"   Coverage: {m['recall']:.1%}")
    print(f"   Trade Frequency: {m['trade_freq']:.1%} ({m['n_trades']:.0f} trades)")
    print(f"   Use Case: Optimal statistical balance")

# Current baseline (0.50)
current = results_df[results_df['threshold'] == 0.50].iloc[0] if 0.50 in results_df['threshold'].values else None
if current is not None:
    print(f"\n📍 CURRENT (0.50 threshold)")
    print(f"   Win Rate: {current['precision']:.1%}")
    print(f"   Coverage: {current['recall']:.1%}")
    print(f"   Trade Frequency: {current['trade_freq']:.1%} ({current['n_trades']:.0f} trades)")

# ======================== Visualizations ========================
print("\n📊 Generating optimization charts...")

fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle('Threshold Optimization for Adaptive Parameter Filter', fontsize=16, fontweight='bold')

# 1. Precision vs Threshold
ax1.plot(results_df['threshold'], results_df['precision'], 'b-', linewidth=2, label='Precision (Win Rate)')
ax1.axhline(y=0.50, color='g', linestyle='--', label='Target: 50% Win Rate')
ax1.axhline(y=0.40, color='orange', linestyle='--', label='Marginal: 40%')
ax1.set_xlabel('Threshold', fontsize=12)
ax1.set_ylabel('Precision (Win Rate)', fontsize=12)
ax1.set_title('Win Rate vs Threshold', fontweight='bold')
ax1.grid(True, alpha=0.3)
ax1.legend()

# 2. Trade Frequency vs Threshold
ax2.plot(results_df['threshold'], results_df['trade_freq'] * 100, 'r-', linewidth=2)
ax2.set_xlabel('Threshold', fontsize=12)
ax2.set_ylabel('Trade Frequency (%)', fontsize=12)
ax2.set_title('Trade Frequency vs Threshold', fontweight='bold')
ax2.grid(True, alpha=0.3)

# 3. Precision-Recall Trade-off
ax3.plot(results_df['recall'], results_df['precision'], 'mo-', linewidth=2)
ax3.set_xlabel('Recall (Coverage of Winners)', fontsize=12)
ax3.set_ylabel('Precision (Win Rate)', fontsize=12)
ax3.set_title('Precision-Recall Trade-off', fontweight='bold')
ax3.grid(True, alpha=0.3)

# Mark important points
if not conservative.empty:
    ax3.scatter(conservative['recall'].values[0], conservative['precision'].values[0], 
               s=200, c='green', marker='*', label='Conservative', zorder=5)
if not balanced.empty:
    ax3.scatter(balanced['recall'].values[0], balanced['precision'].values[0], 
               s=200, c='orange', marker='s', label='Balanced', zorder=5)
ax3.legend()

# 4. F1-Score vs Threshold
ax4.plot(results_df['threshold'], results_df['f1'], 'g-', linewidth=2)
ax4.set_xlabel('Threshold', fontsize=12)
ax4.set_ylabel('F1-Score', fontsize=12)
ax4.set_title('F1-Score vs Threshold', fontweight='bold')
ax4.grid(True, alpha=0.3)

if not max_f1.empty:
    ax4.axvline(x=max_f1['threshold'].values[0], color='red', linestyle='--', 
                label=f'Optimal: {max_f1["threshold"].values[0]:.2f}')
    ax4.legend()

plt.tight_layout()
plt.savefig('threshold_optimization.png', dpi=300, bbox_inches='tight')
print(f"✅ Chart saved: threshold_optimization.png")

# ======================== Probability Distribution Analysis ========================
print("\n" + "=" * 80)
print("PROBABILITY DISTRIBUTION ANALYSIS")
print("=" * 80)

fig2, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
fig2.suptitle('Model Probability Distribution', fontsize=16, fontweight='bold')

# Winners vs Losers
winners_proba = y_proba[y_test == 1]
losers_proba = y_proba[y_test == 0]

ax1.hist(losers_proba, bins=50, alpha=0.6, color='red', label='Losses', density=True)
ax1.hist(winners_proba, bins=50, alpha=0.6, color='green', label='Wins', density=True)
ax1.set_xlabel('Predicted Probability', fontsize=12)
ax1.set_ylabel('Density', fontsize=12)
ax1.set_title('Probability Distribution: Wins vs Losses', fontweight='bold')
ax1.legend()
ax1.grid(True, alpha=0.3)

# Cumulative distribution
ax2.hist(y_proba, bins=50, cumulative=True, alpha=0.7, color='blue', density=True)
ax2.set_xlabel('Predicted Probability', fontsize=12)
ax2.set_ylabel('Cumulative Proportion', fontsize=12)
ax2.set_title('Cumulative Distribution of Predictions', fontweight='bold')
ax2.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('probability_distribution.png', dpi=300, bbox_inches='tight')
print(f"✅ Chart saved: probability_distribution.png")

print(f"\n   Winners - Mean prob: {winners_proba.mean():.3f}, Std: {winners_proba.std():.3f}")
print(f"   Losers  - Mean prob: {losers_proba.mean():.3f}, Std: {losers_proba.std():.3f}")
print(f"   Separation: {abs(winners_proba.mean() - losers_proba.mean()):.3f}")

# ======================== Recommendations ========================
print("\n" + "=" * 80)
print("LIVE TRADING RECOMMENDATIONS")
print("=" * 80)

print("\n📌 Your Use Case: Adaptive SL/TP Parameter Filter")
print("   The model learned which parameter combinations work in different market conditions")

if not conservative.empty:
    c = conservative.iloc[0]
    print(f"\n✅ RECOMMENDED FOR LIVE TRADING:")
    print(f"   Threshold: {c['threshold']:.2f}")
    print(f"   Expected win rate: {c['precision']:.1%}")
    print(f"   Expected trade frequency: {c['trade_freq']:.1%}")
    print(f"\n   Implementation:")
    print(f"   1. Your EA calculates all 21 features for current market state")
    print(f"   2. EA sends features + proposed SL/TP multipliers to model")
    print(f"   3. If probability >= {c['threshold']:.2f} → ENTER with those parameters")
    print(f"   4. If probability < {c['threshold']:.2f} → SKIP or try different parameters")
else:
    print("\n⚠️  WARNING: Model cannot achieve 50%+ win rate at any threshold")
    print("   Recommendations:")
    print("   1. Retrain with higher scale_pos_weight (5.0-10.0)")
    print("   2. Add more predictive features (order flow, multi-timeframe)")
    print("   3. Collect more winning parameter combinations in backtest")
    print("   4. Consider ensemble models or neural networks")

print("\n" + "=" * 80)
print("✅ OPTIMIZATION COMPLETE")
print("=" * 80)
print(f"Review the charts and choose your threshold based on risk tolerance")
print(f"Update model_data['threshold'] in entry_decision_model.pkl if desired")
