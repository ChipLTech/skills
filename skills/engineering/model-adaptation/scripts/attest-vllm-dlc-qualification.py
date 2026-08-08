#!/usr/bin/env python3
"""Attest only a canonical, passed distributed qualification for vLLM startup."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


VALIDATOR_PATH = Path(__file__).with_name("validate-vllm-dlc-qualification.py")
SPEC = importlib.util.spec_from_file_location("distributed_qualification", VALIDATOR_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load canonical distributed qualification validator")
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)
COLLECTOR_PATH = Path(__file__).with_name("collect-vllm-dlc-live-identity.py")
COLLECTOR_SPEC = importlib.util.spec_from_file_location("live_identity_collector", COLLECTOR_PATH)
if COLLECTOR_SPEC is None or COLLECTOR_SPEC.loader is None:
    raise RuntimeError("cannot load live identity collector")
COLLECTOR = importlib.util.module_from_spec(COLLECTOR_SPEC)
COLLECTOR_SPEC.loader.exec_module(COLLECTOR)


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def validate_live_identity(artifact_path: Path, collector_spec_path: Path) -> dict:
    try:
        document = json.loads(artifact_path.read_text(encoding="utf-8"))
        collector_spec = json.loads(collector_spec_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("blocked_invalid_live_identity_artifact") from error
    errors = COLLECTOR.CONTRACT.validate_envelope(document, ("collection",))
    if errors or document.get("producer") != "model-adaptation/live-identity-collector":
        raise ValueError("blocked_invalid_live_identity_artifact")
    if (
        document.get("status") != "not_verified"
        or document.get("primary_blocker", {}).get("code") != "blocked_non_atomic_identity_snapshot"
        or document.get("evidence_class") != "operational_only"
        or document.get("acceptance_eligible") is not False
        or document.get("subject_identity", {}).get("source", {}).get("kind") != "git"
    ):
        raise ValueError("blocked_non_operational_live_identity")
    current = COLLECTOR.collect(collector_spec)
    if current.get("digest") != document.get("digest"):
        raise ValueError("blocked_stale_live_identity")
    return document["subject_identity"]


def attest(
    artifact_path: Path,
    live_identity_path: Path,
    collector_spec_path: Path,
    primitives: list[str],
    world_size: int,
) -> dict:
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    identity = validate_live_identity(live_identity_path, collector_spec_path)
    live_document = json.loads(live_identity_path.read_text(encoding="utf-8"))
    if live_document.get("authoritativeness") != "operational":
        raise ValueError("blocked_missing_authoritative_identity_producers")
    report = VALIDATOR.validate_document(artifact)
    qualification = artifact["qualification"]
    preflight = qualification["preflight"]
    execution = qualification["execution"]
    if (
        report["status"] != "passed"
        or artifact["subject_identity"] != identity
        or artifact["evidence_class"] != "qualification"
        or artifact["authoritativeness"] != "operational"
        or preflight != {
            "hardware_environment": "real_dlc_hardware",
            "hardware_available": True,
            "authorization_granted": True,
            "requested_operation": "qualify",
        }
        or execution is None
        or execution["process_tree_cleanup"]["status"] != "passed"
        or execution["process_tree_cleanup"]["hbm_status"] != "released"
        or execution["health_snapshot"]["status"] != "healthy"
        or execution["health_snapshot"]["source"] != "real_dlc_hardware"
        or any(row["status"] != "passed" for row in execution["correctness"])
    ):
        raise ValueError("blocked_collective_not_qualified")
    # Live identity is closed, but authorization, official hardware
    # observation, pinned harness, and independent oracle provenance still
    # require a trusted issuance workflow before this producer may sign.
    raise ValueError("blocked_missing_trusted_qualification_inputs")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("live_identity", type=Path)
    parser.add_argument("collector_spec", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--active-primitives", required=True)
    parser.add_argument("--world-size", required=True, type=int)
    args = parser.parse_args()
    try:
        result = attest(
            args.artifact, args.live_identity, args.collector_spec,
            [item.strip() for item in args.active_primitives.split(",") if item.strip()],
            args.world_size,
        )
    except (OSError, ValueError, json.JSONDecodeError, VALIDATOR.ContractError) as error:
        print(json.dumps({"status": "blocked", "blocker": str(error)}, sort_keys=True))
        return 20
    args.output.write_bytes(canonical(result) + b"\n")
    print(json.dumps({"status": "passed", "attestation_digest": file_digest(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
