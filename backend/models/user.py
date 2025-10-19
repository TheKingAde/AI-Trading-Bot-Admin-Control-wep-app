import os
import hashlib
from datetime import datetime

ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


async def ensure_admin(db):
    """Ensure the admin user exists."""
    phash = hash_password(ADMIN_PASSWORD)
    await db.execute(
        'INSERT OR IGNORE INTO users (username, password_hash, created_at) VALUES (?, ?, ?)',
        (ADMIN_USERNAME, phash, datetime.utcnow().isoformat())
    )
    await db.commit()


async def authenticate(db, username: str, password: str) -> bool:
    phash = hash_password(password)
    async with db.execute('SELECT id FROM users WHERE username = ? AND password_hash = ?', (username, phash)) as cursor:
        row = await cursor.fetchone()
        return row is not None
