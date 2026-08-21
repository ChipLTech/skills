import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "engineering" / "pd-separation" / "scripts" / "evaluate-pd-gates.py"
CORE_GATES = (
    "static_configuration",
    "transport_qualification",
    "service_readiness",
    "request_routing",
    "kv_transfer",
    "functional_equivalence",
    "lifecycle_cleanup",
    "site_recovery",
)


def valid_contract():
    gates = {name: {"status": "pass", "reason": None, "blocker": None} for name in CORE_GATES}
    gates["performance_workload"] = {"status": "not_requested", "reason": None, "blocker": None}
    gates["stability_baseline"] = {"status": "not_requested", "reason": None, "blocker": None}
    return {
        "schema": "io.chipltech.pd-gate-evaluation/v1",
        "gates": gates,
        "mandatory_optional_gates": [],
    }


class PDGateAggregationTests(unittest.TestCase):
    def evaluate(self, mutate=None):
        value = valid_contract()
        if mutate:
            mutate(value)
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            path = Path(directory) / "gates.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            result = subprocess.run(
                ["python3", str(SCRIPT), str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
        return result, json.loads(result.stdout)

    def test_all_applicable_core_gates_pass(self):
        result, report = self.evaluate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report["terminal_state"], "pd_validated")
        self.assertEqual(report["primary_blocker"], None)
        self.assertFalse(report["authoritative"])
        self.assertFalse(report["runtime_acceptance"])

    def test_cleanup_incomplete_has_highest_precedence(self):
        def mutate(value):
            value["gates"]["transport_qualification"].update(
                status="blocked", blocker="blocked_transport_unqualified", reason="payload mismatch"
            )
            value["gates"]["lifecycle_cleanup"].update(
                status="blocked", blocker="blocked_cleanup_incomplete", reason="port remains owned"
            )

        result, report = self.evaluate(mutate)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(report["terminal_state"], "blocked_cleanup_incomplete")
        self.assertEqual(report["primary_blocker"]["gate"], "lifecycle_cleanup")
        self.assertEqual(len(report["active_blockers"]), 2)

    def test_earliest_workflow_blocker_is_primary_and_all_are_reported(self):
        def mutate(value):
            value["gates"]["request_routing"].update(
                status="blocked", blocker="blocked_network_unreachable", reason="proxy route unavailable"
            )
            value["gates"]["site_recovery"].update(
                status="blocked", blocker="blocked_missing_authorization", reason="recovery not authorized"
            )

        _, report = self.evaluate(mutate)
        self.assertEqual(report["terminal_state"], "blocked_network_unreachable")
        self.assertEqual(report["primary_blocker"]["gate"], "request_routing")
        self.assertEqual(
            [item["gate"] for item in report["active_blockers"]],
            ["request_routing", "site_recovery"],
        )

    def test_failed_mandatory_gate_precedes_not_executed_gate(self):
        def mutate(value):
            value["gates"]["kv_transfer"].update(status="failed", reason="content mismatch")
            value["gates"]["functional_equivalence"].update(status="not_executed", reason="stopped after failure")

        _, report = self.evaluate(mutate)
        self.assertEqual(report["terminal_state"], "failed_validation")

    def test_unexecuted_mandatory_gate_is_not_verified(self):
        _, report = self.evaluate(
            lambda value: value["gates"]["kv_transfer"].update(status="not_executed", reason="no correlated request")
        )
        self.assertEqual(report["terminal_state"], "not_verified")

    def test_optional_dimensions_do_not_downgrade_core_unless_mandatory(self):
        def optional_failure(value):
            value["gates"]["performance_workload"].update(status="failed", reason="target missed")

        _, report = self.evaluate(optional_failure)
        self.assertEqual(report["terminal_state"], "pd_validated")
        self.assertEqual(report["dimensions"]["performance_workload"]["status"], "failed")

        def mandatory_failure(value):
            optional_failure(value)
            value["mandatory_optional_gates"] = ["performance_workload"]

        _, report = self.evaluate(mandatory_failure)
        self.assertEqual(report["terminal_state"], "failed_validation")

    def test_site_recovery_may_be_not_applicable(self):
        _, report = self.evaluate(
            lambda value: value["gates"]["site_recovery"].update(status="not_applicable", reason="no disruption")
        )
        self.assertEqual(report["terminal_state"], "pd_validated")

    def test_unknown_fields_and_invalid_blocker_shape_fail_closed(self):
        for mutate in (
            lambda value: value.update(extra=True),
            lambda value: value["gates"]["kv_transfer"].update(blocker="blocked_transport_unqualified"),
        ):
            with self.subTest(mutate=mutate):
                result, report = self.evaluate(mutate)
                self.assertEqual(result.returncode, 3)
                self.assertEqual(report["terminal_state"], "invalid_contract")


if __name__ == "__main__":
    unittest.main()
