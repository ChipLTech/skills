import hashlib
import importlib.util
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "run-vllm-dlc-smoke.py"
VALIDATOR = ROOT / "scripts" / "validate-vllm-dlc-contracts.py"
SMI_OBSERVER = ROOT / "scripts" / "observe-cltech-smi.py"
SMI_PREFLIGHT = ROOT / "scripts" / "qualify-vllm-dlc-smi-environment.py"
SERVER = Path(__file__).with_name("fake_openai_server.py")
SMI_ADAPTER = Path(__file__).with_name("fake_smi_adapter.py")


def load_smi_observer():
    spec = importlib.util.spec_from_file_location("observe_cltech_smi", SMI_OBSERVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeLsofProcess:
    def __init__(self, stdout, returncode=0, stderr="", pid=9000):
        self.pid = pid
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def communicate(self, timeout):
        return self.stdout, self.stderr


def canonical_digest(document):
    payload = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


class SmokeRunnerCliTests(unittest.TestCase):
    def run_v2_fixture(
        self,
        run_id="ticket06-v2-fixture",
        offline_cleanup_pids=None,
        tamper_tp_derivation=False,
        tensor_parallel_size=1,
        offline_observation_mutator=None,
    ):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            root = Path(directory)
            scenario = root / "scenario.json"
            scenario.write_text(json.dumps({
                "served_model": "fixture-model",
                "long_prefix": {"delay": 0.2},
            }))
            ready_file = root / "ready"
            artifacts = root / "artifacts"
            tokenizer = root / "tokenizer"
            tokenizer.mkdir()
            (tokenizer / "fixture-tokenizer.json").write_text(json.dumps({
                "schema_version": "vllm-dlc-fixture-whitespace-tokenizer/v1"
            }))
            model = root / "model"
            model.mkdir()
            config = model / "config.json"
            config.write_text('{"hidden_size":896,"model_type":"qwen2"}\n')
            (model / "model.safetensors").write_text("fixture weights")
            executable = Path(sys.executable)

            def file_digest(path):
                return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"

            def directory_digest(path):
                value = hashlib.sha256()
                for candidate in sorted(path.rglob("*")):
                    if candidate.is_file():
                        value.update(candidate.relative_to(path).as_posix().encode())
                        value.update(b"\0")
                        value.update(candidate.read_bytes())
                        value.update(b"\0")
                return f"sha256:{value.hexdigest()}"

            requests = [
                ("models", "models", 0, {"served_model": "fixture-model"}),
                ("completion", "completion", 1, {"model": "fixture-model", "prompt": "smoke", "max_tokens": 1}),
                ("chat", "chat", 1, {"model": "fixture-model", "messages": [{"role": "user", "content": "smoke"}], "max_tokens": 1}),
                ("long-prefix", "long_prefix", 1, {
                    "model": "fixture-model",
                    "prompt": " ".join(f"operational-{index}" for index in range(1025)),
                    "max_tokens": 1,
                }),
            ]
            spec = {
                "artifact_destination": str(artifacts),
                "assets": {
                    "model_path": str(model), "model_digest": directory_digest(model),
                    "tokenizer_path": str(tokenizer), "tokenizer_digest": directory_digest(tokenizer),
                    "processor_path": None, "processor_digest": None,
                },
                "claim_level": "operational_only",
                "campaign_digest": None,
                "campaign_manifest": None,
                "contract_kind": "run_spec",
                "deployment_profile": {
                    "role": (
                        "llama_tp1_dense_operational"
                        if tensor_parallel_size == 1
                        else "deepseek_tp2_operational"
                    ),
                    "model_id": "fixture/llama-dense",
                    "model_revision": "3" * 40, "tokenizer_revision": "4" * 40,
                    "processor_revision": None,
                    "tensor_parallel_size": tensor_parallel_size,
                    "approval_digest": None, "tp_derivation_digest": None,
                    "approval_path": None, "tp_derivation_path": None,
                    "pipeline_parallel_size": 1, "dtype": "bfloat16",
                    "quantization": "none", "context_limit": 8192, "device_capacity_mib": 63360,
                    "max_num_batched_tokens": 1024, "chunked_prefill_requested": True,
                    "served_model_name": "fixture-model", "real_weights": False,
                },
                "finalization_intent": "none",
                "gates": [
                    "service_ready", "models_api", "completions_api", "chat_api",
                    "long_prefix_api", "server_liveness", "long_prefix_threshold_exercised",
                    "lifecycle_cleanup",
                    "eager_dlc_configuration_observed", "real_dlc_hardware_operational",
                    "repository_state", "artifact_closure",
                    (
                        "llama_tp1_dense_operational"
                        if tensor_parallel_size == 1
                        else "deepseek_tp2_operational"
                    ),
                ],
                "hardware_observation": {
                    "provider_class": "fixture", "adapter_version": "vllm-dlc-smi-adapter/v1",
                    "qualification_executable": None,
                    "qualification_executable_digest": None,
                    "smi_source_root": None, "smi_source_sha": None,
                    "expected_pid_namespace": None,
                    "expected_mount_namespace": None,
                    "executable": str(SMI_ADAPTER), "executable_digest": file_digest(SMI_ADAPTER),
                    "required_device_count": tensor_parallel_size,
                    "sample_points": ["before_launch", "after_ready", "during_request", "after_cleanup"],
                    "tool_digest": None, "tool_executable": None,
                },
                "launch": {
                    "provider_class": "fixture", "executable": str(executable),
                    "executable_digest": file_digest(executable), "working_directory": str(root),
                    "arguments": [str(SERVER), "--scenario", str(scenario), "--ready-file", str(ready_file)],
                    "environment": {},
                },
                "mode": "diagnostic_only", "repository_guards": ["/work/vllm", "/work/vllm-dlc"],
                "requests": [
                    {
                        "id": request_id, "role": role, "order": index,
                        "timeout_class": "long_prefix" if role == "long_prefix" else "request",
                        "output_token_allowance": allowance,
                        "payload_digest": canonical_digest(payload),
                    }
                    for index, (request_id, role, allowance, payload) in enumerate(requests, 1)
                ],
                "run_id": run_id, "schema_version": "vllm-dlc-run-spec/v2",
                "target": {
                    "vllm_sha": subprocess.run(["git", "-C", "/work/vllm", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip(),
                    "vllm_dlc_sha": subprocess.run(["git", "-C", "/work/vllm-dlc", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip(),
                    "manifest_digest": "sha256:" + "d" * 64,
                },
                "timeouts": {"startup_seconds": 5, "request_seconds": 2, "long_prefix_seconds": 2},
                "workflow": "model_adaptation",
            }
            if tamper_tp_derivation:
                approval_path = root / "approval.json"
                derivation_path = root / "tp-derivation.json"
                approval_path.write_text(json.dumps({
                    "approved": True,
                    "model_id": "fixture/internal-model",
                    "model_path": str(model),
                    "role": "model_adaptation_profile_operational",
                    "schema_version": "vllm-dlc-model-adaptation-approval/v1",
                    "tensor_parallel_size": 1,
                }))
                derivation_path.write_text(json.dumps({
                    "capacity_utilization_limit_bps": 9000,
                    "config_digest": file_digest(config),
                    "config_hidden_size": 896,
                    "config_model_type": "qwen2",
                    "config_path": str(config),
                    "device_capacity_mib": 63360,
                    "dtype": "bfloat16",
                    "model_asset_bytes": (model / "model.safetensors").stat().st_size,
                    "model_digest": directory_digest(model),
                    "model_id": "fixture/internal-model",
                    "model_path": str(model),
                    "quantization": "none",
                    "required_capacity_mib": 1,
                    "result_tensor_parallel_size": 1,
                    "schema_version": "vllm-dlc-tp-derivation/v1",
                    "target": spec["target"],
                }))
                spec["deployment_profile"].update(
                    approval_digest=file_digest(approval_path),
                    approval_path=str(approval_path),
                    model_id="fixture/internal-model",
                    role="model_adaptation_profile_operational",
                    tp_derivation_digest=file_digest(derivation_path),
                    tp_derivation_path=str(derivation_path),
                )
                spec["gates"][-1] = "model_adaptation_profile_operational"
            spec["digest"] = canonical_digest(spec)
            spec_path = root / "run-spec.json"
            spec_path.write_text(json.dumps(spec))

            result = subprocess.run(
                [sys.executable, str(RUNNER), "--run-spec", str(spec_path), "--vllm-dlc-root", "/work/vllm-dlc"],
                capture_output=True, text=True, timeout=20,
            )

            reference = json.loads(result.stdout)
            evidence = json.loads(Path(reference["uri"].removeprefix("file://")).read_text())
            observations = json.loads(next(
                Path(row["uri"].removeprefix("file://")).read_text()
                for row in evidence["artifacts"] if row["id"] == "smi_observations"
            ))
            validation = None
            if offline_cleanup_pids is not None:
                observations[3]["devices"][0]["observed_pids"] = offline_cleanup_pids
            if offline_observation_mutator is not None:
                offline_observation_mutator(observations)
            if offline_cleanup_pids is not None or offline_observation_mutator is not None:
                observation_payload = json.dumps(
                    observations,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
                smi_artifact = next(
                    row for row in evidence["artifacts"] if row["id"] == "smi_observations"
                )
                Path(smi_artifact["uri"].removeprefix("file://")).write_bytes(
                    observation_payload
                )
                smi_artifact["digest"] = (
                    f"sha256:{hashlib.sha256(observation_payload).hexdigest()}"
                )
                evidence["digest"] = canonical_digest({
                    key: value for key, value in evidence.items() if key != "digest"
                })
                Path(reference["uri"].removeprefix("file://")).write_text(
                    json.dumps(evidence)
                )
                reference["digest"] = evidence["digest"]
                reference_path = root / "offline-result-reference.json"
                reference_path.write_text(json.dumps(reference))
            if tamper_tp_derivation:
                derivation_path.write_text('{"tampered":true}')
            if (
                offline_cleanup_pids is not None
                or offline_observation_mutator is not None
                or tamper_tp_derivation
            ):
                reference_path = root / "offline-result-reference.json"
                reference_path.write_text(json.dumps(reference))
                validation = subprocess.run(
                    [
                        sys.executable, str(VALIDATOR), "--skills-root", str(ROOT),
                        "--knowledge-root", "/work/chipltech-knowledge-base",
                        "--vllm-dlc-root", "/work/vllm-dlc",
                        "operational-result-reference", str(reference_path),
                    ],
                    capture_output=True,
                    text=True,
                )
            return result, evidence, observations, validation

    def test_v2_hardware_gate_uses_inventory_and_pid_union_independently(self):
        cases = (
            (1, "ticket06-shared-pids-d8-o8-p1"),
            (2, "ticket06-shared-pids-d8-o1-p2"),
        )
        for tensor_parallel_size, run_id in cases:
            with self.subTest(tensor_parallel_size=tensor_parallel_size):
                result, evidence, observations, validation = self.run_v2_fixture(
                    run_id,
                    tensor_parallel_size=tensor_parallel_size,
                    offline_observation_mutator=lambda rows: None,
                )

                self.assertEqual(result.returncode, 0, evidence["diagnostics"])
                during = observations[2]["devices"]
                self.assertEqual(len(during), 8)
                occupied = [row for row in during if row["process_pids"]]
                self.assertEqual(len(occupied), 1 if tensor_parallel_size == 2 else 8)
                self.assertEqual(
                    len({pid for row in occupied for pid in row["process_pids"]}),
                    tensor_parallel_size,
                )
                self.assertEqual(validation.returncode, 0, validation.stdout)

    def test_v2_hardware_gate_rejects_invalid_inventory_or_pid_union(self):
        cases = (
            ("ticket06-shared-pids-d8-o8-p1", "hardware.process_shape"),
            ("ticket06-shared-pids-d1-o1-p2", "hardware.insufficient"),
            ("ticket06-duplicate-devices", "smi.invalid_schema"),
        )
        for run_id, diagnostic in cases:
            with self.subTest(run_id=run_id):
                result, evidence, _, _ = self.run_v2_fixture(
                    run_id, tensor_parallel_size=2
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn(diagnostic, [row["code"] for row in evidence["diagnostics"]])

    def test_v2_offline_hardware_gate_rejects_invalid_inventory_or_pid_union(self):
        def keep_one_process(observations):
            for device in observations[2]["devices"]:
                device["process_pids"] = device["process_pids"][:1]

        def keep_one_device(observations):
            observations[2]["devices"] = observations[2]["devices"][:1]

        def duplicate_device_identity(observations):
            observations[2]["devices"][1]["device_key"] = observations[2]["devices"][0]["device_key"]

        for mutate in (keep_one_process, keep_one_device, duplicate_device_identity):
            with self.subTest(mutate=mutate.__name__):
                result, _, _, validation = self.run_v2_fixture(
                    "ticket06-shared-pids-d8-o8-p2",
                    tensor_parallel_size=2,
                    offline_observation_mutator=mutate,
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(validation.returncode, 20, validation.stdout)
                self.assertEqual(
                    json.loads(validation.stdout)["checks"][0]["path"],
                    "$.artifacts.smi_observations[2]",
                )

    def test_v2_offline_validation_reuses_tp_derivation_validator(self):
        result, _, _, validation = self.run_v2_fixture(
            "ticket06-tampered-tp-derivation",
            tamper_tp_derivation=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(validation.returncode, 20, validation.stdout)
        self.assertEqual(
            json.loads(validation.stdout)["checks"][0]["code"],
            "artifact.digest_mismatch",
        )

    def test_v2_cleanup_rejects_observed_pid_added_after_baseline(self):
        result, evidence, _, _ = self.run_v2_fixture(
            "ticket06-baseline-occupied-cleanup-added-pid"
        )

        self.assertEqual(result.returncode, 41)
        self.assertEqual(
            next(row for row in evidence["gates"] if row["id"] == "lifecycle_cleanup")["status"],
            "failed",
        )
        self.assertIn(
            "device PID beyond pre-launch baseline survived cleanup",
            [row["message"] for row in evidence["diagnostics"]],
        )

    def test_v2_cleanup_allows_unchanged_baseline_occupancy(self):
        result, evidence, observations, _ = self.run_v2_fixture(
            "ticket06-baseline-occupied"
        )

        self.assertEqual(result.returncode, 0, json.dumps(evidence["diagnostics"]))
        self.assertEqual(observations[0]["devices"][0]["observed_pids"], [700001])
        self.assertEqual(observations[3]["devices"][0]["observed_pids"], [700001])
        self.assertEqual(
            next(row for row in evidence["gates"] if row["id"] == "lifecycle_cleanup")["status"],
            "passed",
        )

    def test_v2_offline_validation_rejects_observed_pid_added_after_baseline(self):
        _, _, _, validation = self.run_v2_fixture(
            "ticket06-baseline-occupied", [700001, 700002]
        )

        self.assertEqual(validation.returncode, 20, validation.stdout)
        self.assertEqual(
            json.loads(validation.stdout)["checks"][0],
            {
                "code": "artifact.invalid",
                "path": "$.artifacts.smi_observations[3]",
                "status": "failed",
            },
        )

    def test_v2_offline_validation_allows_unchanged_baseline_occupancy(self):
        _, _, _, validation = self.run_v2_fixture(
            "ticket06-baseline-occupied", [700001]
        )

        self.assertEqual(validation.returncode, 0, validation.stdout)

    def test_v2_runner_owns_fixture_lifecycle_but_cannot_promote_it(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            root = Path(directory)
            scenario = root / "scenario.json"
            scenario.write_text(json.dumps({
                "served_model": "fixture-model",
                "long_prefix": {"delay": 0.2},
            }))
            ready_file = root / "ready"
            artifacts = root / "artifacts"
            tokenizer = root / "tokenizer"
            tokenizer.mkdir()
            (tokenizer / "fixture-tokenizer.json").write_text(json.dumps({
                "schema_version": "vllm-dlc-fixture-whitespace-tokenizer/v1"
            }))
            model = root / "model"
            model.mkdir()
            (model / "weights.fixture").write_text("fixture weights")
            executable = Path(sys.executable)

            def file_digest(path):
                return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"

            def directory_digest(path):
                value = hashlib.sha256()
                for candidate in sorted(path.rglob("*")):
                    if candidate.is_file():
                        value.update(candidate.relative_to(path).as_posix().encode())
                        value.update(b"\0")
                        value.update(candidate.read_bytes())
                        value.update(b"\0")
                return f"sha256:{value.hexdigest()}"

            requests = [
                ("models", "models", 0, {"served_model": "fixture-model"}),
                ("completion", "completion", 1, {"model": "fixture-model", "prompt": "smoke", "max_tokens": 1}),
                ("chat", "chat", 1, {"model": "fixture-model", "messages": [{"role": "user", "content": "smoke"}], "max_tokens": 1}),
                ("long-prefix", "long_prefix", 1, {
                    "model": "fixture-model",
                    "prompt": " ".join(f"operational-{index}" for index in range(1025)),
                    "max_tokens": 1,
                }),
            ]
            spec = {
                "artifact_destination": str(artifacts),
                "assets": {
                    "model_path": str(model), "model_digest": directory_digest(model),
                    "tokenizer_path": str(tokenizer), "tokenizer_digest": directory_digest(tokenizer),
                    "processor_path": None, "processor_digest": None,
                },
                "claim_level": "operational_only",
                "campaign_digest": None,
                "campaign_manifest": None,
                "contract_kind": "run_spec",
                "deployment_profile": {
                    "role": "llama_tp1_dense_operational", "model_id": "fixture/llama-dense",
                    "model_revision": "3" * 40, "tokenizer_revision": "4" * 40,
                    "processor_revision": None, "tensor_parallel_size": 1,
                    "approval_digest": None, "tp_derivation_digest": None,
                    "approval_path": None, "tp_derivation_path": None,
                    "pipeline_parallel_size": 1, "dtype": "bfloat16",
                    "quantization": "none", "context_limit": 8192, "device_capacity_mib": 63360,
                    "max_num_batched_tokens": 1024, "chunked_prefill_requested": True,
                    "served_model_name": "fixture-model", "real_weights": False,
                },
                "finalization_intent": "none",
                "gates": [
                    "service_ready", "models_api", "completions_api", "chat_api",
                    "long_prefix_api", "server_liveness", "long_prefix_threshold_exercised",
                    "lifecycle_cleanup",
                    "eager_dlc_configuration_observed", "real_dlc_hardware_operational",
                    "repository_state", "artifact_closure", "llama_tp1_dense_operational",
                ],
                "hardware_observation": {
                    "provider_class": "fixture", "adapter_version": "vllm-dlc-smi-adapter/v1",
                    "qualification_executable": None,
                    "qualification_executable_digest": None,
                    "smi_source_root": None, "smi_source_sha": None,
                    "expected_pid_namespace": None,
                    "expected_mount_namespace": None,
                    "executable": str(SMI_ADAPTER), "executable_digest": file_digest(SMI_ADAPTER),
                    "required_device_count": 1,
                    "sample_points": ["before_launch", "after_ready", "during_request", "after_cleanup"],
                    "tool_digest": None, "tool_executable": None,
                },
                "launch": {
                    "provider_class": "fixture", "executable": str(executable),
                    "executable_digest": file_digest(executable), "working_directory": str(root),
                    "arguments": [str(SERVER), "--scenario", str(scenario), "--ready-file", str(ready_file)],
                    "environment": {},
                },
                "mode": "diagnostic_only", "repository_guards": ["/work/vllm", "/work/vllm-dlc"],
                "requests": [
                    {
                        "id": request_id, "role": role, "order": index,
                        "timeout_class": "long_prefix" if role == "long_prefix" else "request",
                        "output_token_allowance": allowance,
                        "payload_digest": canonical_digest(payload),
                    }
                    for index, (request_id, role, allowance, payload) in enumerate(requests, 1)
                ],
                "run_id": "ticket06-v2-fixture", "schema_version": "vllm-dlc-run-spec/v2",
                "target": {
                    "vllm_sha": subprocess.run(["git", "-C", "/work/vllm", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip(),
                    "vllm_dlc_sha": subprocess.run(["git", "-C", "/work/vllm-dlc", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip(),
                    "manifest_digest": "sha256:" + "d" * 64,
                },
                "timeouts": {"startup_seconds": 5, "request_seconds": 2, "long_prefix_seconds": 2},
                "workflow": "model_adaptation",
            }
            spec["digest"] = canonical_digest(spec)
            spec_path = root / "run-spec.json"
            spec_path.write_text(json.dumps(spec))

            result = subprocess.run(
                [sys.executable, str(RUNNER), "--run-spec", str(spec_path), "--vllm-dlc-root", "/work/vllm-dlc"],
                capture_output=True, text=True, timeout=20,
            )

            reference = json.loads(result.stdout)
            evidence = json.loads(Path(reference["uri"].removeprefix("file://")).read_text())
            self.assertEqual(result.returncode, 0, json.dumps(evidence["diagnostics"]))
            self.assertEqual(evidence["schema_version"], "vllm-dlc-result-evidence/v2")
            self.assertEqual(evidence["evidence_class"], "fixture_operational_validation")
            self.assertEqual(evidence["authoritativeness"], "operational_only")
            self.assertFalse(evidence["completion_eligible"])
            self.assertFalse(evidence["acceptance_eligible"])
            self.assertEqual(evidence["overall_status"], "passed")
            self.assertTrue(all(row["status"] == "passed" for row in evidence["gates"]))
            reference_path = root / "result-reference.json"
            reference_path.write_text(json.dumps(reference))
            validation_command = [
                sys.executable, str(VALIDATOR), "--skills-root", str(ROOT),
                "--knowledge-root", "/work/chipltech-knowledge-base",
                "--vllm-dlc-root", "/work/vllm-dlc",
                "operational-result-reference", str(reference_path),
            ]
            validation = subprocess.run(
                validation_command, capture_output=True, text=True
            )
            self.assertEqual(validation.returncode, 0, validation.stderr)
            report = json.loads(validation.stdout)
            self.assertFalse(report["completion_eligible"])
            self.assertEqual(report["evidence_class"], "fixture_operational_validation")
            campaign = {
                "alignment_action": "unchanged",
                "campaign_id": "sha256:" + "f" * 64,
                "claim_level": "operational_only",
                "finalization_intent": "none",
                "manifest_action": "report_only",
                "roles": [
                    {"result_reference": str(reference_path), "role": "model_adaptation_profile_operational"},
                    {"result_reference": str(reference_path), "role": "deepseek_tp2_operational"},
                    {"result_reference": str(reference_path), "role": "llama_tp1_dense_operational"},
                ],
                "schema_version": "vllm-dlc-ticket06-operational-index/v1",
                "ticket07_action": "not_published",
            }
            campaign["digest"] = canonical_digest(campaign)
            campaign_path = root / "campaign.json"
            campaign_path.write_text(json.dumps(campaign))
            campaign_validation = subprocess.run(
                [
                    sys.executable, str(VALIDATOR), "--skills-root", str(ROOT),
                    "--knowledge-root", "/work/chipltech-knowledge-base",
                    "--vllm-dlc-root", "/work/vllm-dlc",
                    "ticket06-evidence", str(campaign_path),
                ],
                capture_output=True, text=True,
            )
            self.assertEqual(campaign_validation.returncode, 20, campaign_validation.stdout)
            self.assertEqual(
                json.loads(campaign_validation.stdout)["checks"][0]["code"],
                "ticket06.fixture_ineligible",
            )
            smi_artifact = next(
                row for row in evidence["artifacts"] if row["id"] == "smi_observations"
            )
            Path(smi_artifact["uri"].removeprefix("file://")).write_text("tampered")
            tampered = subprocess.run(
                validation_command, capture_output=True, text=True
            )
            self.assertEqual(tampered.returncode, 20, tampered.stdout)
            self.assertFalse(ready_file.exists() and self._listener_is_live(int(ready_file.read_text())))

    @staticmethod
    def _listener_is_live(port):
        with socket.socket() as connection:
            connection.settimeout(0.2)
            return connection.connect_ex(("127.0.0.1", port)) == 0

    def test_invalid_endpoint_has_stable_machine_result(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            spec_path = Path(directory) / "missing.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "--run-spec",
                    str(spec_path),
                    "--endpoint",
                    "http://127.0.0.1:bad",
                    "--vllm-dlc-root",
                    "/work/vllm-dlc",
                ],
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 10)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "input.invalid")
        self.assertEqual(report["repository_state"], "preserved")

    def test_invalid_repository_has_stable_machine_result(self):
        result = subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "--run-spec",
                "/tmp/kilo/missing-run-spec.json",
                "--endpoint",
                "http://127.0.0.1:1",
                "--vllm-dlc-root",
                "/tmp/kilo/not-a-git-repository",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 10)
        self.assertEqual(
            json.loads(result.stdout)["code"], "repository_state.not_verified"
        )

    def test_argument_failure_preserves_guarded_repository_snapshot(self):
        result = subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "--vllm-dlc-root",
                "/work/vllm-dlc",
                "--run-spec",
                "/tmp/kilo/missing-run-spec.json",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 10)
        report = json.loads(result.stdout)
        self.assertEqual(report["repository_state"], "preserved")
        self.assertEqual(report["repository_before"], report["repository_after"])

    def run_scenario(self, scenario, timeouts=None):
        temporary = tempfile.TemporaryDirectory(dir="/tmp/kilo")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        scenario_path = root / "scenario.json"
        scenario_path.write_text(json.dumps({"served_model": "fixture-model", **scenario}))
        ready_file = root / "ready"
        server = subprocess.Popen(
            [
                sys.executable,
                str(SERVER),
                "--scenario",
                str(scenario_path),
                "--ready-file",
                str(ready_file),
            ]
        )
        self.addCleanup(self.stop_server, server)
        deadline = time.monotonic() + 5
        while not ready_file.exists() and time.monotonic() < deadline:
            if server.poll() is not None:
                self.fail("fake server exited before binding its socket")
            time.sleep(0.01)
        self.assertTrue(ready_file.exists(), "fake server did not bind its socket")
        port = int(ready_file.read_text())
        spec = {
            "artifact_destination": str(root / "artifacts"),
            "contract_kind": "run_spec",
            "deployment_profile": {
                "model_id": "fixture/model", "model_revision": "1" * 40,
                "tokenizer_revision": "2" * 40, "processor_revision": None,
                "tensor_parallel_size": 1, "pipeline_parallel_size": 1,
                "dtype": "bfloat16", "quantization": "none", "context_limit": 8192,
                "max_num_batched_tokens": 1024, "chunked_prefill": True,
                "served_model_name": "fixture-model", "real_weights": False,
            },
            "finalization_intent": "none",
            "gates": ["service_ready", "models_api", "completions_api", "chat_api", "long_prefix_api", "server_liveness", "chunked_prefill", "runtime_dispatch", "real_dlc_hardware"],
            "hardware": {"class": "fake_server", "device_count": 0, "required": False},
            "mode": "diagnostic_only", "run_id": "fake-smoke-001",
            "runtime_policy": {"execution": "eager", "triton_execution": "forbidden", "compile_execution": "forbidden"},
            "schema_version": "vllm-dlc-run-spec/v1",
            "target": {"vllm_sha": "3" * 40, "vllm_dlc_sha": "4" * 40, "manifest_digest": "sha256:" + "5" * 64},
            "timeouts": timeouts or {"startup_seconds": 2, "request_seconds": 2, "long_prefix_seconds": 2},
            "workflow": "model_adaptation",
        }
        spec["digest"] = canonical_digest(spec)
        spec_path = root / "run-spec.json"
        spec_path.write_text(json.dumps(spec))
        spec_validation = subprocess.run(
            [sys.executable, str(VALIDATOR), "--skills-root", str(ROOT), "--knowledge-root", "/work/chipltech-knowledge-base", "--vllm-dlc-root", "/work/vllm-dlc", "contract", str(spec_path)],
            capture_output=True, text=True,
        )
        self.assertEqual(spec_validation.returncode, 0, spec_validation.stderr)
        result = subprocess.run(
            [sys.executable, str(RUNNER), "--run-spec", str(spec_path), "--endpoint", f"http://127.0.0.1:{port}", "--vllm-dlc-root", "/work/vllm-dlc"],
            capture_output=True, text=True, timeout=15,
        )
        reference = json.loads(result.stdout)
        evidence = json.loads(Path(reference["uri"].removeprefix("file://")).read_text())
        validation = subprocess.run(
            [sys.executable, str(VALIDATOR), "--skills-root", str(ROOT), "--knowledge-root", "/work/chipltech-knowledge-base", "--vllm-dlc-root", "/work/vllm-dlc", "contract", reference["uri"].removeprefix("file://")],
            capture_output=True, text=True,
        )
        self.assertEqual(validation.returncode, 0, validation.stderr)
        for artifact in evidence["artifacts"]:
            artifact_path = Path(artifact["uri"].removeprefix("file://"))
            self.assertTrue(artifact_path.is_file())
            self.assertEqual(
                artifact["digest"],
                f"sha256:{hashlib.sha256(artifact_path.read_bytes()).hexdigest()}",
            )
        if server.poll() is None:
            server.terminate()
        server.wait(timeout=5)
        with socket.socket() as released_port:
            released_port.settimeout(1)
            self.assertNotEqual(released_port.connect_ex(("127.0.0.1", port)), 0)
        return result, reference, evidence

    def stop_server(self, server):
        if server.poll() is None:
            server.kill()
            server.wait(timeout=5)

    def test_success_uses_real_socket_and_seals_ineligible_evidence(self):
        result, reference, evidence = self.run_scenario({})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(reference["digest"], evidence["digest"])
        self.assertEqual(evidence["execution_environment"], "fake_server")
        self.assertFalse(evidence["acceptance_eligible"])
        self.assertEqual(
            [gate["id"] for gate in evidence["gates"]],
            ["service_ready", "models_api", "completions_api", "chat_api", "long_prefix_api", "server_liveness", "chunked_prefill", "runtime_dispatch", "real_dlc_hardware"],
        )
        self.assertEqual(
            [artifact["id"] for artifact in evidence["artifacts"]],
            ["http_transcript", "repository_snapshot"],
        )
        statuses = {gate["id"]: gate["status"] for gate in evidence["gates"]}
        self.assertTrue(all(statuses[gate] == "passed" for gate in ("service_ready", "models_api", "completions_api", "chat_api", "long_prefix_api", "server_liveness")))
        self.assertTrue(all(statuses[gate] == "not_verified" for gate in ("chunked_prefill", "runtime_dispatch", "real_dlc_hardware")))

    def test_preserves_multiple_observed_failures(self):
        result, _, evidence = self.run_scenario(
            {
                "completion": {"body": {"choices": [{"text": ""}]}},
                "chat": {
                    "body": {"choices": [{"message": {"content": ""}}]}
                },
            }
        )
        self.assertEqual(result.returncode, 20, result.stderr)
        self.assertEqual(
            [row["code"] for row in evidence["diagnostics"]].count(
                "api.empty_generated_field"
            ),
            2,
        )

    def test_api_failure_matrix(self):
        cases = [
            ({"models": {"status": 503}}, "api.non_2xx", "service_ready"),
            ({"models": {"malformed": True}}, "api.malformed_json", "service_ready"),
            ({"models": {"body": {"data": []}}}, "api.missing_model", "models_api"),
            ({"completion": {"body": {"choices": [{}]}}}, "api.empty_generated_field", "completions_api"),
            ({"completion": {"body": {"choices": [{"text": ""}]}}}, "api.empty_generated_field", "completions_api"),
            ({"chat": {"body": {"choices": [{"message": None}]}}}, "api.empty_generated_field", "chat_api"),
            ({"chat": {"body": {"choices": [{"message": {}}]}}}, "api.empty_generated_field", "chat_api"),
            ({"chat": {"body": {"choices": [{"message": {"content": ""}}]}}}, "api.empty_generated_field", "chat_api"),
            ({"completion": {"die": True}}, "process.died", "server_liveness", 21),
        ]
        cases = [case if len(case) == 4 else (*case, 20) for case in cases]
        for scenario, code, failed_gate, exit_code in cases:
            with self.subTest(code=code, scenario=scenario):
                result, _, evidence = self.run_scenario(scenario)
                self.assertEqual(result.returncode, exit_code, result.stderr)
                self.assertIn(code, [row["code"] for row in evidence["diagnostics"]])
                statuses = {row["id"]: row["status"] for row in evidence["gates"]}
                self.assertEqual(statuses[failed_gate], "failed")

    def test_timeout_classes_are_distinct(self):
        cases = [
            ({"models": {"delay": 2}}, {"startup_seconds": 1, "request_seconds": 1, "long_prefix_seconds": 1}, 30, "timeout.startup"),
            ({"completion": {"delay": 2}}, {"startup_seconds": 2, "request_seconds": 1, "long_prefix_seconds": 1}, 31, "timeout.request"),
            ({"long_prefix": {"delay": 2}}, {"startup_seconds": 2, "request_seconds": 1, "long_prefix_seconds": 1}, 32, "timeout.long_prefix"),
        ]
        for scenario, timeouts, exit_code, diagnostic in cases:
            with self.subTest(diagnostic=diagnostic):
                result, _, evidence = self.run_scenario(scenario, timeouts)
                self.assertEqual(result.returncode, exit_code, result.stderr)
                self.assertIn(diagnostic, [row["code"] for row in evidence["diagnostics"]])

class SmiObserverCliTests(unittest.TestCase):
    def test_device_pids_excludes_holder_released_between_lsof_samples(self):
        observer = load_smi_observer()
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            device_root = Path(directory)
            (device_root / "cltech0").touch()
            fake_lsof = mock.Mock(side_effect=[
                FakeLsofProcess("4100\n4200\n"),
                FakeLsofProcess("4200\n"),
            ])

            with mock.patch.object(observer.subprocess, "Popen", fake_lsof):
                self.assertEqual(observer.device_pids(0, device_root), [4200])

            self.assertEqual(fake_lsof.call_count, 2)

    def test_device_pids_fails_closed_when_second_lsof_sample_fails(self):
        observer = load_smi_observer()
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            device_root = Path(directory)
            (device_root / "cltech0").touch()
            fake_lsof = mock.Mock(side_effect=[
                FakeLsofProcess("4200\n"),
                FakeLsofProcess("", returncode=2),
            ])

            with mock.patch.object(observer.subprocess, "Popen", fake_lsof):
                with self.assertRaises(RuntimeError):
                    observer.device_pids(0, device_root)

    def test_public_adapter_keeps_stable_holder_and_vendor_pid_cross_check(self):
        observer = load_smi_observer()
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            root = Path(directory)
            device_root = root / "devices"
            device_root.mkdir()
            (device_root / "cltech0").touch()
            smi = root / "cltech_smi"
            smi.touch()
            vendor_pid = [4200]

            def fake_run(command, **kwargs):
                if command == ["/usr/bin/ps", "-eo", "pid=,pgid="]:
                    return subprocess.CompletedProcess(command, 0, "4200 4300\n", "")
                outputs = {
                    ("--list-tpus",): "TPU 0: AI accelerator controller\n",
                    ("--list-excluded-tpus",): "",
                    ("--query-dlc=memory.total", "--format=csv,nounits"): "TPU[0] 63360\n",
                    (): f"[ Process Information ]\n| 0 {vendor_pid[0]} runner\n",
                }
                return subprocess.CompletedProcess(command, 0, outputs[tuple(command[1:])], "")

            arguments = [
                str(SMI_OBSERVER),
                "--sample-point", "after_ready",
                "--server-pid", "4200",
                "--process-group", "4300",
                "--device-count", "1",
                "--run-id", "fixture-run",
                "--device-root", str(device_root),
                "--smi-executable", str(smi),
            ]
            fake_lsof = mock.Mock(side_effect=[
                FakeLsofProcess("4100\n4200\n"),
                FakeLsofProcess("4200\n"),
            ])
            output = io.StringIO()
            with (
                mock.patch.object(observer.subprocess, "run", side_effect=fake_run),
                mock.patch.object(observer.subprocess, "Popen", fake_lsof),
                mock.patch.object(observer.os, "getpgrp", return_value=4400),
                mock.patch.object(sys, "argv", arguments),
                mock.patch("sys.stdout", output),
            ):
                self.assertEqual(observer.main(), 0)

            device = json.loads(output.getvalue())["devices"][0]
            self.assertEqual(device["observed_pids"], [4200])
            self.assertEqual(device["process_pids"], [4200])

            vendor_pid[0] = 4100
            with (
                mock.patch.object(observer.subprocess, "run", side_effect=fake_run),
                mock.patch.object(observer.subprocess, "Popen", side_effect=[
                    FakeLsofProcess("4200\n"),
                    FakeLsofProcess("4200\n"),
                ]),
                mock.patch.object(observer.os, "getpgrp", return_value=4400),
                mock.patch.object(sys, "argv", arguments),
            ):
                self.assertEqual(observer.main(), 20)

    def run_observer_with_capacity(self, capacity_output):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            smi = Path(directory) / "cltech_smi"
            (Path(directory) / "devices").mkdir()
            (Path(directory) / "devices" / "cltech0").touch()
            smi.write_text(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "if sys.argv[1:] == ['--list-tpus']:\n"
                "    print('TPU 0: AI accelerator controller')\n"
                "elif sys.argv[1:] == ['--list-excluded-tpus']:\n"
                "    pass\n"
                "elif sys.argv[1:] == ['--query-dlc=memory.total', '--format=csv,nounits']:\n"
                f"    print({capacity_output!r})\n"
                "elif sys.argv[1:] == []:\n"
                "    print('[ Process Information ]')\n"
                "else:\n"
                "    raise SystemExit(2)\n"
            )
            smi.chmod(0o755)
            return subprocess.run(
                [
                    sys.executable, str(SMI_OBSERVER),
                    "--sample-point", "before_launch",
                    "--server-pid", "1",
                    "--process-group", "0",
                    "--device-count", "1",
                    "--run-id", "fixture-run",
                    "--device-root", str(Path(directory) / "devices"),
                    "--smi-executable", str(smi),
                ],
                capture_output=True,
                text=True,
            )

    def test_official_tool_queries_devices_exclusions_and_hbm_capacity(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            root = Path(directory)
            invocation_log = root / "invocations.jsonl"
            smi = root / "cltech_smi"
            devices = root / "devices"
            devices.mkdir()
            (devices / "cltech0").touch()
            (devices / "cltech1").touch()
            smi.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "with open(os.environ['SMI_INVOCATION_LOG'], 'a') as stream:\n"
                "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
                "if sys.argv[1:] == ['--list-tpus']:\n"
                "    print('TPU 0: AI accelerator controller')\n"
                "    print('TPU 1: AI accelerator controller')\n"
                "elif sys.argv[1:] == ['--list-excluded-tpus']:\n"
                "    pass\n"
                "elif sys.argv[1:] == ['--query-dlc=memory.total', '--format=csv,nounits']:\n"
                "    print('TPU[0] 63360')\n"
                "    print('TPU[1] 63360')\n"
                "elif sys.argv[1:] == []:\n"
                "    print('[ Process Information ]')\n"
                "else:\n"
                "    raise SystemExit(2)\n"
            )
            smi.chmod(0o755)
            environment = os.environ.copy()
            environment["SMI_INVOCATION_LOG"] = str(invocation_log)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SMI_OBSERVER),
                    "--sample-point", "before_launch",
                    "--server-pid", "1",
                    "--process-group", "0",
                    "--device-count", "2",
                    "--run-id", "fixture-run",
                    "--device-root", str(devices),
                    "--smi-executable", str(smi),
                ],
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                [json.loads(line) for line in invocation_log.read_text().splitlines()],
                [
                    ["--list-tpus"],
                    ["--list-excluded-tpus"],
                    ["--query-dlc=memory.total", "--format=csv,nounits"],
                    [],
                ],
            )
            self.assertEqual(len(json.loads(completed.stdout)["devices"]), 2)

    def test_official_tool_rejects_non_finite_or_unindexed_capacity(self):
        for output in ("TPU[0] nan", "63360"):
            with self.subTest(output=output):
                self.assertEqual(self.run_observer_with_capacity(output).returncode, 20)

    def test_environment_preflight_closes_mount_tool_and_query_readiness(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            root = Path(directory)
            proc = root / "proc"
            proc.mkdir()
            (proc / "status").write_text(
                "CapEff:\t000001ffffffffff\nCapBnd:\t000001ffffffffff\n"
            )
            (proc / "cap_last_cap").write_text("40\n")
            (proc / "pid1-comm").write_text("systemd\n")
            (proc / "pid1-cgroup").write_text("0::/init.scope\n")
            mount_targets = [
                "/usr/share/misc/pci.ids", "/dev", "/sys", "/run",
                "/lib/modules", "/var/log",
            ]
            mount_shapes = {
                "/usr/share/misc/pci.ids": ("/usr/share/misc/pci.ids", "ext4"),
                "/dev": ("/", "devtmpfs"),
                "/sys": ("/", "sysfs"),
                "/run": ("/", "tmpfs"),
                str(Path("/lib/modules").resolve()): (str(Path("/lib/modules").resolve()), "ext4"),
                "/var/log": ("/var/log", "ext4"),
            }
            mount_targets = list(mount_shapes)
            (proc / "mountinfo").write_text("".join(
                f"{100 + index} 1 0:1 {mount_shapes[target][0]} {target} rw - "
                f"{mount_shapes[target][1]} /dev/root rw\n"
                for index, target in enumerate(mount_targets)
            ))
            source = root / "chipltech_smi_lib"
            source.mkdir()
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            subprocess.run(
                ["git", "-C", str(source), "remote", "add", "origin", str(source)],
                check=True,
            )
            (source / "README.md").write_text("fixture")
            subprocess.run(
                ["git", "-C", str(source), "add", "README.md"], check=True
            )
            environment = os.environ.copy()
            environment.update({
                "GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example.com",
                "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example.com",
            })
            subprocess.run(
                ["git", "-C", str(source), "commit", "-q", "-m", "fixture"],
                check=True,
                env=environment,
            )
            smi = root / "cltech_smi"
            devices = root / "devices"
            devices.mkdir()
            (devices / "cltech0").touch()
            smi.write_text(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "if sys.argv[1:] == ['--list-tpus']:\n"
                "    print('TPU 0: AI accelerator controller')\n"
                "elif sys.argv[1:] == ['--list-excluded-tpus']:\n"
                "    pass\n"
                "elif sys.argv[1:] == ['--query-dlc=memory.total', '--format=csv,nounits']:\n"
                "    print('TPU[0] 63360')\n"
                "elif sys.argv[1:] == []:\n"
                "    print('[ Process Information ]')\n"
                "else:\n"
                "    raise SystemExit(2)\n"
            )
            smi.chmod(0o755)
            (source / "build").mkdir()
            (source / "build" / "cltech_smi").write_bytes(smi.read_bytes())
            (source / "build" / "cltech_smi").chmod(0o755)
            subprocess.run(
                ["git", "-C", str(source), "add", "build/cltech_smi"], check=True
            )
            subprocess.run(
                ["git", "-C", str(source), "commit", "-q", "-m", "build"],
                check=True,
                env=environment,
            )
            subprocess.run(
                ["git", "-C", str(source), "update-ref", "refs/remotes/origin/test",
                 subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(source), "symbolic-ref", "refs/remotes/origin/HEAD",
                 "refs/remotes/origin/test"], check=True,
            )
            pid_namespace = os.readlink("/proc/self/ns/pid")
            mount_namespace = os.readlink("/proc/self/ns/mnt")
            completed = subprocess.run(
                [
                    sys.executable, str(SMI_PREFLIGHT),
                    "--smi-executable", str(smi),
                    "--smi-source-root", str(source),
                    "--expected-origin", str(source),
                    "--device-count", "1",
                    "--expected-pid-namespace", pid_namespace,
                    "--expected-mount-namespace", mount_namespace,
                    "--mountinfo-path", str(proc / "mountinfo"),
                    "--status-path", str(proc / "status"),
                    "--pid1-comm-path", str(proc / "pid1-comm"),
                    "--pid1-cgroup-path", str(proc / "pid1-cgroup"),
                    "--device-root", str(devices),
                    "--cap-last-cap-path", str(proc / "cap_last_cap"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads(completed.stdout)
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["model_started"], False)
            self.assertRegex(report["smi_source_sha"], r"^[0-9a-f]{40}$")
            self.assertRegex(report["smi_executable_digest"], r"^sha256:[0-9a-f]{64}$")

    def test_environment_preflight_blocks_current_incomplete_container(self):
        completed = subprocess.run(
            [
                sys.executable, str(SMI_PREFLIGHT),
                "--smi-executable",
                "/mnt/jfs/software/patch/dlc_base/20260713/chipltech/chipltech_smi_lib/cltech_smi",
                "--smi-source-root", "/work/chipltech_smi_lib",
                "--device-count", "1",
                "--expected-pid-namespace", os.readlink("/proc/self/ns/pid"),
                "--expected-mount-namespace", os.readlink("/proc/self/ns/mnt"),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 20)
        report = json.loads(completed.stdout)
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["model_started"], False)
        self.assertTrue(any(
            reason.startswith("environment.missing_host_mount:")
            or reason.startswith("environment.non_host_mount:")
            or reason == "smi.executable_source_binding_failed"
            for reason in report["reasons"]
        ))


if __name__ == "__main__":
    unittest.main()
