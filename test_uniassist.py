"""
Automated Verification Suite (test_uniassist.py)
Verifies student-safe RBAC isolation, TC-01 through TC-05, Flask REST API endpoints,
confidence gating, offline failover latency, estimator accuracy, and 60-query benchmark.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app as uni_app  # noqa: E402
from benchmark_suite import run_benchmark  # noqa: E402


class TestUniAssistSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        uni_app.app.config["TESTING"] = True

    def setUp(self):
        self.client = uni_app.app.test_client()

    def _login_admin(self):
        resp = self.client.post(
            "/api/admin/login", json={"passcode": uni_app.ADMIN_PASSCODE}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["authenticated"])

    def test_student_cannot_access_admin_endpoints(self):
        self.assertEqual(self.client.get("/api/tickets").status_code, 401)
        self.assertEqual(self.client.post("/api/benchmark/run").status_code, 401)
        self.assertEqual(
            self.client.post(
                "/api/policies/ingest",
                json={"raw_text": "test policy"},
            ).status_code,
            401,
        )

        # Health should not expose admin telemetry to unauthenticated student
        health = self.client.get("/api/health").get_json()
        self.assertFalse(health["is_admin"])
        self.assertNotIn("tau", health)
        self.assertNotIn("indexing_ms", health)

    def test_admin_health_and_corpus_count(self):
        self._login_admin()
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["is_admin"])
        self.assertGreaterEqual(data["corpus_sections"], 18)
        self.assertEqual(data["tau"], 0.15)
        self.assertEqual(data["role_boost"], 1.15)

    def test_index_page_renders(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"UniAssist", resp.data)
        self.assertIn(b"Eligibility & Fee Estimator", resp.data)

    def test_tc01_mca_eligibility_query_student_view(self):
        resp = self.client.post(
            "/api/chat",
            json={
                "query": "Eligibility criteria for MCA admission?",
                "role": "applicant",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertFalse(data["is_out_of_scope"])
        self.assertEqual(data["inferred_intent"], "ELIGIBILITY")
        self.assertEqual(data["citations"][0]["policy_id"], "POL-ELIG-02")
        self.assertNotIn("top_clauses", data)
        self.assertNotIn("retrieval_ms", data)
        self.assertIn("50%", data["answer"])
        self.assertIn("PGCET", data["answer"])

    def test_tc02_role_disambiguation_student_exam(self):
        self._login_admin()
        resp = self.client.post(
            "/api/chat",
            json={
                "query": "When is the exam schedule released?",
                "role": "student",
                "force_offline": True,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertFalse(data["is_out_of_scope"])
        self.assertEqual(data["inferred_intent"], "EXAMINATIONS")
        self.assertEqual(data["citations"][0]["policy_id"], "POL-EXAM-01")
        self.assertEqual(data["top_clauses"][0]["role_boost"], 1.15)

    def test_tc03_out_of_scope_refusal_and_ticket(self):
        self._login_admin()
        resp = self.client.post(
            "/api/chat",
            json={
                "query": "Does the university offer scuba diving?",
                "role": "applicant",
                "force_offline": True,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["is_out_of_scope"])
        self.assertLess(data["max_score"], 0.15)
        self.assertIsNotNone(data["escalation_ticket"])
        self.assertTrue(data["escalation_ticket"]["ticket_id"].startswith("UA-"))

    def test_tc04_offline_failover_speed(self):
        self._login_admin()
        resp = self.client.post(
            "/api/chat",
            json={
                "query": "Hostel fee structure?",
                "role": "applicant",
                "force_offline": True,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertFalse(data["is_out_of_scope"])
        self.assertEqual(data["engine_mode"], "offline_local")
        self.assertEqual(data["citations"][0]["policy_id"], "POL-FEES-02")
        self.assertLess(data["retrieval_ms"], 10.0)

    def test_tc05_estimator_mca_86_pgcet_general(self):
        resp = self.client.post(
            "/api/estimate",
            json={
                "program": "MCA",
                "percentage": 86,
                "entrance_exam": "PGCET",
                "category": "General",
                "has_math": True,
                "hostel_plan": "None",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["eligible"])
        self.assertEqual(data["scholarship_pct"], 15)
        self.assertEqual(data["gross_tuition_fee"], 128000)
        self.assertEqual(data["net_tuition_fee"], 108800)

    def test_static_assets_and_policies_routes(self):
        self.assertEqual(self.client.get("/static/css/styles.css").status_code, 200)
        self.assertEqual(self.client.get("/static/js/app.js").status_code, 200)

        pol_resp = self.client.get("/api/policies?department=FEES")
        self.assertEqual(pol_resp.status_code, 200)
        self.assertEqual(pol_resp.get_json()["filtered"], 3)

    def test_ticket_lifecycle_and_benchmark_endpoint(self):
        self._login_admin()
        chat_resp = self.client.post(
            "/api/chat",
            json={"query": "Does DSU offer scuba diving?", "role": "applicant"},
        )
        tid = chat_resp.get_json()["escalation_ticket"]["ticket_id"]

        patch_resp = self.client.patch(f"/api/tickets/{tid}", json={"status": "Resolved"})
        self.assertEqual(patch_resp.status_code, 200)
        self.assertEqual(patch_resp.get_json()["ticket"]["status"], "Resolved")

        bench_resp = self.client.post("/api/benchmark/run")
        self.assertEqual(bench_resp.status_code, 200)
        self.assertEqual(bench_resp.get_json()["rank1_accuracy_pct"], 100.0)

    def test_benchmark_suite_metrics(self):
        report = run_benchmark(uni_app.retrieval_engine)
        self.assertGreaterEqual(report["rank1_accuracy_pct"], 95.0)
        self.assertGreaterEqual(report["macro_f1"], 0.96)
        self.assertEqual(report["oos_refusal_precision_pct"], 100.0)
        self.assertLess(report["median_local_latency_ms"], 10.0)
        for tc in report["functional_tests"]:
            self.assertTrue(tc["passed"], f"Functional test failed: {tc}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
