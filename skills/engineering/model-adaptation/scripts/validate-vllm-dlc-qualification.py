#!/usr/bin/env python3
"""Validate distributed collective qualification artifacts and preflight them."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from typing import Any


SHARED_PATH = Path(__file__).with_name("_generated_contracts") / "qualification_artifact.py"
SHARED_SPEC = importlib.util.spec_from_file_location("qualification_artifact", SHARED_PATH)
if SHARED_SPEC is None or SHARED_SPEC.loader is None:
    raise RuntimeError("cannot load qualification artifact envelope")
SHARED = importlib.util.module_from_spec(SHARED_SPEC)
SHARED_SPEC.loader.exec_module(SHARED)

SCHEMAS = {
    "vllm-dlc-distributed-collective-qualification/v1",
    "vllm-dlc-distributed-collective-qualification/v2",
}
SCHEMA_V1 = "vllm-dlc-distributed-collective-qualification/v1"
SCHEMA_V2 = "vllm-dlc-distributed-collective-qualification/v2"
ROUTE_CLASSES = {
    "native_dlc_cl", "pytorch_process_group", "vllm_communicator",
    "model_route", "moe_dispatch", "moe_combine", "custom_kernel",
}
PRIMITIVES = {
    "all_reduce", "all_gather", "all_gather_into_tensor", "gather",
    "reduce_scatter", "reduce_scatter_v", "all_gather_v", "all_to_all",
    "send", "recv", "moe_dispatch", "moe_combine",
}
QUALIFICATION_STATES = {"qualified", "not_qualified", "unsupported", "not_applicable"}
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")

QUALIFICATION_FIELDS = {
    "route_inventory", "primitive_inventory", "required_route_ids", "preflight", "execution",
    "blocker_details", "correctness_oracles",
}
PREFLIGHT_FIELDS = {
    "hardware_environment", "hardware_available", "authorization_granted",
    "requested_operation",
}
ROUTE_FIELDS = {
    "route_id", "route_class", "primitive", "active", "route", "backend",
    "dtype", "shape_or_count", "rank", "world_size", "rank_order", "stream",
    "asynchronous", "completion_boundary", "fallback", "qualification_status",
    "identity",
}
ROUTE_V2_FIELDS = ROUTE_FIELDS | {"selection"}
IDENTITY_FIELDS = {"source_sha", "binary_sha256", "abi_digest", "symbol"}
SELECTION_FIELDS = {
    "selector", "topology_digest", "payload_bytes", "constraints",
    "rank_domain", "rank_order", "strategy", "cache_key_digest", "fallback",
}
SELECTOR_FIELDS = {"source_sha", "binary_sha256", "symbol"}
CONSTRAINT_FIELDS = {
    "min_payload_bytes", "max_payload_bytes", "payload_alignment_bytes",
    "dtypes", "layouts", "actual_layout",
}
RANK_DOMAIN_FIELDS = {
    "domain", "primary_root", "secondary_root", "logical_to_physical",
}
STRATEGY_FIELDS = {
    "strategy_id", "consumer_route_id", "metadata_abi_digest", "rank_domain",
    "requires_secondary_root",
}
FALLBACK_FIELDS = {
    "preferred_strategy_id", "candidate_strategy_id", "validation_state",
    "validation", "committed",
}
FALLBACK_VALIDATION_FIELDS = {
    "graph", "channel", "rank_order", "rank_range", "unique_ranks",
    "root_metadata", "payload", "alignment",
}
EXECUTION_FIELDS = {
    "harness_command", "attempt_count", "timeout_seconds", "watchdog_actions",
    "rank_results", "correctness", "process_tree_cleanup", "health_snapshot",
}
RANK_FIELDS = {"attempt", "rank", "exit_code", "status"}
CLEANUP_FIELDS = {"termination_requested", "inspection_complete", "residual_pids", "hbm_status", "status"}
HEALTH_FIELDS = {"status", "source", "snapshot_digest"}
CORRECTNESS_FIELDS = {"attempt", "status", "primitive_results"}
PRIMITIVE_RESULT_FIELDS = {"primitive", "expected_digest", "actual_digest", "status"}
ORACLE_FIELDS = {"primitive", "expected_digest", "input_digest"}
DETAIL_FIELDS = {"status", "code", "path", "phase", "message", "resume_point"}
STATUS_RANK = {"failed": 0, "blocked": 1, "not_verified": 2}


class ContractError(Exception):
    def __init__(self, code: str, path: str, message: str):
        super().__init__(message)
        self.code = code
        self.path = path
        self.message = message


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def artifact_digest(document: dict[str, Any]) -> str:
    return SHARED.canonical_digest(document)


def selection_cache_digest(selection: dict[str, Any], route: dict[str, Any]) -> str:
    inputs = {
        "selection": {
            field: selection[field]
            for field in sorted(SELECTION_FIELDS - {"cache_key_digest"})
        },
        "route": {
            field: route[field]
            for field in (
                "route_id", "route_class", "primitive", "backend", "dtype",
                "rank", "world_size", "identity",
            )
        },
    }
    return "sha256:" + hashlib.sha256(canonical_bytes(inputs)).hexdigest()


def refresh_selection_digests(
    selection: dict[str, Any], route: dict[str, Any]
) -> None:
    selection["cache_key_digest"] = selection_cache_digest(selection, route)


def exact_object(value: Any, fields: set[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError("contract.invalid_type", path, "expected object")
    unknown = set(value) - fields
    missing = fields - set(value)
    if unknown:
        field = sorted(unknown)[0]
        raise ContractError("contract.unknown_field", f"{path}.{field}", "unknown field")
    if missing:
        field = sorted(missing)[0]
        raise ContractError(
            "contract.missing_required_field", f"{path}.{field}", "missing field"
        )
    return value


def nonempty(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError("contract.invalid_value", path, "expected non-empty string")
    return value


def validate_permutation(value: Any, world_size: int, path: str) -> None:
    if (
        not isinstance(value, list)
        or len(value) != world_size
        or any(type(rank) is not int for rank in value)
        or set(value) != set(range(world_size))
    ):
        raise ContractError(
            "contract.invalid_value", path,
            "rank order must be a complete unique in-range permutation",
        )


def validate_selection(
    value: Any,
    route: dict[str, Any],
    path: str,
    hardware_topology_digest: str,
) -> None:
    if value is None:
        if route["active"] and route["route_class"] == "vllm_communicator" and route["primitive"] == "all_reduce":
            raise ContractError("contract.missing_required_field", path, "topology-aware route requires selection")
        return
    if (
        not route["active"]
        or route["route_class"] != "vllm_communicator"
        or route["primitive"] != "all_reduce"
    ):
        raise ContractError(
            "contract.invalid_value", path,
            "selection is owned only by the topology-aware communicator route",
        )
    selection = exact_object(value, SELECTION_FIELDS, path)
    selector = exact_object(selection["selector"], SELECTOR_FIELDS, f"{path}.selector")
    required_identity(selector["source_sha"], f"{path}.selector.source_sha", SHA_RE)
    required_identity(selector["binary_sha256"], f"{path}.selector.binary_sha256", DIGEST_RE)
    nonempty(selector["symbol"], f"{path}.selector.symbol")
    required_identity(selection["topology_digest"], f"{path}.topology_digest", DIGEST_RE)
    if selection["topology_digest"] != hardware_topology_digest:
        raise ContractError("contract.identity_mismatch", f"{path}.topology_digest", "selection topology contradicts subject hardware identity")
    if type(selection["payload_bytes"]) is not int or selection["payload_bytes"] < 0:
        raise ContractError("contract.invalid_value", f"{path}.payload_bytes", "invalid payload bytes")

    constraints = exact_object(selection["constraints"], CONSTRAINT_FIELDS, f"{path}.constraints")
    minimum, maximum = constraints["min_payload_bytes"], constraints["max_payload_bytes"]
    alignment = constraints["payload_alignment_bytes"]
    if (
        type(minimum) is not int or minimum < 0
        or type(maximum) is not int or maximum < minimum
        or type(alignment) is not int or alignment <= 0
    ):
        raise ContractError("contract.invalid_value", f"{path}.constraints", "invalid payload constraints")
    for field in ("dtypes", "layouts"):
        values = constraints[field]
        if (
            not isinstance(values, list)
            or not values
            or any(not isinstance(item, str) or not item for item in values)
            or len(values) != len(set(values))
        ):
            raise ContractError("contract.invalid_value", f"{path}.constraints.{field}", "invalid closed-world constraints")
    if constraints["actual_layout"] not in constraints["layouts"]:
        raise ContractError("contract.invalid_value", f"{path}.constraints.actual_layout", "route layout violates selection constraints")
    payload = selection["payload_bytes"]
    if payload < minimum or payload > maximum:
        raise ContractError("contract.invalid_value", f"{path}.payload_bytes", "payload is outside strategy threshold")
    if payload % alignment:
        raise ContractError("contract.invalid_value", f"{path}.payload_bytes", "payload is not strategy-aligned")
    if route["dtype"] not in constraints["dtypes"]:
        raise ContractError("contract.invalid_value", f"{path}.constraints.dtypes", "route dtype violates selection constraints")

    rank_domain = exact_object(selection["rank_domain"], RANK_DOMAIN_FIELDS, f"{path}.rank_domain")
    if not isinstance(rank_domain["domain"], str) or rank_domain["domain"] not in {"communicator_local", "logical", "physical"}:
        raise ContractError("contract.invalid_value", f"{path}.rank_domain.domain", "unknown rank mapping domain")
    primary_root = rank_domain["primary_root"]
    secondary_root = rank_domain["secondary_root"]
    if type(primary_root) is not int or not 0 <= primary_root < route["world_size"]:
        raise ContractError("contract.invalid_value", f"{path}.rank_domain.primary_root", "primary root must be in range")
    if secondary_root is not None and (
        type(secondary_root) is not int
        or not 0 <= secondary_root < route["world_size"]
        or secondary_root == primary_root
    ):
        raise ContractError("contract.invalid_value", f"{path}.rank_domain.secondary_root", "secondary root must be distinct and in range")
    validate_permutation(rank_domain["logical_to_physical"], route["world_size"], f"{path}.rank_domain.logical_to_physical")
    validate_permutation(selection["rank_order"], route["world_size"], f"{path}.rank_order")
    if selection["rank_order"] != route["rank_order"]:
        raise ContractError("contract.strategy_contradiction", f"{path}.rank_order", "selection and route rank descriptors contradict")

    strategy = exact_object(selection["strategy"], STRATEGY_FIELDS, f"{path}.strategy")
    nonempty(strategy["strategy_id"], f"{path}.strategy.strategy_id")
    nonempty(strategy["consumer_route_id"], f"{path}.strategy.consumer_route_id")
    required_identity(strategy["metadata_abi_digest"], f"{path}.strategy.metadata_abi_digest", DIGEST_RE)
    if type(strategy["requires_secondary_root"]) is not bool:
        raise ContractError("contract.invalid_value", f"{path}.strategy.requires_secondary_root", "expected boolean")
    if strategy["rank_domain"] != rank_domain["domain"]:
        raise ContractError("contract.strategy_contradiction", f"{path}.strategy.rank_domain", "strategy and rank descriptor domains contradict")
    if strategy["requires_secondary_root"] and secondary_root is None:
        raise ContractError("contract.invalid_value", f"{path}.rank_domain.secondary_root", "selected strategy requires a secondary root")
    fallback = exact_object(selection["fallback"], FALLBACK_FIELDS, f"{path}.fallback")
    nonempty(fallback["preferred_strategy_id"], f"{path}.fallback.preferred_strategy_id")
    nonempty(fallback["candidate_strategy_id"], f"{path}.fallback.candidate_strategy_id")
    if not isinstance(fallback["validation_state"], str) or fallback["validation_state"] not in {"unknown", "validating", "passed", "failed"} or type(fallback["committed"]) is not bool:
        raise ContractError("contract.invalid_value", f"{path}.fallback", "invalid fallback state")
    validation = exact_object(fallback["validation"], FALLBACK_VALIDATION_FIELDS, f"{path}.fallback.validation")
    if any(type(value) is not bool for value in validation.values()):
        raise ContractError("contract.invalid_value", f"{path}.fallback.validation", "invalid fallback validation checks")
    complete = all(validation.values())
    state = fallback["validation_state"]
    if state == "unknown" and any(validation.values()):
        raise ContractError("contract.fallback_state_contradiction", f"{path}.fallback.validation", "unknown fallback cannot contain completed checks")
    if state == "validating" and complete:
        raise ContractError("contract.fallback_state_contradiction", f"{path}.fallback.validation", "complete validation must transition to passed")
    if state == "passed" and not complete:
        raise ContractError("contract.fallback_partial_validation", f"{path}.fallback.validation", "passed fallback requires every candidate check")
    if state == "failed" and complete:
        raise ContractError("contract.fallback_state_contradiction", f"{path}.fallback.validation", "failed fallback must preserve a failed check")
    if fallback["committed"] and not (state == "passed" and complete):
        raise ContractError("contract.fallback_not_validated", f"{path}.fallback", "fallback may commit only after complete validation")
    if fallback["committed"] and fallback["candidate_strategy_id"] != strategy["strategy_id"]:
        raise ContractError("contract.strategy_contradiction", f"{path}.fallback.candidate_strategy_id", "committed fallback contradicts selected strategy")
    if not fallback["committed"] and fallback["preferred_strategy_id"] != strategy["strategy_id"]:
        raise ContractError("contract.strategy_contradiction", f"{path}.fallback.preferred_strategy_id", "uncommitted fallback cannot replace the preferred strategy")
    if selection["cache_key_digest"] != selection_cache_digest(selection, route):
        raise ContractError("contract.cache_key_digest_mismatch", f"{path}.cache_key_digest", "cache key does not bind every selection input")


def nullable_identity(
    value: Any, path: str, pattern: re.Pattern[str] | None = None
) -> None:
    if value is None:
        return
    nonempty(value, path)
    if pattern is not None and not pattern.fullmatch(value):
        raise ContractError("contract.invalid_value", path, "invalid identity format")


def required_identity(
    value: Any, path: str, pattern: re.Pattern[str] | None = None
) -> None:
    nonempty(value, path)
    if pattern is not None and not pattern.fullmatch(value):
        raise ContractError("contract.invalid_value", path, "invalid identity format")


def validate_execution(value: Any, active_primitives: set[str], oracle_by_primitive: dict[str, dict[str, str]]) -> None:
    if value is None:
        return
    execution = exact_object(value, EXECUTION_FIELDS, "$.qualification.execution")
    command = execution["harness_command"]
    if not isinstance(command, list) or not command or any(
        not isinstance(part, str) or not part for part in command
    ):
        raise ContractError(
            "contract.invalid_value",
            "$.qualification.execution.harness_command",
            "invalid argv",
        )
    for field in ("attempt_count", "timeout_seconds"):
        if type(execution[field]) is not int or execution[field] <= 0:
            raise ContractError(
                "contract.invalid_value",
                f"$.qualification.execution.{field}",
                "expected positive integer",
            )
    actions = execution["watchdog_actions"]
    if not isinstance(actions, list) or any(
        action not in {"started", "timeout", "sigterm", "sigkill", "reaped"}
        for action in actions
    ):
        raise ContractError(
            "contract.invalid_value",
            "$.qualification.execution.watchdog_actions",
            "invalid watchdog actions",
        )
    rows = execution["rank_results"]
    if not isinstance(rows, list):
        raise ContractError(
            "contract.invalid_type",
            "$.qualification.execution.rank_results",
            "expected list",
        )
    keys: set[tuple[int, int]] = set()
    for index, row_value in enumerate(rows):
        path = f"$.qualification.execution.rank_results[{index}]"
        row = exact_object(row_value, RANK_FIELDS, path)
        if (
            type(row["attempt"]) is not int
            or row["attempt"] <= 0
            or type(row["rank"]) is not int
            or row["rank"] < 0
        ):
            raise ContractError("contract.invalid_value", path, "invalid attempt or rank")
        if row["exit_code"] is not None and type(row["exit_code"]) is not int:
            raise ContractError(
                "contract.invalid_value", f"{path}.exit_code", "invalid exit code"
            )
        if row["status"] not in {"passed", "failed", "timed_out", "not_reported"}:
            raise ContractError(
                "contract.invalid_value", f"{path}.status", "invalid rank status"
            )
        status_matches_exit = (
            (row["status"] == "passed" and row["exit_code"] == 0)
            or (row["status"] == "failed" and row["exit_code"] is not None and row["exit_code"] != 0)
            or (row["status"] == "timed_out" and "timeout" in execution["watchdog_actions"])
            or (row["status"] == "not_reported" and row["exit_code"] is None and "timeout" not in execution["watchdog_actions"])
        )
        if not status_matches_exit:
            raise ContractError(
                "contract.inconsistent_status", f"{path}.status",
                "rank status must match exit code",
            )
        key = (row["attempt"], row["rank"])
        if key in keys:
            raise ContractError("contract.invalid_value", path, "duplicate attempt/rank")
        keys.add(key)
    attempts = execution["attempt_count"]
    world_size = max(row["rank"] for row in rows) + 1 if rows else 0
    expected_keys = {
        (attempt, rank)
        for attempt in range(1, attempts + 1)
        for rank in range(world_size)
    }
    if not rows or keys != expected_keys:
        raise ContractError(
            "contract.incomplete_rank_results",
            "$.qualification.execution.rank_results",
            "every attempt must contain every rank exactly once",
        )
    correctness_rows = execution["correctness"]
    if not isinstance(correctness_rows, list) or len(correctness_rows) != attempts:
        raise ContractError("contract.incomplete_correctness_results", "$.qualification.execution.correctness", "every attempt requires correctness results")
    for attempt_index, correctness_value in enumerate(correctness_rows, start=1):
        correctness_path = f"$.qualification.execution.correctness[{attempt_index - 1}]"
        correctness = exact_object(correctness_value, CORRECTNESS_FIELDS, correctness_path)
        if correctness["attempt"] != attempt_index or correctness["status"] not in {"passed", "failed"}:
            raise ContractError("contract.invalid_value", correctness_path, "invalid correctness attempt or status")
        primitive_results = correctness["primitive_results"]
        if not isinstance(primitive_results, list) or not primitive_results:
            raise ContractError("contract.invalid_value", f"{correctness_path}.primitive_results", "content correctness results are required")
        seen_primitives = set()
        for index, result_value in enumerate(primitive_results):
            path = f"{correctness_path}.primitive_results[{index}]"
            result = exact_object(result_value, PRIMITIVE_RESULT_FIELDS, path)
            if result["primitive"] not in PRIMITIVES or result["primitive"] in seen_primitives:
                raise ContractError("contract.invalid_value", f"{path}.primitive", "invalid or duplicate primitive")
            seen_primitives.add(result["primitive"])
            for field in ("expected_digest", "actual_digest"):
                nullable_identity(result[field], f"{path}.{field}", DIGEST_RE)
            expected_status = "passed" if result["expected_digest"] == result["actual_digest"] else "failed"
            if result["status"] != expected_status:
                raise ContractError("contract.inconsistent_status", f"{path}.status", "correctness digest verdict mismatch")
            oracle = oracle_by_primitive.get(result["primitive"])
            if oracle is None or result["expected_digest"] != oracle["expected_digest"]:
                raise ContractError("contract.correctness_oracle_mismatch", f"{path}.expected_digest", "expected digest must come from the sealed oracle")
        if seen_primitives != active_primitives:
            raise ContractError("contract.incomplete_correctness_results", f"{correctness_path}.primitive_results", "every active primitive requires one correctness result")
        expected_correctness = "passed" if all(row["status"] == "passed" for row in primitive_results) else "failed"
        if correctness["status"] != expected_correctness:
            raise ContractError("contract.inconsistent_status", f"{correctness_path}.status", "aggregate correctness mismatch")
    cleanup = exact_object(
        execution["process_tree_cleanup"],
        CLEANUP_FIELDS,
        "$.qualification.execution.process_tree_cleanup",
    )
    if (
        type(cleanup["termination_requested"]) is not bool
        or type(cleanup["inspection_complete"]) is not bool
        or not isinstance(cleanup["residual_pids"], list)
        or any(type(pid) is not int or pid <= 0 for pid in cleanup["residual_pids"])
        or cleanup["hbm_status"] not in {"released", "not_verified"}
        or cleanup["status"] not in {"passed", "failed", "not_verified"}
    ):
        raise ContractError(
            "contract.invalid_value",
            "$.qualification.execution.process_tree_cleanup",
            "invalid cleanup record",
        )
    health = exact_object(
        execution["health_snapshot"],
        HEALTH_FIELDS,
        "$.qualification.execution.health_snapshot",
    )
    if (
        health["status"] not in {"healthy", "degraded", "not_verified"}
        or health["source"] not in {"real_dlc_hardware", "controlled_fixture"}
    ):
        raise ContractError(
            "contract.invalid_value",
            "$.qualification.execution.health_snapshot",
            "invalid health snapshot",
        )
    nullable_identity(
        health["snapshot_digest"],
        "$.qualification.execution.health_snapshot.snapshot_digest",
        DIGEST_RE,
    )


def derive_blocker_details(document: dict[str, Any]) -> list[dict[str, str]]:
    qualification = document["qualification"]
    preflight = qualification["preflight"]
    routes = qualification["route_inventory"]
    details: list[dict[str, str]] = []

    def add(
        status: str, code: str, path: str, phase: str, message: str, resume: str
    ) -> None:
        details.append({
            "status": status,
            "code": code,
            "path": path,
            "phase": phase,
            "message": message,
            "resume_point": resume,
        })

    if preflight["requested_operation"] in {"formal_acceptance", "modify_shared_device"}:
        add("blocked", "blocked_dangerous_operation", "$.qualification.preflight.requested_operation", "preflight", "operation is outside runner authority", "authorized_bounded_qualification")
    missing_identity = False
    for route in routes:
        if not route["active"]:
            continue
        identity = route["identity"]
        missing_identity = missing_identity or identity["source_sha"] is None
        if route["route_class"] == "native_dlc_cl":
            missing_identity = missing_identity or identity["binary_sha256"] is None or identity["symbol"] is None
        if route["route_class"] == "custom_kernel":
            missing_identity = missing_identity or identity["binary_sha256"] is None or identity["abi_digest"] is None
    if missing_identity:
        add("blocked", "blocked_missing_identity", "$.qualification.route_inventory", "preflight", "active route identity is incomplete", "route_identity")
    if not preflight["authorization_granted"]:
        add("blocked", "blocked_missing_authorization", "$.qualification.preflight.authorization_granted", "preflight", "bounded launch authorization is absent", "launch_authorization")
    if preflight["hardware_environment"] != "real_dlc_hardware" or not preflight["hardware_available"]:
        status = "not_verified" if preflight["hardware_environment"] == "controlled_fixture" else "blocked"
        add(status, "blocked_missing_hardware", "$.qualification.preflight.hardware_environment", "preflight", "Real DLC Hardware is unavailable", "real_dlc_hardware_allocation")
    elif preflight["requested_operation"] == "qualify":
        add("blocked", "blocked_missing_trusted_qualification_inputs", "$.qualification.preflight", "preflight", "real qualification requires externally validated authorization, observation, pinned harness, and correctness schemas", "trusted_qualification_inputs")
    for index, route in enumerate(routes):
        if not route["active"]:
            continue
        path = f"$.qualification.route_inventory[{index}]"
        if route["qualification_status"] == "unsupported" or not route["route"] or not route["backend"]:
            add("blocked", "blocked_collective_unimplemented", path, "route_inventory", f"active route {route['route_id']} is unsupported", "route_implementation")
        elif route["qualification_status"] != "qualified":
            add("blocked", "blocked_collective_not_qualified", path, "route_inventory", f"active route {route['route_id']} is not qualified", "collective_qualification")
    execution = qualification["execution"]
    if execution is None and preflight["hardware_environment"] == "real_dlc_hardware":
        add("not_verified", "blocked_missing_execution_evidence", "$.qualification.execution", "execution", "real hardware observation without rank, correctness, cleanup, and health evidence cannot pass qualification", "bounded_collective_execution")
    if execution is not None:
        statuses = {row["status"] for row in execution["rank_results"]}
        if "timed_out" in statuses or "timeout" in execution["watchdog_actions"]:
            add("failed", "failed_collective_completion", "$.qualification.execution.rank_results", "execution", "bounded collective did not complete", "collective_failure_diagnosis")
        elif "failed" in statuses:
            add("failed", "failed_collective_correctness", "$.qualification.execution.rank_results", "execution", "one or more ranks or the harness parent failed", "collective_failure_diagnosis")
        if any(row["status"] == "failed" for row in execution["correctness"]):
            add("failed", "failed_collective_correctness", "$.qualification.execution.correctness", "execution", "collective content differs from the independent expected digest", "collective_failure_diagnosis")
        cleanup = execution["process_tree_cleanup"]
        if not cleanup["inspection_complete"] or cleanup["status"] != "passed" or cleanup["residual_pids"]:
            add("blocked", "blocked_cleanup_incomplete", "$.qualification.execution.process_tree_cleanup", "cleanup", "task-owned process cleanup is incomplete", "process_tree_cleanup")
    unique = {(row["status"], row["code"], row["path"]): row for row in details}
    return sorted(unique.values(), key=lambda row: (STATUS_RANK[row["status"]], row["code"], row["path"]))


def derive_blockers(document: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"status": row["status"], "code": row["code"], "path": row["path"]}
        for row in derive_blocker_details(document)
    ]


def normalize_status(document: dict[str, Any]) -> None:
    details = derive_blocker_details(document)
    blockers = [
        {"status": row["status"], "code": row["code"], "path": row["path"]}
        for row in details
    ]
    status, primary = SHARED.aggregate_blockers(blockers)
    document["qualification"]["blocker_details"] = details
    document["blockers"] = blockers
    document["primary_blocker"] = primary
    document["status"] = status
    primary_detail = next(
        (row for row in details if {key: row[key] for key in ("status", "code", "path")} == primary),
        None,
    )
    document["resume_point"] = primary_detail["resume_point"] if primary_detail else "complete"


def validate_document(document: Any) -> dict[str, Any]:
    envelope_errors = SHARED.validate_envelope(
        document,
        ("qualification",),
        accepted_schema_versions=(SCHEMA_V2,),
    )
    if envelope_errors:
        error = envelope_errors[0]
        raise ContractError(f"contract.{error['code']}", error["path"], "shared envelope validation failed")
    artifact = document
    if artifact["schema_version"] not in SCHEMAS:
        raise ContractError("contract.unsupported_schema_version", "$.schema_version", "unsupported schema")
    schema = artifact["schema_version"]

    qualification = exact_object(artifact["qualification"], QUALIFICATION_FIELDS, "$.qualification")
    preflight = exact_object(qualification["preflight"], PREFLIGHT_FIELDS, "$.qualification.preflight")
    if (
        not isinstance(preflight["hardware_environment"], str)
        or preflight["hardware_environment"] not in {"real_dlc_hardware", "controlled_fixture", "none"}
        or type(preflight["hardware_available"]) is not bool
        or type(preflight["authorization_granted"]) is not bool
        or not isinstance(preflight["requested_operation"], str)
        or preflight["requested_operation"] not in {"qualify", "observe", "formal_acceptance", "modify_shared_device"}
    ):
        raise ContractError("contract.invalid_value", "$.qualification.preflight", "invalid preflight")

    routes = qualification["route_inventory"]
    if not isinstance(routes, list):
        raise ContractError("contract.invalid_type", "$.qualification.route_inventory", "expected list")
    route_ids: set[str] = set()
    route_classes: set[str] = set()
    selected_routes: list[tuple[dict[str, Any], str]] = []
    hardware_topology_digest = artifact["subject_identity"]["hardware"]["topology_digest"]
    for index, route_value in enumerate(routes):
        path = f"$.qualification.route_inventory[{index}]"
        route = exact_object(route_value, ROUTE_FIELDS if schema == SCHEMA_V1 else ROUTE_V2_FIELDS, path)
        route_id = nonempty(route["route_id"], f"{path}.route_id")
        if (
            route_id in route_ids
            or not isinstance(route["route_class"], str)
            or route["route_class"] not in ROUTE_CLASSES
            or not isinstance(route["primitive"], str)
            or route["primitive"] not in PRIMITIVES
        ):
            raise ContractError("contract.invalid_value", path, "duplicate or invalid route identity")
        route_ids.add(route_id)
        route_classes.add(route["route_class"])
        for field in ("active", "asynchronous"):
            if type(route[field]) is not bool:
                raise ContractError("contract.invalid_value", f"{path}.{field}", "expected boolean")
        for field in ("route", "backend", "dtype", "shape_or_count", "stream", "completion_boundary", "fallback"):
            if route[field] is not None and (not isinstance(route[field], str) or not route[field]):
                raise ContractError("contract.invalid_value", f"{path}.{field}", "invalid route detail")
        if type(route["rank"]) is not int or route["rank"] < 0 or type(route["world_size"]) is not int or route["world_size"] <= 0 or route["rank"] >= route["world_size"]:
            raise ContractError("contract.invalid_value", path, "invalid rank/world size")
        identity = exact_object(route["identity"], IDENTITY_FIELDS, f"{path}.identity")
        nullable_identity(identity["source_sha"], f"{path}.identity.source_sha", SHA_RE)
        for field in ("binary_sha256", "abi_digest"):
            nullable_identity(identity[field], f"{path}.identity.{field}", DIGEST_RE)
        nullable_identity(identity["symbol"], f"{path}.identity.symbol")
        if schema == SCHEMA_V1:
            if not isinstance(route["rank_order"], list) or route["rank_order"] != list(range(route["world_size"])):
                raise ContractError("contract.invalid_value", f"{path}.rank_order", "rank order must close the world")
        else:
            validate_permutation(route["rank_order"], route["world_size"], f"{path}.rank_order")
            validate_selection(
                route["selection"], route, f"{path}.selection",
                hardware_topology_digest,
            )
            if route["selection"] is not None:
                selected_routes.append((route, path))
        if not isinstance(route["qualification_status"], str) or route["qualification_status"] not in QUALIFICATION_STATES:
            raise ContractError("contract.invalid_value", f"{path}.qualification_status", "invalid qualification state")
    if route_classes != ROUTE_CLASSES:
        raise ContractError("contract.missing_required_route_class", "$.qualification.route_inventory", "route inventory is not closed-world")
    for selected_route, selected_path in selected_routes:
        consumer_route_id = selected_route["selection"]["strategy"]["consumer_route_id"]
        consumers = [
            route for route in routes
            if route["route_id"] == consumer_route_id
            and route["active"]
            and route["route_class"] == "native_dlc_cl"
            and route["primitive"] == selected_route["primitive"]
        ]
        if len(consumers) != 1 or consumers[0]["identity"]["abi_digest"] is None:
            raise ContractError(
                "contract.missing_required_route_class",
                f"{selected_path}.selection.strategy.consumer_route_id",
                "selection requires an exact native consumer ABI",
            )
        consumer = consumers[0]
        if (
            selected_route["selection"]["strategy"]["metadata_abi_digest"]
            != consumer["identity"]["abi_digest"]
        ):
            raise ContractError(
                "contract.strategy_contradiction",
                f"{selected_path}.selection.strategy.metadata_abi_digest",
                "strategy metadata ABI contradicts the native consumer route",
            )
    primitive_inventory = qualification["primitive_inventory"]
    if not isinstance(primitive_inventory, list) or set(primitive_inventory) != PRIMITIVES or len(primitive_inventory) != len(PRIMITIVES):
        raise ContractError("contract.incomplete_primitive_inventory", "$.qualification.primitive_inventory", "every reachable primitive must be inventoried exactly once")
    represented_primitives = {route["primitive"] for route in routes}
    if represented_primitives != set(primitive_inventory):
        raise ContractError("contract.incomplete_primitive_inventory", "$.qualification.route_inventory", "every inventoried primitive requires an explicit route row")
    active_primitives = {route["primitive"] for route in routes if route["active"]}
    oracles = qualification["correctness_oracles"]
    if not isinstance(oracles, list):
        raise ContractError("contract.invalid_type", "$.qualification.correctness_oracles", "expected list")
    oracle_by_primitive = {}
    for index, oracle_value in enumerate(oracles):
        path = f"$.qualification.correctness_oracles[{index}]"
        oracle = exact_object(oracle_value, ORACLE_FIELDS, path)
        primitive = oracle["primitive"]
        if primitive not in PRIMITIVES or primitive in oracle_by_primitive:
            raise ContractError("contract.invalid_value", f"{path}.primitive", "invalid or duplicate oracle")
        for field in ("expected_digest", "input_digest"):
            nullable_identity(oracle[field], f"{path}.{field}", DIGEST_RE)
        oracle_by_primitive[primitive] = oracle
    if set(oracle_by_primitive) != active_primitives:
        raise ContractError("contract.incomplete_correctness_oracles", "$.qualification.correctness_oracles", "every active primitive requires one independent oracle")
    required = qualification["required_route_ids"]
    if not isinstance(required, list) or len(required) != len(set(required)) or not set(required).issubset(route_ids):
        raise ContractError("contract.invalid_value", "$.qualification.required_route_ids", "invalid required routes")
    if set(required) != {route["route_id"] for route in routes if route["active"]}:
        raise ContractError("contract.inconsistent_status", "$.qualification.required_route_ids", "required routes must equal active routes")
    validate_execution(qualification["execution"], active_primitives, oracle_by_primitive)
    if qualification["execution"] is not None:
        expected_world_size = max(route["world_size"] for route in routes if route["active"])
        rows = qualification["execution"]["rank_results"]
        expected_keys = {
            (attempt, rank)
            for attempt in range(1, qualification["execution"]["attempt_count"] + 1)
            for rank in range(expected_world_size)
        }
        if {(row["attempt"], row["rank"]) for row in rows} != expected_keys:
            raise ContractError("contract.incomplete_rank_results", "$.qualification.execution.rank_results", "rank coverage does not match active world size")
    details = qualification["blocker_details"]
    if not isinstance(details, list):
        raise ContractError("contract.invalid_type", "$.qualification.blocker_details", "expected list")
    for index, detail in enumerate(details):
        exact_object(detail, DETAIL_FIELDS, f"$.qualification.blocker_details[{index}]")
    expected_details = derive_blocker_details(artifact)
    expected_blockers = [{"status": row["status"], "code": row["code"], "path": row["path"]} for row in expected_details]
    expected_status, expected_primary = SHARED.aggregate_blockers(expected_blockers)
    if details != expected_details or artifact["blockers"] != expected_blockers:
        raise ContractError("contract.inconsistent_status", "$.blockers", "blockers do not match preflight and execution")
    if artifact["status"] != expected_status or artifact["primary_blocker"] != expected_primary:
        raise ContractError("contract.inconsistent_status", "$.status", "status does not use canonical failed > blocked > not_verified aggregation")
    primary_detail = next((row for row in expected_details if {key: row[key] for key in ("status", "code", "path")} == expected_primary), None)
    expected_resume = primary_detail["resume_point"] if primary_detail else "complete"
    if artifact["resume_point"] != expected_resume:
        raise ContractError("contract.inconsistent_status", "$.resume_point", "resume point does not match primary blocker")
    return {
        "schema_version": schema,
        "status": artifact["status"],
        "reason_code": expected_primary["code"] if expected_primary else "passed",
        "resume_point": artifact["resume_point"],
        "launch_allowed": False,
        "acceptance_eligible": False,
        "claim_boundary": artifact["claim_boundary"],
        "digest": artifact["digest"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args(argv)
    try:
        document = json.loads(args.artifact.read_text(encoding="utf-8"))
        report = validate_document(document)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(json.dumps({"checks": [{"code": "contract.invalid_json", "path": "$", "message": str(error)}]}))
        return 20
    except ContractError as error:
        print(json.dumps({"checks": [{"code": error.code, "path": error.path, "message": error.message}]}))
        return 20
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
