from quart import Blueprint, request, jsonify

from models.db import get_db
from utils.security import auth_required
from models.license import get_license_status, activate_license, deactivate_license, renew_license, get_all_licenses

license_bp = Blueprint('license', __name__)


# Public endpoint for EAs to check license key validity
@license_bp.get('/license/check')
async def license_check():
    key = request.args.get('key')
    if not key:
        return jsonify({"error": "key is required"}), 400

    async with get_db() as db:
        res = await get_license_status(db, key)

    if not res:
        return jsonify({"error": "License key not found"}), 404

    return jsonify({
        "key": res.get("key"),
        "status": res.get("status"),
        "expires_at": res.get("expires_at"),
        "name": res.get("name", "Unknown")
    })


@license_bp.get('/license/status')
@auth_required
async def license_status(user):
    key = request.args.get('key')
    if not key:
        return jsonify({"error": "key is required"}), 400
    async with get_db() as db:
        res = await get_license_status(db, key)
    return jsonify(res)


@license_bp.post('/license/activate')
@auth_required
async def license_activate(user):
    data = await request.get_json()
    key = data.get('key')
    name = data.get('name', 'Unknown')
    days = int(data.get('days', 30))
    if not key:
        return jsonify({"error": "key is required"}), 400
    async with get_db() as db:
        res = await activate_license(db, key, name, days)
    return jsonify(res)


@license_bp.post('/license/deactivate')
@auth_required
async def license_deactivate(user):
    data = await request.get_json()
    key = data.get('key')
    if not key:
        return jsonify({"error": "key is required"}), 400
    async with get_db() as db:
        res = await deactivate_license(db, key)
    return jsonify(res)


@license_bp.post('/license/renew')
@auth_required
async def license_renew(user):
    data = await request.get_json()
    key = data.get('key')
    days = int(data.get('days', 30))
    if not key:
        return jsonify({"error": "key is required"}), 400
    async with get_db() as db:
        res = await renew_license(db, key, days)
    return jsonify(res)


@license_bp.get('/license/all')
@auth_required
async def license_all(user):
    async with get_db() as db:
        licenses = await get_all_licenses(db)
    return jsonify(licenses)
