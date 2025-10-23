from datetime import datetime, timedelta
from quart import Blueprint, jsonify, request

from utils.security import auth_required
from models.db import get_db
from utils.exports import generate_pdf_statement, generate_xls_statement

export_bp = Blueprint('export', __name__)


async def _get_latest_account(db, license_key):
    """Get the latest account info for a specific license key"""
    async with db.execute(
        'SELECT balance, equity, updated_at FROM accounts WHERE license_key = ? ORDER BY id DESC LIMIT 1',
        (license_key,)
    ) as cur:
        row = await cur.fetchone()
        if not row:
            return {"balance": 0, "equity": 0}
        return {"balance": row[0], "equity": row[1]}


async def _get_trades_last_30_days(db, license_key):
    """Get trades from the last 30 days for a specific license key"""
    thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()
    
    async with db.execute('''
        SELECT pair, lots, direction, result, status, opened_at, closed_at, ai_confidence 
        FROM trades 
        WHERE license_key = ? AND created_at >= ? 
        ORDER BY created_at DESC 
        LIMIT 500
    ''', (license_key, thirty_days_ago)) as cur:
        rows = await cur.fetchall()
        return [
            {
                "pair": r[0],
                "lots": r[1],
                "direction": r[2],
                "result": r[3],
                "status": r[4],
                "opened_at": r[5],
                "closed_at": r[6],
                "ai_confidence": f"{int(r[7] * 100)}%" if r[7] is not None else "Unavailable"
            } 
            for r in rows
        ]

peak_balance = 0
async def _calculate_performance(trades, initial_balance=1000):
    """Calculate win rate and drawdown from trades using proper balance tracking"""
    global peak_balance
    
    if not trades:
        return {"win_rate": 0, "drawdown": 0, "total_trades": 0}
    
    # Only consider closed trades for performance metrics
    closed_trades = [t for t in trades if t.get('status') == 'closed']
    
    if not closed_trades:
        return {"win_rate": 0, "drawdown": 0, "total_trades": len(trades)}
    
    # Calculate win rate
    winning_trades = sum(1 for t in closed_trades if t.get('result', 0) > 0)
    win_rate = (winning_trades / len(closed_trades)) * 100 if closed_trades else 0
    
    # Calculate max drawdown using proper balance tracking
    # Sort trades chronologically (they come in DESC order from query, so reverse)
    chronological_trades = list(reversed(closed_trades))
    
    running_balance = initial_balance
    peak_balance = initial_balance
    max_relative_drawdown = 0.0
    current_drawdown = 0.0
    
    for trade in chronological_trades:
        profit = trade.get('result', 0)
        running_balance += profit
        
        # Update peak balance
        if running_balance > peak_balance:
            peak_balance = running_balance
        
        # Calculate current drawdown (%)
        if peak_balance > 0:
            current_drawdown = ((peak_balance - running_balance) / peak_balance) * 100
            if current_drawdown > max_relative_drawdown:
                max_relative_drawdown = current_drawdown
    
    return {
        "win_rate": win_rate,
        "drawdown": max_relative_drawdown,
        "total_trades": len(trades)
    }


@export_bp.get('/export/pdf')
@auth_required
async def export_pdf(user):
    # Get license_key from query parameters
    license_key = request.args.get('license_key')
    if not license_key:
        return jsonify({"error": "license_key parameter is required"}), 400
    
    async with get_db() as db:
        # Verify the license exists
        async with db.execute('SELECT key FROM licenses WHERE key = ?', (license_key,)) as cur:
            if not await cur.fetchone():
                return jsonify({"error": "Invalid license key"}), 404
        
        account = await _get_latest_account(db, license_key)
        trades = await _get_trades_last_30_days(db, license_key)
    
    # Get initial balance (current balance or fallback to 1000)
    initial_balance = account.get('balance', 1000) if account.get('balance', 0) > 0 else 1000
    
    # Calculate performance metrics with initial balance
    performance = await _calculate_performance(trades, initial_balance)
    
    # Merge account and performance data
    account_summary = {**account, **performance, "license_key": license_key}
    
    return await generate_pdf_statement(account_summary, trades)


@export_bp.get('/export/xls')
@auth_required
async def export_xls(user):
    # Get license_key from query parameters
    license_key = request.args.get('license_key')
    if not license_key:
        return jsonify({"error": "license_key parameter is required"}), 400
    
    async with get_db() as db:
        # Verify the license exists
        async with db.execute('SELECT key FROM licenses WHERE key = ?', (license_key,)) as cur:
            if not await cur.fetchone():
                return jsonify({"error": "Invalid license key"}), 404
        
        account = await _get_latest_account(db, license_key)
        trades = await _get_trades_last_30_days(db, license_key)
    
    # Get initial balance (current balance or fallback to 1000)
    initial_balance = account.get('balance', 1000) if account.get('balance', 0) > 0 else 1000
    
    # Calculate performance metrics with initial balance
    performance = await _calculate_performance(trades, initial_balance)
    
    # Merge account and performance data
    account_summary = {**account, **performance, "license_key": license_key}
    
    return await generate_xls_statement(account_summary, trades)
