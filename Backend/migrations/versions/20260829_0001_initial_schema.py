"""Initial Bid to Build schema.

Revision ID: 20260829_0001
Revises: None
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "20260829_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _id_column() -> sa.Column:
    return sa.Column("id", sa.Integer(), primary_key=True, nullable=False)


BASELINE_TABLES = {
    "bids",
    "event_activity_log",
    "event_config",
    "exchange_requests",
    "final_results",
    "game_config",
    "members",
    "problem_statements",
    "registration_import_rows",
    "registration_imports",
    "round_controls",
    "submissions",
    "teams",
    "users",
    "wallet_transactions",
    "wildcard_bids",
    "wildcard_selection_pool",
    "wildcards",
}


def _has_foreign_key(inspector, table: str, columns: list[str], referred_table: str) -> bool:
    return any(
        foreign_key.get("constrained_columns") == columns
        and foreign_key.get("referred_table") == referred_table
        for foreign_key in inspector.get_foreign_keys(table)
    )


def _reconcile_legacy_schema() -> bool:
    """Bring the known pre-Alembic production schema to this baseline.

    Alembic creates its version table before invoking the first migration, so
    it is excluded when deciding whether this is a genuinely fresh database.
    Any partial/unknown schema stops with an actionable error instead of
    blindly creating, dropping, or stamping tables.
    """
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    application_tables = set(inspector.get_table_names()) - {"alembic_version"}
    if not application_tables:
        return False

    missing_tables = BASELINE_TABLES - application_tables
    if missing_tables:
        raise RuntimeError(
            "Legacy schema does not match the known production baseline; "
            f"missing tables: {sorted(missing_tables)}"
        )

    users_columns = {column["name"]: column for column in inspector.get_columns("users")}
    if users_columns["created_at"]["nullable"]:
        null_created_at = connection.execute(
            sa.text("SELECT COUNT(*) FROM users WHERE created_at IS NULL")
        ).scalar_one()
        if null_created_at:
            # The pre-Alembic production schema allowed this field to be null.
            # Its original timestamps cannot be recovered, so use the migration
            # time before enforcing the baseline's non-null constraint.
            connection.execute(
                sa.text("UPDATE users SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
            )
        with op.batch_alter_table("users", recreate="always") as batch_op:
            batch_op.alter_column(
                "created_at",
                existing_type=sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )

    inspector = sa.inspect(connection)
    round_column_details = {
        column["name"]: column for column in inspector.get_columns("round_controls")
    }
    round_columns = set(round_column_details)
    aggregate_columns = {
        "round1_winning_bid_sum",
        "round1_winning_bid_count",
    }
    for column_name in sorted(aggregate_columns - round_columns):
        op.add_column(
            "round_controls",
            sa.Column(column_name, sa.Integer(), nullable=True),
        )
        connection.execute(
            sa.text(f"UPDATE round_controls SET {column_name} = 0 WHERE {column_name} IS NULL")
        )

    inspector = sa.inspect(connection)
    round_column_details = {
        column["name"]: column for column in inspector.get_columns("round_controls")
    }
    missing_round_fk = not _has_foreign_key(
        inspector,
        "round_controls",
        ["final_auto_assignment_problem_id"],
        "problem_statements",
    )
    aggregate_nullable = any(
        round_column_details[column_name]["nullable"]
        for column_name in aggregate_columns
    )
    if aggregate_nullable or missing_round_fk:
        with op.batch_alter_table("round_controls", recreate="always") as batch_op:
            for column_name in sorted(aggregate_columns):
                batch_op.alter_column(
                    column_name,
                    existing_type=sa.Integer(),
                    nullable=False,
                )
            if missing_round_fk:
                batch_op.create_foreign_key(
                    "fk_round_controls_final_auto_assignment_problem_id",
                    "problem_statements",
                    ["final_auto_assignment_problem_id"],
                    ["id"],
                    ondelete="SET NULL",
                )

    inspector = sa.inspect(connection)
    if not _has_foreign_key(
        inspector,
        "registration_import_rows",
        ["team_id"],
        "teams",
    ):
        orphaned_team_references = connection.execute(
            sa.text(
                "SELECT COUNT(*) FROM registration_import_rows AS rows "
                "LEFT JOIN teams ON teams.id = rows.team_id "
                "WHERE rows.team_id IS NOT NULL AND teams.id IS NULL"
            )
        ).scalar_one()
        if orphaned_team_references:
            raise RuntimeError(
                "Cannot add registration_import_rows.team_id foreign key while orphaned values exist."
            )
        with op.batch_alter_table("registration_import_rows", recreate="always") as batch_op:
            batch_op.create_foreign_key(
                "fk_registration_import_rows_team_id",
                "teams",
                ["team_id"],
                ["id"],
                ondelete="SET NULL",
            )

    return True


def upgrade() -> None:
    if not context.is_offline_mode() and _reconcile_legacy_schema():
        return

    op.create_table(
        "problem_statements", _id_column(),
        sa.Column("ps_number", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("round", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.UniqueConstraint("ps_number"),
    )
    op.create_index("ix_problem_statements_id", "problem_statements", ["id"])
    op.create_index("ix_problem_statements_ps_number", "problem_statements", ["ps_number"], unique=True)

    # users.team_id participates in a cycle with teams.leader_id, so its FK is
    # added after both tables exist.
    op.create_table(
        "users", _id_column(),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("is_system_account", sa.Boolean(), nullable=False),
        sa.Column("account_source", sa.String(), nullable=False),
        sa.Column("credentials_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "teams", _id_column(),
        sa.Column("team_name", sa.String(), nullable=False),
        sa.Column("coins", sa.Integer(), nullable=True),
        sa.Column("leader_id", sa.Integer(), nullable=True),
        sa.Column("ps_id", sa.Integer(), nullable=True),
        sa.Column("round1_problem_id", sa.Integer(), nullable=True),
        sa.Column("wildcard_problem_id", sa.Integer(), nullable=True),
        sa.Column("round1_assignment_type", sa.String(), nullable=True),
        sa.Column("round1_assignment_cost", sa.Integer(), nullable=True),
        sa.Column("is_approved", sa.Boolean(), nullable=True),
        sa.Column("is_system_team", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["leader_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ps_id"], ["problem_statements.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["round1_problem_id"], ["problem_statements.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["wildcard_problem_id"], ["problem_statements.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("leader_id"), sa.UniqueConstraint("team_name"),
    )
    op.create_index("ix_teams_id", "teams", ["id"])
    op.create_index("ix_teams_team_name", "teams", ["team_name"], unique=True)
    op.create_foreign_key(
        "fk_users_team_id_teams",
        "users",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "round_controls", _id_column(),
        sa.Column("round_type", sa.String(), nullable=False),
        sa.Column("current_problem_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=True), sa.Column("ended", sa.Boolean(), nullable=True),
        sa.Column("applications_open", sa.Boolean(), nullable=True), sa.Column("slot_count", sa.Integer(), nullable=True),
        sa.Column("selection_pool_frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_selection_rank", sa.Integer(), nullable=True),
        sa.Column("selection_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("selection_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("selection_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("final_auto_assignment_problem_id", sa.Integer(), nullable=True),
        sa.Column("final_auto_assignment_price", sa.Integer(), nullable=True),
        sa.Column("final_auto_assignment_team_count", sa.Integer(), nullable=True),
        sa.Column("round1_winning_bid_sum", sa.Integer(), nullable=False),
        sa.Column("round1_winning_bid_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["current_problem_id"], ["problem_statements.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["final_auto_assignment_problem_id"], ["problem_statements.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("round_type"),
    )
    op.create_index("ix_round_controls_id", "round_controls", ["id"])
    op.create_index("ix_round_controls_round_type", "round_controls", ["round_type"], unique=True)

    op.create_table("members", _id_column(), sa.Column("team_id", sa.Integer()), sa.Column("member_name", sa.String(), nullable=False), sa.Column("email", sa.String()), sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"))
    op.create_index("ix_members_id", "members", ["id"])
    op.create_index("ix_members_team_id", "members", ["team_id"])
    op.create_table("bids", _id_column(), sa.Column("team_id", sa.Integer()), sa.Column("ps_id", sa.Integer()), sa.Column("amount", sa.Integer(), nullable=False), sa.Column("round", sa.Integer(), nullable=False), sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")), sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["ps_id"], ["problem_statements.id"], ondelete="CASCADE"), sa.UniqueConstraint("team_id", "ps_id", "round", name="uq_bid_team_problem_round"))
    op.create_index("ix_bids_id", "bids", ["id"])
    op.create_index("ix_bids_problem_round_rank", "bids", ["ps_id", "round", sa.text("amount DESC"), sa.text("timestamp ASC"), sa.text("team_id ASC")])
    op.create_table("wildcards", _id_column(), sa.Column("team_id", sa.Integer()), sa.Column("coins_paid", sa.Integer(), nullable=False), sa.Column("used", sa.Boolean()), sa.Column("status", sa.String()), sa.Column("applied_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")), sa.Column("rank", sa.Integer()), sa.Column("winning_bid", sa.Integer()), sa.Column("problem_id", sa.Integer()), sa.Column("selected_at", sa.DateTime(timezone=True)), sa.Column("selection_method", sa.String()), sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["problem_id"], ["problem_statements.id"], ondelete="SET NULL"), sa.UniqueConstraint("team_id"), sa.UniqueConstraint("problem_id"), sa.UniqueConstraint("rank", name="uq_wildcards_rank"))
    op.create_index("ix_wildcards_id", "wildcards", ["id"])
    op.create_table("wildcard_selection_pool", _id_column(), sa.Column("position", sa.Integer(), nullable=False), sa.Column("problem_id", sa.Integer(), nullable=False), sa.Column("selected_by_team_id", sa.Integer()), sa.Column("frozen_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False), sa.Column("selected_at", sa.DateTime(timezone=True)), sa.ForeignKeyConstraint(["problem_id"], ["problem_statements.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["selected_by_team_id"], ["teams.id"], ondelete="SET NULL"), sa.UniqueConstraint("position", name="uq_wildcard_pool_position"), sa.UniqueConstraint("problem_id", name="uq_wildcard_pool_problem"), sa.UniqueConstraint("selected_by_team_id", name="uq_wildcard_pool_selected_team"))
    op.create_index("ix_wildcard_selection_pool_id", "wildcard_selection_pool", ["id"])
    op.create_table("wildcard_bids", _id_column(), sa.Column("team_id", sa.Integer(), nullable=False), sa.Column("amount", sa.Integer(), nullable=False), sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False), sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"), sa.UniqueConstraint("team_id"))
    op.create_index("ix_wildcard_bids_id", "wildcard_bids", ["id"])
    op.create_table("exchange_requests", _id_column(), sa.Column("requester_team_id", sa.Integer()), sa.Column("receiver_team_id", sa.Integer()), sa.Column("requester_ps_id", sa.Integer()), sa.Column("receiver_ps_id", sa.Integer()), sa.Column("status", sa.String()), sa.ForeignKeyConstraint(["requester_team_id"], ["teams.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["receiver_team_id"], ["teams.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["requester_ps_id"], ["problem_statements.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["receiver_ps_id"], ["problem_statements.id"], ondelete="CASCADE"))
    op.create_index("ix_exchange_requests_id", "exchange_requests", ["id"])
    op.create_table("wallet_transactions", _id_column(), sa.Column("team_id", sa.Integer()), sa.Column("transaction_type", sa.String(), nullable=False), sa.Column("amount", sa.Integer(), nullable=False), sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")), sa.Column("description", sa.String()), sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"), sa.UniqueConstraint("team_id", "transaction_type", "description", name="uq_wallet_operation"))
    op.create_index("ix_wallet_transactions_id", "wallet_transactions", ["id"])
    op.create_table("submissions", _id_column(), sa.Column("team_id", sa.Integer()), sa.Column("problem_id", sa.Integer()), sa.Column("submitted_by_user_id", sa.Integer()), sa.Column("repository_url", sa.String(), nullable=False), sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")), sa.Column("updated_at", sa.DateTime(timezone=True)), sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["problem_id"], ["problem_statements.id"], ondelete="SET NULL"), sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"], ondelete="SET NULL"), sa.UniqueConstraint("team_id"))
    op.create_index("ix_submissions_id", "submissions", ["id"])
    op.create_table("final_results", _id_column(), sa.Column("first_place_team_id", sa.Integer()), sa.Column("second_place_team_id", sa.Integer()), sa.Column("third_place_team_id", sa.Integer()), sa.Column("saved_at", sa.DateTime(timezone=True)), sa.Column("published_at", sa.DateTime(timezone=True)), sa.Column("result_status", sa.String(), nullable=False), sa.ForeignKeyConstraint(["first_place_team_id"], ["teams.id"], ondelete="SET NULL"), sa.ForeignKeyConstraint(["second_place_team_id"], ["teams.id"], ondelete="SET NULL"), sa.ForeignKeyConstraint(["third_place_team_id"], ["teams.id"], ondelete="SET NULL"))
    op.create_table("registration_imports", _id_column(), sa.Column("filename", sa.String(), nullable=False), sa.Column("status", sa.String()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")), sa.Column("committed_at", sa.DateTime(timezone=True)), sa.Column("source_name", sa.String()), sa.Column("source_headers_json", sa.Text(), nullable=False))
    op.create_index("ix_registration_imports_id", "registration_imports", ["id"])
    op.create_table("registration_import_rows", _id_column(), sa.Column("import_id", sa.Integer()), sa.Column("row_number", sa.Integer(), nullable=False), sa.Column("team_name", sa.String(), nullable=False), sa.Column("leader_name", sa.String(), nullable=False), sa.Column("leader_email", sa.String(), nullable=False), sa.Column("members_json", sa.Text(), nullable=False), sa.Column("status", sa.String()), sa.Column("warnings_json", sa.Text(), nullable=False), sa.Column("source_values_json", sa.Text(), nullable=False), sa.Column("team_id", sa.Integer()), sa.ForeignKeyConstraint(["import_id"], ["registration_imports.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"))
    op.create_index("ix_registration_import_rows_id", "registration_import_rows", ["id"])
    op.create_table("game_config", _id_column(), sa.Column("current_round", sa.Integer()), sa.Column("auction_timer_end", sa.DateTime(timezone=True)), sa.Column("wildcards_visible", sa.Boolean()), sa.Column("state", sa.String()), sa.Column("phase_started_at", sa.DateTime(timezone=True)), sa.Column("timer_paused", sa.Boolean()), sa.Column("timer_paused_remaining_seconds", sa.Integer()), sa.Column("timer_bias_seconds", sa.Integer()), sa.Column("last_state_update", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")))
    op.create_index("ix_game_config_id", "game_config", ["id"])
    op.create_table("event_config", _id_column(), sa.Column("starting_coins", sa.Integer()), sa.Column("round1_preview_seconds", sa.Integer()), sa.Column("round1_bid_seconds", sa.Integer()), sa.Column("round1_winner_count", sa.Integer()), sa.Column("round1_minimum_bid", sa.Integer()), sa.Column("round1_bid_increment", sa.Integer()), sa.Column("wildcard_enabled", sa.Boolean()), sa.Column("wildcard_slots", sa.Integer()), sa.Column("wildcard_application_seconds", sa.Integer()), sa.Column("wildcard_problem_count", sa.Integer()), sa.Column("wildcard_preview_seconds", sa.Integer()), sa.Column("wildcard_bid_seconds", sa.Integer()), sa.Column("wildcard_selection_seconds", sa.Integer()), sa.Column("wildcard_starting_bid", sa.Integer()), sa.Column("wildcard_bid_increment", sa.Integer()), sa.Column("submissions_open", sa.Boolean()), sa.Column("coding_duration_seconds", sa.Integer()), sa.Column("bid_cooldown_seconds", sa.Integer()), sa.Column("royalty_coins_per_point", sa.Integer()), sa.Column("royalty_max_points", sa.Integer()))
    op.create_index("ix_event_config_id", "event_config", ["id"])
    op.create_table("event_activity_log", _id_column(), sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False), sa.Column("actor_type", sa.String(), nullable=False), sa.Column("actor_id", sa.Integer()), sa.Column("action", sa.String(), nullable=False), sa.Column("entity_type", sa.String()), sa.Column("entity_id", sa.Integer()), sa.Column("metadata_json", sa.Text(), nullable=False))
    op.create_index("ix_event_activity_log_id", "event_activity_log", ["id"])
    op.create_index("ix_event_activity_log_timestamp", "event_activity_log", ["timestamp"])
    op.create_index("ix_event_activity_log_action", "event_activity_log", ["action"])


def downgrade() -> None:
    raise RuntimeError("The initial production schema migration is intentionally irreversible.")
