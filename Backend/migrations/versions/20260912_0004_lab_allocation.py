"""Add Lab Admin allocation persistence.

Revision ID: 20260912_0004
Revises: 20260831_0003
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260912_0004"
down_revision: Union[str, None] = "20260831_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "labs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("capacity > 0", name="ck_labs_capacity_positive"),
        sa.CheckConstraint("sort_order >= 0", name="ck_labs_sort_order_nonnegative"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_labs_name_ci", "labs", [sa.text("lower(name)")], unique=True)
    op.create_table(
        "lab_allocation_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="NOT_READY"),
        sa.Column("allocated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('NOT_READY', 'READY', 'ALLOCATING', 'ALLOCATED', 'FINALIZED')",
            name="ck_lab_allocation_state_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "lab_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("original_lab_id", sa.Integer(), nullable=False),
        sa.Column("current_lab_id", sa.Integer(), nullable=False),
        sa.Column("assignment_source", sa.String(length=20), nullable=False, server_default="AUTO"),
        sa.Column("constraint_override", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("effective_ps_id", sa.Integer(), nullable=False),
        sa.Column("moved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("moved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "assignment_source IN ('AUTO', 'MANUAL_OVERRIDE')",
            name="ck_lab_assignments_source",
        ),
        sa.CheckConstraint("version > 0", name="ck_lab_assignments_version_positive"),
        sa.ForeignKeyConstraint(["current_lab_id"], ["labs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["effective_ps_id"], ["problem_statements.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["moved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["original_lab_id"], ["labs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", name="uq_lab_assignments_team"),
    )
    op.create_index("ix_lab_assignments_current_lab", "lab_assignments", ["current_lab_id"])
    op.create_index(
        "ix_lab_assignments_effective_problem_lab",
        "lab_assignments",
        ["effective_ps_id", "current_lab_id"],
    )
    op.create_index(
        "uq_users_single_lab_admin",
        "users",
        ["role"],
        unique=True,
        postgresql_where=sa.text("role = 'lab_admin'"),
    )
    op.bulk_insert(
        sa.table("lab_allocation_state", sa.column("id", sa.Integer), sa.column("status", sa.String)),
        [{"id": 1, "status": "NOT_READY"}],
    )


def downgrade() -> None:
    op.drop_index("uq_users_single_lab_admin", table_name="users")
    op.drop_index("ix_lab_assignments_effective_problem_lab", table_name="lab_assignments")
    op.drop_index("ix_lab_assignments_current_lab", table_name="lab_assignments")
    op.drop_table("lab_assignments")
    op.drop_table("lab_allocation_state")
    op.drop_table("labs")
