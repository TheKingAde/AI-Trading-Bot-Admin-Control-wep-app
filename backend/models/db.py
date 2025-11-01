import os
from pathlib import Path
import aiosqlite
from dotenv import load_dotenv

# __file__ = backend/models/db.py -> parents[2] = project root
ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / '.env')

DB_DIR = ROOT_DIR / 'data'
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / 'app.db'

def get_db():
    # Return the coroutine; use as: async with get_db() as db:
    return aiosqlite.connect(DB_PATH)

SCHEMA = [
    '''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );''',
    '''CREATE TABLE IF NOT EXISTS licenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE NOT NULL,
        name TEXT,
        status TEXT NOT NULL,
        expires_at TEXT,
        created_at TEXT NOT NULL
    );''',
    '''CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        license_key TEXT NOT NULL,
        balance REAL DEFAULT 0,
        equity REAL DEFAULT 0,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (license_key) REFERENCES licenses(key)
    );''',
    '''CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        license_key TEXT NOT NULL,
        pair TEXT NOT NULL,
        lots REAL DEFAULT 0,
        direction TEXT,
        result REAL NOT NULL,
        opened_at TEXT,
        closed_at TEXT,
        status TEXT DEFAULT 'closed',
        ai_confidence REAL DEFAULT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (license_key) REFERENCES licenses(key)
    );''',
    '''CREATE TABLE IF NOT EXISTS performance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        license_key TEXT NOT NULL,
        pair TEXT NOT NULL,
        win_rate REAL DEFAULT 0,
        drawdown REAL DEFAULT 0,
        trades_count INTEGER DEFAULT 0,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (license_key) REFERENCES licenses(key)
    );''',
    '''CREATE TABLE IF NOT EXISTS ai_insights (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        license_key TEXT NOT NULL,
        pair TEXT NOT NULL,
        insight TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (license_key) REFERENCES licenses(key)
    );'''
]

async def init_db():
    async with get_db() as db:
        for stmt in SCHEMA:
            await db.execute(stmt)
        await db.commit()
        # Ensure default admin user exists (username/password from env)
        from .user import ensure_admin
        await ensure_admin(db)
