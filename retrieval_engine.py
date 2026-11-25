"""
Retrieval & Intent Engine (retrieval_engine.py)
Implements sub-linear TF-IDF vectorization (1, 2-grams), L2-normalized cosine similarity,
1.15x stakeholder role-alignment boosting, and tau = 0.15 confidence gating.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from policy_loader import PolicySection


@dataclass
class RetrievedClause:
    """Ranked policy section with raw, boosted, and attribution metadata."""

    section: PolicySection
    raw_score: float
    role_boost: float
    similarity_score: float

    def to_dict(self) -> dict:
        return {
            "policy_id": self.section.policy_id,
            "department": self.section.department,
            "target_role": self.section.target_role,
            "title": self.section.title,
            "content_text": self.section.content_text,
            "source_file": self.section.source_file,
            "raw_score": round(self.raw_score, 4),
            "role_boost": self.role_boost,
            "similarity_score": round(self.similarity_score, 4),
        }


@dataclass
class RetrievalResult:
    """Complete retrieval + intent classification output for a single query."""

    query: str
    user_role: str
    inferred_intent: str
    max_score: float
    threshold_tau: float
    is_out_of_scope: bool
    retrieval_ms: float
    top_clauses: List[RetrievedClause]

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "user_role": self.user_role,
            "inferred_intent": self.inferred_intent,
            "max_score": round(self.max_score, 4),
            "threshold_tau": self.threshold_tau,
            "is_out_of_scope": self.is_out_of_scope,
            "retrieval_ms": round(self.retrieval_ms, 3),
            "top_clauses": [c.to_dict() for c in self.top_clauses],
        }


class RetrievalEngine:
    """CPU-only sub-linear TF-IDF & role-weighted cosine retrieval engine."""

    def __init__(
        self,
        sections: List[PolicySection],
        role_boost_factor: float = 1.15,
        confidence_tau: float = 0.15,
        top_k: int = 3,
    ) -> None:
        self.role_boost_factor = role_boost_factor
        self.confidence_tau = confidence_tau
        self.top_k = top_k
        self.sections: List[PolicySection] = []
        self.vectorizer: TfidfVectorizer | None = None
        self.doc_matrix = None
        self.indexing_ms: float = 0.0
        self.build_index(sections)

    def build_index(self, sections: List[PolicySection]) -> float:
        """Vectorizes atomic policy sections using L2-normalized sub-linear TF-IDF."""
        t0 = time.perf_counter()
        self.sections = list(sections)
        corpus_texts = [
            f"{sec.title} | {sec.department} | {sec.policy_id}\n{sec.content_text}"
            for sec in self.sections
        ]
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            sublinear_tf=True,
            norm="l2",
            stop_words="english",
            lowercase=True,
        )
        self.doc_matrix = self.vectorizer.fit_transform(corpus_texts)
        t1 = time.perf_counter()
        self.indexing_ms = round((t1 - t0) * 1000.0, 3)
        return self.indexing_ms

    def add_sections(self, new_sections: List[PolicySection]) -> float:
        """Appends or updates policy sections and rebuilds the sparse vector matrix."""
        existing_by_id = {s.policy_id: s for s in self.sections}
        for sec in new_sections:
            existing_by_id[sec.policy_id] = sec
        return self.build_index(list(existing_by_id.values()))

    def retrieve(
        self,
        query: str,
        user_role: str = "applicant",
        top_k: int | None = None,
    ) -> RetrievalResult:
        """
        Executes sub-linear TF-IDF cosine search with 1.15x role-alignment boost
        and confidence gating at tau = 0.15.
        """
        t0 = time.perf_counter()
        role = user_role.strip().lower()
        if role not in {"applicant", "student"}:
            role = "applicant"

        k = top_k or self.top_k
        if not self.sections or self.vectorizer is None or self.doc_matrix is None:
            return RetrievalResult(
                query=query,
                user_role=role,
                inferred_intent="ADMISSIONS",
                max_score=0.0,
                threshold_tau=self.confidence_tau,
                is_out_of_scope=True,
                retrieval_ms=0.0,
                top_clauses=[],
            )

        q_vec = self.vectorizer.transform([query.strip()])
        # Because both doc_matrix and q_vec are L2-normalized, dot product == cosine similarity
        raw_sims = (self.doc_matrix @ q_vec.T).toarray().ravel()

        boosts = np.array(
            [
                self.role_boost_factor
                if (sec.target_role == role or sec.target_role == "both")
                else 1.0
                for sec in self.sections
            ],
            dtype=np.float64,
        )
        final_scores = raw_sims * boosts

        sorted_indices = np.argsort(-final_scores)[:k]
        top_clauses: List[RetrievedClause] = []
        for idx in sorted_indices:
            i = int(idx)
            top_clauses.append(
                RetrievedClause(
                    section=self.sections[i],
                    raw_score=float(raw_sims[i]),
                    role_boost=float(boosts[i]),
                    similarity_score=float(final_scores[i]),
                )
            )

        max_score = float(top_clauses[0].similarity_score) if top_clauses else 0.0
        inferred_intent = (
            top_clauses[0].section.department if top_clauses else "ADMISSIONS"
        )
        is_out_of_scope = max_score < self.confidence_tau

        t1 = time.perf_counter()
        retrieval_ms = round((t1 - t0) * 1000.0, 3)

        return RetrievalResult(
            query=query,
            user_role=role,
            inferred_intent=inferred_intent,
            max_score=max_score,
            threshold_tau=self.confidence_tau,
            is_out_of_scope=is_out_of_scope,
            retrieval_ms=retrieval_ms,
            top_clauses=top_clauses,
        )
