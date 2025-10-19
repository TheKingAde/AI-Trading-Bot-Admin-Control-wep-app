import os
from datetime import datetime, timedelta
from functools import wraps
from typing import Callable

from jwt import encode, decode, ExpiredSignatureError
from quart import request, jsonify

JWT_SECRET = os.getenv('JWT_SECRET', 'change_this_secret')
JWT_ALG = 'HS256'
TOKEN_TTL_MIN = int(os.getenv('JWT_TTL_MIN', '120'))

# simple token blacklist in memory (for demo)
_BLACKLIST = set()


def create_token(payload: dict) -> str:
    to_encode = payload.copy()
    to_encode['exp'] = datetime.utcnow() + timedelta(minutes=TOKEN_TTL_MIN)
    return encode(to_encode, JWT_SECRET, algorithm=JWT_ALG)


def invalidate_token(token: str):
    _BLACKLIST.add(token)


def auth_required(fn: Callable):
    @wraps(fn)
    async def wrapper(*args, **kwargs):
        auth = request.headers.get('Authorization')
        if not auth or not auth.startswith('Bearer '):
            return jsonify({"error": "Missing token"}), 401
        token = auth.replace('Bearer ', '')
        if token in _BLACKLIST:
            return jsonify({"error": "Token invalidated"}), 401
        try:
            payload = decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        except ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except Exception:
            return jsonify({"error": "Invalid token"}), 401
        return await fn(*args, user=payload.get('sub'), **kwargs)
    return wrapper
