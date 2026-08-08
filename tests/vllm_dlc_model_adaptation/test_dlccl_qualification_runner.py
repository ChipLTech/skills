import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "engineering" / "model-adaptation"
RUNNER = SKILL / "scripts" / "run-dlccl-qualification.py"
VALIDATOR = SKILL / "scripts" / "validate-vllm-dlc-qualification.py"
FIXTURES = Path(__file__).with_name("fixtures") / "distributed-collective"
SPEC = importlib.util.spec_from_file_location("runner_contract_test", VALIDATOR)
assert SPEC is not None and SPEC.loader is not None
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)


class DlcclQualificationRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir="/tmp/kilo")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def template(self, mutate=None):
        document = json.loads((FIXTURES / "qualified-controlled-template.json").read_text())
        if mutate:
            mutate(document)
        CONTRACT.normalize_status(document)
        document["digest"] = CONTRACT.artifact_digest(document)
        path = self.root / "template.json"
        path.write_text(json.dumps(document))
        return path

    def run_runner(self, harness, *extra, mutate=None):
        output = self.root / "result.json"
        result = subprocess.run(
            [sys.executable, str(RUNNER), str(self.template(mutate)), str(output), "--harness", str((FIXTURES / harness).resolve()), *extra],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        document = json.loads(output.read_text()) if output.exists() else None
        return result, document

    def test_pass_harness_seals_rank_exits_and_non_acceptance_boundary(self):
        result, document = self.run_runner("harness-pass.py", "--controlled-harness", "--attempts", "2")
        self.assertEqual(result.returncode, 24, result.stdout)
        self.assertEqual(document["status"], "not_verified")
        self.assertEqual(document["producer"], "model-adaptation/dlccl-qualification-runner")
        self.assertEqual(document["producer_version"], "1.0.0")
        self.assertEqual(document["evidence_class"], "fixture")
        self.assertEqual(document["authoritativeness"], "non_authoritative")
        self.assertEqual(len(document["qualification"]["execution"]["rank_results"]), 4)
        self.assertTrue(all(row["exit_code"] == 0 for row in document["qualification"]["execution"]["rank_results"]))
        self.assertFalse(document["acceptance_eligible"])
        self.assertTrue(document["claim_boundary"].startswith("Claim Boundary:"))
        self.assertIn("blocked_missing_hardware", {row["code"] for row in document["blockers"]})

    def test_timeout_watchdog_kills_process_tree_and_records_health(self):
        result, document = self.run_runner("harness-hang.py", "--controlled-harness", "--timeout-seconds", "1")
        self.assertEqual(result.returncode, 30, result.stdout)
        self.assertEqual(document["status"], "failed")
        execution = document["qualification"]["execution"]
        self.assertIn("timeout", execution["watchdog_actions"])
        self.assertIn("sigterm", execution["watchdog_actions"])
        self.assertIn("reaped", execution["watchdog_actions"])
        self.assertEqual(execution["process_tree_cleanup"]["residual_pids"], [])
        self.assertEqual(execution["health_snapshot"]["status"], "not_verified")
        self.assertIn("failed_collective_completion", {row["code"] for row in document["blockers"]})

    def test_rank_failure_is_aggregated_without_rewriting_blocker(self):
        result, document = self.run_runner("harness-fail.py", "--controlled-harness")
        self.assertEqual(result.returncode, 30, result.stdout)
        self.assertEqual(document["status"], "failed")
        rows = document["qualification"]["execution"]["rank_results"]
        self.assertEqual([row["exit_code"] for row in rows], [0, 7])
        self.assertIn("failed_collective_correctness", {row["code"] for row in document["blockers"]})
        self.assertEqual(document["primary_blocker"]["status"], "failed")

    def test_failed_content_attempt_stops_and_cannot_be_hidden_by_retry(self):
        result, document = self.run_runner(
            "harness-content-fail.py", "--controlled-harness", "--attempts", "2"
        )
        self.assertEqual(result.returncode, 30, result.stdout)
        execution = document["qualification"]["execution"]
        self.assertEqual(execution["attempt_count"], 1)
        self.assertEqual(len(execution["correctness"]), 1)
        self.assertEqual(execution["correctness"][0]["status"], "failed")
        self.assertEqual(document["primary_blocker"]["code"], "failed_collective_correctness")

    def test_nonzero_harness_parent_cannot_report_passing_ranks(self):
        result, document = self.run_runner("harness-parent-fail.py", "--controlled-harness")
        self.assertEqual(result.returncode, 30, result.stdout)
        self.assertEqual(document["status"], "failed")
        self.assertTrue(all(row["status"] == "failed" for row in document["qualification"]["execution"]["rank_results"]))
        self.assertTrue(all(row["exit_code"] == 9 for row in document["qualification"]["execution"]["rank_results"]))

    def test_cleanup_kills_child_when_parent_exits_first(self):
        result, document = self.run_runner("harness-parent-exits.py", "--controlled-harness")
        self.assertEqual(result.returncode, 30, result.stdout)
        execution = document["qualification"]["execution"]
        self.assertIn("sigterm", execution["watchdog_actions"])
        self.assertEqual(execution["process_tree_cleanup"]["residual_pids"], [])
        self.assertEqual(document["primary_blocker"]["code"], "failed_collective_correctness")

    def test_real_qualification_does_not_launch_without_trusted_inputs(self):
        marker = self.root / "real-launched"
        harness = self.root / "real-marker.py"
        harness.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('launched')\n")
        result, document = self.run_runner(
            str(harness),
            mutate=lambda value: value["qualification"]["preflight"].update(
                hardware_environment="real_dlc_hardware", hardware_available=True
            ),
        )
        self.assertEqual(result.returncode, 24, result.stdout)
        self.assertFalse(marker.exists())
        self.assertFalse(json.loads(result.stdout)["launched"])
        self.assertEqual(document["primary_blocker"]["code"], "blocked_missing_trusted_qualification_inputs")

    def test_preflight_stops_before_launch_and_can_resume(self):
        marker = self.root / "launched"
        harness = self.root / "marker.py"
        harness.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('launched')\n")
        result, document = self.run_runner(
            str(harness),
            mutate=lambda value: (
                value["qualification"]["preflight"].update(
                    hardware_environment="real_dlc_hardware", hardware_available=True
                ),
                value["qualification"]["route_inventory"][0].update(
                    qualification_status="not_qualified"
                ),
            ),
        )
        self.assertEqual(result.returncode, 24, result.stdout)
        self.assertFalse(marker.exists())
        self.assertEqual(document["resume_point"], "collective_qualification")
        self.assertIsNone(document["qualification"]["execution"])

        resumed, resumed_document = self.run_runner("harness-pass.py", "--controlled-harness")
        self.assertTrue(json.loads(resumed.stdout)["launched"])
        self.assertIsNotNone(resumed_document["qualification"]["execution"])

    def test_formal_acceptance_request_is_refused_before_launch(self):
        result, document = self.run_runner(
            "harness-pass.py",
            "--controlled-harness",
            mutate=lambda value: value["qualification"]["preflight"].update(requested_operation="formal_acceptance"),
        )
        self.assertEqual(result.returncode, 24)
        self.assertFalse(json.loads(result.stdout)["launched"])
        self.assertEqual(document["primary_blocker"]["code"], "blocked_dangerous_operation")


if __name__ == "__main__":
    unittest.main()
