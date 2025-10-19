# Bot Dashboard & Control Station

This is an admin-only fullstack web app for managing EA licenses, viewing account performance, receiving live trading data, and exporting statements. Backend is Quart (Python, async); frontend is vanilla HTML/CSS/JS.

## Quick start (Windows, cmd)

1) Create a Python virtual environment and install dependencies

```
python -m venv .venv
.\.venv\Scripts\activate
pip install -r backend\requirements.txt
```

2) Set environment variables

Copy `.env.example` to `.env` and adjust values:

```
copy .env.example .env
```

Edit `.env` and set at least:
- JWT_SECRET
- ADMIN_USERNAME / ADMIN_PASSWORD (for login)

3) Run the backend

```
python backend\app.py
```

Open http://localhost:8000 to access the dashboard.

## API summary

### Authentication
- POST /api/login
- POST /api/logout

### License Management
- POST /api/license/activate - Activate a license (requires: key, name, days)
- POST /api/license/deactivate - Deactivate a license (requires: key)
- POST /api/license/renew - Renew a license (requires: key, days)
- GET /api/license/status?key=... - Check license status
- GET /api/license/all - Get all licenses (NEW)

### Trading Data
- POST /api/trade_history
- POST /api/account_data
- GET /api/trade_data/live

### Performance & Export
- GET /api/performance
- GET /api/export/pdf
- GET /api/export/xls

All routes except /api/login require a Bearer token (Authorization header) with the JWT returned by /api/login.

## Notes

- SQLite DB is stored under `data/app.db` on first run.
- JWT logout uses an in-memory blacklist (resets on server restart). For production, use a persistent store.
- PDF/XLS exports are minimal examples; tailor content to your statement format.
