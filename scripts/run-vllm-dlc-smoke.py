#!/usr/bin/env python3
"""Run the shared vLLM-DLC HTTP smoke seam and seal simulated evidence."""

import argparse
import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from concurrent.futures import ThreadPoolExecutor


VALIDATOR_PATH = Path(__file__).with_name("validate-vllm-dlc-contracts.py")
TOKENIZER_BUILDER_PATH = Path(__file__).with_name("build-vllm-dlc-long-prefix.py")
VALIDATOR_SPEC = importlib.util.spec_from_file_location("vllm_dlc_contract", VALIDATOR_PATH)
if VALIDATOR_SPEC is None or VALIDATOR_SPEC.loader is None:
    raise RuntimeError("cannot load the shared vLLM-DLC contract")
CONTRACT = importlib.util.module_from_spec(VALIDATOR_SPEC)
VALIDATOR_SPEC.loader.exec_module(CONTRACT)

RESULT_SCHEMA = "vllm-dlc-result-evidence/v1"
REFERENCE_SCHEMA = "vllm-dlc-result-reference/v1"
API_GATES = (
    "service_ready",
    "models_api",
    "completions_api",
    "chat_api",
    "long_prefix_api",
    "server_liveness",
)
SIMULATED_GATES = ("chunked_prefill", "runtime_dispatch", "real_dlc_hardware")
V2_RESULT_SCHEMA = "vllm-dlc-result-evidence/v2"
CAMPAIGN_REQUIRED_IDS = CONTRACT.OPERATIONAL_CAMPAIGN_REQUIRED_IDS


class SmokeFailure(Exception):
    def __init__(self, code: str, message: str, *, timeout_class: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.timeout_class = timeout_class


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def digest(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_bytes(value)
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def asset_digest(path: Path) -> str:
    if path.is_symlink() or not path.exists():
        raise SmokeFailure("asset.invalid", f"asset is missing or symlinked: {path}")
    if path.is_dir() and any(candidate.is_symlink() for candidate in path.rglob("*")):
        raise SmokeFailure("asset.invalid", f"asset contains a symlink: {path}")
    accumulator = hashlib.sha256()
    files = [path] if path.is_file() else sorted(
        (candidate for candidate in path.rglob("*") if candidate.is_file()),
        key=lambda candidate: candidate.relative_to(path).as_posix(),
    )
    if not files:
        raise SmokeFailure("asset.invalid", f"asset has no regular files: {path}")
    for candidate in files:
        if candidate.is_symlink() or not candidate.is_file():
            raise SmokeFailure("asset.invalid", f"asset contains an invalid file: {candidate}")
        relative = candidate.name if path.is_file() else candidate.relative_to(path).as_posix()
        accumulator.update(relative.encode("utf-8"))
        accumulator.update(b"\0")
        with candidate.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                accumulator.update(chunk)
        accumulator.update(b"\0")
    return f"sha256:{accumulator.hexdigest()}"


def atomic_write(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("xb") as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)


def v2_exit_code(diagnostics: list[dict[str, Any]], repository_changed: bool) -> int:
    if repository_changed:
        return 50
    codes = {row["code"] for row in diagnostics}
    precedence = (
        ("cleanup.", 41),
        ("internal.", 42),
        ("artifact.", 40),
        ("asset.", 23),
        ("hardware.insufficient", 24),
        ("process.launch_failed", 22),
        ("process.died", 21),
        ("timeout.startup", 30),
        ("timeout.request", 31),
        ("timeout.long_prefix", 32),
        ("smi.", 34),
        ("hardware.", 27),
        ("api.", 25),
        ("tokenizer.", 26),
        ("request.", 26),
    )
    for prefix, exit_code in precedence:
        if any(code == prefix or code.startswith(prefix) for code in codes):
            return exit_code
    return 20 if codes else 0


def request_json(
    endpoint: str,
    path: str,
    timeout: int,
    transcript: list[dict[str, Any]],
    body: dict[str, Any] | None = None,
    timeout_class: str = "request",
) -> dict[str, Any]:
    method = "POST" if body is not None else "GET"
    request = urllib.request.Request(
        f"{endpoint.rstrip('/')}{path}",
        data=canonical_bytes(body) if body is not None else None,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_body = response.read()
            status = response.status
    except urllib.error.HTTPError as error:
        response_body = error.read()
        transcript.append({"method": method, "path": path, "status": error.code})
        raise SmokeFailure("api.non_2xx", f"{path} returned HTTP {error.code}") from error
    except (TimeoutError, socket.timeout) as error:
        raise SmokeFailure(
            f"timeout.{timeout_class}",
            f"{path} exceeded the {timeout_class} timeout",
            timeout_class=timeout_class,
        ) from error
    except (urllib.error.URLError, ConnectionError, OSError) as error:
        raise SmokeFailure("process.unreachable", f"{path} is unreachable") from error
    transcript.append({"method": method, "path": path, "status": status})
    if not 200 <= status < 300:
        raise SmokeFailure("api.non_2xx", f"{path} returned HTTP {status}")
    try:
        value = json.loads(response_body)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise SmokeFailure("api.malformed_json", f"{path} returned malformed JSON") from error
    if not isinstance(value, dict):
        raise SmokeFailure("api.invalid_json", f"{path} returned a non-object JSON value")
    return value


def liveness(endpoint: str, timeout: int) -> bool:
    try:
        request = urllib.request.Request(f"{endpoint.rstrip('/')}/health", method="GET")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def gate_row(gate_id: str, mandatory: bool, status: str, evidence: Any) -> dict[str, Any]:
    return {
        "id": gate_id,
        "mandatory": mandatory,
        "status": status,
        "evidence_digest": digest(evidence),
    }


def run_v2_smi(
    configuration: dict[str, Any], sample_point: str, server_pid: int, run_id: str
) -> dict[str, Any]:
    executable = Path(configuration["executable"])
    command = [str(executable)]
    if executable.suffix == ".py":
        command.insert(0, sys.executable)
    command.extend(
        [
            "--sample-point",
            sample_point,
            "--server-pid",
            str(server_pid),
            "--process-group",
            str(server_pid),
            "--device-count",
            str(configuration["required_device_count"]),
            "--run-id",
            run_id,
        ]
    )
    if configuration["tool_executable"] is not None:
        command.extend(["--smi-executable", configuration["tool_executable"]])
    try:
        process = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
            env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
            start_new_session=True,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SmokeFailure(
            "smi.query_failed", f"SMI sample {sample_point} failed"
        ) from error
    if process.returncode != 0:
        raise SmokeFailure(
            "smi.query_failed",
            f"SMI sample {sample_point} failed with exit {process.returncode}",
        )
    try:
        observation = json.loads(process.stdout)
    except json.JSONDecodeError as error:
        raise SmokeFailure("smi.invalid_json", "SMI adapter returned invalid JSON") from error
    if not isinstance(observation, dict) or set(observation) != {
        "adapter_schema",
        "devices",
        "sample_point",
    }:
        raise SmokeFailure("smi.invalid_schema", "SMI adapter returned an unknown field")
    if (
        observation["adapter_schema"] != "vllm-dlc-smi-observation/v1"
        or observation["sample_point"] != sample_point
        or not isinstance(observation["devices"], list)
    ):
        raise SmokeFailure("smi.invalid_schema", "SMI adapter identity mismatch")
    for device in observation["devices"]:
        if not isinstance(device, dict) or set(device) != {
            "device_key",
            "health",
            "memory_total_mib",
            "observed_pids",
            "process_pids",
        }:
            raise SmokeFailure("smi.invalid_schema", "SMI device row is invalid")
        if (
            not isinstance(device["device_key"], str)
            or not device["device_key"]
            or device["health"] != "queryable_not_excluded"
            or type(device["memory_total_mib"]) not in {int, float}
            or device["memory_total_mib"] <= 0
            or not isinstance(device["observed_pids"], list)
            or any(type(pid) is not int or pid <= 0 for pid in device["observed_pids"])
            or not isinstance(device["process_pids"], list)
            or any(type(pid) is not int or pid <= 0 for pid in device["process_pids"])
            or not set(device["process_pids"]).issubset(device["observed_pids"])
        ):
            raise SmokeFailure("smi.invalid_schema", "SMI device value is invalid")
    if len({device["device_key"] for device in observation["devices"]}) != len(
        observation["devices"]
    ):
        raise SmokeFailure("smi.invalid_schema", "SMI device identities are duplicated")
    if len(observation["devices"]) < configuration["required_device_count"]:
        raise SmokeFailure(
            "hardware.insufficient",
            "queryable non-excluded device count is smaller than required",
        )
    return observation


def process_group_members(process_group: int) -> set[int]:
    try:
        process = subprocess.run(
            ["/usr/bin/ps", "-eo", "pid=,pgid="],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise SmokeFailure(
            "cleanup.query_failed", "runner process group could not be inspected"
        ) from error
    members = set()
    for line in process.stdout.splitlines():
        fields = line.split()
        if len(fields) == 2 and all(field.isdigit() for field in fields):
            pid, pgid = map(int, fields)
            if pgid == process_group:
                members.add(pid)
    return members


def observed_pids(observation: dict[str, Any]) -> set[int]:
    return {
        pid for device in observation["devices"] for pid in device["observed_pids"]
    }


def validate_campaign_manifest(path: Path, run_spec: dict[str, Any]) -> bool:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(document, dict) or set(document) != {
        "entries", "schema_version"
    } or document["schema_version"] != "vllm-dlc-execution-campaign/v1":
        return False
    entries = document["entries"]
    if not isinstance(entries, list) or any(
        not isinstance(entry, dict)
        or set(entry) != {"digest", "id", "kind", "path"}
        or entry["kind"] not in {"file", "git_repository"}
        or not isinstance(entry["id"], str)
        or not isinstance(entry["path"], str)
        or not Path(entry["path"]).is_absolute()
        or not isinstance(entry["digest"], str)
        for entry in entries
    ):
        return False
    by_id = {entry["id"]: entry for entry in entries}
    required_ids = set(CAMPAIGN_REQUIRED_IDS)
    if run_spec["deployment_profile"]["role"] == "model_adaptation_profile_operational":
        required_ids.update({
            "model_adaptation_approval", "model_adaptation_tp_derivation"
        })
    if len(by_id) != len(entries) or not required_ids.issubset(by_id):
        return False
    expected_repositories = {
        "vllm_source": run_spec["target"]["vllm_sha"],
        "vllm_dlc_source": run_spec["target"]["vllm_dlc_sha"],
        "smi_source": run_spec["hardware_observation"]["smi_source_sha"],
    }
    expected_files = {
        "python": Path(sys.executable).resolve(),
        "runner": Path(__file__).resolve(),
        "validator": VALIDATOR_PATH.resolve(),
        "launcher": Path(run_spec["launch"]["arguments"][0]).resolve(),
        "tokenizer_builder": TOKENIZER_BUILDER_PATH.resolve(),
        "smi_adapter": Path(run_spec["hardware_observation"]["executable"]).resolve(),
        "smi_preflight": Path(run_spec["hardware_observation"]["qualification_executable"]).resolve(),
        "smi_tool": Path(run_spec["hardware_observation"]["tool_executable"]).resolve(),
        "dependency_qualifier": CONTRACT.DEPENDENCY_QUALIFIER_PATH,
        "dependency_requirements": CONTRACT.DEPENDENCY_REQUIREMENTS_PATH,
        "dependency_exception_policy": CONTRACT.DEPENDENCY_EXCEPTION_POLICY_PATH,
        "main_to_main_operational_policy": CONTRACT.MAIN_TO_MAIN_OPERATIONAL_POLICY_PATH,
        "vllm_native": Path(importlib.util.find_spec("vllm._C").origin).resolve(),
        "vllm_dlc_native": Path(importlib.util.find_spec("vllm_dlc.vllm_dlc_C").origin).resolve(),
        "model_hosting_container_standards": Path(
            importlib.util.find_spec("model_hosting_container_standards").origin
        ).resolve(),
        "ijson": Path(importlib.util.find_spec("ijson").origin).resolve(),
    }
    if run_spec["deployment_profile"]["role"] == "model_adaptation_profile_operational":
        expected_files.update({
            "model_adaptation_approval": Path(run_spec["deployment_profile"]["approval_path"]).resolve(),
            "model_adaptation_tp_derivation": Path(run_spec["deployment_profile"]["tp_derivation_path"]).resolve(),
        })
        if (
            by_id["model_adaptation_approval"]["digest"]
            != run_spec["deployment_profile"]["approval_digest"]
            or by_id["model_adaptation_tp_derivation"]["digest"]
            != run_spec["deployment_profile"]["tp_derivation_digest"]
        ):
            return False
    expected_roots = {
        "vllm_source": Path(run_spec["repository_guards"][0]).resolve(),
        "vllm_dlc_source": Path(run_spec["repository_guards"][1]).resolve(),
        "smi_source": Path(run_spec["hardware_observation"]["smi_source_root"]).resolve(),
    }
    if any(
        Path(by_id[entry_id]["path"]).resolve() != expected_path
        for entry_id, expected_path in {**expected_files, **expected_roots}.items()
    ):
        return False
    if (
        by_id["main_to_main_operational_policy"]["path"]
        != str(CONTRACT.MAIN_TO_MAIN_OPERATIONAL_POLICY_PATH)
    ):
        return False
    try:
        operational_policy = json.loads(
            Path(by_id["main_to_main_operational_policy"]["path"]).read_bytes()
        )
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if (
        not CONTRACT.validate_main_to_main_operational_policy(operational_policy)
        or operational_policy["target"] != run_spec["target"]
    ):
        return False
    try:
        environment_profile = json.loads(
            Path(by_id["environment_profile"]["path"]).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return False
    if environment_profile != {
        "expected_mount_namespace": run_spec["hardware_observation"]["expected_mount_namespace"],
        "expected_pid_namespace": run_spec["hardware_observation"]["expected_pid_namespace"],
        "schema_version": "vllm-dlc-environment-profile/v1",
    }:
        return False
    if not CONTRACT.validate_dependency_qualification(
        Path(by_id["dependency_qualification"]["path"]),
        run_spec["repository_guards"],
    ):
        return False
    for entry_id, root in (
        ("vllm_snapshot", Path(run_spec["repository_guards"][0])),
        ("vllm_dlc_snapshot", Path(run_spec["repository_guards"][1])),
    ):
        try:
            recorded = json.loads(Path(by_id[entry_id]["path"]).read_text())
        except (OSError, json.JSONDecodeError):
            return False
        if recorded != CONTRACT.repository_snapshot(root):
            return False
    for entry in entries:
        candidate = Path(entry["path"])
        if entry["kind"] == "file":
            try:
                if digest(candidate.read_bytes()) != entry["digest"]:
                    return False
            except OSError:
                return False
        else:
            expected = expected_repositories.get(entry["id"])
            if expected is None or entry["digest"] != expected:
                return False
            revision = subprocess.run(
                ["/usr/bin/git", "-C", str(candidate), "rev-parse", "HEAD^{commit}"],
                check=False,
                capture_output=True,
                text=True,
            )
            if revision.returncode != 0 or revision.stdout.strip() != expected:
                return False
            if entry["id"] == "smi_source":
                status = subprocess.run(
                    ["/usr/bin/git", "-C", str(candidate), "status", "--porcelain=v1"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if status.returncode != 0 or status.stdout.strip():
                    return False
    return True


def build_v2_long_prefix(run_spec: dict[str, Any], output_allowance: int) -> dict[str, Any]:
    profile = run_spec["deployment_profile"]
    command = [
        sys.executable,
        str(TOKENIZER_BUILDER_PATH),
        "--tokenizer-path",
        run_spec["assets"]["tokenizer_path"],
        "--threshold",
        str(profile["max_num_batched_tokens"]),
        "--context-limit",
        str(profile["context_limit"]),
        "--output-allowance",
        str(output_allowance),
    ]
    if run_spec["mode"] == "diagnostic_only":
        command.append("--fixture")
    process = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if process.returncode != 0:
        raise SmokeFailure("tokenizer.proof_failed", "long-prefix tokenizer proof failed")
    try:
        proof = json.loads(process.stdout)
    except json.JSONDecodeError as error:
        raise SmokeFailure("tokenizer.proof_failed", "tokenizer proof is invalid") from error
    expected = {
        "context_limit", "output_allowance", "prompt", "prompt_digest",
        "prompt_token_count", "schema_version", "threshold", "token_ids_digest",
    }
    if not isinstance(proof, dict) or set(proof) != expected or (
        proof["schema_version"] != "vllm-dlc-long-prefix-proof/v1"
        or proof["threshold"] != profile["max_num_batched_tokens"]
        or proof["context_limit"] != profile["context_limit"]
        or proof["output_allowance"] != output_allowance
        or proof["prompt_token_count"] <= proof["threshold"]
        or proof["prompt_token_count"] + output_allowance > proof["context_limit"]
        or digest(proof["prompt"].encode("utf-8")) != proof["prompt_digest"]
    ):
        raise SmokeFailure("tokenizer.proof_failed", "tokenizer proof does not close")
    return proof


def run_v2(
    run_spec: dict[str, Any], vllm_dlc_root: Path, before: dict[str, str]
) -> int:
    guards = run_spec["repository_guards"]
    if Path(guards[1]).resolve() != vllm_dlc_root.resolve():
        return CONTRACT.invalid_input_report(
            ValueError("v2 guarded vllm-dlc root mismatch"), vllm_dlc_root, before
        )
    before_guards = {
        root: before if Path(root).resolve() == vllm_dlc_root.resolve()
        else CONTRACT.repository_snapshot(Path(root))
        for root in guards
    }
    target_bindings = {
        guards[0]: run_spec["target"]["vllm_sha"],
        guards[1]: run_spec["target"]["vllm_dlc_sha"],
    }
    if any(before_guards[root]["head"] != expected for root, expected in target_bindings.items()):
        return CONTRACT.invalid_input_report(
            ValueError("v2 target repository identity mismatch"), vllm_dlc_root, before
        )
    if run_spec["mode"] == "operational_regression":
        campaign_manifest = Path(run_spec["campaign_manifest"])
        qualification = Path(
            run_spec["hardware_observation"]["qualification_executable"]
        )
        if (
            digest(campaign_manifest.read_bytes()) != run_spec["campaign_digest"]
            or digest(qualification.read_bytes())
            != run_spec["hardware_observation"]["qualification_executable_digest"]
            or not validate_campaign_manifest(campaign_manifest, run_spec)
        ):
            return CONTRACT.invalid_input_report(
                ValueError("campaign or SMI qualification identity mismatch"),
                vllm_dlc_root,
                before,
            )
        hardware = run_spec["hardware_observation"]
        preflight = subprocess.run(
            [
                sys.executable, str(qualification),
                "--smi-executable", hardware["tool_executable"],
                "--smi-source-root", hardware["smi_source_root"],
                "--device-count", str(hardware["required_device_count"]),
                "--expected-pid-namespace", hardware["expected_pid_namespace"],
                "--expected-mount-namespace", hardware["expected_mount_namespace"],
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            env={"PATH": "/usr/bin:/bin", "HOME": "/root"},
        )
        try:
            preflight_report = json.loads(preflight.stdout)
        except json.JSONDecodeError:
            preflight_report = {}
        if (
            preflight.returncode != 0
            or preflight_report.get("status") != "passed"
            or preflight_report.get("model_started") is not False
            or preflight_report.get("smi_source_sha") != hardware["smi_source_sha"]
            or preflight_report.get("smi_executable_digest") != hardware["tool_digest"]
        ):
            return CONTRACT.invalid_input_report(
                ValueError("SMI environment qualification failed"),
                vllm_dlc_root,
                before,
            )
    destination = Path(run_spec["artifact_destination"])
    if destination.exists():
        return CONTRACT.invalid_input_report(
            ValueError("v2 artifact destination must not exist"), vllm_dlc_root, before
        )
    try:
        destination.mkdir(parents=True, mode=0o700)
    except OSError as error:
        print(json.dumps({"code": "artifact.unavailable", "status": "failed"}, sort_keys=True))
        print(f"artifact.unavailable: {error}", file=sys.stderr)
        return 40

    launch = run_spec["launch"]
    executable = Path(launch["executable"])
    if digest(executable.read_bytes()) != launch["executable_digest"]:
        return CONTRACT.invalid_input_report(
            ValueError("launcher executable digest mismatch"), vllm_dlc_root, before
        )
    smi_executable = Path(run_spec["hardware_observation"]["executable"])
    if digest(smi_executable.read_bytes()) != run_spec["hardware_observation"]["executable_digest"]:
        return CONTRACT.invalid_input_report(
            ValueError("SMI executable digest mismatch"), vllm_dlc_root, before
        )
    tool_executable = run_spec["hardware_observation"]["tool_executable"]
    if tool_executable is not None and digest(Path(tool_executable).read_bytes()) != run_spec["hardware_observation"]["tool_digest"]:
        return CONTRACT.invalid_input_report(
            ValueError("SMI tool digest mismatch"), vllm_dlc_root, before
        )
    for name in ("model", "tokenizer", "processor"):
        path_value = run_spec["assets"][f"{name}_path"]
        expected = run_spec["assets"][f"{name}_digest"]
        if path_value is None:
            continue
        try:
            actual = asset_digest(Path(path_value))
        except (OSError, SmokeFailure) as error:
            return CONTRACT.invalid_input_report(error, vllm_dlc_root, before)
        if actual != expected:
            return CONTRACT.invalid_input_report(
                ValueError(f"{name} asset digest mismatch"), vllm_dlc_root, before
            )
    if run_spec["mode"] == "operational_regression" and any(
        run_spec["assets"][field] not in launch["arguments"]
        for field in ("model_path", "tokenizer_path")
    ):
        return CONTRACT.invalid_input_report(
            ValueError("launcher does not bind approved asset paths"),
            vllm_dlc_root,
            before,
        )
    arguments = launch["arguments"]
    log_stdout_path = destination / "server-stdout.log"
    log_stderr_path = destination / "server-stderr.log"
    try:
        ready_index = arguments.index("--ready-file") + 1
        ready_file = Path(arguments[ready_index])
    except (ValueError, IndexError):
        return CONTRACT.invalid_input_report(
            ValueError("v2 launcher requires typed ready-file handoff"),
            vllm_dlc_root,
            before,
        )
    if (
        not ready_file.is_absolute()
        or destination.parent.resolve() not in ready_file.resolve().parents
        or ready_file.exists()
        or ready_file.is_symlink()
    ):
        return CONTRACT.invalid_input_report(
            ValueError("v2 ready-file must be absent beneath the run parent"),
            vllm_dlc_root,
            before,
        )

    transcript: list[dict[str, Any]] = []
    api_assertions: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    observed_pid_baseline: set[int] | None = None
    server = None
    endpoint = None
    statuses = {gate: "blocked" for gate in run_spec["gates"]}
    try:
        observations.append(
            run_v2_smi(run_spec["hardware_observation"], "before_launch", 0, run_spec["run_id"])
        )
        observed_pid_baseline = observed_pids(observations[-1])
        environment = {
            "PATH": "/usr/bin:/bin",
            "PYTHONDONTWRITEBYTECODE": "1",
            **launch["environment"],
        }
        stdout_log = log_stdout_path.open("xb")
        stderr_log = log_stderr_path.open("xb")
        try:
            server = subprocess.Popen(
                [str(executable), *arguments],
                cwd=launch["working_directory"],
                env=environment,
                stdout=stdout_log,
                stderr=stderr_log,
                start_new_session=True,
            )
        finally:
            stdout_log.close()
            stderr_log.close()
        deadline = time.monotonic() + run_spec["timeouts"]["startup_seconds"]
        while time.monotonic() < deadline:
            if server.poll() is not None:
                raise SmokeFailure("process.launch_failed", "server exited before readiness")
            if ready_file.is_file():
                try:
                    port = int(ready_file.read_text(encoding="utf-8"))
                    endpoint = f"http://127.0.0.1:{port}"
                    break
                except (OSError, ValueError):
                    pass
            time.sleep(0.02)
        if endpoint is None:
            raise SmokeFailure("timeout.startup", "service readiness timed out", timeout_class="startup")

        model_name = run_spec["deployment_profile"]["served_model_name"]
        models = request_json(
            endpoint,
            "/v1/models",
            run_spec["timeouts"]["request_seconds"],
            transcript,
        )
        model_rows = models.get("data")
        if not isinstance(model_rows, list) or model_name not in [
            row.get("id") for row in model_rows if isinstance(row, dict)
        ]:
            raise SmokeFailure("api.missing_model", "expected served model is absent")
        statuses["service_ready"] = "passed"
        statuses["models_api"] = "passed"
        api_assertions.append({
            "generated_field": "not_applicable",
            "json_contract": True,
            "liveness": liveness(endpoint, min(run_spec["timeouts"]["request_seconds"], 1)),
            "role": "models",
        })
        if not api_assertions[-1]["liveness"]:
            raise SmokeFailure("process.died", "server died after models")
        observations.append(
            run_v2_smi(run_spec["hardware_observation"], "after_ready", server.pid, run_spec["run_id"])
        )

        request_by_role = {row["role"]: row for row in run_spec["requests"]}
        long_prefix_proof = build_v2_long_prefix(
            run_spec, request_by_role["long_prefix"]["output_token_allowance"]
        )
        payloads = {
            "completion": {
                "model": model_name,
                "prompt": "smoke",
                "max_tokens": 1,
            },
            "chat": {
                "model": model_name,
                "messages": [{"role": "user", "content": "smoke"}],
                "max_tokens": 1,
            },
            "long_prefix": {
                "model": model_name,
                "prompt": long_prefix_proof["prompt"],
                "max_tokens": 1,
            },
        }
        for role in ("completion", "chat", "long_prefix"):
            row = request_by_role[role]
            payload = payloads[role]
            if digest(payload) != row["payload_digest"]:
                raise SmokeFailure("request.digest_mismatch", f"{role} payload digest mismatch")
            request_arguments = (
                endpoint,
                "/v1/chat/completions" if role == "chat" else "/v1/completions",
                run_spec["timeouts"][f"{row['timeout_class']}_seconds"],
                transcript,
                payload,
                row["timeout_class"],
            )
            if role == "long_prefix":
                with ThreadPoolExecutor(max_workers=1) as executor:
                    pending_response = executor.submit(request_json, *request_arguments)
                    observations.append(
                        run_v2_smi(
                            run_spec["hardware_observation"],
                            "during_request",
                            server.pid,
                            run_spec["run_id"],
                        )
                    )
                    response = pending_response.result()
            else:
                response = request_json(*request_arguments)
            choices = response.get("choices")
            first = choices[0] if isinstance(choices, list) and choices else None
            generated = (
                first.get("message", {}).get("content")
                if role == "chat" and isinstance(first, dict)
                else first.get("text") if isinstance(first, dict) else None
            )
            if not isinstance(generated, str) or not generated.strip():
                raise SmokeFailure("api.empty_generated_field", f"{role} generated field is empty")
            statuses[{"completion": "completions_api", "chat": "chat_api", "long_prefix": "long_prefix_api"}[role]] = "passed"
            live_after = liveness(endpoint, min(run_spec["timeouts"]["request_seconds"], 1))
            api_assertions.append({
                "generated_field": True,
                "json_contract": True,
                "liveness": live_after,
                "role": role,
            })
            if not live_after:
                raise SmokeFailure("process.died", f"server died after {role}")
        statuses["server_liveness"] = "passed"
        statuses["long_prefix_threshold_exercised"] = "passed"
        statuses["eager_dlc_configuration_observed"] = "passed"

        during_observation = next(
            row for row in observations if row["sample_point"] == "during_request"
        )
        observed_processes = {
            pid
            for device in during_observation["devices"]
            for pid in device["process_pids"]
        }
        tensor_parallel_size = run_spec["deployment_profile"]["tensor_parallel_size"]
        if len(observed_processes) < tensor_parallel_size:
            raise SmokeFailure("hardware.process_shape", "observed process shape is smaller than TP")
        statuses["real_dlc_hardware_operational"] = "passed"
        statuses[run_spec["deployment_profile"]["role"]] = "passed"
    except SmokeFailure as error:
        diagnostics.append({"code": error.code, "message": error.message, "artifact_digest": None})
        for gate, status in statuses.items():
            if status == "blocked" and gate in {
                "service_ready",
                "models_api",
                "completions_api",
                "chat_api",
                "long_prefix_api",
                "server_liveness",
            }:
                statuses[gate] = "failed"
                break
    finally:
        if server is not None and (server.poll() is None or process_group_members(server.pid)):
            try:
                os.killpg(server.pid, 15)
            except ProcessLookupError:
                pass
            try:
                if server.poll() is None:
                    server.wait(timeout=5)
                deadline = time.monotonic() + 5
                while process_group_members(server.pid) and time.monotonic() < deadline:
                    time.sleep(0.05)
            except subprocess.TimeoutExpired:
                pass
            if process_group_members(server.pid):
                try:
                    os.killpg(server.pid, 9)
                except ProcessLookupError:
                    pass
                if server.poll() is None:
                    server.wait(timeout=5)
        try:
            cleanup_observation = run_v2_smi(
                run_spec["hardware_observation"],
                "after_cleanup",
                server.pid if server is not None else 0,
                run_spec["run_id"],
            )
            observations.append(cleanup_observation)
            if server is not None and process_group_members(server.pid):
                raise SmokeFailure(
                    "cleanup.process_survived", "runner process group survived cleanup"
                )
            if any(device["process_pids"] for device in cleanup_observation["devices"]):
                raise SmokeFailure("cleanup.process_survived", "device process occupancy survived cleanup")
            cleanup_observed_pids = observed_pids(cleanup_observation)
            if observed_pid_baseline is None or cleanup_observed_pids - observed_pid_baseline:
                raise SmokeFailure(
                    "cleanup.process_survived",
                    "device PID beyond pre-launch baseline survived cleanup",
                )
            statuses["lifecycle_cleanup"] = "passed"
        except SmokeFailure as error:
            diagnostics.append({"code": error.code, "message": error.message, "artifact_digest": None})
            statuses["lifecycle_cleanup"] = "failed"

    after_guards = {
        root: CONTRACT.repository_snapshot(Path(root)) for root in guards
    }
    repositories_preserved = before_guards == after_guards
    statuses["repository_state"] = "passed" if repositories_preserved else "failed"
    if not repositories_preserved:
        diagnostics.append({"code": "repository_state.changed", "message": "guarded repository changed", "artifact_digest": None})
    if run_spec["mode"] == "operational_regression":
        campaign_manifest = Path(run_spec["campaign_manifest"])
        try:
            campaign_preserved = (
                digest(campaign_manifest.read_bytes()) == run_spec["campaign_digest"]
                and validate_campaign_manifest(campaign_manifest, run_spec)
            )
        except OSError:
            campaign_preserved = False
        if not campaign_preserved:
            statuses["artifact_closure"] = "failed"
            diagnostics.append({
                "code": "campaign.changed",
                "message": "execution campaign changed during the run",
                "artifact_digest": None,
            })
    transcript_bytes = canonical_bytes(transcript)
    api_assertion_bytes = canonical_bytes(api_assertions)
    observation_bytes = canonical_bytes(observations)
    tokenizer_proof_bytes = canonical_bytes(
        long_prefix_proof if "long_prefix_proof" in locals() else {}
    )
    snapshot_bytes = canonical_bytes({"before": before_guards, "after": after_guards})
    artifact_values = (
        ("run_spec", "run_spec", "run-spec.json", canonical_bytes(run_spec)),
        ("http_transcript", "http_transcript", "http-transcript.json", transcript_bytes),
        ("api_assertions", "api_assertions", "api-assertions.json", api_assertion_bytes),
        ("smi_observations", "smi_observations", "smi-observations.json", observation_bytes),
        ("tokenizer_proof", "tokenizer_proof", "tokenizer-proof.json", tokenizer_proof_bytes),
        ("repository_snapshot", "repository_snapshot", "repository-snapshot.json", snapshot_bytes),
        ("server_stdout", "server_stdout", "server-stdout.log", log_stdout_path.read_bytes() if log_stdout_path.is_file() else b""),
        ("server_stderr", "server_stderr", "server-stderr.log", log_stderr_path.read_bytes() if log_stderr_path.is_file() else b""),
    )
    artifacts = []
    for artifact_id, kind, filename, payload in artifact_values:
        path = destination / filename
        if not path.exists():
            atomic_write(path, payload)
        artifacts.append({"id": artifact_id, "kind": kind, "uri": path.as_uri(), "digest": digest(payload)})
    if statuses["artifact_closure"] != "failed":
        statuses["artifact_closure"] = "passed"
    gate_rows = [gate_row(gate, True, statuses[gate], {"gate": gate, "status": statuses[gate]}) for gate in run_spec["gates"]]
    mandatory_statuses = {row["status"] for row in gate_rows}
    overall = next((status for status in ("failed", "blocked", "not_verified") if status in mandatory_statuses), "passed")
    fixture = launch["provider_class"] == "fixture" or run_spec["hardware_observation"]["provider_class"] == "fixture"
    completion_eligible = overall == "passed" and not fixture and run_spec["mode"] == "operational_regression"
    exit_code = v2_exit_code(diagnostics, not repositories_preserved)
    if overall != "passed" and exit_code == 0:
        exit_code = 20
    result = {
        "acceptance_eligible": False,
        "artifacts": artifacts,
        "authoritativeness": "operational_only",
        "completion_eligible": completion_eligible,
        "contract_kind": "result_evidence",
        "diagnostics": diagnostics,
        "digest": "",
        "evidence_class": "fixture_operational_validation" if fixture else "real_dlc_hardware_operational",
        "exit_code": exit_code,
        "gates": gate_rows,
        "overall_status": overall,
        "run_id": run_spec["run_id"],
        "run_spec_digest": run_spec["digest"],
        "schema_version": V2_RESULT_SCHEMA,
    }
    result["digest"] = CONTRACT.canonical_digest(result)
    result_path = destination / "result-evidence.json"
    atomic_write(result_path, canonical_bytes(result))
    reference = {"digest": result["digest"], "schema_version": "vllm-dlc-result-reference/v2", "uri": result_path.as_uri()}
    print(canonical_bytes(reference).decode("utf-8"))
    return exit_code


def main() -> int:
    bootstrapped_root = CONTRACT.bootstrap_guard_root(sys.argv[1:])
    bootstrapped_before = None
    if bootstrapped_root is not None:
        try:
            bootstrapped_before = CONTRACT.repository_snapshot(bootstrapped_root)
        except (OSError, CONTRACT.subprocess.CalledProcessError):
            pass
    parser = CONTRACT.ArgumentErrorParser(allow_abbrev=False)
    parser.add_argument("--run-spec", required=True, type=Path)
    parser.add_argument("--endpoint")
    parser.add_argument("--vllm-dlc-root", required=True, type=Path)
    try:
        arguments = parser.parse_args()
    except ValueError as error:
        return CONTRACT.invalid_input_report(
            error, bootstrapped_root, bootstrapped_before
        )
    try:
        before = (
            bootstrapped_before
            if bootstrapped_root == arguments.vllm_dlc_root
            and bootstrapped_before is not None
            else CONTRACT.repository_snapshot(arguments.vllm_dlc_root)
        )
        run_spec = json.loads(arguments.run_spec.read_text(encoding="utf-8"))
        contract_check = CONTRACT.validate_contract(run_spec, arguments.vllm_dlc_root)
        if contract_check["status"] != "passed":
            raise ValueError(contract_check["code"])
        if run_spec["schema_version"] == "vllm-dlc-run-spec/v2":
            if arguments.endpoint is not None:
                raise ValueError("--endpoint is not supported by run-spec/v2")
            return run_v2(run_spec, arguments.vllm_dlc_root, before)
        if arguments.endpoint is None:
            raise ValueError("--endpoint is required by run-spec/v1")
        endpoint = urllib.parse.urlsplit(arguments.endpoint)
        endpoint.port
        if endpoint.scheme not in {"http", "https"} or not endpoint.hostname:
            raise ValueError("endpoint must be an absolute HTTP URL")
        if endpoint.path not in {"", "/"} or endpoint.query or endpoint.fragment:
            raise ValueError("endpoint must not include a path, query, or fragment")
        if run_spec["hardware"]["class"] == "fake_server" and run_spec["mode"] != "diagnostic_only":
            raise ValueError("fake-server runs must be diagnostic_only")
        unknown_gates = set(run_spec["gates"]) - set(API_GATES) - set(SIMULATED_GATES)
        if unknown_gates:
            raise ValueError(f"unsupported gate: {sorted(unknown_gates)[0]}")
        missing_api_gates = set(API_GATES) - set(run_spec["gates"])
        if missing_api_gates:
            raise ValueError(f"missing mandatory gate: {sorted(missing_api_gates)[0]}")
        if run_spec["hardware"]["class"] == "real_dlc_hardware":
            missing_hardware_gates = set(SIMULATED_GATES) - set(run_spec["gates"])
            if missing_hardware_gates:
                raise ValueError(
                    f"missing mandatory hardware gate: {sorted(missing_hardware_gates)[0]}"
                )
    except CONTRACT.subprocess.CalledProcessError as error:
        print(json.dumps({"code": "repository_state.not_verified", "status": "failed"}, sort_keys=True))
        print(f"repository_state.not_verified: {error}", file=sys.stderr)
        return 10
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        return CONTRACT.invalid_input_report(
            error, arguments.vllm_dlc_root, before
        )

    destination = Path(run_spec["artifact_destination"])
    try:
        destination.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        print(json.dumps({"code": "artifact.unavailable", "status": "failed"}, sort_keys=True))
        print(f"artifact.unavailable: {error}", file=sys.stderr)
        return 40
    transcript: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    statuses = {gate: "blocked" for gate in API_GATES}
    timeout_exit = 0
    process_exit = 0
    model_name = run_spec["deployment_profile"]["served_model_name"]
    timeouts = run_spec["timeouts"]

    startup_deadline = time.monotonic() + timeouts["startup_seconds"]
    models = None
    while time.monotonic() < startup_deadline:
        try:
            models = request_json(
                arguments.endpoint,
                "/v1/models",
                1,
                transcript,
                timeout_class="startup",
            )
            break
        except SmokeFailure as error:
            if error.code not in {"process.unreachable", "timeout.startup"}:
                diagnostics.append({"code": error.code, "message": error.message, "artifact_digest": None})
                statuses["service_ready"] = "failed"
                statuses["models_api"] = "failed"
                break
            time.sleep(0.05)
    if models is None and statuses["service_ready"] != "failed":
        diagnostics.append({"code": "timeout.startup", "message": "service readiness timed out", "artifact_digest": None})
        statuses["service_ready"] = "failed"
        statuses["models_api"] = "blocked"
        timeout_exit = 30
    elif models is not None:
        data = models.get("data")
        model_ids = [row.get("id") for row in data if isinstance(row, dict)] if isinstance(data, list) else []
        if model_name in model_ids:
            statuses["service_ready"] = "passed"
            statuses["models_api"] = "passed"
        else:
            statuses["service_ready"] = "failed"
            statuses["models_api"] = "failed"
            diagnostics.append({"code": "api.missing_model", "message": "expected served model is absent", "artifact_digest": None})

    request_specs = (
        ("completions_api", "/v1/completions", {"model": model_name, "prompt": "smoke", "max_tokens": 1}, "request"),
        ("chat_api", "/v1/chat/completions", {"model": model_name, "messages": [{"role": "user", "content": "smoke"}], "max_tokens": 1}, "request"),
        ("long_prefix_api", "/v1/completions", {"model": model_name, "prompt": "x" * 4096, "max_tokens": 1}, "long_prefix"),
    )
    if statuses["service_ready"] == "passed":
        for gate_id, path, body, timeout_class in request_specs:
            try:
                response = request_json(
                    arguments.endpoint,
                    path,
                    timeouts[f"{timeout_class}_seconds"],
                    transcript,
                    body,
                    timeout_class,
                )
                choices = response.get("choices")
                first = choices[0] if isinstance(choices, list) and choices else None
                if gate_id == "chat_api":
                    message = first.get("message") if isinstance(first, dict) else None
                    generated = message.get("content") if isinstance(message, dict) else None
                else:
                    generated = first.get("text") if isinstance(first, dict) else None
                if not isinstance(generated, str) or not generated.strip():
                    raise SmokeFailure("api.empty_generated_field", f"{gate_id} generated field is missing or empty")
                statuses[gate_id] = "passed"
            except SmokeFailure as error:
                statuses[gate_id] = "failed"
                diagnostics.append({"code": error.code, "message": error.message, "artifact_digest": None})
                if error.timeout_class == "request" and timeout_exit == 0:
                    timeout_exit = 31
                elif error.timeout_class == "long_prefix" and timeout_exit == 0:
                    timeout_exit = 32
            if not liveness(arguments.endpoint, min(timeouts["request_seconds"], 1)):
                statuses["server_liveness"] = "failed"
                diagnostics.append({"code": "process.died", "message": f"server died after {gate_id}", "artifact_digest": None})
                process_exit = 21
                break
        else:
            statuses["server_liveness"] = "passed"

    transcript_path = destination / "http-transcript.json"
    transcript_bytes = canonical_bytes(transcript)
    try:
        transcript_path.write_bytes(transcript_bytes)
    except OSError as error:
        print(json.dumps({"code": "artifact.sealing_failed", "status": "failed"}, sort_keys=True))
        print(f"artifact.sealing_failed: {error}", file=sys.stderr)
        return 40
    snapshot_path = destination / "repository-snapshot.json"
    try:
        after = CONTRACT.repository_snapshot(arguments.vllm_dlc_root)
    except (OSError, CONTRACT.subprocess.CalledProcessError) as error:
        print(json.dumps({"code": "repository_state.not_verified", "status": "failed"}, sort_keys=True))
        print(f"repository_state.not_verified: {error}", file=sys.stderr)
        return 50
    snapshot_bytes = canonical_bytes({"before": before, "after": after})
    try:
        snapshot_path.write_bytes(snapshot_bytes)
    except OSError as error:
        print(json.dumps({"code": "artifact.sealing_failed", "status": "failed"}, sort_keys=True))
        print(f"artifact.sealing_failed: {error}", file=sys.stderr)
        return 40
    if before != after:
        diagnostics.append({"code": "repository_state.changed", "message": "guarded repository changed", "artifact_digest": digest(snapshot_bytes)})

    gate_rows = []
    environment = run_spec["hardware"]["class"]
    execution_environment = environment if environment != "none" else "static"
    for gate_id in run_spec["gates"]:
        if gate_id in SIMULATED_GATES:
            mandatory = environment == "real_dlc_hardware"
            gate_rows.append(gate_row(gate_id, mandatory, "not_verified", {"environment": execution_environment, "gate": gate_id}))
        else:
            gate_rows.append(gate_row(gate_id, True, statuses[gate_id], {"gate": gate_id, "status": statuses[gate_id], "transcript": digest(transcript_bytes)}))
    if before != after:
        gate_rows.append(
            gate_row(
                "repository_state",
                True,
                "failed",
                {"before": before, "after": after},
            )
        )
    mandatory_statuses = {row["status"] for row in gate_rows if row["mandatory"]}
    overall = next((status for status in ("failed", "blocked", "not_verified") if status in mandatory_statuses), "passed")
    exit_code = 50 if before != after else timeout_exit or process_exit or (20 if overall != "passed" else 0)
    acceptance_eligible = execution_environment == "real_dlc_hardware" and overall == "passed"
    result = {
        "acceptance_eligible": acceptance_eligible,
        "artifacts": [
            {"id": "http_transcript", "kind": "http_transcript", "uri": transcript_path.as_uri(), "digest": digest(transcript_bytes)},
            {"id": "repository_snapshot", "kind": "repository_snapshot", "uri": snapshot_path.as_uri(), "digest": digest(snapshot_bytes)},
        ],
        "contract_kind": "result_evidence",
        "diagnostics": diagnostics,
        "execution_environment": execution_environment,
        "exit_code": exit_code,
        "gates": gate_rows,
        "overall_status": overall,
        "run_id": run_spec["run_id"],
        "run_spec_digest": run_spec["digest"],
        "schema_version": RESULT_SCHEMA,
    }
    result["digest"] = CONTRACT.canonical_digest(result)
    result_path = destination / "result-evidence.json"
    try:
        result_path.write_bytes(canonical_bytes(result))
    except OSError as error:
        print(json.dumps({"code": "artifact.sealing_failed", "status": "failed"}, sort_keys=True))
        print(f"artifact.sealing_failed: {error}", file=sys.stderr)
        return 40
    reference = {"digest": result["digest"], "schema_version": REFERENCE_SCHEMA, "uri": result_path.as_uri()}
    print(canonical_bytes(reference).decode("utf-8"))
    if diagnostics:
        print("; ".join(row["code"] for row in diagnostics), file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
