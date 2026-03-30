"""
Aureon Engine — Workflow Design Module
=======================================
Purpose: Create the initial taxonomy base mapping a client's current investment
operating playbook 1:1 to Aladdin-specific workflows and required operating changes.

Doctrine: Every unmapped gap is a transformation risk. This module forces completeness
at intake — before any governance gate can open, every playbook item must have an
Aladdin workflow equivalent, a delta classification, and an operating change owner.

Practice:   transformation (existing Aureon practice)
Route:      /workflow
HITL gate:  workflow_review — must clear before artifact is generated
Audit:      Every mapping row is fingerprinted to the Decision System of Record
Consumers:  Execution Lead (project plan) · Delivery Lead (standardization targets)

Asset class scope (v1): Equities + Fixed Income — core public markets

Storage:    aureon.db — workflow_artifacts table (NOT flask.session)
            Production-safe: survives Vercel cold starts and multi-process deploys.
            Table is auto-created on first use via _ensure_table().
"""

import hashlib
import json
import os
import csv
import tempfile
import uuid
from html import escape
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# TAXONOMY DICTIONARIES
# Aladdin-specific workflow vocabulary per asset class.
# Each entry: canonical Aladdin term -> plain-language description.
# ---------------------------------------------------------------------------

ALADDIN_EQ = {
    "portfolio_construction":   "Aladdin portfolio construction — BQL-driven factor models and constraint optimization",
    "order_management":         "OMS order entry — ticket creation, allocation, and routing via Aladdin trading workflows",
    "pre_trade_compliance":     "Pre-trade compliance checks — rule engine validation before order release",
    "execution_algo_routing":   "Execution algorithm routing — broker connectivity and algo selection within Aladdin",
    "trade_capture":            "Trade capture — real-time booking of equity executions into Aladdin blotter",
    "allocation":               "Post-trade allocation — block trade breakdown to account level",
    "affirmation_matching":     "Affirmation and matching — DTC/DTCC connectivity for trade confirmation",
    "settlement_instruction":   "Settlement instruction generation — custodian-specific SSI routing",
    "custodian_recon":          "Custodian reconciliation — daily position and cash break identification and resolution",
    "corporate_actions":        "Corporate action processing — mandatory and voluntary event workflow within Aladdin",
    "performance_attribution":  "Performance attribution — Aladdin returns calculation against benchmark",
    "compliance_monitoring":    "Ongoing compliance monitoring — rule breach alert and escalation workflow",
    "regulatory_reporting":     "Regulatory reporting — MiFID II, 13F, and other statutory output generation",
    "client_reporting":         "Client reporting — Aladdin report center and custom output scheduling",
}

ALADDIN_FI = {
    "abor":                       "ABOR (Accounting Book of Records) — accounting-basis positions reflecting settled trades and accruals",
    "ibor":                       "IBOR (Investment Book of Records) — real-time investment-basis positions including pending trades",
    "abor_ibor_reconciliation":   "ABOR/IBOR reconciliation — daily automated break identification between investment and accounting views",
    "duration_analytics":         "Duration and DV01 analytics — Aladdin risk factor calculation for fixed income portfolios",
    "yield_curve_mapping":        "Yield curve mapping — rate environment configuration and spread analytics within Aladdin",
    "credit_risk":                "Credit risk analytics — issuer exposure, spread duration, and default probability within Aladdin",
    "pre_trade_compliance_fi":    "Pre-trade compliance — fixed income rule engine including duration, concentration, and rating limits",
    "order_management_fi":        "Fixed income OMS — RFQ workflow, dealer connectivity, and execution capture",
    "trade_date_matching":        "Trade date matching — T+0 confirmation matching with counterparty and custodian",
    "settlement_fi":              "Settlement — fixed income settlement instruction generation and custodian routing (DvP)",
    "accrual_engine":             "Accrual engine — daily coupon and fee accrual calculation and booking",
    "amortization":               "Amortization — premium/discount amortization (effective interest method) within Aladdin accounting",
    "income_recognition":         "Income recognition — dividend and coupon income booking to accounting ledger",
    "fx_hedge_accounting":        "FX hedge accounting — cross-currency hedge designation and effectiveness testing",
    "custodian_recon_fi":         "Custodian reconciliation — fixed income position, cash, and accrual break workflow",
    "data_conversion_fi":         "Data conversion — security master migration, pricing source mapping, and reference data validation",
    "dsor":                       "DSOR (Daily System of Record) — end-of-day position and NAV affirmation workflow",
    "risk_reporting":             "Risk reporting — Aladdin risk factor reporting for fixed income portfolios",
    "performance_attribution_fi": "Fixed income performance attribution — return decomposition by duration, spread, and carry",
}

RISK_LEVELS = {
    "critical": "Blocks go-live. Requires resolution before UAT gate.",
    "high":     "Material delivery risk. Requires mitigation plan by week 4.",
    "medium":   "Managed risk. Owner assigned. Tracked weekly.",
    "low":      "Informational. No action required before parallel run.",
}

CHANGE_TYPES = {
    "process_redesign":    "Client must redesign an existing operational process to match Aladdin workflow",
    "data_remediation":    "Client must cleanse, enrich, or reformat data before Aladdin can consume it",
    "system_decommission": "Client must retire a legacy system or process that Aladdin replaces",
    "new_capability":      "Client is adopting a workflow that does not exist in their current operating model",
    "configuration_only":  "Aladdin configuration change with no client process change required",
    "training_only":       "No process change. User training and adoption work required.",
}


# ---------------------------------------------------------------------------
# DB PERSISTENCE
# Uses the same get_conn() function passed in from app.py.
# Table workflow_artifacts is auto-created on first use.
# ---------------------------------------------------------------------------

def _ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workflow_artifacts (
            engagement_id TEXT PRIMARY KEY,
            artifact_json TEXT NOT NULL,
            gate_status   TEXT NOT NULL DEFAULT 'pending',
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL
        )
    """)
    try:
        conn.execute("ALTER TABLE workflow_artifacts ADD COLUMN extracted_text TEXT")
        conn.commit()
    except Exception:
        pass
    conn.commit()


def save_artifact(conn, engagement_id: str, artifact: dict):
    _ensure_table(conn)
    now = datetime.now(timezone.utc).isoformat()
    extracted_text = artifact.get("extracted_text", "")
    conn.execute("""
        INSERT INTO workflow_artifacts (engagement_id, artifact_json, extracted_text, gate_status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(engagement_id) DO UPDATE SET
            artifact_json = excluded.artifact_json,
            extracted_text = excluded.extracted_text,
            gate_status   = excluded.gate_status,
            updated_at    = excluded.updated_at
    """, (
        engagement_id,
        json.dumps(artifact),
        extracted_text,
        artifact.get("hitl_gate", {}).get("status", "pending"),
        now,
        now,
    ))
    conn.commit()


def load_artifact(conn, engagement_id: str):
    _ensure_table(conn)
    row = conn.execute(
        "SELECT artifact_json, extracted_text FROM workflow_artifacts WHERE engagement_id = ?",
        (engagement_id,)
    ).fetchone()
    if not row:
        return None
    artifact = json.loads(row[0])
    if len(row) > 1 and row[1] is not None:
        artifact["extracted_text"] = row[1]
    return artifact


def list_artifacts(conn) -> list:
    _ensure_table(conn)
    rows = conn.execute(
        "SELECT engagement_id, gate_status, created_at, updated_at "
        "FROM workflow_artifacts ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# CORE MAPPING ENGINE
# ---------------------------------------------------------------------------

def get_anthropic_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")

    from anthropic import Anthropic
    return Anthropic(api_key=api_key)


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        if len(parts) >= 2:
            cleaned = parts[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
    return cleaned.strip()


def _extract_json_object(text: str) -> str:
    cleaned = _strip_code_fences(text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Model response did not contain a JSON object.")
    return cleaned[start:end + 1]


def _parse_gap_analysis_json(text: str) -> dict:
    return json.loads(_extract_json_object(text))


def _repair_gap_analysis_json(client, raw_text: str) -> dict:
    repair_prompt = f"""Repair the following malformed JSON into a single valid JSON object.
Return JSON only. Do not add markdown fences or commentary.

{raw_text}"""
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        messages=[{"role": "user", "content": repair_prompt}]
    )
    repaired = response.content[0].text.strip()
    return _parse_gap_analysis_json(repaired)


def get_workflow_vocab_text() -> str:
    return "\n".join(
        f"- {key}: {value}"
        for dictionary in (ALADDIN_EQ, ALADDIN_FI)
        for key, value in dictionary.items()
    )


def build_transformation_design_prompt(intake: dict, extracted_text: str) -> str:
    asset_classes = ", ".join(intake.get("asset_classes", []))
    return f"""You are an Aladdin Client Transformation (ACT) senior delivery architect.

You have received a client's Current Operating Model document. Your task is to:
1. Design the Aladdin workflow streams that must be built for this client
2. Identify every gap between the client's current state and the Aladdin target state
3. Classify each gap by risk level
4. Estimate a transformation timeline

CLIENT METADATA
---------------
Client: {intake.get("client_name", "Unknown")}
Type: {intake.get("client_type", "Unknown")}
AUM: {intake.get("aum", "Unknown")}
Asset classes: {asset_classes}

CURRENT OPERATING MODEL DOCUMENT
---------------------------------
{extracted_text}

ALADDIN WORKFLOW VOCABULARY
----------------------------
{get_workflow_vocab_text()}

OUTPUT FORMAT
-------------
Return a single valid JSON object. No markdown fences. No prose outside JSON.

{{
  "transformation_summary": {{
    "client_name": "...",
    "total_streams": 0,
    "total_gaps": 0,
    "critical_gaps": 0,
    "high_gaps": 0,
    "estimated_weeks": 0,
    "primary_risk": "one sentence",
    "recommended_first_stream": "..."
  }},
  "transformation_register": [
    {{
      "id": "STREAM-001",
      "workflow_stream": "name of the Aladdin workflow stream to be built",
      "aladdin_module": "exact key from vocabulary",
      "current_state": "how client does this today per the document",
      "gap_description": "specific gap between current state and Aladdin target",
      "risk_level": "critical | high | medium | low",
      "risk_rationale": "one sentence",
      "operating_change": "what the client must change",
      "data_conversion_required": true,
      "uat_scope_item": true,
      "workstream_owner": "Front Office | Execution Lead | Delivery Lead | Technology | Client",
      "phase_name": "Phase 1 — Discovery & Design | Phase 2 — Build & Configure | Phase 3 — UAT & Parallel Run | Phase 4 — Go-Live & Stabilization",
      "week_start": 1,
      "week_end": 8,
      "milestone": "specific deliverable name"
    }}
  ],
  "phases": [
    {{
      "phase_name": "Phase 1 — Discovery & Design",
      "week_start": 1,
      "week_end": 8,
      "objectives": "...",
      "key_deliverables": ["...", "..."]
    }}
  ],
  "data_conversion_summary": "...",
  "uat_scope_summary": "...",
  "configuration_summary": "...",
  "operating_model_changes": "...",
  "handoff_to_execution_lead": "...",
  "handoff_to_delivery_lead": "..."
}}"""


def run_transformation_design(intake: dict, extracted_text: str) -> dict:
    client = get_anthropic_client()
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=5000,
        messages=[{"role": "user", "content": build_transformation_design_prompt(intake, extracted_text)}]
    )
    raw = response.content[0].text.strip()
    try:
        return _parse_gap_analysis_json(raw)
    except (json.JSONDecodeError, ValueError):
        return _repair_gap_analysis_json(client, raw)


def build_document_intake(form) -> dict:
    return {
        "client_name": form.get("client_name", "").strip(),
        "client_type": form.get("client_type", "").strip(),
        "aum": form.get("aum", "").strip(),
        "asset_classes": form.getlist("asset_classes"),
        "director_name": form.get("director_name", "ACT Director").strip(),
    }


def extract_document_text(file_storage, upload_dir: Path) -> str:
    ext = Path(file_storage.filename or "").suffix.lower()
    if ext not in (".pdf", ".docx", ".txt", ".csv"):
        raise ValueError("Unsupported file type")

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext, dir=str(upload_dir)) as temp_file:
        temp_path = Path(temp_file.name)
    file_storage.save(temp_path)

    try:
        if ext == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(str(temp_path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        if ext == ".docx":
            from docx import Document

            document = Document(str(temp_path))
            return "\n".join(p.text for p in document.paragraphs if p.text.strip())
        if ext == ".csv":
            rows = []
            with temp_path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
                reader = csv.reader(handle)
                for row in reader:
                    line = ", ".join(cell.strip() for cell in row if cell.strip())
                    if line:
                        rows.append(line)
            return "\n".join(rows)
        return temp_path.read_text(encoding="utf-8", errors="ignore")
    finally:
        temp_path.unlink(missing_ok=True)


def build_gap_analysis_from_document(intake: dict, extracted_text: str) -> dict:
    doc_intake = {
        **intake,
        "current_platforms": intake.get("current_platforms", "Derived from uploaded current operating model"),
        "custodians": intake.get("custodians", "Derived from uploaded current operating model"),
        "data_sources": intake.get("data_sources", "Derived from uploaded current operating model"),
        "objectives": intake.get("objectives", "Derived from uploaded current operating model"),
        "pain_points": intake.get("pain_points", "Derived from uploaded current operating model"),
        "current_playbook": extracted_text,
    }
    return run_gap_analysis(doc_intake)

def build_gap_analysis_prompt(intake: dict) -> str:
    asset_classes = intake.get("asset_classes", [])
    vocab = {}
    if "equities" in asset_classes:
        vocab.update(ALADDIN_EQ)
    if "fixed_income" in asset_classes:
        vocab.update(ALADDIN_FI)

    vocab_text  = "\n".join(f"- {k}: {v}" for k, v in vocab.items())
    risk_text   = "\n".join(f"- {k}: {v}" for k, v in RISK_LEVELS.items())
    change_text = "\n".join(f"- {k}: {v}" for k, v in CHANGE_TYPES.items())

    return f"""You are an Aladdin Client Transformation (ACT) senior delivery architect.

Produce a structured 1:1 mapping between this client's current investment operating playbook
and Aladdin-specific workflows. This mapping IS the transformation risk register.
Every gap must be classified, owned, and tied to an operating change.

CLIENT ENGAGEMENT CONTEXT
--------------------------
Client name:         {intake.get("client_name", "Unnamed client")}
Client type:         {intake.get("client_type", "Not specified")}
Asset classes:       {", ".join(asset_classes)}
Current platforms:   {intake.get("current_platforms", "Not specified")}
AUM / scale:         {intake.get("aum", "Not specified")}
Primary objectives:  {intake.get("objectives", "Not specified")}
Stated pain points:  {intake.get("pain_points", "Not specified")}
Custodian(s):        {intake.get("custodians", "Not specified")}
Data sources:        {intake.get("data_sources", "Not specified")}
Current playbook:    {intake.get("current_playbook", "Not provided")}

ALADDIN WORKFLOW VOCABULARY (use these exact keys in your output)
------------------------------------------------------------------
{vocab_text}

RISK CLASSIFICATION
-------------------
{risk_text}

OPERATING CHANGE TYPES
----------------------
{change_text}

INSTRUCTIONS
------------
Output a single valid JSON object. No markdown fences. No prose outside the JSON.

{{
  "engagement_summary": {{
    "client_name": "...",
    "client_type": "...",
    "asset_classes": [...],
    "total_gaps": 0,
    "critical_gaps": 0,
    "high_gaps": 0,
    "primary_risk_surface": "one sentence",
    "recommended_first_workstream": "one sentence"
  }},
  "mapping_register": [
    {{
      "id": "GAP-001",
      "lifecycle_phase": "pre_trade | trade | post_trade | reporting | data",
      "asset_class": "equities | fixed_income | both",
      "client_playbook_item": "how the client does this today",
      "aladdin_workflow_key": "<exact key from vocabulary>",
      "aladdin_workflow_description": "what Aladdin does here",
      "delta": "specific gap description — prefix [INFERRED] if inferred",
      "operating_change_type": "<exact key from change types>",
      "operating_change_description": "what the client must specifically do",
      "risk_level": "critical | high | medium | low",
      "risk_rationale": "one sentence",
      "data_conversion_required": true,
      "uat_scope_item": true,
      "workstream_owner": "Front Office | Execution Lead | Delivery Lead | Technology | Client",
      "suggested_milestone_week": 4
    }}
  ],
  "data_conversion_summary": "...",
  "uat_scope_summary": "...",
  "configuration_summary": "...",
  "operating_model_changes": "...",
  "handoff_to_execution_lead": "...",
  "handoff_to_delivery_lead": "..."
}}

Rules:
- Every playbook item the client mentioned must appear in the register.
- Infer reasonable gaps; prefix delta with [INFERRED].
- Minimum 8 rows. Maximum 20 rows."""


def run_gap_analysis(intake: dict) -> dict:
    client = get_anthropic_client()
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        messages=[{"role": "user", "content": build_gap_analysis_prompt(intake)}]
    )
    raw = response.content[0].text.strip()
    try:
        return _parse_gap_analysis_json(raw)
    except (json.JSONDecodeError, ValueError):
        return _repair_gap_analysis_json(client, raw)


def fingerprint_register(mapping_register: list, engagement_id: str) -> list:
    ts = datetime.now(timezone.utc).isoformat()
    for row in mapping_register:
        delta_text = row.get("delta") or row.get("gap_description") or row.get("current_state", "")
        content = f"{engagement_id}|{row['id']}|{delta_text}|{row['risk_level']}|{ts}"
        row["_fingerprint"]    = hashlib.sha256(content.encode()).hexdigest()
        row["_audited_at"]     = ts
        row["_engagement_id"]  = engagement_id
    return mapping_register


def generate_artifact(gap_analysis: dict, intake: dict) -> dict:
    register = gap_analysis.get("mapping_register", [])
    summary  = gap_analysis.get("engagement_summary", {})
    order    = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    reg_sorted = sorted(
        register,
        key=lambda r: (order.get(r.get("risk_level", "low"), 3),
                       r.get("suggested_milestone_week", 99))
    )
    phases, workstreams = {}, {}
    for row in reg_sorted:
        phases.setdefault(row.get("lifecycle_phase", "unknown"), []).append(row)
        workstreams.setdefault(row.get("workstream_owner", "unknown"), []).append(row)

    return {
        "artifact_type":             "workflow_design_v1",
        "generated_at":              datetime.now(timezone.utc).isoformat(),
        "engagement_summary":        summary,
        "client_name":               intake.get("client_name"),
        "asset_classes":             intake.get("asset_classes", []),
        "mapping_register":          reg_sorted,
        "by_phase":                  phases,
        "by_workstream":             workstreams,
        "handoff_to_execution_lead": gap_analysis.get("handoff_to_execution_lead"),
        "handoff_to_delivery_lead":  gap_analysis.get("handoff_to_delivery_lead"),
        "uat_scope":                 [r for r in reg_sorted if r.get("uat_scope_item")],
        "uat_scope_summary":         gap_analysis.get("uat_scope_summary"),
        "data_conversion_scope":     [r for r in reg_sorted if r.get("data_conversion_required")],
        "data_conversion_summary":   gap_analysis.get("data_conversion_summary"),
        "configuration_summary":     gap_analysis.get("configuration_summary"),
        "operating_model_changes":   gap_analysis.get("operating_model_changes"),
        "risk_summary": {
            "total_gaps":      summary.get("total_gaps", len(register)),
            "critical":        summary.get("critical_gaps", 0),
            "high":            summary.get("high_gaps", 0),
            "primary_surface": summary.get("primary_risk_surface"),
        },
        "hitl_gate": {
            "gate_id":    "workflow_review",
            "status":     "pending",
            "cleared_by": None,
            "cleared_at": None,
            "notes":      None,
        },
    }


def clear_hitl_gate(artifact: dict, reviewer: str, notes: str = "") -> dict:
    artifact["hitl_gate"]["status"]     = "cleared"
    artifact["hitl_gate"]["cleared_by"] = reviewer
    artifact["hitl_gate"]["cleared_at"] = datetime.now(timezone.utc).isoformat()
    artifact["hitl_gate"]["notes"]      = notes
    return artifact


# ---------------------------------------------------------------------------
# FLASK ROUTES
# ---------------------------------------------------------------------------

def register_workflow_routes(app, get_conn):
    """
    Register all workflow design routes onto the Aureon Flask app.

    Call from app.py (after existing route definitions):

        from workflow_design import register_workflow_routes
        register_workflow_routes(app, get_conn)

    Parameters
    ----------
    app      : Flask application instance
    get_conn : callable — the get_conn() function from core.db
               Each route opens and closes its own connection.
               Safe for Vercel serverless and multi-worker deploys.

    Routes registered
    -----------------
    GET  /workflow                  Portfolio UI — workflow engagement dashboard
    GET  /workflow/upload           Stage 1 — document upload intake
    POST /workflow/extract          Stage 1 — document extraction + DB persist
    GET  /workflow/confirm/<id>     Stage 1 — extracted text confirmation
    POST /workflow/design/<id>      Stage 2 — gap analysis + transformation design
    GET  /workflow/new              Stage 1 — intake form (Front Office Director)
    POST /workflow/analyze          Stage 2 — Claude gap analysis + DB persist
    GET  /workflow/review/<id>      Stage 2 — HITL review screen
    POST /workflow/clear/<id>       Stage 2 — HITL gate clearance
    GET  /workflow/artifact/<id>    Stage 3 — governed artifact view
    GET  /workflow/export/<id>      Stage 3 — JSON export (Execution + Delivery Lead)
    GET  /workflow/list             Portfolio — all workflow engagements
    """

    @app.route("/workflow")
    def workflow_portfolio():
        from flask import render_template

        conn = get_conn()
        items = list_artifacts(conn)
        conn.close()

        pending = [item for item in items if item.get("gate_status") == "pending"]
        cleared = [item for item in items if item.get("gate_status") == "cleared"]

        enriched = []
        for item in items:
            gate_status = item.get("gate_status", "pending")
            enriched.append({
                **item,
                "detail_href": f"/workflow/artifact/{item['engagement_id']}"
                if gate_status == "cleared"
                else f"/workflow/review/{item['engagement_id']}",
                "detail_label": "Open artifact" if gate_status == "cleared" else "Open review",
            })

        return render_template(
            "workflow_landing.html",
            workflow_items=enriched,
            workflow_total=len(items),
            workflow_pending=len(pending),
            workflow_cleared=len(cleared),
        )

    @app.route("/workflow/upload")
    def workflow_upload():
        return """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Aureon — Workflow Upload</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#0a0a0f;color:#e8e6de;min-height:100vh;padding:40px 24px}
.wrap{max-width:920px;margin:0 auto}
.hdr{border-left:3px solid #c9a84c;padding-left:16px;margin-bottom:40px}
.hdr h1{font-size:22px;font-weight:500;color:#f0ede4}
.hdr p{font-size:13px;color:#888;margin-top:6px}
.sec{margin-bottom:32px}
.lbl{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#c9a84c;margin-bottom:12px;font-weight:500}
label{display:block;font-size:13px;color:#aaa;margin-bottom:5px;margin-top:16px}
input[type=text],select{width:100%;background:#14141e;border:1px solid #2a2a3a;border-radius:6px;color:#e8e6de;font-size:14px;padding:10px 14px;font-family:inherit;transition:border-color .2s}
input:focus,select:focus{outline:none;border-color:#c9a84c}
.drop{border:1px dashed #c9a84c55;background:#14141e;border-radius:10px;padding:26px 22px}
.drop input[type=file]{width:100%;padding:12px 0;color:#aaa}
.drop p{font-size:12px;color:#666;line-height:1.6;margin-top:8px}
.arow{display:flex;gap:16px;margin-top:8px;flex-wrap:wrap}
.arow label{display:flex;align-items:center;gap:8px;color:#e8e6de;font-size:14px;cursor:pointer;margin:0}
input[type=checkbox]{accent-color:#c9a84c;width:16px;height:16px}
hr{border:none;border-top:1px solid #1e1e2e;margin:28px 0}
.note{background:#0f0f1a;border-left:2px solid #2a2a3a;padding:12px 16px;font-size:12px;color:#666;border-radius:0 6px 6px 0;margin-bottom:32px;line-height:1.6}
.note span{color:#c9a84c}
.sub{display:flex;justify-content:flex-end;margin-top:32px}
button{background:#c9a84c;color:#0a0a0f;border:none;border-radius:6px;padding:12px 32px;font-size:14px;font-weight:600;cursor:pointer;transition:opacity .2s}
button:hover{opacity:.85}
.r{color:#c9a84c}
</style></head><body>
<div class="wrap">
  <div class="hdr">
    <h1>Aureon — Workflow Document Upload</h1>
    <p>Stage 1 of 4 · Upload current operating model → Extract text → Confirm → Design Aladdin workflows</p>
  </div>
  <div class="note"><span>Primary entry point:</span> Upload the client's current operating model document first. Aureon extracts the source text, lets you confirm it, then designs the target-state Aladdin workflow streams.</div>
  <form method="POST" action="/workflow/extract" enctype="multipart/form-data">
    <div class="sec">
      <div class="lbl">Document</div>
      <div class="drop">
        <label>Upload source file <span class="r">*</span></label>
        <input type="file" name="file" accept=".pdf,.docx,.txt,.csv" required>
        <p>Supported formats: PDF, DOCX, TXT, CSV. Use the client's current operating model, playbook, or process narrative as the source document.</p>
      </div>
    </div>
    <hr>
    <div class="sec">
      <div class="lbl">Engagement</div>
      <label>Client name <span class="r">*</span></label>
      <input type="text" name="client_name" required placeholder="e.g. Hartwell Asset Management">
      <label>Client type <span class="r">*</span></label>
      <select name="client_type" required>
        <option value="">— select —</option>
        <option>Pension fund</option><option>Insurance company</option><option>Asset manager</option>
        <option>Sovereign wealth fund</option><option>Endowment / foundation</option>
        <option>Family office</option><option>Bank / treasury</option>
      </select>
      <label>AUM / portfolio scale</label>
      <input type="text" name="aum" placeholder="e.g. $12B AUM across 3 mandates">
    </div>
    <hr>
    <div class="sec">
      <div class="lbl">Asset class scope</div>
      <div class="arow">
        <label><input type="checkbox" name="asset_classes" value="equities" checked> Equities</label>
        <label><input type="checkbox" name="asset_classes" value="fixed_income" checked> Fixed income</label>
      </div>
    </div>
    <hr>
    <div class="sec">
      <div class="lbl">ACT Director</div>
      <label>Your name (for audit trail)</label>
      <input type="text" name="director_name" placeholder="e.g. Bill Ravelo">
      <label>Engagement ID (auto-generated if blank)</label>
      <input type="text" name="engagement_id" placeholder="e.g. ACT-2026-014">
    </div>
    <div class="sub"><button type="submit">Extract document &rarr;</button></div>
  </form>
</div></body></html>"""

    @app.route("/workflow/extract", methods=["POST"])
    def workflow_extract():
        from flask import request

        if "file" not in request.files or not request.files["file"].filename:
            return "<pre style='color:#e84c4c;background:#0a0a0f;padding:24px'>Document upload is required.</pre>", 400

        intake = build_document_intake(request.form)
        engagement_id = (
            request.form.get("engagement_id", "").strip()
            or f"ACT-WF-{uuid.uuid4().hex[:8].upper()}"
        )

        try:
            extracted_text = extract_document_text(request.files["file"], Path(app.config["UPLOAD_FOLDER"]))
        except Exception as exc:
            return f"<pre style='color:#e84c4c;background:#0a0a0f;padding:24px'>Document extraction failed:\n{escape(str(exc))}</pre>", 400

        artifact = {
            "artifact_type": "workflow_design_v1",
            "engagement_id": engagement_id,
            "client_name": intake.get("client_name"),
            "client_type": intake.get("client_type"),
            "aum": intake.get("aum"),
            "asset_classes": intake.get("asset_classes", []),
            "director_name": intake.get("director_name"),
            "extracted_text": extracted_text,
            "hitl_gate": {
                "gate_id": "workflow_review",
                "status": "pending",
                "cleared_by": None,
                "cleared_at": None,
                "notes": None,
            },
        }

        conn = get_conn()
        save_artifact(conn, engagement_id, artifact)
        conn.close()

        return __import__("flask").redirect(f"/workflow/confirm/{engagement_id}")

    @app.route("/workflow/confirm/<engagement_id>")
    def workflow_confirm(engagement_id):
        conn = get_conn()
        artifact = load_artifact(conn, engagement_id)
        conn.close()
        if not artifact:
            return f"Engagement {engagement_id} not found.", 404

        extracted_text = escape(artifact.get("extracted_text", ""))
        asset_classes = ", ".join(artifact.get("asset_classes", [])) or "Not specified"
        return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Aureon — Confirm Extraction · {engagement_id}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0a0a0f;color:#e8e6de;padding:32px 24px}}
.wrap{{max-width:1100px;margin:0 auto}}
.hdr{{border-left:3px solid #c9a84c;padding-left:16px;margin-bottom:28px}}
.hdr h1{{font-size:20px;font-weight:500}}.hdr p{{font-size:12px;color:#666;margin-top:4px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:22px}}
.card{{background:#14141e;border:1px solid #1e1e2e;border-radius:8px;padding:14px 16px}}
.card h3{{font-size:11px;color:#c9a84c;margin-bottom:8px;font-weight:500;text-transform:uppercase;letter-spacing:.08em}}
.card p{{font-size:13px;color:#aaa;line-height:1.7}}
.panel{{background:#11131b;border:1px solid #1e1e2e;border-radius:10px;padding:16px;margin-bottom:22px}}
.panel pre{{white-space:pre-wrap;word-break:break-word;max-height:520px;overflow:auto;font-family:'JetBrains Mono','Fira Code',monospace;font-size:12px;line-height:1.6;color:#d6d3cb}}
.actions{{display:flex;justify-content:flex-end;gap:10px;flex-wrap:wrap}}
.btn{{display:inline-flex;align-items:center;justify-content:center;padding:10px 20px;border-radius:6px;font-size:13px;font-weight:600;text-decoration:none;border:1px solid #2a2a3a;background:#14141e;color:#e8e6de}}
.btn:hover{{border-color:#c9a84c;color:#c9a84c}}
.btn-primary{{background:#c9a84c;border-color:#c9a84c;color:#0a0a0f}}
</style></head><body>
<div class="wrap">
  <div class="hdr">
    <h1>Confirm Extracted Text — {engagement_id}</h1>
    <p>Review the uploaded document extraction before Aureon designs the Aladdin workflow streams.</p>
  </div>
  <div class="grid">
    <div class="card"><h3>Client</h3><p>{escape(artifact.get("client_name", "—"))}<br>{escape(artifact.get("client_type", "—"))}<br>{escape(artifact.get("aum", "—"))}</p></div>
    <div class="card"><h3>Scope</h3><p>Asset classes: {escape(asset_classes)}<br>Director: {escape(artifact.get("director_name", "—"))}<br>Gate status: {escape(artifact.get("hitl_gate", {}).get("status", "pending"))}</p></div>
  </div>
  <div class="panel">
    <div style="font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#c9a84c;margin-bottom:10px;font-weight:500">Extracted document text</div>
    <pre>{extracted_text}</pre>
  </div>
  <div class="actions">
    <a href="/workflow/upload" class="btn">Edit and re-upload</a>
    <form method="POST" action="/workflow/design/{engagement_id}" style="display:inline">
      <button class="btn btn-primary" type="submit">Confirm — design Aladdin workflows &rarr;</button>
    </form>
  </div>
</div></body></html>"""

    @app.route("/workflow/design/<engagement_id>", methods=["POST"])
    def workflow_design(engagement_id):
        from flask import redirect

        conn = get_conn()
        artifact = load_artifact(conn, engagement_id)
        if not artifact:
            conn.close()
            return f"Engagement {engagement_id} not found.", 404

        intake = {
            "client_name": artifact.get("client_name", ""),
            "client_type": artifact.get("client_type", ""),
            "aum": artifact.get("aum", ""),
            "asset_classes": artifact.get("asset_classes", []),
            "director_name": artifact.get("director_name", "ACT Director"),
        }
        extracted_text = artifact.get("extracted_text", "")

        try:
            gap_analysis = build_gap_analysis_from_document(intake, extracted_text)
            transformation_design = run_transformation_design(intake, extracted_text)
        except Exception as exc:
            conn.close()
            return f"<pre style='color:#e84c4c;background:#0a0a0f;padding:24px'>Transformation design failed:\n{escape(str(exc))}</pre>", 500

        gap_analysis["mapping_register"] = fingerprint_register(
            gap_analysis.get("mapping_register", []), engagement_id
        )
        transformation_design["transformation_register"] = fingerprint_register(
            transformation_design.get("transformation_register", []), engagement_id
        )

        designed_artifact = generate_artifact(gap_analysis, {
            **intake,
            "current_playbook": extracted_text,
        })
        artifact.update(designed_artifact)
        artifact["engagement_id"] = engagement_id
        artifact["director_name"] = intake["director_name"]
        artifact["extracted_text"] = extracted_text
        artifact["transformation_design"] = transformation_design

        save_artifact(conn, engagement_id, artifact)
        conn.close()

        return redirect(f"/workflow/review/{engagement_id}")

    @app.route("/workflow/new")
    def workflow_new():
        return """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Aureon — Workflow Design Intake</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#0a0a0f;color:#e8e6de;min-height:100vh;padding:40px 24px}
.wrap{max-width:860px;margin:0 auto}
.hdr{border-left:3px solid #c9a84c;padding-left:16px;margin-bottom:40px}
.hdr h1{font-size:22px;font-weight:500;color:#f0ede4}
.hdr p{font-size:13px;color:#888;margin-top:6px}
.sec{margin-bottom:32px}
.lbl{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#c9a84c;margin-bottom:12px;font-weight:500}
label{display:block;font-size:13px;color:#aaa;margin-bottom:5px;margin-top:16px}
input[type=text],textarea,select{width:100%;background:#14141e;border:1px solid #2a2a3a;border-radius:6px;color:#e8e6de;font-size:14px;padding:10px 14px;font-family:inherit;transition:border-color .2s}
input:focus,textarea:focus,select:focus{outline:none;border-color:#c9a84c}
textarea{min-height:100px;resize:vertical}
.arow{display:flex;gap:16px;margin-top:8px}
.arow label{display:flex;align-items:center;gap:8px;color:#e8e6de;font-size:14px;cursor:pointer;margin:0}
input[type=checkbox]{accent-color:#c9a84c;width:16px;height:16px}
hr{border:none;border-top:1px solid #1e1e2e;margin:28px 0}
.note{background:#0f0f1a;border-left:2px solid #2a2a3a;padding:12px 16px;font-size:12px;color:#666;border-radius:0 6px 6px 0;margin-bottom:32px;line-height:1.6}
.note span{color:#c9a84c}
.sub{display:flex;justify-content:flex-end;margin-top:32px}
button{background:#c9a84c;color:#0a0a0f;border:none;border-radius:6px;padding:12px 32px;font-size:14px;font-weight:600;cursor:pointer;transition:opacity .2s}
button:hover{opacity:.85}
.r{color:#c9a84c}
</style></head><body>
<div class="wrap">
  <div class="hdr">
    <h1>Aureon — Workflow Design Intake</h1>
    <p>Front Office · Stage 1 of 3 · Current-state capture → Aladdin taxonomy → Governed artifact</p>
  </div>
  <div class="note"><span>Doctrine:</span> Every item entered here becomes a mapped row in the transformation risk register. Incomplete intake = unmapped gaps = late-stage delivery risk.</div>
  <form method="POST" action="/workflow/analyze">
    <div class="sec">
      <div class="lbl">Engagement</div>
      <label>Client name <span class="r">*</span></label>
      <input type="text" name="client_name" required placeholder="e.g. Meridian Capital Management">
      <label>Client type <span class="r">*</span></label>
      <select name="client_type" required>
        <option value="">— select —</option>
        <option>Pension fund</option><option>Insurance company</option><option>Asset manager</option>
        <option>Sovereign wealth fund</option><option>Endowment / foundation</option>
        <option>Family office</option><option>Bank / treasury</option>
      </select>
      <label>AUM / portfolio scale</label>
      <input type="text" name="aum" placeholder="e.g. $12B AUM across 3 mandates">
    </div>
    <hr>
    <div class="sec">
      <div class="lbl">Asset class scope (v1)</div>
      <div class="arow">
        <label><input type="checkbox" name="asset_classes" value="equities" checked> Equities</label>
        <label><input type="checkbox" name="asset_classes" value="fixed_income" checked> Fixed income</label>
        <label><input type="checkbox" name="asset_classes" value="derivatives" disabled> Derivatives (v2)</label>
        <label><input type="checkbox" name="asset_classes" value="alternatives" disabled> Alternatives (v2)</label>
      </div>
    </div>
    <hr>
    <div class="sec">
      <div class="lbl">Current operating environment</div>
      <label>Current platforms (OMS, PMS, TMS, risk systems) <span class="r">*</span></label>
      <input type="text" name="current_platforms" required placeholder="e.g. Charles River IMS, Bloomberg AIM, SimCorp Dimension">
      <label>Custodian(s)</label>
      <input type="text" name="custodians" placeholder="e.g. BNY Mellon, State Street, JPMorgan">
      <label>Data sources and interfaces</label>
      <input type="text" name="data_sources" placeholder="e.g. Bloomberg pricing, FactSet analytics, internal SQL warehouse">
    </div>
    <hr>
    <div class="sec">
      <div class="lbl">Objectives and pain points</div>
      <label>Primary transformation objectives <span class="r">*</span></label>
      <textarea name="objectives" required placeholder="What is the client trying to achieve?..."></textarea>
      <label>Stated pain points in current operating model <span class="r">*</span></label>
      <textarea name="pain_points" required placeholder="What is broken or inefficient today?..."></textarea>
    </div>
    <hr>
    <div class="sec">
      <div class="lbl">Current playbook</div>
      <label>Describe the client's current investment workflow — pre-trade through settlement and reporting. <span class="r">*</span></label>
      <textarea name="current_playbook" required style="min-height:160px" placeholder="e.g. PMs use Bloomberg AIM for order entry. Orders communicated to trading desk by email..."></textarea>
    </div>
    <hr>
    <div class="sec">
      <div class="lbl">ACT Director</div>
      <label>Your name (for audit trail)</label>
      <input type="text" name="director_name" placeholder="e.g. Bill Ravelo">
      <label>Engagement ID (auto-generated if blank)</label>
      <input type="text" name="engagement_id" placeholder="e.g. ACT-2026-014">
    </div>
    <div class="sub"><button type="submit">Run gap analysis &rarr;</button></div>
  </form>
</div></body></html>"""


    @app.route("/workflow/analyze", methods=["POST"])
    def workflow_analyze():
        from flask import request, redirect

        intake = {
            "client_name":       request.form.get("client_name", "").strip(),
            "client_type":       request.form.get("client_type", "").strip(),
            "aum":               request.form.get("aum", "").strip(),
            "asset_classes":     request.form.getlist("asset_classes"),
            "current_platforms": request.form.get("current_platforms", "").strip(),
            "custodians":        request.form.get("custodians", "").strip(),
            "data_sources":      request.form.get("data_sources", "").strip(),
            "objectives":        request.form.get("objectives", "").strip(),
            "pain_points":       request.form.get("pain_points", "").strip(),
            "current_playbook":  request.form.get("current_playbook", "").strip(),
            "director_name":     request.form.get("director_name", "ACT Director").strip(),
        }
        engagement_id = (
            request.form.get("engagement_id", "").strip()
            or f"ACT-WF-{uuid.uuid4().hex[:8].upper()}"
        )

        try:
            gap_analysis = run_gap_analysis(intake)
        except Exception as e:
            return f"<pre style='color:#e84c4c;background:#0a0a0f;padding:24px'>Gap analysis failed:\n{e}</pre>", 500

        gap_analysis["mapping_register"] = fingerprint_register(
            gap_analysis.get("mapping_register", []), engagement_id
        )
        artifact = generate_artifact(gap_analysis, intake)
        artifact["engagement_id"] = engagement_id
        artifact["director_name"] = intake["director_name"]

        conn = get_conn()
        save_artifact(conn, engagement_id, artifact)
        conn.close()

        return redirect(f"/workflow/review/{engagement_id}")


    @app.route("/workflow/review/<engagement_id>")
    def workflow_review(engagement_id):
        conn     = get_conn()
        artifact = load_artifact(conn, engagement_id)
        conn.close()
        if not artifact:
            return f"Engagement {engagement_id} not found.", 404

        rs  = artifact.get("risk_summary", {})
        reg = artifact.get("mapping_register", [])
        rc  = {"critical": "#e84c4c", "high": "#e8883a", "medium": "#c9a84c", "low": "#4cad7a"}

        rows = "".join(f"""<tr>
          <td style="color:#888;font-size:11px">{r.get("id","")}</td>
          <td style="font-size:12px;color:#aaa">{r.get("lifecycle_phase","")}</td>
          <td style="font-size:12px">{r.get("client_playbook_item","")}</td>
          <td style="font-size:12px;color:#c9a84c">{r.get("aladdin_workflow_key","")}</td>
          <td style="font-size:12px;color:#ccc">{r.get("delta","")}</td>
          <td><span style="background:{rc.get(r.get('risk_level','low'),'#888')}22;color:{rc.get(r.get('risk_level','low'),'#888')};padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600">{r.get("risk_level","").upper()}</span></td>
          <td style="font-size:12px;color:#aaa">{r.get("workstream_owner","")}</td>
        </tr>""" for r in reg)

        return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Aureon — HITL Review · {engagement_id}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0a0a0f;color:#e8e6de;padding:32px 24px}}
.wrap{{max-width:1100px;margin:0 auto}}
.hdr{{border-left:3px solid #c9a84c;padding-left:16px;margin-bottom:28px}}
.hdr h1{{font-size:20px;font-weight:500}}.hdr p{{font-size:12px;color:#666;margin-top:4px}}
.banner{{background:#1a1400;border:1px solid #c9a84c44;border-radius:8px;padding:14px 18px;margin-bottom:24px;font-size:13px;color:#c9a84c;line-height:1.6}}
.stats{{display:flex;gap:14px;margin-bottom:24px;flex-wrap:wrap}}
.stat{{background:#14141e;border:1px solid #1e1e2e;border-radius:8px;padding:14px 18px;flex:1;min-width:130px}}
.stat .n{{font-size:26px;font-weight:600}}.stat .l{{font-size:11px;color:#666;margin-top:2px;text-transform:uppercase;letter-spacing:.08em}}
.sec-lbl{{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#c9a84c;margin-bottom:10px;font-weight:500}}
table{{width:100%;border-collapse:collapse;margin-bottom:28px}}
th{{font-size:11px;color:#555;text-transform:uppercase;letter-spacing:.08em;padding:8px 10px;text-align:left;border-bottom:1px solid #1e1e2e}}
td{{padding:10px;border-bottom:1px solid #12121a;vertical-align:top}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:24px}}
.card{{background:#14141e;border:1px solid #1e1e2e;border-radius:8px;padding:14px 16px}}
.card h3{{font-size:11px;color:#c9a84c;margin-bottom:6px;font-weight:500;text-transform:uppercase;letter-spacing:.08em}}
.card p{{font-size:13px;color:#aaa;line-height:1.6}}
.clearbox{{background:#0f1a0f;border:1px solid #2a4a2a;border-radius:8px;padding:18px}}
.clearbox h3{{font-size:13px;color:#4cad7a;margin-bottom:10px}}
.clearbox input,.clearbox textarea{{width:100%;background:#0a0a0f;border:1px solid #2a3a2a;border-radius:5px;color:#e8e6de;font-size:13px;padding:9px 12px;font-family:inherit;margin-bottom:10px}}
.btn{{background:#4cad7a;color:#0a0f0a;border:none;border-radius:6px;padding:10px 26px;font-size:13px;font-weight:600;cursor:pointer}}
</style></head><body>
<div class="wrap">
  <div class="hdr">
    <h1>HITL Review — {engagement_id}</h1>
    <p>Stage 2 · Gap analysis complete · Gate: PENDING · Director must clear before artifact releases</p>
  </div>
  <div class="banner">Gate <strong>workflow_review</strong> is open. Review every row. Correct misclassifications before clearing. No artifact reaches Execution Lead or Delivery Lead until you sign off.</div>
  <div class="stats">
    <div class="stat"><div class="n">{rs.get("total_gaps",0)}</div><div class="l">Total gaps</div></div>
    <div class="stat"><div class="n" style="color:#e84c4c">{rs.get("critical",0)}</div><div class="l">Critical</div></div>
    <div class="stat"><div class="n" style="color:#e8883a">{rs.get("high",0)}</div><div class="l">High</div></div>
    <div class="stat" style="flex:2"><div class="n" style="font-size:14px;color:#ccc">{rs.get("primary_surface","See register")}</div><div class="l">Primary risk surface</div></div>
  </div>
  <div class="sec-lbl">Mapping register — 1:1 client playbook → Aladdin workflow</div>
  <table><thead><tr><th>ID</th><th>Phase</th><th>Client playbook item</th><th>Aladdin workflow</th><th>Delta</th><th>Risk</th><th>Owner</th></tr></thead>
  <tbody>{rows}</tbody></table>
  <div class="grid">
    <div class="card"><h3>Data conversion scope</h3><p>{artifact.get("data_conversion_summary","See register.")}</p></div>
    <div class="card"><h3>UAT scope</h3><p>{artifact.get("uat_scope_summary","See register.")}</p></div>
    <div class="card"><h3>Configuration required</h3><p>{artifact.get("configuration_summary","See register.")}</p></div>
    <div class="card"><h3>Operating model changes</h3><p>{artifact.get("operating_model_changes","See register.")}</p></div>
  </div>
  <div class="clearbox">
    <h3>Clear gate — workflow_review</h3>
    <form method="POST" action="/workflow/clear/{engagement_id}">
      <input type="text" name="reviewer" placeholder="Your name" required>
      <textarea name="notes" placeholder="Review notes — corrections, caveats, or confirmation register is accurate..." style="min-height:72px"></textarea>
      <button type="submit" class="btn">Clear gate &amp; generate artifact &rarr;</button>
    </form>
  </div>
</div></body></html>"""


    @app.route("/workflow/clear/<engagement_id>", methods=["POST"])
    def workflow_clear(engagement_id):
        from flask import request, redirect

        conn     = get_conn()
        artifact = load_artifact(conn, engagement_id)
        if not artifact:
            conn.close()
            return f"Engagement {engagement_id} not found.", 404

        artifact = clear_hitl_gate(
            artifact,
            request.form.get("reviewer", "Unknown").strip(),
            request.form.get("notes", "").strip()
        )
        save_artifact(conn, engagement_id, artifact)
        conn.close()
        return redirect(f"/workflow/artifact/{engagement_id}")


    @app.route("/workflow/artifact/<engagement_id>")
    def workflow_artifact(engagement_id):
        conn     = get_conn()
        artifact = load_artifact(conn, engagement_id)
        conn.close()
        if not artifact:
            return f"Engagement {engagement_id} not found.", 404

        gate = artifact.get("hitl_gate", {})
        if gate.get("status") != "cleared":
            return (f"Gate not cleared. "
                    f"<a href='/workflow/review/{engagement_id}' style='color:#c9a84c'>Return to review</a>"), 403

        reg = artifact.get("mapping_register", [])
        transformation_design = artifact.get("transformation_design", {})
        transformation_summary = transformation_design.get("transformation_summary", {})
        transformation_register = transformation_design.get("transformation_register", [])
        phases = transformation_design.get("phases", [])
        rc  = {"critical": "#e84c4c", "high": "#e8883a", "medium": "#c9a84c", "low": "#4cad7a"}

        risk_rows = "".join(f"""<tr>
          <td style="color:#888;font-size:11px">{r.get("id","")}</td>
          <td style="font-size:12px;color:#c9a84c">{r.get("aladdin_workflow_key","")}</td>
          <td style="font-size:12px;color:#ccc">{r.get("delta","")}</td>
          <td style="font-size:12px;color:#aaa">{r.get("operating_change_description","")}</td>
          <td><span style="background:{rc.get(r.get('risk_level','low'),'#888')}22;color:{rc.get(r.get('risk_level','low'),'#888')};padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600">{r.get("risk_level","").upper()}</span></td>
          <td style="font-size:12px;color:#aaa">{r.get("workstream_owner","")}</td>
        </tr>""" for r in reg)

        gap_rows = "".join(f"""<tr>
          <td style="color:#888;font-size:11px">{r.get("id","")}</td>
          <td style="font-size:12px;color:#aaa">{r.get("lifecycle_phase","")}</td>
          <td style="font-size:12px">{r.get("client_playbook_item","")}</td>
          <td style="font-size:12px;color:#c9a84c">{r.get("aladdin_workflow_key","")}</td>
          <td style="font-size:12px;color:#aaa">{r.get("operating_change_description","")}</td>
          <td><span style="background:{rc.get(r.get('risk_level','low'),'#888')}22;color:{rc.get(r.get('risk_level','low'),'#888')};padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600">{r.get("risk_level","").upper()}</span></td>
          <td style="font-size:12px;color:#aaa">{r.get("workstream_owner","")}</td>
          <td style="font-size:11px;color:#666;text-align:center">{"YES" if r.get("data_conversion_required") else "—"}</td>
          <td style="font-size:11px;color:#666;text-align:center">{"YES" if r.get("uat_scope_item") else "—"}</td>
          <td style="font-size:11px;color:#555">Wk {r.get("suggested_milestone_week","?")}</td>
        </tr>""" for r in reg)

        week_rows = "".join(f"""<tr>
          <td style="font-size:12px">{row.get("workflow_stream","")}</td>
          <td style="font-size:12px;color:#c9a84c">{row.get("phase_name","")}</td>
          <td style="font-size:12px;color:#aaa">Wk {row.get("week_start","?")}–{row.get("week_end","?")}</td>
          <td style="font-size:12px;color:#aaa">{row.get("workstream_owner","")}</td>
        </tr>""" for row in transformation_register)

        phase_sections = []
        for phase in phases:
            phase_rows = [row for row in transformation_register if row.get("phase_name") == phase.get("phase_name")]
            streams_html = "".join(
                f"<tr><td style='font-size:12px'>{stream.get('workflow_stream','')}</td><td style='font-size:12px;color:#c9a84c'>{stream.get('aladdin_module','')}</td><td style='font-size:12px;color:#aaa'>{stream.get('workstream_owner','')}</td><td style='font-size:12px;color:#aaa'>{stream.get('milestone','')}</td></tr>"
                for stream in phase_rows
            ) or "<tr><td colspan='4' style='font-size:12px;color:#666'>No streams listed for this phase.</td></tr>"
            deliverables = "".join(f"<li>{escape(str(item))}</li>" for item in phase.get("key_deliverables", []))
            phase_sections.append(f"""
              <div class="card" style="margin-bottom:14px">
                <h3>{escape(phase.get("phase_name","Unnamed phase"))}</h3>
                <p>Weeks {phase.get("week_start","?")}–{phase.get("week_end","?")} · {escape(phase.get("objectives",""))}</p>
                <div style="font-size:12px;color:#aaa;margin:10px 0 12px">Key deliverables:<ul style="margin:8px 0 0 18px">{deliverables or '<li>Not provided</li>'}</ul></div>
                <table><thead><tr><th>Stream</th><th>Module</th><th>Owner</th><th>Milestone</th></tr></thead><tbody>{streams_html}</tbody></table>
              </div>
            """)
        phase_view_html = "".join(phase_sections) or "<div class='card'><p>No phase plan generated.</p></div>"

        project_rows = "".join(f"""<tr>
          <td style="font-size:12px;color:#888">{row.get("id","")}</td>
          <td style="font-size:12px">{row.get("workflow_stream","")}</td>
          <td style="font-size:12px;color:#c9a84c">{row.get("aladdin_module","")}</td>
          <td style="font-size:12px;color:#aaa">{row.get("current_state","")}</td>
          <td style="font-size:12px;color:#aaa">{row.get("gap_description","")}</td>
          <td><span style="background:{rc.get(row.get('risk_level','low'),'#888')}22;color:{rc.get(row.get('risk_level','low'),'#888')};padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600">{row.get("risk_level","").upper()}</span></td>
          <td style="font-size:12px;color:#aaa">{row.get("operating_change","")}</td>
          <td style="font-size:12px;color:#aaa">{row.get("workstream_owner","")}</td>
          <td style="font-size:11px;color:#666;text-align:center">{'YES' if row.get('data_conversion_required') else '—'}</td>
          <td style="font-size:11px;color:#666;text-align:center">{'YES' if row.get('uat_scope_item') else '—'}</td>
          <td style="font-size:12px;color:#aaa">{row.get("phase_name","")}</td>
          <td style="font-size:11px;color:#555">Wk {row.get("week_start","?")}–{row.get("week_end","?")}</td>
          <td style="font-size:12px;color:#aaa">{row.get("milestone","")}</td>
        </tr>""" for row in transformation_register)

        return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Aureon — Artifact · {engagement_id}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0a0a0f;color:#e8e6de;padding:32px 24px}}
.wrap{{max-width:1200px;margin:0 auto}}
.hdr{{border-left:3px solid #4cad7a;padding-left:16px;margin-bottom:8px}}
.hdr h1{{font-size:20px;font-weight:500}}.hdr p{{font-size:12px;color:#666;margin-top:4px}}
.badge{{display:inline-block;background:#4cad7a22;color:#4cad7a;border:1px solid #4cad7a44;border-radius:5px;padding:4px 12px;font-size:11px;font-weight:600;letter-spacing:.08em;margin:12px 0 20px}}
.export{{display:inline-block;border:1px solid #2a2a3a;color:#888;padding:7px 16px;border-radius:5px;font-size:12px;text-decoration:none;margin-left:10px}}
.export:hover{{border-color:#c9a84c;color:#c9a84c}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:24px}}
.card{{background:#14141e;border:1px solid #1e1e2e;border-radius:8px;padding:14px 16px}}
.card h3{{font-size:11px;color:#c9a84c;margin-bottom:6px;font-weight:500;text-transform:uppercase;letter-spacing:.1em}}
.card p{{font-size:13px;color:#aaa;line-height:1.6}}
.sec-lbl{{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#c9a84c;margin-bottom:10px;font-weight:500}}
.tabs{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}}
.tab-btn{{background:#14141e;border:1px solid #1e1e2e;border-radius:6px;color:#aaa;padding:9px 14px;font-size:12px;cursor:pointer}}
.tab-btn.active{{border-color:#c9a84c;color:#c9a84c}}
.tab-panel{{margin-bottom:20px}}
table{{width:100%;border-collapse:collapse;margin-bottom:28px}}
th{{font-size:10px;color:#555;text-transform:uppercase;letter-spacing:.08em;padding:8px;text-align:left;border-bottom:1px solid #1e1e2e}}
td{{padding:9px 8px;border-bottom:1px solid #0f0f18;vertical-align:top}}
.audit{{font-size:11px;color:#444;margin-top:24px;padding-top:12px;border-top:1px solid #1a1a2a}}
</style></head><body>
<div class="wrap">
  <div class="hdr">
    <h1>Workflow Design Artifact — {engagement_id}</h1>
    <p>{artifact.get("client_name","—")} · {", ".join(artifact.get("asset_classes",[]))} · {artifact.get("generated_at","")[:10]}</p>
  </div>
  <span class="badge">GATE CLEARED · {gate.get("cleared_by","—")} · {gate.get("cleared_at","")[:10]}</span>
  <a class="export" href="/workflow/export/{engagement_id}">Export JSON &rarr;</a>
  <div class="tabs">
    <button class="tab-btn active" data-tab="risk-register">Risk register</button>
    <button class="tab-btn" data-tab="gap-register">Gap register</button>
    <button class="tab-btn" data-tab="transformation-design">Transformation design</button>
    <button class="tab-btn" data-tab="handoffs">Handoffs</button>
  </div>
  <div class="tab-panel" data-panel="risk-register">
    <div class="sec-lbl">Risk register</div>
    <table><thead><tr>
      <th>ID</th><th>Aladdin workflow</th><th>Gap</th><th>Operating change</th><th>Risk</th><th>Owner</th>
    </tr></thead><tbody>{risk_rows}</tbody></table>
  </div>
  <div class="tab-panel" data-panel="gap-register">
    <div class="sec-lbl">Gap register — 1:1 playbook → Aladdin mapping</div>
    <table><thead><tr>
      <th>ID</th><th>Phase</th><th>Client playbook</th><th>Aladdin workflow</th>
      <th>Operating change</th><th>Risk</th><th>Owner</th><th>Data conv.</th><th>UAT</th><th>Milestone</th>
    </tr></thead><tbody>{gap_rows}</tbody></table>
  </div>
  <div class="tab-panel" data-panel="transformation-design">
    <div class="grid">
      <div class="card"><h3>Total streams</h3><p>{transformation_summary.get("total_streams","—")} streams · {transformation_summary.get("total_gaps","—")} gaps</p></div>
      <div class="card"><h3>Estimated timeline</h3><p>{transformation_summary.get("estimated_weeks","—")} weeks · first stream: {transformation_summary.get("recommended_first_stream","—")}</p></div>
      <div class="card"><h3>Primary risk</h3><p>{transformation_summary.get("primary_risk","—")}</p></div>
      <div class="card"><h3>Scope summary</h3><p>{transformation_design.get("configuration_summary","—")}</p></div>
    </div>
    <div class="sec-lbl">Week view</div>
    <table><thead><tr><th>Stream</th><th>Phase</th><th>Weeks</th><th>Owner</th></tr></thead><tbody>{week_rows or "<tr><td colspan='4' style='font-size:12px;color:#666'>No transformation design available.</td></tr>"}</tbody></table>
    <div class="sec-lbl">Phase view</div>
    {phase_view_html}
    <div class="sec-lbl">Full project plan</div>
    <table><thead><tr>
      <th>ID</th><th>Stream</th><th>Module</th><th>Current state</th><th>Gap</th><th>Risk</th><th>Operating change</th><th>Owner</th><th>Data</th><th>UAT</th><th>Phase</th><th>Weeks</th><th>Milestone</th>
    </tr></thead><tbody>{project_rows or "<tr><td colspan='13' style='font-size:12px;color:#666'>No transformation design available.</td></tr>"}</tbody></table>
  </div>
  <div class="tab-panel" data-panel="handoffs">
    <div class="grid">
      <div class="card"><h3>Execution Lead handoff</h3><p>{artifact.get("handoff_to_execution_lead","—")}</p></div>
      <div class="card"><h3>Delivery Lead handoff</h3><p>{artifact.get("handoff_to_delivery_lead","—")}</p></div>
      <div class="card"><h3>Data conversion scope</h3><p>{artifact.get("data_conversion_summary","—")}</p></div>
      <div class="card"><h3>UAT scope</h3><p>{artifact.get("uat_scope_summary","—")}</p></div>
    </div>
  </div>
  <div class="audit">Artifact fingerprinted · SHA-256 per row · Gate cleared by {gate.get("cleared_by","—")} at {gate.get("cleared_at","")} · Notes: {gate.get("notes","—")}</div>
</div>
<script>
document.addEventListener("DOMContentLoaded", function () {{
  const buttons = Array.from(document.querySelectorAll(".tab-btn"));
  const panels = Array.from(document.querySelectorAll(".tab-panel"));

  function activate(tabName) {{
    buttons.forEach((button) => {{
      button.classList.toggle("active", button.dataset.tab === tabName);
    }});
    panels.forEach((panel) => {{
      panel.style.display = panel.dataset.panel === tabName ? "block" : "none";
    }});
  }}

  buttons.forEach((button) => {{
    button.addEventListener("click", function () {{
      activate(button.dataset.tab);
    }});
  }});

  activate("risk-register");
}});
</script>
</body></html>"""


    @app.route("/workflow/export/<engagement_id>")
    def workflow_export(engagement_id):
        from flask import jsonify

        conn     = get_conn()
        artifact = load_artifact(conn, engagement_id)
        conn.close()

        if not artifact:
            return jsonify({"error": "not found"}), 404
        if artifact.get("hitl_gate", {}).get("status") != "cleared":
            return jsonify({"error": "gate not cleared — artifact not released"}), 403
        return jsonify(artifact)


    @app.route("/workflow/list")
    def workflow_list():
        from flask import jsonify

        conn  = get_conn()
        items = list_artifacts(conn)
        conn.close()
        return jsonify(items)
