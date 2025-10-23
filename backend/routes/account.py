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
        
        inserted_count = 0
        updated_count = 0

        for t in trades:
            symbol = t.get('symbol', 'UNKNOWN')
            lots = float(t.get('lots', 0))
            direction = t.get('type', 'UNKNOWN')
            profit = float(t.get('profit', 0))
            time_open = t.get('time_open')
            time_close = t.get('time_close')
            status = t.get('status', 'closed')  # 'open' or 'closed'

            # For open trades, check if trade already exists (by license_key, symbol, lots, direction, opened_at)
            # If exists, update it; otherwise insert
            if status == 'open':
                cursor = await db.execute("""
                    SELECT id FROM trades 
                    WHERE license_key = ? AND pair = ? AND lots = ? AND direction = ? AND opened_at = ? AND status = 'open'
                """, (license_key, symbol, lots, direction, time_open))
                
                existing = await cursor.fetchone()
                if existing:
                    # Update existing open trade
                    await db.execute("""
                        UPDATE trades SET result = ?, closed_at = ?, status = ?
                        WHERE id = ?
                    """, (profit, time_close, status, existing[0]))
                    updated_count += 1
                else:
                    # Insert new open trade
                    await db.execute('''
                        INSERT INTO trades (license_key, pair, lots, direction, result, opened_at, closed_at, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        license_key,
                        symbol,
                        lots,
                        direction,
                        profit,
                        time_open,
                        time_close,
                        status,
                        datetime.utcnow().isoformat()
                    ))
                    inserted_count += 1
            else:
                # For closed trades, check if there's an open trade to update
                cursor = await db.execute("""
                    SELECT id FROM trades 
                    WHERE license_key = ? AND pair = ? AND lots = ? AND direction = ? AND opened_at = ? AND status = 'open'
                """, (license_key, symbol, lots, direction, time_open))
                
                existing = await cursor.fetchone()
                if existing:
                    # Update the open trade to closed
                    await db.execute("""
                        UPDATE trades SET result = ?, closed_at = ?, status = 'closed'
                        WHERE id = ?
                    """, (profit, time_close, existing[0]))
                    updated_count += 1
                else:
                    # Check for duplicate closed trade
                    cursor = await db.execute("""
                        SELECT 1 FROM trades 
                        WHERE license_key = ? AND pair = ? AND lots = ? AND direction = ? 
                              AND result = ? AND opened_at = ? AND closed_at = ? AND status = 'closed'
                    """, (license_key, symbol, lots, direction, profit, time_open, time_close))
                    
                    exists = await cursor.fetchone()
                    if not exists:
                        # Insert new closed trade
                        await db.execute('''
                            INSERT INTO trades (license_key, pair, lots, direction, result, opened_at, closed_at, status, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            license_key,
                            symbol,
                            lots,
                            direction,
                            profit,
                            time_open,
                            time_close,
                            'closed',
                            datetime.utcnow().isoformat()
                        ))
                        inserted_count += 1

        await db.commit()
    
    return jsonify({"status": "trades stored", "inserted": inserted_count, "updated": updated_count})

@account_bp.get('/trade_data/live')
@auth_required
async def get_live_trades(user):
    """Get trade history for a specific license key"""
    license_key = request.args.get('license_key')
    
    if not license_key:
        return jsonify({"trades": []})
    
    async with get_db() as db:
        # Get recent trades from trade history (last 3)
        cursor = await db.execute(
           'SELECT pair, lots, direction, result, status, ai_confidence FROM trades WHERE license_key = ? ORDER BY created_at DESC LIMIT 3',
            (license_key,)
        )
        rows = await cursor.fetchall()
        trades = []
        for row in rows:
            trades.append({
                "pair": row[0],
                "lots": row[1],
                "direction": row[2],
                "profit": row[3],
                "status": row[4],
               "ai_confidence": f"{int(row[5] * 100)}%" if row[5] is not None else "Unavailable"
            })
    
        return jsonify({"trades": trades if trades else [{"pair": "No trades", "lots": 0, "direction": "-", "profit": 0, "status": "-", "ai_confidence": "Unavailable"}]})


@account_bp.get('/account_stats')
@auth_required
async def get_account_stats(user):
    """Get account stats for a specific license key"""
    license_key = request.args.get('license_key')
    
    if not license_key:
        return jsonify({"balance": 0, "equity": 0})
    
    async with get_db() as db:
        # Get most recent account data
        cursor = await db.execute(
            'SELECT balance, equity FROM accounts WHERE license_key = ? ORDER BY updated_at DESC LIMIT 1',
            (license_key,)
        )
        row = await cursor.fetchone()
        if row:
            return jsonify({"balance": row[0], "equity": row[1]})
    
    return jsonify({"balance": 0, "equity": 0})


# @account_bp.post('/ai_insights')
# async def post_ai_insights():
#     """Public endpoint for EAs to send AI insights"""
#     data = await request.get_json()
#     license_key = data.get('license_key')
#     insights = data.get('insights', [])
    
#     if not license_key:
#         return jsonify({"error": "license_key is required"}), 400
    
#     async with get_db() as db:
#         # Verify license exists
#         cursor = await db.execute('SELECT status FROM licenses WHERE key = ?', (license_key,))
#         lic = await cursor.fetchone()
#         if not lic:
#             return jsonify({"error": "Invalid license key"}), 404
        
#         for insight in insights:
#             await db.execute('INSERT INTO ai_insights (license_key, insight, created_at) VALUES (?, ?, ?)',
#                              (license_key, insight, datetime.utcnow().isoformat()))
#         await db.commit()
    
#     return jsonify({"status": "insights stored", "count": len(insights)})


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
