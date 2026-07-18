import json
import hashlib
import subprocess
import shutil
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "scripts" / "validate-vllm-dlc-contracts.py"
FIXTURES = Path(__file__).with_name("fixtures")


class ContractCliTests(unittest.TestCase):
    def run_cli(self, *arguments: str, skills_root: Path = ROOT) -> subprocess.CompletedProcess[str]:
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
                *arguments,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def synthetic_candidate_root(self, identity: str) -> tuple[tempfile.TemporaryDirectory, Path, Path]:
        temporary = tempfile.TemporaryDirectory(dir="/tmp/kilo")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
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
        return temporary, root, package

    def run_mutated_contract(self, fixture_name: str, mutate) -> subprocess.CompletedProcess[str]:
        document = json.loads((FIXTURES / "positive" / fixture_name).read_text())
        mutate(document)
        document.pop("digest", None)
        payload = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        document["digest"] = f"sha256:{hashlib.sha256(payload.encode()).hexdigest()}"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as fixture:
            json.dump(document, fixture)
            fixture.flush()
            return self.run_cli("contract", fixture.name)

    def run_v2_contract(self, mutate=lambda document: None):
        document = {
            "artifact_destination": "/tmp/kilo/ticket06-operational-fixture",
            "assets": {
                "model_path": "/tmp/kilo/model",
                "model_digest": "sha256:" + "1" * 64,
                "tokenizer_path": "/tmp/kilo/tokenizer",
                "tokenizer_digest": "sha256:" + "2" * 64,
                "processor_path": None,
                "processor_digest": None,
            },
            "claim_level": "operational_only",
            "campaign_digest": None,
            "campaign_manifest": None,
            "contract_kind": "run_spec",
            "deployment_profile": {
                "role": "llama_tp1_dense_operational",
                "model_id": "fixture/llama-dense",
                "model_revision": "3" * 40,
                "tokenizer_revision": "4" * 40,
                "processor_revision": None,
                "approval_digest": None,
                "approval_path": None,
                "tp_derivation_digest": None,
                "tp_derivation_path": None,
                "tensor_parallel_size": 1,
                "pipeline_parallel_size": 1,
                "dtype": "bfloat16",
                "quantization": "none",
                "context_limit": 8192,
                "device_capacity_mib": 63360,
                "max_num_batched_tokens": 1024,
                "chunked_prefill_requested": True,
                "served_model_name": "fixture-model",
                "real_weights": True,
            },
            "finalization_intent": "none",
            "gates": [
                "service_ready", "models_api", "completions_api", "chat_api",
                "long_prefix_api", "server_liveness",
                "long_prefix_threshold_exercised",
                "lifecycle_cleanup",
                "eager_dlc_configuration_observed",
                "real_dlc_hardware_operational", "repository_state",
                "artifact_closure", "llama_tp1_dense_operational",
            ],
            "hardware_observation": {
                "provider_class": "fixture",
                "qualification_executable": None,
                "qualification_executable_digest": None,
                "smi_source_root": None,
                "smi_source_sha": None,
                "expected_pid_namespace": None,
                "expected_mount_namespace": None,
                "adapter_version": "vllm-dlc-smi-adapter/v1",
                "executable": "/tmp/kilo/cltech_smi_fixture",
                "executable_digest": "sha256:" + "5" * 64,
                "required_device_count": 1,
                "sample_points": ["before_launch", "after_ready", "during_request", "after_cleanup"],
                "tool_digest": None,
                "tool_executable": None,
            },
            "launch": {
                "provider_class": "fixture",
                "executable": "/usr/bin/python3",
                "executable_digest": "sha256:" + "6" * 64,
                "working_directory": "/tmp/kilo",
                "arguments": ["fixture-server"],
                "environment": {},
            },
            "mode": "diagnostic_only",
            "repository_guards": ["/work/vllm", "/work/vllm-dlc"],
            "requests": [
                {"id": "models", "role": "models", "order": 1, "timeout_class": "request", "output_token_allowance": 0, "payload_digest": "sha256:" + "7" * 64},
                {"id": "completion", "role": "completion", "order": 2, "timeout_class": "request", "output_token_allowance": 1, "payload_digest": "sha256:" + "8" * 64},
                {"id": "chat", "role": "chat", "order": 3, "timeout_class": "request", "output_token_allowance": 1, "payload_digest": "sha256:" + "9" * 64},
                {"id": "long-prefix", "role": "long_prefix", "order": 4, "timeout_class": "long_prefix", "output_token_allowance": 1, "payload_digest": "sha256:" + "a" * 64},
            ],
            "run_id": "ticket06-v2-fixture",
            "schema_version": "vllm-dlc-run-spec/v2",
            "target": {
                "vllm_sha": subprocess.run(["git", "-C", "/work/vllm", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip(),
                "vllm_dlc_sha": subprocess.run(["git", "-C", "/work/vllm-dlc", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip(),
                "manifest_digest": "sha256:" + "d" * 64,
            },
            "timeouts": {"startup_seconds": 600, "request_seconds": 120, "long_prefix_seconds": 300},
            "workflow": "model_adaptation",
        }
        mutate(document)
        payload = json.dumps(
            document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        document["digest"] = f"sha256:{hashlib.sha256(payload).hexdigest()}"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as fixture:
            json.dump(document, fixture)
            fixture.flush()
            return self.run_cli("contract", fixture.name)

    def run_model_adaptation_v2_contract(
        self,
        mutate=lambda document, approval, derivation: None,
        config_contents='{"hidden_size":896,"model_type":"qwen2"}\n',
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "model"
            model.mkdir()
            config = model / "config.json"
            config.write_text(config_contents)
            weights = model / "model.safetensors"
            weights.write_bytes(b"approved-weight-bytes")

            def asset_digest(path: Path) -> str:
                accumulator = hashlib.sha256()
                for candidate in sorted(path.rglob("*")):
                    if candidate.is_file():
                        accumulator.update(candidate.relative_to(path).as_posix().encode())
                        accumulator.update(b"\0")
                        accumulator.update(candidate.read_bytes())
                        accumulator.update(b"\0")
                return f"sha256:{accumulator.hexdigest()}"

            model_digest = asset_digest(model)
            config_digest = f"sha256:{hashlib.sha256(config.read_bytes()).hexdigest()}"
            target = {
                "vllm_sha": subprocess.run(["git", "-C", "/work/vllm", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip(),
                "vllm_dlc_sha": subprocess.run(["git", "-C", "/work/vllm-dlc", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip(),
                "manifest_digest": "sha256:" + "d" * 64,
            }
            approval = {
                "approved": True,
                "model_id": "fixture/internal-model",
                "model_path": str(model),
                "role": "model_adaptation_profile_operational",
                "schema_version": "vllm-dlc-model-adaptation-approval/v1",
                "tensor_parallel_size": 1,
            }
            derivation = {
                "capacity_utilization_limit_bps": 9000,
                "config_digest": config_digest,
                "config_hidden_size": 896,
                "config_model_type": "qwen2",
                "config_path": str(config),
                "device_capacity_mib": 63360,
                "dtype": "bfloat16",
                "model_asset_bytes": weights.stat().st_size,
                "model_digest": model_digest,
                "model_id": "fixture/internal-model",
                "model_path": str(model),
                "quantization": "none",
                "required_capacity_mib": 1,
                "result_tensor_parallel_size": 1,
                "schema_version": "vllm-dlc-tp-derivation/v1",
                "target": dict(target),
            }
            approval_path = root / "approval.json"
            derivation_path = root / "tp-derivation.json"
            approval_path.write_text(json.dumps(approval))
            derivation_path.write_text(json.dumps(derivation))

            def configure(document):
                document["deployment_profile"].update(
                    approval_digest=f"sha256:{hashlib.sha256(approval_path.read_bytes()).hexdigest()}",
                    approval_path=str(approval_path),
                    device_capacity_mib=63360,
                    model_id="fixture/internal-model",
                    role="model_adaptation_profile_operational",
                    tensor_parallel_size=1,
                    tp_derivation_digest=f"sha256:{hashlib.sha256(derivation_path.read_bytes()).hexdigest()}",
                    tp_derivation_path=str(derivation_path),
                )
                document["assets"].update(
                    model_digest=model_digest,
                    model_path=str(model),
                    tokenizer_digest=model_digest,
                    tokenizer_path=str(model),
                )
                document["gates"][-1] = "model_adaptation_profile_operational"
                document["target"] = target
                mutate(document, approval, derivation)
                approval_path.write_text(json.dumps(approval))
                derivation_path.write_text(json.dumps(derivation))
                document["deployment_profile"].update(
                    approval_digest=f"sha256:{hashlib.sha256(approval_path.read_bytes()).hexdigest()}",
                    tp_derivation_digest=f"sha256:{hashlib.sha256(derivation_path.read_bytes()).hexdigest()}",
                )

            return self.run_v2_contract(configure)

    @staticmethod
    def configure_operational_v2(document, tensor_parallel_size=1):
        launcher = ROOT / "scripts" / "launch-vllm-dlc-server.py"
        smi_adapter = ROOT / "scripts" / "observe-cltech-smi.py"
        qualification_adapter = (
            ROOT / "scripts" / "qualify-vllm-dlc-smi-environment.py"
        )
        role = (
            "llama_tp1_dense_operational"
            if tensor_parallel_size == 1
            else "deepseek_tp2_operational"
        )
        model_id = "fixture/llama-dense" if tensor_parallel_size == 1 else "fixture/deepseek"
        document.update(
            campaign_digest="sha256:" + "e" * 64,
            campaign_manifest="/tmp/kilo/ticket06-campaign.json",
            mode="operational_regression",
        )
        document["deployment_profile"].update(
            model_id=model_id,
            role=role,
            tensor_parallel_size=tensor_parallel_size,
        )
        document["gates"][-1] = role
        document["hardware_observation"].update(
            provider_class="local_process",
            qualification_executable=str(qualification_adapter),
            qualification_executable_digest="sha256:" + "a" * 64,
            smi_source_root="/work/chipltech-smi",
            smi_source_sha="b" * 40,
            expected_pid_namespace="pid:[1]",
            expected_mount_namespace="mnt:[2]",
            executable=str(smi_adapter),
            required_device_count=tensor_parallel_size,
            tool_digest="sha256:" + "c" * 64,
            tool_executable="/usr/bin/cltech-smi",
        )
        document["launch"].update(
            provider_class="local_process",
            executable=str(Path(sys.executable).resolve()),
            working_directory="/work/vllm",
            environment={
                "DLC_VISIBLE_DEVICES": ",".join(
                    str(index) for index in range(tensor_parallel_size)
                ),
                "DLC_SYN_COPY_ASYNC": "O2",
            },
            arguments=[
                str(launcher.resolve()),
                "--ready-file", "/tmp/kilo/ticket06.ready",
                "--host", "127.0.0.1",
                "--port", "18080",
                "--model", document["assets"]["model_path"],
                "--tokenizer", document["assets"]["tokenizer_path"],
                "--served-model-name", document["deployment_profile"]["served_model_name"],
                "--tensor-parallel-size", str(tensor_parallel_size),
                "--pipeline-parallel-size", "1",
                "--dtype", "bfloat16",
                "--quantization", "none",
                "--max-model-len", "8192",
                "--max-num-batched-tokens", "1024",
                "--enforce-eager",
                "--expected-vllm-root", "/work/vllm",
                "--expected-vllm-dlc-root", "/work/vllm-dlc",
            ],
        )

    def test_operational_v2_is_closed_world_without_changing_v1(self) -> None:
        valid = self.run_v2_contract()
        invalid_claim = self.run_v2_contract(
            lambda document: document.update(claim_level="authoritative")
        )
        invalid_finalize = self.run_v2_contract(
            lambda document: document.update(finalization_intent="eligible_only")
        )
        unknown = self.run_v2_contract(
            lambda document: document.update(unsealed_behavior=True)
        )

        self.assertEqual(valid.returncode, 0, valid.stderr)
        self.assertEqual(json.loads(valid.stdout)["checks"][0]["code"], "contract.valid")
        for result in (invalid_claim, invalid_finalize, unknown):
            self.assertEqual(result.returncode, 20, result.stdout)

    def test_operational_v2_requires_canonical_dlc_visible_devices_for_tp(self) -> None:
        for tensor_parallel_size, expected in ((1, "2"), (2, "2,3")):
            with self.subTest(tensor_parallel_size=tensor_parallel_size):
                def mutate(document):
                    self.configure_operational_v2(document, tensor_parallel_size)
                    document["launch"]["environment"] = {
                        "DLC_VISIBLE_DEVICES": expected,
                        "DLC_SYN_COPY_ASYNC": "O2",
                    }

                result = self.run_v2_contract(mutate)
                self.assertEqual(result.returncode, 0, result.stdout)

    def test_operational_v2_rejects_invalid_device_visibility(self) -> None:
        cases = (
            {},
            {"DLC_VISIBLE_DEVICES": "2,3"},
            {"DLC_SYN_COPY_ASYNC": "O2"},
            {"DLC_VISIBLE_DEVICES": "2,3", "DLC_SYN_COPY_ASYNC": "O1"},
            {"DLC_VISIBLE_DEVICES": "2,3", "DLC_SYN_COPY_ASYNC": "o2"},
            {"CHIPLTECH_VISIBLE_DEVICES": "2,3", "DLC_SYN_COPY_ASYNC": "O2"},
            {"DLC_VISIBLE_DEVICES": "all", "DLC_SYN_COPY_ASYNC": "O2"},
            {"DLC_VISIBLE_DEVICES": "2,2", "DLC_SYN_COPY_ASYNC": "O2"},
            {"DLC_VISIBLE_DEVICES": "2, 3", "DLC_SYN_COPY_ASYNC": "O2"},
            {"DLC_VISIBLE_DEVICES": "2,", "DLC_SYN_COPY_ASYNC": "O2"},
            {"DLC_VISIBLE_DEVICES": "-1,2", "DLC_SYN_COPY_ASYNC": "O2"},
            {"DLC_VISIBLE_DEVICES": "02,3", "DLC_SYN_COPY_ASYNC": "O2"},
            {"DLC_VISIBLE_DEVICES": "2", "DLC_SYN_COPY_ASYNC": "O2"},
            {"DLC_VISIBLE_DEVICES": "2,3,4", "DLC_SYN_COPY_ASYNC": "O2"},
            {
                "DLC_VISIBLE_DEVICES": "2,3",
                "DLC_SYN_COPY_ASYNC": "O2",
                "EXTRA": "value",
            },
        )
        for environment in cases:
            with self.subTest(environment=environment):
                def mutate(document):
                    self.configure_operational_v2(document, 2)
                    document["launch"]["environment"] = environment

                result = self.run_v2_contract(mutate)
                self.assertEqual(result.returncode, 20, result.stdout)
                check = json.loads(result.stdout)["checks"][0]
                self.assertEqual(check["code"], "contract.invalid_value")
                self.assertEqual(check["path"], "$.launch.environment")

    def test_operational_v2_accepts_digest_identified_internal_model_assets(self) -> None:
        result = self.run_v2_contract(
            lambda document: document["deployment_profile"].update(
                model_revision=None,
                tokenizer_revision=None,
                processor_revision=None,
            )
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["checks"][0]["code"], "contract.valid")

    def test_model_adaptation_v2_validates_approval_and_tp_derivation_bytes(self) -> None:
        result = self.run_model_adaptation_v2_contract()

        self.assertEqual(result.returncode, 0, result.stdout)

    def test_model_adaptation_v2_rejects_open_world_tp_derivation(self) -> None:
        result = self.run_model_adaptation_v2_contract(
            lambda document, approval, derivation: derivation.update(note="trust me")
        )

        self.assertEqual(result.returncode, 20, result.stdout)
        self.assertEqual(json.loads(result.stdout)["checks"][0]["code"], "contract.unknown_field")

    def test_model_adaptation_v2_binds_approval_and_derivation_to_profile(self) -> None:
        cases = (
            lambda document, approval, derivation: approval.update(model_id="other/model"),
            lambda document, approval, derivation: derivation.update(dtype="float16"),
            lambda document, approval, derivation: derivation.update(result_tensor_parallel_size=2),
            lambda document, approval, derivation: derivation["target"].update(manifest_digest="sha256:" + "e" * 64),
        )
        for mutate in cases:
            with self.subTest(mutation=repr(mutate)):
                result = self.run_model_adaptation_v2_contract(mutate)
                self.assertEqual(result.returncode, 20, result.stdout)
                self.assertEqual(json.loads(result.stdout)["checks"][0]["code"], "contract.identity_mismatch")

    def test_model_adaptation_v2_binds_actual_model_and_config_bytes(self) -> None:
        cases = (
            (lambda document, approval, derivation: derivation.update(model_asset_bytes=1), "artifact.digest_mismatch"),
            (lambda document, approval, derivation: derivation.update(config_digest="sha256:" + "f" * 64), "artifact.digest_mismatch"),
            (lambda document, approval, derivation: derivation.update(config_model_type="qwen3"), "artifact.digest_mismatch"),
            (lambda document, approval, derivation: derivation.update(config_hidden_size=1024), "artifact.digest_mismatch"),
            (lambda document, approval, derivation: derivation.update(model_digest="sha256:" + "f" * 64), "contract.identity_mismatch"),
        )
        for mutate, code in cases:
            with self.subTest(mutation=repr(mutate)):
                result = self.run_model_adaptation_v2_contract(mutate)
                self.assertEqual(result.returncode, 20, result.stdout)
                self.assertEqual(json.loads(result.stdout)["checks"][0]["code"], code)

    def test_model_adaptation_v2_rejects_wrong_required_capacity(self) -> None:
        result = self.run_model_adaptation_v2_contract(
            lambda document, approval, derivation: derivation.update(required_capacity_mib=2)
        )

        self.assertEqual(result.returncode, 20, result.stdout)
        self.assertEqual(json.loads(result.stdout)["checks"][0]["code"], "contract.invalid_value")

    def test_model_adaptation_v2_rejects_wrong_formula_result_tp(self) -> None:
        def mutate(document, approval, derivation):
            derivation["result_tensor_parallel_size"] = 2
            document["deployment_profile"]["tensor_parallel_size"] = 2
            approval["tensor_parallel_size"] = 2

        result = self.run_model_adaptation_v2_contract(mutate)

        self.assertEqual(result.returncode, 20, result.stdout)
        self.assertEqual(json.loads(result.stdout)["checks"][0]["code"], "contract.invalid_value")

    def test_model_adaptation_v2_rejects_wrong_config_semantics(self) -> None:
        cases = ('{"hidden_size":896,"model_type":""}\n', '{"hidden_size":0,"model_type":"qwen2"}\n')
        for config_contents in cases:
            with self.subTest(config_contents=config_contents):
                result = self.run_model_adaptation_v2_contract(
                    config_contents=config_contents
                )
                self.assertEqual(result.returncode, 20, result.stdout)
                self.assertEqual(
                    json.loads(result.stdout)["checks"][0]["code"],
                    "contract.invalid_value",
                )

    def test_valid_run_spec_is_deterministic(self) -> None:
        fixture = FIXTURES / "positive" / "run-spec.json"

        first = self.run_cli("contract", str(fixture))
        second = self.run_cli("contract", str(fixture))

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        report = json.loads(first.stdout)
        self.assertEqual(report["contract_version"], "vllm-dlc-contract/v1")
        self.assertEqual(report["overall_status"], "passed")
        self.assertEqual(report["checks"][0]["code"], "contract.valid")
        self.assertIn("index_diff_digest", report["repository_before"])
        self.assertEqual(report["repository_before"], report["repository_after"])

    def test_unsupported_schema_version_is_contract_failure(self) -> None:
        fixture = FIXTURES / "negative" / "unsupported-version.json"

        result = self.run_cli("contract", str(fixture))

        self.assertEqual(result.returncode, 20)
        report = json.loads(result.stdout)
        self.assertEqual(report["overall_status"], "failed")
        self.assertEqual(
            report["checks"][0],
            {
                "code": "contract.unsupported_schema_version",
                "path": "$.schema_version",
                "status": "failed",
            },
        )

    def test_unknown_field_is_contract_failure(self) -> None:
        fixture = FIXTURES / "negative" / "unknown-field.json"

        result = self.run_cli("contract", str(fixture))

        self.assertEqual(result.returncode, 20)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "contract.unknown_field")
        self.assertEqual(report["checks"][0]["path"], "$.surprise")

    def test_missing_full_identity_is_contract_failure(self) -> None:
        fixture = FIXTURES / "negative" / "missing-full-identity.json"

        result = self.run_cli("contract", str(fixture))

        self.assertEqual(result.returncode, 20)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "contract.missing_identity")
        self.assertEqual(report["checks"][0]["path"], "$.target.vllm_sha")

    def test_inconsistent_digest_is_contract_failure(self) -> None:
        fixture = FIXTURES / "negative" / "inconsistent-digest.json"

        result = self.run_cli("contract", str(fixture))

        self.assertEqual(result.returncode, 20)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "contract.digest_mismatch")
        self.assertEqual(report["checks"][0]["path"], "$.digest")

    def test_valid_result_evidence_contract_passes(self) -> None:
        fixture = FIXTURES / "positive" / "result-evidence.json"

        result = self.run_cli("contract", str(fixture))

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["overall_status"], "passed")

    def test_invalid_gate_status_is_contract_failure(self) -> None:
        fixture = FIXTURES / "negative" / "invalid-status.json"
        result = self.run_cli("contract", str(fixture))
        self.assertEqual(result.returncode, 20)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "contract.invalid_status")

    def test_valid_parent_child_handoff_passes(self) -> None:
        fixture = FIXTURES / "positive" / "parent-child-handoff.json"
        result = self.run_cli("contract", str(fixture))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_valid_skill_package_passes(self) -> None:
        target = FIXTURES / "package" / "positive" / "target.json"
        result = self.run_cli("package", str(target))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_ticket03_public_targets_are_registered(self) -> None:
        fixtures = ROOT / "tests" / "vllm_dlc_model_adaptation" / "fixtures"
        _, skills_root, package = self.synthetic_candidate_root("model-adaptation")
        routing = json.loads((fixtures / "routing.json").read_text())
        routing["candidate_package"] = "package.json"
        routing_path = package.parent / "routing.json"
        routing_path.write_text(json.dumps(routing))
        cases = [
            ("candidate-package", package, skills_root),
            ("model-adaptation-bundle", fixtures / "contract-available-not-verified.json", ROOT),
            ("model-adaptation-routing", routing_path, skills_root),
        ]
        for target, fixture, skills_root_arg in cases:
            with self.subTest(target=target):
                result = self.run_cli(target, str(fixture), skills_root=skills_root_arg)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report["repository_before"], report["repository_after"])

    def test_ticket04_public_targets_are_registered(self) -> None:
        fixtures = ROOT / "tests" / "vllm_dlc_main_to_main" / "fixtures"
        _, skills_root, package = self.synthetic_candidate_root("main-to-main-upgrade")
        routing = json.loads((fixtures / "routing.json").read_text())
        routing["candidate_package"] = "package.json"
        routing_path = package.parent / "routing.json"
        routing_path.write_text(json.dumps(routing))
        bundle = json.loads((fixtures / "complete-not-verified.json").read_text())
        bundle["preflight"].update(
            current_branch="dev-skills",
            required_branch="main",
            branch_matches_main=False,
        )
        temporary = tempfile.NamedTemporaryFile(mode="w", suffix=".json")
        self.addCleanup(temporary.close)
        json.dump(bundle, temporary)
        temporary.flush()
        cases = [
            ("candidate-package", package, skills_root),
            ("main-to-main-bundle", Path(temporary.name), ROOT),
            ("main-to-main-routing", routing_path, skills_root),
        ]
        for target, fixture, skills_root_arg in cases:
            with self.subTest(target=target):
                result = self.run_cli(target, str(fixture), skills_root=skills_root_arg)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report["repository_before"], report["repository_after"])

    def test_ticket05_public_targets_are_registered(self) -> None:
        fixtures = ROOT / "tests" / "vllm_dlc_knowledge" / "fixtures"
        for target, fixture in (
            ("knowledge-package", fixtures / "knowledge-package.json"),
            ("prompt-dry-run", fixtures / "prompt-dry-run.json"),
        ):
            with self.subTest(target=target):
                result = self.run_cli(target, str(fixture))
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report["repository_before"], report["repository_after"])

    def test_missing_publication_surface_has_distinct_failure(self) -> None:
        target = FIXTURES / "package" / "missing-publication" / "target.json"
        result = self.run_cli("package", str(target))
        self.assertEqual(result.returncode, 30)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "publication.inconsistent")

    def test_copied_http_quality_gate_has_distinct_failure(self) -> None:
        target = FIXTURES / "package" / "duplicate-gate" / "target.json"
        result = self.run_cli("package", str(target))
        self.assertEqual(result.returncode, 40)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "quality_gate.duplicated")

    def test_repository_snapshot_mismatch_has_distinct_failure(self) -> None:
        fixture = FIXTURES / "negative" / "repository-state-mismatch.json"
        result = self.run_cli("repository-guard", str(fixture))
        self.assertEqual(result.returncode, 50)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "repository_state.changed")

    def test_diagnostic_result_cannot_claim_acceptance(self) -> None:
        fixture = FIXTURES / "negative" / "diagnostic-acceptance.json"
        result = self.run_cli("contract", str(fixture))
        self.assertEqual(result.returncode, 20)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "contract.inconsistent_status")

    def test_handoff_requires_full_subject_identities(self) -> None:
        fixture = FIXTURES / "negative" / "handoff-identity-mismatch.json"
        result = self.run_cli("contract", str(fixture))
        self.assertEqual(result.returncode, 20)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "contract.missing_identity")

    def test_malformed_json_has_stable_invalid_input_report(self) -> None:
        fixture = FIXTURES / "negative" / "malformed.json"
        result = self.run_cli("contract", str(fixture))
        self.assertEqual(result.returncode, 10)
        report = json.loads(result.stdout)
        self.assertEqual(report["overall_status"], "failed")
        self.assertEqual(report["checks"][0]["code"], "input.invalid")
        self.assertIn("invalid_input:", result.stderr)
        self.assertEqual(report["repository_before"], report["repository_after"])
        self.assertEqual(report["repository_state"], "preserved")

    def test_digest_valid_but_incomplete_contract_fails(self) -> None:
        fixture = FIXTURES / "negative" / "missing-required-field.json"
        result = self.run_cli("contract", str(fixture))
        self.assertEqual(result.returncode, 20)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "contract.missing_required_field")
        self.assertEqual(report["checks"][0]["path"], "$.artifact_destination")

    def test_live_package_checks_fixed_repository_surfaces(self) -> None:
        result = self.run_cli("live-package", "fixture-model-adaptation")
        self.assertEqual(result.returncode, 30)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "publication.inconsistent")

    def test_result_gate_requires_complete_evidence_identity(self) -> None:
        fixture = FIXTURES / "negative" / "incomplete-gate.json"
        result = self.run_cli("contract", str(fixture))
        self.assertEqual(result.returncode, 20)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "contract.invalid_gate")

    def test_nested_unknown_field_is_contract_failure(self) -> None:
        fixture = FIXTURES / "negative" / "nested-unknown-field.json"
        result = self.run_cli("contract", str(fixture))
        self.assertEqual(result.returncode, 20)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "contract.unknown_field")
        self.assertEqual(report["checks"][0]["path"], "$.hardware.surprise")

    def test_single_copied_http_assertion_is_duplicate_gate(self) -> None:
        target = FIXTURES / "package" / "single-http-gate" / "target.json"
        result = self.run_cli("package", str(target))
        self.assertEqual(result.returncode, 40)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "quality_gate.duplicated")

    def test_handoff_rejects_invalid_status(self) -> None:
        fixture = FIXTURES / "negative" / "invalid-handoff-status.json"
        result = self.run_cli("contract", str(fixture))
        self.assertEqual(result.returncode, 20)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "contract.invalid_status")

    def test_result_artifact_rejects_unknown_field(self) -> None:
        fixture = FIXTURES / "negative" / "invalid-artifact.json"
        result = self.run_cli("contract", str(fixture))
        self.assertEqual(result.returncode, 20)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "contract.unknown_field")
        self.assertEqual(report["checks"][0]["path"], "$.artifacts[0].surprise")

    def test_run_spec_rejects_non_full_vllm_dlc_identity(self) -> None:
        fixture = FIXTURES / "negative" / "invalid-vllm-dlc-sha.json"
        result = self.run_cli("contract", str(fixture))
        self.assertEqual(result.returncode, 20)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "contract.missing_identity")
        self.assertEqual(report["checks"][0]["path"], "$.target.vllm_dlc_sha")

    def test_contract_v1_rejects_invalid_nested_values(self) -> None:
        cases = [
            ("run-spec.json", lambda value: value["target"].update(manifest_digest="bad")),
            ("run-spec.json", lambda value: value.update(mode="unknown")),
            ("run-spec.json", lambda value: value["deployment_profile"].update(tensor_parallel_size=0)),
            ("run-spec.json", lambda value: value["runtime_policy"].update(execution="compile")),
            ("result-evidence.json", lambda value: value.update(execution_environment="unknown")),
            ("result-evidence.json", lambda value: value.update(run_spec_digest="bad")),
            ("parent-child-handoff.json", lambda value: value.update(result_evidence_digest="bad")),
            ("parent-child-handoff.json", lambda value: value.update(changed_dependency_ids=["same", "same"])),
        ]
        for fixture_name, mutate in cases:
            with self.subTest(fixture=fixture_name, mutation=repr(mutate)):
                result = self.run_mutated_contract(fixture_name, mutate)
                self.assertEqual(result.returncode, 20, result.stdout)

    def test_invalid_repository_root_is_not_verified(self) -> None:
        fixture = FIXTURES / "positive" / "run-spec.json"
        result = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "--skills-root",
                str(ROOT),
                "--knowledge-root",
                "/work/chipltech-knowledge-base",
                "--vllm-dlc-root",
                "/tmp/kilo/not-a-vllm-dlc-repository",
                "contract",
                str(fixture),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 10)
        report = json.loads(result.stdout)
        self.assertEqual(report["repository_state"], "not_verified")
        self.assertNotIn("repository_before", report)

    def test_package_requires_shared_contract_ownership_marker(self) -> None:
        target = FIXTURES / "package" / "missing-shared-contract" / "target.json"
        result = self.run_cli("package", str(target))
        self.assertEqual(result.returncode, 40)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "quality_gate.duplicated")

    def test_package_requires_resolvable_conditional_reference(self) -> None:
        source = FIXTURES / "package" / "positive"
        with tempfile.TemporaryDirectory() as directory:
            target_root = Path(directory) / "package"
            shutil.copytree(source, target_root)
            skill_file = target_root / "skill" / "SKILL.md"
            skill_file.write_text(
                skill_file.read_text().replace("../knowledge.md", "../missing.md")
            )
            result = self.run_cli("package", str(target_root / "target.json"))

        self.assertEqual(result.returncode, 20, result.stdout)
        self.assertEqual(json.loads(result.stdout)["checks"][0]["code"], "package.invalid")

    def test_publication_requires_exact_skill_identity(self) -> None:
        source = FIXTURES / "package" / "positive"
        with tempfile.TemporaryDirectory() as directory:
            target_root = Path(directory) / "package"
            shutil.copytree(source, target_root)
            for name in (
                "catalog.md",
                "engineering-catalog.md",
                "plugin.json",
                "skillhub.yaml",
                "kilo-linker.sh",
                "install.md",
            ):
                path = target_root / name
                path.write_text(
                    path.read_text().replace(
                        "fixture-model-adaptation",
                        "not-fixture-model-adaptation-extra",
                    )
                )
            result = self.run_cli("package", str(target_root / "target.json"))

        self.assertEqual(result.returncode, 30, result.stdout)

    def test_result_uses_mandatory_status_precedence(self) -> None:
        def mutate(document):
            document["overall_status"] = "blocked"
            document["exit_code"] = 6
            document["gates"][0]["status"] = "failed"

        result = self.run_mutated_contract("result-evidence.json", mutate)
        self.assertEqual(result.returncode, 20)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "contract.inconsistent_status")

    def test_result_requires_non_empty_unique_gate_identities(self) -> None:
        cases = [
            lambda document: document.update(gates=[]),
            lambda document: document["gates"].append(document["gates"][0].copy()),
        ]
        for mutate in cases:
            with self.subTest(mutation=repr(mutate)):
                result = self.run_mutated_contract("result-evidence.json", mutate)
                self.assertEqual(result.returncode, 20, result.stdout)
                self.assertEqual(
                    json.loads(result.stdout)["checks"][0]["code"],
                    "contract.invalid_gate",
                )

    def test_acceptance_run_spec_requires_real_weights_and_hardware(self) -> None:
        def mutate(document):
            document["hardware"] = {
                "class": "fake_server",
                "device_count": 0,
                "required": False,
            }
            document["deployment_profile"]["real_weights"] = False

        result = self.run_mutated_contract("run-spec.json", mutate)
        self.assertEqual(result.returncode, 20, result.stdout)
        self.assertEqual(
            json.loads(result.stdout)["checks"][0]["code"],
            "contract.inconsistent_status",
        )

    def test_artifact_destination_cannot_enter_guarded_repository(self) -> None:
        result = self.run_mutated_contract(
            "run-spec.json",
            lambda document: document.update(
                artifact_destination="/work/vllm-dlc/ticket-artifacts"
            ),
        )
        self.assertEqual(result.returncode, 20)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "contract.read_only_destination")

    def test_contract_identifiers_are_non_empty(self) -> None:
        cases = [
            ("run-spec.json", lambda document: document.update(run_id="")),
            ("result-evidence.json", lambda document: document["gates"][0].update(id="")),
        ]
        for fixture_name, mutate in cases:
            with self.subTest(fixture=fixture_name):
                result = self.run_mutated_contract(fixture_name, mutate)
                self.assertEqual(result.returncode, 20, result.stdout)

    def test_package_frontmatter_requires_exact_identity_and_description(self) -> None:
        source = FIXTURES / "package" / "positive"
        with tempfile.TemporaryDirectory() as directory:
            target_root = Path(directory) / "package"
            shutil.copytree(source, target_root)
            skill_file = target_root / "skill" / "SKILL.md"
            skill = skill_file.read_text()
            skill = skill.replace(
                "name: fixture-model-adaptation",
                "name: fixture-model-adaptation-extra",
            ).replace(
                "description: Adapt a specified model for the DLC Platform when model compatibility work is required.",
                "description:",
            )
            skill_file.write_text(skill)
            result = self.run_cli("package", str(target_root / "target.json"))
        self.assertEqual(result.returncode, 20)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "package.invalid")

    def test_package_rejects_structured_duplicate_quality_gates(self) -> None:
        additions = [
            "```bash\npython smoke-runner.py --run-spec spec.json\n```",
            "Assert status_code == 200 and response.json has non-empty text.",
            "Require observed_chunk_count > 1 before acceptance.",
            "Assert triton_kernel_executed == false.",
            "Assert dynamo_compiled == false.",
        ]
        source = FIXTURES / "package" / "positive"
        for addition in additions:
            with self.subTest(addition=addition), tempfile.TemporaryDirectory() as directory:
                target_root = Path(directory) / "package"
                shutil.copytree(source, target_root)
                knowledge = target_root / "knowledge.md"
                knowledge.write_text(f"{knowledge.read_text()}\n{addition}\n")
                result = self.run_cli("package", str(target_root / "target.json"))
                self.assertEqual(result.returncode, 40, result.stdout)

        for replacement in (
            "not_shared_contract: vllm-dlc-contract/v1",
            "shared_contract: vllm-dlc-contract/v1-extra",
        ):
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as directory:
                target_root = Path(directory) / "package"
                shutil.copytree(source, target_root)
                knowledge = target_root / "knowledge.md"
                knowledge.write_text(
                    knowledge.read_text().replace(
                        "shared_contract: vllm-dlc-contract/v1", replacement
                    )
                )
                result = self.run_cli("package", str(target_root / "target.json"))
                self.assertEqual(result.returncode, 40, result.stdout)

    def test_argument_failure_is_guarded_after_root_bootstrap(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "--vllm-dlc-root",
                "/work/vllm-dlc",
                "contract",
                str(FIXTURES / "positive" / "run-spec.json"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 10)
        report = json.loads(result.stdout)
        self.assertEqual(report["repository_state"], "preserved")
        self.assertEqual(report["repository_before"], report["repository_after"])

    def test_malformed_contract_shapes_are_machine_readable(self) -> None:
        cases = [
            ([], 10, "input.invalid"),
            (
                {
                    **json.loads((FIXTURES / "positive" / "result-evidence.json").read_text()),
                    "gates": {},
                },
                20,
                "contract.invalid_type",
            ),
            (
                {
                    **json.loads((FIXTURES / "positive" / "result-evidence.json").read_text()),
                    "gates": [None],
                },
                20,
                "contract.invalid_type",
            ),
        ]
        for document, exit_code, code in cases:
            if isinstance(document, dict):
                document.pop("digest", None)
                payload = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                document["digest"] = f"sha256:{hashlib.sha256(payload.encode()).hexdigest()}"
            with self.subTest(code=code), tempfile.NamedTemporaryFile(mode="w", suffix=".json") as fixture:
                json.dump(document, fixture)
                fixture.flush()
                result = self.run_cli("contract", fixture.name)
                self.assertEqual(result.returncode, exit_code, result.stderr)
                self.assertEqual(json.loads(result.stdout)["checks"][0]["code"], code)

    def test_package_structure_rejects_semantic_bypasses(self) -> None:
        mutations = [
            lambda skill, agent: (skill.replace(
                "description: Adapt a specified model for the DLC Platform when model compatibility work is required.",
                "description: null",
            ), agent),
            lambda skill, agent: (skill.replace(
                "---\n\nshared_contract:",
                "disable-model-invocation: true # YAML boolean\n---\n\nshared_contract:",
            ), agent),
            lambda skill, agent: (skill.replace("conditional_reference:", "reference:"), agent),
            lambda skill, agent: (skill, "# interface: display_name: short_description: default_prompt:\n"),
        ]
        source = FIXTURES / "package" / "positive"
        for mutate in mutations:
            with self.subTest(mutation=repr(mutate)), tempfile.TemporaryDirectory() as directory:
                target_root = Path(directory) / "package"
                shutil.copytree(source, target_root)
                skill_file = target_root / "skill" / "SKILL.md"
                agent_file = target_root / "skill" / "agents" / "openai.yaml"
                skill, agent = mutate(skill_file.read_text(), agent_file.read_text())
                skill_file.write_text(skill)
                agent_file.write_text(agent)
                result = self.run_cli("package", str(target_root / "target.json"))
                self.assertEqual(result.returncode, 20, result.stdout)
                self.assertEqual(json.loads(result.stdout)["checks"][0]["code"], "package.invalid")

    def test_package_rejects_unfenced_runner_and_numeric_gate_assertions(self) -> None:
        additions = [
            "$ python smoke-runner.py --run-spec spec.json",
            "$ wget http://localhost:8000/health",
            "Acceptance requires prefill_chunk_count == 2.",
        ]
        source = FIXTURES / "package" / "positive"
        for addition in additions:
            with self.subTest(addition=addition), tempfile.TemporaryDirectory() as directory:
                target_root = Path(directory) / "package"
                shutil.copytree(source, target_root)
                knowledge = target_root / "knowledge.md"
                knowledge.write_text(f"{knowledge.read_text()}\n{addition}\n")
                result = self.run_cli("package", str(target_root / "target.json"))
                self.assertEqual(result.returncode, 40, result.stdout)

    def test_quality_gate_detector_preserves_prose_and_rejects_structures(self) -> None:
        allowed = [
            "HTTP 2xx alone is insufficient evidence because generated content may be empty.",
            "Triton is forbidden in stable acceptance because eager execution is supported.",
            "The runner remains external to this package.",
            "Use the `runner` identity from the shared contract.",
            "Use the `runner 'identity` exactly as documented.",
            "Python runner remains external to this package.",
            "Runner behavior remains externally owned.",
            "Require reviewers to discuss HTTP status handling in prose.",
            "Acceptance requires evidence from the shared contract. Generated content is rationale only.",
            "Acceptance requires the shared gate because Triton is forbidden in stable execution.",
            "Compile execution must remain diagnostic until support exists.",
        ]
        prohibited = [
            "```zsh\nprintf ok\n```",
            "```fish\nprintf ok\n```",
            "$ python -m httpie GET http://localhost/health",
            "$ pipenv run httpie GET http://localhost/health",
            "Acceptance requires 2 <= observed_chunk_count.",
            "Assert 2 < prefill_chunk_count.",
            "Assert prefill_chunk_count != 1.",
            "$ http GET http://localhost/health",
            "Assert HTTP status == 200.",
            "Assert response.json is valid.",
            "Assert choices text is non-empty.",
            "if response.status_code != 200: raise RuntimeError()",
            "if not response.json()['choices'][0]['text']: raise RuntimeError()",
            "smoke-runner.py --run-spec spec.json",
            "runner --run-spec spec.json",
            "The endpoint is /v1/embeddings.",
        ]
        source = FIXTURES / "package" / "positive"
        for addition in allowed + prohibited:
            with self.subTest(addition=addition), tempfile.TemporaryDirectory() as directory:
                target_root = Path(directory) / "package"
                shutil.copytree(source, target_root)
                knowledge = target_root / "knowledge.md"
                knowledge.write_text(f"{knowledge.read_text()}\n{addition}\n")
                result = self.run_cli("package", str(target_root / "target.json"))
                expected = 0 if addition in allowed else 40
                self.assertEqual(result.returncode, expected, result.stdout)

    def test_exact_markers_wrapped_commands_and_shell_fences_are_enforced(self) -> None:
        additions = [
            "``` bash\nprintf ok\n```",
            "~~~bash\nprintf ok\n~~~",
            "$ env TOKEN=x curl http://localhost/health",
            "$ conda run python3 -m vllm_dlc.smoke_runner --run-spec spec.json",
            "$ /usr/bin/env python3 -m vllm_dlc.smoke_runner --run-spec spec.json",
            "$ TOKEN=x python3 smoke-runner.py --run-spec spec.json",
            "$ bash -c 'curl http://localhost:8000/health'",
            "$ sh -c 'http GET http://localhost:8000/health'",
            "$ env bash -c 'curl http://localhost:8000/health'",
            "$ sudo sh -c 'http GET http://localhost:8000/health'",
            "$ bash -lc 'curl http://localhost:8000/health'",
            "$ sh -ec 'curl http://localhost:8000/health'",
            "$ bash --noprofile -c 'curl http://localhost/health'",
            "$ bash -O extglob -c 'curl http://localhost/health'",
            "$ sh -o errexit -c 'curl http://localhost/health'",
            "$ bash -c -- 'curl http://localhost/health'",
            "$ python3 -c 'import requests; requests.get(\"http://localhost/health\")'",
            "$ env -i sudo -u root sh -o errexit -c 'http GET http://localhost/health'",
            "$ env TOKEN=x http GET http://localhost/health",
            "$ uv run http GET http://localhost/health",
            "$ pipenv run http GET http://localhost/health",
            "$ conda run http GET http://localhost/health",
            "$ sudo curl http://localhost/health",
        ]
        source = FIXTURES / "package" / "positive"
        for addition in additions:
            with self.subTest(addition=addition), tempfile.TemporaryDirectory() as directory:
                target_root = Path(directory) / "package"
                shutil.copytree(source, target_root)
                knowledge = target_root / "knowledge.md"
                knowledge.write_text(f"{knowledge.read_text()}\n{addition}\n")
                result = self.run_cli("package", str(target_root / "target.json"))
                self.assertEqual(result.returncode, 40, result.stdout)

    def test_repository_snapshot_handles_broken_untracked_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(
                ["git", "-C", str(root), "-c", "user.name=test", "-c", "user.email=test@example.com", "commit", "--allow-empty", "-m", "baseline", "-q"],
                check=True,
            )
            os.symlink("missing-target", root / "broken-link")
            result = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "--skills-root",
                    str(ROOT),
                    "--knowledge-root",
                    "/work/chipltech-knowledge-base",
                    "--vllm-dlc-root",
                    str(root),
                    "contract",
                    str(FIXTURES / "positive" / "run-spec.json"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["repository_before"], report["repository_after"])

    def test_invalid_input_compares_original_before_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(
                ["git", "-C", str(root), "-c", "user.name=test", "-c", "user.email=test@example.com", "commit", "--allow-empty", "-m", "baseline", "-q"],
                check=True,
            )
            fixture = root / "fixture.fifo"
            os.mkfifo(fixture)
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(CLI),
                    "--skills-root",
                    str(ROOT),
                    "--knowledge-root",
                    "/work/chipltech-knowledge-base",
                    "--vllm-dlc-root",
                    str(root),
                    "contract",
                    str(fixture),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            writer = os.open(fixture, os.O_WRONLY)
            (root / "changed-after-before-snapshot").write_text("changed")
            os.write(writer, b"{")
            os.close(writer)
            stdout, stderr = process.communicate(timeout=10)

        self.assertEqual(process.returncode, 50, stderr)
        report = json.loads(stdout)
        self.assertEqual(report["repository_state"], "changed")
        self.assertNotEqual(report["repository_before"], report["repository_after"])

if __name__ == "__main__":
    unittest.main()
