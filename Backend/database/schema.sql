-- Database Schema for Hackathon Auction Platform
-- This is for verification purposes. SQLAlchemy's Base.metadata.create_all() will execute similar commands.

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR NOT NULL,
    email VARCHAR UNIQUE NOT NULL,
    password_hash VARCHAR NOT NULL,
    role VARCHAR NOT NULL,
    session_id VARCHAR
);
CREATE INDEX ix_users_email ON users (email);

CREATE TABLE problem_statements (
    id SERIAL PRIMARY KEY,
    ps_number VARCHAR UNIQUE NOT NULL,
    title VARCHAR NOT NULL,
    description VARCHAR,
    round INTEGER DEFAULT 1,
    status VARCHAR DEFAULT 'visible'
);
CREATE INDEX ix_problem_statements_ps_number ON problem_statements (ps_number);

CREATE TABLE teams (
    id SERIAL PRIMARY KEY,
    team_name VARCHAR UNIQUE NOT NULL,
    coins INTEGER DEFAULT 1000,
    leader_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    ps_id INTEGER REFERENCES problem_statements(id) ON DELETE SET NULL,
    is_approved BOOLEAN DEFAULT FALSE
);
CREATE INDEX ix_teams_team_name ON teams (team_name);

CREATE TABLE members (
    id SERIAL PRIMARY KEY,
    team_id INTEGER REFERENCES teams(id) ON DELETE CASCADE,
    member_name VARCHAR NOT NULL
);

CREATE TABLE bids (
    id SERIAL PRIMARY KEY,
    team_id INTEGER REFERENCES teams(id) ON DELETE CASCADE,
    ps_id INTEGER REFERENCES problem_statements(id) ON DELETE CASCADE,
    amount INTEGER NOT NULL,
    round INTEGER NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE wildcards (
    id SERIAL PRIMARY KEY,
    team_id INTEGER UNIQUE REFERENCES teams(id) ON DELETE CASCADE,
    coins_paid INTEGER NOT NULL,
    used BOOLEAN DEFAULT FALSE
);

CREATE TABLE exchange_requests (
    id SERIAL PRIMARY KEY,
    requester_team_id INTEGER REFERENCES teams(id) ON DELETE CASCADE,
    receiver_team_id INTEGER REFERENCES teams(id) ON DELETE CASCADE,
    requester_ps_id INTEGER REFERENCES problem_statements(id) ON DELETE CASCADE,
    receiver_ps_id INTEGER REFERENCES problem_statements(id) ON DELETE CASCADE,
    status VARCHAR DEFAULT 'pending'
);

CREATE TABLE game_config (
    id SERIAL PRIMARY KEY,
    current_round INTEGER DEFAULT 1,
    auction_timer_end TIMESTAMP WITH TIME ZONE,
    wildcards_visible BOOLEAN DEFAULT FALSE
);
