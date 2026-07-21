#!/usr/bin/python3
"""Resolve read-only ModelZoo evidence into a deterministic JSON contract."""

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


SCHEMA_VERSION = "modelzoo-dlc-tyd-resolved-manifest/v1"
VALIDATION_REPORT_SCHEMA = "modelzoo-dlc-tyd-validation-report/v1"
COMPONENT_NAMES = {
    "dlc-thunk": "dlc-thunk",
    "llvm": "llvm",
    "dlcsim": "dlcsim",
    "dlcsynapse": "dlcsynapse",
    "dlc_cl": "dlc-cl",
    "dlc-custom-kernel": "dlc-custom-kernel",
    "dlc_custom_kernel": "dlc-custom-kernel",
    "pytorch": "pytorch",
    "vllm": "vllm",
}
REQUIRED_COMPONENTS = tuple(sorted(set(COMPONENT_NAMES.values())))
WEIGHT_HEADINGS = {"weights", "weight files", "model weights", "权重文件", "模型权重"}
ENV_HEADINGS = {"environment variables", "enabled environment variables", "启用的环境变量", "环境变量"}
SERVE_HEADINGS = {"start service", "serve", "启动服务"}
REQUEST_HEADINGS = {"request", "send request", "发送请求"}
BLOCK_PRECEDENCE = (
    "blocked_model_not_found",
    "blocked_ambiguous_model",
    "blocked_malformed_metadata",
    "blocked_conflicting_source_claims",
    "blocked_missing_required_field",
    "blocked_missing_asset",
    "blocked_unresolved_component_ref",
    "blocked_missing_hardware",
    "blocked_missing_authorization",
    "blocked_unsupported_framework",
    "blocked_cleanup_incomplete",
)
BLOCK_RECOVERY = {
    "blocked_model_not_found": "provide_exact_existing_model_name",
    "blocked_ambiguous_model": "provide_unique_framework_selector",
    "blocked_malformed_metadata": "repair_or_select_valid_modelzoo_metadata",
    "blocked_missing_required_field": "provide_missing_required_evidence",
    "blocked_conflicting_source_claims": "provide_authoritative_override_or_observation",
    "blocked_missing_asset": "provide_approved_existing_model_asset",
    "blocked_unresolved_component_ref": "provide_approved_fixed_component_source",
    "blocked_missing_hardware": "provide_qualified_available_hardware",
    "blocked_missing_authorization": "provide_explicit_action_authorization",
    "blocked_unsupported_framework": "provide_supported_framework_adapter",
    "blocked_cleanup_incomplete": "complete_task_owned_resource_cleanup",
}
MAX_SOURCE_BYTES = 1024 * 1024
ACTION_INTENTS = {"prepare_dlc", "prepare_tyd", "prepare_both", "validate_dlc", "validate_tyd", "validate_both"}
HOST_GENERATIONS = {"none", "dlc_gen1", "tyd"}
SENSITIVE_NAME = re.compile(r"(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|ACCESS_KEY|PRIVATE_KEY|CREDENTIAL|AUTH)", re.IGNORECASE)
SENSITIVE_FLAG = re.compile(r"(?:^|[-_])(?:api[-_]?key|token|secret|password|passwd|credential|authorization)(?:=|$)", re.IGNORECASE)
URL_WITH_USERINFO = re.compile(r"[a-z][a-z0-9+.-]*://[^\s/@]+@", re.IGNORECASE)
PRODUCTION_OBSERVATION_PUBLIC_KEY = Path("/etc/chipltech/modelzoo-observation.pub")
PRODUCTION_COMPONENT_ROOTS = Path("/etc/chipltech/modelzoo-component-roots.json")
GIT = shutil.which("git")
OPENSSL = "/usr/bin/openssl"


class UniqueSafeLoader(yaml.SafeLoader):
    pass


def construct_mapping(loader: yaml.Loader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise yaml.constructor.ConstructorError(None, None, "duplicate key", key_node.start_mark)
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueSafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping)
for first_character, resolvers in list(UniqueSafeLoader.yaml_implicit_resolvers.items()):
    UniqueSafeLoader.yaml_implicit_resolvers[first_character] = [
        resolver for resolver in resolvers if resolver[0] != "tag:yaml.org,2002:bool"
    ]
UniqueSafeLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$"), list("tf")
)


class ResolutionError(Exception):
    def __init__(self, code: str, detail: str, *, line: int | None = None, column: int | None = None, payload: bytes | None = None):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.line = line
        self.column = column
        self.payload = payload


def canonical_json(document: dict[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def redact_value(value: Any, key: str = "") -> Any:
    if SENSITIVE_NAME.search(key):
        return "[redacted]"
    if isinstance(value, dict):
        return {item_key: redact_value(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [redact_value(item, key) for item in value]
    if isinstance(value, str) and (SENSITIVE_NAME.search(value) or URL_WITH_USERINFO.search(value)):
        return "[redacted]"
    return value


def reported_path(path: str | Path | None) -> str | None:
    if path is None:
        return None
    value = str(path)
    return "[redacted]" if SENSITIVE_NAME.search(value) or URL_WITH_USERINFO.search(value) else value


def attach_digest(document: dict[str, Any]) -> dict[str, Any]:
    payload = {
        key: document[key]
        for key in (
            "inputs", "modelzoo", "selection", "sources", "source_claims",
            "current_observations", "resolved", "missing_fields", "conflicts", "blocked"
        )
    }
    document["resolution_id"] = "sha256:" + hashlib.sha256(canonical_json(payload).encode()).hexdigest()
    return document


def sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def read_regular_file(path: Path) -> bytes:
    if path.is_symlink():
        raise ResolutionError("blocked_malformed_metadata", "symlink_source_rejected")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_SOURCE_BYTES:
            raise ResolutionError("blocked_malformed_metadata", "invalid_source_file")
        chunks = []
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def parse_metafile(path: Path) -> tuple[dict[str, Any], bytes]:
    payload = read_regular_file(path)
    try:
        text = payload.decode("utf-8", errors="strict")
        forbidden = tuple(yaml.tokens.AnchorToken for _ in (0,)) + (yaml.tokens.AliasToken, yaml.tokens.TagToken)
        if any(isinstance(token, forbidden) for token in yaml.scan(text)):
            raise ResolutionError("blocked_malformed_metadata", "yaml_alias_anchor_or_tag_rejected", payload=payload)
        documents = list(yaml.load_all(text, Loader=UniqueSafeLoader))
    except ResolutionError:
        raise
    except (UnicodeDecodeError, yaml.YAMLError) as error:
        mark = getattr(error, "problem_mark", None)
        raise ResolutionError(
            "blocked_malformed_metadata",
            "yaml_parse_error",
            line=None if mark is None else mark.line + 1,
            column=None if mark is None else mark.column + 1,
            payload=payload,
        ) from None
    if len(documents) != 1 or not isinstance(documents[0], dict):
        raise ResolutionError("blocked_malformed_metadata", "metafile_must_be_one_mapping", payload=payload)
    document = documents[0]
    for field in ("Name", "Task"):
        if type(document.get(field)) is not str or not document[field]:
            raise ResolutionError("blocked_malformed_metadata", f"invalid_type:{field}", payload=payload)
    for field in ("Infer", "Train"):
        if type(document.get(field)) is not bool:
            raise ResolutionError("blocked_malformed_metadata", f"invalid_type:{field}", payload=payload)
    if "Parameters" not in document:
        raise ResolutionError("blocked_malformed_metadata", "missing_field:Parameters", payload=payload)
    return document, payload


def malformed_name_hint(payload: bytes | None) -> str | None:
    if payload is None:
        return None
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None
    matches = re.findall(r"^Name:\s*([^\r\n]+?)\s*$", text, re.MULTILINE)
    if len(matches) != 1:
        return None
    value = matches[0].strip()
    if value.startswith(("&", "*", "!", "[", "{", "|", ">")):
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return value or None


def path_identity(root: Path, metafile: Path) -> tuple[str, str, str]:
    relative_directory = metafile.parent.relative_to(root)
    parts = relative_directory.parts
    if parts[:2] == ("vllm", "models"):
        framework = "vllm"
        entry_parts = parts[2:]
    else:
        framework = parts[0]
        entry_parts = parts[1:] or parts[:1]
    entry_id = "/".join(entry_parts)
    return framework, entry_id, relative_directory.as_posix()


def discover(root: Path, model_name: str, framework: str | None) -> list[dict[str, Any]]:
    candidates = []
    for metafile in sorted(root.rglob("metafile.yml"), key=lambda path: path.relative_to(root).as_posix()):
        if metafile.is_symlink() or any(parent.is_symlink() for parent in metafile.parents if parent != root.parent):
            continue
        candidate_framework, entry_id, entry_path = path_identity(root, metafile)
        if framework is not None and candidate_framework != framework:
            continue
        try:
            metadata, payload = parse_metafile(metafile)
            error = None
        except ResolutionError as caught:
            metadata, payload, error = None, caught.payload, caught
            if payload is None:
                try:
                    payload = read_regular_file(metafile)
                except ResolutionError:
                    pass
        declared_name = malformed_name_hint(payload) if metadata is None else metadata["Name"]
        if declared_name != model_name:
            continue
        candidates.append(
            {
                "framework": candidate_framework,
                "entry_id": declared_name,
                "entry_path": entry_path,
                "metafile_path": metafile,
                "metadata": metadata,
                "payload": payload,
                "error": error,
            }
        )
    return sorted(candidates, key=lambda row: (row["framework"], row["entry_path"]))


def git_identity(root: Path) -> dict[str, Any]:
    if GIT is None:
        return {
            "state": "not_available",
            "git_root": None,
            "remote": None,
            "branch_or_tag": None,
            "head": None,
            "dirty_observation": [],
        }
    try:
        top = subprocess.run(
            [GIT, "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if Path(top).resolve() != root:
            return {
                "state": "not_available",
                "git_root": None,
                "remote": None,
                "branch_or_tag": None,
                "head": None,
                "dirty_observation": [],
            }
        head = subprocess.run(
            [GIT, "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        branch = subprocess.run(
            [GIT, "-C", str(root), "branch", "--show-current"], capture_output=True, text=True, check=True
        ).stdout.strip() or None
        if branch is None:
            tag_process = subprocess.run(
                [GIT, "-C", str(root), "describe", "--tags", "--exact-match", "HEAD"],
                capture_output=True,
                text=True,
                check=False,
            )
            branch = tag_process.stdout.strip() if tag_process.returncode == 0 else None
        remotes = subprocess.run(
            [GIT, "-C", str(root), "remote"], capture_output=True, text=True, check=True
        ).stdout.splitlines()
        if not remotes:
            raise subprocess.CalledProcessError(2, ["git", "remote"])
        remote_name = "origin" if "origin" in remotes else sorted(remotes)[0]
        remote_process = subprocess.run(
            [GIT, "-C", str(root), "remote", "get-url", remote_name], capture_output=True, text=True, check=False
        )
        if remote_process.returncode != 0 or not remote_process.stdout.strip():
            raise subprocess.CalledProcessError(remote_process.returncode, remote_process.args)
        status = subprocess.run(
            [GIT, "-C", str(root), "-c", "core.quotePath=false", "status", "--short"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        return {
            "state": "available",
            "git_root": reported_path(top),
            "remote": sanitized_remote(remote_process.stdout.strip()) if remote_process.returncode == 0 else None,
            "branch_or_tag": branch,
            "head": head,
            "dirty_observation": [redact_value(item, "dirty_observation") for item in status],
        }
    except (OSError, subprocess.CalledProcessError):
        return {
            "state": "not_available",
            "git_root": None,
            "remote": None,
            "branch_or_tag": None,
            "head": None,
            "dirty_observation": [],
        }


def source_record(root: Path, path: Path, payload: bytes | None) -> dict[str, Any]:
    return {
        "path": reported_path(path.relative_to(root).as_posix()),
        "sha256": None if payload is None else sha256_bytes(payload),
        "state": "missing" if payload is None else "present",
    }


def sanitized_remote(remote: str) -> str | None:
    if not remote or "?" in remote or "#" in remote or "@" in remote.split("://", 1)[-1].split("/", 1)[0]:
        return None
    return remote


def markdown_sections(text: str) -> list[tuple[str, int, int, str]]:
    headings = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            headings.append((index, len(match.group(1)), match.group(2).strip().lower()))
    sections = []
    for position, (start, level, heading) in enumerate(headings):
        end = len(lines)
        for next_start, next_level, _ in headings[position + 1 :]:
            if next_level <= level:
                end = next_start
                break
        sections.append((heading, start + 2, end, "\n".join(lines[start + 1 : end])))
    return sections


def evidence_value(value: Any, path: str, start: int, end: int, content: str) -> dict[str, Any]:
    return {
        "classification": "modelzoo_declared",
        "state": "present",
        "value": redact_value(value),
        "sources": [{"path": path, "line_start": start, "line_end": end, "content_sha256": sha256_bytes(content.encode())}],
    }


def missing_evidence() -> dict[str, Any]:
    return {"classification": "missing", "state": "missing", "value": None, "sources": []}


def fenced_blocks(content: str) -> list[str]:
    return [match.group(1).strip() for match in re.finditer(r"```(?:bash|sh)?\s*\n(.*?)```", content, re.DOTALL | re.IGNORECASE)]


def parse_readme(root: Path, path: Path) -> tuple[dict[str, Any], bytes | None, list[str]]:
    if not path.is_file() or path.is_symlink():
        return {
            "weight_path": missing_evidence(),
            "component_refs": [],
            "missing_component_refs": list(REQUIRED_COMPONENTS),
            "required_environment": [],
            "serve_contract": missing_evidence(),
            "smoke_request": missing_evidence(),
        }, None, ["blocked_missing_required_field"]
    payload = read_regular_file(path)
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ResolutionError("blocked_malformed_metadata", "readme_not_utf8", payload=payload) from None
    relative = path.relative_to(root).as_posix()
    sections = markdown_sections(text)
    blockers = []

    weights = []
    for heading, start, end, content in sections:
        if heading in WEIGHT_HEADINGS:
            for line in content.splitlines():
                candidate = line.strip().strip("`")
                if candidate.startswith("/") and not re.search(r"[$*?`|;&<>]", candidate):
                    weights.append((candidate, start, end, content))
    unique_weights = sorted({row[0] for row in weights})
    if len(unique_weights) == 1:
        row = next(row for row in weights if row[0] == unique_weights[0])
        weight = evidence_value(row[0], relative, row[1], row[2], row[3])
    elif len(unique_weights) > 1:
        weight = {"classification": "conflicting", "state": "conflicting", "value": None, "sources": [{"path": relative, "line_start": row[1], "line_end": row[2]} for row in weights]}
        blockers.append("blocked_conflicting_source_claims")
    else:
        weight = missing_evidence()
        blockers.append("blocked_missing_required_field")

    refs: dict[str, set[str]] = {}
    for match in re.finditer(r"\*\*([^*]+)\*\*\s*:\s*([0-9a-f]{40})\b", text, re.IGNORECASE):
        label = match.group(1).strip().lower().replace(" ", "_")
        canonical = COMPONENT_NAMES.get(label)
        if canonical:
            line = text.count("\n", 0, match.start()) + 1
            refs.setdefault(canonical, set()).add((match.group(2).lower(), line))
    component_refs = []
    for component in sorted(refs):
        rows = sorted(refs[component])
        values = sorted({row[0] for row in rows})
        state = "present" if len(values) == 1 else "conflicting"
        component_refs.append({"component": component, "classification": "modelzoo_declared", "state": state, "ref": values[0] if len(values) == 1 else None, "sources": [{"path": relative, "line": line} for _, line in rows]})
        if state == "conflicting":
            blockers.append("blocked_conflicting_source_claims")
    if set(refs) != set(REQUIRED_COMPONENTS):
        blockers.append("blocked_missing_required_field")
    missing_component_refs = sorted(set(REQUIRED_COMPONENTS) - set(refs))

    environment: dict[str, list[tuple[str, int]]] = {}
    for heading, section_start, _, content in sections:
        if heading in ENV_HEADINGS:
            for match in re.finditer(r"^\s*export\s+([A-Z_][A-Z0-9_]*)=([^\n]+)$", content, re.MULTILINE):
                name, value = match.groups()
                if not SENSITIVE_NAME.search(name) and not URL_WITH_USERINFO.search(value) and not re.search(r"[`$|;&<>]", value):
                    environment.setdefault(name, []).append(("[redacted]", section_start + content.count("\n", 0, match.start())))
    environment_rows = []
    for name in sorted(environment):
        rows = environment[name]
        values = sorted({row[0] for row in rows})
        if len(values) > 1:
            blockers.append("blocked_conflicting_source_claims")
            environment_rows.append({"name": name, "value": None, "classification": "conflicting", "state": "conflicting", "sources": [{"path": relative, "line": line} for _, line in rows]})
        else:
            environment_rows.append({"name": name, "value": values[0], "classification": "modelzoo_declared", "state": "present", "sources": [{"path": relative, "line": line} for _, line in rows]})

    serve_rows = []
    for heading, start, end, content in sections:
        if heading in SERVE_HEADINGS:
            for block in fenced_blocks(content):
                command = re.sub(r"\\\s*\n\s*", " ", block).strip()
                if re.search(r"[`$|;&<>]", command):
                    continue
                try:
                    tokens = shlex.split(command, posix=True)
                except ValueError:
                    continue
                sensitive = any(
                    SENSITIVE_NAME.search(token)
                    or SENSITIVE_FLAG.search(token)
                    or URL_WITH_USERINFO.search(token)
                    or re.search(r"\b(?:10\.|172\.(?:1[6-9]|2\d|3[01])\.|192\.168\.)", token)
                    for token in tokens
                )
                if not sensitive and ("vllm.entrypoints.openai.api_server" in tokens or tokens[:2] == ["vllm", "serve"]):
                    serve_rows.append((tokens, start, end, content))
    unique_serves = {tuple(row[0]) for row in serve_rows}
    if len(unique_serves) == 1:
        row = serve_rows[0]
        serve = evidence_value(list(row[0]), relative, row[1], row[2], row[3])
    elif len(unique_serves) > 1:
        serve = {"classification": "conflicting", "state": "conflicting", "value": None, "sources": [{"path": relative, "line_start": row[1], "line_end": row[2], "content_sha256": sha256_bytes(row[3].encode())} for row in serve_rows]}
        blockers.append("blocked_conflicting_source_claims")
    else:
        serve = missing_evidence()
        blockers.append("blocked_missing_required_field")

    requests = []
    for heading, start, end, content in sections:
        if heading in REQUEST_HEADINGS:
            requests.extend((block, start, end, content) for block in fenced_blocks(content))
    if requests:
        block, start, end, content = requests[0]
        endpoint = next((value for value in ("/v1/chat/completions", "/v1/completions", "/health") if value in block), None)
        smoke = evidence_value({"endpoint": endpoint, "request_block_sha256": sha256_bytes(block.encode())}, relative, start, end, content)
        if endpoint is None:
            smoke = missing_evidence()
            blockers.append("blocked_missing_required_field")
    else:
        smoke = missing_evidence()
        blockers.append("blocked_missing_required_field")

    return {
        "weight_path": weight,
        "component_refs": component_refs,
        "missing_component_refs": missing_component_refs,
        "required_environment": environment_rows,
        "serve_contract": serve,
        "smoke_request": smoke,
    }, payload, blockers


def workflow_contract() -> dict[str, Any]:
    components = ["dlc-thunk", "LLVM", "DLCsim", "DLCSynapse", "DLC_CL", "DLC_Custom_Kernel Repository", "PyTorch DLC Backend", "vLLM"]
    return {
        "validation_report_schema": VALIDATION_REPORT_SCHEMA,
        "terminal_blockers": ["blocked_cleanup_incomplete"],
        "dlc": {
            "stages": ["image_build", "C1a_package_import", "C1b_fresh_process_device_execution_when_authorized", "model_smoke_when_authorized", "export_tar", "sha256", "attestation", "cleanup"],
            "delegates": {"package_and_layered_smoke": "dlc-env-setup", "model_compatibility_and_tp": "model-adaptation"},
            "artifact_identity": ["fixed_tag", "image_id", "image_configuration", "tar_path", "tar_size", "tar_sha256", "attestation", "validation_report"],
            "validation_states": ["c1a_package_import_pass", "c1b_runtime_execution_pass", "model_functional_pass", "benchmark_pass", "not_verified"],
        },
        "tyd": {
            "build_components": components,
            "compile_process_environment": {component: {"DLC_TPU_VERSION": "2"} for component in components},
            "process_environment_evidence_required": True,
            "component_provenance_record": {
                "required_fields": ["source_full_sha", "build_command_identity", "build_epoch", "artifact_sha256", "compile_process_environment_evidence"],
                "required_environment": {"DLC_TPU_VERSION": "2"},
                "missing_record_status": "blocked_missing_required_field",
                "formal_tag_and_full_stack_pass_allowed_when_incomplete": False,
                "epoch_lifecycle": {
                    "mode": "append_only",
                    "states": ["started", "passed", "failed", "superseded"],
                    "failed_epoch_evidence_retained": True,
                    "completed_component_provenance_retained": True,
                    "retry_requires_new_epoch": True,
                    "supersedes_epoch_reference_required": True,
                },
            },
            "image_env_alone_sufficient": False,
            "static_package_validation": "required",
            "dlc_gen1_device_execution": "prohibited",
            "dlc_gen1_execution_status": "intentionally_not_executed_on_dlc_gen1",
            "artifact_identity": ["fixed_tag", "image_id", "image_configuration", "tar_path", "tar_size", "tar_sha256", "attestation", "validation_report"],
            "validation_states": ["c1a_package_import_pass", "c1b_runtime_execution_pass", "static_package_pass", "model_functional_pass", "benchmark_pass", "not_verified", "blocked_*", "intentionally_not_executed_on_dlc_gen1"],
        },
        "final_report_sections": ["modelzoo_claims", "current_observations", "inferences", "execution_evidence", "unverified_scope"],
    }


def base_report(root: Path, model: str, framework: str | None) -> dict[str, Any]:
    git = git_identity(root)
    return {
        "schema": SCHEMA_VERSION,
        "resolution_status": "blocked",
        "inputs": {"model_name": model, "framework_selector": framework, "model_path_override": None},
        "modelzoo": {
            "root": reported_path(root),
            "read_only": True,
            "git_root": git["git_root"],
            "remote": git["remote"],
            "branch_or_tag": git["branch_or_tag"],
            "head": git["head"],
            "dirty_observation": git["dirty_observation"],
            "identity_state": git["state"],
        },
        "selection": {"framework": None, "model_directory": None, "candidates": []},
        "sources": {
            "metafile": {"path": None, "sha256": None, "fields": None},
            "readme": {"path": None, "sha256": None},
        },
        "source_claims": {
            "weight_paths": [],
            "component_refs": {},
            "required_environment": {},
            "serve_contract": {},
            "smoke_contract": {},
        },
        "current_observations": {
            "model_asset": {"status": "not_observed"},
            "component_refs": {"status": "not_observed"},
            "host_and_hardware": {"status": "not_observed"},
            "authorization": {"status": "not_observed"},
            "trust_class": "not_observed",
            "action_eligible": False,
        },
        "resolved": {
            "model_path": None,
            "component_refs": {},
            "required_environment": {},
            "serve_contract": {},
            "smoke_contract": {},
            "framework_adapter": None,
            "model_path_resolution_reason": None,
        },
        "missing_fields": [],
        "conflicts": [],
        "claim_boundary": {
            "historical_modelzoo_claims_are_current_facts": False,
            "unverified_scope": ["image_build", "c1a", "c1b", "model_functional", "benchmark", "real_hardware"],
            "tyd_device_execution_on_dlc_gen1": "intentionally_not_executed_on_dlc_gen1",
        },
        "blocked": {"code": None, "missing_or_conflicting_fields": [], "evidence": [], "details": []},
        "workflow_contract": workflow_contract(),
    }


def block(report: dict[str, Any], code: str, detail: str, **extra: Any) -> dict[str, Any]:
    blocker = {"code": code, "detail": detail}
    blocker.update({key: value for key, value in extra.items() if value is not None})
    report["blocked"]["details"].append(blocker)
    report["blocked"]["details"].sort(key=lambda row: (BLOCK_PRECEDENCE.index(row["code"]), row["detail"]))
    report["blocked"]["code"] = report["blocked"]["details"][0]["code"]
    field = extra.get("field")
    if field:
        report["blocked"]["missing_or_conflicting_fields"].append(field)
    evidence = extra.get("evidence")
    if evidence:
        report["blocked"]["evidence"].append(evidence)
    elif report["sources"]["metafile"]["path"]:
        report["blocked"]["evidence"].append(report["sources"]["metafile"]["path"])
        if report["sources"]["readme"]["path"]:
            report["blocked"]["evidence"].append(report["sources"]["readme"]["path"])
    recovery = extra.get("recovery", BLOCK_RECOVERY[code])
    report["blocked"].setdefault("recovery_inputs", []).append(recovery)
    report["blocked"]["missing_or_conflicting_fields"] = sorted(set(report["blocked"]["missing_or_conflicting_fields"]))
    report["blocked"]["evidence"] = sorted(set(report["blocked"]["evidence"]))
    if "recovery_inputs" in report["blocked"]:
        report["blocked"]["recovery_inputs"] = sorted(set(report["blocked"]["recovery_inputs"]))
    report["resolution_status"] = "blocked"
    return report


def verified_evidence(document: Any, field: str, expected_claims: dict[str, Any], public_key: Path) -> dict[str, str]:
    if not isinstance(document, dict) or set(document) != {"path", "sha256", "signature_path", "signature_sha256"}:
        raise ResolutionError("blocked_missing_required_field", f"invalid_evidence:{field}")
    path = Path(document["path"])
    signature_path = Path(document["signature_path"])
    if (
        type(document["path"]) is not str
        or type(document["sha256"]) is not str
        or type(document["signature_path"]) is not str
        or type(document["signature_sha256"]) is not str
        or not path.is_absolute()
        or not signature_path.is_absolute()
    ):
        raise ResolutionError("blocked_missing_required_field", f"invalid_evidence:{field}")
    payload = read_regular_file(path)
    actual = sha256_bytes(payload)
    if actual != document["sha256"]:
        raise ResolutionError("blocked_missing_required_field", f"evidence_digest_mismatch:{field}")
    signature = read_regular_file(signature_path)
    if sha256_bytes(signature) != document["signature_sha256"]:
        raise ResolutionError("blocked_missing_required_field", f"evidence_signature_digest_mismatch:{field}")
    verified = subprocess.run(
        [OPENSSL, "pkeyutl", "-verify", "-pubin", "-inkey", str(public_key), "-rawin", "-in", str(path), "-sigfile", str(signature_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if verified.returncode != 0:
        raise ResolutionError("blocked_missing_required_field", f"evidence_signature_invalid:{field}")
    try:
        claims = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ResolutionError("blocked_missing_required_field", f"invalid_evidence_payload:{field}") from None
    if claims != expected_claims:
        raise ResolutionError("blocked_missing_required_field", f"evidence_claim_mismatch:{field}")
    return {"path": reported_path(path.resolve()), "sha256": actual, "signature_path": reported_path(signature_path.resolve()), "signature_sha256": sha256_bytes(signature)}


def commit_exists(repository: Path, ref: str) -> bool:
    if GIT is None or not repository.is_dir() or repository.is_symlink() or not re.fullmatch(r"[0-9a-f]{40}", ref):
        return False
    result = subprocess.run(
        [GIT, "-C", str(repository), "cat-file", "-e", f"{ref}^{{commit}}"],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def component_repository_observation(repository: Path, ref: str) -> dict[str, Any] | None:
    if not commit_exists(repository, ref):
        return None
    identity = git_identity(repository.resolve())
    if identity["state"] != "available":
        return None
    return {
        "repository_root": identity["git_root"],
        "remote": identity["remote"],
        "head": identity["head"],
        "dirty_observation": identity["dirty_observation"],
        "requested_ref": ref,
        "requested_commit_present": True,
    }


def approved_component_root(component: str, repository: Path, fixture_mode: bool) -> bool:
    if fixture_mode:
        return True
    try:
        metadata = repository.stat()
    except OSError:
        return False
    if metadata.st_uid != 0 or metadata.st_mode & 0o022 or not protected_public_key_available(PRODUCTION_COMPONENT_ROOTS):
        return False
    try:
        roots = json.loads(read_regular_file(PRODUCTION_COMPONENT_ROOTS).decode("utf-8"))
    except (ResolutionError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(roots, dict) and set(roots) == set(REQUIRED_COMPONENTS) and roots.get(component) == str(repository.resolve())


def protected_public_key_available(path: Path) -> bool:
    try:
        metadata = path.stat()
    except OSError:
        return False
    return path.is_file() and not path.is_symlink() and metadata.st_uid == 0 and not metadata.st_mode & 0o022


def apply_preflight(report: dict[str, Any], path: Path, test_public_key: Path | None) -> None:
    try:
        document = json.loads(read_regular_file(path).decode("utf-8"))
    except (ResolutionError, UnicodeDecodeError, json.JSONDecodeError):
        block(report, "blocked_missing_required_field", "invalid_preflight_json")
        return
    expected = {"intent", "weight_path", "component_sources", "base_image", "framework_package", "hardware", "authorization"}
    if not isinstance(document, dict) or set(document) != expected:
        block(report, "blocked_missing_required_field", "invalid_preflight_schema")
        return
    if type(document["intent"]) is not str or type(document["weight_path"]) is not str:
        block(report, "blocked_missing_required_field", "invalid_preflight_type")
        return
    if document["intent"] not in ACTION_INTENTS or not Path(document["weight_path"]).is_absolute():
        block(report, "blocked_missing_required_field", "invalid_preflight_value")
        return
    public_key = test_public_key or PRODUCTION_OBSERVATION_PUBLIC_KEY
    if (test_public_key is None and not protected_public_key_available(public_key)) or (test_public_key is not None and (not public_key.is_file() or public_key.is_symlink())):
        block(report, "blocked_missing_required_field", "trusted_observation_key_missing", field="current_observations", recovery="install_protected_observation_trust_root")
        return
    try:
        base_identity = document["base_image"].get("identity")
        package_identity = document["framework_package"].get("identity")
        hardware_generation = document["hardware"].get("generation")
        hardware_available = document["hardware"].get("available")
        resource_occupied = document["hardware"].get("resource_occupied")
        authorized = document["authorization"].get("authorized")
        if type(base_identity) is not str or not re.fullmatch(r"sha256:[0-9a-f]{64}", base_identity):
            raise ResolutionError("blocked_missing_required_field", "invalid_base_image_identity")
        if type(package_identity) is not str or not package_identity.strip():
            raise ResolutionError("blocked_missing_required_field", "invalid_framework_package_identity")
        if hardware_generation not in HOST_GENERATIONS:
            raise ResolutionError("blocked_missing_required_field", "invalid_hardware_generation")
        if type(hardware_available) is not bool or type(resource_occupied) is not bool or type(authorized) is not bool:
            raise ResolutionError("blocked_missing_required_field", "invalid_preflight_observation_type")
        base_image_evidence = verified_evidence(
            document["base_image"].get("evidence"), "base_image",
            {"identity": base_identity},
            public_key,
        )
        package_evidence = verified_evidence(
            document["framework_package"].get("evidence"), "framework_package",
            {"identity": package_identity},
            public_key,
        )
        hardware_evidence = verified_evidence(
            document["hardware"].get("evidence"), "hardware",
            {
                "available": hardware_available,
                "generation": hardware_generation,
                "resource_occupied": resource_occupied,
            },
            public_key,
        )
        authorization_evidence = verified_evidence(
            document["authorization"].get("evidence"), "authorization",
            {"authorized": authorized, "intent": document["intent"]},
            public_key,
        )
    except (AttributeError, ResolutionError) as error:
        block(report, "blocked_missing_required_field", str(error), field="current_observations", recovery="provide_hash_bound_preflight_evidence")
        return
    source = {"path": reported_path(path.resolve()), "sha256": sha256_bytes(read_regular_file(path))}
    report["inputs"]["model_path_override"] = reported_path(document["weight_path"])
    model_config = Path(document["weight_path"]) / "config.json"
    model_config_sha256 = sha256_bytes(read_regular_file(model_config)) if model_config.is_file() and not model_config.is_symlink() else None
    report["current_observations"] = {
        "model_asset": {
            "path": reported_path(document["weight_path"]),
            "exists": Path(document["weight_path"]).is_dir() and model_config_sha256 is not None,
            "config_path": reported_path(model_config) if model_config_sha256 is not None else None,
            "config_sha256": model_config_sha256,
            "source": source,
        },
        "component_refs": {},
        "base_image": {"identity": document["base_image"].get("identity"), "evidence": base_image_evidence},
        "framework_package": {"identity": document["framework_package"].get("identity"), "evidence": package_evidence},
        "host_and_hardware": {
            "generation": document["hardware"].get("generation"),
            "available": document["hardware"].get("available"),
            "resource_occupied": document["hardware"].get("resource_occupied"),
            "evidence": hardware_evidence,
        },
        "authorization": {
            "intent": document["intent"],
            "authorized": document["authorization"].get("authorized"),
            "evidence": authorization_evidence,
        },
        "trust_class": "fixture_diagnostic" if test_public_key else "protected_local_observer",
        # Resolver evidence qualifies discovery only. The action workflow must bind
        # assets, component sources, and authorization in its own sealed run record.
        "action_eligible": False,
    }
    report["resolved"]["model_path"] = reported_path(document["weight_path"])
    declared_weights = [row["value"] for row in report["source_claims"]["weight_paths"]]
    model_path_is_override = document["weight_path"] not in declared_weights
    report["resolved"]["model_path_resolution_reason"] = "user_override" if model_path_is_override else "modelzoo_claim"
    if model_path_is_override:
        report["conflicts"] = sorted(set(report["conflicts"] + ["model_path"]))
    if test_public_key is None:
        report["current_observations"]["model_asset"]["status"] = "untrusted_preflight_path"
        block(report, "blocked_missing_required_field", "model_asset_requires_sealed_action_record", field="model_asset", recovery="provide_sealed_action_record_with_asset_identity")
    elif not report["current_observations"]["model_asset"]["exists"]:
        block(report, "blocked_missing_asset", "effective_model_asset_missing", field="model_asset", evidence=source["path"], recovery="provide_approved_model_asset_with_config")
    sources = document["component_sources"]
    if not isinstance(sources, dict):
        block(report, "blocked_missing_required_field", "invalid_component_sources", field="component_refs", recovery="provide_approved_component_sources")
    else:
        for component, claim in report["source_claims"]["component_refs"].items():
            row = sources.get(component)
            observation = None
            if (
                isinstance(row, dict)
                and set(row) == {"repository_root", "ref"}
                and row.get("ref") == claim["ref"]
                and approved_component_root(component, Path(row.get("repository_root", "")), test_public_key is not None)
            ):
                observation = component_repository_observation(Path(row.get("repository_root", "")), row.get("ref", ""))
            valid = observation is not None
            report["current_observations"]["component_refs"][component] = {"resolved": valid, "observation": observation, "ref": claim["ref"]}
            if not valid:
                block(report, "blocked_unresolved_component_ref", "approved_component_ref_unresolved", field=f"component_refs.{component}", recovery=f"provide_approved_source_for:{component}")
    hardware = report["current_observations"]["host_and_hardware"]
    if document["intent"].startswith("validate") and (hardware["available"] is not True or hardware["resource_occupied"] is not False):
        block(report, "blocked_missing_hardware", "qualified_hardware_missing_or_busy", field="host_and_hardware", evidence=hardware_evidence["path"], recovery="provide_available_unoccupied_hardware")
    if document["intent"] in {"validate_tyd", "validate_both"} and hardware["generation"] != "tyd":
        block(report, "blocked_missing_hardware", "qualified_tyd_hardware_missing", field="host_and_hardware.generation", recovery="provide_qualified_tyd_host")
    if document["authorization"].get("authorized") is not True:
        block(report, "blocked_missing_authorization", "explicit_authorization_missing", field="authorization", evidence=authorization_evidence["path"], recovery="provide_explicit_action_authorization")


def resolve(root: Path, model: str, framework: str | None, preflight: Path | None, test_public_key: Path | None = None) -> dict[str, Any]:
    report = base_report(root, model, framework)
    if report["modelzoo"]["identity_state"] != "available":
        return block(
            report,
            "blocked_malformed_metadata",
            "modelzoo_git_identity_unavailable",
            field="modelzoo.git_identity",
            recovery="provide_authoritative_modelzoo_git_root",
        )
    if not model or "\x00" in model or (framework is not None and (not framework or "\x00" in framework)):
        return block(report, "blocked_malformed_metadata", "invalid_selector")
    all_candidates = discover(root, model, None)
    report["selection"]["candidates"] = [
        {"framework": row["framework"], "model_directory": reported_path(row["entry_path"])}
        for row in all_candidates
    ]
    if not all_candidates:
        return block(report, "blocked_model_not_found", "no_exact_model_match")
    candidates = [row for row in all_candidates if framework is None or row["framework"] == framework]
    if len(candidates) != 1:
        return block(report, "blocked_ambiguous_model", "framework_selector_required")
    candidate = candidates[0]
    report["selection"]["framework"] = candidate["framework"]
    report["selection"]["model_directory"] = reported_path(candidate["entry_path"])
    metafile_source = source_record(root, candidate["metafile_path"], candidate["payload"])
    report["sources"]["metafile"].update(path=metafile_source["path"], sha256=metafile_source["sha256"])
    if candidate["error"] is not None:
        error = candidate["error"]
        return block(report, error.code, error.detail, line=error.line, column=error.column)
    metadata = candidate["metadata"]
    report["sources"]["metafile"]["fields"] = redact_value(metadata)
    readme_path = candidate["metafile_path"].parent / "README.md"
    try:
        evidence, readme_payload, evidence_blockers = parse_readme(root, readme_path)
    except ResolutionError as error:
        readme_source = source_record(root, readme_path, error.payload)
        report["sources"]["readme"].update(path=readme_source["path"], sha256=readme_source["sha256"])
        return block(report, error.code, error.detail)
    readme_source = source_record(root, readme_path, readme_payload)
    report["sources"]["readme"].update(
        path=readme_source["path"] if readme_payload is not None else None,
        sha256=readme_source["sha256"],
    )
    weight = evidence["weight_path"]
    report["source_claims"] = {
        "weight_paths": [] if weight["state"] != "present" else [weight],
        "component_refs": {row["component"]: row for row in evidence["component_refs"]},
        "required_environment": {row["name"]: row for row in evidence["required_environment"]},
        "serve_contract": evidence["serve_contract"],
        "smoke_contract": evidence["smoke_request"],
    }
    report["missing_fields"] = sorted(
        key for key, value in evidence.items() if isinstance(value, dict) and value.get("state") == "missing"
    )
    report["missing_fields"].extend(f"component_refs.{component}" for component in evidence["missing_component_refs"])
    report["conflicts"] = sorted(key for key, value in evidence.items() if isinstance(value, dict) and value.get("state") == "conflicting")
    if candidate["framework"] != "vllm":
        report["resolved"]["framework_adapter"] = None
        block(report, "blocked_unsupported_framework", "no_framework_adapter")
    elif not metadata["Infer"]:
        block(report, "blocked_missing_required_field", "metafile_infer_false_without_adapter_evidence")
    else:
        report["resolved"]["framework_adapter"] = "vllm/v1"
        report["resolved"]["component_refs"] = {
            key: value["ref"] for key, value in report["source_claims"]["component_refs"].items()
        }
        report["resolved"]["required_environment"] = {
            key: value["value"] for key, value in report["source_claims"]["required_environment"].items()
        }
        report["resolved"]["serve_contract"] = evidence["serve_contract"]
        report["resolved"]["smoke_contract"] = evidence["smoke_request"]
        for code in sorted(set(evidence_blockers), key=BLOCK_PRECEDENCE.index):
            block(report, code, "required_vllm_readme_evidence_missing_or_conflicting")
    if candidate["framework"] == "vllm" and preflight is None:
        report["missing_fields"].append("current_host_preflight")
        block(report, "blocked_missing_required_field", "current_host_preflight_missing")
    elif candidate["framework"] == "vllm":
        apply_preflight(report, preflight, test_public_key)
    if report["resolved"]["model_path_resolution_reason"] == "user_override":
        report["conflicts"] = sorted(set(report["conflicts"] + ["model_path"]))
    report["missing_fields"] = sorted(set(report["missing_fields"]))
    report["blocked"]["missing_or_conflicting_fields"] = sorted(set(report["blocked"]["missing_or_conflicting_fields"] + report["missing_fields"] + report["conflicts"]))
    if not report["blocked"]["details"]:
        report["resolution_status"] = "resolved"
        report["blocked"]["code"] = None
    return report


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--model", required=True)
    parser.add_argument("--framework")
    parser.add_argument("--modelzoo-root", type=Path, default=Path("/home/xuansun/ModelZoo"))
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--test-observation-public-key", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        root = args.modelzoo_root.resolve(strict=True)
        if not root.is_dir() or args.modelzoo_root.is_symlink():
            raise OSError("invalid root")
        report = resolve(root, args.model, args.framework, args.preflight, args.test_observation_public_key)
    except (OSError, ResolutionError) as error:
        root = args.modelzoo_root.absolute()
        report = base_report(root, args.model, args.framework)
        block(report, "blocked_malformed_metadata", "invalid_modelzoo_root")
    print(canonical_json(attach_digest(report)))
    return 0 if report["resolution_status"] == "resolved" else 20


if __name__ == "__main__":
    raise SystemExit(main())
