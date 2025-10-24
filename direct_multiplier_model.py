# simplified_model_training.py
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.multioutput import MultiOutputRegressor
from sklearn.preprocessing import RobustScaler
from sklearn.metrics import mean_absolute_error, r2_score, accuracy_score
import joblib
import warnings
warnings.filterwarnings('ignore')

print("=== SIMPLIFIED TRADING MODEL - 12 FEATURES ONLY ===")
print("Training model to predict: 1) Trade Yes/No, 2) SL Multiplier, 3) TP Multiplier")
print("Using ONLY 12 key features for DLL compatibility")

# Load data
df = pd.read_csv('cleaned_merged.csv', sep=';')
print(f"✅ Loaded {len(df):,} rows and {len(df.columns)} columns")

# Sort by time
if 'Time' in df.columns:
    df['Time'] = pd.to_datetime(df['Time'])
    df = df.sort_values('Time')

print("\n=== ANALYZING HISTORICAL OUTCOMES FOR PATTERN RECOGNITION ===")

# Analyze what market conditions led to success
profitable_trades = df[df['Profitable'] == 1]
losing_trades = df[df['Profitable'] == 0]

print(f"Profitable trades: {len(profitable_trades):,} ({len(profitable_trades)/len(df)*100:.1f}%)")
print(f"Losing trades: {len(losing_trades):,} ({len(losing_trades)/len(df)*100:.1f}%)")
print(f"Average profit: ${profitable_trades['Final_PnL'].mean():.2f}")
print(f"Average loss: ${losing_trades['Final_PnL'].mean():.2f}")

def analyze_market_patterns(df):
    """Analyze what market conditions historically led to success"""
    
    # Analyze RSI patterns
    profitable_rsi = profitable_trades['RSI14'].describe()
    losing_rsi = losing_trades['RSI14'].describe()
    
    # Analyze EMA diff patterns
    profitable_ema = profitable_trades['EMA_diff'].describe()
    losing_ema = losing_trades['EMA_diff'].describe()
    
    print(f"\nHistorical Success Patterns:")
    print(f"Profitable RSI range: {profitable_rsi['25%']:.1f} - {profitable_rsi['75%']:.1f}")
    print(f"Losing RSI range: {losing_rsi['25%']:.1f} - {losing_rsi['75%']:.1f}")
    print(f"Profitable EMA_diff: {profitable_ema['mean']:.4f} ± {profitable_ema['std']:.4f}")
    print(f"Losing EMA_diff: {losing_ema['mean']:.4f} ± {losing_ema['std']:.4f}")
    
    return {
        'good_rsi_min': profitable_rsi['25%'],
        'good_rsi_max': profitable_rsi['75%'], 
        'good_ema_threshold': abs(profitable_ema['50%'])
    }

patterns = analyze_market_patterns(df)

# DEFINE EXACT 12 FEATURES FOR THE MODEL
SELECTED_FEATURES = [
    'EMA_diff', 'RSI14', 'Ret_5', 'Range_Ratio', 
    'Pct_from_30h', 'Pct_from_30l', 'Consecutive_Bullish', 
    'Consecutive_Bearish', 'Avg_Body_Size', 'Avg_Range', 
    'Trend_Score', 'Momentum_Strength'
]

print(f"\n=== USING ONLY {len(SELECTED_FEATURES)} SELECTED FEATURES ===")
print(f"Features: {SELECTED_FEATURES}")

# Check if all features exist in the dataset
missing_features = [f for f in SELECTED_FEATURES if f not in df.columns]
if missing_features:
    print(f"❌ Missing features in dataset: {missing_features}")
    print(f"Available columns: {list(df.columns)}")
    exit(1)

# Use only the selected features
X = df[SELECTED_FEATURES].copy()

print(f"✅ Selected {len(X.columns)} features for training")
print(f"Feature columns: {list(X.columns)}")

# Clean data
X = X.replace([np.inf, -np.inf], np.nan)
X = X.fillna(X.median())

# Check feature statistics
print(f"\n=== FEATURE STATISTICS ===")
for feature in SELECTED_FEATURES:
    mean_val = X[feature].mean()
    std_val = X[feature].std()
    min_val = X[feature].min()
    max_val = X[feature].max()
    print(f"{feature}: {mean_val:.4f} ± {std_val:.4f} (range: {min_val:.4f} to {max_val:.4f})")

def create_simplified_targets(df, patterns):
    """Create targets based on simplified logic"""
    
    actual_sl_min, actual_sl_max = df['SL_ATR_Mult'].min(), df['SL_ATR_Mult'].max()
    actual_tp_min, actual_tp_max = df['TP_ATR_Mult'].min(), df['TP_ATR_Mult'].max()
    
    print(f"Using actual data ranges - SL: {actual_sl_min:.4f} to {actual_sl_max:.4f}")
    print(f"Using actual data ranges - TP: {actual_tp_min:.4f} to {actual_tp_max:.4f}")
    
    trade_decisions = []
    sl_multipliers = []
    tp_multipliers = []
    
    for idx, row in df.iterrows():
        rsi = row['RSI14']
        ema_diff = abs(row['EMA_diff'])
        momentum = row.get('Momentum_Strength', 0)
        trend_score = row.get('Trend_Score', 0)
        
        # Simplified decision logic based on key features
        market_score = 0
        
        # RSI scoring
        if patterns['good_rsi_min'] <= rsi <= patterns['good_rsi_max']:
            market_score += 0.4
        elif 40 <= rsi <= 60:  # Neutral zone
            market_score += 0.2
        
        # Trend strength scoring
        if ema_diff >= patterns['good_ema_threshold']:
            market_score += 0.3
        elif ema_diff >= patterns['good_ema_threshold'] * 0.5:
            market_score += 0.1
        
        # Momentum scoring
        if abs(momentum) > 0.5:
            market_score += 0.2
        elif abs(momentum) > 0.2:
            market_score += 0.1
        
        # Trend score consideration
        if abs(trend_score) > 0.3:
            market_score += 0.1
        
        # Trade decision threshold
        trade_decision = 1.0 if market_score >= 0.6 else 0.0
        
        # SL/TP based on volatility and momentum
        range_ratio = row.get('Range_Ratio', 1.0)
        
        # SL varies with volatility
        sl_mult = actual_sl_min + (actual_sl_max - actual_sl_min) * min(range_ratio, 1.0)
        if rsi > 70 or rsi < 30:  # Extreme RSI
            sl_mult *= 0.9  # Tighter stops
        
        # TP varies with trend and momentum
        tp_mult = actual_tp_min + (actual_tp_max - actual_tp_min) * (1 - min(range_ratio, 1.0))
        if abs(momentum) > 0.3:
            tp_mult *= 1.1  # More aggressive with momentum
        
        # Add slight randomness for variety
        sl_mult = np.clip(sl_mult + np.random.normal(0, 0.001), actual_sl_min, actual_sl_max)
        tp_mult = np.clip(tp_mult + np.random.normal(0, 0.005), actual_tp_min, actual_tp_max)
        
        trade_decisions.append(trade_decision)
        sl_multipliers.append(sl_mult)
        tp_multipliers.append(tp_mult)
    
    return np.array(trade_decisions), np.array(sl_multipliers), np.array(tp_multipliers)

print("\n=== CREATING SIMPLIFIED TARGETS ===")
np.random.seed(42)
trade_decisions, target_sl, target_tp = create_simplified_targets(df, patterns)

print(f"Trade Decision: {trade_decisions.min():.0f} - {trade_decisions.max():.0f}")
print(f"Trade percentage: {trade_decisions.mean()*100:.1f}%")
print(f"Target SL range: {target_sl.min():.4f} - {target_sl.max():.4f}")
print(f"Target TP range: {target_tp.min():.4f} - {target_tp.max():.4f}")

# Create 3-output target matrix
y = np.column_stack([trade_decisions, target_sl, target_tp])
print(f"Target shape: {y.shape}")

# Time series split
n_samples = len(df)
train_end = int(0.7 * n_samples)
val_end = int(0.85 * n_samples)

X_train = X.iloc[:train_end]
y_train = y[:train_end]
X_val = X.iloc[train_end:val_end]
y_val = y[train_end:val_end]
X_test = X.iloc[val_end:]
y_test = y[val_end:]

print(f"Training: {len(X_train)} samples")
print(f"Validation: {len(X_val)} samples") 
print(f"Test: {len(X_test)} samples")

# Scale features
scaler = RobustScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_val_scaled = scaler.transform(X_val)
X_test_scaled = scaler.transform(X_test)

print("\n=== TRAINING SIMPLIFIED MODELS ===")

# Simplified models for better generalization
models = {
    'RandomForest': MultiOutputRegressor(
        RandomForestRegressor(
            n_estimators=80,
            max_depth=6,
            min_samples_split=30,
            min_samples_leaf=15,
            max_features='sqrt',
            random_state=42,
            n_jobs=-1
        )
    ),
    'GradientBoosting': MultiOutputRegressor(
        GradientBoostingRegressor(
            n_estimators=80,
            learning_rate=0.08,
            max_depth=4,
            min_samples_split=30,
            subsample=0.85,
            random_state=42
        )
    )
}

results = {}

for name, model in models.items():
    print(f"\nTraining {name}...")
    
    model.fit(X_train_scaled, y_train)
    y_val_pred = model.predict(X_val_scaled)
    
    # Calculate metrics
    decision_pred = y_val_pred[:, 0]
    sl_pred = y_val_pred[:, 1]
    tp_pred = y_val_pred[:, 2]
    
    decision_actual = y_val[:, 0]
    sl_actual = y_val[:, 1]
    tp_actual = y_val[:, 2]
    
    decision_mae = mean_absolute_error(decision_actual, decision_pred)
    sl_mae = mean_absolute_error(sl_actual, sl_pred)
    tp_mae = mean_absolute_error(tp_actual, tp_pred)
    
    decision_r2 = r2_score(decision_actual, decision_pred)
    sl_r2 = r2_score(sl_actual, sl_pred)
    tp_r2 = r2_score(tp_actual, tp_pred)
    
    # Binary accuracy
    decision_binary = (decision_pred >= 0.5).astype(int)
    decision_actual_binary = decision_actual.astype(int)
    decision_accuracy = accuracy_score(decision_actual_binary, decision_binary)
    
    results[name] = {
        'model': model,
        'decision_accuracy': decision_accuracy,
        'sl_r2': sl_r2,
        'tp_r2': tp_r2,
        'combined_score': decision_accuracy + sl_r2 + tp_r2
    }
    
    print(f"  Decision Accuracy: {decision_accuracy:.4f}")
    print(f"  SL R²: {sl_r2:.4f}")
    print(f"  TP R²: {tp_r2:.4f}")

# Select best model
best_model_name = max(results.keys(), key=lambda x: results[x]['combined_score'])
best_model = results[best_model_name]['model']

print(f"\n=== BEST MODEL: {best_model_name} ===")

# Final test
y_test_pred = best_model.predict(X_test_scaled)
decision_test_pred = y_test_pred[:, 0]
sl_test_pred = y_test_pred[:, 1]
tp_test_pred = y_test_pred[:, 2]

decision_test_binary = (decision_test_pred >= 0.5).astype(int)
decision_actual_test_binary = y_test[:, 0].astype(int)
decision_test_accuracy = accuracy_score(decision_actual_test_binary, decision_test_binary)

sl_test_r2 = r2_score(y_test[:, 1], sl_test_pred)
tp_test_r2 = r2_score(y_test[:, 2], tp_test_pred)

print(f"Final Test Performance:")
print(f"Decision Accuracy: {decision_test_accuracy:.4f}")
print(f"SL R²: {sl_test_r2:.4f}")
print(f"TP R²: {tp_test_r2:.4f}")

# Save simplified model
print(f"\n=== SAVING SIMPLIFIED MODEL ===")
model_data = {
    'model': best_model,
    'scaler': scaler,
    'feature_names': SELECTED_FEATURES,
    'model_name': best_model_name,
    'patterns': patterns,
    'performance': {
        'decision_accuracy': decision_test_accuracy,
        'sl_r2': sl_test_r2,
        'tp_r2': tp_test_r2
    },
    'feature_count': len(SELECTED_FEATURES),
    'output_info': {
        'output_0': 'Trade Decision (0=No Trade, 1=Trade)',
        'output_1': f'SL Multiplier ({target_sl.min():.4f}-{target_sl.max():.4f})',
        'output_2': f'TP Multiplier ({target_tp.min():.4f}-{target_tp.max():.4f})'
    }
}

joblib.dump(model_data, 'simplified_trading_model.pkl')
print("✅ Simplified model saved as 'simplified_trading_model.pkl'")

# Test predictions
print(f"\n=== TESTING SIMPLIFIED MODEL ===")
def test_prediction(ema_diff, rsi14, ret_5=0, range_ratio=1.0):
    """Test prediction with simplified inputs"""
    
    # Create test feature vector
    test_features = np.array([[
        ema_diff,           # EMA_diff
        rsi14,              # RSI14
        ret_5,              # Ret_5
        range_ratio,        # Range_Ratio
        0.0,                # Pct_from_30h
        0.0,                # Pct_from_30l
        0,                  # Consecutive_Bullish
        0,                  # Consecutive_Bearish
        0.5,                # Avg_Body_Size 
        1.0,                # Avg_Range
        ema_diff * 10,      # Trend_Score
        (rsi14 - 50) / 10   # Momentum_Strength
    ]])
    
    # Scale and predict
    test_scaled = scaler.transform(test_features)
    prediction = best_model.predict(test_scaled)[0]
    
    decision = prediction[0]
    sl_mult = prediction[1]
    tp_mult = prediction[2]
    
    should_trade = decision >= 0.5
    
    return should_trade, sl_mult, tp_mult

# Test cases
test_cases = [
    (0.002, 45, 0.001, 1.0),   # Moderate trend, neutral RSI
    (0.005, 65, 0.002, 1.2),   # Strong trend, bullish RSI
    (0.001, 25, -0.001, 0.8),  # Weak trend, oversold RSI
    (-0.003, 75, 0.001, 1.1),  # Counter trend, overbought RSI
]

for i, (ema_diff, rsi14, ret_5, range_ratio) in enumerate(test_cases, 1):
    should_trade, sl_mult, tp_mult = test_prediction(ema_diff, rsi14, ret_5, range_ratio)
    trade_action = "TRADE" if should_trade else "NO TRADE"
    
    print(f"Test {i}: EMA={ema_diff:.3f}, RSI={rsi14}, Ret5={ret_5:.3f}")
    print(f"  → {trade_action}, SL={sl_mult:.4f}, TP={tp_mult:.4f}")

print("\n" + "="*60)
print("🎯 SIMPLIFIED TRADING MODEL COMPLETE!")
print("✅ Uses only 12 key features - perfect for DLL")
print("✅ Fast predictions with minimal complexity")
print("✅ Ready for MT5 DLL integration")
print("="*60)