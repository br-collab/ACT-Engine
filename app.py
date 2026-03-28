"""
Aureon Engine — Unified Flask Application
One router. Two practices. Same doctrine.
Onboarding Intelligence Platform + ACT Transformation Engine.
"""

import sys
import json
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, render_template, request, jsonify, redirect, url_for
from core.db import init_db, get_case, get_portfolio, save_mappings, get_conn, ts
from core.taxonomy import get_dictionary, extract_fields, run_mapping
from core.gates import act_on_gate, get_gates, open_gate
from core.audit import log

BASE = Path(__file__).parent
app  = Flask(__name__,
             template_folder=str(BASE / "templates"),
             static_folder=str(BASE / "static"))
app.config["UPLOAD_FOLDER"] = str(BASE / "uploads")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

Path(app.config["UPLOAD_FOLDER"]).mkdir(exist_ok=True)
init_db()


# ══════════════════════════════════════════════════════════════════════
# PAGE ROUTES
# ══════════════════════════════════════════════════════════════════════

@app.route("/")
def brief():
    return render_template("brief.html")


@app.route("/brief")
def brief_legacy():
    return redirect(url_for("brief"))


@app.route("/portfolio")
def index():
    portfolio = get_portfolio()
    transformation = [c for c in portfolio if c["practice"] == "transformation"]
    onboarding     = [c for c in portfolio if c["practice"] == "onboarding"]
    return render_template("index.html",
                           transformation=transformation,
                           onboarding=onboarding,
                           all_cases=portfolio)


@app.route("/case/<case_id>")
def case_view(case_id):
    data = get_case(case_id)
    if not data:
        return redirect(url_for("index"))
    return render_template("case.html", case=data)


@app.route("/mapper")
def mapper():
    case_id  = request.args.get("case_id", "ACT-001")
    practice = request.args.get("practice", "aladdin")
    data     = get_case(case_id)
    all_cases = get_portfolio()
    return render_template("mapper.html",
                           case=data,
                           all_cases=all_cases,
                           practice=practice)


@app.route("/audit")
def audit_view():
    practice = request.args.get("practice")
    all_cases = get_portfolio()
    return render_template("audit.html",
                           all_cases=all_cases,
                           practice=practice)


# ══════════════════════════════════════════════════════════════════════
# API — PORTFOLIO
# ══════════════════════════════════════════════════════════════════════

@app.route("/api/portfolio")
def api_portfolio():
    practice = request.args.get("practice")
    return jsonify(get_portfolio(practice))


@app.route("/api/case/<case_id>")
def api_case(case_id):
    return jsonify(get_case(case_id))


# ══════════════════════════════════════════════════════════════════════
# API — HITL GATES
# ══════════════════════════════════════════════════════════════════════

@app.route("/api/gates/<case_id>")
def api_gates(case_id):
    return jsonify(get_gates(case_id))


@app.route("/api/gate/action", methods=["POST"])
def api_gate_action():
    body     = request.get_json() or {}
    case_id  = body.get("case_id")
    gate_id  = body.get("gate_id")
    action   = body.get("action")
    actor    = body.get("actor", "Director — B. Ravelo")
    rationale= body.get("rationale", "")
    practice = body.get("practice", "transformation")

    if not all([case_id, gate_id, action]):
        return jsonify({"error": "case_id, gate_id, and action required"}), 400

    result = act_on_gate(case_id, practice, gate_id, action, actor, rationale)
    return jsonify(result)


# ══════════════════════════════════════════════════════════════════════
# API — TAXONOMY MAPPING
# ══════════════════════════════════════════════════════════════════════

@app.route("/api/map/text", methods=["POST"])
def api_map_text():
    body     = request.get_json() or {}
    text     = body.get("text", "")
    practice = body.get("practice", "aladdin")
    case_id  = body.get("case_id")
    taxonomy = get_dictionary(practice)
    fields   = extract_fields(text)
    if not fields:
        fields = [f.strip() for f in text.split("\n") if f.strip()]
    result = run_mapping(fields, taxonomy)
    if case_id:
        save_mappings(case_id, practice, result)
        log(case_id, "transformation",
            f"Taxonomy mapping — {result['pct_automated']}% auto-mapped",
            "System",
            f"{result['auto']} auto / {result['review']} review / {result['no_match']} no match",
            "SYSTEM")
        if result["hitl_required"]:
            open_gate(case_id, "transformation", "HITL-3",
                      "Taxonomy confidence review",
                      "Delivery lead", "L2", False,
                      f"{result['review']} fields below confidence threshold require human review.")
    return jsonify(result)


@app.route("/api/map/upload", methods=["POST"])
def api_map_upload():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f        = request.files["file"]
    practice = request.form.get("practice", "aladdin")
    case_id  = request.form.get("case_id", "ACT-001")
    ext      = Path(f.filename).suffix.lower()
    if ext not in (".pdf", ".docx", ".txt", ".csv"):
        return jsonify({"error": "Unsupported file type"}), 400

    fname = f"{uuid.uuid4().hex}{ext}"
    fpath = Path(app.config["UPLOAD_FOLDER"]) / fname
    f.save(fpath)

    text = ""
    try:
        if ext == ".docx":
            from docx import Document
            doc = Document(str(fpath))
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        elif ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(fpath))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        else:
            text = fpath.read_text(errors="ignore")
    finally:
        fpath.unlink(missing_ok=True)

    taxonomy = get_dictionary(practice)
    fields   = extract_fields(text)
    result   = run_mapping(fields, taxonomy)
    result["source_file"] = f.filename
    save_mappings(case_id, "transformation", result)
    log(case_id, "transformation",
        f"Document ingested — {f.filename}",
        "System",
        f"{len(fields)} fields extracted. {result['pct_automated']}% auto-mapped.",
        "SYSTEM")
    return jsonify(result)


# ══════════════════════════════════════════════════════════════════════
# API — AUDIT LOG
# ══════════════════════════════════════════════════════════════════════

@app.route("/api/audit/<case_id>")
def api_audit(case_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM audit_log WHERE case_id=? ORDER BY id DESC LIMIT 100",
        (case_id,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/audit/practice/<practice>")
def api_audit_practice(practice):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM audit_log WHERE practice=? ORDER BY id DESC LIMIT 200",
        (practice,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ══════════════════════════════════════════════════════════════════════
# API — WEEKLY DIGEST
# ══════════════════════════════════════════════════════════════════════

@app.route("/api/digest/<case_id>")
def api_digest(case_id):
    data = get_case(case_id)
    if not data:
        return jsonify({"error": "Case not found"}), 404
    ws      = data["workstreams"]
    rs      = data["risks"]
    gates   = data["gates"]
    overall = data["overall_pct"]
    on_track= sum(1 for w in ws if w["status"] == "on_track")
    blocking= [g for g in gates if g["status"] == "open" and g["blocking"]]
    return jsonify({
        "subject":  f"[Aureon] Weekly status — {data['name']} — Week {data.get('week','')}",
        "summary":  f"{data['client']} is {overall}% complete. "
                    f"{on_track}/{len(ws)} workstreams on track. "
                    f"{len(rs)} open risk(s). {len(blocking)} blocking gate(s).",
        "workstreams": [{"name":w["name"],"progress":w["progress"],"status":w["status"]} for w in ws],
        "risks":    [{"title":r["title"],"severity":r["severity"]} for r in rs],
        "blocking_gates": [{"gate_id":g["gate_id"],"label":g["label"]} for g in blocking],
        "week":     data.get("week"),
        "practice": data["practice"],
    })


# ══════════════════════════════════════════════════════════════════════
# API — CHATBOT
# ══════════════════════════════════════════════════════════════════════

@app.route("/api/chat", methods=["POST"])
def api_chat():
    body    = request.get_json() or {}
    msg     = body.get("message", "")
    case_id = body.get("case_id", "ACT-001")
    data    = get_case(case_id)
    context = json.dumps({
        "case":       {k:v for k,v in data.items()
                       if k not in ("audit","mappings")},
        "open_gates": [g for g in data.get("gates",[]) if g["status"]=="open"],
        "risks":      data.get("risks",[]),
    }, indent=2)

    practice_label = "Aladdin Client Transformations" if data.get("practice") == "transformation" \
                     else "Institutional Onboarding"

    system = f"""You are the Aureon Engine assistant supporting the {practice_label} team.
You have full real-time visibility into this case. Be direct, concise, and think like
a Director-level delivery executive. Answer in 2-4 sentences unless a list is better.
Current case state:
{context}"""

    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=400,
            system=system,
            messages=[{"role": "user", "content": msg}]
        )
        answer = resp.content[0].text
    except Exception as e:
        answer = (f"[Chatbot connects to Claude API in production. "
                  f"Set ANTHROPIC_API_KEY to activate. Error: {str(e)[:60]}]")

    return jsonify({"response": answer, "case_id": case_id})


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "engine": "Aureon v1.0", "practices": ["transformation","onboarding"]})


if __name__ == "__main__":
    print("\n  Aureon Engine — unified platform")
    print("  Practices: ACT Transformation + Onboarding Intelligence")
    print("  http://localhost:5055\n")
    app.run(debug=True, port=5055)
