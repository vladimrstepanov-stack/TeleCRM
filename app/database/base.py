"""Async-движок SQLAlchemy и фабрика сессий."""

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей."""


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker | None = None


def init_engine(database_url: str) -> AsyncEngine:
    """Создаёт движок и фабрику сессий один раз при старте приложения."""
    global _engine, _session_factory
    _engine = create_async_engine(database_url, pool_pre_ping=True, future=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_session_factory() -> async_sessionmaker:
    if _session_factory is None:
        raise RuntimeError("init_engine() должен быть вызван до получения сессий")
    return _session_factory
