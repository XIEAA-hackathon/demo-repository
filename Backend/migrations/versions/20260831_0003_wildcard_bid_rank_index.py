"""Add the Wildcard hot-path ranking index.

Revision ID: 20260831_0003
Revises: 20260830_0002
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260831_0003"
down_revision: Union[str, None] = "20260830_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_wildcard_bids_rank",
        "wildcard_bids",
        [sa.text("amount DESC"), sa.text("timestamp ASC"), sa.text("team_id ASC")],
    )


def downgrade() -> None:
    op.drop_index("ix_wildcard_bids_rank", table_name="wildcard_bids")
