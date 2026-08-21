import json
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts" / "workflow-behavior" / "validate-manifest.py"
RUNNER = ROOT / "scripts" / "workflow-behavior" / "run-manifest.py"


def load_runner():
    script_directory = str(RUNNER.parent)
    sys.path.insert(0, script_directory)
    try:
        spec = importlib.util.spec_from_file_location("workflow_behavior_runner", RUNNER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(script_directory)


def manifest(fixture="case.json", adapter="test-fixture-owner"):
    return {
        "schema": "workflow-behavior-manifest/v1",
        "fixture_root": "fixtures",
        "cases": [
            {
                "id": "owner-case",
                "workflow": "owner-workflow",
                "quality_kind": "behavior",
                "fixture": fixture,
                "adapter": adapter,
                "expected_exit_codes": [0],
                "assertions": [
                    {"path": "$.terminal_state", "op": "equals", "value": "passed"},
                    {"path": "$.claim_boundary", "op": "starts_with", "value": "Claim Boundary:"},
                    {"path": "$.authoritative", "op": "equals", "value": False},
                ],
                "fixture_authority": "fixture_only",
                "forbidden_actions": ["runtime_acceptance", "publication", "workspace_mutation"],
            }
        ],
    }


class WorkflowBehaviorManifestTests(unittest.TestCase):
    def invoke(self, script, value, setup=None):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            root = Path(directory)
            fixtures = root / "fixtures"
            fixtures.mkdir()
            (fixtures / "case.json").write_text("{}", encoding="utf-8")
            if setup:
                setup(root)
            path = root / "manifest.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            result = subprocess.run(
                ["python3", str(script), str(path), "--repo-root", str(ROOT)],
                capture_output=True,
                text=True,
                check=False,
            )
        return result, json.loads(result.stdout)

    def test_closed_world_manifest_is_accepted(self):
        result, report = self.invoke(VALIDATOR, manifest())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report["terminal_state"], "manifest_valid")

    def test_unknown_fields_and_non_allowlisted_adapters_fail_closed(self):
        values = [manifest(), manifest(adapter="python3 -c"), manifest()]
        values[0]["cases"][0]["owner_matrix"] = []
        values[2]["cases"][0]["argv"] = ["python3", "-c", "print('unsafe')"]
        for value in values:
            with self.subTest(value=value):
                result, report = self.invoke(VALIDATOR, value)
                self.assertEqual(result.returncode, 3)
                self.assertEqual(report["terminal_state"], "invalid_manifest")

    def test_arbitrary_command_adapters_are_rejected(self):
        for executable in ("python -c", "git", "rm", "test-fixture-owner-mutation"):
            with self.subTest(executable=executable):
                result, report = self.invoke(VALIDATOR, manifest(adapter=executable))
                self.assertEqual(result.returncode, 3)
                self.assertIn("adapter_allowlist", report["problems"])

    def test_fixture_parent_traversal_and_symlink_escape_are_rejected(self):
        result, _ = self.invoke(VALIDATOR, manifest(fixture="../outside.json"))
        self.assertEqual(result.returncode, 3)

        def setup(root):
            (root / "outside.json").write_text("{}", encoding="utf-8")
            (root / "fixtures" / "link.json").symlink_to(root / "outside.json")

        result, report = self.invoke(VALIDATOR, manifest(fixture="link.json"), setup)
        self.assertEqual(result.returncode, 3)
        self.assertIn("fixture_containment", report["problems"])

    def test_manifest_type_errors_are_stable_machine_json(self):
        mutations = (
            lambda value: value.update(schema=[]),
            lambda value: value["cases"].__setitem__(0, []),
            lambda value: value["cases"][0].update(quality_kind=[]),
            lambda value: value["cases"][0].update(adapter={}),
            lambda value: value["cases"][0].update(expected_exit_codes=[{}]),
            lambda value: value["cases"][0]["assertions"][0].update(op=[]),
            lambda value: value["cases"][0]["assertions"][0].update(op="starts_with", value={}),
            lambda value: value["cases"][0].update(forbidden_actions=[{}]),
        )
        for mutate in mutations:
            value = manifest()
            mutate(value)
            with self.subTest(value=value):
                result, report = self.invoke(VALIDATOR, value)
                self.assertEqual(result.returncode, 3)
                self.assertEqual(report["terminal_state"], "invalid_manifest")
                self.assertEqual(result.stderr, "")

    def test_runner_rejects_substitute_repository_root(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            result, report = self.invoke(RUNNER, manifest(), setup=lambda _root: None)
            path = Path(directory)
            substitute = subprocess.run(
                ["python3", str(RUNNER), str(path / "missing.json"), "--repo-root", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
        substitute_report = json.loads(substitute.stdout)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(report["terminal_state"], "suite_passed")
        self.assertEqual(substitute.returncode, 3)
        self.assertEqual(substitute_report["terminal_state"], "invalid_repository_root")

    def test_runner_reports_machine_json_assertion_failure(self):
        value = manifest()
        value["cases"][0]["assertions"][0]["value"] = "failed"
        result, report = self.invoke(RUNNER, value)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(report["terminal_state"], "suite_failed")
        self.assertEqual(report["cases"][0]["terminal_state"], "assertion_failed")

    def test_runner_binds_manifest_cases_and_repository_snapshot(self):
        value = manifest()
        result, report = self.invoke(RUNNER, value)
        self.assertEqual(result.returncode, 0, result.stderr)
        binding = report["run_binding"]
        self.assertRegex(binding["manifest_digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(binding["case_ids"], ["owner-case"])
        self.assertRegex(binding["repository_head"], r"^[0-9a-f]{40}$")
        self.assertRegex(binding["repository_status_digest"], r"^[0-9a-f]{64}$")
        self.assertRegex(binding["repository_snapshot_digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(binding["repository_snapshot_digest"], report["cases"][0]["repository_after"]["snapshot_digest"])

    def test_claim_boundary_requires_literal_marker_and_negative_semantics(self):
        runner = load_runner()
        self.assertTrue(runner.claim_boundary_preserved({"claim_boundary": "Claim Boundary: this does not establish runtime acceptance."}))
        self.assertFalse(runner.claim_boundary_preserved({"claim_boundary": "This does not establish runtime acceptance."}))
        self.assertFalse(runner.claim_boundary_preserved({"claim_boundary": "Claim Boundary: runtime acceptance established."}))


if __name__ == "__main__":
    unittest.main()
