from datetime import datetime, timedelta
from quart import Blueprint, jsonify

from utils.security import auth_required
from models.db import get_db
from utils.exports import generate_pdf_statement, generate_xls_statement

export_bp = Blueprint('export', __name__)


async def _get_latest_account(db):
    async with db.execute('SELECT balance, equity, updated_at FROM accounts ORDER BY id DESC LIMIT 1') as cur:
        row = await cur.fetchone()
        if not row:
            return {"balance": 0, "equity": 0}
        return {"balance": row[0], "equity": row[1]}


async def _get_trades_last_30_days(db):
    """Get trades from the last 30 days with additional fields"""
    thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()
    
    async with db.execute('''
        SELECT pair, lots, direction, result, status, opened_at, closed_at, ai_confidence 
        FROM trades 
        WHERE created_at >= ? 
        ORDER BY created_at DESC 
        LIMIT 500
    ''', (thirty_days_ago,)) as cur:
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


async def _calculate_performance(trades):
    """Calculate win rate and drawdown from trades"""
    if not trades:
        return {"win_rate": 0, "drawdown": 0, "total_trades": 0}
    
    # Only consider closed trades for performance metrics
    closed_trades = [t for t in trades if t.get('status') == 'closed']
    
    if not closed_trades:
        return {"win_rate": 0, "drawdown": 0, "total_trades": len(trades)}
    
    # Calculate win rate
    winning_trades = sum(1 for t in closed_trades if t.get('result', 0) > 0)
    win_rate = (winning_trades / len(closed_trades)) * 100 if closed_trades else 0
    
    # Calculate max drawdown
    balance = 0
    peak = 0
    max_drawdown = 0
    
    for trade in reversed(closed_trades):  # Process in chronological order
        balance += trade.get('result', 0)
        if balance > peak:
            peak = balance
        drawdown = ((peak - balance) / peak * 100) if peak > 0 else 0
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    
    return {
        "win_rate": win_rate,
        "drawdown": max_drawdown,
        "total_trades": len(trades)
    }


@export_bp.get('/export/pdf')
@auth_required
async def export_pdf(user):
    async with get_db() as db:
        account = await _get_latest_account(db)
        trades = await _get_trades_last_30_days(db)
    
    # Calculate performance metrics
    performance = await _calculate_performance(trades)
    
    # Merge account and performance data
    account_summary = {**account, **performance}
    
    return await generate_pdf_statement(account_summary, trades)


@export_bp.get('/export/xls')
@auth_required
async def export_xls(user):
    async with get_db() as db:
        account = await _get_latest_account(db)
        trades = await _get_trades_last_30_days(db)
    
    # Calculate performance metrics
    performance = await _calculate_performance(trades)
    
    # Merge account and performance data
    account_summary = {**account, **performance}
    
    return await generate_xls_statement(account_summary, trades)
