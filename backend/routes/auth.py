import os
from datetime import datetime, timedelta
# No need to import jwt here
from quart import Blueprint, request, jsonify

from models.db import get_db
from models.user import authenticate
from utils.security import create_token, auth_required, invalidate_token

auth_bp = Blueprint('auth', __name__)


@auth_bp.post('/login')
async def login():
    data = await request.get_json()
    username = data.get('username')
    password = data.get('password')
    async with get_db() as db:
        ok = await authenticate(db, username, password)
    if not ok:
        return jsonify({"error": "Invalid credentials"}), 401
    token = create_token({"sub": username})
    return jsonify({"token": token})


@auth_bp.post('/logout')
@auth_required
async def logout(user):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    invalidate_token(token)
    return jsonify({"status": "logged out"})
