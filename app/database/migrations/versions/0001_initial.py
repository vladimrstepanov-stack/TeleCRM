"""Начальная схема: агенты, клиенты, объекты, связки, сделки, потребности, активности, аудит.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-17
"""
from collections.abc import Sequence

from alembic import op

from app.database.base import Base
from app.database import models  # noqa: F401  (регистрирует таблицы в metadata)

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Схема полностью описана в ORM-моделях, поэтому создаём её из metadata:
    # так DDL и модели гарантированно не расходятся.
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
