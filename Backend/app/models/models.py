from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False) # 'admin', 'leader' or 'member'
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    session_id = Column(String, nullable=True) # Used to track the active session

class ProblemStatement(Base):
    __tablename__ = "problem_statements"

    id = Column(Integer, primary_key=True, index=True)
    ps_number = Column(String, unique=True, index=True, nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    round = Column(Integer, default=1) # 1 = Round 1, 2 = Wildcard / Bonus problem
    status = Column(String, default='visible') # hidden, visible, allocated

class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    team_name = Column(String, unique=True, index=True, nullable=False)
    coins = Column(Integer, default=1000)
    leader_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    ps_id = Column(Integer, ForeignKey("problem_statements.id", ondelete="SET NULL"), nullable=True)
    is_approved = Column(Boolean, default=True)

    members = relationship("Member", back_populates="team", cascade="all, delete-orphan")
    bids = relationship("Bid", back_populates="team", cascade="all, delete-orphan")
    wildcard = relationship("Wildcard", back_populates="team", uselist=False, cascade="all, delete-orphan")
    transactions = relationship("WalletTransaction", back_populates="team", cascade="all, delete-orphan")
    submission = relationship("Submission", back_populates="team", uselist=False, cascade="all, delete-orphan")

class Member(Base):
    __tablename__ = "members"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"))
    member_name = Column(String, nullable=False)
    email = Column(String, nullable=True)

    team = relationship("Team", back_populates="members")

class Bid(Base):
    __tablename__ = "bids"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"))
    ps_id = Column(Integer, ForeignKey("problem_statements.id", ondelete="CASCADE"))
    amount = Column(Integer, nullable=False)
    round = Column(Integer, nullable=False) # 1 = Round 1, 2 = Wildcard auction
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    team = relationship("Team", back_populates="bids")
    problem_statement = relationship("ProblemStatement")

class Wildcard(Base):
    __tablename__ = "wildcards"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), unique=True)
    coins_paid = Column(Integer, nullable=False, default=0)
    used = Column(Boolean, default=False)
    status = Column(String, default='bid') # 'bid', 'won', 'selected'

    team = relationship("Team", back_populates="wildcard")

class ExchangeRequest(Base):
    __tablename__ = "exchange_requests"

    id = Column(Integer, primary_key=True, index=True)
    requester_team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"))
    receiver_team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"))
    requester_ps_id = Column(Integer, ForeignKey("problem_statements.id", ondelete="CASCADE"))
    receiver_ps_id = Column(Integer, ForeignKey("problem_statements.id", ondelete="CASCADE"))
    status = Column(String, default="pending") # pending, accepted, rejected

class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"))
    transaction_type = Column(String, nullable=False) # INITIAL_ALLOCATION, ROUND1_WIN, WILDCARD_WIN, ADMIN_ADJUSTMENT
    amount = Column(Integer, nullable=False) # signed: +credit / -debit
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    description = Column(String, nullable=True)

    team = relationship("Team", back_populates="transactions")

class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), unique=True)
    problem_id = Column(Integer, ForeignKey("problem_statements.id", ondelete="SET NULL"))
    repository_url = Column(String, nullable=False)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    team = relationship("Team", back_populates="submission")

class RegistrationImport(Base):
    __tablename__ = "registration_imports"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    status = Column(String, default='pending') # 'pending', 'committed'
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    committed_at = Column(DateTime(timezone=True), nullable=True)
    source_name = Column(String, nullable=True) # file fingerprint for idempotency

    rows = relationship("RegistrationImportRow", back_populates="import_record", cascade="all, delete-orphan")

class RegistrationImportRow(Base):
    __tablename__ = "registration_import_rows"

    id = Column(Integer, primary_key=True, index=True)
    import_id = Column(Integer, ForeignKey("registration_imports.id", ondelete="CASCADE"))
    row_number = Column(Integer, nullable=False)
    team_name = Column(String, nullable=False)
    leader_name = Column(String, nullable=False)
    leader_email = Column(String, nullable=False)
    members_json = Column(Text, nullable=False, default="[]") # JSON list of {name, email}
    status = Column(String, default='new') # 'new', 'update', 'duplicate', 'error'
    warnings_json = Column(Text, nullable=False, default="[]")

    import_record = relationship("RegistrationImport", back_populates="rows")

class GameConfig(Base):
    __tablename__ = "game_config"

    id = Column(Integer, primary_key=True, index=True)
    current_round = Column(Integer, default=1)
    auction_timer_end = Column(DateTime(timezone=True), nullable=True)
    wildcards_visible = Column(Boolean, default=False)
    state = Column(String, default='WAITING') # event state machine, see schemas.EVENT_STATES
    phase_started_at = Column(DateTime(timezone=True), nullable=True)
    timer_paused = Column(Boolean, default=False)
    timer_paused_remaining_seconds = Column(Integer, nullable=True)
    timer_bias_seconds = Column(Integer, default=0) # admin ADD/REMOVE TIME adjustments

class EventConfig(Base):
    __tablename__ = "event_config"

    id = Column(Integer, primary_key=True, index=True)
    # Starting coins
    starting_coins = Column(Integer, default=1000)

    # Round 1
    round1_preview_seconds = Column(Integer, default=120)
    round1_bid_seconds = Column(Integer, default=300)
    round1_winner_count = Column(Integer, default=5)
    round1_minimum_bid = Column(Integer, default=25)
    round1_bid_increment = Column(Integer, default=1)

    # Wildcard
    wildcard_enabled = Column(Boolean, default=True)
    wildcard_slots = Column(Integer, default=3)
    wildcard_problem_count = Column(Integer, default=3)
    wildcard_preview_seconds = Column(Integer, default=120)
    wildcard_bid_seconds = Column(Integer, default=180)
    wildcard_starting_bid = Column(Integer, default=150)
    wildcard_bid_increment = Column(Integer, default=1)

    # Coding
    coding_duration_seconds = Column(Integer, default=10800)  # 3 hours

    # Royalty
    royalty_coins_per_point = Column(Integer, default=10)
    royalty_max_points = Column(Integer, default=100)
