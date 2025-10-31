import os
import sys
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import joblib
from quart import Quart, jsonify, send_from_directory, request
from quart_cors import cors
from dotenv import load_dotenv
import sqlite3
import uuid

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from routes.auth import auth_bp
from routes.license import license_bp
from routes.account import account_bp
from routes.performance import performance_bp
from routes.export import export_bp
from models.db import init_db

ROOT_DIR = BASE_DIR.parent

# Load env
load_dotenv(ROOT_DIR / '.env')

app = Quart(__name__, static_folder=str(BASE_DIR / 'static'), static_url_path='/static')
app = cors(
    app,
    allow_origin=["http://localhost:8000"],
    allow_credentials=True,
    allow_headers=["Content-Type", "Authorization"]
)

# Register blueprints
app.register_blueprint(auth_bp, url_prefix='/api')
app.register_blueprint(license_bp, url_prefix='/api')
app.register_blueprint(account_bp, url_prefix='/api')
app.register_blueprint(performance_bp, url_prefix='/api')
app.register_blueprint(export_bp, url_prefix='/api')


@app.before_serving
async def startup():
    await init_db()
    # Load model once for fast inference
    try:
        model_path = ROOT_DIR / 'entry_decision_model.pkl'
        app.model_data = joblib.load(model_path)
        app.model = app.model_data['model']
        app.scaler = app.model_data['scaler']
        app.features = app.model_data['features']
        app.threshold = float(app.model_data.get('threshold', 0.5))
        # Precompute indices for categorical expectation
        app.feature_set = set(app.features)
        print(f"✅ Loaded model at startup: {model_path}")
        print(f"   Features: {len(app.features)} | Threshold: {app.threshold:.2f} | Trained: {app.model_data.get('training_date')} ")
    except Exception as e:
        # Defer failure to request time with clear error
        app.model = None
        app.scaler = None
        app.features = None
        app.threshold = 0.5
        print(f"⚠️  Warning: Could not load model at startup: {e}")


@app.get('/api/health')
async def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})


@app.get('/')
async def index():
    # Serve frontend index from static
    return await send_from_directory(app.static_folder, 'index.html')


# ===================== Inference Endpoint for EA =====================
# POST /api/entry-decision
def _build_feature_df(payload: dict):
    if not getattr(app, 'model', None) or not getattr(app, 'scaler', None) or not getattr(app, 'features', None):
        raise RuntimeError("Model not loaded on server. Train and place 'entry_decision_model.pkl' at project root.")

    feats = app.features

    # Case 1: array in correct order
    if isinstance(payload, dict) and 'features' in payload and isinstance(payload['features'], list):
        values = payload['features']
        if len(values) != len(feats):
            raise ValueError(f"Expected {len(feats)} features, got {len(values)}")
        row = values
    else:
        # Case 2: dict keyed by names
        missing = [f for f in feats if f not in payload]
        if missing:
            raise ValueError(f"Missing required feature fields: {missing}")
        # Normalize some fields (Use_BE can be bool/0-1; Symbol/Action expected numeric ids)
        row = []
        for f in feats:
            v = payload.get(f)
            if f == 'Use_BE':
                v = 1 if (v in (1, True, '1', 'true', 'True', 'YES', 'yes')) else 0
            # Coerce to float where possible
            try:
                v = float(v)
            except Exception:
                # Fallback: unknown category -> 0
                v = 0.0
            row.append(v)

    # Create DataFrame with proper feature names to avoid warnings and ensure order
    import pandas as pd
    df = pd.DataFrame([row], columns=feats)
    # Replace inf/nan with 0 (training used median fills; 0 is a safe neutral after robust scaling)
    df = df.replace([np.inf, -np.inf], np.nan).fillna(0)
    return df


@app.post('/api/entry-decision')
async def entry_decision():
    try:
        payload = await request.get_json()
        if payload is None:
            return jsonify({"error": "Expected JSON body"}), 400
        
        # Build feature DataFrame for model prediction
        df = _build_feature_df(payload)
        Xs = app.scaler.transform(df)
        proba = float(app.model.predict_proba(Xs)[0, 1])
        thr = float(app.threshold)
        enter = 1 if proba >= thr else 0
        confidence = max(0.0, min(1.0, abs(proba - thr) * 2.0))

        # ===================== Save COMPLETE trade data to DB =====================
        # Generate a unique Trade_ID for this request
        trade_id = str(uuid.uuid4())
        
        db_path = str(ROOT_DIR / 'data' / '1-training_data_prod.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get all columns in training_data
        cursor.execute(f"PRAGMA table_info(training_data)")
        db_columns = [row[1] for row in cursor.fetchall()]
        
        # Build complete row with ALL 30 fields
        row = {}        
        for col in db_columns:
            if col in payload:
                row[col] = payload[col]
            elif col == 'Trade_ID':
                continue  # Handle separately
            elif col in ['Win', 'Profit', 'Profit_Pct', 'Outcome']:
                row[col] = None  # Will be filled on trade close
            else:
                row[col] = None  # Default NULL for any missing fields
        
        # Add Trade_ID (not from payload)
        if 'Trade_ID' in db_columns:
            row['Trade_ID'] = trade_id
        
        # Prepare INSERT statement
        columns_to_insert = [k for k in row.keys() if k in db_columns]
        col_names = ','.join(columns_to_insert)
        placeholders = ','.join(['?' for _ in columns_to_insert])
        values = [row[k] for k in columns_to_insert]
        
        # Execute insert
        cursor.execute(f"INSERT INTO trades_dataset ({col_names}) VALUES ({placeholders})", values)
        conn.commit()
        conn.close()
        
        print(f"✅ Saved trade entry to DB: trade_id={trade_id}, enter={enter}, probability={proba:.4f}")

        return jsonify({
            "enter": enter,            # 1=ENTER, 0=STAY OUT
            "probability": round(proba, 6),
            "confidence": round(confidence, 6),
            "threshold": thr,
            "trade_id": trade_id
        })
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Prediction failed: {e}"}), 500


# ===================== Update trade outcome after close =====================
# POST /api/entry-update
# Updates the row with matching Trade_ID
@app.post('/api/entry-update')
async def entry_update():
    try:
        payload = await request.get_json()
        if payload is None:
            return jsonify({"error": "Expected JSON body"}), 400
        trade_id = payload.get('trade_id')
        if not trade_id:
            return jsonify({"error": "Missing trade_id"}), 400
        
        # Allow updating outcome fields
        allowed = ['Win', 'Profit', 'Profit_Pct', 'Outcome']
        updates = {k: payload[k] for k in allowed if k in payload}
        if not updates:
            return jsonify({"error": "No updatable fields provided"}), 400
        
        db_path = str(ROOT_DIR / 'data' / '1-training_data_prod.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        set_clause = ', '.join([f"{k}=?" for k in updates])
        values = list(updates.values()) + [trade_id]
        cursor.execute(f"UPDATE training_data SET {set_clause} WHERE Trade_ID=?", values)
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        
        if affected == 0:
            return jsonify({"error": "Trade_ID not found"}), 404
        
        print(f"✅ Updated trade outcome: trade_id={trade_id}, updates={updates}")
        return jsonify({"updated": affected, "trade_id": trade_id})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Update failed: {e}"}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 3000)))
