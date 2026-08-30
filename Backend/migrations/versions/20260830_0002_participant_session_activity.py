"""Add participant session activity timestamps.

Revision ID: 20260830_0002
Revises: 20260829_0001
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260830_0002"
down_revision: Union[str, None] = "20260829_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("session_created_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("session_last_seen_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "session_last_seen_at")
    op.drop_column("users", "session_created_at")
