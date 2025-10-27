from datetime import datetime, timedelta

async def get_license_status(db, key: str):
    async with db.execute('SELECT name, status, expires_at FROM licenses WHERE key = ?', (key,)) as cursor:
        row = await cursor.fetchone()
        if not row:
            return {"valid": False, "message": "License not found"}
        name, status, expires_at = row
        valid = status == 'active' and (not expires_at or datetime.fromisoformat(expires_at) > datetime.utcnow())
        return {"valid": valid, "key": key, "name": name, "status": status, "expires_at": expires_at}


async def activate_license(db, key: str, name: str, days: int = 30):
    expires_at = (datetime.utcnow() + timedelta(days=days)).isoformat()
    sql = (
        "INSERT INTO licenses (key, name, status, expires_at, created_at) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET name=excluded.name, status=excluded.status, expires_at=excluded.expires_at"
    )
    await db.execute(sql, (key, name, 'active', expires_at, datetime.utcnow().isoformat()))
    await db.commit()
    return {"key": key, "name": name, "status": "active", "expires_at": expires_at}


async def deactivate_license(db, key: str):
    await db.execute('UPDATE licenses SET status = ? WHERE key = ?', ('inactive', key))
    await db.commit()
    return {"key": key, "status": "inactive"}


async def renew_license(db, key: str, days: int = 30):
    # Extend existing or set from now
    async with db.execute('SELECT expires_at FROM licenses WHERE key = ?', (key,)) as cursor:
        row = await cursor.fetchone()
    base = datetime.utcnow()
    if row and row[0]:
        try:
            current = datetime.fromisoformat(row[0])
            if current > base:
                base = current
        except Exception:
            pass
    new_exp = (base + timedelta(days=days)).isoformat()
    await db.execute('UPDATE licenses SET expires_at = ?, status = ? WHERE key = ?', (new_exp, 'active', key))
    await db.commit()
    return {"key": key, "status": "active", "expires_at": new_exp}


async def get_all_licenses(db):
    async with db.execute('SELECT name, key, expires_at, status FROM licenses ORDER BY id DESC') as cursor:
        rows = await cursor.fetchall()
        return [
            {
                "name": row[0] or "Unknown",
                "key": row[1],
                "expires_at": row[2],
                "status": row[3]
            }
            for row in rows
        ]


async def delete_license(db, key: str):
    await db.execute('DELETE FROM licenses WHERE key = ?', (key,))
    await db.commit()
    return {"key": key, "deleted": True}
