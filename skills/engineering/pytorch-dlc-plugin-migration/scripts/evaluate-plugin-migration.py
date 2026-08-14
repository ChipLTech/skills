#!/usr/bin/env python3
import json
import hashlib
import re
import sys
from pathlib import Path


OWNERS = {
    "source_governance": "restricted-reference-governance",
    "source_migration": "pytorch-dlc-plugin-migration",
    "compile_link": "pytorch-dlc-plugin-migration",
    "wheel_import": "pytorch-dlc-plugin-migration",
    "stack_preflight": "dlc-env-setup",
    "package_seal": "package-provider",
    "dlc_runtime_execution": "dlc-env-setup",
    "real_dlc_hardware_behavior": "pytorch-dlc-plugin-migration",
    "smi_observation": "dlc-hardware-observability",
    "distributed_behavior": "distributed-qualification",
    "cleanup": "dlc-hardware-observability",
}
STATUSES = {
    "source_governance": {"pass", "not_applicable", "unresolved"},
    "source_migration": {"pass", "failed", "not_verified", "unsupported"},
    "compile_link": {"pass", "failed", "not_applicable", "not_verified"},
    "wheel_import": {"pass", "failed", "not_applicable", "not_verified"},
    "stack_preflight": {"pass", "failed", "missing"},
    "package_seal": {"pass", "failed", "missing", "stale"},
    "dlc_runtime_execution": {"pass", "failed", "not_applicable", "not_verified"},
    "real_dlc_hardware_behavior": {"pass", "failed", "not_applicable", "not_verified"},
    "smi_observation": {"pass", "failed", "missing", "not_applicable"},
    "distributed_behavior": {"pass", "failed", "not_applicable", "not_verified", "unqualified"},
    "cleanup": {"pass", "failed", "incomplete"},
}
FIELDS = {"schema", "device_deferral_permitted", *OWNERS}
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


def emit(state, dimensions=None, problems=None, exit_code=2):
    print(json.dumps({"schema": "io.chipltech.plugin-migration-result/v1", "terminal_state": state, "dimensions": dimensions or {}, "authoritative": False, "acceptance_eligible": False, "problems": problems or [], "claim_boundary": "This result checks owner-bound supplied artifacts; it does not authenticate providers or create production qualification or formal acceptance."}, sort_keys=True))
    return exit_code


def main():
    try:
        value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (IndexError, OSError, json.JSONDecodeError) as error:
        return emit("invalid_contract", problems=[str(error)], exit_code=3)
    if not isinstance(value, dict) or set(value) != FIELDS or value.get("schema") != "io.chipltech.plugin-migration-evidence/v1" or type(value.get("device_deferral_permitted")) is not bool:
        return emit("invalid_contract", problems=["closed_world_fields"], exit_code=3)
    problems = []
    for field, owner in OWNERS.items():
        item = value[field]
        if not isinstance(item, dict) or set(item) != {"status", "owner", "artifact_path", "artifact_id", "fresh", "authority"}:
            problems.append(field)
        elif item["owner"] != owner or item["status"] not in STATUSES[field] or item["authority"] != "operational_only" or type(item["fresh"]) is not bool or not isinstance(item["artifact_path"], str) or not isinstance(item["artifact_id"], str) or not SHA256.fullmatch(item["artifact_id"]):
            problems.append(field)
        else:
            try:
                digest = "sha256:" + hashlib.sha256(Path(item["artifact_path"]).read_bytes()).hexdigest()
            except OSError:
                digest = ""
            if digest != item["artifact_id"]:
                problems.append(field)
    if problems:
        return emit("invalid_contract", problems=sorted(problems), exit_code=3)
    dimensions = {field: value[field] for field in sorted(OWNERS)}
    status = lambda field: value[field]["status"]
    checks = (
        (status("cleanup") in {"failed", "incomplete"}, "blocked_cleanup_incomplete"),
        (status("source_governance") == "unresolved", "blocked_legal_boundary"),
        (any(not value[field]["fresh"] for field in OWNERS if field != "package_seal"), "blocked_stale_owner_evidence"),
        (status("stack_preflight") == "missing", "blocked_missing_preflight"),
        (not value["package_seal"]["fresh"] or status("package_seal") == "stale", "blocked_stale_package_seal"),
        (status("package_seal") == "missing", "blocked_missing_package_seal"),
        (status("smi_observation") == "missing", "blocked_missing_observability"),
        (status("distributed_behavior") == "unqualified", "blocked_distributed_route_unqualified"),
        (status("source_migration") == "unsupported", "unsupported_by_production_backend"),
    )
    for active, state in checks:
        if active:
            return emit(state, dimensions)
    if any(status(field) == "failed" for field in OWNERS):
        return emit("failed_validation", dimensions)
    device_unverified = any(status(field) == "not_verified" for field in ("dlc_runtime_execution", "real_dlc_hardware_behavior", "distributed_behavior"))
    build_package_closed = all(status(field) in {"pass", "not_applicable"} for field in ("source_migration", "compile_link", "wheel_import", "stack_preflight", "package_seal"))
    if device_unverified and value["device_deferral_permitted"] and build_package_closed:
        return emit("implementation_complete_tests_deferred", dimensions, exit_code=0)
    if any(status(field) == "not_verified" for field in OWNERS):
        return emit("not_verified", dimensions)
    return emit("all_declared_dimensions_passed", dimensions, exit_code=0)


if __name__ == "__main__":
    raise SystemExit(main())
