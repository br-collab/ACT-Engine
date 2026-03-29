# Aureon Engine v1.1 — Institutional Governance Platform

One engine. Three practices. Same doctrine.

**ACT Transformation** — Engagement governance, HITL gates, weekly digest, audit trail.

**Onboarding Intelligence** — Document classification, completeness scoring, KYC/AML governance, platform activation.

**Workflow Design** — 1:1 client playbook → Aladdin taxonomy mapping, transformation risk register, governed artifact generation.

---

## Purpose

Aureon is the intelligence layer that makes the ACT (Aladdin Client Transformation) practice operate better. It is not client-facing. It reduces transformation risk by forcing completeness at intake — every client playbook item must be mapped 1:1 to an Aladdin workflow equivalent before any governance gate can open.

**Doctrine:** Intake → Workflow Design → HITL Gate → Governance → Audit → Activation

Every case runs through the same model. Unmapped gaps are transformation risk. Aureon eliminates late-stage surprises by surfacing them at the beginning of the engagement.

---

## Repository structure

```
aureon/
  app.py                    <- Unified Flask router (17 core routes + 7 workflow = 24 total)
  workflow_design.py        <- Workflow Design Module (taxonomy engine, HITL gate, DB persistence)
  vercel.json               <- Vercel deployment config
  requirements.txt          <- Python dependencies
  .gitignore
  core/
    __init__.py
    audit.py                <- Decision System of Record (immutable, SHA-256 fingerprinted)
    gates.py                <- HITL gate framework (open/pending/cleared/escalated)
    completeness.py         <- Scoring engine (shared thresholds)
    taxonomy.py             <- Field translation (4 practice dictionaries)
    db.py                   <- SQLite layer (single DB, practice-partitioned)
  templates/
    base.html               <- Shared nav + design system
    index.html              <- Unified portfolio view
    case.html               <- Case detail (transformation + onboarding)
    mapper.html             <- Taxonomy mapping UI
    audit.html              <- Decision System of Record viewer
  data/
    .gitkeep                <- aureon.db auto-created on first run (not committed)
  uploads/
    .gitkeep                <- Transient upload storage (not committed)
```

---

## Route map (24 total)

### Core page routes (6)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/` | Executive brief |
| GET | `/brief` | Redirect to `/` |
| GET | `/portfolio` | Unified portfolio — all cases |
| GET | `/case/<case_id>` | Case detail view |
| GET | `/mapper` | Taxonomy mapping UI |
| GET | `/audit` | Decision System of Record viewer |

### API — portfolio (2)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/portfolio` | All cases, optional `?practice=` filter |
| GET | `/api/case/<case_id>` | Single case data |

### API — HITL gates (2)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/gates/<case_id>` | Gate status for a case |
| POST | `/api/gate/action` | Open / clear / escalate a gate |

### API — taxonomy mapping (2)

| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/map/text` | Map pasted text against a practice dictionary |
| POST | `/api/map/upload` | Upload document (PDF/DOCX/TXT/CSV) for mapping |

### API — audit (2)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/audit/<case_id>` | Audit log for a case (last 100 entries) |
| GET | `/api/audit/practice/<practice>` | Audit log for a practice (last 200 entries) |

### API — digest, chatbot, health (3)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/digest/<case_id>` | Weekly status digest |
| POST | `/api/chat` | Claude-powered case assistant |
| GET | `/api/health` | Engine health check |

### Workflow Design Module (7)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/workflow/new` | Stage 1 — intake form (Front Office Director) |
| POST | `/workflow/analyze` | Stage 2 — Claude gap analysis, fingerprint, DB persist |
| GET | `/workflow/review/<id>` | Stage 2 — HITL review screen (gate: pending) |
| POST | `/workflow/clear/<id>` | Stage 2 — HITL gate clearance (gate: cleared) |
| GET | `/workflow/artifact/<id>` | Stage 3 — governed artifact (403 if gate not cleared) |
| GET | `/workflow/export/<id>` | Stage 3 — JSON export to Execution Lead / Delivery Lead |
| GET | `/workflow/list` | Portfolio — all workflow design engagements |

---

## Workflow Design Module

### The problem it solves

Every ACT engagement starts with a translation problem. The client has a playbook — how they run their investment operations today. Aladdin has specific workflows, configurations, and operating model requirements. The gap between those two is where transformation risk lives. Currently that gap is mapped manually, inconsistently, by whoever is in the room, into whatever format they prefer.

### What it builds

An initial taxonomy base: a structured 1:1 mapping of the client's current playbook to Aladdin-specific workflows and the operating changes required to close each gap. This mapping becomes the risk register, UAT scope, data conversion scope, and project plan — all from one governed intake. One register. Four views.

### The atomic row

```
client playbook item
  -> Aladdin workflow key
  -> delta (gap description)
  -> operating change type
  -> risk level (critical / high / medium / low)
  -> workstream owner (Front Office / Execution Lead / Delivery Lead / Technology / Client)
  -> suggested milestone week
```

### Three-stage pipeline

```
Stage 1 — Intake (/workflow/new)
  Front Office Director runs this form during client working session with CIO/COO.
  Captures: client type, asset classes, existing platforms, custodians,
  objectives, pain points, and current playbook narrative.

Stage 2 — Gap analysis + HITL gate (/workflow/analyze -> /workflow/review -> /workflow/clear)
  Claude maps intake against Aladdin EQ dictionary (14 keys) and FI dictionary (19 keys).
  Every register row receives a SHA-256 fingerprint (engagement_id + row_id + delta + risk + ts).
  Artifact is persisted to aureon.db (workflow_artifacts table) — NOT flask.session.
  HITL gate workflow_review opens with status: pending.
  Director reviews register on the review screen. Corrects any misclassifications.
  Director clears the gate — human fingerprint applied, status: cleared.

Stage 3 — Governed artifact (/workflow/artifact -> /workflow/export)
  Artifact view returns 403 if gate is not cleared.
  JSON export routes structured output to Execution Lead (project plan view)
  and Delivery Lead (standardization opportunities view).
  Audit trail closed.
```

### Asset class dictionaries (v1 scope)

**Equities — 14 keys:**
portfolio_construction, order_management, pre_trade_compliance, execution_algo_routing,
trade_capture, allocation, affirmation_matching, settlement_instruction, custodian_recon,
corporate_actions, performance_attribution, compliance_monitoring, regulatory_reporting,
client_reporting

**Fixed income — 19 keys:**
abor, ibor, abor_ibor_reconciliation, duration_analytics, yield_curve_mapping, credit_risk,
pre_trade_compliance_fi, order_management_fi, trade_date_matching, settlement_fi,
accrual_engine, amortization, income_recognition, fx_hedge_accounting, custodian_recon_fi,
data_conversion_fi, dsor, risk_reporting, performance_attribution_fi

**v2 scope (not yet built):** derivatives, alternatives

### Storage

Artifacts persist to `aureon.db` in the `workflow_artifacts` table. Table is auto-created on first use via `_ensure_table()`. No flask.session dependency. Production-safe: survives Vercel cold starts and multi-worker deploys.

### Wiring

The module registers itself onto the existing app with two lines in `app.py`:

```python
from workflow_design import register_workflow_routes
register_workflow_routes(app, get_conn)
```

`get_conn` is passed as a callable. Each route opens and closes its own connection.

---

## Local setup

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/aureon-engine.git
cd aureon-engine

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run
python app.py
# -> http://localhost:5055

# 4. Enable AI features (gap analysis + chatbot — required for workflow design)
export ANTHROPIC_API_KEY=your_key_here
python app.py
```

`data/aureon.db` is auto-created and seeded with five demo cases on first run.
`workflow_artifacts` table is created on first workflow intake submission.
No manual DB setup required.

Validate boot:
```
GET http://localhost:5055/api/health
-> {"engine":"Aureon v1.1","practices":["transformation","onboarding","workflow_design"],"routes":24,"status":"ok"}
```

---

## Deploy to Vercel

```bash
# 1. Install Vercel CLI
npm install -g vercel

# 2. From repo root
vercel

# 3. Set environment variable (required for gap analysis and chatbot)
vercel env add ANTHROPIC_API_KEY

# 4. Deploy to production
vercel --prod
```

**Persistence note:** Vercel is serverless. SQLite writes to `/tmp` and resets between cold starts. Demo cases re-seed automatically. Workflow artifacts are empty after a cold start. For production persistence with live engagement data, connect PostgreSQL via `DATABASE_URL` environment variable.

---

## Demo cases (auto-seeded)

| ID | Practice | Scenario | Status |
|----|----------|----------|--------|
| ACT-001 | Transformation | Meridian Capital — Aladdin — Wk 14/32 | 1 blocking gate |
| ACT-002 | Transformation | Atlas Pension — Aladdin — Wk 6/40 | On track |
| ACT-003 | Transformation | Sovereign Wealth DR — Federal taxonomy | Early stage |
| OB-001 | Onboarding | Thornfield Capital — Exception path | 2 blocking gates |
| OB-002 | Onboarding | Meridian AM — Happy path | Gate 6 pending RM |

Workflow design engagements are created live via `/workflow/new`. No demo seeding.

---

## Practice dictionaries (core taxonomy module)

```python
from core.taxonomy import get_dictionary

taxonomy = get_dictionary("aladdin")        # BlackRock Aladdin
taxonomy = get_dictionary("simcorp")        # SimCorp Dimension
taxonomy = get_dictionary("charles_river")  # Charles River IMS
taxonomy = get_dictionary("federal")        # Federal / OMB
```

The workflow design module uses its own asset-class dictionaries (`ALADDIN_EQ`, `ALADDIN_FI`) defined in `workflow_design.py`.

---

## Phased activation plan

| Phase | Name | Primary target |
|-------|------|----------------|
| 0 | Packaging validation | Structure, imports, DB paths |
| 1 | Local boot validation | /api/health, portfolio, gates, audit |
| 2 | Internal demo | Seeded data. Chatbot off unless key set. |
| 3 | Controlled pilot | One case. HITL gates + audit log = primary targets. |
| 4 | Workflow Design MVP | /workflow/new through /workflow/artifact — one live engagement. |
| 5 | Limited operational | Upload + mapping. Daily DB integrity check. |
| 6 | Broader activation | Live workflows, chatbot, notifications layer. |

---

## What Aureon is not

- **Not client-facing.** Clients experience the output of Aureon-governed delivery, not the tool itself.
- **Not competing with Aladdin Copilot.** Aladdin Copilot operates post-go-live inside the Aladdin platform. Aureon operates pre-go-live inside the ACT delivery machine.
- **Not a project management tool.** Smartsheet, Jira, ServiceNow, and Aha! each carry their own taxonomy. Aureon is the unified taxonomy base that those fragmented tools lack.

---

## Built by

Guillermo "Bill" Ravelo — Principal Consultant, Ravelo Strategic Solutions
Columbia University M.S. Technology Management — Project Aureon ecosystem
