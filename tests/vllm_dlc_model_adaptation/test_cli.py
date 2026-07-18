import json
import copy
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "scripts" / "validate-vllm-dlc-contracts.py"
FIXTURES = Path(__file__).with_name("fixtures")


class ModelAdaptationCliTests(unittest.TestCase):
    def test_operational_consumer_rejects_synthetic_passed_json(self):
        document = {
            "claims": {
                "acceptance_eligible": False,
                "alignment_action": "unchanged",
                "finalize_action": "none",
            },
            "result_evidence": {"overall_status": "passed"},
            "role": "model_adaptation_profile_operational",
            "schema_version": "vllm-dlc-model-adaptation-operational/v1",
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as fixture:
            json.dump(document, fixture)
            fixture.flush()
            result = self.run_cli("model-adaptation-operational", Path(fixture.name))

        self.assertEqual(result.returncode, 20, result.stdout)
        self.assertEqual(
            json.loads(result.stdout)["checks"][0]["code"],
            "operational_consumer.synthetic_result",
        )

    def run_cli(
        self, target: str, fixture: Path, *, skills_root: Path = ROOT
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(CLI),
                "--skills-root",
                str(skills_root),
                "--knowledge-root",
                "/work/chipltech-knowledge-base",
                "--vllm-dlc-root",
                "/work/vllm-dlc",
                target,
                str(fixture),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def synthetic_candidate_fixtures(self) -> tuple[tempfile.TemporaryDirectory, Path, Path, Path]:
        temporary = tempfile.TemporaryDirectory(dir="/tmp/kilo")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        identity = "model-adaptation"
        candidate = root / "skills" / "in-progress" / identity
        shutil.copytree(ROOT / "skills" / "engineering" / identity, candidate)
        fixtures = root / "fixtures"
        fixtures.mkdir()
        package = fixtures / "package.json"
        package.write_text(json.dumps({
            "skill_identity": identity,
            "roles": {
                "skill": f"../skills/in-progress/{identity}/SKILL.md",
                "agent": f"../skills/in-progress/{identity}/agents/openai.yaml",
                "knowledge": f"../skills/in-progress/{identity}/knowledge.md",
            },
        }))
        routing = json.loads((FIXTURES / "routing.json").read_text())
        routing["candidate_package"] = "package.json"
        routing_path = fixtures / "routing.json"
        routing_path.write_text(json.dumps(routing))
        return temporary, root, package, routing_path

    def run_bundle(self, mutate=None) -> subprocess.CompletedProcess[str]:
        bundle = json.loads(
            (FIXTURES / "contract-available-not-verified.json").read_text()
        )
        if mutate:
            mutate(bundle)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as fixture:
            json.dump(bundle, fixture)
            fixture.flush()
            return self.run_cli("model-adaptation-bundle", Path(fixture.name))

    @staticmethod
    def digest(document: dict) -> str:
        payload = {key: value for key, value in document.items() if key != "digest"}
        canonical = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        return f"sha256:{hashlib.sha256(canonical).hexdigest()}"

    def attach_sealed_documents(
        self,
        bundle: dict,
        *,
        status: str = "not_verified",
        environment: str = "fake_server",
        parent: bool = False,
        changed: bool = False,
    ) -> None:
        guarded_head = subprocess.run(
            ["git", "-C", "/work/vllm-dlc", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        run_spec = {
            "schema_version": "vllm-dlc-run-spec/v1",
            "contract_kind": "run_spec",
            "run_id": "model-adaptation-child-001",
            "workflow": "model_adaptation",
            "mode": "diagnostic_only",
            "target": {
                "vllm_sha": "1" * 40,
                "vllm_dlc_sha": guarded_head,
                "manifest_digest": "sha256:" + "a" * 64,
            },
            "deployment_profile": {
                "model_id": "approved/model",
                "model_revision": "3" * 40,
                "tokenizer_revision": "4" * 40,
                "processor_revision": None,
                "tensor_parallel_size": 1,
                "pipeline_parallel_size": 1,
                "dtype": "bfloat16",
                "quantization": "none",
                "context_limit": 4096,
                "max_num_batched_tokens": 1024,
                "chunked_prefill": True,
                "served_model_name": "approved-model",
                "real_weights": environment != "dummy",
            },
            "hardware": {
                "class": "none" if environment == "dummy" else "fake_server",
                "device_count": 0,
                "required": False,
            },
            "timeouts": {
                "startup_seconds": 600,
                "request_seconds": 120,
                "long_prefix_seconds": 300,
            },
            "runtime_policy": {
                "execution": "eager",
                "triton_execution": "forbidden",
                "compile_execution": "forbidden",
            },
            "gates": ["service_ready", "real_dlc_hardware"],
            "artifact_destination": "/tmp/kilo/model-adaptation-child-001",
            "finalization_intent": "none",
        }
        bundle["preflight"]["hardware_required"] = False
        bundle["preflight"]["required_device_count"] = 0
        run_spec["digest"] = self.digest(run_spec)
        gate_status = "failed" if status == "failed" else status
        result = {
            "schema_version": "vllm-dlc-result-evidence/v1",
            "contract_kind": "result_evidence",
            "run_id": run_spec["run_id"],
            "run_spec_digest": run_spec["digest"],
            "execution_environment": environment,
            "acceptance_eligible": False,
            "overall_status": status,
            "exit_code": 20 if status != "passed" else 0,
            "gates": [
                {
                    "id": "service_ready",
                    "mandatory": True,
                    "status": gate_status,
                    "evidence_digest": "sha256:" + "b" * 64,
                },
                {
                    "id": "real_dlc_hardware",
                    "mandatory": True,
                    "status": gate_status,
                    "evidence_digest": "sha256:" + "c" * 64,
                },
            ],
            "artifacts": [],
            "diagnostics": [],
        }
        result["digest"] = self.digest(result)
        bundle["run_spec"] = run_spec
        bundle["result_evidence"] = result
        bundle["identity"].update(
            expected_model_id=run_spec["deployment_profile"]["model_id"],
            expected_model_revision=run_spec["deployment_profile"]["model_revision"],
            expected_tokenizer_revision=run_spec["deployment_profile"]["tokenizer_revision"],
            expected_processor_revision=None,
            expected_deployment_digest=self.digest(
                {"digest": "unused", **run_spec["deployment_profile"]}
            ),
            parent_run_id="main-to-main-parent-001" if parent else None,
        )
        bundle["execution"].update(
            runner_requested=True,
            result_reference=result["digest"],
            result_environment=environment,
            result_status=status,
            result_acceptance_eligible=False,
        )
        dependencies = ["model.approved"] if changed else []
        bundle["compatibility"] = {
            "changed": changed,
            "changed_dependency_ids": dependencies,
        }
        if parent:
            handoff = {
                "schema_version": "vllm-dlc-parent-child-handoff/v1",
                "contract_kind": "parent_child_handoff",
                "parent_run_id": "main-to-main-parent-001",
                "child_run_id": run_spec["run_id"],
                "target_vllm_sha": run_spec["target"]["vllm_sha"],
                "candidate_vllm_dlc_sha": run_spec["target"]["vllm_dlc_sha"],
                "result_evidence_digest": result["digest"],
                "changed_dependency_ids": dependencies,
                "status": status,
            }
            handoff["digest"] = self.digest(handoff)
            bundle["handoff"] = handoff

    def attach_prior_real_weight_failure(self, bundle: dict) -> None:
        prior_bundle = copy.deepcopy(bundle)
        self.attach_sealed_documents(
            prior_bundle, status="failed", environment="fake_server"
        )
        prior_spec = prior_bundle["run_spec"]
        prior_spec["run_id"] = "real-weight-failure-001"
        prior_spec["hardware"] = {
            "class": "real_dlc_hardware",
            "device_count": 1,
            "required": True,
        }
        prior_spec["gates"] = [
            "service_ready",
            "chunked_prefill",
            "runtime_dispatch",
            "real_dlc_hardware",
        ]
        prior_spec["digest"] = self.digest(prior_spec)
        prior_result = prior_bundle["result_evidence"]
        prior_result["run_id"] = prior_spec["run_id"]
        prior_result["run_spec_digest"] = prior_spec["digest"]
        prior_result["execution_environment"] = "real_dlc_hardware"
        prior_result["gates"] = [
            {
                "id": gate_id,
                "mandatory": True,
                "status": "failed",
                "evidence_digest": "sha256:" + character * 64,
            }
            for gate_id, character in (
                ("service_ready", "b"),
                ("chunked_prefill", "c"),
                ("runtime_dispatch", "d"),
                ("real_dlc_hardware", "e"),
            )
        ]
        prior_result["digest"] = self.digest(prior_result)
        bundle["prior_real_weight_run_spec"] = prior_spec
        bundle["prior_real_weight_result_evidence"] = prior_result
        bundle["execution"]["real_weight_failure_reference"] = prior_result["digest"]

    def test_complete_bundle_reaches_not_verified_without_hardware_claim(self) -> None:
        result = self.run_cli(
            "model-adaptation-bundle", FIXTURES / "contract-available-not-verified.json"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["workflow"], "model_adaptation")
        self.assertEqual(report["phase"], "runtime_evidence")
        self.assertEqual(report["status"], "not_verified")
        self.assertEqual(report["reason_code"], "not_verified")
        self.assertFalse(report["runner_invoked"])
        self.assertFalse(report["acceptance_eligible"])
        self.assertFalse(report["handoff_emitted"])
        self.assertEqual(report["resume_from"], "real_dlc_hardware_evidence")
        self.assertEqual(report["repository_before"], report["repository_after"])

    def test_capability_matrix_is_closed_world_and_evidence_backed(self) -> None:
        cases = [
            (
                lambda bundle: bundle["capability_matrix"].pop(),
                "contract.missing_required_field",
            ),
            (
                lambda bundle: bundle["capability_matrix"].append(
                    copy.deepcopy(bundle["capability_matrix"][0])
                ),
                "contract.invalid_value",
            ),
            (
                lambda bundle: bundle["capability_matrix"][2].update(evidence=""),
                "contract.invalid_value",
            ),
            (
                lambda bundle: bundle["capability_matrix"][2].update(evidence="not needed"),
                "contract.invalid_value",
            ),
        ]
        for mutate, expected in cases:
            with self.subTest(expected=expected):
                result = self.run_bundle(mutate)
                self.assertEqual(result.returncode, 20, result.stdout)
                self.assertEqual(json.loads(result.stdout)["checks"][0]["code"], expected)

    def test_unresolved_conditional_stops_before_runner(self) -> None:
        result = self.run_bundle(
            lambda bundle: bundle["capability_matrix"][4].update(resolved=False)
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason_code"], "blocked_missing_contract")
        self.assertFalse(report["runner_invoked"])
        self.assertEqual(report["resume_from"], "conditional_capability_resolution")

    def test_tp_decision_requires_all_model_specific_evidence(self) -> None:
        for field in (
            "weights_evidence",
            "config_evidence",
            "dtype",
            "quantization",
            "capacity_evidence",
            "deployment_evidence",
        ):
            with self.subTest(field=field):
                result = self.run_bundle(
                    lambda bundle, field=field: bundle["tp_decision"].update(
                        {field: ""}
                    )
                )
                self.assertEqual(result.returncode, 20, result.stdout)
                self.assertEqual(
                    json.loads(result.stdout)["checks"][0]["path"],
                    f"$.tp_decision.{field}",
                )

    def test_preflight_stop_states_are_stable_and_do_not_invoke_runner(self) -> None:
        cases = [
            (lambda bundle: bundle["preflight"].update(model_path=""), "blocked_missing_asset", "model_assets"),
            (lambda bundle: bundle["preflight"].update(available_device_count=0), "blocked_missing_hardware", "hardware_allocation"),
            (lambda bundle: bundle["preflight"].update(current_branch="wrong"), "blocked_branch_mismatch", "required_branch"),
            (lambda bundle: bundle["preflight"].update(contract_available=False), "blocked_missing_contract", "shared_contract"),
            (lambda bundle: bundle["preflight"].update(chunk_observability_available=False), "blocked_missing_observability", "runtime_observability"),
            (lambda bundle: bundle["preflight"].update(required_execution_path_supported=False), "blocked_unsupported_execution_path", "compatibility_action"),
            (lambda bundle: bundle["preflight"].update(read_only_boundary_preserved=False), "blocked_read_only_boundary", "external_artifact_destination"),
        ]
        for mutate, reason, resume in cases:
            with self.subTest(reason=reason):
                result = self.run_bundle(mutate)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report["status"], "blocked")
                self.assertEqual(report["reason_code"], reason)
                self.assertFalse(report["runner_invoked"])
                self.assertFalse(report["handoff_emitted"])
                self.assertEqual(report["resume_from"], resume)
                self.assertEqual(report["repository_before"], report["repository_after"])

    def test_bundle_rejects_unknown_fields(self) -> None:
        result = self.run_bundle(lambda bundle: bundle.update(surprise=True))
        self.assertEqual(result.returncode, 20)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "contract.unknown_field")
        self.assertEqual(report["checks"][0]["path"], "$.surprise")

    def test_candidate_package_is_model_invoked_without_stable_publication(self) -> None:
        _, skills_root, package, _ = self.synthetic_candidate_fixtures()
        result = self.run_cli("candidate-package", package, skills_root=skills_root)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "candidate_package.valid")
        self.assertEqual(report["repository_before"], report["repository_after"])

    def test_routing_matrix_preserves_trigger_and_anti_trigger_owners(self) -> None:
        _, skills_root, _, routing_path = self.synthetic_candidate_fixtures()
        result = self.run_cli("model-adaptation-routing", routing_path, skills_root=skills_root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["checks"][0]["code"], "routing.valid")

        routing = json.loads(routing_path.read_text())
        owners = {row["id"]: row["expected_owner"] for row in routing["cases"]}
        self.assertEqual(owners["upstream_alignment"], "main-to-main-upgrade")
        self.assertEqual(owners["alignment_recovery"], "main-to-main-upgrade")

    def test_routing_rejects_unrelated_prompt_text(self) -> None:
        _, skills_root, _, routing_path = self.synthetic_candidate_fixtures()
        routing = json.loads(routing_path.read_text())
        routing["cases"][0]["prompt"] = "Unrelated request"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", dir=routing_path.parent
        ) as fixture:
            json.dump(routing, fixture)
            fixture.flush()
            result = self.run_cli(
                "model-adaptation-routing", Path(fixture.name), skills_root=skills_root
            )
        self.assertEqual(result.returncode, 20)
        self.assertEqual(
            json.loads(result.stdout)["checks"][0]["code"],
            "routing.prompt_mismatch",
        )

    def test_failed_assertion_consumes_sealed_runner_result(self) -> None:
        result = self.run_bundle(
            lambda bundle: self.attach_sealed_documents(bundle, status="failed")
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["reason_code"], "failed_assertion")
        self.assertTrue(report["runner_invoked"])
        self.assertEqual(report["resume_from"], "compatibility_diagnosis")

    def test_dummy_requires_prior_failure_and_explicit_approval(self) -> None:
        def invalid_dummy(bundle):
            self.attach_sealed_documents(bundle, status="passed", environment="dummy")
            bundle["execution"].update(
                dummy_requested=True,
                dummy_approved=False,
                dummy_mode="diagnostic_only",
            )

        invalid = self.run_bundle(invalid_dummy)
        self.assertEqual(invalid.returncode, 20)
        self.assertEqual(
            json.loads(invalid.stdout)["checks"][0]["code"],
            "contract.inconsistent_status",
        )

        def approved_dummy(bundle):
            self.attach_sealed_documents(bundle, status="passed", environment="dummy")
            self.attach_prior_real_weight_failure(bundle)
            bundle["execution"].update(
                dummy_requested=True,
                dummy_approved=True,
                dummy_mode="diagnostic_only",
                dummy_acceptance_eligible=False,
            )

        approved = self.run_bundle(approved_dummy)
        self.assertEqual(approved.returncode, 0, approved.stderr)
        report = json.loads(approved.stdout)
        self.assertEqual(report["status"], "diagnostic_only")
        self.assertEqual(report["reason_code"], "diagnostic_only")
        self.assertFalse(report["acceptance_eligible"])
        self.assertFalse(report["handoff_emitted"])

    def test_standalone_sealed_result_does_not_forge_parent(self) -> None:
        result = self.run_bundle(
            lambda bundle: self.attach_sealed_documents(bundle, status="not_verified")
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "not_verified")
        self.assertFalse(report["handoff_emitted"])

    def test_parent_bound_handoff_closes_all_identities(self) -> None:
        result = self.run_bundle(
            lambda bundle: self.attach_sealed_documents(
                bundle, status="not_verified", parent=True, changed=True
            )
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["handoff_emitted"])
        self.assertEqual(report["status"], "not_verified")

    def test_sealed_identity_and_digest_mismatches_are_rejected(self) -> None:
        mutations = [
            lambda bundle: bundle["identity"].update(expected_model_revision="9" * 40),
            lambda bundle: bundle["result_evidence"].update(run_spec_digest="sha256:" + "9" * 64),
            lambda bundle: bundle["handoff"].update(parent_run_id="wrong-parent"),
            lambda bundle: bundle["handoff"].update(status="passed"),
            lambda bundle: bundle["compatibility"].update(changed_dependency_ids=["same", "same"]),
        ]
        for mutation in mutations:
            with self.subTest(mutation=repr(mutation)):
                def mutate(bundle, mutation=mutation):
                    self.attach_sealed_documents(
                        bundle, status="not_verified", parent=True, changed=True
                    )
                    mutation(bundle)
                    if "handoff" in bundle and bundle["handoff"] is not None:
                        bundle["handoff"]["digest"] = self.digest(bundle["handoff"])

                result = self.run_bundle(mutate)
                self.assertEqual(result.returncode, 20, result.stdout)

    def test_sealed_run_is_bound_to_workflow_preflight_and_tp(self) -> None:
        mutations = [
            lambda bundle: bundle["run_spec"].update(workflow="main_to_main"),
            lambda bundle: bundle["preflight"].update(model_revision="9" * 40),
            lambda bundle: bundle["tp_decision"].update(tensor_parallel_size=2),
            lambda bundle: bundle["preflight"].update(hardware_required=True, required_device_count=1),
            lambda bundle: bundle["execution"].update(runner_requested=False),
            lambda bundle: bundle["run_spec"]["target"].update(vllm_dlc_sha="9" * 40),
        ]
        for mutation in mutations:
            with self.subTest(mutation=repr(mutation)):
                def mutate(bundle, mutation=mutation):
                    self.attach_sealed_documents(bundle, status="not_verified")
                    mutation(bundle)
                    if mutation is mutations[0]:
                        bundle["run_spec"]["digest"] = self.digest(bundle["run_spec"])
                        bundle["result_evidence"]["run_spec_digest"] = bundle["run_spec"]["digest"]
                        bundle["result_evidence"]["digest"] = self.digest(bundle["result_evidence"])
                        bundle["execution"]["result_reference"] = bundle["result_evidence"]["digest"]

                result = self.run_bundle(mutate)
                self.assertEqual(result.returncode, 20, result.stdout)

    def test_result_gates_close_exactly_with_run_spec(self) -> None:
        mutations = [
            lambda bundle: bundle["result_evidence"]["gates"].pop(),
            lambda bundle: bundle["result_evidence"]["gates"][0].update(mandatory=False),
        ]
        for mutation in mutations:
            with self.subTest(mutation=repr(mutation)):
                def mutate(bundle, mutation=mutation):
                    self.attach_sealed_documents(bundle, status="not_verified")
                    mutation(bundle)
                    statuses = {
                        gate["status"]
                        for gate in bundle["result_evidence"]["gates"]
                        if gate["mandatory"]
                    }
                    bundle["result_evidence"]["overall_status"] = (
                        "not_verified" if "not_verified" in statuses else "passed"
                    )
                    bundle["result_evidence"]["digest"] = self.digest(
                        bundle["result_evidence"]
                    )
                    bundle["execution"].update(
                        result_reference=bundle["result_evidence"]["digest"],
                        result_status=bundle["result_evidence"]["overall_status"],
                    )

                result = self.run_bundle(mutate)
                self.assertEqual(result.returncode, 20, result.stdout)

    def test_dummy_environment_requires_dummy_branch(self) -> None:
        result = self.run_bundle(
            lambda bundle: self.attach_sealed_documents(
                bundle, status="not_verified", environment="dummy"
            )
        )
        self.assertEqual(result.returncode, 20)

    def test_branch_fact_is_bound_to_guarded_repository(self) -> None:
        result = self.run_bundle(
            lambda bundle: bundle["preflight"].update(
                current_branch="invented", required_branch="invented"
            )
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["reason_code"], "blocked_branch_mismatch")

    def test_dummy_and_blocked_outcome_reject_existing_handoff(self) -> None:
        def blocked(bundle):
            self.attach_sealed_documents(
                bundle, status="not_verified", parent=True, changed=True
            )
            bundle["preflight"]["contract_available"] = False

        blocked_result = self.run_bundle(blocked)
        self.assertEqual(blocked_result.returncode, 20)

        def dummy(bundle):
            self.attach_sealed_documents(
                bundle, status="passed", environment="dummy", parent=True, changed=True
            )
            self.attach_prior_real_weight_failure(bundle)
            bundle["execution"].update(
                dummy_requested=True,
                dummy_approved=True,
                dummy_mode="diagnostic_only",
            )

        dummy_result = self.run_bundle(dummy)
        self.assertEqual(dummy_result.returncode, 20)

    def test_preflight_blocker_rejects_existing_execution_evidence(self) -> None:
        def mutate(bundle):
            self.attach_sealed_documents(bundle, status="not_verified")
            bundle["preflight"]["model_path"] = ""

        result = self.run_bundle(mutate)
        self.assertEqual(result.returncode, 20)

    def test_failed_dummy_result_remains_diagnostic_only(self) -> None:
        def mutate(bundle):
            self.attach_sealed_documents(bundle, status="failed", environment="dummy")
            self.attach_prior_real_weight_failure(bundle)
            bundle["execution"].update(
                dummy_requested=True,
                dummy_approved=True,
                dummy_mode="diagnostic_only",
            )

        result = self.run_bundle(mutate)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "diagnostic_only")
        self.assertEqual(report["phase"], "dummy_diagnostic")

    def test_fake_passed_result_cannot_emit_passed_handoff(self) -> None:
        result = self.run_bundle(
            lambda bundle: self.attach_sealed_documents(
                bundle, status="passed", environment="fake_server", parent=True
            )
        )
        self.assertEqual(result.returncode, 20)

    def test_identity_is_validated_without_execution(self) -> None:
        mutations = [
            lambda bundle: bundle["identity"].update(expected_model_id=""),
            lambda bundle: bundle["identity"].update(expected_model_revision="short"),
            lambda bundle: bundle["identity"].update(expected_deployment_digest="bad"),
        ]
        for mutation in mutations:
            with self.subTest(mutation=repr(mutation)):
                result = self.run_bundle(mutation)
                self.assertEqual(result.returncode, 20, result.stdout)

    def test_diagnostic_run_cannot_be_promoted_to_acceptance(self) -> None:
        def mutate(bundle):
            self.attach_sealed_documents(bundle, status="passed")
            bundle["result_evidence"]["execution_environment"] = "real_dlc_hardware"
            bundle["result_evidence"]["acceptance_eligible"] = True
            bundle["result_evidence"]["gates"] = [
                {
                    "id": gate,
                    "mandatory": True,
                    "status": "passed",
                    "evidence_digest": "sha256:" + character * 64,
                }
                for gate, character in (
                    ("chunked_prefill", "b"),
                    ("runtime_dispatch", "c"),
                    ("real_dlc_hardware", "d"),
                )
            ]
            bundle["run_spec"]["hardware"] = {
                "class": "real_dlc_hardware",
                "device_count": 1,
                "required": True,
            }
            bundle["run_spec"]["gates"] = [
                "chunked_prefill", "runtime_dispatch", "real_dlc_hardware"
            ]
            bundle["preflight"].update(hardware_required=True, required_device_count=1)
            bundle["run_spec"]["digest"] = self.digest(bundle["run_spec"])
            bundle["result_evidence"]["run_spec_digest"] = bundle["run_spec"]["digest"]
            bundle["result_evidence"]["digest"] = self.digest(bundle["result_evidence"])
            bundle["execution"].update(
                result_reference=bundle["result_evidence"]["digest"],
                result_environment="real_dlc_hardware",
                result_acceptance_eligible=True,
            )

        result = self.run_bundle(mutate)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "not_verified")
        self.assertFalse(report["acceptance_eligible"])

    def test_alignment_claim_is_rejected(self) -> None:
        result = self.run_bundle(lambda bundle: bundle.update(alignment_claim="finalized"))
        self.assertEqual(result.returncode, 20)
        self.assertEqual(
            json.loads(result.stdout)["checks"][0]["path"], "$.alignment_claim"
        )

    def test_execution_claims_require_sealed_result(self) -> None:
        result = self.run_bundle(
            lambda bundle: bundle["execution"].update(
                runner_requested=True,
                result_reference="sha256:" + "b" * 64,
                result_environment="fake_server",
                result_status="not_verified",
            )
        )
        self.assertEqual(result.returncode, 20)
        self.assertEqual(
            json.loads(result.stdout)["checks"][0]["path"], "$.result_evidence"
        )

    def test_preflight_rejects_malformed_types_and_identities(self) -> None:
        cases = [
            lambda bundle: bundle["preflight"].update(available_device_count=-1),
            lambda bundle: bundle["preflight"].update(contract_available="true"),
            lambda bundle: bundle["preflight"].update(model_revision="short"),
            lambda bundle: bundle["preflight"].update(weights_evidence="unsealed"),
            lambda bundle: bundle["preflight"].update(artifact_destination="relative"),
        ]
        for mutate in cases:
            with self.subTest(mutation=repr(mutate)):
                result = self.run_bundle(mutate)
                self.assertEqual(result.returncode, 20, result.stdout)

    def test_blocked_result_status_propagates(self) -> None:
        result = self.run_bundle(
            lambda bundle: self.attach_sealed_documents(bundle, status="blocked")
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "blocked")
        self.assertTrue(report["runner_invoked"])

    def test_dummy_prior_result_must_be_failed_real_weight_evidence(self) -> None:
        def mutate(bundle):
            self.attach_sealed_documents(bundle, status="passed", environment="dummy")
            self.attach_prior_real_weight_failure(bundle)
            bundle["prior_real_weight_result_evidence"]["execution_environment"] = "fake_server"
            bundle["prior_real_weight_result_evidence"]["digest"] = self.digest(
                bundle["prior_real_weight_result_evidence"]
            )
            bundle["execution"].update(
                dummy_requested=True,
                dummy_approved=True,
                dummy_mode="diagnostic_only",
                real_weight_failure_reference=bundle["prior_real_weight_result_evidence"]["digest"],
            )

        result = self.run_bundle(mutate)
        self.assertEqual(result.returncode, 20)

    def test_candidate_package_rejects_paths_outside_expected_root(self) -> None:
        package = json.loads((FIXTURES / "package.json").read_text())
        package["roles"]["skill"] = "../../../skills/in-progress/writing-shape/SKILL.md"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", dir=FIXTURES
        ) as fixture:
            json.dump(package, fixture)
            fixture.flush()
            result = self.run_cli("candidate-package", Path(fixture.name))
        self.assertEqual(result.returncode, 20)


if __name__ == "__main__":
    unittest.main()
