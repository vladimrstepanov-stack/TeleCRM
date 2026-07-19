#!/bin/bash
set -euo pipefail
cd /opt/telecrm
source .venv/bin/activate

# ensure cryptography present for MySQL 8 auth
pip install -q cryptography

echo "Testing DB connection..."
python - <<'PY'
from app.config import get_settings
from sqlalchemy.ext.asyncio import create_async_engine
import asyncio

async def main():
    url = get_settings().database_url.get_secret_value()
    # mask for log
    masked = url.split("@")[-1] if "@" in url else "hidden"
    print("DB_HOST_PART:", masked)
    engine = create_async_engine(url, pool_pre_ping=True)
    async with engine.connect() as conn:
        result = await conn.exec_driver_sql("SELECT 1")
        print("DB_CONNECT_OK", result.scalar())
    await engine.dispose()

asyncio.run(main())
PY

echo "Running alembic..."
alembic upgrade head
echo MIGRATE_OK

python - <<'PY'
from app.config import get_settings
from sqlalchemy.ext.asyncio import create_async_engine
import asyncio

async def main():
    url = get_settings().database_url.get_secret_value()
    engine = create_async_engine(url, pool_pre_ping=True)
    async with engine.connect() as conn:
        result = await conn.exec_driver_sql("SHOW TABLES")
        tables = [row[0] for row in result]
        print("TABLES:", ", ".join(tables) if tables else "(none)")
    await engine.dispose()

asyncio.run(main())
PY

systemctl restart telecrm
sleep 4
systemctl is-active telecrm
tail -n 15 /opt/telecrm/logs/app.log || true
echo DONE
