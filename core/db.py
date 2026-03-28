"""
Aureon Engine — Database Layer
Single SQLite database. All practices share the same tables.
Practice column partitions the data.

Vercel note: SQLite writes to /tmp on serverless — data resets between
cold starts. For production persistence use PostgreSQL via DATABASE_URL.
"""

import os
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime, timezone

# Use /tmp on Vercel (serverless), local data/ dir otherwise
if os.environ.get("VERCEL"):
    DB_PATH = Path("/tmp/aureon.db")
else:
    DB_PATH = Path(__file__).parent.parent / "data" / "aureon.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def init_db():
    Path(DB_PATH).parent.mkdir(exist_ok=True)
    conn = get_conn()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS cases (
        id           TEXT PRIMARY KEY,
        practice     TEXT NOT NULL,
        name         TEXT NOT NULL,
        client       TEXT NOT NULL,
        module       TEXT,
        stage        INTEGER DEFAULT 1,
        total_stages INTEGER DEFAULT 5,
        status       TEXT DEFAULT 'active',
        week         INTEGER DEFAULT 1,
        total_weeks  INTEGER DEFAULT 32,
        metadata     TEXT DEFAULT '{}',
        created_at   TEXT,
        updated_at   TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS workstreams (
        id           TEXT PRIMARY KEY,
        case_id      TEXT,
        practice     TEXT,
        name         TEXT,
        progress     INTEGER DEFAULT 0,
        status       TEXT DEFAULT 'not_started',
        owner        TEXT,
        FOREIGN KEY (case_id) REFERENCES cases(id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS risks (
        id           TEXT PRIMARY KEY,
        case_id      TEXT,
        practice     TEXT,
        title        TEXT,
        description  TEXT,
        severity     TEXT DEFAULT 'amber',
        status       TEXT DEFAULT 'open',
        FOREIGN KEY (case_id) REFERENCES cases(id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS mappings (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id      TEXT,
        practice     TEXT,
        client_field TEXT,
        target_field TEXT,
        confidence   REAL,
        status       TEXT DEFAULT 'auto',
        created_at   TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id      TEXT NOT NULL,
        practice     TEXT NOT NULL,
        event        TEXT NOT NULL,
        actor        TEXT NOT NULL,
        detail       TEXT,
        tier         TEXT DEFAULT 'SYSTEM',
        fingerprint  TEXT,
        created_at   TEXT NOT NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS hitl_gates (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id        TEXT NOT NULL,
        practice       TEXT NOT NULL,
        gate_id        TEXT NOT NULL,
        label          TEXT NOT NULL,
        authority      TEXT NOT NULL,
        authority_tier TEXT DEFAULT 'L2',
        status         TEXT DEFAULT 'open',
        blocking       INTEGER DEFAULT 0,
        recommendation TEXT,
        cleared_by     TEXT,
        cleared_at     TEXT,
        rationale      TEXT,
        action         TEXT,
        created_at     TEXT NOT NULL,
        UNIQUE(case_id, gate_id)
    )""")

    conn.commit()
    conn.close()
    _seed()


def _seed():
    conn = get_conn()
    c = conn.cursor()

    if c.execute("SELECT id FROM cases WHERE id='ACT-001'").fetchone():
        conn.close()
        return

    now = ts()

    # ── ACT PRACTICE CASES ────────────────────────────────────────────
    cases = [
        ("ACT-001","transformation","Meridian Capital Partners","Meridian Capital","aladdin",
         3,5,"active",14,32,now,now),
        ("ACT-002","transformation","Atlas Pension Fund","Atlas Pension","aladdin",
         2,5,"active",6,40,now,now),
        ("ACT-003","transformation","Sovereign Wealth DR","Min. of Finance DR","federal",
         1,5,"active",2,52,now,now),
        # ── ONBOARDING PRACTICE CASES ─────────────────────────────────
        ("OB-001","onboarding","Thornfield Capital Group","Thornfield Capital","IVC",
         2,5,"active",8,None,now,now),
        ("OB-002","onboarding","Meridian Asset Management","Meridian AM","PMT",
         4,5,"active",12,None,now,now),
    ]
    c.executemany("""INSERT INTO cases
        (id,practice,name,client,module,stage,total_stages,status,week,total_weeks,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", cases)

    # ── ACT WORKSTREAMS ───────────────────────────────────────────────
    ws = [
        ("WS-001","ACT-001","transformation","Taxonomy translation",94,"on_track","B. Ravelo"),
        ("WS-002","ACT-001","transformation","Workflow design — EQ",80,"on_track","J. Park"),
        ("WS-003","ACT-001","transformation","Workflow design — FI",65,"needs_attention","J. Park"),
        ("WS-004","ACT-001","transformation","Data interface build",40,"needs_attention","T. Chen"),
        ("WS-005","ACT-001","transformation","UAT execution",15,"not_started","M. Singh"),
        ("WS-006","ACT-001","transformation","Training & documentation",20,"not_started","B. Ravelo"),
        ("WS-007","ACT-002","transformation","Taxonomy translation",45,"on_track","B. Ravelo"),
        ("WS-008","ACT-002","transformation","Workflow design — EQ",30,"on_track","L. Torres"),
        ("WS-009","ACT-002","transformation","Workflow design — FI",10,"not_started","L. Torres"),
        ("WS-010","ACT-003","transformation","Document ingestion",80,"on_track","B. Ravelo"),
        ("WS-011","ACT-003","transformation","Taxonomy translation",20,"needs_attention","B. Ravelo"),
        # ── ONBOARDING WORKSTREAMS ────────────────────────────────────
        ("WS-012","OB-001","onboarding","Document classification",45,"needs_attention","D. Patel"),
        ("WS-013","OB-001","onboarding","KYC review",0,"not_started","J. Martinez"),
        ("WS-014","OB-001","onboarding","Platform setup",0,"not_started","T. Okafor"),
        ("WS-015","OB-002","onboarding","Document classification",100,"on_track","D. Patel"),
        ("WS-016","OB-002","onboarding","KYC review",85,"on_track","J. Martinez"),
        ("WS-017","OB-002","onboarding","Platform setup",60,"on_track","T. Okafor"),
        ("WS-018","OB-002","onboarding","UAT & go-live",20,"on_track","S. Reeves"),
    ]
    c.executemany("INSERT INTO workstreams VALUES (?,?,?,?,?,?,?)", ws)

    # ── RISKS ─────────────────────────────────────────────────────────
    risks = [
        ("R-001","ACT-001","transformation","FI workflow sign-off delayed",
         "CRO availability blocking week 15 milestone.","red","open"),
        ("R-002","ACT-001","transformation","Interface file delivery at risk",
         "Client tech team capacity constrained. 3-day buffer remains.","amber","open"),
        ("R-003","ACT-002","transformation","Taxonomy edge cases high",
         "23 unresolved edge cases in derivatives mapping.","amber","open"),
        ("R-004","OB-001","onboarding","Tax pre-gate blocking KYC",
         "W-8BEN-E missing. Cayman Islands entity. KYC blocked.","red","open"),
        ("R-005","OB-001","onboarding","Parent entity not onboarded",
         "Thornfield Capital Group Ltd not in entity registry.","red","open"),
    ]
    c.executemany("INSERT INTO risks VALUES (?,?,?,?,?,?,?)", risks)

    # ── HITL GATES — ACT-001 ──────────────────────────────────────────
    gates = [
        ("ACT-001","transformation","HITL-1","Taxonomy confidence review",
         "Delivery lead","L2","cleared",0,
         "Review field mappings below 85% confidence.",
         "B. Ravelo","2026-03-24T09:18:00Z",
         "18 edge cases resolved. Remaining 3 escalated to client for clarification.","approve",now),
        ("ACT-001","transformation","HITL-2","Workflow design sign-off — EQ",
         "Front office director","L3","cleared",0,
         "CIO/PM sign-off required before EQ workflow goes to UAT.",
         "J. Park","2026-03-25T14:00:00Z",
         "EQ workflow approved. Proceeds to UAT.","approve",now),
        ("ACT-001","transformation","HITL-3","Workflow design sign-off — FI",
         "Front office director","L3","open",1,
         "CRO session required. Blocks UAT start.",
         None,None,None,None,now),
        ("ACT-001","transformation","HITL-4","UAT sign-off",
         "Delivery lead + client PM","L3","pending",0,
         "All workstreams must be complete before UAT gate opens.",
         None,None,None,None,now),
        ("ACT-001","transformation","HITL-5","Interface validation",
         "Integration VP","L2","pending",0,
         "Interface files must be delivered and validated.",
         None,None,None,None,now),
        ("ACT-001","transformation","HITL-6","Go-live authorization",
         "Regional MD","L4","pending",0,
         "All gates must be cleared before go-live is authorized.",
         None,None,None,None,now),
        # ── OB-001 GATES ──────────────────────────────────────────────
        ("OB-001","onboarding","HITL-1","Tax pre-gate",
         "KYC Tax Specialist","L1","open",1,
         "W-8BEN-E missing. Cayman Islands entity requires foreign status cert. KYC BLOCKED.",
         None,None,None,None,now),
        ("OB-001","onboarding","HITL-2","Entity hierarchy check",
         "KYC Senior Analyst","L2","open",1,
         "Parent entity Thornfield Capital Group not in registry. Subsidiary blocked.",
         None,None,None,None,now),
        ("OB-001","onboarding","HITL-3","Document confidence review",
         "Onboarding Specialist","L1","open",0,
         "IS-001 classified at 72% confidence. Entity name discrepancy detected.",
         None,None,None,None,now),
        ("OB-001","onboarding","HITL-4","Enhanced due diligence",
         "KYC Senior Analyst","L2","pending",0,
         "Cayman Islands jurisdiction. Will activate after HITL-1 and HITL-2 cleared.",
         None,None,None,None,now),
        ("OB-001","onboarding","HITL-5","Completeness approval",
         "KYC Supervisor","L3","pending",0,
         "Completeness score 45%. Gate opens at 100%.",
         None,None,None,None,now),
        ("OB-001","onboarding","HITL-6","Go-live authorization",
         "Relationship Manager","L4","pending",0,
         "Awaiting all upstream gate clearances.",
         None,None,None,None,now),
        # ── OB-002 GATES (mostly cleared) ─────────────────────────────
        ("OB-002","onboarding","HITL-1","Tax pre-gate",
         "KYC Tax Specialist","L1","cleared",0,
         "W-9 present and current.",
         "D. Patel","2026-03-20T09:20:00Z",
         "US domestic entity confirmed. No withholding exception.","approve",now),
        ("OB-002","onboarding","HITL-2","Entity hierarchy check",
         "KYC Senior Analyst","L2","cleared",0,
         "Standalone entity confirmed.",
         "J. Martinez","2026-03-20T09:22:00Z",
         "No parent dependency. Beneficial ownership current.","approve",now),
        ("OB-002","onboarding","HITL-3","Document confidence review",
         "Onboarding Specialist","L1","cleared",0,
         "All documents at 85%+ confidence.",
         "T. Okafor","2026-03-20T09:18:00Z",
         "All documents verified. Matrix accepted.","approve",now),
        ("OB-002","onboarding","HITL-4","Enhanced due diligence",
         "KYC Senior Analyst","L2","cleared",0,
         "No EDD trigger.",
         "J. Martinez","2026-03-20T09:25:00Z",
         "US entity, standard jurisdiction, no PEP flag.","approve",now),
        ("OB-002","onboarding","HITL-5","Completeness approval",
         "KYC Supervisor","L3","cleared",0,
         "Completeness 100%.",
         "R. Thompson","2026-03-22T11:00:00Z",
         "All documents present. Platform setup authorized.","approve",now),
        ("OB-002","onboarding","HITL-6","Go-live authorization",
         "Relationship Manager","L4","open",0,
         "UAT complete. Awaiting RM go-live sign-off.",
         None,None,None,None,now),
    ]
    c.executemany("""INSERT INTO hitl_gates
        (case_id,practice,gate_id,label,authority,authority_tier,status,blocking,
         recommendation,cleared_by,cleared_at,rationale,action,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", gates)

    # ── AUDIT LOG SEED ────────────────────────────────────────────────
    import hashlib, json
    def fp(d):
        p = json.dumps({k:v for k,v in d.items() if k!="fingerprint"}, sort_keys=True)
        return hashlib.sha256(p.encode()).hexdigest()[:16]

    logs = [
        ("ACT-001","transformation","Engagement created","System",
         "Meridian Capital Partners onboarding initiated. Practice: Aladdin.","SYSTEM",now),
        ("ACT-001","transformation","Document ingestion complete","System",
         "Client SLA and playbooks ingested. 47 fields extracted for taxonomy mapping.","SYSTEM",now),
        ("ACT-001","transformation","Taxonomy mapping — 94% auto-mapped","System",
         "44/47 fields mapped automatically. 3 edge cases routed to HITL-1.","SYSTEM",now),
        ("ACT-001","transformation","HITL-1 Cleared — Taxonomy confidence review","B. Ravelo",
         "18 edge cases resolved. 3 escalated to client.","L2",now),
        ("ACT-001","transformation","HITL-2 Cleared — Workflow design sign-off EQ","J. Park",
         "EQ workflow approved by Front Office Director.","L3",now),
        ("OB-001","onboarding","Case created — Exception path","System",
         "Thornfield Capital Group Ltd. Product: IVC. Cayman Islands entity.","SYSTEM",now),
        ("OB-001","onboarding","Tax pre-gate FAILED — HITL-1 opened","System",
         "W-8BEN-E not found. Cayman Islands entity requires foreign cert. KYC BLOCKED.","SYSTEM",now),
        ("OB-001","onboarding","Entity hierarchy check FAILED — HITL-2 opened","System",
         "Parent entity not in onboarded registry. Subsidiary blocked.","SYSTEM",now),
        ("OB-002","onboarding","HITL-5 Cleared — Completeness approval","R. Thompson",
         "All documents present. Platform setup authorized.","L3",now),
        ("OB-002","onboarding","HITL-6 opened — Go-live authorization","System",
         "UAT complete. Awaiting Relationship Manager authorization.","SYSTEM",now),
    ]
    for log_entry in logs:
        d = {"case_id":log_entry[0],"practice":log_entry[1],"event":log_entry[2],
             "actor":log_entry[3],"detail":log_entry[4],"tier":log_entry[5],
             "created_at":log_entry[6]}
        d["fingerprint"] = fp(d)
        c.execute("""INSERT INTO audit_log
            (case_id,practice,event,actor,detail,tier,fingerprint,created_at)
            VALUES (:case_id,:practice,:event,:actor,:detail,:tier,:fingerprint,:created_at)
        """, d)

    conn.commit()
    conn.close()


# ── READ HELPERS ──────────────────────────────────────────────────────

def get_case(case_id: str) -> dict:
    conn = get_conn()
    c = conn.cursor()
    case = c.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
    if not case:
        conn.close()
        return {}
    case = dict(case)
    case["workstreams"] = [dict(r) for r in
        c.execute("SELECT * FROM workstreams WHERE case_id=?", (case_id,)).fetchall()]
    case["risks"] = [dict(r) for r in
        c.execute("SELECT * FROM risks WHERE case_id=? AND status='open'", (case_id,)).fetchall()]
    case["gates"] = [dict(r) for r in
        c.execute("SELECT * FROM hitl_gates WHERE case_id=? ORDER BY id", (case_id,)).fetchall()]
    case["audit"] = [dict(r) for r in
        c.execute("SELECT * FROM audit_log WHERE case_id=? ORDER BY id DESC LIMIT 50", (case_id,)).fetchall()]
    case["mappings"] = [dict(r) for r in
        c.execute("SELECT * FROM mappings WHERE case_id=? ORDER BY id DESC LIMIT 100", (case_id,)).fetchall()]
    conn.close()

    ws = case["workstreams"]
    case["overall_pct"] = sum(w["progress"] for w in ws) // max(len(ws), 1) if ws else 0
    case["open_risks"]  = len(case["risks"])
    case["blocking_gates"] = sum(1 for g in case["gates"]
                                 if g["status"] == "open" and g["blocking"])
    return case


def get_portfolio(practice: str = None) -> list[dict]:
    conn = get_conn()
    c = conn.cursor()
    if practice:
        rows = c.execute("SELECT * FROM cases WHERE practice=? ORDER BY updated_at DESC",
                         (practice,)).fetchall()
    else:
        rows = c.execute("SELECT * FROM cases ORDER BY practice, updated_at DESC").fetchall()
    result = []
    for row in rows:
        case = dict(row)
        ws = [dict(r) for r in
              c.execute("SELECT * FROM workstreams WHERE case_id=?", (case["id"],)).fetchall()]
        rs = [dict(r) for r in
              c.execute("SELECT * FROM risks WHERE case_id=? AND status='open'", (case["id"],)).fetchall()]
        gs = [dict(r) for r in
              c.execute("SELECT * FROM hitl_gates WHERE case_id=? AND status='open' AND blocking=1",
                        (case["id"],)).fetchall()]
        case["workstreams"]    = ws
        case["open_risks"]     = len(rs)
        case["blocking_gates"] = len(gs)
        case["overall_pct"]    = sum(w["progress"] for w in ws) // max(len(ws),1) if ws else 0
        result.append(case)
    conn.close()
    return result


def save_mappings(case_id: str, practice: str, results: dict):
    conn = get_conn()
    now = ts()
    for m in results.get("mappings", []):
        if m["status"] != "no_match":
            conn.execute("""INSERT INTO mappings
                (case_id,practice,client_field,target_field,confidence,status,created_at)
                VALUES (?,?,?,?,?,?,?)""",
                (case_id, practice, m["client_field"], m.get("target_field"),
                 m["confidence"], m["status"], now))
    conn.commit()
    conn.close()
