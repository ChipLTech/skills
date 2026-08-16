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
    def document(self, version="v1"):
        document = json.loads((FIXTURES / "qualified-controlled-template.json").read_text())
        if version == "v2":
            selection = json.loads((FIXTURES / "qualified-controlled-v2-base.json").read_text())
            document["schema_version"] = "vllm-dlc-distributed-collective-qualification/v2"
            for route in document["qualification"]["route_inventory"]:
                route["selection"] = None
            document["qualification"]["route_inventory"][2].update(
                rank_order=[1, 0], selection=selection
            )
            CONTRACT.refresh_selection_digests(
                selection, document["qualification"]["route_inventory"][2]
            )
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

    def test_v1_is_frozen_and_v2_requires_exact_selection_shape(self):
        v1 = self.document()
        v1["qualification"]["route_inventory"][2]["selection"] = None
        result = self.run_document(v1)
        self.assertEqual(result.returncode, 20)
        self.assertEqual(json.loads(result.stdout)["checks"][0]["code"], "contract.unknown_field")

        v2 = self.document("v2")
        result = self.run_document(v2)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)["schema_version"], "vllm-dlc-distributed-collective-qualification/v2")

        del v2["qualification"]["route_inventory"][2]["selection"]["selector"]
        result = self.run_document(v2)
        self.assertEqual(result.returncode, 20)
        self.assertEqual(json.loads(result.stdout)["checks"][0]["path"], "$.qualification.route_inventory[2].selection.selector")

    def test_v2_accepts_complete_non_natural_rank_permutation(self):
        document = self.document("v2")
        selection = document["qualification"]["route_inventory"][2]["selection"]
        self.assertEqual(selection["rank_order"], [1, 0])
        result = self.run_document(document)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_v2_rejects_incomplete_duplicate_and_out_of_range_rank_order(self):
        for rank_order in ([1], [1, 1], [1, 2]):
            with self.subTest(rank_order=rank_order):
                document = self.document("v2")
                document["qualification"]["route_inventory"][2]["selection"]["rank_order"] = rank_order
                result = self.run_document(document)
                self.assertEqual(result.returncode, 20)
                self.assertEqual(json.loads(result.stdout)["checks"][0]["path"], "$.qualification.route_inventory[2].selection.rank_order")

    def test_v2_validates_thresholds_and_payload_alignment(self):
        for payload, alignment, expected in ((128, 64, 0), (256, 64, 0), (127, 64, 20), (257, 64, 20), (192, 128, 20)):
            with self.subTest(payload=payload, alignment=alignment):
                document = self.document("v2")
                selection = document["qualification"]["route_inventory"][2]["selection"]
                selection["payload_bytes"] = payload
                selection["constraints"]["payload_alignment_bytes"] = alignment
                CONTRACT.refresh_selection_digests(
                    selection, document["qualification"]["route_inventory"][2]
                )
                result = self.run_document(document)
                self.assertEqual(result.returncode, expected, result.stdout)

    def test_v2_rejects_missing_out_of_range_duplicate_root_and_unknown_mapping(self):
        cases = (
            (lambda selection: selection["rank_domain"].pop("primary_root"), ".primary_root"),
            (lambda selection: selection["rank_domain"].update(primary_root=2), ".primary_root"),
            (lambda selection: selection["rank_domain"].update(secondary_root=1), ".secondary_root"),
            (lambda selection: selection["rank_domain"].update(secondary_root=None), ".secondary_root"),
            (lambda selection: selection["rank_domain"].update(domain="unknown"), ".domain"),
        )
        for mutate, suffix in cases:
            with self.subTest(suffix=suffix):
                document = self.document("v2")
                selection = document["qualification"]["route_inventory"][2]["selection"]
                mutate(selection)
                result = self.run_document(document)
                self.assertEqual(result.returncode, 20)
                self.assertTrue(json.loads(result.stdout)["checks"][0]["path"].endswith(suffix))

    def test_v2_rejects_partial_fallback_and_strategy_rank_contradictions(self):
        cases = (
            lambda selection: selection["fallback"]["validation"].update(graph=False),
            lambda selection: selection["strategy"].update(rank_domain="physical"),
            lambda selection: selection["strategy"].update(metadata_abi_digest="sha256:" + "e" * 64),
            lambda selection: selection["fallback"].update(candidate_strategy_id="other"),
        )
        for mutate in cases:
            document = self.document("v2")
            selection = document["qualification"]["route_inventory"][2]["selection"]
            mutate(selection)
            result = self.run_document(document)
            self.assertEqual(result.returncode, 20)

    def test_v2_requires_exact_selection_identities(self):
        mutations = (
            lambda selection: selection["selector"].update(source_sha=None),
            lambda selection: selection["selector"].update(binary_sha256=None),
            lambda selection: selection.update(topology_digest=None),
            lambda selection: selection["strategy"].update(
                metadata_abi_digest=None
            ),
        )
        for mutate in mutations:
            document = self.document("v2")
            selection = document["qualification"]["route_inventory"][2]["selection"]
            mutate(selection)
            result = self.run_document(document)
            self.assertEqual(result.returncode, 20)

    def test_v2_fallback_validate_then_commit_states_are_consistent(self):
        valid_states = (
            ("unknown", False, False),
            ("validating", False, False),
            ("passed", True, False),
            ("passed", True, True),
            ("failed", False, False),
        )
        for state, complete, committed in valid_states:
            with self.subTest(state=state, committed=committed):
                document = self.document("v2")
                route = document["qualification"]["route_inventory"][2]
                fallback = route["selection"]["fallback"]
                fallback["validation_state"] = state
                fallback["validation"] = {
                    field: complete
                    for field in CONTRACT.FALLBACK_VALIDATION_FIELDS
                }
                if state in {"validating", "failed"}:
                    fallback["validation"]["graph"] = True
                fallback["committed"] = committed
                if not committed:
                    route["selection"]["strategy"]["strategy_id"] = fallback[
                        "preferred_strategy_id"
                    ]
                CONTRACT.refresh_selection_digests(route["selection"], route)
                result = self.run_document(document)
                self.assertEqual(result.returncode, 0, result.stdout)

        contradictions = (
            ("unknown", True, False),
            ("validating", True, False),
            ("passed", False, False),
            ("failed", True, False),
            ("validating", False, True),
        )
        for state, complete, committed in contradictions:
            with self.subTest(state=state, contradiction=True):
                document = self.document("v2")
                route = document["qualification"]["route_inventory"][2]
                fallback = route["selection"]["fallback"]
                fallback["validation_state"] = state
                fallback["validation"] = {
                    field: complete
                    for field in CONTRACT.FALLBACK_VALIDATION_FIELDS
                }
                fallback["committed"] = committed
                if not committed:
                    route["selection"]["strategy"]["strategy_id"] = fallback[
                        "preferred_strategy_id"
                    ]
                CONTRACT.refresh_selection_digests(route["selection"], route)
                result = self.run_document(document)
                self.assertEqual(result.returncode, 20)

    def test_v2_cache_key_binds_dtype_strategy_and_fallback(self):
        mutations = (
            lambda route: (
                route.update(dtype="float32"),
                route["selection"]["constraints"]["dtypes"].append("float32"),
            ),
            lambda route: (
                route["selection"]["strategy"].update(
                    strategy_id="different-strategy"
                ),
                route["selection"]["fallback"].update(
                    candidate_strategy_id="different-strategy"
                ),
            ),
            lambda route: (
                route["selection"]["fallback"].update(
                    candidate_strategy_id="different-fallback",
                    committed=False,
                ),
                route["selection"]["fallback"].update(
                    preferred_strategy_id=route["selection"]["strategy"]["strategy_id"]
                ),
            ),
        )
        for mutate in mutations:
            document = self.document("v2")
            route = document["qualification"]["route_inventory"][2]
            mutate(route)
            result = self.run_document(document)
            self.assertEqual(result.returncode, 20)
            self.assertEqual(
                json.loads(result.stdout)["checks"][0]["code"],
                "contract.cache_key_digest_mismatch",
            )

    def test_v2_malformed_nested_values_are_contract_errors(self):
        mutations = (
            lambda route: route["selection"]["constraints"].update(dtypes=[{}]),
            lambda route: route.update(identity=None),
            lambda route: route["selection"]["rank_domain"].update(domain={}),
            lambda route: route["selection"]["fallback"].update(validation_state=[]),
            lambda route: route.update(route_class={}),
        )
        for mutate in mutations:
            document = self.document("v2")
            mutate(document["qualification"]["route_inventory"][2])
            result = self.run_document(document)
            self.assertEqual(result.returncode, 20, result.stderr)
            self.assertEqual(result.stderr, "")
            self.assertTrue(json.loads(result.stdout)["checks"][0]["code"].startswith("contract."))

        document = self.document("v2")
        document["qualification"]["preflight"]["requested_operation"] = []
        result = self.run_document(document)
        self.assertEqual(result.returncode, 20, result.stderr)
        self.assertEqual(result.stderr, "")

    def test_v2_selection_topology_matches_subject_identity(self):
        document = self.document("v2")
        route = document["qualification"]["route_inventory"][2]
        route["selection"]["topology_digest"] = "sha256:" + "e" * 64
        CONTRACT.refresh_selection_digests(route["selection"], route)

        result = self.run_document(document)

        self.assertEqual(result.returncode, 20)
        self.assertEqual(
            json.loads(result.stdout)["checks"][0]["code"],
            "contract.identity_mismatch",
        )

    def test_v2_selection_is_owned_only_by_the_communicator(self):
        document = self.document("v2")
        communicator = document["qualification"]["route_inventory"][2]
        process_group = document["qualification"]["route_inventory"][1]
        process_group["selection"] = copy.deepcopy(communicator["selection"])
        CONTRACT.refresh_selection_digests(process_group["selection"], process_group)

        result = self.run_document(document)

        self.assertEqual(result.returncode, 20)
        self.assertEqual(
            json.loads(result.stdout)["checks"][0]["path"],
            "$.qualification.route_inventory[1].selection",
        )

        inactive = self.document("v2")
        route = inactive["qualification"]["route_inventory"][2]
        route["active"] = False
        inactive["qualification"]["required_route_ids"].remove(route["route_id"])
        route["qualification_status"] = "not_applicable"
        self.normalize(inactive)
        result = self.run_document(inactive)
        self.assertEqual(result.returncode, 20)
        self.assertEqual(
            json.loads(result.stdout)["checks"][0]["path"],
            "$.qualification.route_inventory[2].selection",
        )

    def test_v2_binds_an_exact_native_consumer_route(self):
        for consumer_route_id in ("missing-route", "process-group-all-reduce"):
            with self.subTest(consumer_route_id=consumer_route_id):
                document = self.document("v2")
                route = document["qualification"]["route_inventory"][2]
                route["selection"]["strategy"]["consumer_route_id"] = (
                    consumer_route_id
                )
                CONTRACT.refresh_selection_digests(route["selection"], route)
                result = self.run_document(document)
                self.assertEqual(result.returncode, 20)
                self.assertTrue(
                    json.loads(result.stdout)["checks"][0]["path"].endswith(
                        ".strategy.consumer_route_id"
                    )
                )

    def test_v2_rejects_layout_constraint_contradiction(self):
        document = self.document("v2")
        selection = document["qualification"]["route_inventory"][2]["selection"]
        selection["constraints"]["actual_layout"] = "strided"
        CONTRACT.refresh_selection_digests(
            selection, document["qualification"]["route_inventory"][2]
        )
        result = self.run_document(document)
        self.assertEqual(result.returncode, 20)
        self.assertTrue(json.loads(result.stdout)["checks"][0]["path"].endswith(".constraints.actual_layout"))

    def test_v2_cache_key_binds_changed_payload_on_same_communicator(self):
        document = self.document("v2")
        selection = document["qualification"]["route_inventory"][2]["selection"]
        selection["payload_bytes"] = 256
        result = self.run_document(document)
        self.assertEqual(result.returncode, 20)
        check = json.loads(result.stdout)["checks"][0]
        self.assertEqual(check["code"], "contract.cache_key_digest_mismatch")
        self.assertTrue(check["path"].endswith(".cache_key_digest"))

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
