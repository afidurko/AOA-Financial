-- Live swarm analytics (SQLite) — unified cycle history, ROI attribution, approvals.
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cycle_runs (
    run_id          TEXT PRIMARY KEY,
    started_at      TEXT NOT NULL,
    completed_at    TEXT NOT NULL,
    mode            TEXT NOT NULL,
    halted          INTEGER NOT NULL DEFAULT 0,
    halt_reason     TEXT,
    cycles_total    INTEGER NOT NULL DEFAULT 0,
    payload         TEXT
);

CREATE TABLE IF NOT EXISTS cycle_signals (
    run_id      TEXT NOT NULL,
    ticker      TEXT NOT NULL,
    agent       TEXT NOT NULL,
    direction   TEXT,
    conviction  REAL,
    summary     TEXT,
    metrics     TEXT,
    PRIMARY KEY (run_id, ticker, agent)
);

CREATE TABLE IF NOT EXISTS cycle_proposals (
    run_id          TEXT NOT NULL,
    ticker          TEXT NOT NULL,
    side            TEXT,
    qty             REAL,
    approved        INTEGER NOT NULL DEFAULT 0,
    strategy        TEXT,
    est_notional    REAL,
    rationale       TEXT,
    payload         TEXT,
    PRIMARY KEY (run_id, ticker, side)
);

CREATE TABLE IF NOT EXISTS stage_metrics (
    run_id          TEXT NOT NULL,
    stage           TEXT NOT NULL,
    duration_ms     REAL NOT NULL,
    skipped         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, stage)
);

CREATE TABLE IF NOT EXISTS notification_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT,
    kind            TEXT NOT NULL,
    title           TEXT NOT NULL,
    message         TEXT NOT NULL,
    payload         TEXT,
    pushed          INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approval_inbox (
    id              TEXT PRIMARY KEY,
    kind            TEXT NOT NULL,
    title           TEXT NOT NULL,
    summary         TEXT NOT NULL,
    payload         TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      TEXT NOT NULL,
    resolved_at     TEXT
);

CREATE TABLE IF NOT EXISTS research_proposals (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    abstract        TEXT,
    source          TEXT,
    source_url      TEXT,
    technique       TEXT,
    backtest_score  REAL,
    status          TEXT NOT NULL DEFAULT 'pending',
    payload         TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cycle_runs_started ON cycle_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_approval_status ON approval_inbox(status);
CREATE INDEX IF NOT EXISTS idx_research_status ON research_proposals(status);
