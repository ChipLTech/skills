import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "engineering" / "model-adaptation" / "scripts" / "route-model-adaptation-request.py"


class ReportRoutingTests(unittest.TestCase):
    def route(self, mutate=None, text="整理已有 evidence 形成报告", raw=None):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            root = Path(directory)
            artifacts = []
            report = json.dumps({"route_feasibility": "not_verified", "adaptation_completion": "not_verified", "stable_delivery": "not_verified", "claim_boundary": "Claim Boundary: report-only creates no execution evidence."}).encode()
            for name, content in (("evidence.json", b"evidence"), ("summary.json", report), ("attachment.json", report)):
                path = root / name
                path.write_bytes(content)
                artifacts.append({"path": str(path), "sha256": hashlib.sha256(content).hexdigest()})
            value = {"schema": "io.chipltech.model-adaptation-request/v1", "request_text": text, "evidence_artifacts": artifacts[:1], "evidence_state": "available", "audience": "reviewers", "decision_questions": ["Is the route feasible?"], "decision_summary_artifact": artifacts[1], "technical_attachment_artifact": artifacts[2]}
            if mutate:
                mutate(value)
            request_path = root / "request.json"
            request_path.write_text(raw if raw is not None else json.dumps(value), encoding="utf-8")
            result = subprocess.run(["python3", str(SCRIPT), str(request_path)], capture_output=True, text=True, check=False)
        return result, json.loads(result.stdout)

    def test_existing_evidence_summary_is_classified_report_only(self):
        result, report = self.route()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(report["terminal_state"], "report_complete")
        self.assertEqual(report["route"], "report_only")

    def test_missing_report_evidence_does_not_request_hardware(self):
        _, report = self.route(lambda value: value.update(evidence_artifacts=[]))
        self.assertEqual(report["terminal_state"], "blocked_missing_evidence")
        self.assertNotIn("hardware", report["resume_requirements"])

    def test_digest_mismatch_blocks_completion(self):
        _, report = self.route(lambda value: value["decision_summary_artifact"].update(sha256="0" * 64))
        self.assertEqual(report["terminal_state"], "blocked_missing_evidence")

    def test_unstructured_report_outputs_block_completion(self):
        def mutate(value):
            path = Path(value["decision_summary_artifact"]["path"])
            path.write_text("unstructured", encoding="utf-8")
            value["decision_summary_artifact"]["sha256"] = hashlib.sha256(b"unstructured").hexdigest()
        _, report = self.route(mutate)
        self.assertEqual(report["terminal_state"], "blocked_missing_evidence")

    def test_conflicting_evidence_is_not_auto_resolved(self):
        _, report = self.route(lambda value: value.update(evidence_state="conflicting"))
        self.assertEqual(report["terminal_state"], "blocked_conflicting_evidence")

    def test_missing_reader_contract_blocks_report(self):
        _, report = self.route(lambda value: value.update(audience="", decision_questions=[]))
        self.assertEqual(report["terminal_state"], "blocked_missing_reader_contract")

    def test_execution_and_mixed_requests_retain_execution_gates(self):
        for text in ("适配并运行模型，执行 build 和 device validation", "整理已有 evidence 并运行模型", "build the model and produce an analysis summary"):
            with self.subTest(text=text):
                result, report = self.route(text=text)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(report["terminal_state"], "execution_preflight_required")
                self.assertEqual(report["route"], "execution")

    def test_malformed_input_fails_closed(self):
        result, report = self.route(raw="not-json")
        self.assertEqual(result.returncode, 3)
        self.assertEqual(report["terminal_state"], "invalid_contract")


if __name__ == "__main__":
    unittest.main()
