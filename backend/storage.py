"""Small, durable local store. All user-owned records reserve an owner_id."""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def connect():
    path = Path(os.getenv("MONITOR_DB", "data/monitor.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def initialize():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS watchlist (
            symbol TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL,
            owner_id INTEGER NOT NULL DEFAULT 1, added_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS rules (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, expression TEXT NOT NULL,
            symbols TEXT NOT NULL DEFAULT '[]', enabled INTEGER NOT NULL DEFAULT 1,
            owner_id INTEGER NOT NULL DEFAULT 1, version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS rule_state (
            rule_id INTEGER NOT NULL REFERENCES rules(id) ON DELETE CASCADE,
            symbol TEXT NOT NULL, source TEXT NOT NULL, matched INTEGER NOT NULL,
            bar_time TEXT, PRIMARY KEY(rule_id,symbol,source));
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY, rule_id INTEGER, rule_name TEXT NOT NULL,
            symbol TEXT NOT NULL, name TEXT NOT NULL, source TEXT NOT NULL,
            bar_time TEXT NOT NULL, expression TEXT NOT NULL, evidence TEXT NOT NULL,
            read INTEGER NOT NULL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            owner_id INTEGER NOT NULL DEFAULT 1,
            event_key TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS outbox (
            id INTEGER PRIMARY KEY, alert_id INTEGER UNIQUE REFERENCES alerts(id),
            status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
            retry_at REAL NOT NULL DEFAULT 0, error TEXT);
        CREATE TABLE IF NOT EXISTS market_cache (
            symbol TEXT NOT NULL, source TEXT NOT NULL, payload TEXT NOT NULL,
            updated_at TEXT NOT NULL, PRIMARY KEY(symbol,source));
        ''')
        if not all(os.getenv(key) for key in ['SMTP_HOST','SMTP_FROM','ALERT_EMAIL']):
            db.execute("UPDATE outbox SET status='disabled' WHERE status='pending'")
        if not db.execute("SELECT 1 FROM settings WHERE key='initialized'").fetchone():
            db.executemany("INSERT INTO watchlist(symbol,name,kind) VALUES(?,?,?)", [
                ('510300.SH', '沪深300ETF', 'ETF'), ('159915.SZ', '创业板ETF', 'ETF'),
                ('588000.SH', '科创50ETF', 'ETF'), ('600519.SH', '贵州茅台', '股票'),
                ('300750.SZ', '宁德时代', '股票'), ('601318.SH', '中国平安', '股票')])
            db.executemany("INSERT INTO rules(name,expression,enabled) VALUES(?,?,?)", [
                ('趋势观察 · 日线多头', 'CLOSE(tf="1d") > MA(20, tf="1d") and RSI(14, tf="1d") > 50', 1),
                ('超卖观察 · 15分钟', 'RSI(14, tf="15m") < 30', 1),
                ('多周期共振 · MACD', 'CROSSUP(MACD(tf="5m", line="dif"), MACD(tf="5m", line="dea")) and CLOSE(tf="1d") > MA(20, tf="1d")', 0)])
            for key, val in {'initialized': True, 'source': 'demo', 'interval': 60}.items():
                db.execute("INSERT INTO settings VALUES(?,?)", (key, json.dumps(val)))


def settings():
    with connect() as db:
        return {r['key']: json.loads(r['value']) for r in db.execute("SELECT * FROM settings")}


def rows(sql, args=()):
    with connect() as db:
        return [dict(row) for row in db.execute(sql, args)]


def rules():
    result = rows("SELECT * FROM rules ORDER BY id DESC")
    for r in result:
        r['symbols'] = json.loads(r['symbols'])
        r['enabled'] = bool(r['enabled'])
    return result
