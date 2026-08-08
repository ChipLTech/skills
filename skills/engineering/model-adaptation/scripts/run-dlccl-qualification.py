#!/usr/bin/env python3
"""Run a bounded DLCCL qualification harness and seal its artifact."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any


VALIDATOR_PATH = Path(__file__).with_name("validate-vllm-dlc-qualification.py")
SPEC = importlib.util.spec_from_file_location("dlccl_qualification_contract", VALIDATOR_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load distributed qualification validator")
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)


def process_group_members(pgid: int) -> set[int] | None:
    try:
        result = subprocess.run(
            ["/usr/bin/ps", "-eo", "pid=,pgid="],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    members: set[int] = set()
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) == 2 and all(field.isdigit() for field in fields):
            pid, candidate_pgid = map(int, fields)
            if candidate_pgid == pgid:
                members.add(pid)
    return members


def terminate_tree(process: subprocess.Popen[str], actions: list[str]) -> tuple[list[int], bool]:
    members = process_group_members(process.pid)
    if process.poll() is None or members is None or any(pid > 0 and pid != process.pid for pid in members):
        actions.append("sigterm")
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        time_limit = 1.0
        while time_limit > 0:
            observed = process_group_members(process.pid)
            if observed is not None and not any(pid > 0 for pid in observed):
                break
            import time
            time.sleep(0.05)
            time_limit -= 0.05
        observed = process_group_members(process.pid)
        if observed is None or any(pid > 0 for pid in observed):
            actions.append("sigkill")
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
    actions.append("reaped")
    final = process_group_members(process.pid)
    return (sorted(final) if final is not None else [], final is not None)


def rank_rows(stdout: str, attempt: int, world_size: int, returncode: int | None, timed_out: bool) -> list[dict[str, Any]]:
    if not timed_out and returncode == 0:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("rank_results"), list):
            rows = []
            seen: set[int] = set()
            for value in payload["rank_results"]:
                if not isinstance(value, dict) or set(value) != {"rank", "exit_code"}:
                    rows = []
                    break
                rank, exit_code = value["rank"], value["exit_code"]
                if type(rank) is not int or rank < 0 or rank >= world_size or rank in seen or type(exit_code) is not int:
                    rows = []
                    break
                seen.add(rank)
                rows.append({"attempt": attempt, "rank": rank, "exit_code": exit_code, "status": "passed" if exit_code == 0 else "failed"})
            if len(rows) == world_size:
                return sorted(rows, key=lambda row: row["rank"])
    status = "timed_out" if timed_out else "failed"
    return [
        {"attempt": attempt, "rank": rank, "exit_code": returncode, "status": status}
        for rank in range(world_size)
    ]


def correctness_record(
    stdout: str, returncode: int | None, timed_out: bool,
    oracle_by_primitive: dict[str, str],
) -> dict[str, Any]:
    results = []
    if not timed_out and returncode == 0:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = None
        values = payload.get("primitive_results") if isinstance(payload, dict) else None
        if isinstance(values, list):
            seen = set()
            for value in values:
                if not isinstance(value, dict) or set(value) != {"primitive", "actual_digest"}:
                    results = []
                    break
                primitive = value["primitive"]
                expected = oracle_by_primitive.get(primitive)
                actual = value["actual_digest"]
                if primitive not in CONTRACT.PRIMITIVES or primitive in seen or not isinstance(expected, str) or not CONTRACT.DIGEST_RE.fullmatch(expected) or not isinstance(actual, str) or not CONTRACT.DIGEST_RE.fullmatch(actual):
                    results = []
                    break
                seen.add(primitive)
                results.append({"primitive": primitive, "expected_digest": expected, "actual_digest": actual, "status": "passed" if expected == actual else "failed"})
    if not results:
        results = [
            {
                "primitive": primitive,
                "expected_digest": expected,
                "actual_digest": "sha256:" + "0" * 64,
                "status": "failed",
            }
            for primitive, expected in sorted(oracle_by_primitive.items())
        ]
    return {
        "status": "passed" if all(row["status"] == "passed" for row in results) else "failed",
        "primitive_results": results,
    }


def preflight(template: dict[str, Any], controlled: bool) -> tuple[bool, list[dict[str, str]]]:
    blockers = CONTRACT.derive_blockers(template)
    hard = [row for row in blockers if row["code"] != "blocked_missing_hardware"]
    if hard:
        return False, blockers
    if blockers and not controlled:
        return False, blockers
    if controlled and template["qualification"]["preflight"]["hardware_environment"] != "controlled_fixture":
        return False, [{
            "code": "blocked_dangerous_operation",
            "phase": "preflight",
            "message": "controlled harness requires controlled_fixture environment",
            "resume_point": "controlled_fixture_identity",
        }]
    return True, blockers


def seal(document: dict[str, Any]) -> None:
    CONTRACT.normalize_status(document)
    document["acceptance_eligible"] = False
    document["digest"] = CONTRACT.artifact_digest(document)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--harness", type=Path, required=True)
    parser.add_argument("--harness-arg", action="append", default=[])
    parser.add_argument("--timeout-seconds", type=int, default=10)
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--controlled-harness", action="store_true")
    args = parser.parse_args(argv)
    if args.timeout_seconds <= 0 or args.attempts <= 0 or not args.harness.is_absolute():
        parser.error("positive bounds and an absolute harness path are required")
    try:
        document = json.loads(args.template.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(json.dumps({"code": "contract.invalid_json", "message": str(error)}))
        return 20
    try:
        CONTRACT.validate_document(document)
    except CONTRACT.ContractError as error:
        print(json.dumps({"code": error.code, "path": error.path, "message": error.message}))
        return 20
    allowed, blockers = preflight(document, args.controlled_harness)
    if not allowed:
        seal(document)
        args.output.write_bytes(CONTRACT.canonical_bytes(document) + b"\n")
        print(json.dumps({"status": document["status"], "reason_code": document["primary_blocker"]["code"], "launched": False}))
        return 24

    world_size = max(route["world_size"] for route in document["qualification"]["route_inventory"] if route["active"])
    command = [str(args.harness), *args.harness_arg]
    if args.harness.suffix == ".py":
        command.insert(0, sys.executable)
    actions = ["started"]
    rows: list[dict[str, Any]] = []
    residual: set[int] = set()
    inspection_complete = True
    correctness_rows = []
    oracle_by_primitive = {
        row["primitive"]: row["expected_digest"]
        for row in document["qualification"]["correctness_oracles"]
    }
    termination_requested = False
    completed_attempts = 0
    for attempt in range(1, args.attempts + 1):
        completed_attempts = attempt
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        timed_out = False
        try:
            stdout, _ = process.communicate(timeout=args.timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            termination_requested = True
            actions.append("timeout")
            stdout = ""
        action_count = len(actions)
        remaining, inspected = terminate_tree(process, actions)
        residual.update(remaining)
        inspection_complete = inspection_complete and inspected
        termination_requested = termination_requested or "sigterm" in actions[action_count:]
        rows.extend(rank_rows(stdout, attempt, world_size, process.returncode, timed_out))
        correctness = correctness_record(
            stdout, process.returncode, timed_out, oracle_by_primitive
        )
        correctness["attempt"] = attempt
        correctness_rows.append(correctness)
        if (
            timed_out
            or correctness["status"] != "passed"
            or any(row["status"] != "passed" for row in rows if row["attempt"] == attempt)
        ):
            break

    document.update(
        producer="model-adaptation/dlccl-qualification-runner",
        producer_version="1.0.0",
        evidence_class="fixture" if args.controlled_harness else "qualification",
        authoritativeness="non_authoritative" if args.controlled_harness else "operational",
    )
    document["claim_boundary"] = (
        "Claim Boundary: controlled harness validates watchdog, rank aggregation, and cleanup only; "
        "it does not verify Real DLC Hardware or collective correctness."
        if args.controlled_harness else
        "Claim Boundary: bounded collective qualification is producer evidence only; formal model, benchmark, and image acceptance require an independent modelzoo-image-validation run."
    )
    document["qualification"]["execution"] = {
        "harness_command": command,
        "attempt_count": completed_attempts,
        "timeout_seconds": args.timeout_seconds,
        "watchdog_actions": actions,
        "rank_results": rows,
        "correctness": correctness_rows,
        "process_tree_cleanup": {
            "termination_requested": termination_requested,
            "inspection_complete": inspection_complete,
            "residual_pids": sorted(pid for pid in residual if pid > 0),
            "hbm_status": "not_verified",
            "status": "passed" if inspection_complete and not residual else "failed",
        },
        "health_snapshot": {
            "status": "not_verified",
            "source": "controlled_fixture" if args.controlled_harness else "real_dlc_hardware",
            "snapshot_digest": None,
        },
    }
    seal(document)
    try:
        CONTRACT.validate_document(document)
    except CONTRACT.ContractError as error:
        print(json.dumps({"code": error.code, "path": error.path, "message": error.message}))
        return 20
    args.output.write_bytes(CONTRACT.canonical_bytes(document) + b"\n")
    print(json.dumps({"status": document["status"], "reason_code": document["primary_blocker"]["code"] if document["primary_blocker"] else "passed", "launched": True, "digest": document["digest"]}, sort_keys=True))
    execution_failures = {
        row["code"] for row in document["blockers"]
    } & {"failed_collective_completion", "failed_collective_correctness"}
    return 30 if execution_failures else 0 if document["status"] == "passed" else 24


if __name__ == "__main__":
    raise SystemExit(main())
