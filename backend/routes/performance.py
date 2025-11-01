from datetime import datetime
from quart import Blueprint, jsonify, request

from utils.security import auth_required
from models.db import get_db

performance_bp = Blueprint('performance', __name__)

peak_balance = 0
min_win_rate = 50
insights = []
@performance_bp.get('/performance')
@auth_required
async def get_performance(user):
    """Get performance data calculated from trade history for a specific license key"""
    global insights
    license_key = request.args.get('license_key')
    
    if not license_key:
        return jsonify({"performance": []})

    async with get_db() as db:
        # Get latest account balance/equity
        cursor1 = await db.execute(
            'SELECT balance, equity FROM accounts WHERE license_key = ? ORDER BY updated_at DESC LIMIT 1',
            (license_key,)
        )
        row1 = await cursor1.fetchone()
        initial_balance = row1[0] if row1 else 1000  # fallback default

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
        insight = []
        for row in rows:
            pair = row[0]
            total_trades = row[1]
            winning_trades = row[2]
            total_profit = row[3] or 0
            
            # Calculate win rate
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            if win_rate < min_win_rate:
                insight.append(f"Warning: Bot is underperforming in pair: {pair}")
            if win_rate >= min_win_rate:
                insight.append(f"Everything is working as expected in pair: {pair}")

            # Get all trade results for drawdown calculation
            trades_cursor = await db.execute('''
                SELECT result 
                FROM trades 
                WHERE license_key = ? AND pair = ? AND closed_at IS NOT NULL
                ORDER BY closed_at ASC
            ''', (license_key, pair))
            
            trade_results = await trades_cursor.fetchall()

            # Initialize balance and drawdown variables
            running_balance = initial_balance
            peak_balance = initial_balance
            max_relative_drawdown = 0.0
            current_drawdown = 0.0

            for trade_result in trade_results:
                profit = trade_result[0] or 0
                running_balance += profit

                # Update peak balance
                if running_balance > peak_balance:
                    peak_balance = running_balance

                # Calculate current drawdown (%)
                if peak_balance > 0:
                    current_drawdown = ((peak_balance - running_balance) / peak_balance) * 100
                    if current_drawdown > max_relative_drawdown:
                        max_relative_drawdown = current_drawdown
            
            performance.append({
                "pair": pair,
                "win_rate": round(win_rate, 2),
                "max_drawdown": round(max_relative_drawdown, 2),  # highest DD %
                "current_drawdown": round(current_drawdown, 2),   # most recent DD %
                "trades": total_trades,
                "total_profit": round(total_profit, 2)
            })

        if insight != insights:
            insights = insight  # update cache

            # Remove old rows for this license
            await db.execute('DELETE FROM ai_insights WHERE license_key = ?', (license_key,))

            # Insert new ones
            for i in insights:
                await db.execute(
                    '''
                    INSERT INTO ai_insights (license_key, insight, created_at)
                    VALUES (?, ?, ?)
                    ''',
                    (license_key, i, datetime.utcnow().isoformat())
                )

            await db.commit()

    return jsonify({
        "performance": performance if performance else [{
            "pair": "No data",
            "win_rate": 0,
            "max_drawdown": 0,
            "current_drawdown": 0,
            "trades": 0,
            "total_profit": 0
        }]
    })