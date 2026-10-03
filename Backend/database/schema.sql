-- Bid to Build: current PostgreSQL schema reference
-- PostgreSQL is the runtime database; Alembic migrations are authoritative.
-- Snapshot generated from an empty PostgreSQL 16 database after applying all
-- migrations through 20260919_0006, cross-checked against ORM metadata.
-- This human-readable, schema-only snapshot includes the Alembic version table,
-- but no version-row data, application data, owners, grants or credentials.
-- Production upgrades must use: python -m alembic upgrade head
-- This reference does not replace Alembic or its data migrations.
-- ORM-side defaults are not server defaults and are not invented in this SQL.

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: bids; Type: TABLE; Schema: public
--

CREATE TABLE public.bids (
    id integer NOT NULL,
    team_id integer,
    ps_id integer,
    amount integer NOT NULL,
    round integer NOT NULL,
    "timestamp" timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: bids_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.bids_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: bids_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.bids_id_seq OWNED BY public.bids.id;


--
-- Name: event_activity_log; Type: TABLE; Schema: public
--

CREATE TABLE public.event_activity_log (
    id integer NOT NULL,
    "timestamp" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    actor_type character varying NOT NULL,
    actor_id integer,
    action character varying NOT NULL,
    entity_type character varying,
    entity_id integer,
    metadata_json text NOT NULL
);


--
-- Name: event_activity_log_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.event_activity_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: event_activity_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.event_activity_log_id_seq OWNED BY public.event_activity_log.id;


--
-- Name: event_config; Type: TABLE; Schema: public
--

CREATE TABLE public.event_config (
    id integer NOT NULL,
    starting_coins integer,
    round1_preview_seconds integer,
    round1_bid_seconds integer,
    round1_winner_count integer,
    round1_minimum_bid integer,
    round1_bid_increment integer,
    wildcard_enabled boolean,
    wildcard_slots integer,
    wildcard_application_seconds integer,
    wildcard_problem_count integer,
    wildcard_preview_seconds integer,
    wildcard_bid_seconds integer,
    wildcard_selection_seconds integer,
    wildcard_starting_bid integer,
    wildcard_bid_increment integer,
    submissions_open boolean,
    coding_duration_seconds integer,
    bid_cooldown_seconds integer,
    royalty_coins_per_point integer,
    royalty_max_points integer,
    wildcard_final_choice_seconds integer DEFAULT 60 NOT NULL
);


--
-- Name: event_config_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.event_config_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: event_config_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.event_config_id_seq OWNED BY public.event_config.id;


--
-- Name: exchange_requests; Type: TABLE; Schema: public
--

CREATE TABLE public.exchange_requests (
    id integer NOT NULL,
    requester_team_id integer,
    receiver_team_id integer,
    requester_ps_id integer,
    receiver_ps_id integer,
    status character varying
);


--
-- Name: exchange_requests_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.exchange_requests_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: exchange_requests_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.exchange_requests_id_seq OWNED BY public.exchange_requests.id;


--
-- Name: final_results; Type: TABLE; Schema: public
--

CREATE TABLE public.final_results (
    id integer NOT NULL,
    first_place_team_id integer,
    second_place_team_id integer,
    third_place_team_id integer,
    saved_at timestamp with time zone,
    published_at timestamp with time zone,
    result_status character varying NOT NULL
);


--
-- Name: final_results_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.final_results_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: final_results_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.final_results_id_seq OWNED BY public.final_results.id;


--
-- Name: game_config; Type: TABLE; Schema: public
--

CREATE TABLE public.game_config (
    id integer NOT NULL,
    current_round integer,
    auction_timer_end timestamp with time zone,
    wildcards_visible boolean,
    state character varying,
    phase_started_at timestamp with time zone,
    timer_paused boolean,
    timer_paused_remaining_seconds integer,
    timer_bias_seconds integer,
    last_state_update timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: game_config_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.game_config_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: game_config_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.game_config_id_seq OWNED BY public.game_config.id;


--
-- Name: lab_allocation_state; Type: TABLE; Schema: public
--

CREATE TABLE public.lab_allocation_state (
    id integer NOT NULL,
    status character varying(20) DEFAULT 'NOT_READY'::character varying NOT NULL,
    allocated_at timestamp with time zone,
    finalized_at timestamp with time zone,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_lab_allocation_state_status CHECK (((status)::text = ANY ((ARRAY['NOT_READY'::character varying, 'READY'::character varying, 'ALLOCATING'::character varying, 'ALLOCATED'::character varying, 'FINALIZED'::character varying])::text[])))
);


--
-- Name: lab_allocation_state_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.lab_allocation_state_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: lab_allocation_state_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.lab_allocation_state_id_seq OWNED BY public.lab_allocation_state.id;


--
-- Name: lab_assignments; Type: TABLE; Schema: public
--

CREATE TABLE public.lab_assignments (
    id integer NOT NULL,
    team_id integer NOT NULL,
    original_lab_id integer NOT NULL,
    current_lab_id integer NOT NULL,
    assignment_source character varying(20) DEFAULT 'AUTO'::character varying NOT NULL,
    constraint_override boolean DEFAULT false NOT NULL,
    effective_ps_id integer NOT NULL,
    moved_by_user_id integer,
    moved_at timestamp with time zone,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_lab_assignments_source CHECK (((assignment_source)::text = ANY ((ARRAY['AUTO'::character varying, 'MANUAL_OVERRIDE'::character varying])::text[]))),
    CONSTRAINT ck_lab_assignments_version_positive CHECK ((version > 0))
);


--
-- Name: lab_assignments_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.lab_assignments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: lab_assignments_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.lab_assignments_id_seq OWNED BY public.lab_assignments.id;


--
-- Name: labs; Type: TABLE; Schema: public
--

CREATE TABLE public.labs (
    id integer NOT NULL,
    name character varying(120) NOT NULL,
    capacity integer NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_labs_capacity_positive CHECK ((capacity > 0)),
    CONSTRAINT ck_labs_sort_order_nonnegative CHECK ((sort_order >= 0))
);


--
-- Name: labs_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.labs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: labs_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.labs_id_seq OWNED BY public.labs.id;


--
-- Name: members; Type: TABLE; Schema: public
--

CREATE TABLE public.members (
    id integer NOT NULL,
    team_id integer,
    member_name character varying NOT NULL,
    email character varying
);


--
-- Name: members_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.members_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: members_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.members_id_seq OWNED BY public.members.id;


--
-- Name: problem_statements; Type: TABLE; Schema: public
--

CREATE TABLE public.problem_statements (
    id integer NOT NULL,
    ps_number character varying NOT NULL,
    title character varying NOT NULL,
    description character varying,
    round integer,
    status character varying
);


--
-- Name: problem_statements_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.problem_statements_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: problem_statements_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.problem_statements_id_seq OWNED BY public.problem_statements.id;


--
-- Name: registration_import_rows; Type: TABLE; Schema: public
--

CREATE TABLE public.registration_import_rows (
    id integer NOT NULL,
    import_id integer,
    row_number integer NOT NULL,
    team_name character varying NOT NULL,
    leader_name character varying NOT NULL,
    leader_email character varying NOT NULL,
    members_json text NOT NULL,
    status character varying,
    warnings_json text NOT NULL,
    source_values_json text NOT NULL,
    team_id integer
);


--
-- Name: registration_import_rows_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.registration_import_rows_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: registration_import_rows_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.registration_import_rows_id_seq OWNED BY public.registration_import_rows.id;


--
-- Name: registration_imports; Type: TABLE; Schema: public
--

CREATE TABLE public.registration_imports (
    id integer NOT NULL,
    filename character varying NOT NULL,
    status character varying,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    committed_at timestamp with time zone,
    source_name character varying,
    source_headers_json text NOT NULL
);


--
-- Name: registration_imports_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.registration_imports_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: registration_imports_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.registration_imports_id_seq OWNED BY public.registration_imports.id;


--
-- Name: round_controls; Type: TABLE; Schema: public
--

CREATE TABLE public.round_controls (
    id integer NOT NULL,
    round_type character varying NOT NULL,
    current_problem_id integer,
    status character varying,
    ended boolean,
    applications_open boolean,
    slot_count integer,
    selection_pool_frozen_at timestamp with time zone,
    current_selection_rank integer,
    selection_started_at timestamp with time zone,
    selection_ends_at timestamp with time zone,
    selection_duration_seconds integer,
    final_auto_assignment_problem_id integer,
    final_auto_assignment_price integer,
    final_auto_assignment_team_count integer,
    round1_winning_bid_sum integer NOT NULL,
    round1_winning_bid_count integer NOT NULL,
    final_choice_started_at timestamp with time zone,
    final_choice_ends_at timestamp with time zone,
    final_choice_duration_seconds integer
);


--
-- Name: round_controls_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.round_controls_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: round_controls_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.round_controls_id_seq OWNED BY public.round_controls.id;


--
-- Name: submissions; Type: TABLE; Schema: public
--

CREATE TABLE public.submissions (
    id integer NOT NULL,
    team_id integer,
    problem_id integer,
    submitted_by_user_id integer,
    repository_url character varying NOT NULL,
    submitted_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone
);


--
-- Name: submissions_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.submissions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: submissions_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.submissions_id_seq OWNED BY public.submissions.id;


--
-- Name: teams; Type: TABLE; Schema: public
--

CREATE TABLE public.teams (
    id integer NOT NULL,
    team_name character varying NOT NULL,
    coins integer,
    leader_id integer,
    ps_id integer,
    round1_problem_id integer,
    wildcard_problem_id integer,
    round1_assignment_type character varying,
    round1_assignment_cost integer,
    is_approved boolean,
    is_system_team boolean NOT NULL,
    final_problem_choice character varying,
    final_problem_confirmed_at timestamp with time zone,
    final_problem_defaulted boolean DEFAULT false NOT NULL,
    CONSTRAINT ck_teams_final_problem_choice CHECK (((final_problem_choice IS NULL) OR ((final_problem_choice)::text = ANY ((ARRAY['ROUND1'::character varying, 'WILDCARD'::character varying])::text[]))))
);


--
-- Name: teams_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.teams_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: teams_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.teams_id_seq OWNED BY public.teams.id;


--
-- Name: users; Type: TABLE; Schema: public
--

CREATE TABLE public.users (
    id integer NOT NULL,
    name character varying NOT NULL,
    email character varying NOT NULL,
    password_hash character varying NOT NULL,
    role character varying NOT NULL,
    team_id integer,
    session_id character varying,
    is_system_account boolean NOT NULL,
    account_source character varying NOT NULL,
    credentials_active boolean NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    session_created_at timestamp with time zone,
    session_last_seen_at timestamp with time zone
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: wallet_transactions; Type: TABLE; Schema: public
--

CREATE TABLE public.wallet_transactions (
    id integer NOT NULL,
    team_id integer,
    transaction_type character varying NOT NULL,
    amount integer NOT NULL,
    "timestamp" timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    description character varying
);


--
-- Name: wallet_transactions_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.wallet_transactions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: wallet_transactions_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.wallet_transactions_id_seq OWNED BY public.wallet_transactions.id;


--
-- Name: wildcard_bids; Type: TABLE; Schema: public
--

CREATE TABLE public.wildcard_bids (
    id integer NOT NULL,
    team_id integer NOT NULL,
    amount integer NOT NULL,
    "timestamp" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: wildcard_bids_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.wildcard_bids_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: wildcard_bids_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.wildcard_bids_id_seq OWNED BY public.wildcard_bids.id;


--
-- Name: wildcard_selection_pool; Type: TABLE; Schema: public
--

CREATE TABLE public.wildcard_selection_pool (
    id integer NOT NULL,
    "position" integer NOT NULL,
    problem_id integer NOT NULL,
    selected_by_team_id integer,
    frozen_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    selected_at timestamp with time zone
);


--
-- Name: wildcard_selection_pool_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.wildcard_selection_pool_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: wildcard_selection_pool_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.wildcard_selection_pool_id_seq OWNED BY public.wildcard_selection_pool.id;


--
-- Name: wildcards; Type: TABLE; Schema: public
--

CREATE TABLE public.wildcards (
    id integer NOT NULL,
    team_id integer,
    coins_paid integer NOT NULL,
    used boolean,
    status character varying,
    applied_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    rank integer,
    winning_bid integer,
    problem_id integer,
    selected_at timestamp with time zone,
    selection_method character varying
);


--
-- Name: wildcards_id_seq; Type: SEQUENCE; Schema: public
--

CREATE SEQUENCE public.wildcards_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: wildcards_id_seq; Type: SEQUENCE OWNED BY; Schema: public
--

ALTER SEQUENCE public.wildcards_id_seq OWNED BY public.wildcards.id;


--
-- Name: bids id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.bids ALTER COLUMN id SET DEFAULT nextval('public.bids_id_seq'::regclass);


--
-- Name: event_activity_log id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.event_activity_log ALTER COLUMN id SET DEFAULT nextval('public.event_activity_log_id_seq'::regclass);


--
-- Name: event_config id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.event_config ALTER COLUMN id SET DEFAULT nextval('public.event_config_id_seq'::regclass);


--
-- Name: exchange_requests id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.exchange_requests ALTER COLUMN id SET DEFAULT nextval('public.exchange_requests_id_seq'::regclass);


--
-- Name: final_results id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.final_results ALTER COLUMN id SET DEFAULT nextval('public.final_results_id_seq'::regclass);


--
-- Name: game_config id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.game_config ALTER COLUMN id SET DEFAULT nextval('public.game_config_id_seq'::regclass);


--
-- Name: lab_allocation_state id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.lab_allocation_state ALTER COLUMN id SET DEFAULT nextval('public.lab_allocation_state_id_seq'::regclass);


--
-- Name: lab_assignments id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.lab_assignments ALTER COLUMN id SET DEFAULT nextval('public.lab_assignments_id_seq'::regclass);


--
-- Name: labs id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.labs ALTER COLUMN id SET DEFAULT nextval('public.labs_id_seq'::regclass);


--
-- Name: members id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.members ALTER COLUMN id SET DEFAULT nextval('public.members_id_seq'::regclass);


--
-- Name: problem_statements id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.problem_statements ALTER COLUMN id SET DEFAULT nextval('public.problem_statements_id_seq'::regclass);


--
-- Name: registration_import_rows id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.registration_import_rows ALTER COLUMN id SET DEFAULT nextval('public.registration_import_rows_id_seq'::regclass);


--
-- Name: registration_imports id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.registration_imports ALTER COLUMN id SET DEFAULT nextval('public.registration_imports_id_seq'::regclass);


--
-- Name: round_controls id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.round_controls ALTER COLUMN id SET DEFAULT nextval('public.round_controls_id_seq'::regclass);


--
-- Name: submissions id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.submissions ALTER COLUMN id SET DEFAULT nextval('public.submissions_id_seq'::regclass);


--
-- Name: teams id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.teams ALTER COLUMN id SET DEFAULT nextval('public.teams_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: wallet_transactions id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.wallet_transactions ALTER COLUMN id SET DEFAULT nextval('public.wallet_transactions_id_seq'::regclass);


--
-- Name: wildcard_bids id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.wildcard_bids ALTER COLUMN id SET DEFAULT nextval('public.wildcard_bids_id_seq'::regclass);


--
-- Name: wildcard_selection_pool id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.wildcard_selection_pool ALTER COLUMN id SET DEFAULT nextval('public.wildcard_selection_pool_id_seq'::regclass);


--
-- Name: wildcards id; Type: DEFAULT; Schema: public
--

ALTER TABLE ONLY public.wildcards ALTER COLUMN id SET DEFAULT nextval('public.wildcards_id_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: bids bids_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.bids
    ADD CONSTRAINT bids_pkey PRIMARY KEY (id);


--
-- Name: event_activity_log event_activity_log_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.event_activity_log
    ADD CONSTRAINT event_activity_log_pkey PRIMARY KEY (id);


--
-- Name: event_config event_config_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.event_config
    ADD CONSTRAINT event_config_pkey PRIMARY KEY (id);


--
-- Name: exchange_requests exchange_requests_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.exchange_requests
    ADD CONSTRAINT exchange_requests_pkey PRIMARY KEY (id);


--
-- Name: final_results final_results_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.final_results
    ADD CONSTRAINT final_results_pkey PRIMARY KEY (id);


--
-- Name: game_config game_config_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.game_config
    ADD CONSTRAINT game_config_pkey PRIMARY KEY (id);


--
-- Name: lab_allocation_state lab_allocation_state_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.lab_allocation_state
    ADD CONSTRAINT lab_allocation_state_pkey PRIMARY KEY (id);


--
-- Name: lab_assignments lab_assignments_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.lab_assignments
    ADD CONSTRAINT lab_assignments_pkey PRIMARY KEY (id);


--
-- Name: labs labs_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.labs
    ADD CONSTRAINT labs_pkey PRIMARY KEY (id);


--
-- Name: members members_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.members
    ADD CONSTRAINT members_pkey PRIMARY KEY (id);


--
-- Name: problem_statements problem_statements_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.problem_statements
    ADD CONSTRAINT problem_statements_pkey PRIMARY KEY (id);


--
-- Name: problem_statements problem_statements_ps_number_key; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.problem_statements
    ADD CONSTRAINT problem_statements_ps_number_key UNIQUE (ps_number);


--
-- Name: registration_import_rows registration_import_rows_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.registration_import_rows
    ADD CONSTRAINT registration_import_rows_pkey PRIMARY KEY (id);


--
-- Name: registration_imports registration_imports_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.registration_imports
    ADD CONSTRAINT registration_imports_pkey PRIMARY KEY (id);


--
-- Name: round_controls round_controls_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.round_controls
    ADD CONSTRAINT round_controls_pkey PRIMARY KEY (id);


--
-- Name: round_controls round_controls_round_type_key; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.round_controls
    ADD CONSTRAINT round_controls_round_type_key UNIQUE (round_type);


--
-- Name: submissions submissions_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT submissions_pkey PRIMARY KEY (id);


--
-- Name: submissions submissions_team_id_key; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT submissions_team_id_key UNIQUE (team_id);


--
-- Name: teams teams_leader_id_key; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.teams
    ADD CONSTRAINT teams_leader_id_key UNIQUE (leader_id);


--
-- Name: teams teams_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.teams
    ADD CONSTRAINT teams_pkey PRIMARY KEY (id);


--
-- Name: teams teams_team_name_key; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.teams
    ADD CONSTRAINT teams_team_name_key UNIQUE (team_name);


--
-- Name: bids uq_bid_team_problem_round; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.bids
    ADD CONSTRAINT uq_bid_team_problem_round UNIQUE (team_id, ps_id, round);


--
-- Name: lab_assignments uq_lab_assignments_team; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.lab_assignments
    ADD CONSTRAINT uq_lab_assignments_team UNIQUE (team_id);


--
-- Name: wallet_transactions uq_wallet_operation; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT uq_wallet_operation UNIQUE (team_id, transaction_type, description);


--
-- Name: wildcard_selection_pool uq_wildcard_pool_position; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.wildcard_selection_pool
    ADD CONSTRAINT uq_wildcard_pool_position UNIQUE ("position");


--
-- Name: wildcard_selection_pool uq_wildcard_pool_problem; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.wildcard_selection_pool
    ADD CONSTRAINT uq_wildcard_pool_problem UNIQUE (problem_id);


--
-- Name: wildcard_selection_pool uq_wildcard_pool_selected_team; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.wildcard_selection_pool
    ADD CONSTRAINT uq_wildcard_pool_selected_team UNIQUE (selected_by_team_id);


--
-- Name: wildcards uq_wildcards_rank; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.wildcards
    ADD CONSTRAINT uq_wildcards_rank UNIQUE (rank);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: wallet_transactions wallet_transactions_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT wallet_transactions_pkey PRIMARY KEY (id);


--
-- Name: wildcard_bids wildcard_bids_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.wildcard_bids
    ADD CONSTRAINT wildcard_bids_pkey PRIMARY KEY (id);


--
-- Name: wildcard_bids wildcard_bids_team_id_key; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.wildcard_bids
    ADD CONSTRAINT wildcard_bids_team_id_key UNIQUE (team_id);


--
-- Name: wildcard_selection_pool wildcard_selection_pool_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.wildcard_selection_pool
    ADD CONSTRAINT wildcard_selection_pool_pkey PRIMARY KEY (id);


--
-- Name: wildcards wildcards_pkey; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.wildcards
    ADD CONSTRAINT wildcards_pkey PRIMARY KEY (id);


--
-- Name: wildcards wildcards_problem_id_key; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.wildcards
    ADD CONSTRAINT wildcards_problem_id_key UNIQUE (problem_id);


--
-- Name: wildcards wildcards_team_id_key; Type: CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.wildcards
    ADD CONSTRAINT wildcards_team_id_key UNIQUE (team_id);


--
-- Name: ix_bids_id; Type: INDEX; Schema: public
--

CREATE INDEX ix_bids_id ON public.bids USING btree (id);


--
-- Name: ix_bids_problem_round_rank; Type: INDEX; Schema: public
--

CREATE INDEX ix_bids_problem_round_rank ON public.bids USING btree (ps_id, round, amount DESC, "timestamp", team_id);


--
-- Name: ix_event_activity_log_action; Type: INDEX; Schema: public
--

CREATE INDEX ix_event_activity_log_action ON public.event_activity_log USING btree (action);


--
-- Name: ix_event_activity_log_id; Type: INDEX; Schema: public
--

CREATE INDEX ix_event_activity_log_id ON public.event_activity_log USING btree (id);


--
-- Name: ix_event_activity_log_timestamp; Type: INDEX; Schema: public
--

CREATE INDEX ix_event_activity_log_timestamp ON public.event_activity_log USING btree ("timestamp");


--
-- Name: ix_event_config_id; Type: INDEX; Schema: public
--

CREATE INDEX ix_event_config_id ON public.event_config USING btree (id);


--
-- Name: ix_exchange_requests_id; Type: INDEX; Schema: public
--

CREATE INDEX ix_exchange_requests_id ON public.exchange_requests USING btree (id);


--
-- Name: ix_game_config_id; Type: INDEX; Schema: public
--

CREATE INDEX ix_game_config_id ON public.game_config USING btree (id);


--
-- Name: ix_lab_assignments_current_lab; Type: INDEX; Schema: public
--

CREATE INDEX ix_lab_assignments_current_lab ON public.lab_assignments USING btree (current_lab_id);


--
-- Name: ix_lab_assignments_effective_problem_lab; Type: INDEX; Schema: public
--

CREATE INDEX ix_lab_assignments_effective_problem_lab ON public.lab_assignments USING btree (effective_ps_id, current_lab_id);


--
-- Name: ix_members_id; Type: INDEX; Schema: public
--

CREATE INDEX ix_members_id ON public.members USING btree (id);


--
-- Name: ix_members_team_id; Type: INDEX; Schema: public
--

CREATE INDEX ix_members_team_id ON public.members USING btree (team_id);


--
-- Name: ix_problem_statements_id; Type: INDEX; Schema: public
--

CREATE INDEX ix_problem_statements_id ON public.problem_statements USING btree (id);


--
-- Name: ix_problem_statements_ps_number; Type: INDEX; Schema: public
--

CREATE UNIQUE INDEX ix_problem_statements_ps_number ON public.problem_statements USING btree (ps_number);


--
-- Name: ix_registration_import_rows_id; Type: INDEX; Schema: public
--

CREATE INDEX ix_registration_import_rows_id ON public.registration_import_rows USING btree (id);


--
-- Name: ix_registration_imports_id; Type: INDEX; Schema: public
--

CREATE INDEX ix_registration_imports_id ON public.registration_imports USING btree (id);


--
-- Name: ix_round_controls_id; Type: INDEX; Schema: public
--

CREATE INDEX ix_round_controls_id ON public.round_controls USING btree (id);


--
-- Name: ix_round_controls_round_type; Type: INDEX; Schema: public
--

CREATE UNIQUE INDEX ix_round_controls_round_type ON public.round_controls USING btree (round_type);


--
-- Name: ix_submissions_id; Type: INDEX; Schema: public
--

CREATE INDEX ix_submissions_id ON public.submissions USING btree (id);


--
-- Name: ix_teams_id; Type: INDEX; Schema: public
--

CREATE INDEX ix_teams_id ON public.teams USING btree (id);


--
-- Name: ix_teams_team_name; Type: INDEX; Schema: public
--

CREATE UNIQUE INDEX ix_teams_team_name ON public.teams USING btree (team_name);


--
-- Name: ix_users_email; Type: INDEX; Schema: public
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: ix_users_id; Type: INDEX; Schema: public
--

CREATE INDEX ix_users_id ON public.users USING btree (id);


--
-- Name: ix_wallet_transactions_id; Type: INDEX; Schema: public
--

CREATE INDEX ix_wallet_transactions_id ON public.wallet_transactions USING btree (id);


--
-- Name: ix_wildcard_bids_id; Type: INDEX; Schema: public
--

CREATE INDEX ix_wildcard_bids_id ON public.wildcard_bids USING btree (id);


--
-- Name: ix_wildcard_bids_rank; Type: INDEX; Schema: public
--

CREATE INDEX ix_wildcard_bids_rank ON public.wildcard_bids USING btree (amount DESC, "timestamp", team_id);


--
-- Name: ix_wildcard_selection_pool_id; Type: INDEX; Schema: public
--

CREATE INDEX ix_wildcard_selection_pool_id ON public.wildcard_selection_pool USING btree (id);


--
-- Name: ix_wildcards_id; Type: INDEX; Schema: public
--

CREATE INDEX ix_wildcards_id ON public.wildcards USING btree (id);


--
-- Name: uq_labs_name_ci; Type: INDEX; Schema: public
--

CREATE UNIQUE INDEX uq_labs_name_ci ON public.labs USING btree (lower((name)::text));


--
-- Name: uq_users_single_lab_admin; Type: INDEX; Schema: public
--

CREATE UNIQUE INDEX uq_users_single_lab_admin ON public.users USING btree (role) WHERE ((role)::text = 'lab_admin'::text);


--
-- Name: bids bids_ps_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.bids
    ADD CONSTRAINT bids_ps_id_fkey FOREIGN KEY (ps_id) REFERENCES public.problem_statements(id) ON DELETE CASCADE;


--
-- Name: bids bids_team_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.bids
    ADD CONSTRAINT bids_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE CASCADE;


--
-- Name: exchange_requests exchange_requests_receiver_ps_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.exchange_requests
    ADD CONSTRAINT exchange_requests_receiver_ps_id_fkey FOREIGN KEY (receiver_ps_id) REFERENCES public.problem_statements(id) ON DELETE CASCADE;


--
-- Name: exchange_requests exchange_requests_receiver_team_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.exchange_requests
    ADD CONSTRAINT exchange_requests_receiver_team_id_fkey FOREIGN KEY (receiver_team_id) REFERENCES public.teams(id) ON DELETE CASCADE;


--
-- Name: exchange_requests exchange_requests_requester_ps_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.exchange_requests
    ADD CONSTRAINT exchange_requests_requester_ps_id_fkey FOREIGN KEY (requester_ps_id) REFERENCES public.problem_statements(id) ON DELETE CASCADE;


--
-- Name: exchange_requests exchange_requests_requester_team_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.exchange_requests
    ADD CONSTRAINT exchange_requests_requester_team_id_fkey FOREIGN KEY (requester_team_id) REFERENCES public.teams(id) ON DELETE CASCADE;


--
-- Name: final_results final_results_first_place_team_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.final_results
    ADD CONSTRAINT final_results_first_place_team_id_fkey FOREIGN KEY (first_place_team_id) REFERENCES public.teams(id) ON DELETE SET NULL;


--
-- Name: final_results final_results_second_place_team_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.final_results
    ADD CONSTRAINT final_results_second_place_team_id_fkey FOREIGN KEY (second_place_team_id) REFERENCES public.teams(id) ON DELETE SET NULL;


--
-- Name: final_results final_results_third_place_team_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.final_results
    ADD CONSTRAINT final_results_third_place_team_id_fkey FOREIGN KEY (third_place_team_id) REFERENCES public.teams(id) ON DELETE SET NULL;


--
-- Name: users fk_users_team_id_teams; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT fk_users_team_id_teams FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE SET NULL;


--
-- Name: lab_assignments lab_assignments_current_lab_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.lab_assignments
    ADD CONSTRAINT lab_assignments_current_lab_id_fkey FOREIGN KEY (current_lab_id) REFERENCES public.labs(id) ON DELETE RESTRICT;


--
-- Name: lab_assignments lab_assignments_effective_ps_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.lab_assignments
    ADD CONSTRAINT lab_assignments_effective_ps_id_fkey FOREIGN KEY (effective_ps_id) REFERENCES public.problem_statements(id) ON DELETE RESTRICT;


--
-- Name: lab_assignments lab_assignments_moved_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.lab_assignments
    ADD CONSTRAINT lab_assignments_moved_by_user_id_fkey FOREIGN KEY (moved_by_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: lab_assignments lab_assignments_original_lab_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.lab_assignments
    ADD CONSTRAINT lab_assignments_original_lab_id_fkey FOREIGN KEY (original_lab_id) REFERENCES public.labs(id) ON DELETE RESTRICT;


--
-- Name: lab_assignments lab_assignments_team_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.lab_assignments
    ADD CONSTRAINT lab_assignments_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE CASCADE;


--
-- Name: members members_team_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.members
    ADD CONSTRAINT members_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE CASCADE;


--
-- Name: registration_import_rows registration_import_rows_import_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.registration_import_rows
    ADD CONSTRAINT registration_import_rows_import_id_fkey FOREIGN KEY (import_id) REFERENCES public.registration_imports(id) ON DELETE CASCADE;


--
-- Name: registration_import_rows registration_import_rows_team_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.registration_import_rows
    ADD CONSTRAINT registration_import_rows_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE SET NULL;


--
-- Name: round_controls round_controls_current_problem_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.round_controls
    ADD CONSTRAINT round_controls_current_problem_id_fkey FOREIGN KEY (current_problem_id) REFERENCES public.problem_statements(id) ON DELETE SET NULL;


--
-- Name: round_controls round_controls_final_auto_assignment_problem_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.round_controls
    ADD CONSTRAINT round_controls_final_auto_assignment_problem_id_fkey FOREIGN KEY (final_auto_assignment_problem_id) REFERENCES public.problem_statements(id) ON DELETE SET NULL;


--
-- Name: submissions submissions_problem_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT submissions_problem_id_fkey FOREIGN KEY (problem_id) REFERENCES public.problem_statements(id) ON DELETE SET NULL;


--
-- Name: submissions submissions_submitted_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT submissions_submitted_by_user_id_fkey FOREIGN KEY (submitted_by_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: submissions submissions_team_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.submissions
    ADD CONSTRAINT submissions_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE CASCADE;


--
-- Name: teams teams_leader_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.teams
    ADD CONSTRAINT teams_leader_id_fkey FOREIGN KEY (leader_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: teams teams_ps_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.teams
    ADD CONSTRAINT teams_ps_id_fkey FOREIGN KEY (ps_id) REFERENCES public.problem_statements(id) ON DELETE SET NULL;


--
-- Name: teams teams_round1_problem_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.teams
    ADD CONSTRAINT teams_round1_problem_id_fkey FOREIGN KEY (round1_problem_id) REFERENCES public.problem_statements(id) ON DELETE SET NULL;


--
-- Name: teams teams_wildcard_problem_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.teams
    ADD CONSTRAINT teams_wildcard_problem_id_fkey FOREIGN KEY (wildcard_problem_id) REFERENCES public.problem_statements(id) ON DELETE SET NULL;


--
-- Name: wallet_transactions wallet_transactions_team_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT wallet_transactions_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE CASCADE;


--
-- Name: wildcard_bids wildcard_bids_team_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.wildcard_bids
    ADD CONSTRAINT wildcard_bids_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE CASCADE;


--
-- Name: wildcard_selection_pool wildcard_selection_pool_problem_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.wildcard_selection_pool
    ADD CONSTRAINT wildcard_selection_pool_problem_id_fkey FOREIGN KEY (problem_id) REFERENCES public.problem_statements(id) ON DELETE RESTRICT;


--
-- Name: wildcard_selection_pool wildcard_selection_pool_selected_by_team_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.wildcard_selection_pool
    ADD CONSTRAINT wildcard_selection_pool_selected_by_team_id_fkey FOREIGN KEY (selected_by_team_id) REFERENCES public.teams(id) ON DELETE SET NULL;


--
-- Name: wildcards wildcards_problem_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.wildcards
    ADD CONSTRAINT wildcards_problem_id_fkey FOREIGN KEY (problem_id) REFERENCES public.problem_statements(id) ON DELETE SET NULL;


--
-- Name: wildcards wildcards_team_id_fkey; Type: FK CONSTRAINT; Schema: public
--

ALTER TABLE ONLY public.wildcards
    ADD CONSTRAINT wildcards_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE CASCADE;
