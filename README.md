# Aureon Engine — Institutional Governance Platform

One engine. Two practices. Same doctrine.

**ACT Transformation** — Taxonomy translation, engagement governance, HITL gates, weekly digest, audit trail.

**Onboarding Intelligence** — Document classification, completeness scoring, KYC/AML governance, platform activation.

---

## Repository structure

```
aureon/
  app.py                  ← Unified Flask router (16 routes)
  vercel.json             ← Vercel deployment config
  requirements.txt        ← Python dependencies
  .gitignore
  core/
    __init__.py
    audit.py              ← Decision System of Record — immutable, fingerprinted
    gates.py              ← HITL gate framework — open/pending/cleared/escalated
    completeness.py       ← Scoring engine — shared thresholds
    taxonomy.py           ← Field translation — 4 practice dictionaries
    db.py                 ← SQLite layer — single DB, practice-partitioned
  templates/
    base.html             ← Shared nav + design system
    index.html            ← Unified portfolio view
    case.html             ← Case detail (both practices)
    mapper.html           ← Taxonomy mapping UI
    audit.html            ← Decision System of Record viewer
  data/
    .gitkeep              ← aureon.db auto-created here on first run (not committed)
  uploads/
    .gitkeep              ← Transient upload storage (not committed)
```

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
# → http://localhost:5055

# 4. Optional — enable chatbot
export ANTHROPIC_API_KEY=your_key_here
python app.py
```

Database (data/aureon.db) is auto-created and seeded with five demo cases on first run. No manual setup required.

Validate boot:
  GET http://localhost:5055/api/health
  → {"engine": "Aureon v1.0", "practices": ["transformation", "onboarding"], "status": "ok"}

---

## Deploy to Vercel

```bash
# 1. Install Vercel CLI
npm install -g vercel

# 2. From repo root
vercel

# 3. Set environment variable (optional — activates chatbot)
vercel env add ANTHROPIC_API_KEY

# 4. Deploy to production
vercel --prod
```

Vercel note on persistence: Vercel is a serverless environment. SQLite writes to /tmp and reset between cold starts. The demo data re-seeds automatically on each cold start, so the app works correctly for demonstration purposes. For production persistence with live client data, connect a PostgreSQL database via DATABASE_URL environment variable.

---

## Demo cases (auto-seeded)

| ID      | Practice       | Scenario                              | Status             |
|---------|----------------|---------------------------------------|--------------------|
| ACT-001 | Transformation | Meridian Capital — Aladdin — Wk 14/32 | 1 blocking gate    |
| ACT-002 | Transformation | Atlas Pension — Aladdin — Wk 6/40     | On track           |
| ACT-003 | Transformation | Sovereign Wealth DR — Federal taxonomy| Early stage        |
| OB-001  | Onboarding     | Thornfield Capital — Exception path   | 2 blocking gates   |
| OB-002  | Onboarding     | Meridian AM — Happy path              | Gate 6 pending RM  |

---

## Practice dictionaries

```python
from core.taxonomy import get_dictionary

taxonomy = get_dictionary("aladdin")       # BlackRock Aladdin
taxonomy = get_dictionary("simcorp")       # SimCorp Dimension
taxonomy = get_dictionary("charles_river") # Charles River IMS
taxonomy = get_dictionary("federal")       # Federal / OMB
```

---

## Phased activation plan

| Phase | Name                   | Primary target                                      |
|-------|------------------------|-----------------------------------------------------|
| 0     | Packaging validation   | Structure, imports, DB paths                        |
| 1     | Local boot validation  | /api/health, portfolio, gates, audit                |
| 2     | Internal demo          | Seeded data only. Chatbot off unless key set.       |
| 3     | Controlled pilot       | One case. HITL gates + audit log = primary targets. |
| 4     | Limited operational    | Upload + mapping. Daily DB integrity check.         |
| 5     | Broader activation     | Live workflows, chatbot, external-facing.           |

---

## Four-layer doctrine

Intake → Governance → Audit → Activation

Every case runs through the same model. Only the taxonomy dictionary and gate configuration change between practices.

---

## Built by

Guillermo "Bill" Ravelo — Principal Consultant, Ravelo Strategic Solutions
Columbia University M.S. Technology Management — Project Aureon ecosystem
