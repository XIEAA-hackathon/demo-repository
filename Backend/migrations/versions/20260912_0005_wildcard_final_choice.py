"""Add Wildcard final problem choice persistence.

Revision ID: 20260912_0005
Revises: 20260912_0004
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260912_0005"
down_revision: Union[str, None] = "20260912_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("teams", sa.Column("final_problem_choice", sa.String(), nullable=True))
    op.add_column("teams", sa.Column("final_problem_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "teams",
        sa.Column("final_problem_defaulted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("round_controls", sa.Column("final_choice_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("round_controls", sa.Column("final_choice_ends_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("round_controls", sa.Column("final_choice_duration_seconds", sa.Integer(), nullable=True))
    op.add_column(
        "event_config",
        sa.Column("wildcard_final_choice_seconds", sa.Integer(), nullable=False, server_default="60"),
    )


def downgrade() -> None:
    op.drop_column("event_config", "wildcard_final_choice_seconds")
    op.drop_column("round_controls", "final_choice_duration_seconds")
    op.drop_column("round_controls", "final_choice_ends_at")
    op.drop_column("round_controls", "final_choice_started_at")
    op.drop_column("teams", "final_problem_defaulted")
    op.drop_column("teams", "final_problem_confirmed_at")
    op.drop_column("teams", "final_problem_choice")
