import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "engineering" / "pytorch-dlc-plugin-migration" / "scripts" / "evaluate-plugin-migration.py"


def evidence(status, owner, artifact="sha256:" + "1" * 64, fresh=True):
    return {"status": status, "owner": owner, "artifact_path": "", "artifact_id": artifact, "fresh": fresh, "authority": "operational_only"}


def valid_result():
    return {
        "schema": "io.chipltech.plugin-migration-evidence/v1",
        "source_governance": evidence("not_applicable", "restricted-reference-governance"),
        "source_migration": evidence("pass", "pytorch-dlc-plugin-migration"),
        "compile_link": evidence("pass", "pytorch-dlc-plugin-migration"),
        "wheel_import": evidence("pass", "pytorch-dlc-plugin-migration"),
        "stack_preflight": evidence("pass", "dlc-env-setup"),
        "package_seal": evidence("pass", "package-provider"),
        "dlc_runtime_execution": evidence("pass", "dlc-env-setup"),
        "real_dlc_hardware_behavior": evidence("pass", "pytorch-dlc-plugin-migration"),
        "smi_observation": evidence("pass", "dlc-hardware-observability"),
        "distributed_behavior": evidence("not_applicable", "distributed-qualification"),
        "cleanup": evidence("pass", "dlc-hardware-observability"),
        "device_deferral_permitted": False,
    }


class PluginMigrationResultContractTests(unittest.TestCase):
    def evaluate(self, mutate=None):
        payload = valid_result()
        if mutate:
            mutate(payload)
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            root = Path(directory)
            for field, item in payload.items():
                if isinstance(item, dict) and "artifact_path" in item:
                    artifact = root / f"{field}.json"
                    artifact.write_text(field, encoding="utf-8")
                    item["artifact_path"] = str(artifact)
                    item["artifact_id"] = "sha256:" + __import__("hashlib").sha256(field.encode()).hexdigest()
            path = Path(directory) / "result.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = subprocess.run(["python3", str(SCRIPT), str(path)], capture_output=True, text=True, check=False)
        return result, json.loads(result.stdout)

    def test_all_owner_bound_evidence_closes_each_dimension(self):
        result, report = self.evaluate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report["terminal_state"], "all_declared_dimensions_passed")
        self.assertFalse(report["authoritative"])
        self.assertFalse(report["acceptance_eligible"])

    def test_unresolved_reference_stops_at_legal_boundary(self):
        result, report = self.evaluate(lambda value: value["source_governance"].update(status="unresolved"))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(report["terminal_state"], "blocked_legal_boundary")

    def test_missing_preflight_is_not_device_validated(self):
        _, report = self.evaluate(lambda value: value["stack_preflight"].update(status="missing"))
        self.assertEqual(report["terminal_state"], "blocked_missing_preflight")

    def test_stale_package_seal_blocks_runtime_claim(self):
        _, report = self.evaluate(lambda value: value["package_seal"].update(fresh=False))
        self.assertEqual(report["terminal_state"], "blocked_stale_package_seal")

    def test_stale_owner_evidence_blocks_all_dimensions(self):
        _, report = self.evaluate(lambda value: value["stack_preflight"].update(fresh=False))
        self.assertEqual(report["terminal_state"], "blocked_stale_owner_evidence")

    def test_wrong_owner_fails_contract(self):
        result, report = self.evaluate(lambda value: value["smi_observation"].update(owner="migration"))
        self.assertEqual(result.returncode, 3)
        self.assertEqual(report["terminal_state"], "invalid_contract")

    def test_unqualified_distributed_route_is_independent(self):
        _, report = self.evaluate(lambda value: value["distributed_behavior"].update(status="unqualified"))
        self.assertEqual(report["terminal_state"], "blocked_distributed_route_unqualified")

    def test_cleanup_incomplete_has_highest_precedence(self):
        def mutate(value):
            value["stack_preflight"].update(status="missing")
            value["cleanup"].update(status="incomplete")
        _, report = self.evaluate(mutate)
        self.assertEqual(report["terminal_state"], "blocked_cleanup_incomplete")

    def test_permitted_device_deferral_is_separate_from_validation(self):
        def mutate(value):
            value["device_deferral_permitted"] = True
            value["dlc_runtime_execution"].update(status="not_verified")
            value["real_dlc_hardware_behavior"].update(status="not_verified")
        _, report = self.evaluate(mutate)
        self.assertEqual(report["terminal_state"], "implementation_complete_tests_deferred")

    def test_device_deferral_requires_build_and_package_closure(self):
        def mutate(value):
            value["device_deferral_permitted"] = True
            value["dlc_runtime_execution"].update(status="not_verified")
            value["compile_link"].update(status="not_verified")
        _, report = self.evaluate(mutate)
        self.assertEqual(report["terminal_state"], "not_verified")

    def test_unsupported_production_behavior_is_explicit(self):
        _, report = self.evaluate(lambda value: value["source_migration"].update(status="unsupported"))
        self.assertEqual(report["terminal_state"], "unsupported_by_production_backend")

    def test_unknown_fields_fail_closed(self):
        result, report = self.evaluate(lambda value: value.update(unexpected=True))
        self.assertEqual(result.returncode, 3)
        self.assertEqual(report["terminal_state"], "invalid_contract")


if __name__ == "__main__":
    unittest.main()
