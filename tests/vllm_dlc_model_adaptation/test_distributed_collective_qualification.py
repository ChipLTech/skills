import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "skills" / "engineering" / "model-adaptation" / "scripts" / "validate-vllm-dlc-qualification.py"
FIXTURES = Path(__file__).with_name("fixtures") / "distributed-collective"
SPEC = importlib.util.spec_from_file_location("qualification_contract_test", VALIDATOR)
assert SPEC is not None and SPEC.loader is not None
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)


class DistributedCollectiveQualificationTests(unittest.TestCase):
    def document(self):
        document = json.loads((FIXTURES / "qualified-controlled-template.json").read_text())
        document["digest"] = CONTRACT.artifact_digest(document)
        return document

    def run_document(self, document):
        document["digest"] = CONTRACT.artifact_digest(document)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", dir="/tmp/kilo") as fixture:
            json.dump(document, fixture)
            fixture.flush()
            return subprocess.run(
                [sys.executable, str(VALIDATOR), fixture.name],
                capture_output=True,
                text=True,
                check=False,
            )

    def normalize(self, document):
        CONTRACT.normalize_status(document)

    def test_fixture_has_closed_world_routes_and_no_hardware_is_not_verified(self):
        result = self.run_document(self.document())
        self.assertEqual(result.returncode, 0, result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "not_verified")
        self.assertEqual(report["reason_code"], "blocked_missing_hardware")
        self.assertEqual(report["resume_point"], "real_dlc_hardware_allocation")
        self.assertFalse(report["launch_allowed"])
        self.assertTrue(report["claim_boundary"].startswith("Claim Boundary:"))

    def test_unknown_field_and_missing_route_class_fail_closed(self):
        unknown = self.document()
        unknown["surprise"] = True
        result = self.run_document(unknown)
        self.assertEqual(result.returncode, 20)
        self.assertEqual(json.loads(result.stdout)["checks"][0]["code"], "contract.unknown_field")

        missing = self.document()
        missing["qualification"]["route_inventory"] = [
            route for route in missing["qualification"]["route_inventory"]
            if route["route_class"] != "custom_kernel"
        ]
        missing["qualification"]["required_route_ids"].remove("custom-kernel-dispatch")
        self.normalize(missing)
        result = self.run_document(missing)
        self.assertEqual(result.returncode, 20)
        self.assertEqual(json.loads(result.stdout)["checks"][0]["code"], "contract.missing_required_route_class")

    def test_active_route_and_anti_route_are_distinct(self):
        document = self.document()
        route = document["qualification"]["route_inventory"][2]
        route["active"] = False
        document["qualification"]["required_route_ids"].remove(route["route_id"])
        route["qualification_status"] = "not_applicable"
        self.normalize(document)
        result = self.run_document(document)
        self.assertEqual(result.returncode, 0, result.stdout)

        inconsistent = copy.deepcopy(document)
        inconsistent["qualification"]["required_route_ids"].append(route["route_id"])
        result = self.run_document(inconsistent)
        self.assertEqual(result.returncode, 20)
        self.assertEqual(json.loads(result.stdout)["checks"][0]["path"], "$.qualification.required_route_ids")

    def test_unsupported_and_unqualified_active_routes_block_before_launch(self):
        for state, expected, resume in (
            ("unsupported", "blocked_collective_unimplemented", "route_implementation"),
            ("not_qualified", "blocked_collective_not_qualified", "collective_qualification"),
        ):
            with self.subTest(state=state):
                document = self.document()
                document["qualification"]["preflight"].update(hardware_environment="real_dlc_hardware", hardware_available=True)
                document["qualification"]["route_inventory"][0]["qualification_status"] = state
                self.normalize(document)
                document["status"] = "blocked"
                result = self.run_document(document)
                self.assertEqual(result.returncode, 0, result.stdout)
                report = json.loads(result.stdout)
                self.assertEqual(report["reason_code"], expected)
                self.assertEqual(report["resume_point"], resume)
                self.assertFalse(report["launch_allowed"])

    def test_real_qualification_fails_closed_without_trusted_external_inputs(self):
        document = self.document()
        document["qualification"]["preflight"].update(
            hardware_environment="real_dlc_hardware", hardware_available=True
        )
        self.normalize(document)
        result = self.run_document(document)
        self.assertEqual(result.returncode, 0, result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason_code"], "blocked_missing_trusted_qualification_inputs")
        self.assertEqual(report["resume_point"], "trusted_qualification_inputs")
        self.assertFalse(report["launch_allowed"])

    def test_real_hardware_observe_without_execution_cannot_pass(self):
        document = self.document()
        document["qualification"]["preflight"].update(
            hardware_environment="real_dlc_hardware",
            hardware_available=True,
            requested_operation="observe",
        )
        self.normalize(document)
        result = self.run_document(document)
        self.assertEqual(result.returncode, 0, result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "not_verified")
        self.assertEqual(report["reason_code"], "blocked_missing_execution_evidence")

    def test_missing_identity_authorization_and_hardware_preserve_blocker_fidelity(self):
        cases = [
            (lambda value: value["qualification"]["route_inventory"][0]["identity"].update(binary_sha256=None), "blocked_missing_identity", "route_identity"),
            (lambda value: value["qualification"]["preflight"].update(authorization_granted=False), "blocked_missing_authorization", "launch_authorization"),
            (lambda value: None, "blocked_missing_hardware", "real_dlc_hardware_allocation"),
        ]
        for mutate, code, resume in cases:
            with self.subTest(code=code):
                document = self.document()
                mutate(document)
                self.normalize(document)
                result = self.run_document(document)
                self.assertEqual(result.returncode, 0, result.stdout)
                report = json.loads(result.stdout)
                self.assertEqual(report["reason_code"], code)
                self.assertEqual(report["resume_point"], resume)

    def test_dangerous_operation_is_refused_with_literal_claim_boundary(self):
        document = self.document()
        document["qualification"]["preflight"]["requested_operation"] = "formal_acceptance"
        self.normalize(document)
        result = self.run_document(document)
        self.assertEqual(result.returncode, 0, result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["reason_code"], "blocked_dangerous_operation")
        self.assertFalse(report["acceptance_eligible"])
        self.assertTrue(report["claim_boundary"].startswith("Claim Boundary:"))

    def test_producer_never_has_formal_acceptance_authority(self):
        for mutation, path in (
            (lambda value: value.update(evidence_class="formal_acceptance"), "$.evidence_class"),
            (lambda value: value.update(acceptance_eligible=True), "$.acceptance_eligible"),
        ):
            document = self.document()
            mutation(document)
            result = self.run_document(document)
            self.assertEqual(result.returncode, 20)
            self.assertEqual(json.loads(result.stdout)["checks"][0]["path"], path)

    def test_rank_exit_code_and_status_cannot_contradict(self):
        document = self.document()
        execution = copy.deepcopy(document["qualification"]["execution"])
        self.assertIsNone(execution)
        document["qualification"]["execution"] = {
            "harness_command": ["fixture"], "attempt_count": 1,
            "timeout_seconds": 1, "watchdog_actions": ["started", "reaped"],
            "rank_results": [{"attempt": 1, "rank": rank, "exit_code": 7, "status": "passed"} for rank in range(2)],
            "correctness": [{"attempt": 1, "status": "passed", "primitive_results": [
                {"primitive": oracle["primitive"], "expected_digest": oracle["expected_digest"], "actual_digest": oracle["expected_digest"], "status": "passed"}
                for oracle in document["qualification"]["correctness_oracles"]
            ]}],
            "process_tree_cleanup": {"termination_requested": False, "inspection_complete": True, "residual_pids": [], "hbm_status": "not_verified", "status": "passed"},
            "health_snapshot": {"status": "not_verified", "source": "controlled_fixture", "snapshot_digest": None},
        }
        self.normalize(document)
        result = self.run_document(document)
        self.assertEqual(result.returncode, 20)
        self.assertEqual(json.loads(result.stdout)["checks"][0]["code"], "contract.inconsistent_status")


if __name__ == "__main__":
    unittest.main()
