from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False) # 'admin' or 'leader'
    session_id = Column(String, nullable=True) # Used to track the active session

class ProblemStatement(Base):
    __tablename__ = "problem_statements"
    
    id = Column(Integer, primary_key=True, index=True)
    ps_number = Column(String, unique=True, index=True, nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    round = Column(Integer, default=1)
    status = Column(String, default='visible') # hidden, visible, allocated

class Team(Base):
    __tablename__ = "teams"
    
    id = Column(Integer, primary_key=True, index=True)
    team_name = Column(String, unique=True, index=True, nullable=False)
    coins = Column(Integer, default=1000)
    leader_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    ps_id = Column(Integer, ForeignKey("problem_statements.id", ondelete="SET NULL"), nullable=True)
    is_approved = Column(Boolean, default=False)
    
    members = relationship("Member", back_populates="team", cascade="all, delete-orphan")
    bids = relationship("Bid", back_populates="team", cascade="all, delete-orphan")
    wildcard = relationship("Wildcard", back_populates="team", uselist=False, cascade="all, delete-orphan")

class Member(Base):
    __tablename__ = "members"
    
    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"))
    member_name = Column(String, nullable=False)
    
    team = relationship("Team", back_populates="members")

class Bid(Base):
    __tablename__ = "bids"
    
    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"))
    ps_id = Column(Integer, ForeignKey("problem_statements.id", ondelete="CASCADE"))
    amount = Column(Integer, nullable=False)
    round = Column(Integer, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    team = relationship("Team", back_populates="bids")
    problem_statement = relationship("ProblemStatement")

class Wildcard(Base):
    __tablename__ = "wildcards"
    
    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), unique=True)
    coins_paid = Column(Integer, nullable=False)
    used = Column(Boolean, default=False)
    
    team = relationship("Team", back_populates="wildcard")

class ExchangeRequest(Base):
    __tablename__ = "exchange_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    requester_team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"))
    receiver_team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"))
    requester_ps_id = Column(Integer, ForeignKey("problem_statements.id", ondelete="CASCADE"))
    receiver_ps_id = Column(Integer, ForeignKey("problem_statements.id", ondelete="CASCADE"))
    status = Column(String, default="pending") # pending, accepted, rejected

class GameConfig(Base):
    __tablename__ = "game_config"
    
    id = Column(Integer, primary_key=True, index=True)
    current_round = Column(Integer, default=1)
    auction_timer_end = Column(DateTime(timezone=True), nullable=True)
    wildcards_visible = Column(Boolean, default=False)
