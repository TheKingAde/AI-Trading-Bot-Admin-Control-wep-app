from datetime import datetime
from quart import Blueprint, jsonify, request

from utils.security import auth_required
from models.db import get_db

performance_bp = Blueprint('performance', __name__)


@performance_bp.get('/performance')
@auth_required
async def get_performance(user):
    """Get performance data for a specific license key"""
    license_key = request.args.get('license_key')
    
    if not license_key:
        return jsonify({"performance": []})
    
    async with get_db() as db:
        # Get performance data
        cursor = await db.execute(
            'SELECT pair, win_rate, drawdown, trades_count FROM performance WHERE license_key = ? ORDER BY pair',
            (license_key,)
        )
        rows = await cursor.fetchall()
        performance = []
        for row in rows:
            performance.append({
                "pair": row[0],
                "win_rate": row[1],
                "drawdown": row[2],
                "trades": row[3]
            })
    
    return jsonify({"performance": performance if performance else [{"pair": "No data", "win_rate": 0, "drawdown": 0, "trades": 0}]})


@performance_bp.post('/performance')
async def post_performance():
    """Public endpoint for EAs to send performance data"""
    data = await request.get_json()
    license_key = data.get('license_key')
    performance_data = data.get('performance', [])
    
    if not license_key:
        return jsonify({"error": "license_key is required"}), 400
    
    async with get_db() as db:
        # Verify license exists
        cursor = await db.execute('SELECT status FROM licenses WHERE key = ?', (license_key,))
        lic = await cursor.fetchone()
        if not lic:
            return jsonify({"error": "Invalid license key"}), 404
        
        # Delete old performance data for this license
        await db.execute('DELETE FROM performance WHERE license_key = ?', (license_key,))
        
        # Insert new performance data
        for perf in performance_data:
            await db.execute(
                'INSERT INTO performance (license_key, pair, win_rate, drawdown, trades_count, updated_at) VALUES (?, ?, ?, ?, ?, ?)',
                (
                    license_key,
                    perf.get('pair', 'UNKNOWN'),
                    float(perf.get('win_rate', 0)),
                    float(perf.get('drawdown', 0)),
                    int(perf.get('trades', 0)),
                    datetime.utcnow().isoformat()
                )
            )
        await db.commit()
    
    return jsonify({"status": "performance stored", "count": len(performance_data)})
