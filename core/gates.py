"""
Aureon Engine — Human-in-the-Loop (HITL) Gate Framework
Shared authority checkpoint system. Every consequential decision requires
explicit human clearance before downstream workflow proceeds.
No gate can be bypassed. Every decision is logged.

Gate states: open → pending → approved | escalated | rejected
"""

import os
import sqlite3
from pathlib import Path
from core.audit import log, ts

if os.environ.get("VERCEL"):
    DB_PATH = Path("/tmp/aureon.db")
else:
    DB_PATH = Path(__file__).parent.parent / "data" / "aureon.db"

VALID_ACTIONS = {"approve", "escalate", "reject"}

# Authority tier labels
TIER = {
    "L0": "System",
    "L1": "Analyst / Specialist",
    "L2": "Senior Analyst / Manager",
    "L3": "Supervisor / Director",
    "L4": "Relationship Manager / MD",
}


def init_gates_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hitl_gates (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id         TEXT NOT NULL,
            practice        TEXT NOT NULL,
            gate_id         TEXT NOT NULL,
            label           TEXT NOT NULL,
            authority       TEXT NOT NULL,
            authority_tier  TEXT DEFAULT 'L2',
            status          TEXT DEFAULT 'pending',
            blocking        INTEGER DEFAULT 0,
            recommendation  TEXT,
            cleared_by      TEXT,
            cleared_at      TEXT,
            rationale       TEXT,
            action          TEXT,
            created_at      TEXT NOT NULL,
            UNIQUE(case_id, gate_id)
        )
    """)
    conn.commit()


def open_gate(case_id: str, practice: str, gate_id: str, label: str,
              authority: str, authority_tier: str = "L2",
              blocking: bool = False, recommendation: str = "") -> dict:
    """Open a new HITL gate — fires automatically when trigger condition is met."""
    conn = sqlite3.connect(DB_PATH)
    init_gates_table(conn)
    now = ts()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO hitl_gates
            (case_id, practice, gate_id, label, authority, authority_tier,
             status, blocking, recommendation, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (case_id, practice, gate_id, label, authority, authority_tier,
              "open", int(blocking), recommendation, now))
        conn.commit()
    finally:
        conn.close()

    log(case_id, practice,
        f"{gate_id} Opened — {label}",
        "System",
        f"Authority: {authority}. Blocking: {blocking}. {recommendation}",
        "SYSTEM")

    return get_gate(case_id, gate_id)


def act_on_gate(case_id: str, practice: str, gate_id: str,
                action: str, actor: str, rationale: str) -> dict:
    """Record a human decision on a HITL gate."""
    if action not in VALID_ACTIONS:
        raise ValueError(f"Invalid action: {action}. Must be one of {VALID_ACTIONS}")

    conn = sqlite3.connect(DB_PATH)
    init_gates_table(conn)
    now = ts()
    status_map = {"approve": "cleared", "escalate": "escalated", "reject": "rejected"}
    new_status = status_map[action]

    conn.execute("""
        UPDATE hitl_gates
        SET status=?, action=?, cleared_by=?, cleared_at=?, rationale=?
        WHERE case_id=? AND gate_id=?
    """, (new_status, action, actor, now, rationale, case_id, gate_id))
    conn.commit()
    conn.close()

    tier = "L2"
    conn2 = sqlite3.connect(DB_PATH)
    row = conn2.execute(
        "SELECT authority_tier, label FROM hitl_gates WHERE case_id=? AND gate_id=?",
        (case_id, gate_id)).fetchone()
    conn2.close()
    if row:
        tier = row[0]
        label = row[1]
    else:
        label = gate_id

    log(case_id, practice,
        f"{gate_id} {new_status.title()} — {label}",
        actor,
        rationale,
        tier)

    return get_gate(case_id, gate_id)


def get_gate(case_id: str, gate_id: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM hitl_gates WHERE case_id=? AND gate_id=?",
        (case_id, gate_id)).fetchone()
    conn.close()
    return dict(row) if row else {}


def get_gates(case_id: str) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM hitl_gates WHERE case_id=? ORDER BY id",
        (case_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def all_gates_cleared(case_id: str, required_gates: list[str]) -> bool:
    """Check if all required gates for a stage transition are cleared."""
    gates = {g["gate_id"]: g for g in get_gates(case_id)}
    return all(gates.get(gid, {}).get("status") == "cleared"
               for gid in required_gates)


def has_blocking_gates(case_id: str) -> bool:
    """Return True if any open blocking gate exists."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT COUNT(*) FROM hitl_gates WHERE case_id=? AND blocking=1 AND status='open'",
        (case_id,)).fetchone()
    conn.close()
    return row[0] > 0
