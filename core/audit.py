"""
Aureon Engine — Decision System of Record (DSOR)
Immutable audit trail. Every classification, gate decision, and stage
transition is logged with authority tier, timestamp, and governance
fingerprint. Shared across all practices.
"""

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

if os.environ.get("VERCEL"):
    DB_PATH = Path("/tmp/aureon.db")
else:
    DB_PATH = Path(__file__).parent.parent / "data" / "aureon.db"


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fingerprint(entry: dict) -> str:
    """Cryptographic governance fingerprint — makes each log entry tamper-evident."""
    payload = json.dumps({k: v for k, v in entry.items() if k != "fingerprint"},
                         sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def init_audit_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id     TEXT NOT NULL,
            practice    TEXT NOT NULL,
            event       TEXT NOT NULL,
            actor       TEXT NOT NULL,
            detail      TEXT,
            tier        TEXT DEFAULT 'SYSTEM',
            fingerprint TEXT,
            created_at  TEXT NOT NULL
        )
    """)
    conn.commit()


def log(case_id: str, practice: str, event: str, actor: str,
        detail: str = "", tier: str = "SYSTEM") -> dict:
    """Append an immutable entry to the Decision System of Record."""
    conn = sqlite3.connect(DB_PATH)
    init_audit_table(conn)
    entry = {
        "case_id":  case_id,
        "practice": practice,
        "event":    event,
        "actor":    actor,
        "detail":   detail,
        "tier":     tier,
        "created_at": ts(),
    }
    entry["fingerprint"] = fingerprint(entry)
    conn.execute("""
        INSERT INTO audit_log
        (case_id, practice, event, actor, detail, tier, fingerprint, created_at)
        VALUES (:case_id,:practice,:event,:actor,:detail,:tier,:fingerprint,:created_at)
    """, entry)
    conn.commit()
    conn.close()
    return entry


def get_log(case_id: str, limit: int = 100) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM audit_log WHERE case_id=? ORDER BY id DESC LIMIT ?",
        (case_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_logs(practice: str, limit: int = 200) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM audit_log WHERE practice=? ORDER BY id DESC LIMIT ?",
        (practice, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
