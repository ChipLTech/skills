import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "tests" / "workflow_behavior" / "fixtures" / "representative-manifest.json"
VALIDATOR = ROOT / "scripts" / "workflow-behavior" / "validate-manifest.py"
RUNNER = ROOT / "scripts" / "workflow-behavior" / "run-manifest.py"
PROJECTOR = ROOT / "scripts" / "workflow-behavior" / "project-quality.py"


class RepresentativeWorkflowBehaviorTests(unittest.TestCase):
    def invoke(self, script, *arguments):
        result = subprocess.run(
            ["python3", str(script), *map(str, arguments)],
            capture_output=True,
            text=True,
            check=False,
            cwd=ROOT,
        )
        return result, json.loads(result.stdout)

    def test_manifest_calls_representative_owner_interfaces(self):
        result, report = self.invoke(VALIDATOR, MANIFEST, "--repo-root", ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report["case_count"], 8)

        result, report = self.invoke(RUNNER, MANIFEST, "--repo-root", ROOT)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(report["terminal_state"], "suite_passed")
        self.assertEqual(
            {case["workflow"] for case in report["cases"]},
            {
                "pd-separation",
                "pytorch-dlc-plugin-migration",
                "model-adaptation-report-routing",
                "technical-delivery-summary",
                "topology-selection",
                "technical-issue-summary",
                "publication-candidate",
                "publication-candidate-stale-lease",
            },
        )
        self.assertTrue(all(not case["authoritative"] for case in report["cases"]))
        self.assertTrue(all(not case["runtime_acceptance"] for case in report["cases"]))
        self.assertTrue(all(case["repository_before"] == case["repository_after"] for case in report["cases"]))
        self.assertEqual(report["run_binding"]["case_ids"], [case["id"] for case in report["cases"]])
        self.assertRegex(report["run_binding"]["repository_head"], r"^[0-9a-f]{40}$")
        self.assertRegex(report["run_binding"]["repository_status_digest"], r"^[0-9a-f]{64}$")
        self.assertRegex(report["run_binding"]["repository_snapshot_digest"], r"^sha256:[0-9a-f]{64}$")

    def test_quality_projection_separates_behavior_and_contract_static(self):
        run_result, run_report = self.invoke(RUNNER, MANIFEST, "--repo-root", ROOT)
        self.assertEqual(run_result.returncode, 0)
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            result_path = Path(directory) / "representative-result.json"
            result_path.write_text(json.dumps(run_report), encoding="utf-8")
            result, projection = self.invoke(PROJECTOR, result_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("score", projection)
        self.assertNotIn("runtime_acceptance", projection["claims"])
        self.assertEqual(projection["fixture_authority"], "never_authoritative")
        self.assertEqual(
            [item["workflow"] for item in projection["contract_static"]],
            ["technical-issue-summary"],
        )
        behavior = {item["workflow"]: item for item in projection["behavior"]}
        self.assertEqual(behavior["publication-candidate"]["state"], "not_proposed")
        self.assertEqual(behavior["publication-candidate-stale-lease"]["state"], "blocked")
        self.assertEqual(behavior["publication-candidate-stale-lease"]["blocker"], "lease.target_base_mismatch")
        self.assertEqual(behavior["topology-selection"]["reason"], "blocked_missing_hardware")
        self.assertEqual(behavior["topology-selection"]["blocker"], "blocked_missing_hardware")
        self.assertIn("performance_workload", behavior["pd-separation"]["dimensions"])
        self.assertTrue(all("blocker" in item and "resume_point" in item for item in projection["behavior"] + projection["contract_static"]))
        self.assertTrue(all(item["claim_boundary_preserved"] for item in projection["behavior"]))
        self.assertTrue(all(not item["forbidden_action_preserved"] for item in projection["behavior"]))
        self.assertTrue(all(item["quality"]["not_reported"] for item in projection["behavior"]))
        self.assertIn("workspace_mutation", behavior["pd-separation"]["quality"]["observed"])
        self.assertIn("device_execution", behavior["pd-separation"]["quality"]["not_reported"])
        self.assertIn("hardware_execution", behavior["topology-selection"]["quality"]["not_reported"])
        static = projection["contract_static"][0]
        self.assertNotIn("forbidden_action_preserved", static)
        self.assertNotIn("quality", static)

    def test_projection_never_reports_forbidden_actions_as_preserved(self):
        run = {
            "schema": "workflow-behavior-run-result/v1",
            "cases": [{
                "workflow": "workspace-only",
                "quality_kind": "behavior",
                "terminal_state": "passed",
                "owner_terminal_state": "passed",
                "owner_reason": None,
                "owner_dimensions": {},
                "owner_blocker": None,
                "owner_resume_point": None,
                "claim_boundary_preserved": True,
                "forbidden_actions": ["workspace_mutation"],
                "workspace_mutation_observed": False,
            }],
        }
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            result_path = Path(directory) / "run.json"
            result_path.write_text(json.dumps(run), encoding="utf-8")
            result, projection = self.invoke(PROJECTOR, result_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        row = projection["behavior"][0]
        self.assertFalse(row["forbidden_action_preserved"])
        self.assertEqual(row["quality"], {"observed": ["workspace_mutation"], "not_reported": []})


if __name__ == "__main__":
    unittest.main()
