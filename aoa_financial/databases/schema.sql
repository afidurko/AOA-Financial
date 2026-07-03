-- AOA-Financial relational schema (SQLite).
-- Normalised stores for the full pipeline: reference data, raw market history,
-- fundamentals, sentiment, and the engine's own derived outputs (inferred
-- regimes, per-agent signals, and final swarm decisions).

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Reference data: one row per security ---------------------------------------
CREATE TABLE IF NOT EXISTS securities (
    ticker      TEXT PRIMARY KEY,
    name        TEXT,
    sector      TEXT,
    listed_on   TEXT,            -- ISO date the synthetic/real history begins
    source      TEXT,            -- 'synthetic' | 'stooq' | ...
    meta        TEXT             -- JSON blob for arbitrary extra attributes
);

-- Daily OHLCV history --------------------------------------------------------
CREATE TABLE IF NOT EXISTS prices (
    ticker  TEXT NOT NULL REFERENCES securities(ticker) ON DELETE CASCADE,
    date    TEXT NOT NULL,       -- ISO date
    open    REAL NOT NULL,
    high    REAL NOT NULL,
    low     REAL NOT NULL,
    close   REAL NOT NULL,
    volume  INTEGER NOT NULL,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_prices_ticker_date ON prices(ticker, date);

-- Point-in-time fundamentals -------------------------------------------------
CREATE TABLE IF NOT EXISTS fundamentals (
    ticker          TEXT NOT NULL REFERENCES securities(ticker) ON DELETE CASCADE,
    date            TEXT NOT NULL,
    pe_ratio        REAL,
    pb_ratio        REAL,
    dividend_yield  REAL,
    revenue_growth  REAL,
    profit_margin   REAL,
    debt_to_equity  REAL,
    roe             REAL,
    free_cash_flow  REAL,
    PRIMARY KEY (ticker, date)
);

-- Sentiment time series (news / social / aggregate) --------------------------
CREATE TABLE IF NOT EXISTS sentiment (
    ticker      TEXT NOT NULL REFERENCES securities(ticker) ON DELETE CASCADE,
    date        TEXT NOT NULL,
    score       REAL NOT NULL,   -- [-1, 1]
    volume      INTEGER,         -- count of underlying mentions
    source      TEXT,
    PRIMARY KEY (ticker, date, source)
);

-- Inferred market regimes (output of analysis/regimes.py) --------------------
CREATE TABLE IF NOT EXISTS regimes (
    ticker      TEXT NOT NULL REFERENCES securities(ticker) ON DELETE CASCADE,
    date        TEXT NOT NULL,
    regime      TEXT NOT NULL,   -- bull | bear | correction | recovery | sideways
    confidence  REAL NOT NULL,
    annualized_vol  REAL,
    trend_strength  REAL,
    PRIMARY KEY (ticker, date)
);

-- Per-agent signals (output of swarm specialist agents) ----------------------
CREATE TABLE IF NOT EXISTS signals (
    run_id      TEXT NOT NULL,
    ticker      TEXT NOT NULL,
    asof        TEXT NOT NULL,
    agent       TEXT NOT NULL,
    action      TEXT NOT NULL,   -- BUY | HOLD | SELL
    score       REAL NOT NULL,   -- [-1, 1] directional conviction
    confidence  REAL NOT NULL,   -- [0, 1]
    rationale   TEXT,
    PRIMARY KEY (run_id, ticker, agent)
);

-- Final aggregated swarm decisions -------------------------------------------
CREATE TABLE IF NOT EXISTS decisions (
    run_id          TEXT NOT NULL,
    ticker          TEXT NOT NULL,
    asof            TEXT NOT NULL,
    action          TEXT NOT NULL,
    conviction      REAL NOT NULL,   -- [-1, 1]
    confidence      REAL NOT NULL,   -- [0, 1]
    target_weight   REAL NOT NULL,   -- suggested portfolio weight [0, 1]
    rationale       TEXT,
    payload         TEXT,            -- full JSON of contributing evidence
    PRIMARY KEY (run_id, ticker)
);
