"""
UniAssist Flask Web Server & REST API (app.py)
Serves the Student/Applicant Helpdesk UI (information-only by default) and
passcode-protected Staff/Admin Portal (Circular Ingestion, Escalation Tickets,
and Benchmark & Diagnostics).
"""

from __future__ import annotations

import functools
import json
import os
import secrets
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session
from werkzeug.utils import secure_filename

from benchmark_suite import run_benchmark
from estimator_engine import HOSTEL_PLANS, PROGRAM_NORMS, estimate_eligibility_and_fee
from helpdesk_service import HelpdeskService, TicketStore
from policy_loader import extract_text_from_file, load_policy_corpus, parse_policy_text
from retrieval_engine import RetrievalEngine

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CHUNKS_PATH = DATA_DIR / "policy_chunks.json"
TICKETS_PATH = DATA_DIR / "tickets.json"

load_dotenv(BASE_DIR / ".env")

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(24)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB upload limit

ADMIN_PASSCODE = os.environ.get("ADMIN_PASSCODE", "admin123")

# Initialize 5-stage RAG Pipeline at startup
sections = load_policy_corpus(DATA_DIR, export_json_path=CHUNKS_PATH)
retrieval_engine = RetrievalEngine(
    sections=sections,
    role_boost_factor=1.15,
    confidence_tau=0.15,
    top_k=3,
)
ticket_store = TicketStore(TICKETS_PATH)
helpdesk_service = HelpdeskService(retrieval_engine, ticket_store)


def _is_admin() -> bool:
    return bool(session.get("is_admin"))


def admin_required(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not _is_admin():
            return jsonify({"error": "Staff / Admin authentication required."}), 401
        return fn(*args, **kwargs)

    return wrapper


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json(silent=True) or {}
    passcode = (data.get("passcode") or "").strip()
    if passcode == ADMIN_PASSCODE:
        session["is_admin"] = True
        return jsonify({"authenticated": True})
    return jsonify({"authenticated": False, "error": "Invalid staff passcode."}), 401


@app.route("/api/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("is_admin", None)
    return jsonify({"authenticated": False})


@app.route("/api/health", methods=["GET"])
def health():
    is_admin = _is_admin()
    payload = {
        "status": "ok",
        "app": "UniAssist Policy-Grounded RAG Helpdesk",
        "is_admin": is_admin,
        "corpus_sections": len(retrieval_engine.sections),
        "programs": list(PROGRAM_NORMS.keys()),
        "hostel_plans": list(HOSTEL_PLANS.keys()),
    }
    if is_admin:
        dept_counts = {}
        for sec in retrieval_engine.sections:
            dept_counts[sec.department] = dept_counts.get(sec.department, 0) + 1
        payload.update(
            {
                "departments": dept_counts,
                "indexing_ms": retrieval_engine.indexing_ms,
                "tau": retrieval_engine.confidence_tau,
                "role_boost": retrieval_engine.role_boost_factor,
                "gemini_configured": bool((os.environ.get("GEMINI_API_KEY") or "").strip()),
                "open_tickets": sum(
                    1 for t in ticket_store.list_tickets() if t["status"] == "Open"
                ),
            }
        )
    return jsonify(payload)


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()
    role = (data.get("role") or "applicant").strip().lower()
    is_admin = _is_admin()

    # Only staff/admin can force offline simulation or supply a custom API key override
    force_offline = bool(data.get("force_offline", False)) if is_admin else False
    api_key_override: Optional[str] = (
        ((data.get("api_key") or "").strip() or None) if is_admin else None
    )

    if not query:
        return jsonify({"error": "Please enter a valid question."}), 400

    result = helpdesk_service.answer_query(
        query=query,
        user_role=role,
        force_offline=force_offline,
        api_key_override=api_key_override,
    )

    # For regular students/applicants, return clean informational data without internal RAG debug traces
    if not is_admin:
        # Keep top_clauses content only so citation modals work when clicked
        citation_lookup = {
            c["policy_id"]: {
                "policy_id": c["policy_id"],
                "department": c["department"],
                "target_role": c["target_role"],
                "title": c["title"],
                "content_text": c["content_text"],
                "source_file": c["source_file"],
            }
            for c in result.get("top_clauses", [])
        }
        student_citations = [
            {
                "policy_id": c["policy_id"],
                "title": c["title"],
                "department": c["department"],
                "target_role": c["target_role"],
            }
            for c in result.get("citations", [])
        ]
        student_ticket = None
        if result.get("escalation_ticket"):
            t = result["escalation_ticket"]
            student_ticket = {
                "ticket_id": t["ticket_id"],
                "routed_desk": t["routed_desk"],
                "status": t["status"],
            }
            student_answer = (
                "I could not find an official university circular covering your question. "
                "To avoid providing inaccurate information, I have forwarded your query to a university counselor.\n\n"
                f"**Support Ticket Created:** `#{t['ticket_id']}`\n"
                f"**Assigned Office:** {t['routed_desk']}"
            )
        else:
            student_answer = result["answer"]

        return jsonify(
            {
                "answer": student_answer,
                "inferred_intent": result["inferred_intent"],
                "user_role": result["user_role"],
                "is_out_of_scope": result["is_out_of_scope"],
                "citations": student_citations,
                "citation_details": citation_lookup,
                "escalation_ticket": student_ticket,
            }
        )

    return jsonify(result)


@app.route("/api/estimate", methods=["POST"])
def estimate():
    data = request.get_json(silent=True) or {}
    program = data.get("program", "MCA")
    try:
        percentage = float(data.get("percentage", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid percentage value."}), 400

    entrance_exam = data.get("entrance_exam", "PGCET")
    category = data.get("category", "General")
    has_math = bool(data.get("has_math", True))
    hostel_plan = data.get("hostel_plan", "None")
    raw_rank = data.get("entrance_rank")
    entrance_rank = None
    if raw_rank not in (None, "", 0, "0"):
        try:
            entrance_rank = int(raw_rank)
        except (TypeError, ValueError):
            entrance_rank = None

    try:
        result = estimate_eligibility_and_fee(
            program=program,
            percentage=percentage,
            entrance_exam=entrance_exam,
            category=category,
            has_math=has_math,
            hostel_plan=hostel_plan,
            entrance_rank=entrance_rank,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(result.to_dict())


@app.route("/api/policies", methods=["GET"])
def get_policies():
    dept = (request.args.get("department") or "").strip().upper()
    role = (request.args.get("role") or "").strip().lower()
    search = (request.args.get("q") or "").strip().lower()

    items = []
    for sec in retrieval_engine.sections:
        if dept and dept != "ALL" and sec.department != dept:
            continue
        if role and role != "all" and sec.target_role != role:
            continue
        if search and (
            search not in sec.policy_id.lower()
            and search not in sec.title.lower()
            and search not in sec.content_text.lower()
        ):
            continue
        items.append(sec.to_dict())

    return jsonify(
        {
            "total": len(retrieval_engine.sections),
            "filtered": len(items),
            "policies": items,
        }
    )


@app.route("/api/policies/ingest", methods=["POST"])
@admin_required
def ingest_policy():
    """Admin-only: Ingests a new .txt, .md, or .pdf circular into the live vector index."""
    new_sections = []
    source_name = "custom_circular.txt"

    if "file" in request.files and request.files["file"].filename:
        uploaded = request.files["file"]
        filename = secure_filename(uploaded.filename)
        ext = Path(filename).suffix.lower()
        if ext not in {".txt", ".md", ".pdf"}:
            return jsonify({"error": "Only .txt, .md, and .pdf files are supported."}), 400
        save_path = DATA_DIR / filename
        uploaded.save(str(save_path))
        source_name = filename
        raw_text = extract_text_from_file(save_path)
        default_dept = request.form.get("department", "ADMISSIONS")
        default_role = request.form.get("target_role", "both")
        new_sections = parse_policy_text(
            raw_text,
            source_file=source_name,
            default_department=default_dept,
            default_role=default_role,
        )
    else:
        data = request.get_json(silent=True) or {}
        raw_text = (data.get("raw_text") or "").strip()
        if not raw_text:
            return jsonify({"error": "Provide a policy file or circular text to ingest."}), 400
        default_dept = data.get("department", "ADMISSIONS")
        default_role = data.get("target_role", "both")
        title = (data.get("title") or "").strip()
        policy_id = (data.get("policy_id") or "").strip()
        if policy_id and title and "=== SECTION:" not in raw_text:
            raw_text = (
                f"=== SECTION: {policy_id} | DEPT: {default_dept} | "
                f"ROLE: {default_role} | TITLE: {title} ===\n{raw_text}"
            )
        new_sections = parse_policy_text(
            raw_text,
            source_file="live_portal_circular.txt",
            default_department=default_dept,
            default_role=default_role,
        )

    if not new_sections:
        return jsonify({"error": "No valid policy sections could be extracted."}), 400

    indexing_ms = retrieval_engine.add_sections(new_sections)
    CHUNKS_PATH.write_text(
        json.dumps([s.to_dict() for s in retrieval_engine.sections], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return jsonify(
        {
            "ingested_count": len(new_sections),
            "total_sections": len(retrieval_engine.sections),
            "indexing_ms": indexing_ms,
            "ingested_ids": [s.policy_id for s in new_sections],
        }
    )


@app.route("/api/tickets", methods=["GET"])
@admin_required
def list_tickets():
    return jsonify({"tickets": ticket_store.list_tickets()})


@app.route("/api/tickets/<ticket_id>", methods=["PATCH"])
@admin_required
def update_ticket(ticket_id: str):
    data = request.get_json(silent=True) or {}
    status = (data.get("status") or "").strip()
    if status not in {"Open", "In Review", "Resolved"}:
        return jsonify({"error": "Status must be Open, In Review, or Resolved."}), 400
    updated = ticket_store.update_status(ticket_id, status)
    if updated is None:
        return jsonify({"error": "Ticket not found."}), 404
    return jsonify({"ticket": updated})


@app.route("/api/benchmark", methods=["GET"])
@app.route("/api/benchmark/run", methods=["POST"])
@admin_required
def benchmark():
    report = run_benchmark(retrieval_engine)
    return jsonify(report)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5050"))
    print(f"UniAssist indexed {len(retrieval_engine.sections)} sections in {retrieval_engine.indexing_ms} ms.")
    app.run(host="0.0.0.0", port=port, debug=False)
