# UniAssist: Policy-Grounded RAG & Intent-Aware Virtual Helpdesk

**Dayananda Sagar University (DSU)** — School of Computer Applications  
**Program:** Master of Computer Applications (MCA — Ready To Deploy)  
**Submitted by:** Zainabi Amjad Ali Shaikh (USN: `SCA25MCA069`)

## Overview
UniAssist is a policy-grounded Retrieval-Augmented Generation (RAG) and intent-aware virtual helpdesk built for university admissions and student services. It eliminates fee/deadline hallucinations using:
- **Policy-Boundary Knowledge Ingestion (`policy_loader.py`)**: Segments `.txt`, `.md`, and `.pdf` circulars along explicit section delimiters (`=== SECTION: ... ===`) so multi-condition eligibility matrices and fee tables remain intact.
- **Hybrid Sub-Linear TF-IDF Retrieval & Intent Routing (`retrieval_engine.py`)**: Uses L2-normalized unigram/bigram TF-IDF (`sublinear_tf=True`) with a `1.15×` stakeholder role-alignment boost (`Prospective Applicant` vs. `Enrolled Student`) in `< 5 ms` on commodity CPU hardware.
- **Confidence-Gated Dual-Engine Synthesis (`helpdesk_service.py`)**: Enforces `τ = 0.15` refusal gating with automatic Tier-2 Escalation Ticket generation (`#UA-...`), Google Gemini Flash synthesis (`temperature = 0.15`) when online with an API key, and automatic `< 10 ms` Offline Local Deterministic Failover.
- **Interactive Eligibility & Fee Estimator (`estimator_engine.py`)**: Deterministic calculator for `MCA`, `MBA`, `B.Tech`, `BCA`, and `B.Sc.` covering quotas, category relaxations, merit scholarship slabs, and hostel plans.
- **Live Benchmark & Diagnostics Lab (`benchmark_suite.py`)**: Evaluates 60 curated queries, 10 adversarial out-of-scope queries, and Functional Test Cases `TC-01` through `TC-05`.

## Quick Start
1. Install dependencies (already satisfied if Python 3.11 environment has Flask & scikit-learn):
   ```powershell
   pip install -r requirements.txt
   ```
2. Optional: Copy `.env.example` to `.env` and add `GEMINI_API_KEY` for online Gemini Flash synthesis (leave empty to run 100% locally via the Offline Grounded Engine).
3. Launch the web application:
   ```powershell
   python app.py
   ```
   Or double-click `run_uniassist.bat`, then open `http://127.0.0.1:5050`.
4. Run automated verification tests:
   ```powershell
   python test_uniassist.py
   ```
