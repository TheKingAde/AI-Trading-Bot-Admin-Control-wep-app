from datetime import datetime
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


async def _get_trades(db):
    async with db.execute('SELECT pair, result, opened_at, closed_at, ai_confidence FROM trades ORDER BY id DESC LIMIT 500') as cur:
        rows = await cur.fetchall()
        return [
            {"pair": r[0], "result": r[1], "opened_at": r[2], "closed_at": r[3], "ai_confidence": r[4]} for r in rows
        ]


@export_bp.get('/export/pdf')
@auth_required
async def export_pdf(user):
    async with get_db() as db:
        account = await _get_latest_account(db)
        trades = await _get_trades(db)
    return await generate_pdf_statement(account, trades)


@export_bp.get('/export/xls')
@auth_required
async def export_xls(user):
    async with get_db() as db:
        account = await _get_latest_account(db)
        trades = await _get_trades(db)
    return await generate_xls_statement(account, trades)
