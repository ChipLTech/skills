#!/usr/bin/env python3
"""Read-only validator for DLC Chrome Trace Event profiling artifacts."""

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


MANIFEST_SCHEMA = "dlc-profile-evidence-manifest/v1"
RESULT_SCHEMA = "dlc-profile-validation-result/v1"
SEMANTIC_SCHEMA = "dlc-profile-semantic-artifact/v1"
VALIDATOR_VERSION = "1.0.0"
SCOPES = ("trace_track", "request", "phase", "rank", "device")
SCOPE_FIELDS = tuple("valid_for_%s_localization" % scope for scope in SCOPES)
STATUSES = ("passed", "failed", "blocked", "not_verified")
TRACE_SCHEMAS = ("chrome-trace-event-json/v1",)
TIME_UNITS = ("ns", "us", "ms")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")

ENVELOPE_FIELDS = {
    "schema_version", "artifact_id", "producer", "producer_version", "created_at",
    "subject_identity", "input_artifact_digests", "evidence_class", "authoritativeness",
    "acceptance_eligible", "status", "blockers", "primary_blocker", "resume_point",
    "claim_boundary", "unverified_scope", "digest",
}
MANIFEST_EXTENSION_FIELDS = (
    "trace",
    "acquisition",
    "expected_localization_scopes",
    "semantic_producer",
    "diagnostic_epoch",
    "profiler_perturbation",
    "hardware_counters",
    "smi_reference",
    "cleanup_reference",
)
RESULT_EXTENSION_FIELDS = (
    "validator_version", "manifest_digest", "trace_digest", "trace_schema", "time_unit",
    "trace_event_count", "trace_syntax_valid", "trace_byte_identity_valid", "counter_state",
    *SCOPE_FIELDS, "stale_evidence_reason",
)
SEMANTIC_EXTENSION_FIELDS = (
    "trace_digest", "workload_digest", "diagnostic_epoch", "localization_scopes",
    "request_event_bindings",
)
_MANIFEST_FIELDS = ENVELOPE_FIELDS | set(MANIFEST_EXTENSION_FIELDS)
_TRACE_FIELDS = {"path", "digest", "schema", "time_unit"}
_ACQUISITION_FIELDS = {"entry", "config_digest", "evidence_sources"}
_SEMANTIC_FIELDS = {"producer", "artifact_path", "artifact_digest"}
_COUNTER_FIELDS = {"state", "artifact_path", "artifact_digest"}
_EVENT_REQUIRED = {"name", "ph", "pid", "tid", "ts", "dur", "args"}
_EVENT_ALLOWED = _EVENT_REQUIRED | {"cat", "id", "bp", "s", "tts", "tdur"}


def _load_contract_module() -> Any:
    path = Path(__file__).with_name("_generated_contracts") / "qualification_artifact.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("dlc_profile_qualification_artifact", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CONTRACT = _load_contract_module()


def canonical_json(document: Mapping[str, Any]) -> bytes:
    if _CONTRACT is None:
        raise RuntimeError("generated qualification artifact contract is required")
    return _CONTRACT.canonical_json(document)


def canonical_digest(document: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(document)).hexdigest()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _problem(status: str, code: str, path: str) -> Dict[str, str]:
    return {"status": status, "code": code, "path": path}


def _sort_problems(problems: Sequence[Mapping[str, str]]) -> List[Dict[str, str]]:
    rank = {"failed": 0, "blocked": 1, "not_verified": 2}
    unique = {(row["status"], row["code"], row["path"]): dict(row) for row in problems}
    return sorted(unique.values(), key=lambda row: (rank[row["status"]], row["code"], row["path"]))


def _is_digest(value: Any) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _closed_fields(value: Any, fields: set, path: str, problems: List[Dict[str, str]]) -> bool:
    if not isinstance(value, dict):
        problems.append(_problem("failed", "invalid_type", path))
        return False
    for field in sorted(set(value) - fields):
        problems.append(_problem("failed", "unknown_field", "%s.%s" % (path, field)))
    for field in sorted(fields - set(value)):
        problems.append(_problem("failed", "missing_required_field", "%s.%s" % (path, field)))
    return set(value) == fields


def validate_manifest_shape(manifest: Any) -> List[Dict[str, str]]:
    if _CONTRACT is None:
        return [_problem("blocked", "missing_generated_contract", "$._generated_contracts.qualification_artifact")]
    problems: List[Dict[str, str]] = []
    if not _closed_fields(manifest, _MANIFEST_FIELDS, "$", problems):
        if not isinstance(manifest, dict):
            return problems
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        problems.append(_problem("failed", "unsupported_schema_version", "$.schema_version"))
    if not isinstance(manifest.get("artifact_id"), str) or not manifest.get("artifact_id"):
        problems.append(_problem("failed", "invalid_value", "$.artifact_id"))
    problems.extend(
        _problem("blocked" if error["code"] == "missing_identity" else "failed", error["code"], error["path"])
        for error in _CONTRACT.validate_envelope(manifest, MANIFEST_EXTENSION_FIELDS)
    )
    trace = manifest.get("trace")
    if _closed_fields(trace, _TRACE_FIELDS, "$.trace", problems):
        if not isinstance(trace["path"], str) or not trace["path"]:
            problems.append(_problem("failed", "invalid_value", "$.trace.path"))
        if not _is_digest(trace["digest"]):
            problems.append(_problem("failed", "missing_trace_digest", "$.trace.digest"))
        if trace["schema"] not in TRACE_SCHEMAS:
            problems.append(_problem("failed", "unsupported_trace_schema", "$.trace.schema"))
        if trace["time_unit"] not in TIME_UNITS:
            problems.append(_problem("failed", "unsupported_time_unit", "$.trace.time_unit"))
    acquisition = manifest.get("acquisition")
    if _closed_fields(acquisition, _ACQUISITION_FIELDS, "$.acquisition", problems):
        if not isinstance(acquisition["entry"], str) or not acquisition["entry"]:
            problems.append(_problem("failed", "invalid_value", "$.acquisition.entry"))
        if not _is_digest(acquisition["config_digest"]):
            problems.append(_problem("failed", "invalid_digest", "$.acquisition.config_digest"))
        sources = acquisition["evidence_sources"]
        if not isinstance(sources, list) or not sources or not all(isinstance(item, str) and item for item in sources):
            problems.append(_problem("failed", "invalid_value", "$.acquisition.evidence_sources"))
        elif set(sources) <= {"profiler_start_success", "profiler_stop_success"}:
            problems.append(_problem("failed", "unsupported_success_stub_not_evidence", "$.acquisition.evidence_sources"))
    scopes = manifest.get("expected_localization_scopes")
    if not isinstance(scopes, dict):
        problems.append(_problem("failed", "invalid_type", "$.expected_localization_scopes"))
    else:
        for field in sorted(set(scopes) - set(SCOPES)):
            problems.append(_problem("failed", "unknown_field", "$.expected_localization_scopes.%s" % field))
        for field in SCOPES:
            if field not in scopes:
                problems.append(_problem("failed", "missing_required_field", "$.expected_localization_scopes.%s" % field))
            elif not isinstance(scopes[field], bool):
                problems.append(_problem("failed", "invalid_type", "$.expected_localization_scopes.%s" % field))
    semantic = manifest.get("semantic_producer")
    if semantic is not None and _closed_fields(semantic, _SEMANTIC_FIELDS, "$.semantic_producer", problems):
        if not all(isinstance(semantic[field], str) and semantic[field] for field in ("producer", "artifact_path")):
            problems.append(_problem("failed", "invalid_value", "$.semantic_producer"))
        if not _is_digest(semantic["artifact_digest"]):
            problems.append(_problem("failed", "invalid_digest", "$.semantic_producer.artifact_digest"))
    if isinstance(trace, dict):
        expected_inputs = [trace.get("digest")]
        if isinstance(semantic, dict):
            expected_inputs.append(semantic.get("artifact_digest"))
        if manifest.get("input_artifact_digests") != expected_inputs:
            problems.append(_problem("failed", "input_artifact_binding_mismatch", "$.input_artifact_digests"))
    if manifest.get("diagnostic_epoch") != "diagnostic":
        problems.append(_problem("failed", "diagnostic_cannot_be_formal_benchmark", "$.diagnostic_epoch"))
    perturbation = manifest.get("profiler_perturbation")
    if not isinstance(perturbation, list) or not all(isinstance(item, str) and item for item in perturbation):
        problems.append(_problem("failed", "invalid_value", "$.profiler_perturbation"))
    counters = manifest.get("hardware_counters")
    if _closed_fields(counters, _COUNTER_FIELDS, "$.hardware_counters", problems):
        if counters["state"] not in ("not_verified", "present"):
            problems.append(_problem("failed", "invalid_value", "$.hardware_counters.state"))
        if counters["state"] == "present" and (not counters["artifact_path"] or not _is_digest(counters["artifact_digest"])):
            problems.append(_problem("failed", "claimed_counter_artifact_missing", "$.hardware_counters"))
        if counters["state"] == "not_verified" and (counters["artifact_path"] is not None or counters["artifact_digest"] is not None):
            problems.append(_problem("failed", "inconsistent_counter_state", "$.hardware_counters"))
    for field in ("smi_reference", "cleanup_reference"):
        if manifest.get(field) is not None and not _is_digest(manifest.get(field)):
            problems.append(_problem("failed", "invalid_digest", "$.%s" % field))
    if not isinstance(manifest.get("claim_boundary"), str) or not manifest.get("claim_boundary"):
        problems.append(_problem("failed", "invalid_value", "$.claim_boundary"))
    return _sort_problems(problems)


def validate_trace_document(document: Any) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
    problems: List[Dict[str, str]] = []
    if not isinstance(document, dict) or set(document) != {"traceEvents"}:
        if not isinstance(document, dict):
            return [_problem("failed", "invalid_trace_root", "$.trace")], []
        for field in sorted(set(document) - {"traceEvents"}):
            problems.append(_problem("failed", "unknown_trace_field", "$.trace.%s" % field))
        if "traceEvents" not in document:
            problems.append(_problem("failed", "missing_trace_events", "$.trace.traceEvents"))
    events = document.get("traceEvents") if isinstance(document, dict) else None
    if not isinstance(events, list) or not events:
        problems.append(_problem("failed", "invalid_trace_events", "$.trace.traceEvents"))
        return _sort_problems(problems), []
    complete: List[Dict[str, Any]] = []
    for index, event in enumerate(events):
        path = "$.trace.traceEvents[%d]" % index
        if not isinstance(event, dict):
            problems.append(_problem("failed", "invalid_trace_event", path))
            continue
        for field in sorted(set(event) - _EVENT_ALLOWED):
            problems.append(_problem("failed", "unknown_trace_event_field", "%s.%s" % (path, field)))
        if event.get("ph") != "X":
            continue
        if not _EVENT_REQUIRED <= set(event):
            problems.append(_problem("failed", "incomplete_complete_event", path))
            continue
        if not isinstance(event["name"], str) or not event["name"] or type(event["ts"]) is not int or event["ts"] < 0 or type(event["dur"]) is not int or event["dur"] < 0 or not isinstance(event["args"], dict):
            problems.append(_problem("failed", "invalid_complete_event", path))
            continue
        if type(event["pid"]) not in (int, str) or type(event["tid"]) not in (int, str):
            problems.append(_problem("failed", "invalid_trace_track", path))
            continue
        complete.append(event)
    if not complete:
        problems.append(_problem("failed", "missing_complete_events", "$.trace.traceEvents"))
    return _sort_problems(problems), complete


def _validate_semantic_artifact(
    document: Any, manifest: Mapping[str, Any], expected_producer: str
) -> Tuple[List[Dict[str, str]], Sequence[str]]:
    problems: List[Dict[str, str]] = []
    if not isinstance(document, dict):
        return [_problem("failed", "invalid_semantic_artifact", "$.semantic_producer.artifact_path")], ()
    envelope_errors = _CONTRACT.validate_envelope(document, SEMANTIC_EXTENSION_FIELDS)
    problems.extend(
        _problem("failed", "invalid_semantic_artifact", "$.semantic_producer.artifact_path")
        for _ in envelope_errors
    )
    scopes = document.get("localization_scopes")
    if (
        not isinstance(scopes, list)
        or not scopes
        or len(scopes) != len(set(scopes))
        or any(scope != "request" for scope in scopes)
    ):
        problems.append(_problem("failed", "invalid_semantic_artifact", "$.semantic_producer.artifact_path"))
    bindings_value = document.get("request_event_bindings")
    bindings_valid = isinstance(bindings_value, list)
    if bindings_valid:
        seen_bindings = set()
        for binding in bindings_value:
            if not isinstance(binding, dict) or set(binding) != {"request_id", "name", "pid", "tid", "ts", "dur"}:
                bindings_valid = False
                break
            values = (binding["request_id"], binding["name"], binding["pid"], binding["tid"], binding["ts"], binding["dur"])
            key = tuple(values)
            if (
                not isinstance(binding["request_id"], str) or not binding["request_id"]
                or not isinstance(binding["name"], str) or not binding["name"]
                or type(binding["pid"]) not in (int, str)
                or type(binding["tid"]) not in (int, str)
                or type(binding["ts"]) is not int or binding["ts"] < 0
                or type(binding["dur"]) is not int or binding["dur"] < 0
                or key in seen_bindings
            ):
                bindings_valid = False
                break
            seen_bindings.add(key)
    if not bindings_valid or ("request" in scopes and not bindings_value):
        problems.append(_problem("failed", "invalid_semantic_request_binding", "$.semantic_producer.artifact_path"))
    trace = manifest.get("trace", {})
    identity = manifest.get("subject_identity", {})
    bindings = (
        (document.get("producer"), expected_producer),
        (document.get("trace_digest"), trace.get("digest")),
        (document.get("workload_digest"), identity.get("workload", {}).get("digest") if isinstance(identity.get("workload"), dict) else None),
        (document.get("subject_identity"), identity),
        (document.get("diagnostic_epoch"), manifest.get("diagnostic_epoch")),
        (document.get("input_artifact_digests"), [trace.get("digest")]),
    )
    if any(actual != expected for actual, expected in bindings):
        problems.append(_problem("failed", "semantic_binding_mismatch", "$.semantic_producer.artifact_path"))
    problems = _sort_problems(problems)
    return problems, tuple(scopes) if not problems else ()


def validate_profile(manifest: Any, manifest_path: Path, current_identity: Any = None) -> Dict[str, Any]:
    if _CONTRACT is None:
        blocker = _problem("blocked", "missing_generated_contract", "$._generated_contracts.qualification_artifact")
        return {"schema_version": RESULT_SCHEMA, "status": "blocked", "blockers": [blocker], "primary_blocker": blocker}
    problems = validate_manifest_shape(manifest)
    try:
        manifest_digest = canonical_digest(manifest) if isinstance(manifest, dict) else None
    except (TypeError, ValueError):
        problems.append(_problem("failed", "invalid_canonical_value", "$"))
        manifest_digest = None
    trace_syntax = "not_verified"
    byte_identity = "not_verified"
    scope_status = {scope: "not_verified" for scope in SCOPES}
    counter_state = "not_verified"
    actual_trace_digest: Optional[str] = None
    trace_event_count = 0

    trace_spec = manifest.get("trace") if isinstance(manifest, dict) else None
    trace_path: Optional[Path] = None
    if isinstance(trace_spec, dict) and isinstance(trace_spec.get("path"), str):
        candidate = Path(trace_spec["path"])
        trace_path = candidate if candidate.is_absolute() else (manifest_path.parent / candidate).resolve()
        if not trace_path.is_file():
            problems.append(_problem("blocked", "blocked_missing_profile_artifact", "$.trace.path"))
        else:
            actual_trace_digest = file_digest(trace_path)
            if _is_digest(trace_spec.get("digest")):
                if actual_trace_digest == trace_spec["digest"]:
                    byte_identity = "passed"
                else:
                    byte_identity = "failed"
                    problems.append(_problem("failed", "trace_digest_mismatch", "$.trace.digest"))
            try:
                trace_document = json.loads(trace_path.read_bytes())
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                trace_syntax = "failed"
                problems.append(_problem("failed", "malformed_trace_json", "$.trace.path"))
            else:
                trace_problems, events = validate_trace_document(trace_document)
                problems.extend(trace_problems)
                trace_syntax = "failed" if trace_problems else "passed"
                trace_event_count = len(events)
                if trace_syntax == "passed" and byte_identity == "passed":
                    scope_status["trace_track"] = "passed"
                elif trace_syntax == "failed" or byte_identity == "failed":
                    scope_status["trace_track"] = "failed"

    semantic = manifest.get("semantic_producer") if isinstance(manifest, dict) else None
    semantic_valid = False
    semantic_scopes: Sequence[str] = ()
    if isinstance(semantic, dict) and isinstance(semantic.get("artifact_path"), str):
        semantic_path = Path(semantic["artifact_path"])
        if not semantic_path.is_absolute():
            semantic_path = (manifest_path.parent / semantic_path).resolve()
        if not semantic_path.is_file():
            problems.append(_problem("blocked", "blocked_missing_semantic_artifact", "$.semantic_producer.artifact_path"))
        elif _is_digest(semantic.get("artifact_digest")) and file_digest(semantic_path) != semantic["artifact_digest"]:
            problems.append(_problem("failed", "semantic_artifact_digest_mismatch", "$.semantic_producer.artifact_digest"))
        else:
            try:
                semantic_document = json.loads(semantic_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                problems.append(_problem("failed", "invalid_semantic_artifact", "$.semantic_producer.artifact_path"))
            else:
                semantic_problems, semantic_scopes = _validate_semantic_artifact(
                    semantic_document, manifest, semantic.get("producer")
                )
                problems.extend(semantic_problems)
                semantic_valid = not semantic_problems
    if scope_status["trace_track"] == "passed" and semantic_valid:
        for scope in semantic_scopes:
            scope_status[scope] = "passed"

    expected = manifest.get("expected_localization_scopes") if isinstance(manifest, dict) else None
    if isinstance(expected, dict):
        for scope in SCOPES:
            missing_input = any(row["code"] in ("blocked_missing_profile_artifact", "blocked_missing_semantic_artifact") for row in problems)
            if expected.get(scope) is True and scope_status[scope] != "passed" and not missing_input:
                scope_status[scope] = "failed"
                problems.append(_problem("failed", "claimed_localization_scope_unproven", "$.expected_localization_scopes.%s" % scope))

    counters = manifest.get("hardware_counters") if isinstance(manifest, dict) else None
    if isinstance(counters, dict):
        counter_state = counters.get("state", "not_verified")
        if counter_state == "present" and isinstance(counters.get("artifact_path"), str):
            counter_path = Path(counters["artifact_path"])
            if not counter_path.is_absolute():
                counter_path = (manifest_path.parent / counter_path).resolve()
            if not counter_path.is_file():
                counter_state = "failed"
                problems.append(_problem("failed", "claimed_counter_artifact_missing", "$.hardware_counters.artifact_path"))
            elif file_digest(counter_path) != counters.get("artifact_digest"):
                counter_state = "failed"
                problems.append(_problem("failed", "counter_artifact_digest_mismatch", "$.hardware_counters.artifact_digest"))

    if current_identity is not None and isinstance(manifest, dict):
        stale = _CONTRACT.stale_identity_blockers(manifest.get("subject_identity", {}), current_identity)
        problems.extend(stale)
        if stale:
            scope_status = {scope: "not_verified" for scope in SCOPES}

    problems = _sort_problems(problems)
    status = problems[0]["status"] if problems else "passed"
    result: Dict[str, Any] = {
        "schema_version": RESULT_SCHEMA,
        "artifact_id": "%s-validation" % manifest.get("artifact_id") if isinstance(manifest, dict) else "invalid-manifest-validation",
        "producer": "diagnosing-bugs/profile-artifact-validator",
        "producer_version": VALIDATOR_VERSION,
        "created_at": manifest.get("created_at") if isinstance(manifest, dict) else "1970-01-01T00:00:00Z",
        "subject_identity": manifest.get("subject_identity") if isinstance(manifest, dict) else {},
        "input_artifact_digests": [manifest_digest] if manifest_digest else [],
        "evidence_class": "diagnostic",
        "authoritativeness": "non_authoritative",
        "acceptance_eligible": False,
        "validator_version": VALIDATOR_VERSION,
        "manifest_digest": manifest_digest,
        "trace_digest": actual_trace_digest,
        "trace_schema": trace_spec.get("schema") if isinstance(trace_spec, dict) else None,
        "time_unit": trace_spec.get("time_unit") if isinstance(trace_spec, dict) else None,
        "trace_event_count": trace_event_count,
        "trace_syntax_valid": trace_syntax,
        "trace_byte_identity_valid": byte_identity,
        "counter_state": counter_state,
        "status": status,
        "blockers": problems,
        "primary_blocker": problems[0] if problems else None,
        "resume_point": "supply_or_reseal_profile_artifact" if any(row["code"] == "blocked_missing_profile_artifact" for row in problems) else ("repair_profile_evidence" if problems else None),
        "claim_boundary": "Diagnostic localization evidence only; not a formal benchmark, OS process identity, rank, device, request, or causal performance claim unless its explicit scope passed.",
        "unverified_scope": [scope for scope in SCOPES if scope_status[scope] != "passed"] + ["formal_benchmark"],
        "stale_evidence_reason": next((row["path"] for row in problems if row["code"] == "stale_identity"), None),
    }
    for scope, field in zip(SCOPES, SCOPE_FIELDS):
        result[field] = scope_status[scope]
    result["digest"] = canonical_digest(result)
    return result


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="dlc-profile-evidence-manifest/v1 JSON")
    parser.add_argument("--current-identity", type=Path, help="current subject_identity JSON for freshness validation")
    args = parser.parse_args(argv)
    try:
        manifest = _load_json(args.manifest)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        result = {
            "schema_version": RESULT_SCHEMA,
            "status": "failed",
            "blockers": [_problem("failed", "malformed_manifest_json", "$")],
            "primary_blocker": _problem("failed", "malformed_manifest_json", "$"),
        }
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 1
    current_identity = None
    if args.current_identity is not None:
        try:
            current_identity = _load_json(args.current_identity)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            print(json.dumps({"schema_version": RESULT_SCHEMA, "status": "failed", "blockers": [_problem("failed", "malformed_current_identity", "$.subject_identity")]}, sort_keys=True, separators=(",", ":")))
            return 1
    result = validate_profile(manifest, args.manifest.resolve(), current_identity)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
