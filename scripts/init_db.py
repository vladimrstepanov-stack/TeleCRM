"""Быстрое создание схемы локально без Alembic (для разработки).

Использует DATABASE_URL из .env. Для рабочей среды предпочтителен `alembic upgrade head`.
"""

import asyncio

from app.config import get_settings
from app.database.base import Base, init_engine
from app.database import models  # noqa: F401  (регистрирует таблицы)


async def main() -> None:
    settings = get_settings()
    engine = init_engine(settings.database_url.get_secret_value())
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("Схема создана.")


if __name__ == "__main__":
    asyncio.run(main())
