"""Validate and backfill Wildcard final choices.

Revision ID: 20260919_0006
Revises: 20260912_0005
"""
from typing import Sequence, Union

from alembic import op


revision: str = "20260919_0006"
down_revision: Union[str, None] = "20260912_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Preserve the effective problem already used by historical completed rows.
    op.execute(
        """
        UPDATE teams
        SET final_problem_choice = COALESCE(
                final_problem_choice,
                CASE
                    WHEN wildcard_problem_id IS NOT NULL AND ps_id = wildcard_problem_id THEN 'WILDCARD'
                    WHEN round1_problem_id IS NOT NULL AND ps_id = round1_problem_id THEN 'ROUND1'
                    ELSE NULL
                END
            ),
            final_problem_confirmed_at = COALESCE(
                final_problem_confirmed_at,
                CASE
                    WHEN wildcard_problem_id IS NOT NULL AND ps_id IN (round1_problem_id, wildcard_problem_id)
                    THEN CURRENT_TIMESTAMP
                    ELSE NULL
                END
            )
        WHERE wildcard_problem_id IS NOT NULL
        """
    )
    op.create_check_constraint(
        "ck_teams_final_problem_choice",
        "teams",
        "final_problem_choice IS NULL OR final_problem_choice IN ('ROUND1', 'WILDCARD')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_teams_final_problem_choice", "teams", type_="check")
