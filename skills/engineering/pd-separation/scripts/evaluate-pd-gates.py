#!/usr/bin/env python3
import json
import sys
from pathlib import Path


CORE_GATES = (
    "static_configuration",
    "transport_qualification",
    "service_readiness",
    "request_routing",
    "kv_transfer",
    "functional_equivalence",
    "lifecycle_cleanup",
    "site_recovery",
)
OPTIONAL_GATES = ("performance_workload", "stability_baseline")
GATE_FIELDS = {"status", "reason", "blocker"}
BLOCKERS = {
    "blocked_missing_contract",
    "blocked_missing_hardware",
    "blocked_missing_observability",
    "blocked_missing_authorization",
    "blocked_network_unreachable",
    "blocked_model_or_cache_incompatible",
    "blocked_transport_unqualified",
    "blocked_cleanup_incomplete",
}


def emit(state, dimensions=None, blockers=None, primary=None, problems=None, exit_code=2):
    print(
        json.dumps(
            {
                "schema": "io.chipltech.pd-gate-result/v1",
                "terminal_state": state,
                "primary_blocker": primary,
                "active_blockers": blockers or [],
                "dimensions": dimensions or {},
                "problems": problems or [],
                "authoritative": False,
                "runtime_acceptance": False,
                "claim_boundary": (
                    "Claim Boundary: gate aggregation evaluates supplied software-contract states only; it does not establish "
                    "PD execution, KV transfer, performance, topology qualification, or runtime acceptance."
                ),
            },
            sort_keys=True,
        )
    )
    return exit_code


def invalid(problems):
    return emit("invalid_contract", problems=sorted(problems), exit_code=3)


def validate(value):
    if not isinstance(value, dict) or set(value) != {"schema", "gates", "mandatory_optional_gates"}:
        return ["closed_world_fields"]
    if value["schema"] != "io.chipltech.pd-gate-evaluation/v1":
        return ["schema"]
    gates = value["gates"]
    if not isinstance(gates, dict) or set(gates) != set(CORE_GATES + OPTIONAL_GATES):
        return ["gates"]
    mandatory = value["mandatory_optional_gates"]
    if not isinstance(mandatory, list) or len(mandatory) != len(set(mandatory)) or any(
        item not in OPTIONAL_GATES for item in mandatory
    ):
        return ["mandatory_optional_gates"]
    problems = []
    for name, gate in gates.items():
        allowed = {"pass", "failed", "not_executed", "blocked"}
        if name == "site_recovery":
            allowed.add("not_applicable")
        if name in OPTIONAL_GATES:
            allowed = {"pass", "failed", "not_requested", "not_verified", "blocked"}
        if not isinstance(gate, dict) or set(gate) != GATE_FIELDS:
            problems.append(name)
            continue
        status, reason, blocker = gate["status"], gate["reason"], gate["blocker"]
        if status not in allowed or (reason is not None and not isinstance(reason, str)):
            problems.append(name)
        elif status == "blocked":
            if blocker not in BLOCKERS or not reason:
                problems.append(name)
        elif blocker is not None:
            problems.append(name)
    return problems


def main():
    try:
        value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (IndexError, OSError, json.JSONDecodeError) as error:
        return invalid([str(error)])
    problems = validate(value)
    if problems:
        return invalid(problems)

    dimensions = value["gates"]
    active = [
        {"gate": name, "state": dimensions[name]["blocker"], "reason": dimensions[name]["reason"]}
        for name in CORE_GATES + OPTIONAL_GATES
        if dimensions[name]["status"] == "blocked"
    ]
    cleanup = next((item for item in active if item["state"] == "blocked_cleanup_incomplete"), None)
    primary = cleanup or (active[0] if active else None)
    if primary:
        return emit(primary["state"], dimensions, active, primary)

    mandatory = CORE_GATES + tuple(value["mandatory_optional_gates"])
    if any(dimensions[name]["status"] == "failed" for name in mandatory):
        return emit("failed_validation", dimensions)
    if any(dimensions[name]["status"] in {"not_executed", "not_verified", "not_requested"} for name in mandatory):
        return emit("not_verified", dimensions)
    return emit("pd_validated", dimensions, exit_code=0)


if __name__ == "__main__":
    raise SystemExit(main())
