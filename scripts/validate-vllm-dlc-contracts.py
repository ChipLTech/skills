#!/usr/bin/env python3
"""Validate versioned vLLM-DLC workflow contracts through one read-only CLI."""

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import shlex
import subprocess
import sys
from urllib.parse import unquote, urlsplit
from pathlib import Path
from typing import Any

import yaml
from yaml.resolver import BaseResolver


CONTRACT_VERSION = "vllm-dlc-contract/v1"
DEPENDENCY_QUALIFIER_PATH = Path(__file__).with_name(
    "qualify-vllm-dlc-dependencies.py"
).resolve()
DEPENDENCY_REQUIREMENTS_PATH = Path(
    "/work/skills/requirements-vllm-dlc-contracts.txt"
).resolve()
DEPENDENCY_EXCEPTION_POLICY_PATH = Path(
    "/work/skills/config/vllm-dlc/ticket06-dependency-exceptions.json"
).resolve()
MAIN_TO_MAIN_OPERATIONAL_POLICY_PATH = Path(
    "/work/skills/config/vllm-dlc/ticket06-main-to-main-operational-policy.json"
).resolve()
DEPENDENCY_EXCEPTION = {
    "dependency": "opencv-python-headless",
    "distribution": "vllm",
    "installed_version": "4.11.0.86",
    "rationale": "vllm-dlc requires <=4.11.0.86 to preserve numpy<2",
    "requirement": "opencv-python-headless>=4.13.0",
    "vllm_dlc_requirement": "opencv-python-headless<=4.11.0.86",
}
OPERATIONAL_CAMPAIGN_REQUIRED_IDS = {
    "python", "runner", "validator", "launcher", "tokenizer_builder",
    "smi_adapter", "smi_preflight", "smi_tool", "environment_profile",
    "dependency_qualifier", "dependency_requirements", "dependency_exception_policy",
    "dependency_qualification",
    "vllm_source", "vllm_dlc_source", "smi_source",
    "vllm_snapshot", "vllm_dlc_snapshot",
    "vllm_native", "vllm_dlc_native",
    "model_hosting_container_standards", "ijson",
    "main_to_main_operational_policy",
}


def validate_main_to_main_operational_policy(document: Any) -> bool:
    fields = {
        "alignment_action", "approved", "claim_level", "finalization_intent",
        "manifest_action", "roles", "schema_version", "target",
    }
    target_fields = {"manifest_digest", "vllm_dlc_sha", "vllm_sha"}
    roles = [
        {"role": "deepseek_tp2_operational", "tensor_parallel_size": 2},
        {"role": "llama_tp1_dense_operational", "tensor_parallel_size": 1},
    ]
    if (
        not isinstance(document, dict)
        or set(document) != fields
        or document["schema_version"]
        != "vllm-dlc-main-to-main-operational-policy/v1"
        or document["claim_level"] != "operational_only"
        or document["approved"] is not True
        or document["roles"] != roles
        or document["finalization_intent"] != "none"
        or document["manifest_action"] != "report_only"
        or document["alignment_action"] != "unchanged"
        or not isinstance(document["target"], dict)
        or set(document["target"]) != target_fields
    ):
        return False
    target = document["target"]
    return (
        isinstance(target["vllm_sha"], str)
        and re.fullmatch(SHA_PATTERN, target["vllm_sha"]) is not None
        and isinstance(target["vllm_dlc_sha"], str)
        and re.fullmatch(SHA_PATTERN, target["vllm_dlc_sha"]) is not None
        and isinstance(target["manifest_digest"], str)
        and re.fullmatch(DIGEST_PATTERN, target["manifest_digest"]) is not None
    )


def validate_dependency_exception_policy(path: Path) -> bool:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return document == {
        "exception": DEPENDENCY_EXCEPTION,
        "schema_version": "vllm-dlc-dependency-exception-policy/v1",
    }


def validate_dependency_qualification(
    path: Path, repository_guards: list[str]
) -> bool:
    if (
        not path.is_absolute()
        or not validate_dependency_exception_policy(DEPENDENCY_EXCEPTION_POLICY_PATH)
    ):
        return False
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(document, dict) or set(document) != {
        "compatibility_exceptions",
        "dependencies",
        "imports",
        "metadata_checks",
        "model_started",
        "native_modules",
        "reasons",
        "requirements_path",
        "schema_version",
        "status",
    }:
        return False
    if (
        document["schema_version"] != "vllm-dlc-dependency-qualification/v1"
        or document["status"] != "passed"
        or document["model_started"] is not False
        or document["reasons"] != []
        or not isinstance(document["requirements_path"], str)
        or Path(document["requirements_path"]).resolve()
        != DEPENDENCY_REQUIREMENTS_PATH
    ):
        return False
    dependencies = document["dependencies"]
    imports = document["imports"]
    metadata_checks = document["metadata_checks"]
    native_modules = document["native_modules"]
    if (
        not isinstance(dependencies, list)
        or not dependencies
        or any(
            not isinstance(dependency, dict)
            or set(dependency)
            != {"distribution", "expected_version", "installed_version"}
            or not isinstance(dependency["distribution"], str)
            or not isinstance(dependency["expected_version"], str)
            or dependency["installed_version"] != dependency["expected_version"]
            for dependency in dependencies
        )
        or not isinstance(imports, list)
        or not imports
        or any(
            not isinstance(item, dict)
            or set(item) != {"name", "passed"}
            or not isinstance(item["name"], str)
            or item["passed"] is not True
            for item in imports
        )
        or document["compatibility_exceptions"] != [DEPENDENCY_EXCEPTION]
        or not isinstance(metadata_checks, list)
        or not metadata_checks
        or any(
            not isinstance(check, dict)
            or set(check) != {
                "compatibility_exception", "dependency", "distribution",
                "installed_version", "requirement", "satisfied",
            }
            or check["distribution"] not in {"vllm", "vllm-dlc"}
            or not isinstance(check["dependency"], str)
            or not isinstance(check["requirement"], str)
            or (
                check["installed_version"] is not None
                and not isinstance(check["installed_version"], str)
            )
            or type(check["satisfied"]) is not bool
            or type(check["compatibility_exception"]) is not bool
            or (
                check["compatibility_exception"]
                and {
                    "dependency": check["dependency"],
                    "distribution": check["distribution"],
                    "installed_version": check["installed_version"],
                    "requirement": check["requirement"],
                }
                != {
                    key: DEPENDENCY_EXCEPTION[key]
                    for key in (
                        "dependency", "distribution", "installed_version", "requirement"
                    )
                }
            )
            or (not check["satisfied"] and not check["compatibility_exception"])
            or (check["satisfied"] and check["compatibility_exception"])
            for check in metadata_checks
        )
        or {check["distribution"] for check in metadata_checks} != {"vllm", "vllm-dlc"}
        or sum(check["compatibility_exception"] for check in metadata_checks) != 1
        or not any(
            check == {
                "compatibility_exception": False,
                "dependency": DEPENDENCY_EXCEPTION["dependency"],
                "distribution": "vllm-dlc",
                "installed_version": DEPENDENCY_EXCEPTION["installed_version"],
                "requirement": DEPENDENCY_EXCEPTION["vllm_dlc_requirement"],
                "satisfied": True,
            }
            for check in metadata_checks
        )
        or not isinstance(native_modules, list)
        or not native_modules
    ):
        return False
    guarded_roots = [Path(root).resolve() for root in repository_guards]
    for module in native_modules:
        if (
            not isinstance(module, dict)
            or set(module) != {"expected_root", "name", "origin", "passed"}
            or not isinstance(module["name"], str)
            or not isinstance(module["expected_root"], str)
            or not isinstance(module["origin"], str)
            or module["passed"] is not True
        ):
            return False
        expected_root = Path(module["expected_root"]).resolve()
        if expected_root not in guarded_roots:
            return False
        try:
            Path(module["origin"]).resolve().relative_to(expected_root)
        except ValueError:
            return False
    return True


RUN_SPEC_FIELDS = {
    "artifact_destination",
    "contract_kind",
    "deployment_profile",
    "digest",
    "finalization_intent",
    "gates",
    "hardware",
    "mode",
    "run_id",
    "runtime_policy",
    "schema_version",
    "target",
    "timeouts",
    "workflow",
}
RUN_SPEC_V2_FIELDS = {
    "artifact_destination",
    "assets",
    "claim_level",
    "campaign_digest",
    "campaign_manifest",
    "contract_kind",
    "deployment_profile",
    "digest",
    "finalization_intent",
    "gates",
    "hardware_observation",
    "launch",
    "mode",
    "repository_guards",
    "requests",
    "run_id",
    "schema_version",
    "target",
    "timeouts",
    "workflow",
}
RUN_SPEC_V2_PROFILE_FIELDS = {
    "chunked_prefill_requested",
    "context_limit",
    "device_capacity_mib",
    "dtype",
    "max_num_batched_tokens",
    "model_id",
    "model_revision",
    "pipeline_parallel_size",
    "processor_revision",
    "quantization",
    "real_weights",
    "role",
    "served_model_name",
    "tensor_parallel_size",
    "tokenizer_revision",
    "approval_digest",
    "approval_path",
    "tp_derivation_digest",
    "tp_derivation_path",
}
RUN_SPEC_V2_ASSET_FIELDS = {
    "model_digest",
    "model_path",
    "processor_digest",
    "processor_path",
    "tokenizer_digest",
    "tokenizer_path",
}
RUN_SPEC_V2_LAUNCH_FIELDS = {
    "arguments",
    "environment",
    "executable",
    "executable_digest",
    "provider_class",
    "working_directory",
}
RUN_SPEC_V2_HARDWARE_FIELDS = {
    "adapter_version",
    "executable",
    "executable_digest",
    "provider_class",
    "qualification_executable",
    "qualification_executable_digest",
    "smi_source_root",
    "smi_source_sha",
    "expected_pid_namespace",
    "expected_mount_namespace",
    "required_device_count",
    "sample_points",
    "tool_digest",
    "tool_executable",
}
RUN_SPEC_V2_REQUEST_FIELDS = {
    "id",
    "order",
    "output_token_allowance",
    "payload_digest",
    "role",
    "timeout_class",
}
RUN_SPEC_V2_SHARED_GATES = {
    "artifact_closure",
    "chat_api",
    "completions_api",
    "eager_dlc_configuration_observed",
    "long_prefix_api",
    "long_prefix_threshold_exercised",
    "lifecycle_cleanup",
    "models_api",
    "real_dlc_hardware_operational",
    "repository_state",
    "server_liveness",
    "service_ready",
}
RUN_SPEC_V2_ROLE_GATES = {
    "deepseek_tp2_operational",
    "llama_tp1_dense_operational",
    "model_adaptation_profile_operational",
}
RESULT_EVIDENCE_FIELDS = {
    "acceptance_eligible",
    "artifacts",
    "contract_kind",
    "diagnostics",
    "digest",
    "execution_environment",
    "exit_code",
    "gates",
    "overall_status",
    "run_id",
    "run_spec_digest",
    "schema_version",
}
HANDOFF_FIELDS = {
    "candidate_vllm_dlc_sha",
    "changed_dependency_ids",
    "child_run_id",
    "contract_kind",
    "digest",
    "parent_run_id",
    "result_evidence_digest",
    "schema_version",
    "status",
    "target_vllm_sha",
}
SCHEMAS = {
    "run_spec": ("vllm-dlc-run-spec/v1", RUN_SPEC_FIELDS),
    "result_evidence": (
        "vllm-dlc-result-evidence/v1",
        RESULT_EVIDENCE_FIELDS,
    ),
    "parent_child_handoff": (
        "vllm-dlc-parent-child-handoff/v1",
        HANDOFF_FIELDS,
    ),
}
GATE_STATUSES = {"passed", "failed", "blocked", "not_applicable", "not_verified"}
SHA_PATTERN = r"[0-9a-f]{40}"
DIGEST_PATTERN = r"sha256:[0-9a-f]{64}"
PACKAGE_ROLES = {
    "skill",
    "agent",
    "knowledge",
    "top_level_catalog",
    "engineering_catalog",
    "plugin_manifest",
    "skillhub_manifest",
    "kilo_linker",
    "installation_documentation",
}

CANDIDATE_PACKAGE_ROLES = {"skill", "agent", "knowledge"}
MODEL_ADAPTATION_SCHEMA = "vllm-dlc-model-adaptation-bundle/v1"
MODEL_ADAPTATION_FIELDS = {
    "alignment_claim",
    "capability_matrix",
    "compatibility",
    "execution",
    "handoff",
    "identity",
    "preflight",
    "prior_real_weight_result_evidence",
    "prior_real_weight_run_spec",
    "result_evidence",
    "run_spec",
    "schema_version",
    "tp_decision",
    "workflow",
}
CAPABILITY_IDENTITIES = {
    "text_generation",
    "attention",
    "mla",
    "moe",
    "quantization",
    "multimodal",
    "distributed",
    "mtp",
    "tokenizer",
    "processor",
    "model_specific",
}
PREFLIGHT_FIELDS = {
    "artifact_destination",
    "available_device_count",
    "chunk_observability_available",
    "contract_available",
    "current_branch",
    "dispatch_observability_available",
    "hardware_required",
    "model_path",
    "model_revision",
    "processor_required",
    "processor_revision",
    "read_only_boundary_preserved",
    "required_branch",
    "required_device_count",
    "required_execution_path_supported",
    "tokenizer_revision",
    "weights_evidence",
}
TP_DECISION_FIELDS = {
    "capacity_evidence",
    "config_evidence",
    "deployment_evidence",
    "dtype",
    "quantization",
    "tensor_parallel_size",
    "weights_evidence",
}
COMPATIBILITY_FIELDS = {"changed", "changed_dependency_ids"}
EXECUTION_FIELDS = {
    "dummy_acceptance_eligible",
    "dummy_approved",
    "dummy_mode",
    "dummy_requested",
    "real_weight_failure_reference",
    "result_acceptance_eligible",
    "result_environment",
    "result_reference",
    "result_status",
    "runner_requested",
}
IDENTITY_FIELDS = {
    "expected_deployment_digest",
    "expected_model_id",
    "expected_model_revision",
    "expected_processor_revision",
    "expected_tokenizer_revision",
    "parent_run_id",
}
MAIN_TO_MAIN_SCHEMA = "vllm-dlc-main-to-main-bundle/v1"
MAIN_TO_MAIN_FIELDS = {
    "assignments",
    "baseline",
    "candidate_vllm_dlc_sha",
    "child_bundles",
    "claims",
    "delta",
    "freeze",
    "history",
    "manifest_impact",
    "parent_run_id",
    "preflight",
    "regression_policy",
    "schema_version",
    "target",
    "workflow",
}
MAIN_TO_MAIN_CLAIM_FIELDS = {
    "alignment_action",
    "finalize_action",
    "manifest_action",
}
MAIN_TO_MAIN_TARGET_FIELDS = {"lineage_tag", "vllm_sha"}
MAIN_TO_MAIN_PREFLIGHT_FIELDS = {
    "assets_available",
    "branch_matches_main",
    "contract_available",
    "current_branch",
    "hardware_available",
    "observability_available",
    "read_only_boundary_preserved",
    "required_branch",
    "target_available",
}
MAIN_TO_MAIN_BASELINE_FIELDS = {"candidates", "selected_candidate_id", "state"}
MAIN_TO_MAIN_BASELINE_CANDIDATE_FIELDS = {
    "evidence_digest",
    "id",
    "mandatory_evidence_complete",
    "revalidation_status",
    "source",
    "upstream_sha",
    "verified_alignment",
}
BASELINE_SOURCE_ORDER = (
    "historical_evidence",
    "explicit_git_pin",
    "correlated_candidate",
    "checkout_clue",
    "installation_clue",
    "readme_clue",
)
MAIN_TO_MAIN_HISTORY_FIELDS = {
    "complete",
    "discovered_changed_surface_count",
    "range_end_sha",
    "range_evidence_digest",
    "range_start_sha",
}
MAIN_TO_MAIN_DELTA_FIELDS = {
    "declared_changed_surface_count",
    "declared_unknown_impact_count",
    "surfaces",
}
MAIN_TO_MAIN_DELTA_ROW_FIELDS = {
    "classification",
    "dependency_id",
    "evidence",
    "id",
}
DELTA_CLASSIFICATIONS = {
    "affected_dependency",
    "confirmed_irrelevant",
    "new_dependency_candidate",
}
MAIN_TO_MAIN_MANIFEST_FIELDS = {
    "applied_changes",
    "future_changes",
    "manifest_digest",
    "modified",
    "read_only",
}
MAIN_TO_MAIN_MANIFEST_ROW_FIELDS = {"action", "dependency_id", "reason"}
MANIFEST_ACTIONS = {"future_add", "future_update", "future_remove", "no_change"}
MAIN_TO_MAIN_ASSIGNMENT_FIELDS = {
    "assignment_id",
    "child_run_id",
    "deployment_digest",
    "expected_dependency_ids",
    "hardware_class",
    "mandatory",
    "mode",
    "model_id",
    "model_revision",
    "processor_revision",
    "real_weights_required",
    "role",
    "tensor_parallel_size",
    "tokenizer_revision",
}
MAIN_TO_MAIN_CHILD_FIELDS = {"assignment_id", "model_adaptation_bundle"}
MAIN_TO_MAIN_FREEZE_FIELDS = {
    "commit_authorized",
    "commit_required",
    "evidence_stale",
    "tested_revision_unique",
}
MAIN_TO_MAIN_REGRESSION_POLICY_FIELDS = {"digest", "schema_version", "status"}
CANDIDATE_BOUNDARY_TERMS = {
    "model-adaptation": {
        "specific", "incompatible", "attention", "mla", "moe", "quantization",
        "multimodal", "mtp", "distributed", "upstream alignment", "environment rebuild",
        "single-operator", "compile", "smoke-only", "main-to-main",
    },
    "main-to-main-upgrade": {
        "upstream", "full sha", "verified vllm alignment", "baseline", "affected dependency",
        "new dependency candidate", "confirmed irrelevant", "unknown impact", "manifest",
        "deepseek", "tp=2", "llama", "tp=1", "model adaptation", "no-finalize",
        "standalone model adaptation", "environment rebuild", "single-operator", "compile",
        "release branch", "smoke-only",
    },
}
KNOWLEDGE_PACKAGE_SCHEMA = "vllm-dlc-knowledge-package/v1"
PROMPT_DRY_RUN_SCHEMA = "vllm-dlc-prompt-dry-run/v1"
REUSABLE_PROMPT_SCHEMA = "vllm-dlc-reusable-prompt/v1"
KNOWLEDGE_DOCUMENT_ROLES = {
    "entry_point",
    "decision_record",
    "model_adaptation_prompt",
    "main_to_main_prompt",
}
PROMPT_ROLES = {"model_adaptation_prompt", "main_to_main_prompt"}
REQUIRED_KNOWLEDGE_LINKS = {
    ("entry_point", "decision_record"),
    ("entry_point", "model_adaptation_prompt"),
    ("entry_point", "main_to_main_prompt"),
}
PROMPT_FIELDS = {
    "prompt_schema",
    "skill_identity",
    "shared_contract",
    "required_inputs",
    "missing_input_status",
    "missing_input_reason",
    "hardware_evidence",
}
PROMPT_PROFILES = {
    "model_adaptation_prompt": {
        "skill_identity": "model-adaptation",
        "missing_input_reason": "blocked_missing_asset",
        "required_inputs": (
            "model_id", "model_revision", "tokenizer_revision", "processor_revision",
            "target_vllm_full_sha", "candidate_vllm_dlc_full_sha", "deployment_profile",
            "model_assets", "hardware_requirement", "available_device_count",
            "manifest_dependency_identity", "artifact_destination",
        ),
        "body_terms": (
            "特定模型", "blocked_missing_asset", "blocked_missing_hardware",
            "diagnostic-only", "verified vllm alignment", "not_verified",
        ),
    },
    "main_to_main_prompt": {
        "skill_identity": "main-to-main-upgrade",
        "missing_input_reason": "blocked_missing_target",
        "required_inputs": (
            "target_vllm_full_sha", "lineage_tag", "guarded_repository_snapshot",
            "baseline_candidates", "history_range_evidence", "changed_surface_inventory",
            "unresolved_impact_state", "manifest_impact_identity", "regression_policy_state",
            "deepseek_tp2_assignment", "llama_tp1_assignment", "model_adaptation_handoffs",
            "artifact_evidence_references", "commit_authorization_state",
        ),
        "body_terms": (
            "exact upstream", "blocked_missing_target", "report-only", "no-finalize",
            "ticket 03", "tp=2", "tp=1", "not_verified",
        ),
    },
}
EVIDENCE_CLASSES = (
    "Static validation",
    "Fake-server validation",
    "Dummy diagnostics",
    "DLCsim evidence",
    "Real-weight evidence",
    "Real DLC Hardware acceptance",
)


class ArgumentErrorParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def construct_unique_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(BaseResolver.DEFAULT_MAPPING_TAG, construct_unique_mapping)


def bootstrap_guard_root(arguments: list[str]) -> Path | None:
    root = None
    for index, argument in enumerate(arguments):
        if argument == "--vllm-dlc-root" and index + 1 < len(arguments):
            root = Path(arguments[index + 1])
        if argument.startswith("--vllm-dlc-root="):
            root = Path(argument.split("=", 1)[1])
    return root
REQUIRED_FIELDS = {
    "run_spec": RUN_SPEC_FIELDS,
    "result_evidence": RESULT_EVIDENCE_FIELDS,
    "parent_child_handoff": HANDOFF_FIELDS,
}
NESTED_FIELDS = {
    "run_spec": {
        "target": {"vllm_sha", "vllm_dlc_sha", "manifest_digest"},
        "deployment_profile": {
            "model_id", "model_revision", "tokenizer_revision", "processor_revision",
            "tensor_parallel_size", "pipeline_parallel_size", "dtype", "quantization",
            "context_limit", "max_num_batched_tokens", "chunked_prefill",
            "served_model_name", "real_weights",
        },
        "hardware": {"class", "device_count", "required"},
        "timeouts": {"startup_seconds", "request_seconds", "long_prefix_seconds"},
        "runtime_policy": {"execution", "triton_execution", "compile_execution"},
    }
}


def repository_snapshot(root: Path) -> dict[str, str]:
    def git(*arguments: str) -> str:
        return subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.rstrip("\n")

    status_process = subprocess.run(
        ["git", "-C", str(root), "-c", "core.quotePath=false", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        check=True,
        capture_output=True,
    )
    status_entries = [entry for entry in status_process.stdout.split(b"\0") if entry]
    status = "\n".join(
        entry.decode("utf-8", errors="backslashreplace") for entry in status_entries
    )
    tracked_diff = subprocess.run(
        ["git", "-C", str(root), "diff", "--binary"],
        check=True,
        capture_output=True,
    ).stdout
    index_diff = subprocess.run(
        ["git", "-C", str(root), "diff", "--binary", "--cached"],
        check=True,
        capture_output=True,
    ).stdout
    untracked_paths = [entry[3:] for entry in status_entries if entry.startswith(b"?? ")]
    untracked = hashlib.sha256()
    for relative_path in sorted(untracked_paths):
        path = os.path.join(os.fsencode(root), relative_path)
        untracked.update(relative_path)
        untracked.update(b"\0")
        if os.path.islink(path):
            untracked.update(b"symlink\0")
            target = os.readlink(path)
            untracked.update(target if isinstance(target, bytes) else os.fsencode(target))
        else:
            untracked.update(b"file\0")
            with open(path, "rb") as untracked_file:
                untracked.update(untracked_file.read())
        untracked.update(b"\0")
    return {
        "branch": git("branch", "--show-current"),
        "head": git("rev-parse", "HEAD"),
        "status": status,
        "status_digest": f"sha256:{hashlib.sha256(status_process.stdout).hexdigest()}",
        "tracked_diff_digest": f"sha256:{hashlib.sha256(tracked_diff).hexdigest()}",
        "index_diff_digest": f"sha256:{hashlib.sha256(index_diff).hexdigest()}",
        "untracked_content_digest": f"sha256:{untracked.hexdigest()}",
    }


def emit(report: dict[str, Any]) -> None:
    print(
        json.dumps(
            report,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def canonical_digest(document: dict[str, Any]) -> str:
    payload = {key: value for key, value in document.items() if key != "digest"}
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def validate_model_adaptation_derivation(
    run_spec: dict[str, Any],
) -> dict[str, str] | None:
    def error(code: str, path: str) -> dict[str, str]:
        return {"code": code, "path": path, "status": "failed"}

    profile = run_spec["deployment_profile"]
    assets = run_spec["assets"]
    documents = {}
    for name in ("approval", "tp_derivation"):
        path = Path(profile[f"{name}_path"])
        try:
            payload = path.read_bytes()
            document = json.loads(payload)
        except (OSError, json.JSONDecodeError):
            return error("artifact.invalid", f"$.deployment_profile.{name}_path")
        if f"sha256:{hashlib.sha256(payload).hexdigest()}" != profile[f"{name}_digest"]:
            return error("artifact.digest_mismatch", f"$.deployment_profile.{name}_digest")
        if not isinstance(document, dict):
            return error("contract.invalid_type", f"$.deployment_profile.{name}_path")
        documents[name] = document

    approval = documents["approval"]
    approval_fields = {
        "approved",
        "model_id",
        "model_path",
        "role",
        "schema_version",
        "tensor_parallel_size",
    }
    unknown = sorted(set(approval) - approval_fields)
    missing = sorted(approval_fields - set(approval))
    if unknown:
        return error("contract.unknown_field", f"$.approval.{unknown[0]}")
    if missing:
        return error("contract.missing_required_field", f"$.approval.{missing[0]}")
    if (
        approval["schema_version"] != "vllm-dlc-model-adaptation-approval/v1"
        or approval["approved"] is not True
        or approval["role"] != "model_adaptation_profile_operational"
        or type(approval["tensor_parallel_size"]) is not int
        or approval["tensor_parallel_size"] <= 0
    ):
        return error("contract.invalid_value", "$.approval")
    if any(
        approval[field] != expected
        for field, expected in (
            ("model_id", profile["model_id"]),
            ("model_path", assets["model_path"]),
            ("role", profile["role"]),
            ("tensor_parallel_size", profile["tensor_parallel_size"]),
        )
    ):
        return error("contract.identity_mismatch", "$.approval")

    derivation = documents["tp_derivation"]
    derivation_fields = {
        "capacity_utilization_limit_bps",
        "config_digest",
        "config_hidden_size",
        "config_model_type",
        "config_path",
        "device_capacity_mib",
        "dtype",
        "model_asset_bytes",
        "model_digest",
        "model_id",
        "model_path",
        "quantization",
        "required_capacity_mib",
        "result_tensor_parallel_size",
        "schema_version",
        "target",
    }
    unknown = sorted(set(derivation) - derivation_fields)
    missing = sorted(derivation_fields - set(derivation))
    if unknown:
        return error("contract.unknown_field", f"$.tp_derivation.{unknown[0]}")
    if missing:
        return error("contract.missing_required_field", f"$.tp_derivation.{missing[0]}")
    if derivation["schema_version"] != "vllm-dlc-tp-derivation/v1":
        return error("contract.unsupported_schema_version", "$.tp_derivation.schema_version")
    if (
        type(derivation["capacity_utilization_limit_bps"]) is not int
        or derivation["capacity_utilization_limit_bps"] != 9000
        or not isinstance(derivation["config_model_type"], str)
        or not derivation["config_model_type"].strip()
        or type(derivation["config_hidden_size"]) is not int
        or derivation["config_hidden_size"] <= 0
        or type(derivation["device_capacity_mib"]) is not int
        or derivation["device_capacity_mib"] <= 0
        or type(derivation["required_capacity_mib"]) is not int
        or derivation["required_capacity_mib"] <= 0
        or type(derivation["result_tensor_parallel_size"]) is not int
        or derivation["result_tensor_parallel_size"] <= 0
    ):
        return error("contract.invalid_value", "$.tp_derivation")
    if any(
        derivation[field] != expected
        for field, expected in (
            ("model_id", profile["model_id"]),
            ("model_path", assets["model_path"]),
            ("model_digest", assets["model_digest"]),
            ("dtype", profile["dtype"]),
            ("quantization", profile["quantization"]),
            ("device_capacity_mib", profile["device_capacity_mib"]),
            ("target", run_spec["target"]),
            ("result_tensor_parallel_size", profile["tensor_parallel_size"]),
        )
    ):
        return error("contract.identity_mismatch", "$.tp_derivation")

    model_path = Path(assets["model_path"])
    if (
        not isinstance(derivation["config_path"], str)
        or not Path(derivation["config_path"]).is_absolute()
    ):
        return error("contract.invalid_value", "$.tp_derivation.config_path")
    config_path = Path(derivation["config_path"])
    if (
        config_path.is_symlink()
        or not config_path.is_file()
        or model_path.resolve() not in config_path.resolve().parents
    ):
        return error("contract.invalid_value", "$.tp_derivation.config_path")
    try:
        config_payload = config_path.read_bytes()
        config = json.loads(config_payload)
        config_digest = f"sha256:{hashlib.sha256(config_payload).hexdigest()}"
        model_digest = canonical_asset_digest(model_path)
        model_asset_bytes = sum(
            candidate.stat().st_size
            for candidate in model_path.rglob("*")
            if candidate.is_file()
            and not candidate.is_symlink()
            and candidate.suffix.lower() in {".bin", ".gguf", ".pt", ".pth", ".safetensors"}
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return error("artifact.missing", "$.assets.model_path")
    if (
        not isinstance(config, dict)
        or not isinstance(config.get("model_type"), str)
        or not config["model_type"].strip()
        or type(config.get("hidden_size")) is not int
        or config["hidden_size"] <= 0
    ):
        return error("contract.invalid_value", "$.tp_derivation.config_path")
    required_capacity_mib = (
        model_asset_bytes * 10000
        + derivation["capacity_utilization_limit_bps"] * 2**20
        - 1
    ) // (derivation["capacity_utilization_limit_bps"] * 2**20)
    expected_tensor_parallel_size = (
        required_capacity_mib + derivation["device_capacity_mib"] - 1
    ) // derivation["device_capacity_mib"]
    if (
        derivation["config_digest"] != config_digest
        or derivation["config_model_type"] != config["model_type"]
        or derivation["config_hidden_size"] != config["hidden_size"]
        or derivation["model_digest"] != model_digest
        or type(derivation["model_asset_bytes"]) is not int
        or derivation["model_asset_bytes"] <= 0
        or derivation["model_asset_bytes"] != model_asset_bytes
    ):
        return error("artifact.digest_mismatch", "$.tp_derivation")
    if derivation["required_capacity_mib"] != required_capacity_mib:
        return error("contract.invalid_value", "$.tp_derivation.required_capacity_mib")
    if derivation["result_tensor_parallel_size"] != expected_tensor_parallel_size:
        return error(
            "contract.invalid_value", "$.tp_derivation.result_tensor_parallel_size"
        )
    return None


def validate_run_spec_v2(
    document: dict[str, Any], guarded_root: Path
) -> dict[str, str]:
    def error(code: str, path: str) -> dict[str, str]:
        return {"code": code, "path": path, "status": "failed"}

    unknown = sorted(set(document) - RUN_SPEC_V2_FIELDS)
    if unknown:
        return error("contract.unknown_field", f"$.{unknown[0]}")
    missing = sorted(RUN_SPEC_V2_FIELDS - set(document))
    if missing:
        return error("contract.missing_required_field", f"$.{missing[0]}")
    if document.get("contract_kind") != "run_spec":
        return error("contract.invalid_value", "$.contract_kind")
    if document.get("claim_level") != "operational_only":
        return error("contract.invalid_value", "$.claim_level")
    if document.get("finalization_intent") != "none":
        return error("contract.invalid_value", "$.finalization_intent")
    if document.get("mode") not in {"diagnostic_only", "operational_regression"}:
        return error("contract.invalid_value", "$.mode")
    if document.get("workflow") not in {"model_adaptation", "main_to_main"}:
        return error("contract.invalid_value", "$.workflow")
    if not isinstance(document.get("run_id"), str) or not document["run_id"]:
        return error("contract.invalid_value", "$.run_id")

    exact_objects = (
        ("assets", RUN_SPEC_V2_ASSET_FIELDS),
        ("deployment_profile", RUN_SPEC_V2_PROFILE_FIELDS),
        ("hardware_observation", RUN_SPEC_V2_HARDWARE_FIELDS),
        ("launch", RUN_SPEC_V2_LAUNCH_FIELDS),
        ("target", {"manifest_digest", "vllm_dlc_sha", "vllm_sha"}),
        ("timeouts", {"long_prefix_seconds", "request_seconds", "startup_seconds"}),
    )
    for field, expected in exact_objects:
        value = document.get(field)
        if not isinstance(value, dict):
            return error("contract.invalid_type", f"$.{field}")
        nested_unknown = sorted(set(value) - expected)
        if nested_unknown:
            return error("contract.unknown_field", f"$.{field}.{nested_unknown[0]}")
        nested_missing = sorted(expected - set(value))
        if nested_missing:
            return error(
                "contract.missing_required_field",
                f"$.{field}.{nested_missing[0]}",
            )

    target = document["target"]
    for field in ("vllm_sha", "vllm_dlc_sha"):
        if not isinstance(target[field], str) or not re.fullmatch(SHA_PATTERN, target[field]):
            return error("contract.missing_identity", f"$.target.{field}")
    if not isinstance(target["manifest_digest"], str) or not re.fullmatch(
        DIGEST_PATTERN, target["manifest_digest"]
    ):
        return error("contract.invalid_value", "$.target.manifest_digest")

    profile = document["deployment_profile"]
    if profile["role"] not in RUN_SPEC_V2_ROLE_GATES:
        return error("contract.invalid_value", "$.deployment_profile.role")
    for field in ("model_id", "served_model_name", "dtype", "quantization"):
        if not isinstance(profile[field], str) or not profile[field]:
            return error("contract.invalid_value", f"$.deployment_profile.{field}")
    for field in ("model_revision", "tokenizer_revision"):
        if profile[field] is not None and (
            not isinstance(profile[field], str)
            or not re.fullmatch(SHA_PATTERN, profile[field])
        ):
            return error("contract.missing_identity", f"$.deployment_profile.{field}")
    if profile["processor_revision"] is not None and (
        not isinstance(profile["processor_revision"], str)
        or not re.fullmatch(SHA_PATTERN, profile["processor_revision"])
    ):
        return error("contract.missing_identity", "$.deployment_profile.processor_revision")
    for field in (
        "context_limit",
        "device_capacity_mib",
        "max_num_batched_tokens",
        "pipeline_parallel_size",
        "tensor_parallel_size",
    ):
        if type(profile[field]) is not int or profile[field] <= 0:
            return error("contract.invalid_value", f"$.deployment_profile.{field}")
    for field in ("chunked_prefill_requested", "real_weights"):
        if type(profile[field]) is not bool:
            return error("contract.invalid_value", f"$.deployment_profile.{field}")
    for field in ("approval", "tp_derivation"):
        value = profile[f"{field}_digest"]
        path_value = profile[f"{field}_path"]
        if profile["role"] == "model_adaptation_profile_operational":
            if (
                not isinstance(value, str)
                or not re.fullmatch(DIGEST_PATTERN, value)
                or not isinstance(path_value, str)
                or not Path(path_value).is_absolute()
            ):
                return error("contract.missing_identity", f"$.deployment_profile.{field}_digest")
        elif (path_value, value) != (None, None):
            return error("contract.inconsistent_status", f"$.deployment_profile.{field}_digest")
    role_tp = {
        "deepseek_tp2_operational": 2,
        "llama_tp1_dense_operational": 1,
    }
    if profile["role"] in role_tp and profile["tensor_parallel_size"] != role_tp[profile["role"]]:
        return error("contract.inconsistent_status", "$.deployment_profile.tensor_parallel_size")

    assets = document["assets"]
    for field in ("model_path", "tokenizer_path"):
        if not isinstance(assets[field], str) or not Path(assets[field]).is_absolute():
            return error("contract.invalid_value", f"$.assets.{field}")
    for field in ("model_digest", "tokenizer_digest"):
        if not isinstance(assets[field], str) or not re.fullmatch(DIGEST_PATTERN, assets[field]):
            return error("contract.invalid_value", f"$.assets.{field}")
    processor_pair = (assets["processor_path"], assets["processor_digest"])
    if processor_pair != (None, None) and (
        not isinstance(processor_pair[0], str)
        or not Path(processor_pair[0]).is_absolute()
        or not isinstance(processor_pair[1], str)
        or not re.fullmatch(DIGEST_PATTERN, processor_pair[1])
    ):
        return error("contract.invalid_value", "$.assets.processor_path")
    if document["mode"] == "operational_regression" and processor_pair != (None, None):
        return error("contract.invalid_value", "$.assets.processor_path")
    if (
        document["mode"] == "operational_regression"
        and profile["processor_revision"] is not None
    ):
        return error("contract.invalid_value", "$.deployment_profile.processor_revision")
    if profile["role"] == "model_adaptation_profile_operational":
        derivation_error = validate_model_adaptation_derivation(document)
        if derivation_error:
            return derivation_error

    launch = document["launch"]
    hardware = document["hardware_observation"]
    for field, value in (("launch", launch), ("hardware_observation", hardware)):
        if value["provider_class"] not in {"fixture", "local_process"}:
            return error("contract.invalid_value", f"$.{field}.provider_class")
        if not isinstance(value["executable"], str) or not Path(value["executable"]).is_absolute():
            return error("contract.invalid_value", f"$.{field}.executable")
        if not isinstance(value["executable_digest"], str) or not re.fullmatch(
            DIGEST_PATTERN, value["executable_digest"]
        ):
            return error("contract.invalid_value", f"$.{field}.executable_digest")
    if document["mode"] == "operational_regression" and (
        launch["provider_class"] != "local_process"
        or hardware["provider_class"] != "local_process"
        or profile["real_weights"] is not True
    ):
        return error("contract.inconsistent_status", "$.mode")
    campaign_pair = (document["campaign_manifest"], document["campaign_digest"])
    if document["mode"] == "operational_regression":
        if (
            not isinstance(campaign_pair[0], str)
            or not Path(campaign_pair[0]).is_absolute()
            or not isinstance(campaign_pair[1], str)
            or not re.fullmatch(DIGEST_PATTERN, campaign_pair[1])
        ):
            return error("contract.invalid_value", "$.campaign_manifest")
    elif campaign_pair != (None, None):
        return error("contract.inconsistent_status", "$.campaign_manifest")
    if document["mode"] == "operational_regression":
        launcher_adapter = Path(__file__).with_name("launch-vllm-dlc-server.py").resolve()
        smi_adapter = Path(__file__).with_name("observe-cltech-smi.py").resolve()
        if (
            not launch["arguments"]
            or Path(launch["arguments"][0]).resolve() != launcher_adapter
            or Path(hardware["executable"]).resolve() != smi_adapter
            or Path(launch["executable"]).resolve() != Path(sys.executable).resolve()
        ):
            return error("contract.invalid_value", "$.launch.provider_class")
        ready_file = next(
            (
                launch["arguments"][index + 1]
                for index, value in enumerate(launch["arguments"][:-1])
                if value == "--ready-file"
            ),
            None,
        )
        port = next(
            (
                launch["arguments"][index + 1]
                for index, value in enumerate(launch["arguments"][:-1])
                if value == "--port"
            ),
            None,
        )
        expected_arguments = [
            str(launcher_adapter),
            "--ready-file", ready_file,
            "--host", "127.0.0.1",
            "--port", port,
            "--model", assets["model_path"],
            "--tokenizer", assets["tokenizer_path"],
            "--served-model-name", profile["served_model_name"],
            "--tensor-parallel-size", str(profile["tensor_parallel_size"]),
            "--pipeline-parallel-size", str(profile["pipeline_parallel_size"]),
            "--dtype", profile["dtype"],
            "--quantization", profile["quantization"],
            "--max-model-len", str(profile["context_limit"]),
            "--max-num-batched-tokens", str(profile["max_num_batched_tokens"]),
            "--enforce-eager",
            "--expected-vllm-root", document["repository_guards"][0],
            "--expected-vllm-dlc-root", document["repository_guards"][1],
        ]
        if (
            ready_file is None
            or port is None
            or not port.isdigit()
            or not 1 <= int(port) <= 65535
            or launch["arguments"] != expected_arguments
        ):
            return error("contract.identity_mismatch", "$.launch.arguments")
        model_name = profile["model_id"].lower()
        if profile["role"] == "deepseek_tp2_operational" and "deepseek" not in model_name:
            return error("contract.identity_mismatch", "$.deployment_profile.model_id")
        if profile["role"] == "llama_tp1_dense_operational" and "llama" not in model_name:
            return error("contract.identity_mismatch", "$.deployment_profile.model_id")
    if document["mode"] == "diagnostic_only" and not (
        launch["provider_class"] == "fixture"
        and hardware["provider_class"] == "fixture"
    ):
        return error("contract.inconsistent_status", "$.mode")
    tool_pair = (hardware["tool_executable"], hardware["tool_digest"])
    if hardware["provider_class"] == "local_process":
        if (
            not isinstance(tool_pair[0], str)
            or not Path(tool_pair[0]).is_absolute()
            or not isinstance(tool_pair[1], str)
            or not re.fullmatch(DIGEST_PATTERN, tool_pair[1])
        ):
            return error("contract.invalid_value", "$.hardware_observation.tool_executable")
        qualification_values = (
            hardware["qualification_executable"],
            hardware["qualification_executable_digest"],
            hardware["smi_source_root"],
            hardware["smi_source_sha"],
            hardware["expected_pid_namespace"],
            hardware["expected_mount_namespace"],
        )
        qualification_adapter = Path(__file__).with_name(
            "qualify-vllm-dlc-smi-environment.py"
        ).resolve()
        if (
            not isinstance(qualification_values[0], str)
            or not Path(qualification_values[0]).is_absolute()
            or not isinstance(qualification_values[1], str)
            or not re.fullmatch(DIGEST_PATTERN, qualification_values[1])
            or not isinstance(qualification_values[2], str)
            or not Path(qualification_values[2]).is_absolute()
            or not isinstance(qualification_values[3], str)
            or not re.fullmatch(SHA_PATTERN, qualification_values[3])
            or not isinstance(qualification_values[4], str)
            or not re.fullmatch(r"pid:\[[0-9]+\]", qualification_values[4])
            or not isinstance(qualification_values[5], str)
            or not re.fullmatch(r"mnt:\[[0-9]+\]", qualification_values[5])
            or Path(qualification_values[0]).resolve() != qualification_adapter
        ):
            return error("contract.invalid_value", "$.hardware_observation.qualification_executable")
    elif tool_pair != (None, None):
        return error("contract.inconsistent_status", "$.hardware_observation.tool_executable")
    elif any(hardware[field] is not None for field in (
        "qualification_executable", "qualification_executable_digest",
        "smi_source_root", "smi_source_sha", "expected_pid_namespace",
        "expected_mount_namespace",
    )):
        return error("contract.inconsistent_status", "$.hardware_observation.qualification_executable")
    if not isinstance(launch["arguments"], list) or any(
        not isinstance(value, str) for value in launch["arguments"]
    ):
        return error("contract.invalid_value", "$.launch.arguments")
    if not isinstance(launch["environment"], dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in launch["environment"].items()
    ):
        return error("contract.invalid_value", "$.launch.environment")
    if document["mode"] == "operational_regression":
        if set(launch["environment"]) != {
            "DLC_VISIBLE_DEVICES",
            "DLC_SYN_COPY_ASYNC",
        }:
            return error("contract.invalid_value", "$.launch.environment")
        if launch["environment"]["DLC_SYN_COPY_ASYNC"] != "O2":
            return error("contract.invalid_value", "$.launch.environment")
        visible_devices = launch["environment"]["DLC_VISIBLE_DEVICES"]
        if not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:,(?:0|[1-9][0-9]*))*", visible_devices):
            return error("contract.invalid_value", "$.launch.environment")
        devices = visible_devices.split(",")
        if (
            len(devices) != len(set(devices))
            or len(devices) != profile["tensor_parallel_size"]
        ):
            return error("contract.invalid_value", "$.launch.environment")
    if not isinstance(launch["working_directory"], str) or not Path(
        launch["working_directory"]
    ).is_absolute():
        return error("contract.invalid_value", "$.launch.working_directory")
    if (
        document["mode"] == "operational_regression"
        and Path(launch["working_directory"]).resolve()
        != Path(document["repository_guards"][0]).resolve()
    ):
        return error("contract.invalid_value", "$.launch.working_directory")
    if not isinstance(hardware["adapter_version"], str) or not hardware["adapter_version"]:
        return error("contract.invalid_value", "$.hardware_observation.adapter_version")
    if type(hardware["required_device_count"]) is not int or hardware["required_device_count"] <= 0:
        return error("contract.invalid_value", "$.hardware_observation.required_device_count")
    if hardware["required_device_count"] != profile["tensor_parallel_size"]:
        return error("contract.identity_mismatch", "$.hardware_observation.required_device_count")
    if hardware["sample_points"] != [
        "before_launch",
        "after_ready",
        "during_request",
        "after_cleanup",
    ]:
        return error("contract.invalid_value", "$.hardware_observation.sample_points")

    requests = document.get("requests")
    if not isinstance(requests, list) or len(requests) != 4:
        return error("contract.invalid_value", "$.requests")
    expected_roles = ["models", "completion", "chat", "long_prefix"]
    for index, request in enumerate(requests):
        if not isinstance(request, dict) or set(request) != RUN_SPEC_V2_REQUEST_FIELDS:
            return error("contract.invalid_value", f"$.requests[{index}]")
        if request["role"] != expected_roles[index] or request["order"] != index + 1:
            return error("contract.invalid_value", f"$.requests[{index}].role")
        if not isinstance(request["id"], str) or not request["id"]:
            return error("contract.invalid_value", f"$.requests[{index}].id")
        if request["timeout_class"] != (
            "long_prefix" if request["role"] == "long_prefix" else "request"
        ):
            return error("contract.invalid_value", f"$.requests[{index}].timeout_class")
        if type(request["output_token_allowance"]) is not int or request["output_token_allowance"] < 0:
            return error("contract.invalid_value", f"$.requests[{index}].output_token_allowance")
        if not isinstance(request["payload_digest"], str) or not re.fullmatch(
            DIGEST_PATTERN, request["payload_digest"]
        ):
            return error("contract.invalid_value", f"$.requests[{index}].payload_digest")
    if len({request["id"] for request in requests}) != len(requests):
        return error("contract.invalid_value", "$.requests")

    gates = document.get("gates")
    expected_gates = RUN_SPEC_V2_SHARED_GATES | {profile["role"]}
    if (
        not isinstance(gates, list)
        or len(gates) != len(set(gates))
        or set(gates) != expected_gates
    ):
        return error("contract.inconsistent_status", "$.gates")
    for field, value in document["timeouts"].items():
        if type(value) is not int or value <= 0:
            return error("contract.invalid_value", f"$.timeouts.{field}")
    guards = document.get("repository_guards")
    if (
        not isinstance(guards, list)
        or guards != ["/work/vllm", "/work/vllm-dlc"]
    ):
        return error("contract.invalid_value", "$.repository_guards")
    destination = document.get("artifact_destination")
    if not isinstance(destination, str) or not Path(destination).is_absolute():
        return error("contract.invalid_value", "$.artifact_destination")
    resolved_destination = Path(destination).resolve()
    if any(
        resolved_destination == Path(root).resolve()
        or Path(root).resolve() in resolved_destination.parents
        for root in guards
    ):
        return error("contract.read_only_destination", "$.artifact_destination")
    if document.get("digest") != canonical_digest(document):
        return error("contract.digest_mismatch", "$.digest")
    return {"code": "contract.valid", "status": "passed"}


def validate_operational_result_reference(
    reference_file: Path, guarded_root: Path
) -> tuple[dict[str, str], dict[str, Any]]:
    def failure(code: str, path: str) -> tuple[dict[str, str], dict[str, Any]]:
        return {"code": code, "path": path, "status": "failed"}, {}

    reference = json.loads(reference_file.read_text(encoding="utf-8"))
    if not isinstance(reference, dict) or set(reference) != {
        "digest",
        "schema_version",
        "uri",
    }:
        return failure("operational_reference.invalid", "$")
    if reference["schema_version"] != "vllm-dlc-result-reference/v2":
        return failure("contract.unsupported_schema_version", "$.schema_version")
    if not isinstance(reference["digest"], str) or not re.fullmatch(
        DIGEST_PATTERN, reference["digest"]
    ):
        return failure("contract.invalid_value", "$.digest")
    parsed = urlsplit(reference["uri"])
    if parsed.scheme != "file" or parsed.netloc or parsed.query or parsed.fragment:
        return failure("artifact.invalid_uri", "$.uri")
    result_path = Path(unquote(parsed.path))
    if not result_path.is_absolute() or result_path.is_symlink():
        return failure("artifact.invalid_path", "$.uri")
    run_root = result_path.parent.resolve()
    if result_path.resolve().parent != run_root or not result_path.is_file():
        return failure("artifact.missing", "$.uri")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result_fields = {
        "acceptance_eligible",
        "artifacts",
        "authoritativeness",
        "completion_eligible",
        "contract_kind",
        "diagnostics",
        "digest",
        "evidence_class",
        "exit_code",
        "gates",
        "overall_status",
        "run_id",
        "run_spec_digest",
        "schema_version",
    }
    if not isinstance(result, dict) or set(result) != result_fields:
        return failure("operational_result.invalid", "$")
    if (
        result["schema_version"] != "vllm-dlc-result-evidence/v2"
        or result["contract_kind"] != "result_evidence"
        or result["authoritativeness"] != "operational_only"
        or result["acceptance_eligible"] is not False
        or type(result["completion_eligible"]) is not bool
        or type(result["exit_code"]) is not int
    ):
        return failure("operational_result.invalid", "$")
    if result["digest"] != canonical_digest(result) or result["digest"] != reference["digest"]:
        return failure("contract.digest_mismatch", "$.digest")

    artifacts = result["artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        return failure("artifact.missing", "$.artifacts")
    artifact_ids = []
    artifact_kinds = []
    artifacts_by_kind = {}
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict) or set(artifact) != {
            "digest",
            "id",
            "kind",
            "uri",
        }:
            return failure("artifact.invalid", f"$.artifacts[{index}]")
        artifact_ids.append(artifact["id"])
        artifact_kinds.append(artifact["kind"])
        artifact_uri = urlsplit(artifact["uri"])
        if (
            artifact_uri.scheme != "file"
            or artifact_uri.netloc
            or artifact_uri.query
            or artifact_uri.fragment
        ):
            return failure("artifact.invalid_uri", f"$.artifacts[{index}].uri")
        path = Path(unquote(artifact_uri.path))
        if not path.is_absolute() or path.is_symlink() or not path.is_file():
            return failure("artifact.missing", f"$.artifacts[{index}].uri")
        resolved = path.resolve()
        if resolved.parent != run_root:
            return failure("artifact.outside_root", f"$.artifacts[{index}].uri")
        payload = path.read_bytes()
        if not isinstance(artifact["digest"], str) or artifact["digest"] != (
            f"sha256:{hashlib.sha256(payload).hexdigest()}"
        ):
            return failure("artifact.digest_mismatch", f"$.artifacts[{index}].digest")
        artifacts_by_kind[artifact["kind"]] = payload
    if len(artifact_ids) != len(set(artifact_ids)) or len(artifact_kinds) != len(
        set(artifact_kinds)
    ):
        return failure("artifact.duplicate", "$.artifacts")
    required_artifacts = {
        "api_assertions",
        "http_transcript",
        "repository_snapshot",
        "run_spec",
        "server_stderr",
        "server_stdout",
        "smi_observations",
        "tokenizer_proof",
    }
    if set(artifacts_by_kind) != required_artifacts:
        return failure("artifact.missing", "$.artifacts")

    run_spec = json.loads(artifacts_by_kind["run_spec"])
    spec_check = validate_contract(run_spec, guarded_root)
    if spec_check["status"] != "passed":
        return failure(spec_check["code"], "$.artifacts.run_spec")
    if (
        run_spec["digest"] != result["run_spec_digest"]
        or run_spec["run_id"] != result["run_id"]
    ):
        return failure("contract.identity_mismatch", "$.run_spec_digest")
    if run_spec["mode"] == "operational_regression":
        try:
            campaign_path = Path(run_spec["campaign_manifest"])
            campaign_bytes = campaign_path.read_bytes()
            campaign = json.loads(campaign_bytes)
        except (OSError, json.JSONDecodeError):
            return failure("artifact.invalid", "$.artifacts.run_spec.campaign_manifest")
        if (
            f"sha256:{hashlib.sha256(campaign_bytes).hexdigest()}"
            != run_spec["campaign_digest"]
            or not isinstance(campaign, dict)
            or set(campaign) != {"entries", "schema_version"}
            or campaign["schema_version"] != "vllm-dlc-execution-campaign/v1"
            or not isinstance(campaign["entries"], list)
        ):
            return failure("artifact.invalid", "$.artifacts.run_spec.campaign_manifest")
        required_ids = set(OPERATIONAL_CAMPAIGN_REQUIRED_IDS)
        if run_spec["deployment_profile"]["role"] == "model_adaptation_profile_operational":
            required_ids.update({
                "model_adaptation_approval", "model_adaptation_tp_derivation"
            })
        by_id = {
            entry.get("id"): entry
            for entry in campaign["entries"]
            if isinstance(entry, dict)
        }
        if len(by_id) != len(campaign["entries"]) or not required_ids.issubset(by_id):
            return failure("artifact.invalid", "$.artifacts.run_spec.campaign_manifest")
        expected_paths = {
            "python": Path(sys.executable).resolve(),
            "runner": Path(__file__).with_name("run-vllm-dlc-smoke.py").resolve(),
            "validator": Path(__file__).resolve(),
            "launcher": Path(run_spec["launch"]["arguments"][0]).resolve(),
            "tokenizer_builder": Path(__file__).with_name("build-vllm-dlc-long-prefix.py").resolve(),
            "smi_adapter": Path(run_spec["hardware_observation"]["executable"]).resolve(),
            "smi_preflight": Path(run_spec["hardware_observation"]["qualification_executable"]).resolve(),
            "smi_tool": Path(run_spec["hardware_observation"]["tool_executable"]).resolve(),
            "dependency_qualifier": DEPENDENCY_QUALIFIER_PATH,
            "dependency_requirements": DEPENDENCY_REQUIREMENTS_PATH,
            "dependency_exception_policy": DEPENDENCY_EXCEPTION_POLICY_PATH,
            "main_to_main_operational_policy": MAIN_TO_MAIN_OPERATIONAL_POLICY_PATH,
            "vllm_source": Path(run_spec["repository_guards"][0]).resolve(),
            "vllm_dlc_source": Path(run_spec["repository_guards"][1]).resolve(),
            "smi_source": Path(run_spec["hardware_observation"]["smi_source_root"]).resolve(),
            "vllm_native": Path(importlib.util.find_spec("vllm._C").origin).resolve(),
            "vllm_dlc_native": Path(importlib.util.find_spec("vllm_dlc.vllm_dlc_C").origin).resolve(),
            "model_hosting_container_standards": Path(
                importlib.util.find_spec("model_hosting_container_standards").origin
            ).resolve(),
            "ijson": Path(importlib.util.find_spec("ijson").origin).resolve(),
        }
        if run_spec["deployment_profile"]["role"] == "model_adaptation_profile_operational":
            expected_paths.update({
                "model_adaptation_approval": Path(run_spec["deployment_profile"]["approval_path"]).resolve(),
                "model_adaptation_tp_derivation": Path(run_spec["deployment_profile"]["tp_derivation_path"]).resolve(),
            })
            if (
                by_id["model_adaptation_approval"]["digest"]
                != run_spec["deployment_profile"]["approval_digest"]
                or by_id["model_adaptation_tp_derivation"]["digest"]
                != run_spec["deployment_profile"]["tp_derivation_digest"]
            ):
                return failure("artifact.invalid", "$.artifacts.run_spec.campaign_manifest")
        if any(
            not Path(by_id[entry_id]["path"]).is_absolute()
            or Path(by_id[entry_id]["path"]).resolve() != expected
            for entry_id, expected in expected_paths.items()
        ):
            return failure("artifact.invalid", "$.artifacts.run_spec.campaign_manifest")
        if (
            by_id["main_to_main_operational_policy"]["path"]
            != str(MAIN_TO_MAIN_OPERATIONAL_POLICY_PATH)
        ):
            return failure("artifact.invalid", "$.artifacts.run_spec.campaign_manifest")
        try:
            operational_policy = json.loads(
                Path(by_id["main_to_main_operational_policy"]["path"]).read_bytes()
            )
        except (OSError, UnicodeError, json.JSONDecodeError):
            return failure("artifact.invalid", "$.artifacts.run_spec.campaign_manifest")
        if (
            not validate_main_to_main_operational_policy(operational_policy)
            or operational_policy["target"] != run_spec["target"]
        ):
            return failure("artifact.invalid", "$.artifacts.run_spec.campaign_manifest")
        if not validate_dependency_qualification(
            Path(by_id["dependency_qualification"]["path"]),
            run_spec["repository_guards"],
        ):
            return failure("artifact.invalid", "$.artifacts.run_spec.campaign_manifest")
        for entry_id, root in (
            ("vllm_snapshot", Path(run_spec["repository_guards"][0])),
            ("vllm_dlc_snapshot", Path(run_spec["repository_guards"][1])),
        ):
            try:
                recorded = json.loads(Path(by_id[entry_id]["path"]).read_text())
            except (OSError, json.JSONDecodeError):
                return failure("artifact.invalid", "$.artifacts.run_spec.campaign_manifest")
            if recorded != repository_snapshot(root):
                return failure("artifact.invalid", "$.artifacts.run_spec.campaign_manifest")
        for entry in campaign["entries"]:
            if not isinstance(entry, dict) or set(entry) != {
                "digest", "id", "kind", "path"
            }:
                return failure("artifact.invalid", "$.artifacts.run_spec.campaign_manifest")
            candidate = Path(entry["path"])
            if entry["kind"] == "file":
                try:
                    actual = f"sha256:{hashlib.sha256(candidate.read_bytes()).hexdigest()}"
                except OSError:
                    return failure("artifact.invalid", "$.artifacts.run_spec.campaign_manifest")
                if actual != entry["digest"]:
                    return failure("artifact.invalid", "$.artifacts.run_spec.campaign_manifest")
            elif entry["kind"] == "git_repository":
                revision = subprocess.run(
                    ["git", "-C", str(candidate), "rev-parse", "HEAD^{commit}"],
                    check=False, capture_output=True, text=True,
                )
                if revision.returncode != 0 or revision.stdout.strip() != entry["digest"]:
                    return failure("artifact.invalid", "$.artifacts.run_spec.campaign_manifest")
                if entry["id"] == "smi_source":
                    status = subprocess.run(
                        ["git", "-C", str(candidate), "status", "--porcelain=v1"],
                        check=False, capture_output=True, text=True,
                    )
                    if status.returncode != 0 or status.stdout.strip():
                        return failure("artifact.invalid", "$.artifacts.run_spec.campaign_manifest")
            else:
                return failure("artifact.invalid", "$.artifacts.run_spec.campaign_manifest")
    try:
        for name in ("model", "tokenizer", "processor"):
            asset_path = run_spec["assets"][f"{name}_path"]
            expected_digest = run_spec["assets"][f"{name}_digest"]
            if asset_path is not None and canonical_asset_digest(Path(asset_path)) != expected_digest:
                return failure("artifact.digest_mismatch", f"$.assets.{name}_digest")
    except (OSError, ValueError):
        return failure("artifact.missing", "$.assets")
    snapshot = json.loads(artifacts_by_kind["repository_snapshot"])
    if not isinstance(snapshot, dict) or set(snapshot) != {"after", "before"}:
        return failure("repository_state.not_verified", "$.artifacts.repository_snapshot")
    if set(snapshot["before"]) != set(run_spec["repository_guards"]):
        return failure("repository_state.not_verified", "$.artifacts.repository_snapshot")
    if set(snapshot["after"]) != set(run_spec["repository_guards"]):
        return failure("repository_state.not_verified", "$.artifacts.repository_snapshot")
    expected_heads = {
        run_spec["repository_guards"][0]: run_spec["target"]["vllm_sha"],
        run_spec["repository_guards"][1]: run_spec["target"]["vllm_dlc_sha"],
    }
    if any(
        snapshot["before"][root].get("head") != head
        for root, head in expected_heads.items()
    ):
        return failure("contract.identity_mismatch", "$.artifacts.repository_snapshot")

    try:
        api_assertions = json.loads(artifacts_by_kind["api_assertions"])
        transcript = json.loads(artifacts_by_kind["http_transcript"])
        observations = json.loads(artifacts_by_kind["smi_observations"])
        tokenizer_proof = json.loads(artifacts_by_kind["tokenizer_proof"])
    except (UnicodeError, json.JSONDecodeError):
        return failure("artifact.invalid", "$.artifacts")
    if not isinstance(api_assertions, list) or [
        row.get("role") for row in api_assertions if isinstance(row, dict)
    ] != ["models", "completion", "chat", "long_prefix"]:
        return failure("artifact.invalid", "$.artifacts.api_assertions")
    for index, row in enumerate(api_assertions):
        if set(row) != {"generated_field", "json_contract", "liveness", "role"}:
            return failure("artifact.invalid", f"$.artifacts.api_assertions[{index}]")
        expected_generated = "not_applicable" if row["role"] == "models" else True
        if (
            row["generated_field"] != expected_generated
            or row["json_contract"] is not True
            or row["liveness"] is not True
        ):
            return failure("artifact.invalid", f"$.artifacts.api_assertions[{index}]")
    if not isinstance(transcript, list) or any(
        not isinstance(row, dict)
        or set(row) != {"method", "path", "status"}
        or type(row["status"]) is not int
        or not 200 <= row["status"] < 300
        for row in transcript
    ):
        return failure("artifact.invalid", "$.artifacts.http_transcript")
    expected_requests = [
        ("GET", "/v1/models"),
        ("POST", "/v1/completions"),
        ("POST", "/v1/chat/completions"),
        ("POST", "/v1/completions"),
    ]
    if [(row["method"], row["path"]) for row in transcript] != expected_requests:
        return failure("artifact.invalid", "$.artifacts.http_transcript")
    if not isinstance(tokenizer_proof, dict) or set(tokenizer_proof) != {
        "context_limit", "output_allowance", "prompt", "prompt_digest",
        "prompt_token_count", "schema_version", "threshold", "token_ids_digest",
    } or (
        tokenizer_proof["schema_version"] != "vllm-dlc-long-prefix-proof/v1"
        or tokenizer_proof["threshold"] != run_spec["deployment_profile"]["max_num_batched_tokens"]
        or tokenizer_proof["context_limit"] != run_spec["deployment_profile"]["context_limit"]
        or tokenizer_proof["prompt_token_count"] <= tokenizer_proof["threshold"]
        or tokenizer_proof["prompt_token_count"] + tokenizer_proof["output_allowance"] > tokenizer_proof["context_limit"]
        or f"sha256:{hashlib.sha256(tokenizer_proof['prompt'].encode('utf-8')).hexdigest()}" != tokenizer_proof["prompt_digest"]
    ):
        return failure("artifact.invalid", "$.artifacts.tokenizer_proof")
    try:
        if run_spec["mode"] == "diagnostic_only":
            token_ids = list(range(1, len(tokenizer_proof["prompt"].split()) + 1))
        else:
            from transformers import AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(
                run_spec["assets"]["tokenizer_path"],
                local_files_only=True,
                trust_remote_code=False,
            )
            token_ids = tokenizer.encode(
                tokenizer_proof["prompt"], add_special_tokens=False
            )
    except Exception:
        return failure("artifact.invalid", "$.artifacts.tokenizer_proof")
    token_ids_bytes = json.dumps(token_ids, separators=(",", ":")).encode("utf-8")
    if (
        len(token_ids) != tokenizer_proof["prompt_token_count"]
        or f"sha256:{hashlib.sha256(token_ids_bytes).hexdigest()}" != tokenizer_proof["token_ids_digest"]
    ):
        return failure("artifact.invalid", "$.artifacts.tokenizer_proof")
    sample_points = ["before_launch", "after_ready", "during_request", "after_cleanup"]
    if not isinstance(observations, list) or [row.get("sample_point") for row in observations if isinstance(row, dict)] != sample_points:
        return failure("artifact.invalid", "$.artifacts.smi_observations")
    for index, observation in enumerate(observations):
        if set(observation) != {"adapter_schema", "devices", "sample_point"} or observation["adapter_schema"] != "vllm-dlc-smi-observation/v1":
            return failure("artifact.invalid", f"$.artifacts.smi_observations[{index}]")
        if not isinstance(observation["devices"], list) or any(
            not isinstance(device, dict)
            or set(device) != {
                "device_key", "health", "memory_total_mib", "process_pids"
                , "observed_pids"
            }
            or not isinstance(device["device_key"], str)
            or not device["device_key"]
            or device["health"] != "queryable_not_excluded"
            or type(device["memory_total_mib"]) not in {int, float}
            or not math.isfinite(device["memory_total_mib"])
            or device["memory_total_mib"] <= 0
            or not isinstance(device["observed_pids"], list)
            or any(type(pid) is not int or pid <= 0 for pid in device["observed_pids"])
            or not isinstance(device["process_pids"], list)
            or any(type(pid) is not int or pid <= 0 for pid in device["process_pids"])
            or not set(device["process_pids"]).issubset(device["observed_pids"])
            for device in observation["devices"]
        ):
            return failure("artifact.invalid", f"$.artifacts.smi_observations[{index}]")
        if len({device["device_key"] for device in observation["devices"]}) != len(
            observation["devices"]
        ):
            return failure("artifact.invalid", f"$.artifacts.smi_observations[{index}]")
    required_devices = run_spec["hardware_observation"]["required_device_count"]
    for index, observation in enumerate(observations):
        if len(observation["devices"]) < required_devices:
            return failure("artifact.invalid", f"$.artifacts.smi_observations[{index}]")
    tensor_parallel_size = run_spec["deployment_profile"]["tensor_parallel_size"]
    observed_processes = {
        pid for row in observations[2]["devices"] for pid in row["process_pids"]
    }
    if len(observed_processes) < tensor_parallel_size:
        return failure("artifact.invalid", "$.artifacts.smi_observations[2]")
    if any(row["process_pids"] for row in observations[3]["devices"]):
        return failure("artifact.invalid", "$.artifacts.smi_observations[3]")
    observed_pid_baseline = {
        pid for row in observations[0]["devices"] for pid in row["observed_pids"]
    }
    cleanup_observed_pids = {
        pid for row in observations[3]["devices"] for pid in row["observed_pids"]
    }
    if cleanup_observed_pids - observed_pid_baseline:
        return failure("artifact.invalid", "$.artifacts.smi_observations[3]")

    gates = result["gates"]
    if not isinstance(gates, list) or any(
        not isinstance(gate, dict)
        or set(gate) != {"evidence_digest", "id", "mandatory", "status"}
        or gate.get("status") not in GATE_STATUSES
        or type(gate.get("mandatory")) is not bool
        or gate.get("mandatory") is not True
        or not isinstance(gate.get("evidence_digest"), str)
        or not re.fullmatch(DIGEST_PATTERN, gate.get("evidence_digest", ""))
        for gate in gates
    ):
        return failure("contract.invalid_gate", "$.gates")
    gate_ids = [gate["id"] for gate in gates]
    if len(gate_ids) != len(set(gate_ids)) or set(gate_ids) != set(run_spec["gates"]):
        return failure("contract.identity_mismatch", "$.gates")
    for gate in gates:
        if gate["evidence_digest"] != value_digest(
            {"gate": gate["id"], "status": gate["status"]}
        ):
            return failure("contract.digest_mismatch", "$.gates")
    mandatory_statuses = {
        gate["status"] for gate in gates if gate["mandatory"]
    }
    expected_overall = next(
        (
            status
            for status in ("failed", "blocked", "not_verified")
            if status in mandatory_statuses
        ),
        "passed",
    )
    if result["overall_status"] != expected_overall:
        return failure("contract.inconsistent_status", "$.overall_status")
    gates_by_id = {gate["id"]: gate for gate in gates}
    artifact_derived_passes = {
        "service_ready", "models_api", "completions_api", "chat_api",
        "long_prefix_api", "server_liveness", "long_prefix_threshold_exercised",
        "real_dlc_hardware_operational", "lifecycle_cleanup", "repository_state",
        "artifact_closure", run_spec["deployment_profile"]["role"],
    }
    if expected_overall == "passed" and any(
        gates_by_id[gate_id]["status"] != "passed"
        for gate_id in artifact_derived_passes
    ):
        return failure("contract.inconsistent_status", "$.gates")
    fixture = (
        run_spec["launch"]["provider_class"] == "fixture"
        or run_spec["hardware_observation"]["provider_class"] == "fixture"
    )
    expected_class = (
        "fixture_operational_validation"
        if fixture
        else "real_dlc_hardware_operational"
    )
    expected_completion = (
        not fixture
        and run_spec["mode"] == "operational_regression"
        and expected_overall == "passed"
        and snapshot["before"] == snapshot["after"]
        and result["exit_code"] == 0
    )
    if (
        result["evidence_class"] != expected_class
        or result["completion_eligible"] != expected_completion
        or (result["exit_code"] == 0) != (expected_overall == "passed")
    ):
        return failure("contract.inconsistent_status", "$.completion_eligible")
    outcome = {
        "authoritativeness": result["authoritativeness"],
        "campaign_digest": run_spec["campaign_digest"],
        "completion_eligible": result["completion_eligible"],
        "evidence_class": result["evidence_class"],
        "run_id": result["run_id"],
    }
    return {"code": "operational_result_reference.valid", "status": "passed"}, outcome


def validate_ticket06_evidence(
    index_file: Path, guarded_root: Path
) -> tuple[dict[str, str], dict[str, Any]]:
    def failure(code: str, path: str) -> tuple[dict[str, str], dict[str, Any]]:
        return {"code": code, "path": path, "status": "failed"}, {}

    document = json.loads(index_file.read_text(encoding="utf-8"))
    fields = {
        "alignment_action",
        "campaign_id",
        "claim_level",
        "digest",
        "finalization_intent",
        "manifest_action",
        "roles",
        "schema_version",
        "ticket07_action",
    }
    if not isinstance(document, dict):
        return failure("ticket06.invalid", "$")
    unknown = sorted(set(document) - fields)
    missing = sorted(fields - set(document))
    if unknown:
        return failure("contract.unknown_field", f"$.{unknown[0]}")
    if missing:
        return failure("contract.missing_required_field", f"$.{missing[0]}")
    if (
        document["schema_version"] != "vllm-dlc-ticket06-operational-index/v1"
        or document["claim_level"] != "operational_only"
        or document["alignment_action"] != "unchanged"
        or document["manifest_action"] != "report_only"
        or document["finalization_intent"] != "none"
        or document["ticket07_action"] != "not_published"
        or not isinstance(document["campaign_id"], str)
        or not re.fullmatch(DIGEST_PATTERN, document["campaign_id"])
    ):
        return failure("ticket06.invalid", "$")
    if document["digest"] != canonical_digest(document):
        return failure("contract.digest_mismatch", "$.digest")
    rows = document["roles"]
    expected_roles = {
        "deepseek_tp2_operational",
        "llama_tp1_dense_operational",
        "model_adaptation_profile_operational",
    }
    if not isinstance(rows, list) or len(rows) != 3:
        return failure("ticket06.missing_role", "$.roles")
    references = []
    validated = []
    for index, row in enumerate(rows):
        if (
            not isinstance(row, dict)
            or set(row) != {"result_reference", "role"}
            or row.get("role") not in expected_roles
            or not isinstance(row.get("result_reference"), str)
            or not Path(row["result_reference"]).is_absolute()
        ):
            return failure("ticket06.invalid", f"$.roles[{index}]")
        reference_path = Path(row["result_reference"])
        check, outcome = validate_operational_result_reference(
            reference_path, guarded_root
        )
        if check["status"] != "passed":
            return failure(check["code"], f"$.roles[{index}].result_reference")
        references.append(reference_path.resolve())
        validated.append((row, outcome, reference_path))
    if any(
        outcome["evidence_class"] == "fixture_operational_validation"
        or not outcome["completion_eligible"]
        for _, outcome, _ in validated
    ):
        return failure("ticket06.fixture_ineligible", "$.roles")
    role_ids = [row["role"] for row, _, _ in validated]
    if set(role_ids) != expected_roles or len(role_ids) != len(set(role_ids)):
        return failure("ticket06.missing_role", "$.roles")
    if len(references) != len(set(references)):
        return failure("ticket06.duplicate_reference", "$.roles")

    run_ids = []
    artifact_roots = []
    targets = []
    campaign_digests = []
    for index, (row, outcome, reference_path) in enumerate(validated):
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
        result_path = Path(unquote(urlsplit(reference["uri"]).path))
        result = json.loads(result_path.read_text(encoding="utf-8"))
        run_spec_artifact = next(
            artifact for artifact in result["artifacts"] if artifact["kind"] == "run_spec"
        )
        run_spec = json.loads(
            Path(unquote(urlsplit(run_spec_artifact["uri"]).path)).read_text(
                encoding="utf-8"
            )
        )
        if run_spec["deployment_profile"]["role"] != row["role"]:
            return failure("ticket06.role_mismatch", f"$.roles[{index}].role")
        run_ids.append(outcome["run_id"])
        artifact_roots.append(result_path.parent.resolve())
        targets.append(run_spec["target"])
        campaign_digests.append(outcome["campaign_digest"])
        expected_workflow = (
            "model_adaptation"
            if row["role"] == "model_adaptation_profile_operational"
            else "main_to_main"
        )
        if run_spec["workflow"] != expected_workflow:
            return failure("ticket06.role_mismatch", f"$.roles[{index}].role")
    if len(run_ids) != len(set(run_ids)) or len(artifact_roots) != len(
        set(artifact_roots)
    ):
        return failure("ticket06.identity_collision", "$.roles")
    if any(target != targets[0] for target in targets[1:]):
        return failure("ticket06.target_mismatch", "$.roles")
    if (
        any(value != campaign_digests[0] for value in campaign_digests[1:])
        or document["campaign_id"] != campaign_digests[0]
    ):
        return failure("ticket06.campaign_mismatch", "$.campaign_id")
    outcome = {
        "acceptance_eligible": False,
        "alignment_outcome": "unchanged",
        "campaign_id": document["campaign_id"],
        "completion_status": "passed",
        "finalize_action": "none",
        "manifest_outcome": "report_only",
        "ticket07_action": "not_published",
    }
    return {"code": "ticket06_evidence.valid", "status": "passed"}, outcome


def validate_model_adaptation_operational(
    document_file: Path, guarded_root: Path
) -> tuple[dict[str, str], dict[str, Any]]:
    document = json.loads(document_file.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or "result_evidence" in document:
        return {"code": "operational_consumer.synthetic_result", "path": "$", "status": "failed"}, {}
    fields = {"claims", "result_reference", "role", "schema_version"}
    if set(document) != fields:
        code = (
            "contract.unknown_field"
            if set(document) - fields
            else "contract.missing_required_field"
        )
        return {"code": code, "path": "$", "status": "failed"}, {}
    if (
        document["schema_version"] != "vllm-dlc-model-adaptation-operational/v1"
        or document["role"] != "model_adaptation_profile_operational"
        or document["claims"]
        != {
            "acceptance_eligible": False,
            "alignment_action": "unchanged",
            "finalize_action": "none",
        }
        or not isinstance(document["result_reference"], str)
        or not Path(document["result_reference"]).is_absolute()
    ):
        return {"code": "operational_consumer.invalid", "path": "$", "status": "failed"}, {}
    check, result = validate_operational_result_reference(
        Path(document["result_reference"]), guarded_root
    )
    if check["status"] != "passed":
        return check, {}
    if not result["completion_eligible"]:
        return {"code": "operational_consumer.ineligible", "path": "$.result_reference", "status": "failed"}, {}
    reference = json.loads(Path(document["result_reference"]).read_text(encoding="utf-8"))
    evidence = json.loads(Path(unquote(urlsplit(reference["uri"]).path)).read_text(encoding="utf-8"))
    run_spec_row = next(row for row in evidence["artifacts"] if row["kind"] == "run_spec")
    run_spec = json.loads(Path(unquote(urlsplit(run_spec_row["uri"]).path)).read_text(encoding="utf-8"))
    if run_spec["deployment_profile"]["role"] != document["role"]:
        return {"code": "operational_consumer.role_mismatch", "path": "$.role", "status": "failed"}, {}
    return {"code": "model_adaptation_operational.valid", "status": "passed"}, {
        "acceptance_eligible": False,
        "alignment_outcome": "unchanged",
        "completion_status": "passed",
        "finalize_action": "none",
        "run_id": result["run_id"],
    }


def validate_main_to_main_operational(
    document_file: Path, guarded_root: Path
) -> tuple[dict[str, str], dict[str, Any]]:
    document = json.loads(document_file.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or any(
        isinstance(child, dict) and "status" in child
        for child in document.get("children", [])
    ):
        return {"code": "operational_consumer.synthetic_result", "path": "$", "status": "failed"}, {}
    fields = {
        "children", "claims", "policy_digest", "policy_path", "schema_version"
    }
    if set(document) != fields:
        return {"code": "operational_consumer.invalid", "path": "$", "status": "failed"}, {}
    claims = {
        "acceptance_eligible": False,
        "alignment_action": "unchanged",
        "finalize_action": "none",
        "manifest_action": "report_only",
    }
    if (
        document["schema_version"] != "vllm-dlc-main-to-main-operational/v1"
        or document["claims"] != claims
        or not isinstance(document["policy_digest"], str)
        or not re.fullmatch(DIGEST_PATTERN, document["policy_digest"])
        or not isinstance(document["policy_path"], str)
        or not Path(document["policy_path"]).is_absolute()
        or not isinstance(document["children"], list)
        or len(document["children"]) != 2
    ):
        return {"code": "operational_consumer.invalid", "path": "$", "status": "failed"}, {}
    policy_path = Path(document["policy_path"])
    try:
        policy_bytes = policy_path.read_bytes()
    except OSError:
        return {"code": "operational_consumer.policy_invalid", "path": "$.policy_path", "status": "failed"}, {}
    if f"sha256:{hashlib.sha256(policy_bytes).hexdigest()}" != document["policy_digest"]:
        return {"code": "operational_consumer.policy_digest_mismatch", "path": "$.policy_digest", "status": "failed"}, {}
    try:
        policy = json.loads(policy_bytes)
    except (UnicodeError, json.JSONDecodeError):
        return {"code": "operational_consumer.policy_invalid", "path": "$.policy_path", "status": "failed"}, {}
    if not validate_main_to_main_operational_policy(policy):
        return {"code": "operational_consumer.policy_invalid", "path": "$.policy_path", "status": "failed"}, {}
    expected_roles = {"deepseek_tp2_operational", "llama_tp1_dense_operational"}
    run_ids = []
    roles = []
    targets = []
    campaign_digests = []
    policy_roles = {row["role"]: row for row in policy["roles"]}
    for index, child in enumerate(document["children"]):
        if (
            not isinstance(child, dict)
            or set(child) != {"result_reference", "role"}
            or child["role"] not in expected_roles
            or not isinstance(child["result_reference"], str)
            or not Path(child["result_reference"]).is_absolute()
        ):
            return {"code": "operational_consumer.invalid", "path": f"$.children[{index}]", "status": "failed"}, {}
        check, result = validate_operational_result_reference(
            Path(child["result_reference"]), guarded_root
        )
        if check["status"] != "passed":
            return check, {}
        if not result["completion_eligible"]:
            return {"code": "operational_consumer.ineligible", "path": f"$.children[{index}]", "status": "failed"}, {}
        reference = json.loads(Path(child["result_reference"]).read_text(encoding="utf-8"))
        evidence = json.loads(Path(unquote(urlsplit(reference["uri"]).path)).read_text(encoding="utf-8"))
        run_spec_row = next(row for row in evidence["artifacts"] if row["kind"] == "run_spec")
        run_spec = json.loads(Path(unquote(urlsplit(run_spec_row["uri"]).path)).read_text(encoding="utf-8"))
        if run_spec["deployment_profile"]["role"] != child["role"]:
            return {"code": "operational_consumer.role_mismatch", "path": f"$.children[{index}].role", "status": "failed"}, {}
        if run_spec["target"] != policy["target"]:
            return {"code": "operational_consumer.target_mismatch", "path": f"$.children[{index}]", "status": "failed"}, {}
        if (
            run_spec["deployment_profile"]["tensor_parallel_size"]
            != policy_roles[child["role"]]["tensor_parallel_size"]
        ):
            return {"code": "operational_consumer.tp_mismatch", "path": f"$.children[{index}]", "status": "failed"}, {}
        roles.append(child["role"])
        run_ids.append(result["run_id"])
        targets.append(run_spec["target"])
        campaign_digests.append(run_spec["campaign_digest"])
    if set(roles) != expected_roles or len(run_ids) != len(set(run_ids)):
        return {"code": "operational_consumer.identity_collision", "path": "$.children", "status": "failed"}, {}
    if targets[0] != targets[1]:
        return {"code": "operational_consumer.target_mismatch", "path": "$.children", "status": "failed"}, {}
    if campaign_digests[0] != campaign_digests[1]:
        return {"code": "operational_consumer.campaign_mismatch", "path": "$.children", "status": "failed"}, {}
    return {"code": "main_to_main_operational.valid", "status": "passed"}, {
        "acceptance_eligible": False,
        "alignment_outcome": "unchanged",
        "completion_status": "passed",
        "finalize_action": "none",
        "manifest_outcome": "report_only",
    }


def value_digest(value: Any) -> str:
    canonical = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def canonical_asset_digest(path: Path) -> str:
    if path.is_symlink() or not path.exists():
        raise ValueError("asset is missing or symlinked")
    if path.is_dir() and any(candidate.is_symlink() for candidate in path.rglob("*")):
        raise ValueError("asset contains a symlink")
    accumulator = hashlib.sha256()
    files = [path] if path.is_file() else sorted(
        (candidate for candidate in path.rglob("*") if candidate.is_file()),
        key=lambda candidate: candidate.relative_to(path).as_posix(),
    )
    if not files:
        raise ValueError("asset has no regular files")
    for candidate in files:
        if candidate.is_symlink() or not candidate.is_file():
            raise ValueError("asset contains an invalid file")
        relative = candidate.name if path.is_file() else candidate.relative_to(path).as_posix()
        accumulator.update(relative.encode("utf-8"))
        accumulator.update(b"\0")
        with candidate.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                accumulator.update(chunk)
        accumulator.update(b"\0")
    return f"sha256:{accumulator.hexdigest()}"


def nested_shape_error(document: dict[str, Any]) -> dict[str, str] | None:
    for field, expected in NESTED_FIELDS.get(document.get("contract_kind"), {}).items():
        value = document.get(field)
        if not isinstance(value, dict):
            return {"code": "contract.invalid_type", "path": f"$.{field}", "status": "failed"}
        unknown = sorted(set(value) - expected)
        if unknown:
            return {
                "code": "contract.unknown_field",
                "path": f"$.{field}.{unknown[0]}",
                "status": "failed",
            }
        missing = sorted(expected - set(value))
        if missing:
            if field == "target" and missing[0] in {"vllm_sha", "vllm_dlc_sha", "manifest_digest"}:
                return {
                    "code": "contract.missing_identity",
                    "path": f"$.{field}.{missing[0]}",
                    "status": "failed",
                }
            return {
                "code": "contract.missing_required_field",
                "path": f"$.{field}.{missing[0]}",
                "status": "failed",
            }
    if document.get("contract_kind") == "result_evidence":
        row_shapes = {
            "artifacts": {"id", "kind", "uri", "digest"},
            "diagnostics": {"code", "message", "artifact_digest"},
        }
        for field, expected in row_shapes.items():
            rows = document.get(field)
            if not isinstance(rows, list):
                return {
                    "code": "contract.invalid_type",
                    "path": f"$.{field}",
                    "status": "failed",
                }
            for index, row in enumerate(rows):
                if not isinstance(row, dict):
                    return {
                        "code": "contract.invalid_type",
                        "path": f"$.{field}[{index}]",
                        "status": "failed",
                    }
                unknown = sorted(set(row) - expected)
                if unknown:
                    return {
                        "code": "contract.unknown_field",
                        "path": f"$.{field}[{index}].{unknown[0]}",
                        "status": "failed",
                    }
                missing = sorted(expected - set(row))
                if missing:
                    return {
                        "code": "contract.missing_required_field",
                        "path": f"$.{field}[{index}].{missing[0]}",
                        "status": "failed",
                    }
    return None


def invalid_value(path: str) -> dict[str, str]:
    return {"code": "contract.invalid_value", "path": path, "status": "failed"}


def semantic_error(document: dict[str, Any]) -> dict[str, str] | None:
    kind = document.get("contract_kind")
    if kind == "run_spec":
        if not isinstance(document["run_id"], str) or not document["run_id"]:
            return invalid_value("$.run_id")
        target = document["target"]
        for field in ("vllm_sha", "vllm_dlc_sha"):
            if not isinstance(target[field], str) or not re.fullmatch(SHA_PATTERN, target[field]):
                return {"code": "contract.missing_identity", "path": f"$.target.{field}", "status": "failed"}
        if not isinstance(target["manifest_digest"], str) or not re.fullmatch(DIGEST_PATTERN, target["manifest_digest"]):
            return invalid_value("$.target.manifest_digest")
        if not isinstance(document["workflow"], str) or document["workflow"] not in {"model_adaptation", "main_to_main"}:
            return invalid_value("$.workflow")
        if not isinstance(document["mode"], str) or document["mode"] not in {"acceptance", "diagnostic_only"}:
            return invalid_value("$.mode")
        if not isinstance(document["finalization_intent"], str) or document["finalization_intent"] not in {"none", "eligible_only"}:
            return invalid_value("$.finalization_intent")
        profile = document["deployment_profile"]
        for field in ("model_id", "served_model_name", "dtype", "quantization"):
            if not isinstance(profile[field], str) or not profile[field]:
                return invalid_value(f"$.deployment_profile.{field}")
        for field in ("model_revision", "tokenizer_revision"):
            if not isinstance(profile[field], str) or not re.fullmatch(SHA_PATTERN, profile[field]):
                return {"code": "contract.missing_identity", "path": f"$.deployment_profile.{field}", "status": "failed"}
        processor = profile["processor_revision"]
        if processor is not None and (not isinstance(processor, str) or not re.fullmatch(SHA_PATTERN, processor)):
            return {"code": "contract.missing_identity", "path": "$.deployment_profile.processor_revision", "status": "failed"}
        for field in ("tensor_parallel_size", "pipeline_parallel_size", "context_limit", "max_num_batched_tokens"):
            if type(profile[field]) is not int or profile[field] <= 0:
                return invalid_value(f"$.deployment_profile.{field}")
        for field in ("chunked_prefill", "real_weights"):
            if type(profile[field]) is not bool:
                return invalid_value(f"$.deployment_profile.{field}")
        hardware = document["hardware"]
        if not isinstance(hardware["class"], str) or hardware["class"] not in {"real_dlc_hardware", "fake_server", "dlcsim", "none"}:
            return invalid_value("$.hardware.class")
        if type(hardware["required"]) is not bool or type(hardware["device_count"]) is not int:
            return invalid_value("$.hardware")
        if hardware["device_count"] < 0 or (hardware["required"] and hardware["device_count"] < 1):
            return invalid_value("$.hardware.device_count")
        if document["mode"] == "acceptance" and (
            hardware != {
                "class": "real_dlc_hardware",
                "device_count": hardware["device_count"],
                "required": True,
            }
            or not profile["real_weights"]
        ):
            return {
                "code": "contract.inconsistent_status",
                "path": "$.mode",
                "status": "failed",
            }
        for field, value in document["timeouts"].items():
            if type(value) is not int or value <= 0:
                return invalid_value(f"$.timeouts.{field}")
        policy = document["runtime_policy"]
        expected_policy = {"execution": "eager", "triton_execution": "forbidden", "compile_execution": "forbidden"}
        if policy != expected_policy:
            return invalid_value("$.runtime_policy")
        gates = document["gates"]
        if not isinstance(gates, list) or not gates or any(not isinstance(gate, str) or not gate for gate in gates) or len(gates) != len(set(gates)):
            return invalid_value("$.gates")
        if hardware["class"] == "real_dlc_hardware" and not {
            "chunked_prefill",
            "runtime_dispatch",
            "real_dlc_hardware",
        }.issubset(gates):
            return {
                "code": "contract.inconsistent_status",
                "path": "$.gates",
                "status": "failed",
            }
        if not isinstance(document["artifact_destination"], str) or not Path(document["artifact_destination"]).is_absolute():
            return invalid_value("$.artifact_destination")
    elif kind == "result_evidence":
        if not isinstance(document["run_id"], str) or not document["run_id"]:
            return invalid_value("$.run_id")
        if not isinstance(document["run_spec_digest"], str) or not re.fullmatch(DIGEST_PATTERN, document["run_spec_digest"]):
            return invalid_value("$.run_spec_digest")
        if not isinstance(document["execution_environment"], str) or document["execution_environment"] not in {"real_dlc_hardware", "dummy", "fake_server", "dlcsim", "static"}:
            return invalid_value("$.execution_environment")
        if type(document["acceptance_eligible"]) is not bool or type(document["exit_code"]) is not int or document["exit_code"] < 0:
            return invalid_value("$.acceptance_eligible")
        if not isinstance(document["overall_status"], str) or document["overall_status"] not in GATE_STATUSES - {"not_applicable"}:
            return {"code": "contract.invalid_status", "path": "$.overall_status", "status": "failed"}
        if any(not isinstance(gate.get("id"), str) or not gate["id"] for gate in document["gates"]):
            return invalid_value("$.gates")
        gate_ids = [gate["id"] for gate in document["gates"]]
        if not gate_ids or len(gate_ids) != len(set(gate_ids)):
            return {
                "code": "contract.invalid_gate",
                "path": "$.gates",
                "status": "failed",
            }
        if any(not isinstance(gate.get("status"), str) or gate.get("status") not in GATE_STATUSES for gate in document["gates"]):
            return {
                "code": "contract.invalid_status",
                "path": "$.gates",
                "status": "failed",
            }
        mandatory_statuses = {
            gate["status"] for gate in document["gates"] if gate.get("mandatory")
        }
        expected_overall = next(
            (
                status
                for status in ("failed", "blocked", "not_verified")
                if status in mandatory_statuses
            ),
            "passed",
        )
        if document["overall_status"] != expected_overall:
            return {
                "code": "contract.inconsistent_status",
                "path": "$.overall_status",
                "status": "failed",
            }
        if document["acceptance_eligible"]:
            gates_by_id = {gate["id"]: gate for gate in document["gates"]}
            required_acceptance_gates = {
                "chunked_prefill",
                "runtime_dispatch",
                "real_dlc_hardware",
            }
            if document["execution_environment"] != "real_dlc_hardware" or any(
                gate_id not in gates_by_id
                or not gates_by_id[gate_id]["mandatory"]
                or gates_by_id[gate_id]["status"] != "passed"
                for gate_id in required_acceptance_gates
            ):
                return {
                    "code": "contract.inconsistent_status",
                    "path": "$.acceptance_eligible",
                    "status": "failed",
                }
        for index, artifact in enumerate(document["artifacts"]):
            if any(not isinstance(artifact[field], str) or not artifact[field] for field in ("id", "kind", "uri")):
                return invalid_value(f"$.artifacts[{index}]")
            if not isinstance(artifact["digest"], str) or not re.fullmatch(DIGEST_PATTERN, artifact["digest"]):
                return invalid_value(f"$.artifacts[{index}].digest")
        for index, diagnostic in enumerate(document["diagnostics"]):
            if any(not isinstance(diagnostic[field], str) or not diagnostic[field] for field in ("code", "message")):
                return invalid_value(f"$.diagnostics[{index}]")
            artifact_digest = diagnostic["artifact_digest"]
            if artifact_digest is not None and (not isinstance(artifact_digest, str) or not re.fullmatch(DIGEST_PATTERN, artifact_digest)):
                return invalid_value(f"$.diagnostics[{index}].artifact_digest")
    elif kind == "parent_child_handoff":
        for field in ("parent_run_id", "child_run_id"):
            if not isinstance(document[field], str) or not document[field]:
                return invalid_value(f"$.{field}")
        for field in ("target_vllm_sha", "candidate_vllm_dlc_sha"):
            if not isinstance(document[field], str) or not re.fullmatch(SHA_PATTERN, document[field]):
                return {"code": "contract.missing_identity", "path": f"$.{field}", "status": "failed"}
        if not isinstance(document["result_evidence_digest"], str) or not re.fullmatch(DIGEST_PATTERN, document["result_evidence_digest"]):
            return invalid_value("$.result_evidence_digest")
        dependencies = document["changed_dependency_ids"]
        if not isinstance(dependencies, list) or any(not isinstance(value, str) or not value for value in dependencies) or len(dependencies) != len(set(dependencies)):
            return invalid_value("$.changed_dependency_ids")
        if not isinstance(document["status"], str) or document["status"] not in GATE_STATUSES - {"not_applicable"}:
            return {"code": "contract.invalid_status", "path": "$.status", "status": "failed"}
    return None


def package_content_error(
    identity: str,
    skill: str,
    agent: str,
    knowledge: str,
    skill_path: Path,
) -> dict[str, str] | None:
    frontmatter = re.match(r"\A---\n(.*?)\n---\n", skill, re.DOTALL)
    if not frontmatter:
        return {"code": "package.invalid", "status": "failed"}
    try:
        frontmatter_values = yaml.load(frontmatter.group(1), Loader=UniqueKeyLoader)
    except yaml.YAMLError:
        return {"code": "package.invalid", "status": "failed"}
    if not isinstance(frontmatter_values, dict):
        return {"code": "package.invalid", "status": "failed"}
    if not isinstance(frontmatter_values.get("name"), str) or frontmatter_values["name"] != identity:
        return {"code": "package.invalid", "status": "failed"}
    if not isinstance(frontmatter_values.get("description"), str) or not frontmatter_values["description"]:
        return {"code": "package.invalid", "status": "failed"}
    if frontmatter_values.get("disable-model-invocation") is True:
        return {"code": "package.invalid", "status": "failed"}
    steps = re.findall(r"(?m)^(\d+)\.\s+(.+)$", skill)
    if len(steps) < 2 or [number for number, _ in steps] != [str(index) for index in range(1, len(steps) + 1)]:
        return {"code": "package.invalid", "status": "failed"}
    if any("Complete when:" not in text for _, text in steps):
        return {"code": "package.invalid", "status": "failed"}
    references = re.findall(
        r"(?im)^\s*conditional_reference:\s*\[[^]]+\]\(([^)]+\.md)\)\s*$",
        skill,
    )
    if (
        not re.search(r"(?m)^#{1,6}\s+Stop Semantics\s*$", skill)
        or not references
        or any(not (skill_path.parent / reference).resolve().is_file() for reference in references)
    ):
        return {"code": "package.invalid", "status": "failed"}
    if not valid_agent_resource(agent):
        return {"code": "package.invalid", "status": "failed"}
    ownership = re.compile(
        r"(?m)^\s*shared_contract:\s*vllm-dlc-contract/v1\s*$"
    )
    if not ownership.search(skill) or not ownership.search(knowledge):
        return {"code": "quality_gate.duplicated", "status": "failed"}
    quality_text = f"{skill}\n{knowledge}".lower()
    if contains_duplicate_quality_gate(quality_text):
        return {"code": "quality_gate.duplicated", "status": "failed"}
    return None


def contains_duplicate_quality_gate(text: str) -> bool:
    if re.search(r"(?<![A-Za-z0-9_])/v1/[A-Za-z0-9._~!$&'()*+,;=:@%/-]+", text):
        return True
    if re.search(
        r"(?is)(?:```|~~~)\s*(?:bash|sh|shell|zsh|fish)\b[\s\S]*?(?:```|~~~)",
        text,
    ):
        return True
    wrappers = {"env", "uv", "poetry", "pipenv", "conda", "sudo", "bash", "sh", "zsh", "fish"}
    clients = {"curl", "wget", "httpie", "httpx"}

    def is_prohibited_command(candidate: str, explicit_command_syntax: bool) -> bool:
        try:
            tokens = shlex.split(candidate)
        except ValueError:
            return False
        while tokens and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[0]):
            tokens.pop(0)
        if not tokens:
            return False
        lowered_tokens = [token.lower() for token in tokens]
        raw_first = tokens[0].lower()
        first = os.path.basename(raw_first)
        python_command = first.startswith("python") and len(tokens) > 1 and (
            tokens[1].startswith("-") or tokens[1].lower().endswith(".py")
        )
        runner_command = ("runner" in first or "smoke" in first) and any(
            token.startswith("-") for token in tokens[1:]
        )
        explicit_command_syntax = explicit_command_syntax or bool(
            python_command
            or first in wrappers
            or first in clients
            or raw_first.startswith(("./", "/"))
            or runner_command
        )
        command_like = explicit_command_syntax and (
            first in wrappers
            or first in clients
            or (
                first == "http"
                and len(lowered_tokens) > 1
                and lowered_tokens[1] in {"get", "post", "put", "delete", "patch"}
            )
            or python_command
            or runner_command
        )
        invokes_prohibited = any(
            re.search(
                r"(?:^|[\s;/])(?:curl|wget|httpie|httpx)(?:\s|$)"
                r"|(?:^|[\s;/])http\s+(?:get|post|put|delete|patch)\b"
                r"|(?:^|[\s;/])(?:import\s+|from\s+)(?:requests|urllib|http\.client)\b"
                r"|(?:runner|smoke)(?:[._/-]|$)",
                token,
            )
            for token in lowered_tokens
        ) or any(
            os.path.basename(token) == "http"
            and index + 1 < len(lowered_tokens)
            and lowered_tokens[index + 1] in {"get", "post", "put", "delete", "patch"}
            for index, token in enumerate(lowered_tokens)
        ) or (
            first == "http"
            and len(lowered_tokens) > 1
            and lowered_tokens[1] in {"get", "post", "put", "delete", "patch"}
        )
        return command_like and invokes_prohibited

    for inline_code in re.findall(r"`([^`]+)`", text):
        try:
            inline_tokens = shlex.split(inline_code)
        except ValueError:
            inline_tokens = []
        if len(inline_tokens) > 1 and is_prohibited_command(inline_code, True):
            return True
    for line in text.splitlines():
        candidate = re.sub(r"^\s*\$\s*", "", line).strip()
        if is_prohibited_command(
            candidate, explicit_command_syntax=bool(re.match(r"^\s*\$", line))
        ):
            return True
    assertion_line = r"(?im)^\s*(?:assert|require)\s+"
    if re.search(
        assertion_line
        + r"(?:status_code|http\s+status|response\.json|choices(?:\[[^]]+\])?(?:\.|\s)+(?:text|message|content))\b",
        text,
    ):
        return True
    if re.search(
        r"(?is)\b(?:response\.)?status_code\s*(?:==|!=|<=|>=|<|>)\s*\d{3}\b",
        text,
    ):
        return True
    if re.search(
        r"(?im)^\s*if\s+(?:not\s+)?response\.json\(\)[^:\n]*"
        r"(?:choices|text|message|content)[^:\n]*:\s*(?:raise|return)\b",
        text,
    ):
        return True
    if re.search(
        r"(?im)^\s*(?:assert|require|acceptance\s+requires?)[^\n]*(?:chunk|prefill)[^\n]*\b\d+\b",
        text,
    ):
        return True
    if re.search(
        r"(?im)^\s*(?:assert|require|acceptance\s+requires?)[^\n]*(?:"
        r"\d\s*(?:[<>!]=?|==)\s*\w*(?:chunk|prefill)"
        r"|\w*(?:chunk|prefill)\w*\s*(?:[<>!]=?|==)\s*\d)",
        text,
    ):
        return True
    if re.search(
        r"(?im)^\s*(?:assert|require)[^\n]*(?:triton|compile|dynamo)\w*\s*(?:==|!=|is\s+(?:true|false))",
        text,
    ):
        return True
    return False


def valid_agent_resource(text: str) -> bool:
    try:
        document = yaml.load(text, Loader=UniqueKeyLoader)
    except yaml.YAMLError:
        return False
    if not isinstance(document, dict) or set(document) != {"interface"}:
        return False
    fields = document["interface"]
    if not isinstance(fields, dict):
        return False
    required = {"display_name", "short_description", "default_prompt"}
    return set(fields) == required and all(
        isinstance(fields[field], str) and fields[field] for field in required
    )


def documentation_error(
    code: str, path: str, role: str | None = None
) -> dict[str, str]:
    error = {"code": code, "path": path, "status": "failed"}
    if role is not None:
        error["role"] = role
    return error


def path_is_beneath(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def markdown_local_links(text: str) -> list[str]:
    links = []
    for match in re.finditer(r"(?<!!)\[[^]]*\]\(([^)]+)\)", text):
        destination = match.group(1).strip()
        if destination.startswith("<") and destination.endswith(">"):
            destination = destination[1:-1]
        destination = destination.split(maxsplit=1)[0]
        parsed = urlsplit(destination)
        if parsed.scheme or parsed.netloc or destination.startswith("#"):
            continue
        links.append(unquote(parsed.path))
    return links


def parse_prompt_document(
    role: str, text: str, relative_path: str
) -> tuple[dict[str, str] | None, dict[str, Any] | None]:
    frontmatter = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not frontmatter:
        return documentation_error("prompt.invalid", relative_path, role), None
    try:
        metadata = yaml.load(frontmatter.group(1), Loader=UniqueKeyLoader)
    except yaml.YAMLError:
        return documentation_error("prompt.invalid", relative_path, role), None
    profile = PROMPT_PROFILES[role]
    if not isinstance(metadata, dict) or set(metadata) != PROMPT_FIELDS:
        return documentation_error("prompt.invalid", relative_path, role), None
    required_inputs = metadata.get("required_inputs")
    if (
        metadata.get("prompt_schema") != REUSABLE_PROMPT_SCHEMA
        or metadata.get("skill_identity") != profile["skill_identity"]
        or metadata.get("shared_contract") != CONTRACT_VERSION
        or metadata.get("missing_input_status") != "blocked"
        or metadata.get("missing_input_reason") != profile["missing_input_reason"]
        or metadata.get("hardware_evidence") != "not_verified"
        or not isinstance(required_inputs, list)
        or tuple(required_inputs) != profile["required_inputs"]
        or any(not isinstance(value, str) or not value for value in required_inputs)
        or len(required_inputs) != len(set(required_inputs))
    ):
        return documentation_error("prompt.invalid", relative_path, role), None
    body = text[frontmatter.end():].lower()
    if any(term not in body for term in profile["body_terms"]):
        return documentation_error("prompt.invalid", relative_path, role), None
    unsupported_claim = re.compile(
        r"(?im)^(?![^\n]*(?:\bnot\b|\bnever\b|\bcannot\b|\bnone\b|\bfalse\b|不得|不能|未|不))"
        r"[^\n]*\b(?:acceptance|finalization|finalize)\b[^\n]*"
        r"\b(?:passed|verified|finalized|complete|completed|eligible)\b[^\n]*$"
    )
    if re.search(
        r"(?im)^.*(?:acceptance_eligible|finalize_eligible|hardware_evidence)\s*:\s*(?:true|passed)\s*$",
        body,
    ) or re.search(
        r"(?im)^.*(?:real weights|real dlc hardware|chunked prefill runtime|dlc runtime dispatch)"
        r"[^\n]*(?:is|are|为)\s+(?:passed|verified|通过|已验证)\s*[。.]*$",
        body,
    ) or re.search(
        r"(?im)^\s*(?:real weights?|real dlc hardware|acceptance|the workflow)\b"
        r"[^\n]*(?:\bpassed\b|\bverified\b|\bfinalized\b|已通过|已验证|已完成)\s*[。.]*$",
        body,
    ) or unsupported_claim.search(body):
        return documentation_error("prompt.invalid", relative_path, role), None
    return None, metadata


def validate_knowledge_package(
    manifest_file: Path, knowledge_root: Path
) -> tuple[dict[str, str], dict[str, Any]]:
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise TypeError("knowledge package must be a JSON object")
    unknown = sorted(set(manifest) - {"schema_version", "documents", "required_links"})
    if unknown:
        return documentation_error("documentation.unknown_field", f"$.{unknown[0]}"), {}
    missing = sorted({"schema_version", "documents", "required_links"} - set(manifest))
    if missing:
        return documentation_error("documentation.missing_required_field", f"$.{missing[0]}"), {}
    if manifest["schema_version"] != KNOWLEDGE_PACKAGE_SCHEMA:
        return documentation_error(
            "documentation.unsupported_schema_version", "$.schema_version"
        ), {}

    documents = manifest["documents"]
    if not isinstance(documents, dict):
        return documentation_error("documentation.missing_required_field", "$.documents"), {}
    unknown_roles = sorted(set(documents) - KNOWLEDGE_DOCUMENT_ROLES)
    if unknown_roles:
        return documentation_error("documentation.unknown_field", f"$.documents.{unknown_roles[0]}"), {}
    missing_roles = sorted(KNOWLEDGE_DOCUMENT_ROLES - set(documents))
    if missing_roles:
        return documentation_error("documentation.missing_required_field", f"$.documents.{missing_roles[0]}"), {}

    expected_paths = {
        "entry_point": "README.md",
        "decision_record": "vllm-dlc/model-adaptation-and-main-to-main-decisions.md",
        "model_adaptation_prompt": "prompt-examples/vllm-dlc-model-adaptation.md",
        "main_to_main_prompt": "prompt-examples/vllm-dlc-main-to-main-upgrade.md",
    }
    root = knowledge_root.resolve()
    resolved_paths: dict[str, Path] = {}
    for role in sorted(KNOWLEDGE_DOCUMENT_ROLES):
        value = documents[role]
        if (
            not isinstance(value, str)
            or not value
            or Path(value).is_absolute()
            or ".." in Path(value).parts
            or value != expected_paths[role]
        ):
            return documentation_error("documentation.invalid_path", f"$.documents.{role}", role), {}
        path = (root / value).resolve()
        if not path_is_beneath(path, root):
            return documentation_error("link.outside_root", value, role), {}
        if not path.is_file():
            return documentation_error("documentation.missing_document", value, role), {}
        resolved_paths[role] = path
    if len(set(resolved_paths.values())) != len(resolved_paths):
        return documentation_error("documentation.invalid_path", "$.documents"), {}

    links = manifest["required_links"]
    if not isinstance(links, list):
        return documentation_error("documentation.missing_required_field", "$.required_links"), {}
    edges = []
    for index, row in enumerate(links):
        if not isinstance(row, dict):
            return documentation_error("documentation.missing_required_field", f"$.required_links[{index}]"), {}
        unknown_fields = sorted(set(row) - {"from", "to"})
        if unknown_fields:
            return documentation_error("documentation.unknown_field", f"$.required_links[{index}].{unknown_fields[0]}"), {}
        if set(row) != {"from", "to"} or row["from"] not in documents or row["to"] not in documents:
            return documentation_error("documentation.missing_required_field", f"$.required_links[{index}]"), {}
        edges.append((row["from"], row["to"]))
    if set(edges) != REQUIRED_KNOWLEDGE_LINKS or len(edges) != len(REQUIRED_KNOWLEDGE_LINKS):
        return documentation_error("link.required_missing", "$.required_links"), {}

    texts = {
        role: path.read_text(encoding="utf-8") for role, path in resolved_paths.items()
    }
    required_link_results = []
    for source_role, target_role in sorted(REQUIRED_KNOWLEDGE_LINKS):
        target = resolved_paths[target_role]
        destinations = markdown_local_links(texts[source_role])
        matching = any(
            (resolved_paths[source_role].parent / destination).resolve() == target
            for destination in destinations
        )
        if not matching:
            return documentation_error("link.required_missing", documents[source_role], source_role), {}
        required_link_results.append({"from": source_role, "status": "passed", "to": target_role})

    for role in ("decision_record", *sorted(PROMPT_ROLES)):
        source = resolved_paths[role]
        for destination in markdown_local_links(texts[role]):
            if not destination:
                continue
            lexical = source.parent / destination
            resolved = lexical.resolve()
            if not path_is_beneath(resolved, root):
                return documentation_error("link.outside_root", destination, role), {}
            if not resolved.is_file():
                return documentation_error("link.unresolved", destination, role), {}

    ownership = re.compile(r"(?m)^\s*shared_contract:\s*vllm-dlc-contract/v1\s*$")
    for role in ("decision_record", *sorted(PROMPT_ROLES)):
        if not ownership.search(texts[role]):
            code = "prompt.invalid" if role in PROMPT_ROLES else "quality_gate.duplicated"
            return documentation_error(code, documents[role], role), {}
        if contains_duplicate_quality_gate(texts[role].lower()):
            return documentation_error("quality_gate.duplicated", documents[role], role), {}

    decision = texts["decision_record"].lower()
    decision_markers = (
        "当前实现范围", "target architecture decision", "fact", "experience",
        "recommendation", "not verified", "blocked_missing_hardware", "not_verified",
        "read-only", "ticket 06", "ticket 07",
    )
    if any(marker not in decision for marker in decision_markers):
        return documentation_error("documentation.missing_required_field", documents["decision_record"], "decision_record"), {}
    missing_evidence = [name for name in EVIDENCE_CLASSES if name.lower() not in decision]
    if missing_evidence or "fixture_verified" in decision:
        return documentation_error("documentation.missing_required_field", documents["decision_record"], "decision_record"), {}
    if re.search(
        r"(?im)^\s*(?:real weights?|real dlc hardware|acceptance|the workflow)\b"
        r"[^\n]*(?:\bpassed\b|\bverified\b|\bfinalized\b|已通过|已验证|已完成)\s*[。.]*$",
        decision,
    ) or re.search(
        r"(?im)^(?![^\n]*(?:\bnot\b|\bnever\b|\bcannot\b|\bnone\b|\bfalse\b|不得|不能|未|不))"
        r"[^\n]*\b(?:acceptance|finalization|finalize)\b[^\n]*"
        r"\b(?:passed|verified|finalized|complete|completed|eligible)\b[^\n]*$",
        decision,
    ):
        return documentation_error("documentation.missing_required_field", documents["decision_record"], "decision_record"), {}

    prompt_metadata = {}
    for role in sorted(PROMPT_ROLES):
        error, metadata = parse_prompt_document(role, texts[role], documents[role])
        if error:
            return error, {}
        prompt_metadata[role] = metadata

    outcome = {
        "documents": {
            role: {"path": documents[role], "status": "passed"}
            for role in sorted(documents)
        },
        "required_links": required_link_results,
        "evidence_classes": list(EVIDENCE_CLASSES),
        "prompt_identities": {
            role: prompt_metadata[role]["skill_identity"] for role in sorted(PROMPT_ROLES)
        },
        "duplicate_gate_status": "passed",
        "prompt_metadata": prompt_metadata,
    }
    return {"code": "knowledge_package.valid", "status": "passed"}, outcome


def validate_prompt_dry_run(
    fixture: Path, knowledge_root: Path, guarded_root: Path
) -> tuple[dict[str, str], dict[str, Any]]:
    repository_before = repository_snapshot(guarded_root)
    document = json.loads(fixture.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise TypeError("prompt dry run fixture must be a JSON object")
    if document.get("schema_version") != PROMPT_DRY_RUN_SCHEMA:
        return documentation_error("documentation.unsupported_schema_version", "$.schema_version"), {}
    if set(document) != {"schema_version", "knowledge_package", "cases"}:
        return documentation_error("prompt.invalid", "$"), {}
    package_reference = document["knowledge_package"]
    if not isinstance(package_reference, str) or not package_reference or Path(package_reference).is_absolute() or ".." in Path(package_reference).parts:
        return documentation_error("prompt.invalid", "$.knowledge_package"), {}
    fixture_root = fixture.parent.resolve()
    package_file = (fixture_root / package_reference).resolve()
    if not path_is_beneath(package_file, fixture_root) or not package_file.is_file():
        return documentation_error("prompt.invalid", "$.knowledge_package"), {}
    package_check, package_outcome = validate_knowledge_package(package_file, knowledge_root)
    if package_check["status"] != "passed":
        return package_check, {}
    cases = document["cases"]
    if not isinstance(cases, list) or not cases:
        return documentation_error("prompt.invalid", "$.cases"), {}
    transcripts = []
    case_ids = []
    for index, row in enumerate(cases):
        if not isinstance(row, dict) or set(row) != {"id", "prompt_role", "provided_inputs"}:
            return documentation_error("prompt.invalid", f"$.cases[{index}]"), {}
        case_id = row["id"]
        role = row["prompt_role"]
        provided = row["provided_inputs"]
        if not isinstance(case_id, str) or not case_id or role not in PROMPT_ROLES or not isinstance(provided, dict):
            return documentation_error("prompt.invalid", f"$.cases[{index}]"), {}
        case_ids.append(case_id)
        metadata = package_outcome["prompt_metadata"][role]
        declared = metadata["required_inputs"]
        if any(not isinstance(key, str) or key not in declared for key in provided):
            return documentation_error("prompt.invalid", f"$.cases[{index}].provided_inputs"), {}
        for key, value in provided.items():
            nullable = key in {"processor_revision", "lineage_tag"}
            valid = value is None and nullable
            if key in {"target_vllm_full_sha", "candidate_vllm_dlc_full_sha"}:
                valid = isinstance(value, str) and bool(re.fullmatch(SHA_PATTERN, value))
            elif key == "available_device_count":
                valid = type(value) is int and value >= 0
            elif not valid:
                valid = isinstance(value, (str, dict, list, bool, int)) and (
                    not isinstance(value, str) or bool(value.strip())
                )
            if not valid:
                return documentation_error("prompt.invalid", f"$.cases[{index}].provided_inputs.{key}"), {}
        missing_inputs = [name for name in declared if name not in provided]
        if not missing_inputs:
            reason_code = "inputs_complete"
        elif role == "main_to_main_prompt" and "target_vllm_full_sha" not in missing_inputs:
            reason_code = "blocked_missing_contract"
        else:
            reason_code = metadata["missing_input_reason"]
        transcripts.append({
            "id": case_id,
            "prompt_role": role,
            "selected_skill": metadata["skill_identity"],
            "missing_inputs": missing_inputs,
            "status": metadata["missing_input_status"] if missing_inputs else "ready",
            "reason_code": reason_code,
            "shared_contract": metadata["shared_contract"],
            "runner_invoked": False,
            "acceptance_eligible": False,
            "finalize_eligible": False,
            "evidence_states": {
                "real_weights": "not_verified",
                "real_dlc_hardware": "not_verified",
                "chunked_prefill_runtime": "not_verified",
                "dlc_runtime_dispatch": "not_verified",
            },
        })
    if len(case_ids) != len(set(case_ids)):
        return documentation_error("prompt.invalid", "$.cases"), {}
    repository_after = repository_snapshot(guarded_root)
    for transcript in transcripts:
        transcript["repository_before"] = repository_before
        transcript["repository_after"] = repository_after
    return {"code": "prompt_dry_run.valid", "status": "passed"}, {"transcripts": transcripts}


def validate_package(target_file: Path) -> dict[str, str]:
    target = json.loads(target_file.read_text(encoding="utf-8"))
    root = target_file.parent
    identity = target["skill_identity"]
    roles = target.get("roles")
    if not isinstance(roles, dict) or set(roles) != PACKAGE_ROLES:
        return {"code": "publication.inconsistent", "status": "failed"}
    role_paths = {role: root / relative_path for role, relative_path in roles.items()}
    if not all(path.is_file() for path in role_paths.values()):
        return {"code": "publication.inconsistent", "status": "failed"}
    skill = role_paths["skill"].read_text(encoding="utf-8")
    agent = role_paths["agent"].read_text(encoding="utf-8")
    knowledge = role_paths["knowledge"].read_text(encoding="utf-8")
    package_valid = True
    content_error = package_content_error(
        identity,
        skill,
        agent,
        knowledge,
        role_paths["skill"],
    )
    publication_paths = [
        role_paths[role]
        for role in PACKAGE_ROLES - {"skill", "agent", "knowledge"}
    ]
    identity_pattern = re.compile(rf"(?<![A-Za-z0-9_-]){re.escape(identity)}(?![A-Za-z0-9_-])")
    publication_valid = all(
        identity_pattern.search(path.read_text(encoding="utf-8"))
        for path in publication_paths
    ) and len(set(publication_paths)) == 6
    if content_error:
        return content_error
    if package_valid and not publication_valid:
        return {"code": "publication.inconsistent", "status": "failed"}
    return {
        "code": "package.valid" if package_valid else "package.invalid",
        "status": "passed" if package_valid else "failed",
    }


def validate_candidate_package(target_file: Path, skills_root: Path) -> dict[str, str]:
    target = json.loads(target_file.read_text(encoding="utf-8"))
    roles = target.get("roles") if isinstance(target, dict) else None
    if set(target) != {"skill_identity", "roles"} or not isinstance(roles, dict) or set(roles) != CANDIDATE_PACKAGE_ROLES:
        return {"code": "package.invalid", "status": "failed"}
    identity = target.get("skill_identity")
    if not isinstance(identity, str) or not identity:
        return {"code": "package.invalid", "status": "failed"}
    root = target_file.parent
    if any(not isinstance(value, str) for value in roles.values()):
        return {"code": "package.invalid", "status": "failed"}
    paths = {role: (root / value).resolve() for role, value in roles.items()}
    if not all(path.is_file() for path in paths.values()):
        return {"code": "package.invalid", "status": "failed"}
    candidate_root = (skills_root / "skills" / "in-progress" / identity).resolve()
    expected_paths = {
        "skill": candidate_root / "SKILL.md",
        "agent": candidate_root / "agents" / "openai.yaml",
        "knowledge": candidate_root / "knowledge.md",
    }
    if paths != expected_paths:
        return {"code": "package.invalid", "status": "failed"}
    error = package_content_error(
        identity, paths["skill"].read_text(encoding="utf-8"),
        paths["agent"].read_text(encoding="utf-8"),
        paths["knowledge"].read_text(encoding="utf-8"), paths["skill"],
    )
    combined = (
        paths["skill"].read_text(encoding="utf-8")
        + "\n"
        + paths["agent"].read_text(encoding="utf-8")
    ).lower()
    boundary_terms = CANDIDATE_BOUNDARY_TERMS.get(identity)
    if not error and (
        boundary_terms is None or any(term not in combined for term in boundary_terms)
    ):
        error = {"code": "package.invalid", "status": "failed"}
    return error or {"code": "candidate_package.valid", "status": "passed"}


def validate_model_adaptation_routing(
    fixture: Path, skills_root: Path
) -> dict[str, str]:
    document = json.loads(fixture.read_text(encoding="utf-8"))
    expected_owners = {
        "new_model": "model-adaptation",
        "attention_incompatibility": "model-adaptation",
        "main_to_main_delegation": "model-adaptation",
        "upstream_alignment": "main-to-main-upgrade",
        "alignment_recovery": "main-to-main-upgrade",
        "environment_rebuild": "dlc-env-setup",
        "single_operator": "diagnosing-bugs",
        "independent_compile": "compile-capability",
        "smoke_only": "shared-smoke-runner",
    }
    required_prompt_terms = {
        "new_model": {"load", "serve", "dlc platform"},
        "attention_incompatibility": {"attention", "incompatib"},
        "main_to_main_delegation": {"main-to-main", "assignment", "adaptation"},
        "upstream_alignment": {"align", "upstream", "sha"},
        "alignment_recovery": {"recover", "verified vllm alignment"},
        "environment_rebuild": {"rebuild", "dlc ecosystem"},
        "single_operator": {"diagnose", "dlc custom kernel"},
        "independent_compile": {"independent", "compile"},
        "smoke_only": {"only", "smoke"},
    }
    if (
        not isinstance(document, dict)
        or set(document) != {"schema_version", "candidate_package", "cases"}
        or document["schema_version"] != "vllm-dlc-model-adaptation-routing/v1"
        or not isinstance(document["cases"], list)
    ):
        return {"code": "routing.invalid", "status": "failed"}
    candidate = (fixture.parent / document["candidate_package"]).resolve()
    if validate_candidate_package(candidate, skills_root)["status"] != "passed":
        return {"code": "routing.package_mismatch", "status": "failed"}
    ids = []
    for row in document["cases"]:
        if (
            not isinstance(row, dict)
            or set(row) != {"id", "prompt", "expected_owner"}
            or any(not isinstance(row[field], str) or not row[field] for field in row)
        ):
            return {"code": "routing.invalid", "status": "failed"}
        ids.append(row["id"])
        if expected_owners.get(row["id"]) != row["expected_owner"]:
            return {"code": "routing.owner_mismatch", "status": "failed"}
        prompt = row["prompt"].lower()
        if any(term not in prompt for term in required_prompt_terms.get(row["id"], set())):
            return {"code": "routing.prompt_mismatch", "status": "failed"}
    if set(ids) != set(expected_owners) or len(ids) != len(set(ids)):
        return {"code": "routing.invalid", "status": "failed"}
    return {"code": "routing.valid", "status": "passed"}


def validate_main_to_main_routing(
    fixture: Path, skills_root: Path
) -> dict[str, str]:
    document = json.loads(fixture.read_text(encoding="utf-8"))
    expected_owners = {
        "upstream_target": "main-to-main-upgrade",
        "alignment_recovery": "main-to-main-upgrade",
        "compatibility_impact": "main-to-main-upgrade",
        "standalone_model": "model-adaptation",
        "environment_rebuild": "dlc-env-setup",
        "single_operator": "diagnosing-bugs",
        "independent_compile": "compile-capability",
        "release_branch": "release-management",
        "smoke_only": "shared-smoke-runner",
    }
    required_prompt_terms = {
        "upstream_target": {"main", "upstream", "full sha"},
        "alignment_recovery": {"recover", "verified vllm alignment"},
        "compatibility_impact": {"complete", "compatibility impact"},
        "standalone_model": {"specific", "model"},
        "environment_rebuild": {"rebuild", "dlc ecosystem"},
        "single_operator": {"diagnose", "dlc custom kernel"},
        "independent_compile": {"independent", "compile"},
        "release_branch": {"release branch"},
        "smoke_only": {"only", "smoke"},
    }
    if (
        not isinstance(document, dict)
        or set(document) != {"schema_version", "candidate_package", "cases"}
        or document["schema_version"] != "vllm-dlc-main-to-main-routing/v1"
        or not isinstance(document["cases"], list)
    ):
        return {"code": "routing.invalid", "status": "failed"}
    candidate = (fixture.parent / document["candidate_package"]).resolve()
    if validate_candidate_package(candidate, skills_root)["status"] != "passed":
        return {"code": "routing.package_mismatch", "status": "failed"}
    ids = []
    for row in document["cases"]:
        if (
            not isinstance(row, dict)
            or set(row) != {"id", "prompt", "expected_owner"}
            or any(not isinstance(row[field], str) or not row[field] for field in row)
        ):
            return {"code": "routing.invalid", "status": "failed"}
        ids.append(row["id"])
        if expected_owners.get(row["id"]) != row["expected_owner"]:
            return {"code": "routing.owner_mismatch", "status": "failed"}
        prompt = row["prompt"].lower()
        if any(term not in prompt for term in required_prompt_terms.get(row["id"], set())):
            return {"code": "routing.prompt_mismatch", "status": "failed"}
    if set(ids) != set(expected_owners) or len(ids) != len(set(ids)):
        return {"code": "routing.invalid", "status": "failed"}
    return {"code": "routing.valid", "status": "passed"}


def bundle_error(code: str, path: str) -> dict[str, str]:
    return {"code": code, "path": path, "status": "failed"}


def exact_object(value: Any, fields: set[str], path: str) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return bundle_error("contract.invalid_type", path)
    unknown = sorted(set(value) - fields)
    if unknown:
        return bundle_error("contract.unknown_field", f"{path}.{unknown[0]}")
    missing = sorted(fields - set(value))
    if missing:
        return bundle_error("contract.missing_required_field", f"{path}.{missing[0]}")
    return None


def validate_model_adaptation_bundle(bundle: dict[str, Any], guarded_root: Path) -> tuple[dict[str, str], dict[str, Any]]:
    if not isinstance(bundle, dict):
        raise TypeError("model adaptation bundle must be a JSON object")
    if bundle.get("schema_version") != MODEL_ADAPTATION_SCHEMA:
        return bundle_error("contract.unsupported_schema_version", "$.schema_version"), {}
    shape_error = exact_object(bundle, MODEL_ADAPTATION_FIELDS, "$")
    if shape_error:
        return shape_error, {}
    if bundle["workflow"] != "model_adaptation":
        return bundle_error("contract.invalid_value", "$.workflow"), {}
    for field, expected in (("preflight", PREFLIGHT_FIELDS), ("tp_decision", TP_DECISION_FIELDS), ("compatibility", COMPATIBILITY_FIELDS), ("execution", EXECUTION_FIELDS), ("identity", IDENTITY_FIELDS)):
        error = exact_object(bundle[field], expected, f"$.{field}")
        if error:
            return error, {}

    matrix = bundle["capability_matrix"]
    if not isinstance(matrix, list):
        return bundle_error("contract.invalid_type", "$.capability_matrix"), {}
    identities = [row.get("id") for row in matrix if isinstance(row, dict)]
    if len(identities) != len(matrix) or len(identities) != len(set(identities)):
        return bundle_error("contract.invalid_value", "$.capability_matrix"), {}
    missing = sorted(CAPABILITY_IDENTITIES - set(identities))
    unknown = sorted(set(identities) - CAPABILITY_IDENTITIES)
    if missing:
        return bundle_error("contract.missing_required_field", f"$.capability_matrix.{missing[0]}"), {}
    if unknown:
        return bundle_error("contract.unknown_field", f"$.capability_matrix.{unknown[0]}"), {}
    for index, row in enumerate(matrix):
        classification = row.get("classification")
        fields = {"id", "classification", "evidence"}
        if classification == "conditional":
            fields |= {"activation_predicate", "resolved", "active"}
        error = exact_object(row, fields, f"$.capability_matrix[{index}]")
        if error:
            return error, {}
        if classification not in {"required", "conditional", "not_applicable"} or not isinstance(row["evidence"], str) or not row["evidence"]:
            return bundle_error("contract.invalid_value", f"$.capability_matrix[{index}]"), {}
        if classification == "not_applicable" and not re.match(
            r"^(?:model-config|source|model-metadata):\S+", row["evidence"]
        ):
            return bundle_error("contract.invalid_value", f"$.capability_matrix[{index}].evidence"), {}
        if classification == "conditional" and (not isinstance(row["activation_predicate"], str) or not row["activation_predicate"] or type(row["resolved"]) is not bool or type(row["active"]) is not bool):
            return bundle_error("contract.invalid_value", f"$.capability_matrix[{index}]"), {}

    tp = bundle["tp_decision"]
    if type(tp["tensor_parallel_size"]) is not int or tp["tensor_parallel_size"] <= 0:
        return bundle_error("contract.invalid_value", "$.tp_decision.tensor_parallel_size"), {}
    for field in TP_DECISION_FIELDS - {"tensor_parallel_size"}:
        if not isinstance(tp[field], str) or not tp[field]:
            return bundle_error("contract.invalid_value", f"$.tp_decision.{field}"), {}

    preflight = bundle["preflight"]
    for field in {"artifact_destination", "current_branch", "model_path", "model_revision", "required_branch", "tokenizer_revision", "weights_evidence"}:
        if not isinstance(preflight[field], str):
            return bundle_error("contract.invalid_value", f"$.preflight.{field}"), {}
    for field in {"chunk_observability_available", "contract_available", "dispatch_observability_available", "hardware_required", "processor_required", "read_only_boundary_preserved", "required_execution_path_supported"}:
        if type(preflight[field]) is not bool:
            return bundle_error("contract.invalid_value", f"$.preflight.{field}"), {}
    for field in {"available_device_count", "required_device_count"}:
        if type(preflight[field]) is not int or preflight[field] < 0:
            return bundle_error("contract.invalid_value", f"$.preflight.{field}"), {}
    for field in {"model_revision", "tokenizer_revision"}:
        if preflight[field] and not re.fullmatch(SHA_PATTERN, preflight[field]):
            return bundle_error("contract.invalid_value", f"$.preflight.{field}"), {}
    processor = preflight["processor_revision"]
    if processor is not None and (not isinstance(processor, str) or not re.fullmatch(SHA_PATTERN, processor)):
        return bundle_error("contract.invalid_value", "$.preflight.processor_revision"), {}
    if preflight["weights_evidence"] and not re.fullmatch(DIGEST_PATTERN, preflight["weights_evidence"]):
        return bundle_error("contract.invalid_value", "$.preflight.weights_evidence"), {}
    if not Path(preflight["artifact_destination"]).is_absolute():
        return bundle_error("contract.invalid_value", "$.preflight.artifact_destination"), {}

    compatibility = bundle["compatibility"]
    dependencies = compatibility["changed_dependency_ids"]
    if (
        type(compatibility["changed"]) is not bool
        or not isinstance(dependencies, list)
        or any(not isinstance(value, str) or not value for value in dependencies)
        or len(dependencies) != len(set(dependencies))
        or compatibility["changed"] != bool(dependencies)
    ):
        return bundle_error("contract.invalid_value", "$.compatibility.changed_dependency_ids"), {}
    if bundle["alignment_claim"] != "none":
        return bundle_error("contract.invalid_value", "$.alignment_claim"), {}

    identity = bundle["identity"]
    execution = bundle["execution"]
    if not isinstance(identity["expected_model_id"], str) or not identity["expected_model_id"]:
        return bundle_error("contract.invalid_value", "$.identity.expected_model_id"), {}
    for field, preflight_field in {
        "expected_model_revision": "model_revision",
        "expected_tokenizer_revision": "tokenizer_revision",
    }.items():
        if not isinstance(identity[field], str) or not re.fullmatch(SHA_PATTERN, identity[field]) or identity[field] != preflight[preflight_field]:
            return bundle_error("contract.identity_mismatch", f"$.identity.{field}"), {}
    if identity["expected_processor_revision"] != preflight["processor_revision"]:
        return bundle_error("contract.identity_mismatch", "$.identity.expected_processor_revision"), {}
    if not isinstance(identity["expected_deployment_digest"], str) or not re.fullmatch(DIGEST_PATTERN, identity["expected_deployment_digest"]):
        return bundle_error("contract.invalid_value", "$.identity.expected_deployment_digest"), {}
    if identity["parent_run_id"] is not None and (not isinstance(identity["parent_run_id"], str) or not identity["parent_run_id"]):
        return bundle_error("contract.invalid_value", "$.identity.parent_run_id"), {}
    for field in {"runner_requested", "result_acceptance_eligible", "dummy_requested", "dummy_approved", "dummy_acceptance_eligible"}:
        if type(execution[field]) is not bool:
            return bundle_error("contract.invalid_value", f"$.execution.{field}"), {}
    run_spec = bundle["run_spec"]
    result = bundle["result_evidence"]
    handoff = bundle["handoff"]
    if run_spec is not None:
        check = validate_contract(run_spec, guarded_root)
        if check["status"] != "passed":
            return bundle_error(check["code"], "$.run_spec"), {}
        if run_spec["workflow"] != "model_adaptation":
            return bundle_error("contract.identity_mismatch", "$.run_spec.workflow"), {}
        guarded_snapshot = repository_snapshot(guarded_root)
        if run_spec["target"]["vllm_dlc_sha"] != guarded_snapshot["head"]:
            return bundle_error("contract.identity_mismatch", "$.run_spec.target.vllm_dlc_sha"), {}
        profile = run_spec["deployment_profile"]
        expected_identity = {
            "expected_model_id": profile["model_id"],
            "expected_model_revision": profile["model_revision"],
            "expected_tokenizer_revision": profile["tokenizer_revision"],
            "expected_processor_revision": profile["processor_revision"],
            "expected_deployment_digest": value_digest(profile),
        }
        for field, expected in expected_identity.items():
            if identity[field] != expected:
                return bundle_error("contract.identity_mismatch", f"$.identity.{field}"), {}
        profile_bindings = {
            "model_revision": preflight["model_revision"],
            "tokenizer_revision": preflight["tokenizer_revision"],
            "processor_revision": preflight["processor_revision"],
            "tensor_parallel_size": tp["tensor_parallel_size"],
            "dtype": tp["dtype"],
            "quantization": tp["quantization"],
        }
        for field, expected in profile_bindings.items():
            if profile[field] != expected:
                return bundle_error("contract.identity_mismatch", f"$.run_spec.deployment_profile.{field}"), {}
        hardware = run_spec["hardware"]
        if hardware["required"] != preflight["hardware_required"] or (
            hardware["required"]
            and hardware["device_count"] != preflight["required_device_count"]
        ):
            return bundle_error("contract.identity_mismatch", "$.run_spec.hardware"), {}
    if result is not None:
        if execution["runner_requested"] is not True:
            return bundle_error("contract.inconsistent_status", "$.execution.runner_requested"), {}
        check = validate_contract(result, guarded_root)
        if check["status"] != "passed":
            return bundle_error(check["code"], "$.result_evidence"), {}
        if run_spec is None or result["run_id"] != run_spec["run_id"] or result["run_spec_digest"] != run_spec["digest"]:
            return bundle_error("contract.identity_mismatch", "$.result_evidence.run_spec_digest"), {}
        result_gates = {gate["id"]: gate for gate in result["gates"]}
        if set(result_gates) != set(run_spec["gates"]) or any(
            not result_gates[gate_id]["mandatory"] for gate_id in run_spec["gates"]
        ):
            return bundle_error("contract.identity_mismatch", "$.result_evidence.gates"), {}
        result_values = {
            "result_reference": result["digest"],
            "result_environment": result["execution_environment"],
            "result_status": result["overall_status"],
            "result_acceptance_eligible": result["acceptance_eligible"],
        }
        for field, expected in result_values.items():
            if execution[field] != expected:
                return bundle_error("contract.identity_mismatch", f"$.execution.{field}"), {}
    elif execution["runner_requested"] or any(
        execution[field] is not None
        for field in {"result_reference", "result_environment", "result_status"}
    ) or execution["result_acceptance_eligible"]:
        return bundle_error("contract.missing_required_field", "$.result_evidence"), {}

    if result is not None and result["execution_environment"] == "dummy" and not execution["dummy_requested"]:
        return bundle_error("contract.inconsistent_status", "$.execution.dummy_requested"), {}
    if execution["dummy_requested"]:
        prior_spec = bundle["prior_real_weight_run_spec"]
        prior_result = bundle["prior_real_weight_result_evidence"]
        if (
            not execution["dummy_approved"]
            or prior_spec is None
            or prior_result is None
            or execution["dummy_mode"] != "diagnostic_only"
            or execution["dummy_acceptance_eligible"] is not False
            or execution["result_environment"] != "dummy"
            or handoff is not None
        ):
            return bundle_error("contract.inconsistent_status", "$.execution.dummy_requested"), {}
        if validate_contract(prior_spec, guarded_root)["status"] != "passed" or validate_contract(prior_result, guarded_root)["status"] != "passed":
            return bundle_error("contract.inconsistent_status", "$.prior_real_weight_result_evidence"), {}
        if (
            prior_spec["deployment_profile"]["real_weights"] is not True
            or prior_result["execution_environment"] != "real_dlc_hardware"
            or prior_result["overall_status"] != "failed"
            or prior_result["run_id"] != prior_spec["run_id"]
            or prior_result["run_spec_digest"] != prior_spec["digest"]
            or execution["real_weight_failure_reference"] != prior_result["digest"]
        ):
            return bundle_error("contract.inconsistent_status", "$.prior_real_weight_result_evidence"), {}
    elif execution["dummy_approved"] or execution["dummy_mode"] is not None or execution["dummy_acceptance_eligible"] is not False:
        return bundle_error("contract.inconsistent_status", "$.execution.dummy_requested"), {}
    elif bundle["prior_real_weight_run_spec"] is not None or bundle["prior_real_weight_result_evidence"] is not None or execution["real_weight_failure_reference"] is not None:
        return bundle_error("contract.inconsistent_status", "$.execution.real_weight_failure_reference"), {}

    if handoff is not None:
        check = validate_contract(handoff, guarded_root)
        if check["status"] != "passed":
            return bundle_error(check["code"], "$.handoff"), {}
        if run_spec is None or result is None or identity["parent_run_id"] is None:
            return bundle_error("contract.identity_mismatch", "$.handoff"), {}
        expected_handoff = {
            "parent_run_id": identity["parent_run_id"],
            "child_run_id": run_spec["run_id"],
            "target_vllm_sha": run_spec["target"]["vllm_sha"],
            "candidate_vllm_dlc_sha": run_spec["target"]["vllm_dlc_sha"],
            "result_evidence_digest": result["digest"],
            "changed_dependency_ids": dependencies,
            "status": result["overall_status"],
        }
        if result["overall_status"] == "passed" and not result["acceptance_eligible"]:
            return bundle_error("contract.inconsistent_status", "$.handoff.status"), {}
        for field, expected in expected_handoff.items():
            if handoff[field] != expected:
                return bundle_error("contract.identity_mismatch", f"$.handoff.{field}"), {}
    elif identity["parent_run_id"] is not None:
        return bundle_error("contract.missing_required_field", "$.handoff"), {}

    outcome = {"workflow": "model_adaptation", "phase": "runtime_evidence", "status": "not_verified", "reason_code": "not_verified", "runner_invoked": bool(execution["runner_requested"]), "acceptance_eligible": False, "handoff_emitted": bundle["handoff"] is not None, "resume_from": "real_dlc_hardware_evidence"}
    artifact = Path(preflight["artifact_destination"]).resolve()
    blockers = [
        (not preflight["model_path"] or not preflight["model_revision"] or not preflight["weights_evidence"] or not preflight["tokenizer_revision"] or (preflight["processor_required"] and not preflight["processor_revision"]), "preflight", "blocked_missing_asset", "model_assets"),
        (preflight["hardware_required"] and preflight["available_device_count"] < preflight["required_device_count"], "preflight", "blocked_missing_hardware", "hardware_allocation"),
        (preflight["current_branch"] != repository_snapshot(guarded_root)["branch"] or preflight["current_branch"] != preflight["required_branch"], "preflight", "blocked_branch_mismatch", "required_branch"),
        (not preflight["contract_available"], "preflight", "blocked_missing_contract", "shared_contract"),
        (not preflight["chunk_observability_available"] or not preflight["dispatch_observability_available"], "preflight", "blocked_missing_observability", "runtime_observability"),
        (not preflight["required_execution_path_supported"], "capability_matrix", "blocked_unsupported_execution_path", "compatibility_action"),
        (not preflight["read_only_boundary_preserved"] or artifact == guarded_root.resolve() or guarded_root.resolve() in artifact.parents, "preflight", "blocked_read_only_boundary", "external_artifact_destination"),
        (any(row["classification"] == "conditional" and not row["resolved"] for row in matrix), "capability_matrix", "blocked_missing_contract", "conditional_capability_resolution"),
    ]
    for blocked, phase, reason, resume in blockers:
        if blocked:
            if handoff is not None or result is not None or execution["runner_requested"]:
                return bundle_error("contract.inconsistent_status", "$.execution.runner_requested"), {}
            outcome.update(phase=phase, status="blocked", reason_code=reason, runner_invoked=False, handoff_emitted=False, resume_from=resume)
            break
    else:
        if execution["dummy_requested"]:
            outcome.update(phase="dummy_diagnostic", status="diagnostic_only", reason_code="diagnostic_only", runner_invoked=True, acceptance_eligible=False, handoff_emitted=False, resume_from="real_weight_failure")
        elif result is not None and result["overall_status"] == "failed":
            outcome.update(phase="runner", status="failed", reason_code="failed_assertion", runner_invoked=True, resume_from="compatibility_diagnosis")
        elif result is not None and result["overall_status"] == "blocked":
            outcome.update(phase="runner", status="blocked", reason_code="blocked_missing_observability", runner_invoked=True, resume_from="runner_blocker")
        elif result is not None and result["overall_status"] == "passed" and result["execution_environment"] == "real_dlc_hardware" and result["acceptance_eligible"] and run_spec["mode"] == "acceptance":
            outcome.update(phase="sealed_result", status="passed", reason_code="passed", runner_invoked=True, acceptance_eligible=True, resume_from="complete")
    return {"code": "model_adaptation_bundle.valid", "status": "passed"}, outcome


def validate_main_to_main_bundle(
    bundle: dict[str, Any], guarded_root: Path
) -> tuple[dict[str, str], dict[str, Any]]:
    if not isinstance(bundle, dict):
        raise TypeError("main-to-main bundle must be a JSON object")
    if bundle.get("schema_version") != MAIN_TO_MAIN_SCHEMA:
        return bundle_error("contract.unsupported_schema_version", "$.schema_version"), {}
    shape_error = exact_object(bundle, MAIN_TO_MAIN_FIELDS, "$")
    if shape_error:
        return shape_error, {}
    if bundle["workflow"] != "main_to_main":
        return bundle_error("contract.invalid_value", "$.workflow"), {}
    for field, expected in (
        ("target", MAIN_TO_MAIN_TARGET_FIELDS),
        ("preflight", MAIN_TO_MAIN_PREFLIGHT_FIELDS),
        ("baseline", MAIN_TO_MAIN_BASELINE_FIELDS),
        ("history", MAIN_TO_MAIN_HISTORY_FIELDS),
        ("delta", MAIN_TO_MAIN_DELTA_FIELDS),
        ("manifest_impact", MAIN_TO_MAIN_MANIFEST_FIELDS),
        ("freeze", MAIN_TO_MAIN_FREEZE_FIELDS),
        ("regression_policy", MAIN_TO_MAIN_REGRESSION_POLICY_FIELDS),
    ):
        error = exact_object(bundle[field], expected, f"$.{field}")
        if error:
            return error, {}
    target = bundle["target"]
    if not isinstance(target["vllm_sha"], str) or not re.fullmatch(
        SHA_PATTERN, target["vllm_sha"]
    ):
        return bundle_error("contract.missing_identity", "$.target.vllm_sha"), {}
    if target["lineage_tag"] is not None and (
        not isinstance(target["lineage_tag"], str) or not target["lineage_tag"]
    ):
        return bundle_error("contract.invalid_value", "$.target.lineage_tag"), {}
    if not isinstance(bundle["candidate_vllm_dlc_sha"], str) or not re.fullmatch(
        SHA_PATTERN, bundle["candidate_vllm_dlc_sha"]
    ):
        return bundle_error("contract.missing_identity", "$.candidate_vllm_dlc_sha"), {}
    if bundle["candidate_vllm_dlc_sha"] != repository_snapshot(guarded_root)["head"]:
        return bundle_error("contract.identity_mismatch", "$.candidate_vllm_dlc_sha"), {}
    if not isinstance(bundle["parent_run_id"], str) or not bundle["parent_run_id"]:
        return bundle_error("contract.invalid_value", "$.parent_run_id"), {}

    preflight = bundle["preflight"]
    for field in MAIN_TO_MAIN_PREFLIGHT_FIELDS - {"current_branch", "required_branch"}:
        if type(preflight[field]) is not bool:
            return bundle_error("contract.invalid_value", f"$.preflight.{field}"), {}
    for field in {"current_branch", "required_branch"}:
        if not isinstance(preflight[field], str) or not preflight[field]:
            return bundle_error("contract.invalid_value", f"$.preflight.{field}"), {}
    if preflight["required_branch"] != "main":
        return bundle_error("contract.invalid_value", "$.preflight.required_branch"), {}
    actual_branch = repository_snapshot(guarded_root)["branch"]
    if preflight["current_branch"] != actual_branch:
        return bundle_error("contract.identity_mismatch", "$.preflight.current_branch"), {}
    expected_branch_match = preflight["current_branch"] == preflight["required_branch"]
    if preflight["branch_matches_main"] != expected_branch_match:
        return bundle_error("contract.inconsistent_status", "$.preflight.branch_matches_main"), {}

    baseline = bundle["baseline"]
    if not isinstance(baseline["state"], str) or baseline["state"] not in {"fixture_verified", "unknown"}:
        return bundle_error("contract.invalid_value", "$.baseline.state"), {}
    if not isinstance(baseline["candidates"], list):
        return bundle_error("contract.invalid_type", "$.baseline.candidates"), {}
    sources = []
    candidate_ids = []
    for index, candidate in enumerate(baseline["candidates"]):
        error = exact_object(
            candidate,
            MAIN_TO_MAIN_BASELINE_CANDIDATE_FIELDS,
            f"$.baseline.candidates[{index}]",
        )
        if error:
            return error, {}
        if (
            not isinstance(candidate["id"], str)
            or not candidate["id"]
            or not isinstance(candidate["source"], str)
            or candidate["source"] not in BASELINE_SOURCE_ORDER
            or not isinstance(candidate["upstream_sha"], str)
            or not re.fullmatch(SHA_PATTERN, candidate["upstream_sha"])
            or type(candidate["mandatory_evidence_complete"]) is not bool
            or type(candidate["verified_alignment"]) is not bool
            or not isinstance(candidate["revalidation_status"], str)
            or candidate["revalidation_status"] not in {"passed", "not_verified", "not_applicable"}
            or (
                candidate["evidence_digest"] is not None
                and (
                    not isinstance(candidate["evidence_digest"], str)
                    or not re.fullmatch(DIGEST_PATTERN, candidate["evidence_digest"])
                )
            )
        ):
            return bundle_error(
                "contract.invalid_value", f"$.baseline.candidates[{index}]"
            ), {}
        if candidate["verified_alignment"] != candidate["mandatory_evidence_complete"]:
            return bundle_error(
                "contract.inconsistent_status",
                f"$.baseline.candidates[{index}].verified_alignment",
            ), {}
        if candidate["verified_alignment"] and (
            candidate["evidence_digest"] is None
            or candidate["revalidation_status"] != "passed"
            or candidate["source"] in {"checkout_clue", "installation_clue", "readme_clue"}
        ):
            return bundle_error(
                "contract.inconsistent_status",
                f"$.baseline.candidates[{index}].verified_alignment",
            ), {}
        sources.append(candidate["source"])
        candidate_ids.append(candidate["id"])
    expected_sources = list(BASELINE_SOURCE_ORDER[: len(sources)])
    if sources != expected_sources or len(candidate_ids) != len(set(candidate_ids)):
        return bundle_error("contract.invalid_value", "$.baseline.candidates"), {}
    selected = baseline["selected_candidate_id"]
    verified_ids = [
        candidate["id"]
        for candidate in baseline["candidates"]
        if candidate["verified_alignment"]
    ]
    if baseline["state"] == "fixture_verified":
        if len(verified_ids) != 1 or selected != verified_ids[0]:
            return bundle_error("contract.inconsistent_status", "$.baseline"), {}
    elif selected is not None or verified_ids:
        return bundle_error("contract.inconsistent_status", "$.baseline"), {}

    history = bundle["history"]
    if (
        type(history["complete"]) is not bool
        or type(history["discovered_changed_surface_count"]) is not int
        or history["discovered_changed_surface_count"] < 0
        or (
            history["range_evidence_digest"] is not None
            and (
                not isinstance(history["range_evidence_digest"], str)
                or not re.fullmatch(DIGEST_PATTERN, history["range_evidence_digest"])
            )
        )
        or (history["complete"] and history["range_evidence_digest"] is None)
    ):
        return bundle_error("contract.invalid_value", "$.history.complete"), {}
    for field in {"range_start_sha", "range_end_sha"}:
        if not isinstance(history[field], str) or not re.fullmatch(
            SHA_PATTERN, history[field]
        ):
            return bundle_error("contract.missing_identity", f"$.history.{field}"), {}
    if history["range_end_sha"] != target["vllm_sha"]:
        return bundle_error("contract.identity_mismatch", "$.history.range_end_sha"), {}
    selected_candidate = next(
        (
            candidate
            for candidate in baseline["candidates"]
            if candidate["id"] == selected
        ),
        None,
    )
    if selected_candidate is not None and history["range_start_sha"] != selected_candidate["upstream_sha"]:
        return bundle_error("contract.identity_mismatch", "$.history.range_start_sha"), {}

    delta = bundle["delta"]
    if (
        type(delta["declared_changed_surface_count"]) is not int
        or delta["declared_changed_surface_count"] < 0
        or type(delta["declared_unknown_impact_count"]) is not int
        or delta["declared_unknown_impact_count"] < 0
        or not isinstance(delta["surfaces"], list)
    ):
        return bundle_error("contract.invalid_value", "$.delta"), {}
    surface_ids = []
    classification_counts = {classification: 0 for classification in DELTA_CLASSIFICATIONS}
    actual_unknown = 0
    for index, surface in enumerate(delta["surfaces"]):
        error = exact_object(
            surface, MAIN_TO_MAIN_DELTA_ROW_FIELDS, f"$.delta.surfaces[{index}]"
        )
        if error:
            return error, {}
        if (
            not isinstance(surface["id"], str)
            or not surface["id"]
            or not isinstance(surface["evidence"], str)
            or not surface["evidence"]
            or (
                surface["dependency_id"] is not None
                and (
                    not isinstance(surface["dependency_id"], str)
                    or not surface["dependency_id"]
                )
            )
        ):
            return bundle_error(
                "contract.invalid_value", f"$.delta.surfaces[{index}]"
            ), {}
        classification = surface["classification"]
        if not isinstance(classification, str):
            return bundle_error(
                "contract.invalid_value", f"$.delta.surfaces[{index}].classification"
            ), {}
        if classification in DELTA_CLASSIFICATIONS:
            classification_counts[classification] += 1
            if classification == "confirmed_irrelevant" and surface["dependency_id"] is not None:
                return bundle_error(
                    "contract.inconsistent_status",
                    f"$.delta.surfaces[{index}].dependency_id",
                ), {}
            if classification != "confirmed_irrelevant" and surface["dependency_id"] is None:
                return bundle_error(
                    "contract.missing_required_field",
                    f"$.delta.surfaces[{index}].dependency_id",
                ), {}
        elif classification == "unknown":
            actual_unknown += 1
        else:
            return bundle_error(
                "contract.invalid_value", f"$.delta.surfaces[{index}].classification"
            ), {}
        surface_ids.append(surface["id"])
    if len(surface_ids) != len(set(surface_ids)):
        return bundle_error("contract.invalid_value", "$.delta.surfaces"), {}
    if delta["declared_changed_surface_count"] != len(delta["surfaces"]):
        return bundle_error(
            "contract.inconsistent_status", "$.delta.declared_changed_surface_count"
        ), {}
    if delta["declared_unknown_impact_count"] != actual_unknown:
        return bundle_error(
            "contract.inconsistent_status", "$.delta.declared_unknown_impact_count"
        ), {}
    if history["discovered_changed_surface_count"] != len(delta["surfaces"]):
        return bundle_error(
            "contract.inconsistent_status", "$.history.discovered_changed_surface_count"
        ), {}

    manifest = bundle["manifest_impact"]
    if (
        manifest["read_only"] is not True
        or manifest["modified"] is not False
        or manifest["applied_changes"] != []
    ):
        return bundle_error("contract.read_only_boundary", "$.manifest_impact"), {}
    if not isinstance(manifest["manifest_digest"], str) or not re.fullmatch(
        DIGEST_PATTERN, manifest["manifest_digest"]
    ):
        return bundle_error("contract.invalid_value", "$.manifest_impact.manifest_digest"), {}
    if not isinstance(manifest["future_changes"], list):
        return bundle_error("contract.invalid_type", "$.manifest_impact.future_changes"), {}
    manifest_ids = []
    for index, row in enumerate(manifest["future_changes"]):
        error = exact_object(
            row,
            MAIN_TO_MAIN_MANIFEST_ROW_FIELDS,
            f"$.manifest_impact.future_changes[{index}]",
        )
        if error:
            return error, {}
        if (
            not isinstance(row["dependency_id"], str)
            or not row["dependency_id"]
            or not isinstance(row["action"], str)
            or row["action"] not in MANIFEST_ACTIONS
            or not isinstance(row["reason"], str)
            or not row["reason"]
        ):
            return bundle_error(
                "contract.invalid_value", f"$.manifest_impact.future_changes[{index}]"
            ), {}
        manifest_ids.append(row["dependency_id"])
    if len(manifest_ids) != len(set(manifest_ids)):
        return bundle_error("contract.invalid_value", "$.manifest_impact.future_changes"), {}
    expected_manifest_actions = {
        surface["dependency_id"]: (
            {"future_update", "future_remove", "no_change"}
            if surface["classification"] == "affected_dependency"
            else {"future_add"}
        )
        for surface in delta["surfaces"]
        if surface["classification"]
        in {"affected_dependency", "new_dependency_candidate"}
    }
    actual_manifest_actions = {
        row["dependency_id"]: row["action"] for row in manifest["future_changes"]
    }
    if (
        set(actual_manifest_actions) != set(expected_manifest_actions)
        or any(
            actual_manifest_actions[dependency_id] not in allowed_actions
            for dependency_id, allowed_actions in expected_manifest_actions.items()
        )
    ):
        return bundle_error(
            "contract.inconsistent_status", "$.manifest_impact.future_changes"
        ), {}

    assignments = bundle["assignments"]
    if not isinstance(assignments, list):
        return bundle_error("contract.invalid_type", "$.assignments"), {}
    assignment_ids = []
    child_run_ids = []
    deployment_digests = []
    model_identities = []
    mandatory_profiles = []
    for index, assignment in enumerate(assignments):
        error = exact_object(
            assignment,
            MAIN_TO_MAIN_ASSIGNMENT_FIELDS,
            f"$.assignments[{index}]",
        )
        if error:
            return error, {}
        for field in {"assignment_id", "child_run_id", "model_id", "role"}:
            if not isinstance(assignment[field], str) or not assignment[field]:
                return bundle_error(
                    "contract.invalid_value", f"$.assignments[{index}].{field}"
                ), {}
        for field in {"model_revision", "tokenizer_revision"}:
            if not isinstance(assignment[field], str) or not re.fullmatch(
                SHA_PATTERN, assignment[field]
            ):
                return bundle_error(
                    "contract.missing_identity", f"$.assignments[{index}].{field}"
                ), {}
        processor = assignment["processor_revision"]
        if processor is not None and (
            not isinstance(processor, str) or not re.fullmatch(SHA_PATTERN, processor)
        ):
            return bundle_error(
                "contract.missing_identity", f"$.assignments[{index}].processor_revision"
            ), {}
        if (
            type(assignment["mandatory"]) is not bool
            or type(assignment["real_weights_required"]) is not bool
            or type(assignment["tensor_parallel_size"]) is not int
            or assignment["tensor_parallel_size"] <= 0
            or not isinstance(assignment["mode"], str)
            or assignment["mode"] not in {"acceptance", "diagnostic_only"}
            or not isinstance(assignment["hardware_class"], str)
            or assignment["hardware_class"] not in {
                "real_dlc_hardware",
                "fake_server",
                "dlcsim",
                "none",
            }
            or not isinstance(assignment["deployment_digest"], str)
            or not re.fullmatch(DIGEST_PATTERN, assignment["deployment_digest"])
            or not isinstance(assignment["expected_dependency_ids"], list)
            or any(
                not isinstance(dependency, str) or not dependency
                for dependency in assignment["expected_dependency_ids"]
            )
            or len(assignment["expected_dependency_ids"])
            != len(set(assignment["expected_dependency_ids"]))
        ):
            return bundle_error(
                "contract.invalid_value", f"$.assignments[{index}]"
            ), {}
        if assignment["mandatory"] and (
            assignment["mode"] != "acceptance"
            or not assignment["real_weights_required"]
            or assignment["hardware_class"] != "real_dlc_hardware"
        ):
            return bundle_error(
                "contract.inconsistent_status", f"$.assignments[{index}]"
            ), {}
        if not set(assignment["expected_dependency_ids"]).issubset(
            expected_manifest_actions
        ):
            return bundle_error(
                "contract.identity_mismatch",
                f"$.assignments[{index}].expected_dependency_ids",
            ), {}
        if assignment["role"] == "deepseek_diagnostic" and (
            assignment["mandatory"]
            or assignment["mode"] != "diagnostic_only"
            or assignment["tensor_parallel_size"] != 1
        ):
            return bundle_error(
                "contract.inconsistent_status", f"$.assignments[{index}]"
            ), {}
        expected_model_name = {
            "deepseek_distributed": "deepseek-v2-lite-chat",
            "deepseek_diagnostic": "deepseek-v2-lite-chat",
            "llama_dense": "llama-dense",
        }.get(assignment["role"])
        if expected_model_name is not None and assignment["model_id"].lower().rsplit("/", 1)[-1] != expected_model_name:
            return bundle_error(
                "contract.identity_mismatch", f"$.assignments[{index}].model_id"
            ), {}
        assignment_ids.append(assignment["assignment_id"])
        child_run_ids.append(assignment["child_run_id"])
        if assignment["mandatory"]:
            deployment_digests.append(assignment["deployment_digest"])
            model_identities.append(
                (
                    assignment["model_id"],
                    assignment["model_revision"],
                    assignment["tokenizer_revision"],
                    assignment["processor_revision"],
                )
            )
            mandatory_profiles.append(
                (
                    assignment["role"],
                    assignment["tensor_parallel_size"],
                )
            )
    if (
        len(assignment_ids) != len(set(assignment_ids))
        or len(child_run_ids) != len(set(child_run_ids))
        or len(deployment_digests) != len(set(deployment_digests))
        or len(model_identities) != len(set(model_identities))
    ):
        return bundle_error("contract.invalid_value", "$.assignments"), {}
    if sorted(mandatory_profiles) != [
        ("deepseek_distributed", 2),
        ("llama_dense", 1),
    ]:
        return bundle_error("contract.inconsistent_status", "$.assignments"), {}

    assignments_by_id = {
        assignment["assignment_id"]: assignment for assignment in assignments
    }
    child_rows = bundle["child_bundles"]
    if not isinstance(child_rows, list):
        return bundle_error("contract.invalid_type", "$.child_bundles"), {}
    prerequisite_blocked = (
        any(
            not preflight[field]
            for field in {
                "target_available",
                "contract_available",
                "assets_available",
                "hardware_available",
                "observability_available",
                "read_only_boundary_preserved",
            }
        )
        or not preflight["branch_matches_main"]
        or baseline["state"] != "fixture_verified"
        or not history["complete"]
        or actual_unknown > 0
    )
    if child_rows and prerequisite_blocked:
        return bundle_error("contract.inconsistent_status", "$.child_bundles"), {}
    child_assignment_ids = []
    child_statuses = {
        assignment["assignment_id"]: "not_verified"
        for assignment in assignments
        if assignment["mandatory"]
    }
    child_acceptance = {}
    for index, child_row in enumerate(child_rows):
        error = exact_object(
            child_row, MAIN_TO_MAIN_CHILD_FIELDS, f"$.child_bundles[{index}]"
        )
        if error:
            return error, {}
        assignment_id = child_row["assignment_id"]
        assignment = assignments_by_id.get(assignment_id)
        if assignment is None:
            return bundle_error(
                "contract.identity_mismatch",
                f"$.child_bundles[{index}].assignment_id",
            ), {}
        child_assignment_ids.append(assignment_id)
        child_bundle = child_row["model_adaptation_bundle"]
        child_check, child_outcome = validate_model_adaptation_bundle(
            child_bundle, guarded_root
        )
        if child_check["status"] != "passed":
            return bundle_error(
                child_check["code"], f"$.child_bundles[{index}].model_adaptation_bundle"
            ), {}
        run_spec = child_bundle["run_spec"]
        result = child_bundle["result_evidence"]
        handoff = child_bundle["handoff"]
        if run_spec is None or result is None or handoff is None:
            return bundle_error(
                "contract.missing_required_field",
                f"$.child_bundles[{index}].model_adaptation_bundle.handoff",
            ), {}
        profile = run_spec["deployment_profile"]
        expected_values = {
            "parent_run_id": (handoff["parent_run_id"], bundle["parent_run_id"]),
            "child_run_id": (handoff["child_run_id"], assignment["child_run_id"]),
            "target_vllm_sha": (handoff["target_vllm_sha"], target["vllm_sha"]),
            "candidate_vllm_dlc_sha": (
                handoff["candidate_vllm_dlc_sha"],
                bundle["candidate_vllm_dlc_sha"],
            ),
            "model_id": (profile["model_id"], assignment["model_id"]),
            "model_revision": (
                profile["model_revision"],
                assignment["model_revision"],
            ),
            "tokenizer_revision": (
                profile["tokenizer_revision"],
                assignment["tokenizer_revision"],
            ),
            "processor_revision": (
                profile["processor_revision"],
                assignment["processor_revision"],
            ),
            "tensor_parallel_size": (
                profile["tensor_parallel_size"],
                assignment["tensor_parallel_size"],
            ),
            "deployment_digest": (
                value_digest(profile),
                assignment["deployment_digest"],
            ),
            "result_evidence_digest": (
                handoff["result_evidence_digest"],
                result["digest"],
            ),
            "changed_dependency_ids": (
                handoff["changed_dependency_ids"],
                assignment["expected_dependency_ids"],
            ),
            "manifest_digest": (
                run_spec["target"]["manifest_digest"],
                manifest["manifest_digest"],
            ),
        }
        for field, (actual, expected) in expected_values.items():
            if actual != expected:
                return bundle_error(
                    "contract.identity_mismatch",
                    f"$.child_bundles[{index}].{field}",
                ), {}
        if handoff["status"] != result["overall_status"]:
            return bundle_error(
                "contract.identity_mismatch", f"$.child_bundles[{index}].status"
            ), {}
        status = result["overall_status"]
        role_gate = (
            "dlccl_lyp_distributed"
            if assignment["role"] == "deepseek_distributed"
            else "dense_attention_generation"
        )
        required_regression_gates = {
            "service_ready",
            "models_api",
            "completions_api",
            "chat_api",
            "long_prefix_api",
            "server_liveness",
            "chunked_prefill",
            "runtime_dispatch",
            "real_dlc_hardware",
            role_gate,
        }
        if result["acceptance_eligible"] and not required_regression_gates.issubset(
            set(run_spec["gates"])
        ):
            return bundle_error(
                "contract.missing_required_field",
                f"$.child_bundles[{index}].mandatory_gates",
            ), {}
        child_acceptance[assignment_id] = bool(
            child_outcome.get("acceptance_eligible")
            and run_spec["mode"] == "acceptance"
            and run_spec["deployment_profile"]["real_weights"]
            and result["execution_environment"] == "real_dlc_hardware"
            and all(
                gate["status"] == "passed"
                for gate in result["gates"]
                if gate["mandatory"]
            )
        )
        if assignment["mandatory"]:
            child_statuses[assignment_id] = status
    if len(child_assignment_ids) != len(set(child_assignment_ids)):
        return bundle_error("contract.invalid_value", "$.child_bundles"), {}

    freeze = bundle["freeze"]
    if any(type(freeze[field]) is not bool for field in MAIN_TO_MAIN_FREEZE_FIELDS):
        return bundle_error("contract.invalid_value", "$.freeze"), {}
    guarded_snapshot = repository_snapshot(guarded_root)
    repository_revision_unique = (
        guarded_snapshot["status"] == ""
        and guarded_snapshot["tracked_diff_digest"]
        == "sha256:" + hashlib.sha256(b"").hexdigest()
        and guarded_snapshot["index_diff_digest"]
        == "sha256:" + hashlib.sha256(b"").hexdigest()
        and guarded_snapshot["untracked_content_digest"]
        == "sha256:" + hashlib.sha256(b"").hexdigest()
    )
    if freeze["tested_revision_unique"] != repository_revision_unique:
        return bundle_error("contract.identity_mismatch", "$.freeze.tested_revision_unique"), {}
    if not repository_revision_unique and not freeze["commit_required"]:
        return bundle_error("contract.inconsistent_status", "$.freeze.commit_required"), {}
    regression_policy = bundle["regression_policy"]
    if (
        regression_policy["schema_version"]
        != "vllm-dlc-main-to-main-regression-policy/v1"
        or not isinstance(regression_policy["status"], str)
        or regression_policy["status"] not in {"verified", "not_verified"}
        or (
            regression_policy["digest"] is not None
            and (
                not isinstance(regression_policy["digest"], str)
                or not re.fullmatch(DIGEST_PATTERN, regression_policy["digest"])
            )
        )
        or (
            regression_policy["status"] == "verified"
            and regression_policy["digest"] is None
        )
    ):
        return bundle_error("contract.invalid_value", "$.regression_policy"), {}
    claims_error = exact_object(bundle["claims"], MAIN_TO_MAIN_CLAIM_FIELDS, "$.claims")
    if claims_error:
        return claims_error, {}
    if bundle["claims"] != {
        "alignment_action": "unchanged",
        "manifest_action": "report_only",
        "finalize_action": "none",
    }:
        return bundle_error("contract.inconsistent_status", "$.claims"), {}
    outcome = {
        "workflow": "main_to_main",
        "phase": "mandatory_child_evidence",
        "status": "not_verified",
        "reason_code": "not_verified",
        "acceptance_eligible": False,
        "finalize_eligible": False,
        "alignment_outcome": "unchanged",
        "manifest_outcome": "report_only",
        "resume_from": "real_dlc_hardware_evidence",
        "evidence_states": {
            "real_weights": "not_verified",
            "real_dlc_hardware": "not_verified",
            "chunked_prefill_runtime": "not_verified",
            "dlc_runtime_dispatch": "not_verified",
        },
        "changed_surface_count": len(delta["surfaces"]),
        "unknown_impact_count": actual_unknown,
        "delta_classification_counts": classification_counts,
        "manifest_future_change_count": len(manifest["future_changes"]),
        "mandatory_assignments": [
            {
                "assignment_id": assignment["assignment_id"],
                "role": assignment["role"],
                "tensor_parallel_size": assignment["tensor_parallel_size"],
            }
            for assignment in assignments
            if assignment["mandatory"]
        ],
        "child_statuses": child_statuses,
    }
    blockers = [
        (not preflight["target_available"], "blocked_missing_target", "target_identity"),
        (not preflight["branch_matches_main"], "blocked_branch_mismatch", "required_branch"),
        (not preflight["contract_available"], "blocked_missing_contract", "shared_contract"),
        (not preflight["assets_available"], "blocked_missing_asset", "approved_assets"),
        (not preflight["hardware_available"], "blocked_missing_hardware", "hardware_allocation"),
        (not preflight["observability_available"], "blocked_missing_observability", "runtime_observability"),
        (not preflight["read_only_boundary_preserved"], "blocked_read_only_boundary", "read_only_boundary"),
    ]
    for blocked, reason, resume in blockers:
        if blocked:
            outcome.update(
                phase="preflight",
                status="blocked",
                reason_code=reason,
                resume_from=resume,
            )
            break
    else:
        if baseline["state"] == "unknown":
            outcome.update(
                phase="baseline_recovery",
                status="blocked",
                reason_code="blocked_missing_verified_alignment",
                resume_from="verified_alignment_evidence",
                baseline_state="unknown",
            )
        else:
            outcome["baseline_state"] = "fixture_verified"
            if not history["complete"]:
                outcome.update(
                    phase="upstream_history",
                    status="blocked",
                    reason_code="blocked_incomplete_upstream_history",
                    resume_from="complete_upstream_history",
                )
            elif actual_unknown:
                outcome.update(
                    phase="upstream_delta",
                    status="blocked",
                    reason_code="blocked_unresolved_compatibility_impact",
                    resume_from="classify_upstream_delta",
                )
            else:
                mandatory_statuses = set(child_statuses.values())
                aggregate = next(
                    (
                        status
                        for status in ("failed", "blocked", "not_verified")
                        if status in mandatory_statuses
                    ),
                    "passed",
                )
                all_children_eligible = all(
                    child_acceptance.get(assignment["assignment_id"], False)
                    for assignment in assignments
                    if assignment["mandatory"]
                )
                if aggregate != "passed" or not all_children_eligible:
                    outcome.update(
                        phase="mandatory_child_evidence",
                        status=aggregate if aggregate != "passed" else "not_verified",
                        reason_code=(
                            f"mandatory_child_{aggregate}"
                            if aggregate != "passed" and child_rows
                            else "not_verified"
                        ),
                        resume_from="mandatory_child_evidence",
                    )
                else:
                    freeze_blockers = [
                        (not freeze["tested_revision_unique"], "blocked_non_unique_tested_revision", "unique_tested_revision"),
                        (freeze["commit_required"] and not freeze["commit_authorized"], "blocked_missing_commit_authorization", "commit_authorization"),
                        (freeze["evidence_stale"], "blocked_stale_evidence", "refresh_stale_evidence"),
                    ]
                    freeze_blocker = next((item for item in freeze_blockers if item[0]), None)
                    if freeze_blocker:
                        _, reason, resume = freeze_blocker
                        outcome.update(
                            phase="freeze_candidate",
                            status="blocked",
                            reason_code=reason,
                            resume_from=resume,
                        )
                    elif regression_policy["status"] != "verified":
                        outcome.update(
                            phase="mandatory_child_evidence",
                            status="not_verified",
                            reason_code="blocked_missing_regression_policy",
                            resume_from="verified_regression_policy",
                        )
                    else:
                        outcome.update(
                            phase="finalize_eligibility",
                            status="not_verified",
                            reason_code="not_verified",
                            acceptance_eligible=False,
                            finalize_eligible=False,
                            resume_from="ticket06_real_dlc_hardware_evidence",
                        )
    return {"code": "main_to_main_bundle.valid", "status": "passed"}, outcome


def validate_live_package(skills_root: Path, knowledge_root: Path, identity: str) -> dict[str, str]:
    skill_root = skills_root / "skills" / "engineering" / identity
    skill_file = skill_root / "SKILL.md"
    required_files = [
        skill_file,
        skill_root / "agents" / "openai.yaml",
        skills_root / "README.md",
        skills_root / "skills" / "engineering" / "README.md",
        skills_root / ".claude-plugin" / "plugin.json",
        skills_root / "SKILLHUB.yaml",
        skills_root / "scripts" / "link-kilo-skills.sh",
        skills_root / "README.zh-CN.md",
        knowledge_root / "vllm-dlc" / "model-adaptation-and-main-to-main-decisions.md",
    ]
    if not all(path.is_file() for path in required_files):
        return {"code": "publication.inconsistent", "status": "failed"}
    publication_files = required_files[2:8]
    identity_pattern = re.compile(rf"(?<![A-Za-z0-9_-]){re.escape(identity)}(?![A-Za-z0-9_-])")
    if not all(
        identity_pattern.search(path.read_text(encoding="utf-8"))
        for path in publication_files
    ):
        return {"code": "publication.inconsistent", "status": "failed"}
    skill = skill_file.read_text(encoding="utf-8")
    agent = (skill_root / "agents" / "openai.yaml").read_text(encoding="utf-8")
    knowledge = required_files[-1].read_text(encoding="utf-8")
    content_error = package_content_error(identity, skill, agent, knowledge, skill_file)
    if content_error:
        return content_error
    return {"code": "package.valid", "status": "passed"}


def invalid_input_report(
    error: Exception,
    root: Path | None,
    before: dict[str, str] | None = None,
) -> int:
    after = None
    if root is not None:
        try:
            after = repository_snapshot(root)
        except (OSError, subprocess.CalledProcessError):
            after = None
    repository_state = "not_verified"
    if before is not None and after is not None:
        repository_state = "preserved" if before == after else "changed"
    report: dict[str, Any] = {
        "checks": [{"code": "input.invalid", "status": "failed"}],
        "contract_version": CONTRACT_VERSION,
        "overall_status": "failed",
        "repository_state": repository_state,
    }
    if before is not None and after is not None:
        report["repository_before"] = before
        report["repository_after"] = after
    emit(report)
    print(f"invalid_input: {error}", file=sys.stderr)
    return 50 if repository_state == "changed" else 10


def main() -> int:
    bootstrapped_root = bootstrap_guard_root(sys.argv[1:])
    bootstrapped_before = None
    if bootstrapped_root is not None:
        try:
            bootstrapped_before = repository_snapshot(bootstrapped_root)
        except (OSError, subprocess.CalledProcessError):
            pass
    parser = ArgumentErrorParser(allow_abbrev=False)
    parser.add_argument("--skills-root", required=True, type=Path)
    parser.add_argument("--knowledge-root", required=True, type=Path)
    parser.add_argument("--vllm-dlc-root", required=True, type=Path)
    subparsers = parser.add_subparsers(dest="target", required=True)
    contract = subparsers.add_parser("contract")
    contract.add_argument("fixture", type=Path)
    package = subparsers.add_parser("package")
    package.add_argument("fixture", type=Path)
    candidate_package = subparsers.add_parser("candidate-package")
    candidate_package.add_argument("fixture", type=Path)
    model_adaptation = subparsers.add_parser("model-adaptation-bundle")
    model_adaptation.add_argument("fixture", type=Path)
    main_to_main = subparsers.add_parser("main-to-main-bundle")
    main_to_main.add_argument("fixture", type=Path)
    routing = subparsers.add_parser("model-adaptation-routing")
    routing.add_argument("fixture", type=Path)
    main_routing = subparsers.add_parser("main-to-main-routing")
    main_routing.add_argument("fixture", type=Path)
    knowledge_package = subparsers.add_parser("knowledge-package")
    knowledge_package.add_argument("fixture", type=Path)
    prompt_dry_run = subparsers.add_parser("prompt-dry-run")
    prompt_dry_run.add_argument("fixture", type=Path)
    operational_reference = subparsers.add_parser("operational-result-reference")
    operational_reference.add_argument("fixture", type=Path)
    ticket06_evidence = subparsers.add_parser("ticket06-evidence")
    ticket06_evidence.add_argument("fixture", type=Path)
    model_operational = subparsers.add_parser("model-adaptation-operational")
    model_operational.add_argument("fixture", type=Path)
    main_operational = subparsers.add_parser("main-to-main-operational")
    main_operational.add_argument("fixture", type=Path)
    guard = subparsers.add_parser("repository-guard")
    guard.add_argument("fixture", type=Path)
    live_package = subparsers.add_parser("live-package")
    live_package.add_argument("skill_identity")
    try:
        arguments = parser.parse_args()
    except ValueError as error:
        return invalid_input_report(error, bootstrapped_root, bootstrapped_before)

    before = bootstrapped_before
    try:
        before = (
            bootstrapped_before
            if bootstrapped_root == arguments.vllm_dlc_root
            and bootstrapped_before is not None
            else repository_snapshot(arguments.vllm_dlc_root)
        )
        if arguments.target == "live-package":
            contract_check = validate_live_package(
                arguments.skills_root,
                arguments.knowledge_root,
                arguments.skill_identity,
            )
        elif arguments.target == "repository-guard":
            expected = json.loads(arguments.fixture.read_text(encoding="utf-8"))
            contract_check = {
                "code": (
                    "repository_state.expected"
                    if expected == before
                    else "repository_state.changed"
                ),
                "status": "passed" if expected == before else "failed",
            }
        elif arguments.target == "package":
            contract_check = validate_package(arguments.fixture)
        elif arguments.target == "candidate-package":
            contract_check = validate_candidate_package(arguments.fixture, arguments.skills_root)
        elif arguments.target == "model-adaptation-bundle":
            document = json.loads(arguments.fixture.read_text(encoding="utf-8"))
            contract_check, outcome = validate_model_adaptation_bundle(
                document, arguments.vllm_dlc_root
            )
        elif arguments.target == "model-adaptation-routing":
            contract_check = validate_model_adaptation_routing(
                arguments.fixture, arguments.skills_root
            )
        elif arguments.target == "main-to-main-bundle":
            document = json.loads(arguments.fixture.read_text(encoding="utf-8"))
            contract_check, outcome = validate_main_to_main_bundle(
                document, arguments.vllm_dlc_root
            )
        elif arguments.target == "main-to-main-routing":
            contract_check = validate_main_to_main_routing(
                arguments.fixture, arguments.skills_root
            )
        elif arguments.target == "knowledge-package":
            contract_check, outcome = validate_knowledge_package(
                arguments.fixture, arguments.knowledge_root
            )
        elif arguments.target == "prompt-dry-run":
            contract_check, outcome = validate_prompt_dry_run(
                arguments.fixture,
                arguments.knowledge_root,
                arguments.vllm_dlc_root,
            )
        elif arguments.target == "operational-result-reference":
            contract_check, outcome = validate_operational_result_reference(
                arguments.fixture, arguments.vllm_dlc_root
            )
        elif arguments.target == "ticket06-evidence":
            contract_check, outcome = validate_ticket06_evidence(
                arguments.fixture, arguments.vllm_dlc_root
            )
        elif arguments.target == "model-adaptation-operational":
            contract_check, outcome = validate_model_adaptation_operational(
                arguments.fixture, arguments.vllm_dlc_root
            )
        elif arguments.target == "main-to-main-operational":
            contract_check, outcome = validate_main_to_main_operational(
                arguments.fixture, arguments.vllm_dlc_root
            )
        else:
            document = json.loads(arguments.fixture.read_text(encoding="utf-8"))
            contract_check = validate_contract(document, arguments.vllm_dlc_root)
    except (OSError, UnicodeError, subprocess.CalledProcessError, json.JSONDecodeError, KeyError, TypeError, AttributeError) as error:
        return invalid_input_report(error, arguments.vllm_dlc_root, before)
    valid = contract_check["status"] == "passed"
    after = repository_snapshot(arguments.vllm_dlc_root)
    preserved = before == after
    passed = valid and preserved
    report = {
            "checks": [
                contract_check,
                {
                    "code": "repository_state.preserved",
                    "status": "passed" if preserved else "failed",
                },
            ],
            "contract_version": CONTRACT_VERSION,
            "overall_status": "passed" if passed else "failed",
            "repository_before": before,
            "repository_after": after,
        }
    if arguments.target in {
        "model-adaptation-bundle",
        "main-to-main-bundle",
        "knowledge-package",
        "prompt-dry-run",
        "operational-result-reference",
        "ticket06-evidence",
        "model-adaptation-operational",
        "main-to-main-operational",
    } and valid:
        report.update(outcome)
    emit(report)
    if passed:
        return 0
    print(f"{contract_check['code']}: validation failed", file=sys.stderr)
    if contract_check["code"] == "publication.inconsistent":
        return 30
    if contract_check["code"] == "quality_gate.duplicated":
        return 40
    if contract_check["code"] == "repository_state.changed" or not preserved:
        return 50
    return 20


def validate_contract(
    document: dict[str, Any], guarded_root: Path
) -> dict[str, str]:
        if not isinstance(document, dict):
            raise TypeError("contract document must be a JSON object")
        if (
            document.get("contract_kind") == "run_spec"
            and document.get("schema_version") == "vllm-dlc-run-spec/v2"
        ):
            return validate_run_spec_v2(document, guarded_root)
        schema = SCHEMAS.get(document.get("contract_kind"))
        expected_version, allowed_fields = schema or (None, set())
        unknown_fields = sorted(set(document) - allowed_fields)
        missing_fields = sorted(REQUIRED_FIELDS.get(document.get("contract_kind"), set()) - set(document))
        if document.get("contract_kind") == "result_evidence" and (
            not isinstance(document.get("gates"), list)
            or any(not isinstance(gate, dict) for gate in document.get("gates", []))
        ):
            nested_error = {
                "code": "contract.invalid_type",
                "path": "$.gates",
                "status": "failed",
            }
        else:
            nested_error = nested_shape_error(document)
        value_error = semantic_error(document) if not missing_fields and not nested_error else None
        if document.get("schema_version") != expected_version:
            contract_check = {
                "code": "contract.unsupported_schema_version",
                "path": "$.schema_version",
                "status": "failed",
            }
        elif unknown_fields:
            contract_check = {
                "code": "contract.unknown_field",
                "path": f"$.{unknown_fields[0]}",
                "status": "failed",
            }
        elif missing_fields:
            contract_check = {
                "code": "contract.missing_required_field",
                "path": f"$.{missing_fields[0]}",
                "status": "failed",
            }
        elif nested_error:
            contract_check = nested_error
        elif value_error:
            contract_check = value_error
        elif document["contract_kind"] == "run_spec" and (
            Path(document["artifact_destination"]).resolve() == guarded_root.resolve()
            or guarded_root.resolve() in Path(document["artifact_destination"]).resolve().parents
        ):
            contract_check = {
                "code": "contract.read_only_destination",
                "path": "$.artifact_destination",
                "status": "failed",
            }
        elif document["contract_kind"] == "run_spec" and next(
            (
                f"$.target.{field}"
                for field in ("vllm_sha", "vllm_dlc_sha")
                if not re.fullmatch(r"[0-9a-f]{40}", document["target"][field])
            ),
            None,
        ) is not None:
            invalid_path = next(
                f"$.target.{field}"
                for field in ("vllm_sha", "vllm_dlc_sha")
                if not re.fullmatch(r"[0-9a-f]{40}", document["target"][field])
            )
            contract_check = {
                "code": "contract.missing_identity",
                "path": invalid_path,
                "status": "failed",
            }
        elif document["contract_kind"] == "parent_child_handoff" and not all(
            re.fullmatch(r"[0-9a-f]{40}", document.get(field, ""))
            for field in ("target_vllm_sha", "candidate_vllm_dlc_sha")
        ):
            contract_check = {
                "code": "contract.missing_identity",
                "path": "$.target_vllm_sha",
                "status": "failed",
            }
        elif (
            document["contract_kind"] == "parent_child_handoff"
            and document.get("status") not in GATE_STATUSES - {"not_applicable"}
        ):
            contract_check = {
                "code": "contract.invalid_status",
                "path": "$.status",
                "status": "failed",
            }
        elif document["contract_kind"] == "result_evidence" and any(
            gate.get("status") not in GATE_STATUSES
            for gate in document.get("gates", [])
        ):
            contract_check = {
                "code": "contract.invalid_status",
                "path": "$.gates",
                "status": "failed",
            }
        elif document["contract_kind"] == "result_evidence" and any(
            set(gate) != {"id", "mandatory", "status", "evidence_digest"}
            or not isinstance(gate.get("id"), str)
            or not isinstance(gate.get("mandatory"), bool)
            or not re.fullmatch(
                r"sha256:[0-9a-f]{64}", gate.get("evidence_digest", "")
            )
            for gate in document.get("gates", [])
        ):
            contract_check = {
                "code": "contract.invalid_gate",
                "path": "$.gates",
                "status": "failed",
            }
        elif document["contract_kind"] == "result_evidence" and (
            (
                document.get("execution_environment")
                in {"dummy", "fake_server", "dlcsim", "static"}
                and document.get("acceptance_eligible") is not False
            )
            or (
                document.get("overall_status") == "passed"
                and any(
                    gate.get("mandatory")
                    and gate.get("status") in {"failed", "blocked", "not_verified"}
                    for gate in document.get("gates", [])
                )
            )
        ):
            contract_check = {
                "code": "contract.inconsistent_status",
                "path": "$.overall_status",
                "status": "failed",
            }
        elif document.get("digest") != canonical_digest(document):
            contract_check = {
                "code": "contract.digest_mismatch",
                "path": "$.digest",
                "status": "failed",
            }
        else:
            contract_check = {"code": "contract.valid", "status": "passed"}
        return contract_check


if __name__ == "__main__":
    raise SystemExit(main())
