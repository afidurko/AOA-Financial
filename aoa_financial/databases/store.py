"""SQLite-backed market store.

A single :class:`MarketStore` owns one SQLite database holding every table in
``schema.sql``. It exposes small, explicit methods rather than an ORM so the
data flow stays obvious and dependency-free.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


@dataclass(frozen=True)
class Security:
    ticker: str
    name: str
    sector: str
    listed_on: str
    source: str
    meta: dict


@dataclass(frozen=True)
class Bar:
    """A single daily OHLCV observation."""

    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class MarketStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    # -- lifecycle --------------------------------------------------------
    def _init_schema(self) -> None:
        self._conn.executescript(_SCHEMA_PATH.read_text())
        self._conn.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "MarketStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- securities -------------------------------------------------------
    def upsert_security(self, sec: Security) -> None:
        with self.transaction() as c:
            c.execute(
                """INSERT INTO securities(ticker,name,sector,listed_on,source,meta)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(ticker) DO UPDATE SET
                     name=excluded.name, sector=excluded.sector,
                     listed_on=excluded.listed_on, source=excluded.source,
                     meta=excluded.meta""",
                (sec.ticker, sec.name, sec.sector, sec.listed_on,
                 sec.source, json.dumps(sec.meta)),
            )

    def get_security(self, ticker: str) -> Optional[Security]:
        row = self._conn.execute(
            "SELECT * FROM securities WHERE ticker=?", (ticker,)
        ).fetchone()
        if row is None:
            return None
        return Security(
            ticker=row["ticker"], name=row["name"], sector=row["sector"],
            listed_on=row["listed_on"], source=row["source"],
            meta=json.loads(row["meta"] or "{}"),
        )

    def list_securities(self) -> List[str]:
        return [r["ticker"] for r in
                self._conn.execute("SELECT ticker FROM securities ORDER BY ticker")]

    def has_prices(self, ticker: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM prices WHERE ticker=? LIMIT 1", (ticker,)
        ).fetchone()
        return row is not None

    # -- prices -----------------------------------------------------------
    def insert_bars(self, ticker: str, bars: Iterable[Bar]) -> int:
        rows = [(ticker, b.date, b.open, b.high, b.low, b.close, b.volume)
                for b in bars]
        with self.transaction() as c:
            c.executemany(
                """INSERT INTO prices(ticker,date,open,high,low,close,volume)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(ticker,date) DO UPDATE SET
                     open=excluded.open, high=excluded.high, low=excluded.low,
                     close=excluded.close, volume=excluded.volume""",
                rows,
            )
        return len(rows)

    def get_bars(
        self,
        ticker: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Bar]:
        q = "SELECT date,open,high,low,close,volume FROM prices WHERE ticker=?"
        args: List[object] = [ticker]
        if start:
            q += " AND date>=?"; args.append(start)
        if end:
            q += " AND date<=?"; args.append(end)
        q += " ORDER BY date ASC"
        rows = self._conn.execute(q, args).fetchall()
        bars = [Bar(r["date"], r["open"], r["high"], r["low"],
                    r["close"], r["volume"]) for r in rows]
        if limit is not None and len(bars) > limit:
            bars = bars[-limit:]
        return bars

    def closes(self, ticker: str, limit: Optional[int] = None) -> List[float]:
        return [b.close for b in self.get_bars(ticker, limit=limit)]

    # -- fundamentals -----------------------------------------------------
    def upsert_fundamentals(self, ticker: str, asof: str, data: Dict[str, float]) -> None:
        cols = ["pe_ratio", "pb_ratio", "dividend_yield", "revenue_growth",
                "profit_margin", "debt_to_equity", "roe", "free_cash_flow"]
        vals = [data.get(c) for c in cols]
        with self.transaction() as c:
            c.execute(
                f"""INSERT INTO fundamentals(ticker,date,{','.join(cols)})
                    VALUES(?,?,{','.join('?' * len(cols))})
                    ON CONFLICT(ticker,date) DO UPDATE SET
                    {','.join(f'{col}=excluded.{col}' for col in cols)}""",
                [ticker, asof, *vals],
            )

    def latest_fundamentals(self, ticker: str) -> Optional[Dict[str, float]]:
        row = self._conn.execute(
            "SELECT * FROM fundamentals WHERE ticker=? ORDER BY date DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d.pop("ticker", None)
        return d

    # -- sentiment --------------------------------------------------------
    def upsert_sentiment(self, ticker: str, asof: str, score: float,
                         volume: int = 0, source: str = "aggregate") -> None:
        with self.transaction() as c:
            c.execute(
                """INSERT INTO sentiment(ticker,date,score,volume,source)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(ticker,date,source) DO UPDATE SET
                     score=excluded.score, volume=excluded.volume""",
                (ticker, asof, score, volume, source),
            )

    def latest_sentiment(self, ticker: str) -> Optional[float]:
        row = self._conn.execute(
            "SELECT score FROM sentiment WHERE ticker=? ORDER BY date DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        return None if row is None else row["score"]

    # -- regimes ----------------------------------------------------------
    def upsert_regime(self, ticker: str, asof: str, regime: str,
                      confidence: float, vol: float, trend: float) -> None:
        with self.transaction() as c:
            c.execute(
                """INSERT INTO regimes(ticker,date,regime,confidence,
                       annualized_vol,trend_strength)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(ticker,date) DO UPDATE SET
                     regime=excluded.regime, confidence=excluded.confidence,
                     annualized_vol=excluded.annualized_vol,
                     trend_strength=excluded.trend_strength""",
                (ticker, asof, regime, confidence, vol, trend),
            )

    # -- signals & decisions ---------------------------------------------
    def insert_signals(self, run_id: str, signals: Sequence[dict]) -> None:
        with self.transaction() as c:
            c.executemany(
                """INSERT INTO signals(run_id,ticker,asof,agent,action,
                       score,confidence,rationale)
                   VALUES(:run_id,:ticker,:asof,:agent,:action,
                          :score,:confidence,:rationale)
                   ON CONFLICT(run_id,ticker,agent) DO UPDATE SET
                     action=excluded.action, score=excluded.score,
                     confidence=excluded.confidence, rationale=excluded.rationale""",
                signals,
            )

    def insert_decision(self, run_id: str, decision: dict) -> None:
        with self.transaction() as c:
            c.execute(
                """INSERT INTO decisions(run_id,ticker,asof,action,conviction,
                       confidence,target_weight,rationale,payload)
                   VALUES(:run_id,:ticker,:asof,:action,:conviction,
                          :confidence,:target_weight,:rationale,:payload)
                   ON CONFLICT(run_id,ticker) DO UPDATE SET
                     action=excluded.action, conviction=excluded.conviction,
                     confidence=excluded.confidence,
                     target_weight=excluded.target_weight,
                     rationale=excluded.rationale, payload=excluded.payload""",
                decision,
            )

    def get_decisions(self, run_id: str) -> List[dict]:
        rows = self._conn.execute(
            "SELECT * FROM decisions WHERE run_id=? ORDER BY conviction DESC",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]
