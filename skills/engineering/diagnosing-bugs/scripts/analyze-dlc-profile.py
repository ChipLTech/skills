#!/usr/bin/env python3
"""Produce a deterministic, non-overlapping DLC trace performance breakdown."""

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


BREAKDOWN_SCHEMA = "dlc-perf-breakdown/v1"
ANALYZER_VERSION = "1.0.0"
UNIT_TO_NS = {"ns": 1, "us": 1000, "ms": 1000000}
BREAKDOWN_EXTENSION_FIELDS = (
    "analyzer_version", "source_validation_digest", "source_trace_digest",
    "localization_scope", "localization_scopes", "time_unit", "parent",
    "parent_instance", "inclusive_exclusive_semantics", "components",
    "component_aggregates", "non_overlapping_coverage", "overlap",
    "unmatched_intervals", "unmatched_events", "residual", "identity",
    "smallest_confirmed_boundary", "unresolved_boundaries",
)


def _load_validator() -> Any:
    path = Path(__file__).with_name("validate-dlc-profile-artifacts.py")
    spec = importlib.util.spec_from_file_location("dlc_profile_validator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("profile validator cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = _load_validator()


def _event_key(item: Tuple[int, Mapping[str, Any]]) -> Tuple[Any, ...]:
    index, event = item
    return (event["ts"], -event["dur"], str(event["pid"]), str(event["tid"]), event["name"], index)


def _interval_union(intervals: Iterable[Tuple[int, int]]) -> List[Tuple[int, int]]:
    merged: List[Tuple[int, int]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        elif end > merged[-1][1]:
            merged[-1] = (merged[-1][0], end)
    return merged


def _gaps(start: int, end: int, covered: Sequence[Tuple[int, int]]) -> List[Tuple[int, int]]:
    cursor = start
    gaps: List[Tuple[int, int]] = []
    for child_start, child_end in covered:
        if cursor < child_start:
            gaps.append((cursor, child_start))
        cursor = max(cursor, child_end)
    if cursor < end:
        gaps.append((cursor, end))
    return gaps


def _duration(value: int, unit: str) -> Dict[str, int]:
    return {"trace_units": value, "nanoseconds": value * UNIT_TO_NS[unit]}


def _event_record(index: int, event: Mapping[str, Any], unit: str, relation: str) -> Dict[str, Any]:
    return {
        "event_index": index,
        "name": event["name"],
        "track": {"pid": event["pid"], "tid": event["tid"]},
        "start_trace_units": event["ts"],
        "duration": _duration(event["dur"], unit),
        "relation": relation,
    }


def _direct_children(parent: Tuple[int, Mapping[str, Any]], events: Sequence[Tuple[int, Mapping[str, Any]]]) -> List[Tuple[int, Mapping[str, Any]]]:
    _, parent_event = parent
    start = parent_event["ts"]
    end = start + parent_event["dur"]
    track = (parent_event["pid"], parent_event["tid"])
    contained = [
        item
        for item in events
        if item != parent
        and (item[1]["pid"], item[1]["tid"]) == track
        and start <= item[1]["ts"]
        and item[1]["ts"] + item[1]["dur"] <= end
    ]
    direct = []
    for item in contained:
        item_start = item[1]["ts"]
        item_end = item_start + item[1]["dur"]
        enclosed = any(
            other != item
            and other[1]["ts"] <= item_start
            and item_end <= other[1]["ts"] + other[1]["dur"]
            and (other[1]["ts"], other[1]["dur"]) != (item_start, item[1]["dur"])
            for other in contained
        )
        if not enclosed:
            direct.append(item)
    return sorted(direct, key=_event_key)


def analyze(manifest: Mapping[str, Any], manifest_path: Path, parent_name: str, parent_index: int = 0, scope: str = "trace_track") -> Dict[str, Any]:
    validation = VALIDATOR.validate_profile(manifest, manifest_path)
    required_field = "valid_for_%s_localization" % scope
    if scope not in ("trace_track", "request"):
        return _blocked("unsupported_breakdown_scope", "$.scope", validation)
    if validation.get(required_field) != "passed":
        code = "request_scope_requires_companion_semantic_producer" if scope == "request" else "r1_trace_track_validation_required"
        return _blocked(code, "$.r1_validation.%s" % required_field, validation)
    if validation.get("status") != "passed":
        return _blocked("r1_overall_validation_required", "$.r1_validation.status", validation)

    trace_spec = manifest["trace"]
    trace_path = Path(trace_spec["path"])
    if not trace_path.is_absolute():
        trace_path = (manifest_path.parent / trace_path).resolve()
    document = json.loads(trace_path.read_text(encoding="utf-8"))
    events = [(index, event) for index, event in enumerate(document["traceEvents"]) if isinstance(event, dict) and event.get("ph") == "X"]
    events.sort(key=_event_key)
    parents = [item for item in events if item[1]["name"] == parent_name]
    if parent_index < 0 or parent_index >= len(parents):
        return _blocked("parent_instance_not_found", "$.parent", validation)

    parent = parents[parent_index]
    parent_event = parent[1]
    if parent_event["dur"] <= 0:
        return _blocked("non_positive_parent_duration", "$.parent.dur", validation)
    request_id = None
    if scope == "request":
        semantic = manifest.get("semantic_producer")
        semantic_path = Path(semantic["artifact_path"])
        if not semantic_path.is_absolute():
            semantic_path = (manifest_path.parent / semantic_path).resolve()
        semantic_document = json.loads(semantic_path.read_text(encoding="utf-8"))
        matches = [
            binding for binding in semantic_document["request_event_bindings"]
            if all(binding[field] == parent_event[field] for field in ("name", "pid", "tid", "ts", "dur"))
        ]
        if len(matches) != 1:
            return _blocked("request_event_binding_required", "$.semantic_producer.request_event_bindings", validation)
        request_id = matches[0]["request_id"]
    unit = trace_spec["time_unit"]
    parent_start = parent_event["ts"]
    parent_end = parent_start + parent_event["dur"]
    children = _direct_children(parent, events)
    if not children:
        return _blocked("missing_trace_track_component", "$.components", validation)
    if any(event["dur"] <= 0 for _, event in children):
        return _blocked("non_positive_component_duration", "$.components", validation)
    child_intervals = [(max(parent_start, event["ts"]), min(parent_end, event["ts"] + event["dur"])) for _, event in children]
    covered = _interval_union(child_intervals)
    covered_duration = sum(end - start for start, end in covered)
    child_sum = sum(end - start for start, end in child_intervals)
    overlap_duration = child_sum - covered_duration
    residual = parent_event["dur"] - covered_duration

    unmatched_events: List[Dict[str, Any]] = []
    parent_track = (parent_event["pid"], parent_event["tid"])
    child_indexes = {index for index, _ in children}
    for index, event in events:
        if index == parent[0] or index in child_indexes:
            continue
        event_start = event["ts"]
        event_end = event_start + event["dur"]
        if event_start < parent_end and parent_start < event_end:
            track = (event["pid"], event["tid"])
            relation = "nested_descendant" if track == parent_track and parent_start <= event_start and event_end <= parent_end else ("overlapping_other_trace_track" if track != parent_track else "partial_overlap")
            unmatched_events.append(_event_record(index, event, unit, relation))

    gaps = _gaps(parent_start, parent_end, covered)
    components = [_event_record(index, event, unit, "direct_child") for index, event in children]
    by_name: Dict[str, Dict[str, Any]] = {}
    for component in components:
        row = by_name.setdefault(component["name"], {"name": component["name"], "invocation_count": 0, "duration_trace_units": 0, "duration_nanoseconds": 0})
        row["invocation_count"] += 1
        row["duration_trace_units"] += component["duration"]["trace_units"]
        row["duration_nanoseconds"] += component["duration"]["nanoseconds"]

    result: Dict[str, Any] = {
        "schema_version": BREAKDOWN_SCHEMA,
        "artifact_id": "%s-breakdown" % manifest["artifact_id"],
        "producer": "diagnosing-bugs/perf-breakdown-analyzer",
        "producer_version": ANALYZER_VERSION,
        "created_at": manifest["created_at"],
        "subject_identity": manifest["subject_identity"],
        "input_artifact_digests": [validation["digest"], validation["trace_digest"]],
        "evidence_class": "diagnostic",
        "authoritativeness": "non_authoritative",
        "acceptance_eligible": False,
        "analyzer_version": ANALYZER_VERSION,
        "status": "passed",
        "blockers": [],
        "primary_blocker": None,
        "resume_point": None,
        "source_validation_digest": validation["digest"],
        "source_trace_digest": validation["trace_digest"],
        "localization_scope": scope,
        "localization_scopes": {name: validation["valid_for_%s_localization" % name] for name in VALIDATOR.SCOPES},
        "time_unit": unit,
        "parent": _event_record(parent[0], parent_event, unit, "selected_parent"),
        "parent_instance": parent_index,
        "inclusive_exclusive_semantics": "parent inclusive; direct-child intervals are unioned before coverage; residual is parent inclusive minus covered union",
        "components": components,
        "component_aggregates": [by_name[name] for name in sorted(by_name)],
        "non_overlapping_coverage": {
            "intervals": [{"start_trace_units": start, "end_trace_units": end, "duration": _duration(end - start, unit)} for start, end in covered],
            "duration": _duration(covered_duration, unit),
            "basis_points_of_parent": (covered_duration * 10000 // parent_event["dur"]) if parent_event["dur"] else 0,
        },
        "overlap": {"duration": _duration(overlap_duration, unit), "definition": "sum of direct-child clipped durations minus their interval union"},
        "unmatched_intervals": [{"start_trace_units": start, "end_trace_units": end, "duration": _duration(end - start, unit)} for start, end in gaps],
        "unmatched_events": unmatched_events,
        "residual": {"duration": _duration(residual, unit), "interpretation": "unattributed time; never proof of duplicate execution"},
        "identity": {
            "framework_op": parent_event["name"] if parent_event["name"].startswith("aten::") else None,
            "dlc_custom_op": None,
            "dlc_custom_kernel": None,
            "shape": None,
            "dtype": None,
            "stride": None,
            "layout": None,
            "rank": None,
            "device": None,
            "request": request_id,
        },
        "smallest_confirmed_boundary": {"scope": scope, "parent_name": parent_event["name"], "track": {"pid": parent_event["pid"], "tid": parent_event["tid"]}},
        "unresolved_boundaries": ["request", "rank", "device", "causal_root_cause", "formal_benchmark"],
        "claim_boundary": "Deterministic diagnostic interval accounting only. Track pid/tid are opaque trace-track labels; no OS PID, rank, device, request, root-cause, or formal benchmark claim is inferred.",
        "unverified_scope": [name for name in VALIDATOR.SCOPES if validation["valid_for_%s_localization" % name] != "passed"] + ["causal_root_cause", "formal_benchmark"],
    }
    result["digest"] = VALIDATOR.canonical_digest(result)
    return result


def _blocked(code: str, path: str, validation: Mapping[str, Any]) -> Dict[str, Any]:
    blocker = {"status": "blocked", "code": code, "path": path}
    result = {
        "schema_version": BREAKDOWN_SCHEMA,
        "artifact_id": "%s-breakdown" % validation.get("artifact_id", "invalid-profile"),
        "producer": "diagnosing-bugs/perf-breakdown-analyzer",
        "producer_version": ANALYZER_VERSION,
        "created_at": validation.get("created_at", "1970-01-01T00:00:00Z"),
        "subject_identity": validation.get("subject_identity", {}),
        "input_artifact_digests": [validation["digest"]] if validation.get("digest") else [],
        "evidence_class": "diagnostic",
        "authoritativeness": "non_authoritative",
        "acceptance_eligible": False,
        "analyzer_version": ANALYZER_VERSION,
        "status": "blocked",
        "source_validation_digest": validation.get("digest"),
        "source_trace_digest": validation.get("trace_digest"),
        "localization_scope": None,
        "localization_scopes": {name: validation.get("valid_for_%s_localization" % name, "not_verified") for name in VALIDATOR.SCOPES},
        "time_unit": validation.get("time_unit"),
        "parent": None,
        "parent_instance": None,
        "inclusive_exclusive_semantics": None,
        "components": [],
        "component_aggregates": [],
        "non_overlapping_coverage": None,
        "overlap": None,
        "unmatched_intervals": [],
        "unmatched_events": [],
        "residual": None,
        "identity": None,
        "smallest_confirmed_boundary": None,
        "unresolved_boundaries": list(VALIDATOR.SCOPES) + ["causal_root_cause", "formal_benchmark"],
        "blockers": [blocker],
        "primary_blocker": blocker,
        "resume_point": "repair_profile_evidence",
        "claim_boundary": "No performance breakdown was produced.",
        "unverified_scope": list(VALIDATOR.SCOPES) + ["causal_root_cause", "formal_benchmark"],
    }
    result["digest"] = VALIDATOR.canonical_digest(result)
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--parent-name", required=True)
    parser.add_argument("--parent-index", type=int, default=0)
    parser.add_argument("--scope", choices=("trace_track", "request"), default="trace_track")
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        result = analyze(manifest, args.manifest.resolve(), args.parent_name, args.parent_index, args.scope)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        result = {"schema_version": BREAKDOWN_SCHEMA, "status": "failed", "blockers": [{"status": "failed", "code": "invalid_breakdown_input", "path": "$"}], "detail": str(error)}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if result.get("status") == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
