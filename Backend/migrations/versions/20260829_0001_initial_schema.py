"""Initial Bid to Build schema.

Revision ID: 20260829_0001
Revises: None
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260829_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _id_column() -> sa.Column:
    return sa.Column("id", sa.Integer(), primary_key=True, nullable=False)


def upgrade() -> None:
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
    op.create_index("ix_problem_statements_ps_number", "problem_statements", ["ps_number"])

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
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_email", "users", ["email"])

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
    op.create_index("ix_teams_team_name", "teams", ["team_name"])
    op.create_foreign_key("fk_users_team_id_teams", "users", "teams", ["team_id"], ["id"], ondelete="SET NULL")

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
    op.create_index("ix_round_controls_round_type", "round_controls", ["round_type"])

    op.create_table("members", _id_column(), sa.Column("team_id", sa.Integer()), sa.Column("member_name", sa.String(), nullable=False), sa.Column("email", sa.String()), sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"))
    op.create_index("ix_members_id", "members", ["id"])
    op.create_index("ix_members_team_id", "members", ["team_id"])
    op.create_table("bids", _id_column(), sa.Column("team_id", sa.Integer()), sa.Column("ps_id", sa.Integer()), sa.Column("amount", sa.Integer(), nullable=False), sa.Column("round", sa.Integer(), nullable=False), sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()")), sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["ps_id"], ["problem_statements.id"], ondelete="CASCADE"), sa.UniqueConstraint("team_id", "ps_id", "round", name="uq_bid_team_problem_round"))
    op.create_index("ix_bids_id", "bids", ["id"])
    op.create_index("ix_bids_problem_round_rank", "bids", ["ps_id", "round", sa.text("amount DESC"), sa.text("timestamp ASC"), sa.text("team_id ASC")])
    op.create_table("wildcards", _id_column(), sa.Column("team_id", sa.Integer()), sa.Column("coins_paid", sa.Integer(), nullable=False), sa.Column("used", sa.Boolean()), sa.Column("status", sa.String()), sa.Column("applied_at", sa.DateTime(timezone=True), server_default=sa.text("now()")), sa.Column("rank", sa.Integer()), sa.Column("winning_bid", sa.Integer()), sa.Column("problem_id", sa.Integer()), sa.Column("selected_at", sa.DateTime(timezone=True)), sa.Column("selection_method", sa.String()), sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["problem_id"], ["problem_statements.id"], ondelete="SET NULL"), sa.UniqueConstraint("team_id"), sa.UniqueConstraint("problem_id"), sa.UniqueConstraint("rank", name="uq_wildcards_rank"))
    op.create_index("ix_wildcards_id", "wildcards", ["id"])
    op.create_table("wildcard_selection_pool", _id_column(), sa.Column("position", sa.Integer(), nullable=False), sa.Column("problem_id", sa.Integer(), nullable=False), sa.Column("selected_by_team_id", sa.Integer()), sa.Column("frozen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("selected_at", sa.DateTime(timezone=True)), sa.ForeignKeyConstraint(["problem_id"], ["problem_statements.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["selected_by_team_id"], ["teams.id"], ondelete="SET NULL"), sa.UniqueConstraint("position", name="uq_wildcard_pool_position"), sa.UniqueConstraint("problem_id", name="uq_wildcard_pool_problem"), sa.UniqueConstraint("selected_by_team_id", name="uq_wildcard_pool_selected_team"))
    op.create_index("ix_wildcard_selection_pool_id", "wildcard_selection_pool", ["id"])
    op.create_table("wildcard_bids", _id_column(), sa.Column("team_id", sa.Integer(), nullable=False), sa.Column("amount", sa.Integer(), nullable=False), sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"), sa.UniqueConstraint("team_id"))
    op.create_index("ix_wildcard_bids_id", "wildcard_bids", ["id"])
    op.create_table("exchange_requests", _id_column(), sa.Column("requester_team_id", sa.Integer()), sa.Column("receiver_team_id", sa.Integer()), sa.Column("requester_ps_id", sa.Integer()), sa.Column("receiver_ps_id", sa.Integer()), sa.Column("status", sa.String()), sa.ForeignKeyConstraint(["requester_team_id"], ["teams.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["receiver_team_id"], ["teams.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["requester_ps_id"], ["problem_statements.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["receiver_ps_id"], ["problem_statements.id"], ondelete="CASCADE"))
    op.create_index("ix_exchange_requests_id", "exchange_requests", ["id"])
    op.create_table("wallet_transactions", _id_column(), sa.Column("team_id", sa.Integer()), sa.Column("transaction_type", sa.String(), nullable=False), sa.Column("amount", sa.Integer(), nullable=False), sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()")), sa.Column("description", sa.String()), sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"), sa.UniqueConstraint("team_id", "transaction_type", "description", name="uq_wallet_operation"))
    op.create_index("ix_wallet_transactions_id", "wallet_transactions", ["id"])
    op.create_table("submissions", _id_column(), sa.Column("team_id", sa.Integer()), sa.Column("problem_id", sa.Integer()), sa.Column("submitted_by_user_id", sa.Integer()), sa.Column("repository_url", sa.String(), nullable=False), sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.text("now()")), sa.Column("updated_at", sa.DateTime(timezone=True)), sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["problem_id"], ["problem_statements.id"], ondelete="SET NULL"), sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"], ondelete="SET NULL"), sa.UniqueConstraint("team_id"))
    op.create_index("ix_submissions_id", "submissions", ["id"])
    op.create_table("final_results", _id_column(), sa.Column("first_place_team_id", sa.Integer()), sa.Column("second_place_team_id", sa.Integer()), sa.Column("third_place_team_id", sa.Integer()), sa.Column("saved_at", sa.DateTime(timezone=True)), sa.Column("published_at", sa.DateTime(timezone=True)), sa.Column("result_status", sa.String(), nullable=False), sa.ForeignKeyConstraint(["first_place_team_id"], ["teams.id"], ondelete="SET NULL"), sa.ForeignKeyConstraint(["second_place_team_id"], ["teams.id"], ondelete="SET NULL"), sa.ForeignKeyConstraint(["third_place_team_id"], ["teams.id"], ondelete="SET NULL"))
    op.create_table("registration_imports", _id_column(), sa.Column("filename", sa.String(), nullable=False), sa.Column("status", sa.String()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")), sa.Column("committed_at", sa.DateTime(timezone=True)), sa.Column("source_name", sa.String()), sa.Column("source_headers_json", sa.Text(), nullable=False))
    op.create_index("ix_registration_imports_id", "registration_imports", ["id"])
    op.create_table("registration_import_rows", _id_column(), sa.Column("import_id", sa.Integer()), sa.Column("row_number", sa.Integer(), nullable=False), sa.Column("team_name", sa.String(), nullable=False), sa.Column("leader_name", sa.String(), nullable=False), sa.Column("leader_email", sa.String(), nullable=False), sa.Column("members_json", sa.Text(), nullable=False), sa.Column("status", sa.String()), sa.Column("warnings_json", sa.Text(), nullable=False), sa.Column("source_values_json", sa.Text(), nullable=False), sa.Column("team_id", sa.Integer()), sa.ForeignKeyConstraint(["import_id"], ["registration_imports.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"))
    op.create_index("ix_registration_import_rows_id", "registration_import_rows", ["id"])
    op.create_table("game_config", _id_column(), sa.Column("current_round", sa.Integer()), sa.Column("auction_timer_end", sa.DateTime(timezone=True)), sa.Column("wildcards_visible", sa.Boolean()), sa.Column("state", sa.String()), sa.Column("phase_started_at", sa.DateTime(timezone=True)), sa.Column("timer_paused", sa.Boolean()), sa.Column("timer_paused_remaining_seconds", sa.Integer()), sa.Column("timer_bias_seconds", sa.Integer()), sa.Column("last_state_update", sa.DateTime(timezone=True), server_default=sa.text("now()")))
    op.create_index("ix_game_config_id", "game_config", ["id"])
    op.create_table("event_config", _id_column(), sa.Column("starting_coins", sa.Integer()), sa.Column("round1_preview_seconds", sa.Integer()), sa.Column("round1_bid_seconds", sa.Integer()), sa.Column("round1_winner_count", sa.Integer()), sa.Column("round1_minimum_bid", sa.Integer()), sa.Column("round1_bid_increment", sa.Integer()), sa.Column("wildcard_enabled", sa.Boolean()), sa.Column("wildcard_slots", sa.Integer()), sa.Column("wildcard_application_seconds", sa.Integer()), sa.Column("wildcard_problem_count", sa.Integer()), sa.Column("wildcard_preview_seconds", sa.Integer()), sa.Column("wildcard_bid_seconds", sa.Integer()), sa.Column("wildcard_selection_seconds", sa.Integer()), sa.Column("wildcard_starting_bid", sa.Integer()), sa.Column("wildcard_bid_increment", sa.Integer()), sa.Column("submissions_open", sa.Boolean()), sa.Column("coding_duration_seconds", sa.Integer()), sa.Column("bid_cooldown_seconds", sa.Integer()), sa.Column("royalty_coins_per_point", sa.Integer()), sa.Column("royalty_max_points", sa.Integer()))
    op.create_index("ix_event_config_id", "event_config", ["id"])
    op.create_table("event_activity_log", _id_column(), sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("actor_type", sa.String(), nullable=False), sa.Column("actor_id", sa.Integer()), sa.Column("action", sa.String(), nullable=False), sa.Column("entity_type", sa.String()), sa.Column("entity_id", sa.Integer()), sa.Column("metadata_json", sa.Text(), nullable=False))
    op.create_index("ix_event_activity_log_id", "event_activity_log", ["id"])
    op.create_index("ix_event_activity_log_timestamp", "event_activity_log", ["timestamp"])
    op.create_index("ix_event_activity_log_action", "event_activity_log", ["action"])


def downgrade() -> None:
    raise RuntimeError("The initial production schema migration is intentionally irreversible.")
