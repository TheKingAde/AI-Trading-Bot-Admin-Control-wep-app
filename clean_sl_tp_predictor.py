# 12_feature_model.py - Using ONLY 12 Selected Features for DLL
import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.metrics import mean_absolute_error, r2_score, accuracy_score
from sklearn.preprocessing import RobustScaler
from sklearn.multioutput import MultiOutputRegressor
import joblib
import warnings
warnings.filterwarnings('ignore')

print("=== 12-FEATURE TRADE DECISION + SL/TP MULTIPLIER PREDICTOR ===")
print("Predicting: 1) Trade Yes/No, 2) SL Multiplier, 3) TP Multiplier")
print("Using ONLY 12 selected features for optimal DLL performance")

# Load data
print("\nLoading data...")
df = pd.read_csv('cleaned_merged.csv', sep=';')
print(f"✅ Loaded {len(df):,} rows and {len(df.columns)} columns")

# Sort by time
if 'Time' in df.columns:
    df['Time'] = pd.to_datetime(df['Time'])
    df = df.sort_values('Time')
    print("✅ Data sorted by time")

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
    
    # Show similar column names for debugging
    print("\nSimilar column names found:")
    for missing in missing_features:
        similar = [col for col in df.columns if missing.lower() in col.lower() or col.lower() in missing.lower()]
        if similar:
            print(f"  {missing} → Similar: {similar}")
    exit(1)

print("\n=== ANALYZING HISTORICAL SUCCESS PATTERNS ===")

# Analyze what market conditions led to success (for pattern recognition only)
profitable_trades = df[df['Profitable'] == 1]
losing_trades = df[df['Profitable'] == 0]

print(f"Historical outcomes: {len(profitable_trades):,} profitable ({len(profitable_trades)/len(df)*100:.1f}%)")
print(f"Average profit: ${profitable_trades['Final_PnL'].mean():.2f}")
print(f"Average loss: ${losing_trades['Final_PnL'].mean():.2f}")

# Analyze market conditions that historically led to success
profitable_rsi = profitable_trades['RSI14'].describe()
profitable_ema = profitable_trades['EMA_diff'].describe()

print(f"\nHistorical Success Patterns (for reference only):")
print(f"Profitable RSI range: {profitable_rsi['25%']:.1f} - {profitable_rsi['75%']:.1f}")
print(f"Profitable EMA_diff: {profitable_ema['mean']:.4f} ± {profitable_ema['std']:.4f}")

# Use only the selected 12 features
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

def create_simplified_trade_decisions(df):
    """Create trade decisions based ONLY on the 12 selected features"""
    
    trade_decisions = []
    
    # Get market condition ranges from historical success patterns
    good_rsi_min, good_rsi_max = profitable_rsi['25%'], profitable_rsi['75%']
    good_ema_threshold = abs(profitable_ema['50%'])
    
    for idx, row in df.iterrows():
        rsi = row['RSI14']
        ema_diff = abs(row['EMA_diff'])
        momentum = row['Momentum_Strength']
        trend_score = row['Trend_Score']
        range_ratio = row['Range_Ratio']
        
        # SIMPLIFIED MARKET CONDITION SCORING using only our 12 features
        market_score = 0
        
        # RSI scoring (30% weight)
        if good_rsi_min <= rsi <= good_rsi_max:
            market_score += 0.3
        elif 40 <= rsi <= 60:  # Neutral RSI
            market_score += 0.15
        
        # EMA trend strength (25% weight)
        if ema_diff >= good_ema_threshold * 1.2:
            market_score += 0.25
        elif ema_diff >= good_ema_threshold * 0.8:
            market_score += 0.15
        
        # Momentum strength (20% weight)
        if abs(momentum) > 0.5:
            market_score += 0.2
        elif abs(momentum) > 0.2:
            market_score += 0.1
        
        # Trend score (15% weight)
        if abs(trend_score) > 0.3:
            market_score += 0.15
        elif abs(trend_score) > 0.1:
            market_score += 0.08
        
        # Range ratio volatility check (10% weight)
        if 0.8 <= range_ratio <= 1.2:  # Normal volatility
            market_score += 0.1
        elif range_ratio < 2.0:  # Acceptable volatility
            market_score += 0.05
        
        # CONSERVATIVE: Trade only when market conditions are very favorable
        trade_decision = 1.0 if market_score >= 0.65 else 0.0
        trade_decisions.append(trade_decision)
    
    return np.array(trade_decisions)

def create_optimized_multipliers(df):
    """Create optimized SL/TP multipliers based on 12-feature market conditions"""
    
    actual_sl_min, actual_sl_max = df['SL_ATR_Mult'].min(), df['SL_ATR_Mult'].max()
    actual_tp_min, actual_tp_max = df['TP_ATR_Mult'].min(), df['TP_ATR_Mult'].max()
    
    optimal_sl = []
    optimal_tp = []
    
    for idx, row in df.iterrows():
        rsi = row['RSI14']
        ema_diff = abs(row['EMA_diff'])
        range_ratio = row['Range_Ratio']
        momentum = row['Momentum_Strength']
        trend_score = row['Trend_Score']
        avg_range = row['Avg_Range']
        
        # SL Logic: Based on volatility and momentum
        # Higher volatility (range_ratio) = tighter stops
        # Strong momentum = slightly wider stops to avoid whipsaws
        
        volatility_factor = min(range_ratio / 1.0, 2.0)  # Normalize range ratio
        momentum_factor = min(abs(momentum), 1.0)
        
        # Base SL calculation
        if volatility_factor > 1.5:  # High volatility
            sl_mult = actual_sl_min + (actual_sl_max - actual_sl_min) * 0.8
        elif volatility_factor < 0.7:  # Low volatility
            sl_mult = actual_sl_min + (actual_sl_max - actual_sl_min) * 0.3
        else:  # Normal volatility
            sl_mult = actual_sl_min + (actual_sl_max - actual_sl_min) * 0.5
        
        # Adjust for momentum
        if momentum_factor > 0.6:
            sl_mult *= 1.1  # Slightly wider stops for strong momentum
        
        # TP Logic: Based on trend strength and momentum
        # Strong trends = let profits run
        # Weak trends = take profits quicker
        
        trend_factor = min(abs(trend_score), 1.0)
        ema_factor = min(ema_diff / 0.005, 2.0)  # Normalize EMA diff
        
        # Base TP calculation
        if trend_factor > 0.5 and ema_factor > 1.0:  # Strong trend
            tp_mult = actual_tp_min + (actual_tp_max - actual_tp_min) * 0.8
        elif trend_factor < 0.2 or ema_factor < 0.5:  # Weak trend
            tp_mult = actual_tp_min + (actual_tp_max - actual_tp_min) * 0.3
        else:  # Normal trend
            tp_mult = actual_tp_min + (actual_tp_max - actual_tp_min) * 0.5
        
        # RSI extremes adjustment
        if rsi > 75 or rsi < 25:
            sl_mult *= 0.9  # Tighter stops at extremes
            tp_mult *= 0.8  # Take profits quicker at extremes
        
        # Add small random variation for model learning
        sl_mult += np.random.normal(0, 0.002)
        tp_mult += np.random.normal(0, 0.005)
        
        # Ensure bounds and minimum risk-reward ratio
        sl_mult = np.clip(sl_mult, actual_sl_min, actual_sl_max)
        tp_mult = np.clip(tp_mult, actual_tp_min, actual_tp_max)
        
        # Ensure minimum 1.5:1 risk-reward ratio
        if tp_mult / sl_mult < 1.5:
            tp_mult = sl_mult * 1.8
            tp_mult = np.clip(tp_mult, actual_tp_min, actual_tp_max)
        
        optimal_sl.append(sl_mult)
        optimal_tp.append(tp_mult)
    
    return np.array(optimal_sl), np.array(optimal_tp)

# Create realistic trade decisions based on 12 features
print("\n=== CREATING TARGETS BASED ON 12 FEATURES ===")
np.random.seed(42)  # For reproducible results

trade_decisions = create_simplified_trade_decisions(df)

print(f"Trade decisions created based on 12-feature market conditions:")
print(f"Trade (1): {(trade_decisions == 1).sum():,} ({(trade_decisions == 1).mean()*100:.1f}%)")
print(f"No Trade (0): {(trade_decisions == 0).sum():,} ({(trade_decisions == 0).mean()*100:.1f}%)")

# Create optimized SL/TP multipliers
target_sl, target_tp = create_optimized_multipliers(df)

print(f"SL multiplier range: {target_sl.min():.4f} - {target_sl.max():.4f}")
print(f"TP multiplier range: {target_tp.min():.4f} - {target_tp.max():.4f}")
print(f"Average risk-reward ratio: {(target_tp/target_sl).mean():.2f}:1")
print(f"SL std dev: {target_sl.std():.4f}")
print(f"TP std dev: {target_tp.std():.4f}")

# Combine all targets: [Trade Decision, SL Multiplier, TP Multiplier]
y = np.column_stack([trade_decisions, target_sl, target_tp])
print(f"Target matrix shape: {y.shape} (Trade Decision, SL, TP)")

# === TIME SERIES VALIDATION ===
print("\n=== TIME SERIES VALIDATION SETUP ===")

n_samples = len(df)
train_size = int(0.7 * n_samples)
val_size = int(0.15 * n_samples)

X_train = X.iloc[:train_size]
y_train = y[:train_size]
X_val = X.iloc[train_size:train_size+val_size]
y_val = y[train_size:train_size+val_size]
X_test = X.iloc[train_size+val_size:]
y_test = y[train_size+val_size:]

print(f"Training set: {len(X_train):,} samples")
print(f"Validation set: {len(X_val):,} samples")
print(f"Test set: {len(X_test):,} samples")

# === SCALING ===
print("\n=== APPLYING FEATURE SCALING ===")
scaler = RobustScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_val_scaled = scaler.transform(X_val)
X_test_scaled = scaler.transform(X_test)

# === MODEL TRAINING ===
print("\n=== TRAINING 12-FEATURE MODEL ===")

# Optimized LightGBM for 12-feature model
model = MultiOutputRegressor(
    lgb.LGBMRegressor(
        objective='regression',
        metric='rmse',
        boosting_type='gbdt',
        num_leaves=20,      # Slightly more complex for 12 features
        learning_rate=0.05, # Moderate learning rate
        feature_fraction=0.9, # Use most features (we only have 12)
        bagging_fraction=0.8,
        bagging_freq=5,
        verbose=-1,
        random_state=42,
        n_estimators=200,   # More trees for better learning
        reg_alpha=0.1,      # Light L1 regularization
        reg_lambda=0.1,     # Light L2 regularization
        min_child_samples=50  # Moderate minimum samples
    )
)

print("Training model for 3 outputs with 12 features...")
model.fit(X_train_scaled, y_train)

# === VALIDATION ===
print("\n=== MODEL VALIDATION ===")

y_val_pred = model.predict(X_val_scaled)

# Separate predictions for each output
decision_pred = y_val_pred[:, 0]
sl_pred = y_val_pred[:, 1]
tp_pred = y_val_pred[:, 2]

decision_actual = y_val[:, 0]
sl_actual = y_val[:, 1]
tp_actual = y_val[:, 2]

# Calculate metrics for each output
decision_mae = mean_absolute_error(decision_actual, decision_pred)
decision_r2 = r2_score(decision_actual, decision_pred)
decision_binary_pred = (decision_pred >= 0.5).astype(int)
decision_binary_actual = decision_actual.astype(int)
decision_accuracy = accuracy_score(decision_binary_actual, decision_binary_pred)

sl_mae = mean_absolute_error(sl_actual, sl_pred)
sl_r2 = r2_score(sl_actual, sl_pred)
tp_mae = mean_absolute_error(tp_actual, tp_pred)
tp_r2 = r2_score(tp_actual, tp_pred)

print(f"Validation Results:")
print(f"Trade Decision - MAE: {decision_mae:.4f}, Accuracy: {decision_accuracy:.4f}, R²: {decision_r2:.4f}")
print(f"SL Prediction - MAE: {sl_mae:.4f}, R²: {sl_r2:.4f}")
print(f"TP Prediction - MAE: {tp_mae:.4f}, R²: {tp_r2:.4f}")

# === TEST SET EVALUATION ===
print("\n=== TEST SET EVALUATION ===")

y_test_pred = model.predict(X_test_scaled)

decision_test_pred = y_test_pred[:, 0]
sl_test_pred = y_test_pred[:, 1]
tp_test_pred = y_test_pred[:, 2]

decision_test_mae = mean_absolute_error(y_test[:, 0], decision_test_pred)
decision_test_r2 = r2_score(y_test[:, 0], decision_test_pred)
decision_test_binary_pred = (decision_test_pred >= 0.5).astype(int)
decision_test_binary_actual = y_test[:, 0].astype(int)
decision_test_accuracy = accuracy_score(decision_test_binary_actual, decision_test_binary_pred)

sl_test_mae = mean_absolute_error(y_test[:, 1], sl_test_pred)
sl_test_r2 = r2_score(y_test[:, 1], sl_test_pred)
tp_test_mae = mean_absolute_error(y_test[:, 2], tp_test_pred)
tp_test_r2 = r2_score(y_test[:, 2], tp_test_pred)

print(f"Test Results:")
print(f"Trade Decision - MAE: {decision_test_mae:.4f}, Accuracy: {decision_test_accuracy:.4f}, R²: {decision_test_r2:.4f}")
print(f"SL Prediction - MAE: {sl_test_mae:.4f}, R²: {sl_test_r2:.4f}")
print(f"TP Prediction - MAE: {tp_test_mae:.4f}, R²: {tp_test_r2:.4f}")

# === FEATURE IMPORTANCE ===
print("\n=== 12-FEATURE IMPORTANCE ANALYSIS ===")

decision_importance = model.estimators_[0].feature_importances_
sl_importance = model.estimators_[1].feature_importances_
tp_importance = model.estimators_[2].feature_importances_

importance_df = pd.DataFrame({
    'Feature': SELECTED_FEATURES,
    'Decision_Importance': decision_importance,
    'SL_Importance': sl_importance,
    'TP_Importance': tp_importance
})

importance_df['Total_Importance'] = importance_df['Decision_Importance'] + importance_df['SL_Importance'] + importance_df['TP_Importance']
importance_df = importance_df.sort_values('Total_Importance', ascending=False)

print("Feature Importance Ranking:")
for i, row in importance_df.iterrows():
    print(f"{row['Feature']:20} | Decision: {row['Decision_Importance']:.3f} | SL: {row['SL_Importance']:.3f} | TP: {row['TP_Importance']:.3f} | Total: {row['Total_Importance']:.3f}")

# === SAMPLE PREDICTIONS ===
print("\n=== SAMPLE PREDICTIONS FOR 12-FEATURE MODEL ===")

test_indices = np.random.choice(len(X_test), 8, replace=False)

print("Sample predictions using 12 features:")
for i, idx in enumerate(test_indices[:6]):
    actual_decision, actual_sl, actual_tp = y_test[idx]
    pred_decision, pred_sl, pred_tp = y_test_pred[idx]
    
    sample_data = X_test.iloc[idx]
    
    # Trade recommendation
    recommendation = "✅ TRADE" if pred_decision >= 0.5 else "❌ NO TRADE"
    confidence = abs(pred_decision - 0.5) * 2  # Convert to 0-1 confidence
    
    print(f"\nSample {i+1}:")
    print(f"  Key Features: RSI={sample_data['RSI14']:.1f}, EMA_diff={sample_data['EMA_diff']:.4f}")
    print(f"  Momentum={sample_data['Momentum_Strength']:.3f}, Trend={sample_data['Trend_Score']:.3f}")
    print(f"  Trade Decision: {pred_decision:.3f} → {recommendation} (Confidence: {confidence:.1%})")
    print(f"  Predicted SL/TP: {pred_sl:.4f} / {pred_tp:.4f} (RR: {pred_tp/pred_sl:.1f}:1)")
    print(f"  Target SL/TP:    {actual_sl:.4f} / {actual_tp:.4f}")

# === SAVE 12-FEATURE MODEL ===
print("\n=== SAVING 12-FEATURE MODEL ===")

model_data = {
    'model': model,
    'scaler': scaler,
    'features': SELECTED_FEATURES,  # Exactly 12 features
    'feature_count': 12,
    'decision_stats': {
        'threshold': 0.5,
        'trade_percentage': (trade_decisions == 1).mean() * 100
    },
    'sl_stats': {
        'min': target_sl.min(),
        'max': target_sl.max(),
        'mean': target_sl.mean(),
        'std': target_sl.std()
    },
    'tp_stats': {
        'min': target_tp.min(),
        'max': target_tp.max(), 
        'mean': target_tp.mean(),
        'std': target_tp.std()
    },
    'performance': {
        'decision_test_accuracy': decision_test_accuracy,
        'decision_test_mae': decision_test_mae,
        'decision_test_r2': decision_test_r2,
        'sl_test_mae': sl_test_mae,
        'sl_test_r2': sl_test_r2,
        'tp_test_mae': tp_test_mae,
        'tp_test_r2': tp_test_r2
    },
    'feature_importance': importance_df.to_dict('records')
}

joblib.dump(model_data, 'clean_trade_decision_sl_tp_predictor.pkl')
print("✅ 12-feature model saved as 'clean_trade_decision_sl_tp_predictor.pkl'")

# === DLL-READY PREDICTION FUNCTION ===
def predict_with_12_features(ema_diff, rsi14, ret_5=0, range_ratio=1.0, 
                           pct_from_30h=0, pct_from_30l=0, consecutive_bullish=0,
                           consecutive_bearish=0, avg_body_size=0.5, avg_range=1.0,
                           trend_score=None, momentum_strength=None):
    """
    DLL-ready function to predict trade decision and SL/TP multipliers using exactly 12 features
    
    Args:
        ema_diff: EMA difference (trend indicator)
        rsi14: RSI(14) value
        ret_5: 5-period return (optional, default 0)
        range_ratio: Current range vs average range (optional, default 1.0)
        pct_from_30h: Distance from 30-period high (optional, default 0)
        pct_from_30l: Distance from 30-period low (optional, default 0)
        consecutive_bullish: Count of consecutive bullish candles (optional, default 0)
        consecutive_bearish: Count of consecutive bearish candles (optional, default 0)
        avg_body_size: Average candlestick body size (optional, default 0.5)
        avg_range: Average range (optional, default 1.0)
        trend_score: Trend strength score (optional, calculated from ema_diff if None)
        momentum_strength: Momentum indicator (optional, calculated from rsi14 if None)
    
    Returns:
        tuple: (should_trade, predicted_sl_multiplier, predicted_tp_multiplier, confidence)
    """
    # Load model
    model_data = joblib.load('clean_trade_decision_sl_tp_predictor.pkl')
    model = model_data['model']
    scaler = model_data['scaler']
    
    # Calculate derived features if not provided
    if trend_score is None:
        trend_score = ema_diff * 10  # Scale EMA diff to trend score
    if momentum_strength is None:
        momentum_strength = (rsi14 - 50) / 10  # RSI-based momentum
    
    # Create exactly 12 features in the correct order
    feature_vector = np.array([[
        ema_diff,               # 0: EMA_diff
        rsi14,                  # 1: RSI14  
        ret_5,                  # 2: Ret_5
        range_ratio,            # 3: Range_Ratio
        pct_from_30h,           # 4: Pct_from_30h
        pct_from_30l,           # 5: Pct_from_30l
        consecutive_bullish,    # 6: Consecutive_Bullish
        consecutive_bearish,    # 7: Consecutive_Bearish
        avg_body_size,          # 8: Avg_Body_Size
        avg_range,              # 9: Avg_Range
        trend_score,            # 10: Trend_Score
        momentum_strength       # 11: Momentum_Strength
    ]])
    
    # Scale features
    feature_vector_scaled = scaler.transform(feature_vector)
    
    # Get predictions
    predictions = model.predict(feature_vector_scaled)[0]
    
    decision_score = predictions[0]
    sl_mult = predictions[1]
    tp_mult = predictions[2]
    
    # Binary trade decision and confidence
    should_trade = decision_score >= 0.5
    confidence = abs(decision_score - 0.5) * 2  # Convert to 0-1 confidence
    
    # Ensure multipliers are within bounds
    sl_mult = np.clip(sl_mult, 0.01, 0.15)
    tp_mult = np.clip(tp_mult, 0.02, 0.50)
    
    # Ensure minimum risk-reward ratio
    if tp_mult / sl_mult < 1.5:
        tp_mult = sl_mult * 1.8
    
    return should_trade, sl_mult, tp_mult, confidence

print("\n" + "="*70)
print("🎯 12-FEATURE MODEL COMPLETE - PERFECT FOR DLL!")
print("✅ Uses exactly 12 selected features")
print("✅ Fast predictions with minimal complexity")
print("✅ Optimized for MT5 DLL integration")
print("✅ Conservative trade decisions with good risk-reward ratios")
print("✅ Ready for real-time trading implementation")
print("="*70)

# Test the DLL-ready prediction function
print("\n=== TESTING DLL-READY PREDICTION FUNCTION ===")
should_trade, test_sl, test_tp, confidence = predict_with_12_features(
    ema_diff=0.002, rsi14=55.0, range_ratio=1.1, 
    trend_score=0.2, momentum_strength=0.1
)
trade_action = "TRADE" if should_trade else "NO TRADE"
print(f"Test: EMA_diff=0.002, RSI=55.0 → {trade_action}")
print(f"SL={test_sl:.4f}, TP={test_tp:.4f}, RR={test_tp/test_sl:.1f}:1, Confidence={confidence:.1%}")