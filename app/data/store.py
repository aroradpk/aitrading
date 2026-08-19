from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

from app.data.types import Bar

SCHEMA = """
CREATE TABLE IF NOT EXISTS instruments (
    symbol TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    yahoo_ticker TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_bars (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    PRIMARY KEY (symbol, date)
);

CREATE TABLE IF NOT EXISTS features (
    symbol TEXT NOT NULL,
    asof_date TEXT NOT NULL,
    name TEXT NOT NULL,
    value REAL,
    PRIMARY KEY (symbol, asof_date, name)
);

CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asof_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    strategy TEXT NOT NULL,
    side TEXT NOT NULL,
    entry_price REAL NOT NULL,
    stop_price REAL NOT NULL,
    target_price REAL NOT NULL,
    reward_risk REAL NOT NULL,
    supporting_json TEXT NOT NULL,
    risk_json TEXT NOT NULL,
            invalidation TEXT NOT NULL,
            entry_condition TEXT NOT NULL DEFAULT 'Enter at next session open.',
    UNIQUE (asof_date, symbol, strategy)
);

CREATE TABLE IF NOT EXISTS labels (
    candidate_id INTEGER PRIMARY KEY,
    asof_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    target_hit_before_stop INTEGER NOT NULL,
    exit_reason TEXT NOT NULL,
    pnl_pct REAL NOT NULL,
    mfe_pct REAL NOT NULL,
    mae_pct REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS model_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    model_type TEXT NOT NULL,
    train_end TEXT NOT NULL,
    valid_end TEXT NOT NULL,
    test_end TEXT,
    metrics_json TEXT NOT NULL,
    feature_names_json TEXT NOT NULL,
    artifact_path TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS predictions (
    candidate_id INTEGER NOT NULL,
    model_run_id INTEGER NOT NULL,
    probability REAL NOT NULL,
    PRIMARY KEY (candidate_id, model_run_id)
);

CREATE TABLE IF NOT EXISTS backtest_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fold TEXT NOT NULL,
    asof_date TEXT NOT NULL,
    fill_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    strategy TEXT NOT NULL,
    side TEXT NOT NULL,
    entry REAL NOT NULL,
    exit REAL NOT NULL,
    qty REAL NOT NULL,
    pnl REAL NOT NULL,
    pnl_pct REAL NOT NULL,
    costs REAL NOT NULL,
    exit_reason TEXT NOT NULL,
    regime TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS news_items (
    symbol TEXT NOT NULL,
    asof_date TEXT NOT NULL,
    headline TEXT NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (symbol, asof_date, headline)
);
"""


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        try:
            self.conn.execute(
                "ALTER TABLE candidates ADD COLUMN entry_condition TEXT NOT NULL DEFAULT 'Enter at next session open.'"
            )
        except sqlite3.OperationalError:
            pass
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def upsert_instrument(self, symbol: str, name: str, kind: str, yahoo_ticker: str) -> None:
        self.conn.execute(
            """
            INSERT INTO instruments(symbol, name, kind, yahoo_ticker)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                name=excluded.name, kind=excluded.kind, yahoo_ticker=excluded.yahoo_ticker
            """,
            (symbol, name, kind, yahoo_ticker),
        )
        self.conn.commit()

    def replace_daily_bars(self, symbol: str, frame: pd.DataFrame) -> None:
        if frame.empty:
            return
        payload = frame.copy()
        payload["symbol"] = symbol
        payload["date"] = pd.to_datetime(payload["date"]).dt.strftime("%Y-%m-%d")
        self.conn.execute("DELETE FROM daily_bars WHERE symbol = ?", (symbol,))
        payload[["symbol", "date", "open", "high", "low", "close", "volume"]].to_sql(
            "daily_bars", self.conn, if_exists="append", index=False
        )
        self.conn.commit()

    def load_daily(self, symbol: str | None = None) -> pd.DataFrame:
        if symbol is None:
            query = "SELECT * FROM daily_bars ORDER BY symbol, date"
            frame = pd.read_sql_query(query, self.conn)
        else:
            query = "SELECT * FROM daily_bars WHERE symbol = ? ORDER BY date"
            frame = pd.read_sql_query(query, self.conn, params=(symbol,))
        if frame.empty:
            return frame
        frame["date"] = pd.to_datetime(frame["date"]).dt.date
        return frame

    def available_dates(self) -> list[date]:
        rows = self.conn.execute("SELECT DISTINCT date FROM daily_bars ORDER BY date").fetchall()
        return [date.fromisoformat(row[0]) for row in rows]

    def replace_features(self, frame: pd.DataFrame) -> None:
        if frame.empty:
            return
        payload = frame.copy()
        payload["asof_date"] = pd.to_datetime(payload["asof_date"]).dt.strftime("%Y-%m-%d")
        dates = sorted(payload["asof_date"].unique())
        self.conn.executemany(
            "DELETE FROM features WHERE asof_date = ?",
            [(d,) for d in dates],
        )
        payload.to_sql("features", self.conn, if_exists="append", index=False)
        self.conn.commit()

    def load_features(self) -> pd.DataFrame:
        frame = pd.read_sql_query("SELECT * FROM features", self.conn)
        if frame.empty:
            return frame
        frame["asof_date"] = pd.to_datetime(frame["asof_date"]).dt.date
        return frame

    def replace_candidates(self, rows: list[dict]) -> None:
        if not rows:
            return
        dates = sorted({row["asof_date"] for row in rows})
        self.conn.executemany(
            "DELETE FROM candidates WHERE asof_date = ?",
            [(d,) for d in dates],
        )
        self.conn.executemany(
            """
            INSERT INTO candidates(
                asof_date, symbol, strategy, side, entry_price, stop_price,
                target_price, reward_risk, supporting_json, risk_json, invalidation, entry_condition
            ) VALUES (:asof_date, :symbol, :strategy, :side, :entry_price, :stop_price,
                      :target_price, :reward_risk, :supporting_json, :risk_json, :invalidation, :entry_condition)
            """,
            rows,
        )
        self.conn.commit()

    def load_candidates(self) -> pd.DataFrame:
        frame = pd.read_sql_query("SELECT * FROM candidates ORDER BY asof_date, symbol", self.conn)
        if frame.empty:
            return frame
        frame["asof_date"] = pd.to_datetime(frame["asof_date"]).dt.date
        return frame

    def replace_labels(self, frame: pd.DataFrame) -> None:
        if frame.empty:
            return
        payload = frame.copy()
        payload["asof_date"] = pd.to_datetime(payload["asof_date"]).dt.strftime("%Y-%m-%d")
        self.conn.execute("DELETE FROM labels")
        payload.to_sql("labels", self.conn, if_exists="append", index=False)
        self.conn.commit()

    def load_labels(self) -> pd.DataFrame:
        frame = pd.read_sql_query("SELECT * FROM labels", self.conn)
        if frame.empty:
            return frame
        frame["asof_date"] = pd.to_datetime(frame["asof_date"]).dt.date
        return frame

    def insert_model_run(
        self,
        created_at: str,
        model_type: str,
        train_end: str,
        valid_end: str,
        test_end: str | None,
        metrics_json: str,
        feature_names_json: str,
        artifact_path: str,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO model_runs(
                created_at, model_type, train_end, valid_end, test_end,
                metrics_json, feature_names_json, artifact_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                model_type,
                train_end,
                valid_end,
                test_end,
                metrics_json,
                feature_names_json,
                artifact_path,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def latest_model_run(self) -> dict | None:
        row = self.conn.execute("SELECT * FROM model_runs ORDER BY id DESC LIMIT 1").fetchone()
        if row is None:
            return None
        return dict(row)

    def replace_predictions(self, model_run_id: int, rows: list[tuple[int, float]]) -> None:
        self.conn.execute("DELETE FROM predictions WHERE model_run_id = ?", (model_run_id,))
        self.conn.executemany(
            "INSERT INTO predictions(candidate_id, model_run_id, probability) VALUES (?, ?, ?)",
            [(cid, model_run_id, prob) for cid, prob in rows],
        )
        self.conn.commit()

    def replace_backtest_trades(self, frame: pd.DataFrame) -> None:
        self.conn.execute("DELETE FROM backtest_trades")
        if not frame.empty:
            payload = frame.copy()
            payload["asof_date"] = pd.to_datetime(payload["asof_date"]).dt.strftime("%Y-%m-%d")
            payload["fill_date"] = pd.to_datetime(payload["fill_date"]).dt.strftime("%Y-%m-%d")
            payload.to_sql("backtest_trades", self.conn, if_exists="append", index=False)
        self.conn.commit()

    def load_backtest_trades(self) -> pd.DataFrame:
        frame = pd.read_sql_query("SELECT * FROM backtest_trades ORDER BY fill_date", self.conn)
        if frame.empty:
            return frame
        frame["asof_date"] = pd.to_datetime(frame["asof_date"]).dt.date
        frame["fill_date"] = pd.to_datetime(frame["fill_date"]).dt.date
        return frame

    def insert_bars(self, bars: list[Bar]) -> None:
        if not bars:
            return
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO daily_bars(symbol, date, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    bar.symbol,
                    bar.date.isoformat(),
                    bar.open,
                    bar.high,
                    bar.low,
                    bar.close,
                    bar.volume,
                )
                for bar in bars
            ],
        )
        self.conn.commit()
