import os
import sys
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from quart import Quart, jsonify, send_from_directory
from quart_cors import cors
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from routes.auth import auth_bp
from routes.license import license_bp
from routes.account import account_bp
from routes.performance import performance_bp
from routes.export import export_bp
from models.db import init_db

ROOT_DIR = BASE_DIR.parent

# Load env
load_dotenv(ROOT_DIR / '.env')

app = Quart(__name__, static_folder=str(BASE_DIR / 'static'), static_url_path='/static')
app = cors(
    app,
    allow_origin=["http://localhost:8000"],
    allow_credentials=True,
    allow_headers=["Content-Type", "Authorization"]
)

# Register blueprints
app.register_blueprint(auth_bp, url_prefix='/api')
app.register_blueprint(license_bp, url_prefix='/api')
app.register_blueprint(account_bp, url_prefix='/api')
app.register_blueprint(performance_bp, url_prefix='/api')
app.register_blueprint(export_bp, url_prefix='/api')


@app.before_serving
async def startup():
    await init_db()


@app.get('/api/health')
async def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})


@app.get('/')
async def index():
    # Serve frontend index from static
    return await send_from_directory(app.static_folder, 'index.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8000)))
