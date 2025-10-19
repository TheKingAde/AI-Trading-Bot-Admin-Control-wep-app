from datetime import datetime
from quart import Blueprint, request, jsonify

from models.db import get_db
from utils.security import auth_required

account_bp = Blueprint('account', __name__)


@account_bp.post('/account_data')
@auth_required
async def post_account_data(user):
    data = await request.get_json()
    balance = float(data.get('balance', 0))
    equity = float(data.get('equity', 0))
    win_rate = float(data.get('win_rate', 0))
    async with get_db() as db:
        await db.execute('INSERT INTO accounts (balance, equity, win_rate, updated_at) VALUES (?, ?, ?, ?)',
                         (balance, equity, win_rate, datetime.utcnow().isoformat()))
        await db.commit()
    return jsonify({"status": "stored"})


@account_bp.post('/trade_history')
@auth_required
async def post_trade_history(user):
    data = await request.get_json()
    trades = data.get('trades', [])
    async with get_db() as db:
        for t in trades:
            await db.execute('INSERT INTO trades (pair, result, opened_at, closed_at, ai_confidence, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                             (
                                 t.get('pair', 'UNKNOWN'),
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
    # Dummy live trades with AI confidence
    dummy = [
        {"pair": "EURUSD", "lots": 0.1, "direction": "BUY", "ai_confidence": 0.76},
        {"pair": "GBPUSD", "lots": 0.2, "direction": "SELL", "ai_confidence": 0.63},
    ]
    return jsonify({"trades": dummy})
