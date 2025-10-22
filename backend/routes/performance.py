from datetime import datetime
from quart import Blueprint, jsonify, request

from utils.security import auth_required
from models.db import get_db

performance_bp = Blueprint('performance', __name__)

@performance_bp.get('/performance')
@auth_required
async def get_performance(user):
    """Get performance data calculated from trade history for a specific license key"""
    license_key = request.args.get('license_key')
    
    if not license_key:
        return jsonify({"performance": []})
    
    async with get_db() as db:
        # Aggregate summary stats
        cursor = await db.execute('''
            SELECT 
                pair,
                COUNT(*) as total_trades,
                SUM(CASE WHEN result > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(result) as total_profit
            FROM trades 
            WHERE license_key = ? AND closed_at IS NOT NULL
            GROUP BY pair
            ORDER BY pair
        ''', (license_key,))
        
        rows = await cursor.fetchall()
        performance = []
        
        for row in rows:
            pair = row[0]
            total_trades = row[1]
            winning_trades = row[2]
            total_profit = row[3] or 0
            
            # Calculate win rate
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            # Get all trade results for drawdown calculation
            trades_cursor = await db.execute('''
                SELECT result 
                FROM trades 
                WHERE license_key = ? AND pair = ? AND closed_at IS NOT NULL
                ORDER BY closed_at ASC
            ''', (license_key, pair))
            
            trade_results = await trades_cursor.fetchall()
            
            # Calculate running balance & relative drawdown
            running_balance = 0
            peak_balance = 0
            max_relative_drawdown = 0.0
            
            for trade_result in trade_results:
                profit = trade_result[0] or 0
                running_balance += profit

                # Update peak balance
                if running_balance > peak_balance:
                    peak_balance = running_balance

                # Calculate relative drawdown (%)
                if peak_balance > 0:
                    relative_dd = ((peak_balance - running_balance) / peak_balance) * 100
                    if relative_dd > max_relative_drawdown:
                        max_relative_drawdown = relative_dd
            
            performance.append({
                "pair": pair,
                "win_rate": round(win_rate, 2),
                "drawdown": round(max_relative_drawdown, 2),  # relative DD in %
                "trades": total_trades,
                "total_profit": round(total_profit, 2)
            })
    
    return jsonify({
        "performance": performance if performance else [{
            "pair": "No data",
            "win_rate": 0,
            "drawdown": 0,
            "trades": 0,
            "total_profit": 0
        }]
    })
