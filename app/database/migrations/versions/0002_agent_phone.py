"""Добавляет колонку agents.phone для онбординга агента.

Revision ID: 0002_agent_phone
Revises: 0001_initial
Create Date: 2026-07-18
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_agent_phone"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("phone", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "phone")
