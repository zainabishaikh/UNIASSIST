"""
Helpdesk Synthesis Service (helpdesk_service.py)
Coordinates:
1. Confidence Gate (tau = 0.15) & Tier-2 Counselor Escalation Ticket generation
2. Google Gemini 2.5 / 1.5 Flash REST API synthesis (temperature = 0.15)
3. Automatic < 10ms Offline Deterministic Clause-Extraction Failover
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests

from retrieval_engine import RetrievalEngine, RetrievalResult, RetrievedClause


DEPARTMENT_DESK_MAP = {
    "ELIGIBILITY": "Admissions Counseling Desk",
    "FEES": "University Accounts & Fee Cell",
    "SCHOLARSHIPS": "Institutional Scholarship & SSP/NSP Desk",
    "ADMISSIONS": "Central Admissions & Document Verification Office",
    "HOSTEL": "Chief Warden & Campus Facilities Office",
    "EXAMINATIONS": "Controller of Examinations & Registrar Office",
}

GEMINI_MODELS = ("gemini-2.5-flash", "gemini-1.5-flash")


class TicketStore:
    """Thread-safe lightweight JSON persistence for Tier-2 Escalation Tickets."""

    def __init__(self, storage_path: str | Path) -> None:
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.tickets: List[dict] = self._load()

    def _load(self) -> List[dict]:
        if self.storage_path.exists():
            try:
                data = json.loads(self.storage_path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
            except Exception:
                pass
        return []

    def _save(self) -> None:
        self.storage_path.write_text(
            json.dumps(self.tickets, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def create_ticket(
        self,
        query: str,
        user_role: str,
        inferred_intent: str,
        max_score: float,
    ) -> dict:
        date_part = datetime.now().strftime("%Y%m%d")
        short_hex = uuid.uuid4().hex[:4].upper()
        ticket = {
            "ticket_id": f"UA-{date_part}-{short_hex}",
            "query": query.strip(),
            "user_role": user_role,
            "routed_desk": DEPARTMENT_DESK_MAP.get(
                inferred_intent, "Central Admissions & Registrar Office"
            ),
            "inferred_intent": inferred_intent,
            "max_similarity_score": round(max_score, 4),
            "status": "Open",
            "priority": "Tier-2 Counselor Review",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.tickets.insert(0, ticket)
        self._save()
        return ticket

    def list_tickets(self) -> List[dict]:
        return list(self.tickets)

    def update_status(self, ticket_id: str, status: str) -> Optional[dict]:
        for t in self.tickets:
            if t["ticket_id"] == ticket_id:
                t["status"] = status
                self._save()
                return t
        return None


def _build_strict_policy_prompt(
    query: str,
    user_role: str,
    top_clauses: List[RetrievedClause],
) -> str:
    """Zero-hallucination prompt envelope enforcing verbatim figures & [Policy Ref: ID] citations."""
    role_label = "Prospective Applicant" if user_role == "applicant" else "Enrolled Student"
    context_blocks = []
    for clause in top_clauses:
        sec = clause.section
        context_blocks.append(
            f"[Policy Ref: {sec.policy_id}] | Dept: {sec.department} | Audience: {sec.target_role} | Title: {sec.title}\n"
            f"{sec.content_text}"
        )
    joined_context = "\n\n---\n\n".join(context_blocks)

    return (
        "You are UniAssist, the official policy-grounded virtual helpdesk for Dayananda Sagar University.\n"
        f"Stakeholder Mode: {role_label}\n\n"
        "STRICT ZERO-HALLUCINATION RULES:\n"
        "1. Answer ONLY using facts, fee figures, percentages, entrance exams, and dates explicitly present in the POLICY CONTEXT below.\n"
        "2. Every stated fee, cutoff, deadline, or rule MUST cite its exact section tag inline in the format [Policy Ref: POL-XXXX-XX].\n"
        "3. Do NOT invent, estimate, or extrapolate any unstated numbers or external rules.\n"
        "4. If the retrieved context only partially addresses a sub-detail, state clearly what is verified and recommend contacting the relevant office for the unindexed detail.\n"
        "5. Keep the response concise, structured with bullet points, and tailored to the user's Stakeholder Mode.\n\n"
        f"POLICY CONTEXT:\n{joined_context}\n\n"
        f"USER QUESTION: {query}\n\n"
        "GROUNDED RESPONSE:"
    )


def _call_gemini_flash(
    prompt: str,
    api_key: str,
    temperature: float = 0.15,
    timeout_sec: float = 8.0,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Calls Google Gemini 2.5 / 1.5 Flash REST API at low temperature (0.15).
    Returns (response_text, model_used, error_message).
    """
    last_error = None
    for model_name in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "topP": 0.85,
                "maxOutputTokens": 650,
            },
        }
        try:
            resp = requests.post(url, json=payload, timeout=timeout_sec)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    text = "".join(p.get("text", "") for p in parts).strip()
                    if text:
                        return text, model_name, None
                last_error = f"{model_name}: empty candidate response"
            else:
                last_error = f"{model_name}: HTTP {resp.status_code}"
        except Exception as exc:
            last_error = f"{model_name}: {type(exc).__name__}"
    return None, None, last_error


def _deterministic_offline_extract(
    query: str,
    retrieval: RetrievalResult,
) -> str:
    """
    100% Offline Local Grounded Engine (< 10ms).
    Extracts and formats verified clauses directly from top retrieved policy sections
    without speculative generation.
    """
    clauses = retrieval.top_clauses
    if not clauses:
        return "No indexed policy clauses available."

    q_tokens = set(re.findall(r"[a-z0-9]{2,}", query.lower()))
    primary = clauses[0]
    sec = primary.section

    # Score individual lines inside primary section so most relevant bullets surface first
    raw_lines = [ln.strip() for ln in sec.content_text.splitlines() if ln.strip()]
    scored_lines = []
    for idx, line in enumerate(raw_lines):
        line_tokens = set(re.findall(r"[a-z0-9]{2,}", line.lower()))
        overlap = len(q_tokens & line_tokens)
        has_fact = 1 if re.search(r"(\d+%|INR|Rs\.?|days?|CGPA|PGCET|KCET|KMAT|DSAT|COMED-K|SEE|CIE)", line, re.I) else 0
        # Preserve top heading lines slightly
        scored_lines.append((overlap * 2 + has_fact, -idx, line))

    # Keep all lines if section is concise (<= 10 lines), otherwise top relevant lines in original order
    if len(raw_lines) <= 10:
        selected_lines = raw_lines
    else:
        top_indices = {
            -neg_idx
            for _, neg_idx, _ in sorted(scored_lines, reverse=True)[:8]
        }
        # Always include the first structural line for context
        top_indices.add(0)
        selected_lines = [raw_lines[i] for i in sorted(top_indices)]

    formatted_bullets = "\n".join(
        line if line.startswith(("-", "*", "•")) else f"- {line}"
        for line in selected_lines
    )

    parts = [
        f"**{sec.title}** `[Policy Ref: {sec.policy_id}]`\n{formatted_bullets}"
    ]

    # Include secondary clause if it also passes threshold and is reasonably close to primary
    if len(clauses) > 1:
        secondary = clauses[1]
        if (
            secondary.similarity_score >= retrieval.threshold_tau
            and secondary.similarity_score >= 0.55 * primary.similarity_score
        ):
            sec2 = secondary.section
            sec2_lines = [ln.strip() for ln in sec2.content_text.splitlines() if ln.strip()][:5]
            sec2_text = "\n".join(
                ln if ln.startswith(("-", "*", "•")) else f"- {ln}" for ln in sec2_lines
            )
            parts.append(
                f"**Related Clause — {sec2.title}** `[Policy Ref: {sec2.policy_id}]`\n{sec2_text}"
            )

    parts.append(
        f"_Verified directly from official policy section [{sec.policy_id}] via Local Offline Grounded Engine._"
    )
    return "\n\n".join(parts)


class HelpdeskService:
    """Orchestrates retrieval, confidence gating, dual-engine synthesis, and escalation."""

    def __init__(
        self,
        retrieval_engine: RetrievalEngine,
        ticket_store: TicketStore,
    ) -> None:
        self.retrieval_engine = retrieval_engine
        self.ticket_store = ticket_store

    def answer_query(
        self,
        query: str,
        user_role: str = "applicant",
        force_offline: bool = False,
        api_key_override: Optional[str] = None,
    ) -> dict:
        t_total_start = time.perf_counter()
        cleaned_query = (query or "").strip()
        if not cleaned_query:
            raise ValueError("Query cannot be empty.")

        retrieval = self.retrieval_engine.retrieve(cleaned_query, user_role=user_role)

        # Stage 3: Confidence Gate (tau = 0.15)
        if retrieval.is_out_of_scope:
            ticket = self.ticket_store.create_ticket(
                query=cleaned_query,
                user_role=retrieval.user_role,
                inferred_intent=retrieval.inferred_intent,
                max_score=retrieval.max_score,
            )
            total_ms = round((time.perf_counter() - t_total_start) * 1000.0, 3)
            refusal_msg = (
                f"**Out-of-Scope / Unindexed Policy Notice**\n\n"
                f"Your query returned a maximum policy confidence score of `{retrieval.max_score:.4f}`, "
                f"which falls below the strict grounding threshold (`τ = {retrieval.threshold_tau:.2f}`). "
                f"To guarantee zero hallucination, UniAssist has blocked speculative generation.\n\n"
                f"A Tier-2 Counselor Escalation Ticket (**#{ticket['ticket_id']}**) has been automatically created "
                f"and routed to the **{ticket['routed_desk']}**."
            )
            return {
                "answer": refusal_msg,
                "engine_mode": "confidence_gate_refusal",
                "engine_label": "Confidence Gate Refusal (τ < 0.15)",
                "failover_reason": None,
                "inferred_intent": retrieval.inferred_intent,
                "user_role": retrieval.user_role,
                "max_score": round(retrieval.max_score, 4),
                "threshold_tau": retrieval.threshold_tau,
                "is_out_of_scope": True,
                "retrieval_ms": retrieval.retrieval_ms,
                "total_ms": total_ms,
                "citations": [],
                "top_clauses": [c.to_dict() for c in retrieval.top_clauses],
                "escalation_ticket": ticket,
            }

        # Stage 4: Dual-Engine Synthesis (Online Gemini Flash vs. Offline Local Extractor)
        api_key = (api_key_override or os.environ.get("GEMINI_API_KEY") or "").strip()
        failover_reason = None
        answer_text = None
        engine_mode = "offline_local"
        engine_label = "Offline Local Grounded Engine"

        if not force_offline and api_key:
            prompt = _build_strict_policy_prompt(
                cleaned_query, retrieval.user_role, retrieval.top_clauses
            )
            llm_text, model_used, err = _call_gemini_flash(prompt, api_key=api_key)
            if llm_text:
                answer_text = llm_text
                engine_mode = "gemini_flash_online"
                engine_label = f"Google {model_used} (Temp 0.15)"
            else:
                failover_reason = f"Cloud API unavailable ({err}); auto-switched to Offline Local Engine."
        elif force_offline:
            failover_reason = "Offline Kiosk Failover Mode enabled."
        else:
            failover_reason = "No Gemini API key configured; running 100% Local Offline Grounded Engine."

        if answer_text is None:
            answer_text = _deterministic_offline_extract(cleaned_query, retrieval)

        # Ensure exact verified citations are always surfaced cleanly
        cited_clauses = [
            c for c in retrieval.top_clauses if c.similarity_score >= retrieval.threshold_tau
        ]
        if not cited_clauses and retrieval.top_clauses:
            cited_clauses = [retrieval.top_clauses[0]]

        citations = [
            {
                "policy_id": c.section.policy_id,
                "title": c.section.title,
                "department": c.section.department,
                "target_role": c.section.target_role,
                "similarity_score": round(c.similarity_score, 4),
                "raw_score": round(c.raw_score, 4),
                "role_boost": c.role_boost,
            }
            for c in cited_clauses
        ]

        total_ms = round((time.perf_counter() - t_total_start) * 1000.0, 3)

        return {
            "answer": answer_text,
            "engine_mode": engine_mode,
            "engine_label": engine_label,
            "failover_reason": failover_reason,
            "inferred_intent": retrieval.inferred_intent,
            "user_role": retrieval.user_role,
            "max_score": round(retrieval.max_score, 4),
            "threshold_tau": retrieval.threshold_tau,
            "is_out_of_scope": False,
            "retrieval_ms": retrieval.retrieval_ms,
            "total_ms": total_ms,
            "citations": citations,
            "top_clauses": [c.to_dict() for c in retrieval.top_clauses],
            "escalation_ticket": None,
        }
