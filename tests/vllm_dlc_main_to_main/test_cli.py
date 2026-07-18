import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "scripts" / "validate-vllm-dlc-contracts.py"
FIXTURES = Path(__file__).with_name("fixtures")


def load_validator():
    spec = importlib.util.spec_from_file_location("vllm_dlc_contract", CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MainToMainCliTests(unittest.TestCase):
    def validate_operational_policy_children(self, mutate_policy=None, mutate_specs=None):
        validator = load_validator()
        temporary = tempfile.TemporaryDirectory(dir="/tmp/kilo")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        target = {
            "vllm_sha": "1" * 40,
            "vllm_dlc_sha": "2" * 40,
            "manifest_digest": "sha256:" + "3" * 64,
        }
        policy = {
            "alignment_action": "unchanged",
            "approved": True,
            "claim_level": "operational_only",
            "finalization_intent": "none",
            "manifest_action": "report_only",
            "roles": [
                {"role": "deepseek_tp2_operational", "tensor_parallel_size": 2},
                {"role": "llama_tp1_dense_operational", "tensor_parallel_size": 1},
            ],
            "schema_version": "vllm-dlc-main-to-main-operational-policy/v1",
            "target": target,
        }
        if mutate_policy:
            mutate_policy(policy)
        policy_path = root / "policy.json"
        policy_path.write_text(json.dumps(policy))
        policy_digest = "sha256:" + hashlib.sha256(policy_path.read_bytes()).hexdigest()
        roles = ["deepseek_tp2_operational", "llama_tp1_dense_operational"]
        specs = []
        children = []
        outcomes = {}
        for index, role in enumerate(roles):
            child_root = root / role
            child_root.mkdir()
            run_spec = {
                "campaign_digest": "sha256:" + "4" * 64,
                "deployment_profile": {
                    "role": role,
                    "tensor_parallel_size": 2 if index == 0 else 1,
                },
                "run_id": f"child-{index}",
                "target": dict(target),
            }
            specs.append(run_spec)
            run_spec_path = child_root / "run-spec.json"
            evidence_path = child_root / "result.json"
            reference_path = child_root / "reference.json"
            evidence_path.write_text(json.dumps({
                "artifacts": [{"kind": "run_spec", "uri": run_spec_path.as_uri()}]
            }))
            reference_path.write_text(json.dumps({"uri": evidence_path.as_uri()}))
            children.append({"result_reference": str(reference_path), "role": role})
            outcomes[str(reference_path)] = {
                "campaign_digest": run_spec["campaign_digest"],
                "completion_eligible": True,
                "run_id": run_spec["run_id"],
            }
        if mutate_specs:
            mutate_specs(specs)
        for index, run_spec in enumerate(specs):
            (root / roles[index] / "run-spec.json").write_text(json.dumps(run_spec))
            outcomes[str(root / roles[index] / "reference.json")].update(
                campaign_digest=run_spec["campaign_digest"],
                run_id=run_spec["run_id"],
            )
        document_path = root / "consumer.json"
        document_path.write_text(json.dumps({
            "children": children,
            "claims": {
                "acceptance_eligible": False,
                "alignment_action": "unchanged",
                "finalize_action": "none",
                "manifest_action": "report_only",
            },
            "policy_digest": policy_digest,
            "policy_path": str(policy_path),
            "schema_version": "vllm-dlc-main-to-main-operational/v1",
        }))

        def validate_reference(path, guarded_root):
            return (
                {"code": "operational_result_reference.valid", "status": "passed"},
                outcomes[str(path)],
            )

        with mock.patch.object(
            validator,
            "validate_operational_result_reference",
            side_effect=validate_reference,
        ):
            return validator.validate_main_to_main_operational(
                document_path, Path("/work/vllm-dlc")
            )

    def test_operational_consumer_rejects_random_policy_digest(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            policy_path = Path(directory) / "policy.json"
            policy_path.write_text(json.dumps({
                "alignment_action": "unchanged",
                "approved": True,
                "claim_level": "operational_only",
                "finalization_intent": "none",
                "manifest_action": "report_only",
                "roles": [
                    {"role": "deepseek_tp2_operational", "tensor_parallel_size": 2},
                    {"role": "llama_tp1_dense_operational", "tensor_parallel_size": 1},
                ],
                "schema_version": "vllm-dlc-main-to-main-operational-policy/v1",
                "target": {
                    "vllm_sha": "1" * 40,
                    "vllm_dlc_sha": "2" * 40,
                    "manifest_digest": "sha256:" + "3" * 64,
                },
            }))
            document_path = Path(directory) / "consumer.json"
            document_path.write_text(json.dumps({
                "children": [
                    {"result_reference": "/tmp/kilo/deepseek.json", "role": "deepseek_tp2_operational"},
                    {"result_reference": "/tmp/kilo/llama.json", "role": "llama_tp1_dense_operational"},
                ],
                "claims": {
                    "acceptance_eligible": False,
                    "alignment_action": "unchanged",
                    "finalize_action": "none",
                    "manifest_action": "report_only",
                },
                "policy_digest": "sha256:" + "f" * 64,
                "policy_path": str(policy_path),
                "schema_version": "vllm-dlc-main-to-main-operational/v1",
            }))

            check, _ = validator.validate_main_to_main_operational(
                document_path, Path("/work/vllm-dlc")
            )

        self.assertEqual(check["status"], "failed")
        self.assertEqual(check["code"], "operational_consumer.policy_digest_mismatch")

    def test_operational_consumer_rejects_tampered_policy_bytes(self):
        validator = load_validator()
        policy_path = validator.MAIN_TO_MAIN_OPERATIONAL_POLICY_PATH
        document = {
            "children": [],
            "claims": {
                "acceptance_eligible": False,
                "alignment_action": "unchanged",
                "finalize_action": "none",
                "manifest_action": "report_only",
            },
            "policy_digest": "sha256:" + hashlib.sha256(policy_path.read_bytes()).hexdigest(),
            "policy_path": "",
            "schema_version": "vllm-dlc-main-to-main-operational/v1",
        }
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            root = Path(directory)
            tampered = root / "policy.json"
            tampered.write_bytes(policy_path.read_bytes() + b"\n")
            document["policy_path"] = str(tampered)
            document["children"] = [
                {"result_reference": "/tmp/kilo/deepseek.json", "role": "deepseek_tp2_operational"},
                {"result_reference": "/tmp/kilo/llama.json", "role": "llama_tp1_dense_operational"},
            ]
            consumer = root / "consumer.json"
            consumer.write_text(json.dumps(document))
            check, _ = validator.validate_main_to_main_operational(
                consumer, Path("/work/vllm-dlc")
            )

        self.assertEqual(check["code"], "operational_consumer.policy_digest_mismatch")

    def test_operational_consumer_rejects_child_policy_identity_mismatches(self):
        cases = {
            "target": lambda specs: specs[0]["target"].update(vllm_sha="5" * 40),
            "role": lambda specs: specs[0]["deployment_profile"].update(
                role="llama_tp1_dense_operational"
            ),
            "tensor_parallel_size": lambda specs: specs[0]["deployment_profile"].update(
                tensor_parallel_size=1
            ),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                check, _ = self.validate_operational_policy_children(
                    mutate_specs=mutate
                )
                self.assertEqual(check["status"], "failed")

    def test_operational_consumer_rejects_child_campaign_mismatch(self):
        check, _ = self.validate_operational_policy_children(
            mutate_specs=lambda specs: specs[1].update(
                campaign_digest="sha256:" + "5" * 64
            )
        )

        self.assertEqual(check["status"], "failed")
        self.assertEqual(check["code"], "operational_consumer.campaign_mismatch")

    def test_operational_consumer_accepts_policy_closed_children(self):
        check, outcome = self.validate_operational_policy_children()

        self.assertEqual(check["code"], "main_to_main_operational.valid")
        self.assertEqual(outcome["completion_status"], "passed")
        self.assertFalse(outcome["acceptance_eligible"])

    def test_operational_consumer_rejects_synthetic_children(self):
        document = {
            "children": [
                {"role": "deepseek_tp2_operational", "status": "passed"},
                {"role": "llama_tp1_dense_operational", "status": "passed"},
            ],
            "claims": {
                "acceptance_eligible": False,
                "alignment_action": "unchanged",
                "finalize_action": "none",
                "manifest_action": "report_only",
            },
            "policy_digest": "sha256:" + "1" * 64,
            "schema_version": "vllm-dlc-main-to-main-operational/v1",
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as fixture:
            json.dump(document, fixture)
            fixture.flush()
            result = self.run_cli("main-to-main-operational", Path(fixture.name))

        self.assertEqual(result.returncode, 20, result.stdout)
        self.assertEqual(
            json.loads(result.stdout)["checks"][0]["code"],
            "operational_consumer.synthetic_result",
        )

    @classmethod
    def setUpClass(cls):
        cls.synthetic_repository = tempfile.TemporaryDirectory(dir="/tmp/kilo")
        cls.main_root = Path(cls.synthetic_repository.name) / "vllm-dlc"
        subprocess.run(
            ["git", "clone", "--quiet", "--no-hardlinks", "/work/vllm-dlc", str(cls.main_root)],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(cls.main_root), "checkout", "--quiet", "-B", "main"],
            check=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.synthetic_repository.cleanup()

    def run_cli(
        self,
        target: str,
        fixture: Path,
        guarded_root: str = "/work/vllm-dlc",
        *,
        skills_root: Path = ROOT,
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
                guarded_root,
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
        identity = "main-to-main-upgrade"
        candidate = root / "skills" / "in-progress" / identity
        shutil.copytree(ROOT / "skills" / "engineering" / identity, candidate)
        fixtures = root / "fixtures"
        fixtures.mkdir()
        package_path = fixtures / "package.json"
        package_path.write_text(json.dumps({
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
        return temporary, root, package_path, routing_path

    def run_bundle(self, mutate=None, guarded_root=None) -> subprocess.CompletedProcess[str]:
        bundle = json.loads((FIXTURES / "complete-not-verified.json").read_text())
        if mutate:
            mutate(bundle)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as fixture:
            json.dump(bundle, fixture)
            fixture.flush()
            return self.run_cli(
                "main-to-main-bundle",
                Path(fixture.name),
                str(guarded_root or self.main_root),
            )

    @staticmethod
    def pass_branch(bundle):
        bundle["preflight"].update(
            current_branch="main",
            required_branch="main",
            branch_matches_main=True,
        )
        bundle["freeze"].update(
            tested_revision_unique=True,
            commit_required=False,
        )
        bundle["baseline"].update(
            state="fixture_verified",
            selected_candidate_id="historical-verified",
        )
        bundle["baseline"]["candidates"][0].update(
            mandatory_evidence_complete=True,
            evidence_digest="sha256:" + "1" * 64,
            revalidation_status="passed",
            verified_alignment=True,
        )
        bundle["history"].update(
            complete=True,
            range_evidence_digest="sha256:" + "2" * 64,
        )

    @staticmethod
    def digest(document):
        payload = {key: value for key, value in document.items() if key != "digest"}
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        return f"sha256:{hashlib.sha256(canonical).hexdigest()}"

    def attach_child(self, parent, assignment_index=0, status="not_verified", environment="fake_server", eligible=False):
        assignment = parent["assignments"][assignment_index]
        child = json.loads((ROOT / "tests/vllm_dlc_model_adaptation/fixtures/contract-available-not-verified.json").read_text())
        child["preflight"].update(
            model_revision=assignment["model_revision"], tokenizer_revision=assignment["tokenizer_revision"],
            processor_revision=assignment["processor_revision"], required_branch="main", current_branch="main",
            hardware_required=eligible,
            required_device_count=assignment["tensor_parallel_size"] if eligible else 0,
            available_device_count=assignment["tensor_parallel_size"] if eligible else 0,
        )
        child["tp_decision"]["tensor_parallel_size"] = assignment["tensor_parallel_size"]
        profile = {
            "model_id": assignment["model_id"], "model_revision": assignment["model_revision"],
            "tokenizer_revision": assignment["tokenizer_revision"], "processor_revision": assignment["processor_revision"],
            "tensor_parallel_size": assignment["tensor_parallel_size"], "pipeline_parallel_size": 1,
            "dtype": "bfloat16", "quantization": "none", "context_limit": 4096,
            "max_num_batched_tokens": 1024, "chunked_prefill": True,
            "served_model_name": assignment["assignment_id"], "real_weights": True,
        }
        assignment["deployment_digest"] = self.digest({"digest": "ignored", **profile})
        role_gate = "dlccl_lyp_distributed" if assignment["role"] == "deepseek_distributed" else "dense_attention_generation"
        gates = [
            "service_ready", "models_api", "completions_api", "chat_api",
            "long_prefix_api", "server_liveness", "chunked_prefill",
            "runtime_dispatch", "real_dlc_hardware", role_gate,
        ] if eligible else ["service_ready", "real_dlc_hardware"]
        run_spec = {
            "schema_version": "vllm-dlc-run-spec/v1", "contract_kind": "run_spec",
            "run_id": assignment["child_run_id"], "workflow": "model_adaptation", "mode": "acceptance" if eligible else "diagnostic_only",
            "target": {"vllm_sha": parent["target"]["vllm_sha"], "vllm_dlc_sha": parent["candidate_vllm_dlc_sha"], "manifest_digest": parent["manifest_impact"]["manifest_digest"]},
            "deployment_profile": profile, "hardware": ({"class": "real_dlc_hardware", "device_count": assignment["tensor_parallel_size"], "required": True} if eligible else {"class": "fake_server", "device_count": 0, "required": False}),
            "timeouts": {"startup_seconds": 600, "request_seconds": 120, "long_prefix_seconds": 300},
            "runtime_policy": {"execution": "eager", "triton_execution": "forbidden", "compile_execution": "forbidden"},
            "gates": gates, "artifact_destination": "/tmp/kilo/" + assignment["child_run_id"],
            "finalization_intent": "none",
        }
        run_spec["digest"] = self.digest(run_spec)
        result = {
            "schema_version": "vllm-dlc-result-evidence/v1", "contract_kind": "result_evidence",
            "run_id": run_spec["run_id"], "run_spec_digest": run_spec["digest"], "execution_environment": environment,
            "acceptance_eligible": eligible, "overall_status": status, "exit_code": 0 if status == "passed" else 20,
            "gates": [{"id": gate, "mandatory": True, "status": status, "evidence_digest": "sha256:" + format(index + 1, "x") * 64} for index, gate in enumerate(gates)],
            "artifacts": [], "diagnostics": [],
        }
        result["digest"] = self.digest(result)
        dependencies = assignment["expected_dependency_ids"]
        child["compatibility"] = {"changed": bool(dependencies), "changed_dependency_ids": dependencies}
        child["identity"].update(
            expected_model_id=profile["model_id"], expected_model_revision=profile["model_revision"],
            expected_tokenizer_revision=profile["tokenizer_revision"], expected_processor_revision=profile["processor_revision"],
            expected_deployment_digest=assignment["deployment_digest"], parent_run_id=parent["parent_run_id"],
        )
        child["execution"].update(runner_requested=True, result_reference=result["digest"], result_environment=environment, result_status=status, result_acceptance_eligible=eligible)
        handoff = {
            "schema_version": "vllm-dlc-parent-child-handoff/v1", "contract_kind": "parent_child_handoff",
            "parent_run_id": parent["parent_run_id"], "child_run_id": run_spec["run_id"],
            "target_vllm_sha": parent["target"]["vllm_sha"], "candidate_vllm_dlc_sha": parent["candidate_vllm_dlc_sha"],
            "result_evidence_digest": result["digest"], "changed_dependency_ids": dependencies, "status": status,
        }
        handoff["digest"] = self.digest(handoff)
        child.update(run_spec=run_spec, result_evidence=result, handoff=handoff)
        parent["child_bundles"].append({"assignment_id": assignment["assignment_id"], "model_adaptation_bundle": child})

    def test_complete_dry_run_is_structured_not_verified_and_never_finalizes(self):
        result = self.run_bundle(self.pass_branch)

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["workflow"], "main_to_main")
        self.assertEqual(report["status"], "not_verified")
        self.assertEqual(report["reason_code"], "not_verified")
        self.assertFalse(report["acceptance_eligible"])
        self.assertFalse(report["finalize_eligible"])
        self.assertEqual(report["alignment_outcome"], "unchanged")
        self.assertEqual(report["manifest_outcome"], "report_only")
        self.assertEqual(
            report["evidence_states"],
            {
                "chunked_prefill_runtime": "not_verified",
                "dlc_runtime_dispatch": "not_verified",
                "real_dlc_hardware": "not_verified",
                "real_weights": "not_verified",
            },
        )
        self.assertEqual(report["repository_before"], report["repository_after"])

    def test_target_requires_full_sha_and_tag_is_lineage_only(self):
        result = self.run_bundle(lambda bundle: bundle["target"].update(vllm_sha="v0.9.0"))

        self.assertEqual(result.returncode, 20)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "contract.missing_identity")
        self.assertEqual(report["checks"][0]["path"], "$.target.vllm_sha")

    def test_candidate_revision_is_bound_to_guarded_head(self):
        result = self.run_bundle(
            lambda bundle: bundle.update(candidate_vllm_dlc_sha="6" * 40)
        )
        self.assertEqual(result.returncode, 20)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "contract.identity_mismatch")
        self.assertEqual(report["checks"][0]["path"], "$.candidate_vllm_dlc_sha")

    def test_branch_mismatch_blocks_before_analysis(self):
        def mutate(bundle):
            bundle["preflight"].update(
                current_branch="dev-skills",
                required_branch="main",
                branch_matches_main=False,
            )

        result = self.run_bundle(mutate, guarded_root="/work/vllm-dlc")

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["phase"], "preflight")
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason_code"], "blocked_branch_mismatch")
        self.assertEqual(report["resume_from"], "required_branch")
        self.assertFalse(report["finalize_eligible"])

    def test_unknown_baseline_stays_unknown_and_blocks(self):
        def mutate(bundle):
            self.pass_branch(bundle)
            bundle["baseline"].update(state="unknown", selected_candidate_id=None)
            bundle["baseline"]["candidates"][0].update(
                mandatory_evidence_complete=False, verified_alignment=False
            )

        result = self.run_bundle(mutate)

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["phase"], "baseline_recovery")
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason_code"], "blocked_missing_verified_alignment")
        self.assertEqual(report["baseline_state"], "unknown")

    def test_baseline_candidates_follow_confidence_order_and_clues_cannot_verify(self):
        def promote_clue(bundle):
            self.pass_branch(bundle)
            bundle["baseline"].update(selected_candidate_id="checkout-clue")
            bundle["baseline"]["candidates"][3].update(
                mandatory_evidence_complete=True, verified_alignment=True
            )

        clue = self.run_bundle(promote_clue)
        self.assertEqual(clue.returncode, 20)
        self.assertEqual(
            json.loads(clue.stdout)["checks"][0]["code"],
            "contract.inconsistent_status",
        )

        def reorder(bundle):
            self.pass_branch(bundle)
            bundle["baseline"]["candidates"].reverse()

        order = self.run_bundle(reorder)
        self.assertEqual(order.returncode, 20)
        self.assertEqual(
            json.loads(order.stdout)["checks"][0]["path"], "$.baseline.candidates"
        )

    def test_incomplete_history_blocks_before_delta_claims(self):
        def mutate(bundle):
            self.pass_branch(bundle)
            bundle["history"]["complete"] = False

        result = self.run_bundle(mutate)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["phase"], "upstream_history")
        self.assertEqual(report["reason_code"], "blocked_incomplete_upstream_history")
        self.assertEqual(report["resume_from"], "complete_upstream_history")

    def test_unresolved_upstream_impact_blocks_until_unknown_count_is_zero(self):
        def mutate(bundle):
            self.pass_branch(bundle)
            bundle["delta"]["declared_unknown_impact_count"] = 1
            bundle["delta"]["surfaces"][0]["classification"] = "unknown"
            bundle["assignments"][0]["expected_dependency_ids"] = []
            bundle["manifest_impact"]["future_changes"] = [
                row
                for row in bundle["manifest_impact"]["future_changes"]
                if row["dependency_id"] != "attention.api"
            ]

        result = self.run_bundle(mutate)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["phase"], "upstream_delta")
        self.assertEqual(
            report["reason_code"], "blocked_unresolved_compatibility_impact"
        )
        self.assertEqual(report["unknown_impact_count"], 1)

    def test_delta_classification_is_exhaustive_and_manifest_report_is_read_only(self):
        result = self.run_bundle(self.pass_branch)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["changed_surface_count"], 3)
        self.assertEqual(report["unknown_impact_count"], 0)
        self.assertEqual(
            report["delta_classification_counts"],
            {
                "affected_dependency": 1,
                "confirmed_irrelevant": 1,
                "new_dependency_candidate": 1,
            },
        )
        self.assertEqual(report["manifest_outcome"], "report_only")
        self.assertEqual(report["manifest_future_change_count"], 2)

    def test_manifest_mutation_claim_is_rejected(self):
        def mutate(bundle):
            self.pass_branch(bundle)
            bundle["manifest_impact"].update(modified=True)
            bundle["manifest_impact"]["applied_changes"] = ["attention.api"]

        result = self.run_bundle(mutate)
        self.assertEqual(result.returncode, 20)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "contract.read_only_boundary")
        self.assertEqual(report["checks"][0]["path"], "$.manifest_impact")

    def test_candidate_package_and_routing_preserve_workflow_boundaries(self):
        _, skills_root, package_path, routing_path = self.synthetic_candidate_fixtures()
        package = self.run_cli(
            "candidate-package", package_path, skills_root=skills_root
        )
        self.assertEqual(package.returncode, 0, package.stderr)
        self.assertEqual(
            json.loads(package.stdout)["checks"][0]["code"],
            "candidate_package.valid",
        )

        routing = self.run_cli(
            "main-to-main-routing", routing_path, skills_root=skills_root
        )
        self.assertEqual(routing.returncode, 0, routing.stderr)
        self.assertEqual(json.loads(routing.stdout)["checks"][0]["code"], "routing.valid")

    def test_mandatory_assignments_are_unique_deepseek_tp2_and_llama_tp1(self):
        result = self.run_bundle(self.pass_branch)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(
            report["mandatory_assignments"],
            [
                {"assignment_id": "deepseek-tp2", "role": "deepseek_distributed", "tensor_parallel_size": 2},
                {"assignment_id": "llama-tp1", "role": "llama_dense", "tensor_parallel_size": 1},
            ],
        )

        def duplicate(bundle):
            self.pass_branch(bundle)
            bundle["assignments"][1]["child_run_id"] = bundle["assignments"][0]["child_run_id"]

        invalid = self.run_bundle(duplicate)
        self.assertEqual(invalid.returncode, 20)
        self.assertEqual(
            json.loads(invalid.stdout)["checks"][0]["path"], "$.assignments"
        )

    def test_deepseek_tp1_can_only_be_non_mandatory_diagnostic(self):
        def mutate(bundle):
            self.pass_branch(bundle)
            diagnostic = copy.deepcopy(bundle["assignments"][0])
            diagnostic.update(
                assignment_id="deepseek-tp1-diagnostic",
                child_run_id="deepseek-diagnostic-child-001",
                mandatory=False,
                role="deepseek_diagnostic",
                tensor_parallel_size=1,
                mode="diagnostic_only",
                real_weights_required=False,
                hardware_class="none",
                deployment_digest="sha256:" + "c" * 64,
            )
            bundle["assignments"].append(diagnostic)

        valid = self.run_bundle(mutate)
        self.assertEqual(valid.returncode, 0, valid.stderr)

        def mandatory(bundle):
            mutate(bundle)
            bundle["assignments"][-1]["mandatory"] = True

        invalid = self.run_bundle(mandatory)
        self.assertEqual(invalid.returncode, 20)
        self.assertEqual(
            json.loads(invalid.stdout)["checks"][0]["code"],
            "contract.inconsistent_status",
        )

    def test_ticket03_handoff_is_consumed_with_complete_identity_closure(self):
        def mutate(bundle):
            self.pass_branch(bundle)
            self.attach_child(bundle)

        result = self.run_bundle(mutate)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "not_verified")
        self.assertEqual(report["child_statuses"], {"deepseek-tp2": "not_verified", "llama-tp1": "not_verified"})
        self.assertFalse(report["finalize_eligible"])

    def test_child_identity_and_digest_mismatches_are_rejected(self):
        mutations = [
            lambda row: row["model_adaptation_bundle"]["handoff"].update(parent_run_id="wrong"),
            lambda row: row["model_adaptation_bundle"]["run_spec"]["target"].update(vllm_sha="6" * 40),
            lambda row: row["model_adaptation_bundle"]["identity"].update(expected_model_id="wrong/model"),
            lambda row: row["model_adaptation_bundle"]["handoff"].update(result_evidence_digest="sha256:" + "6" * 64),
        ]
        for mutation in mutations:
            with self.subTest(mutation=repr(mutation)):
                def mutate(bundle, mutation=mutation):
                    self.pass_branch(bundle)
                    self.attach_child(bundle)
                    mutation(bundle["child_bundles"][0])
                    handoff = bundle["child_bundles"][0]["model_adaptation_bundle"]["handoff"]
                    handoff["digest"] = self.digest(handoff)
                result = self.run_bundle(mutate)
                self.assertEqual(result.returncode, 20, result.stdout)

    def test_mandatory_child_failed_blocked_and_not_verified_stop_parent(self):
        for status in ("failed", "blocked", "not_verified"):
            with self.subTest(status=status):
                def mutate(bundle, status=status):
                    self.pass_branch(bundle)
                    self.attach_child(bundle, status=status)
                result = self.run_bundle(mutate)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report["status"], status)
                self.assertFalse(report["finalize_eligible"])

    def test_preflight_blocker_matrix_is_stable(self):
        cases = [
            ("target_available", "blocked_missing_target"),
            ("contract_available", "blocked_missing_contract"),
            ("assets_available", "blocked_missing_asset"),
            ("hardware_available", "blocked_missing_hardware"),
            ("observability_available", "blocked_missing_observability"),
            ("read_only_boundary_preserved", "blocked_read_only_boundary"),
        ]
        for field, reason in cases:
            with self.subTest(field=field):
                def mutate(bundle, field=field):
                    self.pass_branch(bundle)
                    bundle["preflight"][field] = False
                result = self.run_bundle(mutate)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report["phase"], "preflight")
                self.assertEqual(report["reason_code"], reason)
                self.assertFalse(report["finalize_eligible"])

    def test_fake_server_dlcsim_and_static_evidence_never_promote_acceptance(self):
        for environment in ("fake_server", "dlcsim", "static"):
            with self.subTest(environment=environment):
                def mutate(bundle, environment=environment):
                    self.pass_branch(bundle)
                    self.attach_child(bundle, environment=environment)
                result = self.run_bundle(mutate)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report["status"], "not_verified")
                self.assertFalse(report["acceptance_eligible"])
                self.assertFalse(report["finalize_eligible"])

    def test_dummy_child_feedback_is_rejected_by_ticket03_seam(self):
        def mutate(bundle):
            self.pass_branch(bundle)
            self.attach_child(bundle, environment="dummy")

        result = self.run_bundle(mutate)
        self.assertEqual(result.returncode, 20)
        self.assertIn(
            json.loads(result.stdout)["checks"][0]["code"],
            {"contract.inconsistent_status", "contract.invalid_value"},
        )

    def test_non_unique_revision_missing_authorization_and_stale_evidence_block_finalize(self):
        cases = [
            (lambda bundle: bundle["freeze"].update(commit_required=True, commit_authorized=False), "blocked_missing_commit_authorization"),
            (lambda bundle: bundle["freeze"].update(evidence_stale=True), "blocked_stale_evidence"),
        ]
        for mutation, reason in cases:
            with self.subTest(reason=reason):
                def mutate(bundle, mutation=mutation):
                    self.pass_branch(bundle)
                    self.attach_child(bundle, assignment_index=0, status="passed", environment="real_dlc_hardware", eligible=True)
                    self.attach_child(bundle, assignment_index=1, status="passed", environment="real_dlc_hardware", eligible=True)
                    mutation(bundle)
                result = self.run_bundle(mutate)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report["phase"], "freeze_candidate")
                self.assertEqual(report["reason_code"], reason)
                self.assertEqual(report["alignment_outcome"], "unchanged")
                self.assertFalse(report["finalize_eligible"])

    def test_dirty_guarded_repository_derives_non_unique_revision_blocker(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            guarded_root = Path(directory) / "vllm-dlc"
            subprocess.run(
                ["git", "clone", "--quiet", "--no-hardlinks", "/work/vllm-dlc", str(guarded_root)],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(guarded_root), "checkout", "--quiet", "-B", "main"],
                check=True,
            )
            (guarded_root / "ticket04-untracked").write_text("dirty")

            def mutate(bundle):
                self.pass_branch(bundle)
                bundle["freeze"].update(tested_revision_unique=False, commit_required=True)
                self.attach_child(bundle, assignment_index=0, status="passed", environment="real_dlc_hardware", eligible=True)
                self.attach_child(bundle, assignment_index=1, status="passed", environment="real_dlc_hardware", eligible=True)

            result = self.run_bundle(mutate, guarded_root=guarded_root)

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["phase"], "freeze_candidate")
        self.assertEqual(report["reason_code"], "blocked_non_unique_tested_revision")
        self.assertFalse(report["finalize_eligible"])

    def test_alignment_manifest_update_and_finalize_claims_are_rejected(self):
        mutations = [
            lambda bundle: bundle["claims"].update(alignment_action="updated"),
            lambda bundle: bundle["claims"].update(manifest_action="updated"),
            lambda bundle: bundle["claims"].update(finalize_action="finalized"),
        ]
        for mutation in mutations:
            with self.subTest(mutation=repr(mutation)):
                def mutate(bundle, mutation=mutation):
                    self.pass_branch(bundle)
                    mutation(bundle)

                result = self.run_bundle(mutate)
                self.assertEqual(result.returncode, 20)
                self.assertEqual(
                    json.loads(result.stdout)["checks"][0]["code"],
                    "contract.inconsistent_status",
                )

    def test_parent_child_target_candidate_model_deployment_result_and_dependency_mismatches_reject(self):
        mutations = [
            lambda bundle, row: bundle.update(parent_run_id="wrong-parent"),
            lambda bundle, row: row["model_adaptation_bundle"]["handoff"].update(child_run_id="wrong-child"),
            lambda bundle, row: bundle["target"].update(vllm_sha="6" * 40),
            lambda bundle, row: bundle.update(candidate_vllm_dlc_sha="6" * 40),
            lambda bundle, row: bundle["assignments"][0].update(model_revision="6" * 40),
            lambda bundle, row: bundle["assignments"][0].update(deployment_digest="sha256:" + "6" * 64),
            lambda bundle, row: row["model_adaptation_bundle"]["result_evidence"].update(run_spec_digest="sha256:" + "6" * 64),
            lambda bundle, row: bundle["assignments"][0].update(expected_dependency_ids=["wrong.dependency"]),
        ]
        for mutation in mutations:
            with self.subTest(mutation=repr(mutation)):
                def mutate(bundle, mutation=mutation):
                    self.pass_branch(bundle)
                    self.attach_child(bundle)
                    row = bundle["child_bundles"][0]
                    mutation(bundle, row)
                    for document_name in ("run_spec", "result_evidence", "handoff"):
                        document = row["model_adaptation_bundle"][document_name]
                        document["digest"] = self.digest(document)
                result = self.run_bundle(mutate)
                self.assertEqual(result.returncode, 20, result.stdout)

    def test_main_to_main_bundle_is_closed_world(self):
        mutations = [
            lambda bundle: bundle.update(surprise=True),
            lambda bundle: bundle["target"].update(surprise=True),
            lambda bundle: bundle["assignments"][0].update(surprise=True),
            lambda bundle: bundle["manifest_impact"]["future_changes"][0].update(surprise=True),
        ]
        for mutation in mutations:
            with self.subTest(mutation=repr(mutation)):
                def mutate(bundle, mutation=mutation):
                    self.pass_branch(bundle)
                    mutation(bundle)

                result = self.run_bundle(mutate)
                self.assertEqual(result.returncode, 20)
                self.assertEqual(
                    json.loads(result.stdout)["checks"][0]["code"],
                    "contract.unknown_field",
                )

    def test_baseline_and_history_require_auditable_evidence_identity(self):
        cases = [
            lambda bundle: bundle["baseline"]["candidates"][0].update(evidence_digest=None),
            lambda bundle: bundle["baseline"]["candidates"][0].update(revalidation_status="not_verified"),
            lambda bundle: bundle["history"].update(range_evidence_digest=None),
            lambda bundle: bundle["history"].update(discovered_changed_surface_count=4),
        ]
        for mutation in cases:
            with self.subTest(mutation=repr(mutation)):
                def mutate(bundle, mutation=mutation):
                    self.pass_branch(bundle)
                    mutation(bundle)
                result = self.run_bundle(mutate)
                self.assertEqual(result.returncode, 20, result.stdout)

    def test_explicit_and_correlated_candidates_need_passed_revalidation(self):
        for index in (1, 2):
            with self.subTest(index=index):
                def mutate(bundle, index=index):
                    self.pass_branch(bundle)
                    bundle["baseline"]["candidates"][0].update(
                        mandatory_evidence_complete=False,
                        evidence_digest=None,
                        revalidation_status="not_verified",
                        verified_alignment=False,
                    )
                    candidate = bundle["baseline"]["candidates"][index]
                    candidate.update(mandatory_evidence_complete=True, verified_alignment=True)
                    bundle["baseline"]["selected_candidate_id"] = candidate["id"]
                result = self.run_bundle(mutate)
                self.assertEqual(result.returncode, 20, result.stdout)

    def test_manifest_report_closes_every_affected_or_new_delta_dependency(self):
        mutations = [
            lambda bundle: bundle["manifest_impact"]["future_changes"].pop(),
            lambda bundle: bundle["manifest_impact"]["future_changes"][1].update(action="future_remove"),
            lambda bundle: bundle["manifest_impact"]["future_changes"].append(
                {"dependency_id": "unrelated", "action": "future_add", "reason": "not in delta"}
            ),
        ]
        for mutation in mutations:
            with self.subTest(mutation=repr(mutation)):
                def mutate(bundle, mutation=mutation):
                    self.pass_branch(bundle)
                    mutation(bundle)
                result = self.run_bundle(mutate)
                self.assertEqual(result.returncode, 20, result.stdout)

    def test_mandatory_roles_are_bound_to_deepseek_and_llama_model_identity(self):
        def mutate(bundle):
            self.pass_branch(bundle)
            bundle["assignments"][0]["model_id"] = "approved/unrelated-model"
        result = self.run_bundle(mutate)
        self.assertEqual(result.returncode, 20, result.stdout)

    def test_prerequisite_blockers_reject_already_attached_child_evidence(self):
        def mutate(bundle):
            self.pass_branch(bundle)
            self.attach_child(bundle)
            bundle["history"]["complete"] = False
        result = self.run_bundle(mutate)
        self.assertEqual(result.returncode, 20, result.stdout)
        self.assertEqual(
            json.loads(result.stdout)["checks"][0]["code"],
            "contract.inconsistent_status",
        )

    def test_malformed_nested_values_are_contract_failures(self):
        mutations = [
            lambda bundle: bundle["baseline"].update(state=[]),
            lambda bundle: bundle["baseline"]["candidates"][0].update(revalidation_status=[]),
            lambda bundle: bundle["regression_policy"].update(status=[]),
            lambda bundle: bundle["delta"]["surfaces"][0].update(classification=[]),
            lambda bundle: bundle["manifest_impact"]["future_changes"][0].update(action=[]),
            lambda bundle: bundle["assignments"][0].update(mode=[]),
        ]
        for mutation in mutations:
            with self.subTest(mutation=repr(mutation)):
                def mutate(bundle, mutation=mutation):
                    self.pass_branch(bundle)
                    mutation(bundle)
                result = self.run_bundle(mutate)
                self.assertEqual(result.returncode, 20, result.stdout)
                self.assertEqual(
                    json.loads(result.stdout)["checks"][0]["code"],
                    "contract.invalid_value",
                )

    def test_affected_dependency_can_report_future_removal(self):
        def mutate(bundle):
            self.pass_branch(bundle)
            bundle["manifest_impact"]["future_changes"][0]["action"] = "future_remove"

        result = self.run_bundle(mutate)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["manifest_outcome"], "report_only")

    def test_mandatory_assignment_binds_exact_model_family_identity(self):
        mutations = [
            lambda bundle: bundle["assignments"][0].update(model_id="unapproved/deepseek-counterfeit"),
            lambda bundle: bundle["assignments"][1].update(model_id="unapproved/llama-counterfeit"),
        ]
        for mutation in mutations:
            with self.subTest(mutation=repr(mutation)):
                def mutate(bundle, mutation=mutation):
                    self.pass_branch(bundle)
                    mutation(bundle)
                result = self.run_bundle(mutate)
                self.assertEqual(result.returncode, 20, result.stdout)

    def test_unknown_surface_does_not_disable_manifest_closure_for_classified_surfaces(self):
        def mutate(bundle):
            self.pass_branch(bundle)
            bundle["delta"]["declared_unknown_impact_count"] = 1
            bundle["delta"]["surfaces"][2]["classification"] = "unknown"
            bundle["manifest_impact"]["future_changes"].pop()

        result = self.run_bundle(mutate)
        self.assertEqual(result.returncode, 20, result.stdout)
        self.assertEqual(
            json.loads(result.stdout)["checks"][0]["path"],
            "$.manifest_impact.future_changes",
        )

    def test_three_gate_hardware_result_cannot_satisfy_mandatory_regression(self):
        def mutate(bundle):
            self.pass_branch(bundle)
            self.attach_child(bundle, status="passed", environment="real_dlc_hardware", eligible=True)
            child = bundle["child_bundles"][0]["model_adaptation_bundle"]
            keep = {"chunked_prefill", "runtime_dispatch", "real_dlc_hardware"}
            child["run_spec"]["gates"] = [gate for gate in child["run_spec"]["gates"] if gate in keep]
            child["result_evidence"]["gates"] = [gate for gate in child["result_evidence"]["gates"] if gate["id"] in keep]
            child["run_spec"]["digest"] = self.digest(child["run_spec"])
            child["result_evidence"]["run_spec_digest"] = child["run_spec"]["digest"]
            child["result_evidence"]["digest"] = self.digest(child["result_evidence"])
            child["execution"]["result_reference"] = child["result_evidence"]["digest"]
            child["handoff"]["result_evidence_digest"] = child["result_evidence"]["digest"]
            child["handoff"]["digest"] = self.digest(child["handoff"])

        result = self.run_bundle(mutate)
        self.assertEqual(result.returncode, 20, result.stdout)

    def test_synthetic_passed_children_cannot_claim_production_acceptance(self):
        def mutate(bundle):
            self.pass_branch(bundle)
            self.attach_child(bundle, assignment_index=0, status="passed", environment="real_dlc_hardware", eligible=True)
            self.attach_child(bundle, assignment_index=1, status="passed", environment="real_dlc_hardware", eligible=True)

        result = self.run_bundle(mutate)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "not_verified")
        self.assertEqual(report["reason_code"], "blocked_missing_regression_policy")
        self.assertFalse(report["acceptance_eligible"])
        self.assertFalse(report["finalize_eligible"])
        self.assertEqual(report["alignment_outcome"], "unchanged")
        self.assertTrue(all(state == "not_verified" for state in report["evidence_states"].values()))

    def test_child_manifest_identity_must_match_parent_report(self):
        def mutate(bundle):
            self.pass_branch(bundle)
            self.attach_child(bundle)
            child = bundle["child_bundles"][0]["model_adaptation_bundle"]
            child["run_spec"]["target"]["manifest_digest"] = "sha256:" + "6" * 64
            child["run_spec"]["digest"] = self.digest(child["run_spec"])
            child["result_evidence"]["run_spec_digest"] = child["run_spec"]["digest"]
            child["result_evidence"]["digest"] = self.digest(child["result_evidence"])
            child["execution"]["result_reference"] = child["result_evidence"]["digest"]
            child["handoff"]["result_evidence_digest"] = child["result_evidence"]["digest"]
            child["handoff"]["digest"] = self.digest(child["handoff"])

        result = self.run_bundle(mutate)
        self.assertEqual(result.returncode, 20, result.stdout)

    def test_coordinated_child_dependency_must_exist_in_parent_impact(self):
        def mutate(bundle):
            self.pass_branch(bundle)
            self.attach_child(bundle)
            assignment = bundle["assignments"][0]
            assignment["expected_dependency_ids"] = ["invented.dependency"]
            child = bundle["child_bundles"][0]["model_adaptation_bundle"]
            child["compatibility"] = {
                "changed": True,
                "changed_dependency_ids": ["invented.dependency"],
            }
            child["handoff"]["changed_dependency_ids"] = ["invented.dependency"]
            child["handoff"]["digest"] = self.digest(child["handoff"])

        result = self.run_bundle(mutate)
        self.assertEqual(result.returncode, 20, result.stdout)
        self.assertEqual(
            json.loads(result.stdout)["checks"][0]["path"],
            "$.assignments[0].expected_dependency_ids",
        )

    def test_mandatory_child_failure_precedes_freeze_blocker(self):
        def mutate(bundle):
            self.pass_branch(bundle)
            self.attach_child(bundle, status="failed")
            bundle["freeze"].update(commit_required=True, commit_authorized=False)

        result = self.run_bundle(mutate)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["reason_code"], "mandatory_child_failed")


if __name__ == "__main__":
    unittest.main()
