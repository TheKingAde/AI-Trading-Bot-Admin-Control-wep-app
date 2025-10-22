from datetime import datetime
from quart import Blueprint, request, jsonify

from models.db import get_db
from utils.security import auth_required

account_bp = Blueprint('account', __name__)


@account_bp.post('/account_data')
async def post_account_data():
    """Public endpoint for EAs to send account data"""
    data = await request.get_json()
    license_key = data.get('license_key')
    balance = float(data.get('balance', 0))
    equity = float(data.get('equity', 0))
    
    if not license_key:
        return jsonify({"error": "license_key is required"}), 400
    
    async with get_db() as db:
        # Verify license exists and is active
        cursor = await db.execute('SELECT status FROM licenses WHERE key = ?', (license_key,))
        lic = await cursor.fetchone()
        if not lic:
            return jsonify({"error": "Invalid license key"}), 404
        
        # Insert account data
        await db.execute('INSERT INTO accounts (license_key, balance, equity, updated_at) VALUES (?, ?, ?, ?)',
                         (license_key, balance, equity, datetime.utcnow().isoformat()))
        await db.commit()
    return jsonify({"status": "stored"})


@account_bp.post('/trade_history')
async def post_trade_history():
    """Public endpoint for EAs to send trade history"""
    data = await request.get_json()
    license_key = data.get('license_key')
    trades = data.get('trades', [])
    
    if not license_key:
        return jsonify({"error": "license_key is required"}), 400
    
    async with get_db() as db:
        # Verify license exists
        cursor = await db.execute('SELECT status FROM licenses WHERE key = ?', (license_key,))
        lic = await cursor.fetchone()
        if not lic:
            return jsonify({"error": "Invalid license key"}), 404
        
        for t in trades:
            await db.execute('INSERT INTO trades (license_key, pair, lots, direction, result, opened_at, closed_at, ai_confidence, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                             (
                                 license_key,
                                 t.get('pair', 'UNKNOWN'),
                                 float(t.get('lots', 0)),
                                 t.get('direction', 'UNKNOWN'),
                                 float(t.get('result', 0)),
                                 t.get('opened_at'),
                                 t.get('closed_at'),
                                 float(t.get('ai_confidence', 0)),
                                 datetime.utcnow().isoformat()
                             ))
        await db.commit()
    return jsonify({"status": "trades stored", "count": len(trades)})


@account_bp.get('/trade_data/live')
@auth_required
async def get_live_trades(user):
    """Get live trades for a specific license key"""
    license_key = request.args.get('license_key')
    
    if not license_key:
        return jsonify({"trades": []})
    
    async with get_db() as db:
        # Get recent trades (last 10, still open or recently closed)
        cursor = await db.execute(
            'SELECT pair, lots, direction, ai_confidence FROM trades WHERE license_key = ? AND closed_at IS NULL ORDER BY created_at DESC LIMIT 10',
            (license_key,)
        )
        rows = await cursor.fetchall()
        trades = []
        for row in rows:
            trades.append({
                "pair": row[0],
                "lots": row[1],
                "direction": row[2],
                "ai_confidence": row[3] or 0
            })
    
    return jsonify({"trades": trades if trades else [{"pair": "No active trades", "lots": 0, "direction": "-", "ai_confidence": 0}]})


@account_bp.get('/account_stats')
@auth_required
async def get_account_stats(user):
    """Get account stats for a specific license key"""
    license_key = request.args.get('license_key')
    
    if not license_key:
        return jsonify({"balance": 0, "equity": 0, "win_rate": 0})
    
    async with get_db() as db:
        # Get most recent account data
        cursor = await db.execute(
            'SELECT balance, equity, win_rate FROM accounts WHERE license_key = ? ORDER BY updated_at DESC LIMIT 1',
            (license_key,)
        )
        row = await cursor.fetchone()
        if row:
            return jsonify({"balance": row[0], "equity": row[1], "win_rate": row[2]})
    
    return jsonify({"balance": 0, "equity": 0, "win_rate": 0})


@account_bp.post('/ai_insights')
async def post_ai_insights():
    """Public endpoint for EAs to send AI insights"""
    data = await request.get_json()
    license_key = data.get('license_key')
    insights = data.get('insights', [])
    
    if not license_key:
        return jsonify({"error": "license_key is required"}), 400
    
    async with get_db() as db:
        # Verify license exists
        cursor = await db.execute('SELECT status FROM licenses WHERE key = ?', (license_key,))
        lic = await cursor.fetchone()
        if not lic:
            return jsonify({"error": "Invalid license key"}), 404
        
        for insight in insights:
            await db.execute('INSERT INTO ai_insights (license_key, insight, created_at) VALUES (?, ?, ?)',
                             (license_key, insight, datetime.utcnow().isoformat()))
        await db.commit()
    
    return jsonify({"status": "insights stored", "count": len(insights)})


@account_bp.get('/ai_insights')
@auth_required
async def get_ai_insights(user):
    """Get AI insights for a specific license key"""
    license_key = request.args.get('license_key')
    
    if not license_key:
        return jsonify({"insights": []})
    
    async with get_db() as db:
        # Get recent insights (last 5)
        cursor = await db.execute(
            'SELECT insight FROM ai_insights WHERE license_key = ? ORDER BY created_at DESC LIMIT 5',
            (license_key,)
        )
        rows = await cursor.fetchall()
        insights = [row[0] for row in rows]
    
    return jsonify({"insights": insights if insights else ["No insights available"]})
