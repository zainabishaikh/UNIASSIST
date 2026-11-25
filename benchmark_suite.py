"""
Evaluation & Benchmark Suite (benchmark_suite.py)
Executes the 60-query intent & retrieval benchmark, 10 adversarial out-of-scope queries,
and Functional Test Cases TC-01 through TC-05 directly against the live UniAssist engines.
"""

from __future__ import annotations

import statistics
from typing import Dict, List

from estimator_engine import estimate_eligibility_and_fee
from retrieval_engine import RetrievalEngine

DEPARTMENTS = [
    "ELIGIBILITY",
    "FEES",
    "SCHOLARSHIPS",
    "ADMISSIONS",
    "HOSTEL",
    "EXAMINATIONS",
]

# 60 curated benchmark queries (10 per administrative department)
BENCHMARK_QUERIES: List[dict] = [
    # ELIGIBILITY (10)
    {"query": "Eligibility criteria for MCA admission?", "role": "applicant", "expected_dept": "ELIGIBILITY", "expected_policy": "POL-ELIG-02"},
    {"query": "Am I eligible for MCA with 58% in BCA and no Mathematics in Class 12?", "role": "applicant", "expected_dept": "ELIGIBILITY", "expected_policy": "POL-ELIG-02"},
    {"query": "What is the minimum percentage required for B.Tech CSE admission?", "role": "applicant", "expected_dept": "ELIGIBILITY", "expected_policy": "POL-ELIG-01"},
    {"query": "Can diploma students apply for B.Tech lateral entry via DCET?", "role": "applicant", "expected_dept": "ELIGIBILITY", "expected_policy": "POL-ELIG-01"},
    {"query": "Is Physics and Mathematics compulsory for B.Tech eligibility?", "role": "applicant", "expected_dept": "ELIGIBILITY", "expected_policy": "POL-ELIG-01"},
    {"query": "What entrance exams are accepted for MBA admission?", "role": "applicant", "expected_dept": "ELIGIBILITY", "expected_policy": "POL-ELIG-03"},
    {"query": "Minimum aggregate marks for BCA and B.Sc. Biotechnology?", "role": "applicant", "expected_dept": "ELIGIBILITY", "expected_policy": "POL-ELIG-03"},
    {"query": "Do SC ST candidates get 45% relaxation in MCA eligibility?", "role": "applicant", "expected_dept": "ELIGIBILITY", "expected_policy": "POL-ELIG-02"},
    {"query": "Is there a Mathematics bridge course for non-math MCA graduates?", "role": "applicant", "expected_dept": "ELIGIBILITY", "expected_policy": "POL-ELIG-02"},
    {"query": "Are CAT and MAT scores valid for MBA eligibility?", "role": "applicant", "expected_dept": "ELIGIBILITY", "expected_policy": "POL-ELIG-03"},

    # FEES (10)
    {"query": "What is the MCA tuition fee under PGCET government quota?", "role": "applicant", "expected_dept": "FEES", "expected_policy": "POL-FEES-01"},
    {"query": "B.Tech COMED-K and KCET annual tuition fee structure?", "role": "applicant", "expected_dept": "FEES", "expected_policy": "POL-FEES-01"},
    {"query": "Hostel fee structure for single AC and twin sharing rooms?", "role": "applicant", "expected_dept": "FEES", "expected_policy": "POL-FEES-02"},
    {"query": "How much is the mess dining and lodging fee for triple sharing hostel?", "role": "both", "expected_dept": "FEES", "expected_policy": "POL-FEES-02"},
    {"query": "What is the UGC fee refund policy if I withdraw before admission closes?", "role": "applicant", "expected_dept": "FEES", "expected_policy": "POL-FEES-03"},
    {"query": "Late payment fine for odd and even semester tuition fee installments?", "role": "student", "expected_dept": "FEES", "expected_policy": "POL-FEES-03"},
    {"query": "How much is the refundable caution deposit and admission registration fee?", "role": "applicant", "expected_dept": "FEES", "expected_policy": "POL-FEES-01"},
    {"query": "What is the annual tuition fee for MBA and BCA programs?", "role": "applicant", "expected_dept": "FEES", "expected_policy": "POL-FEES-01"},
    {"query": "Refund percentage when cancelling admission 20 days after last date?", "role": "applicant", "expected_dept": "FEES", "expected_policy": "POL-FEES-03"},
    {"query": "Is laundry and Wi-Fi included in the annual hostel fee?", "role": "applicant", "expected_dept": "FEES", "expected_policy": "POL-FEES-02"},

    # SCHOLARSHIPS (10)
    {"query": "What are the university merit scholarship slabs for 86% marks?", "role": "applicant", "expected_dept": "SCHOLARSHIPS", "expected_policy": "POL-SCHOL-01"},
    {"query": "What CGPA is required to renew merit scholarship in Year 2?", "role": "student", "expected_dept": "SCHOLARSHIPS", "expected_policy": "POL-SCHOL-01"},
    {"query": "Does KCET rank under 500 qualify for a 50% tuition fee waiver?", "role": "applicant", "expected_dept": "SCHOLARSHIPS", "expected_policy": "POL-SCHOL-01"},
    {"query": "How to apply for Karnataka SSP and NSP post-matric scholarships?", "role": "student", "expected_dept": "SCHOLARSHIPS", "expected_policy": "POL-SCHOL-02"},
    {"query": "What is the deadline and income limit for SSP scholarship desk submission?", "role": "student", "expected_dept": "SCHOLARSHIPS", "expected_policy": "POL-SCHOL-02"},
    {"query": "Is AICTE Pragati scholarship available on National Scholarship Portal?", "role": "both", "expected_dept": "SCHOLARSHIPS", "expected_policy": "POL-SCHOL-02"},
    {"query": "Are there fee concessions for defence personnel wards and national sports medalists?", "role": "applicant", "expected_dept": "SCHOLARSHIPS", "expected_policy": "POL-SCHOL-03"},
    {"query": "Do DSU alumni and siblings get a loyalty tuition concession?", "role": "applicant", "expected_dept": "SCHOLARSHIPS", "expected_policy": "POL-SCHOL-03"},
    {"query": "Can I combine sports concession with merit scholarship waiver?", "role": "applicant", "expected_dept": "SCHOLARSHIPS", "expected_policy": "POL-SCHOL-03"},
    {"query": "What is the Vidyasiri food and accommodation assistance scheme?", "role": "student", "expected_dept": "SCHOLARSHIPS", "expected_policy": "POL-SCHOL-02"},

    # ADMISSIONS (10)
    {"query": "What is the step-by-step admission counseling and seat allotment process?", "role": "applicant", "expected_dept": "ADMISSIONS", "expected_policy": "POL-ADM-01"},
    {"query": "What documents are mandatory during physical document verification?", "role": "applicant", "expected_dept": "ADMISSIONS", "expected_policy": "POL-ADM-02"},
    {"query": "Is Migration Certificate required for out-of-state university graduates?", "role": "applicant", "expected_dept": "ADMISSIONS", "expected_policy": "POL-ADM-02"},
    {"query": "When do classes and orientation week start for 2026 admissions?", "role": "applicant", "expected_dept": "ADMISSIONS", "expected_policy": "POL-ADM-03"},
    {"query": "Can final year students awaiting 6th semester results get provisional admission?", "role": "applicant", "expected_dept": "ADMISSIONS", "expected_policy": "POL-ADM-03"},
    {"query": "How many days are given to lock seat after provisional allotment letter?", "role": "applicant", "expected_dept": "ADMISSIONS", "expected_policy": "POL-ADM-01"},
    {"query": "What is the DSAT application fee and portal URL?", "role": "applicant", "expected_dept": "ADMISSIONS", "expected_policy": "POL-ADM-01"},
    {"query": "Is anti-ragging undertaking printout needed at verification?", "role": "applicant", "expected_dept": "ADMISSIONS", "expected_policy": "POL-ADM-02"},
    {"query": "What is the final cut-off date for admissions and document submission?", "role": "applicant", "expected_dept": "ADMISSIONS", "expected_policy": "POL-ADM-03"},
    {"query": "Do Karnataka quota candidates need a 7-year study certificate?", "role": "applicant", "expected_dept": "ADMISSIONS", "expected_policy": "POL-ADM-02"},

    # HOSTEL (10)
    {"query": "What are the hostel biometric curfew timings and night out leave pass rules?", "role": "student", "expected_dept": "HOSTEL", "expected_policy": "POL-HOSTEL-01"},
    {"query": "Are induction cookers or electric heaters allowed inside hostel rooms?", "role": "student", "expected_dept": "HOSTEL", "expected_policy": "POL-HOSTEL-01"},
    {"query": "How does hostel room allotment priority work for outstation students?", "role": "applicant", "expected_dept": "HOSTEL", "expected_policy": "POL-HOSTEL-01"},
    {"query": "What are the campus bus shuttle routes and annual transport fees?", "role": "student", "expected_dept": "HOSTEL", "expected_policy": "POL-HOSTEL-02"},
    {"query": "Central library borrowing limit and operating hours during exams?", "role": "student", "expected_dept": "HOSTEL", "expected_policy": "POL-HOSTEL-02"},
    {"query": "Does the campus have a 24x7 medical infirmary and ambulance tie-up?", "role": "student", "expected_dept": "HOSTEL", "expected_policy": "POL-HOSTEL-02"},
    {"query": "How do I request a hostel room change during the semester?", "role": "student", "expected_dept": "HOSTEL", "expected_policy": "POL-HOSTEL-03"},
    {"query": "When is the INR 15,000 hostel security deposit refunded after vacating?", "role": "student", "expected_dept": "HOSTEL", "expected_policy": "POL-HOSTEL-03"},
    {"query": "Is unused mess charge refunded for long medical leave?", "role": "student", "expected_dept": "HOSTEL", "expected_policy": "POL-HOSTEL-03"},
    {"query": "Is parent SMS approval mandatory for hostel home leave gate pass?", "role": "student", "expected_dept": "HOSTEL", "expected_policy": "POL-HOSTEL-01"},

    # EXAMINATIONS (10)
    {"query": "When is the exam schedule released?", "role": "student", "expected_dept": "EXAMINATIONS", "expected_policy": "POL-EXAM-01"},
    {"query": "What is the minimum attendance requirement for SEE and condonation rules?", "role": "student", "expected_dept": "EXAMINATIONS", "expected_policy": "POL-EXAM-01"},
    {"query": "When are exam hall tickets unlocked on the Student ERP portal?", "role": "student", "expected_dept": "EXAMINATIONS", "expected_policy": "POL-EXAM-01"},
    {"query": "What happens if attendance falls below 75% in a course?", "role": "student", "expected_dept": "EXAMINATIONS", "expected_policy": "POL-EXAM-01"},
    {"query": "What is the CIE and SEE marks split and minimum passing criteria?", "role": "student", "expected_dept": "EXAMINATIONS", "expected_policy": "POL-EXAM-02"},
    {"query": "How does the 10-point CGPA grading scale convert marks to grade points?", "role": "student", "expected_dept": "EXAMINATIONS", "expected_policy": "POL-EXAM-02"},
    {"query": "What is the fee and deadline for answer-script photocopy and revaluation?", "role": "student", "expected_dept": "EXAMINATIONS", "expected_policy": "POL-EXAM-02"},
    {"query": "How to apply for a bonafide certificate or fee structure letter on ERP?", "role": "student", "expected_dept": "EXAMINATIONS", "expected_policy": "POL-EXAM-03"},
    {"query": "What is the No-Dues clearance approval sequence for graduating students?", "role": "student", "expected_dept": "EXAMINATIONS", "expected_policy": "POL-EXAM-03"},
    {"query": "How long does it take to get official transcripts and provisional degree certificate?", "role": "student", "expected_dept": "EXAMINATIONS", "expected_policy": "POL-EXAM-03"},
]

OUT_OF_SCOPE_QUERIES: List[str] = [
    "Does the university offer scuba diving?",
    "Can I book a private helicopter tour in Bengaluru?",
    "What is the Bitcoin to INR exchange rate today?",
    "Who won the FIFA World Cup cricket match yesterday?",
    "Recipe for making masala dosa in five minutes",
    "How to repair a broken iPhone screen in Bengaluru?",
    "Does DSU provide astronaut training for Mars missions?",
    "What is the stock price of Infosys on NSE right now?",
    "Can I rent a yacht for weekend sailing near Kudlu Gate?",
    "Best Python syntax to invert a binary tree in LeetCode",
]


def run_benchmark(engine: RetrievalEngine) -> dict:
    """Runs the live 60-query + 10-OOS evaluation and computes confusion matrix & F1."""
    idx_map = {dept: i for i, dept in enumerate(DEPARTMENTS)}
    confusion = [[0 for _ in DEPARTMENTS] for _ in DEPARTMENTS]

    rank1_hits = 0
    dept_hits = 0
    latencies: List[float] = []
    misclassified = []

    for item in BENCHMARK_QUERIES:
        res = engine.retrieve(item["query"], user_role=item["role"])
        latencies.append(res.retrieval_ms)
        actual = item["expected_dept"]
        pred = res.inferred_intent
        if actual in idx_map and pred in idx_map:
            confusion[idx_map[actual]][idx_map[pred]] += 1
        if pred == actual:
            dept_hits += 1
        top_policy = res.top_clauses[0].section.policy_id if res.top_clauses else ""
        if top_policy == item["expected_policy"] and not res.is_out_of_scope:
            rank1_hits += 1
        else:
            misclassified.append(
                {
                    "query": item["query"],
                    "expected_policy": item["expected_policy"],
                    "predicted_policy": top_policy,
                    "expected_dept": actual,
                    "predicted_dept": pred,
                    "score": round(res.max_score, 4),
                }
            )

    precisions, recalls, f1s = [], [], []
    per_dept = []
    for i, dept in enumerate(DEPARTMENTS):
        tp = confusion[i][i]
        fp = sum(confusion[r][i] for r in range(len(DEPARTMENTS)) if r != i)
        fn = sum(confusion[i][c] for c in range(len(DEPARTMENTS)) if c != i)
        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0
        precisions.append(p)
        recalls.append(r)
        f1s.append(f1)
        per_dept.append(
            {
                "department": dept,
                "precision": round(p, 3),
                "recall": round(r, 3),
                "f1": round(f1, 3),
            }
        )

    # Adversarial Out-of-Scope test
    oos_refused = 0
    oos_details = []
    for q in OUT_OF_SCOPE_QUERIES:
        res = engine.retrieve(q, user_role="applicant")
        latencies.append(res.retrieval_ms)
        if res.is_out_of_scope:
            oos_refused += 1
        oos_details.append(
            {
                "query": q,
                "max_score": round(res.max_score, 4),
                "refused": res.is_out_of_scope,
            }
        )

    total_q = len(BENCHMARK_QUERIES)
    rank1_acc = round((rank1_hits / total_q) * 100.0, 1)
    dept_acc = round((dept_hits / total_q) * 100.0, 1)
    macro_p = round(sum(precisions) / len(DEPARTMENTS), 3)
    macro_r = round(sum(recalls) / len(DEPARTMENTS), 3)
    macro_f1 = round(sum(f1s) / len(DEPARTMENTS), 3)
    oos_precision = round((oos_refused / len(OUT_OF_SCOPE_QUERIES)) * 100.0, 1)
    median_ms = round(statistics.median(latencies), 2)

    # Functional Test Cases TC-01..TC-05
    tc01 = engine.retrieve("Eligibility criteria for MCA admission?", user_role="applicant")
    tc01_ok = (
        not tc01.is_out_of_scope
        and tc01.top_clauses[0].section.policy_id == "POL-ELIG-02"
        and "50%" in tc01.top_clauses[0].section.content_text
    )

    tc02 = engine.retrieve("When is the exam schedule released?", user_role="student")
    tc02_ok = (
        not tc02.is_out_of_scope
        and tc02.top_clauses[0].section.policy_id == "POL-EXAM-01"
        and tc02.top_clauses[0].role_boost == 1.15
    )

    tc03 = engine.retrieve("Does the university offer scuba diving?", user_role="applicant")
    tc03_ok = tc03.is_out_of_scope and tc03.max_score < 0.15

    tc04 = engine.retrieve("Hostel fee structure?", user_role="applicant")
    tc04_ok = (
        not tc04.is_out_of_scope
        and tc04.top_clauses[0].section.policy_id == "POL-FEES-02"
        and tc04.retrieval_ms < 10.0
    )

    tc05 = estimate_eligibility_and_fee(
        program="MCA",
        percentage=86.0,
        entrance_exam="PGCET",
        category="General",
        has_math=True,
    )
    tc05_ok = tc05.eligible and tc05.scholarship_pct == 15

    functional_tests = [
        {
            "test_id": "TC-01",
            "scenario": "Eligibility Query",
            "input": "'Eligibility criteria for MCA admission?' (Applicant)",
            "observed": f"{tc01.top_clauses[0].section.policy_id} (score={tc01.max_score:.3f}, {tc01.retrieval_ms:.2f} ms)",
            "passed": tc01_ok,
        },
        {
            "test_id": "TC-02",
            "scenario": "Role Disambiguation",
            "input": "'When is the exam schedule released?' (Student)",
            "observed": f"{tc02.top_clauses[0].section.policy_id} (boost={tc02.top_clauses[0].role_boost}x, score={tc02.max_score:.3f})",
            "passed": tc02_ok,
        },
        {
            "test_id": "TC-03",
            "scenario": "Out-of-Scope Refusal",
            "input": "'Does the university offer scuba diving?'",
            "observed": f"Refused={tc03.is_out_of_scope} (score={tc03.max_score:.3f} < 0.15)",
            "passed": tc03_ok,
        },
        {
            "test_id": "TC-04",
            "scenario": "Offline Failover Speed",
            "input": "'Hostel fee structure?' (Local TF-IDF < 10 ms)",
            "observed": f"{tc04.top_clauses[0].section.policy_id} in {tc04.retrieval_ms:.2f} ms",
            "passed": tc04_ok,
        },
        {
            "test_id": "TC-05",
            "scenario": "Fee & Merit Estimator",
            "input": "MCA | 86% Marks | PGCET | General",
            "observed": f"Eligible={tc05.eligible}; Scholarship={tc05.scholarship_pct}% (Net Tuition INR {tc05.net_tuition_fee:,})",
            "passed": tc05_ok,
        },
    ]

    return {
        "total_benchmark_queries": total_q,
        "rank1_hits": rank1_hits,
        "rank1_accuracy_pct": rank1_acc,
        "department_accuracy_pct": dept_acc,
        "macro_precision": macro_p,
        "macro_recall": macro_r,
        "macro_f1": macro_f1,
        "oos_total": len(OUT_OF_SCOPE_QUERIES),
        "oos_refused": oos_refused,
        "oos_refusal_precision_pct": oos_precision,
        "median_local_latency_ms": median_ms,
        "indexing_latency_ms": engine.indexing_ms,
        "departments": DEPARTMENTS,
        "confusion_matrix": confusion,
        "per_department": per_dept,
        "misclassified": misclassified,
        "oos_details": oos_details,
        "functional_tests": functional_tests,
    }
