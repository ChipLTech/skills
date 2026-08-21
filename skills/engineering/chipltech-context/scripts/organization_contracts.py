"""Closed-world Stage O organization contract validation."""

import copy
import datetime as _datetime
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence


SCHEMA_VERSIONS = (
    "agent-evidence-return/v1",
    "engineering-handoff/v1",
    "context-reference-package/v1",
    "team-task-brief/v1",
)
ASSIGNMENT_STATES = ("passed", "failed", "blocked", "not_applicable", "not_verified")
EVIDENCE_CLASSES = (
    "static_snapshot",
    "fixture",
    "diagnostic",
    "operational_only",
    "qualification",
    "formal_acceptance",
)
OPTIONAL_LEDGER_PROFILE = {
    "profile_id": "task-plan-round-ledger/v1",
    "required_characteristics": (
        "multiple_candidates", "multiple_rounds", "resumable", "real_scenario"
    ),
}

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_SCHEMA_VERSION = re.compile(r"^[a-z0-9][a-z0-9-]*/v1$")
_TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z$"
)
_CLAIM_BOUNDARY = re.compile(
    r"^Claim Boundary: Establishes [^;\r\n]+; does not establish [^\r\n]+$"
)
_REFERENCE_FIELDS = ("artifact_id", "schema_version", "uri", "digest")
_FIELDS = {
    "agent-evidence-return/v1": (
        "schema_version", "return_id", "task_id", "producer", "role",
        "assignment_state", "evidence_references", "claims", "changed_artifacts",
        "blocker_reference", "resume_point", "unverified_scope", "claim_boundary", "digest",
    ),
    "context-reference-package/v1": (
        "schema_version", "package_id", "owning_skill", "created_at", "references",
        "freshness", "claim_boundary", "digest",
    ),
    "engineering-handoff/v1": (
        "schema_version", "handoff_id", "task_id", "objective", "current_state",
        "fact_baseline_references", "decision_references", "evidence_return_references",
        "failed_attempts_not_to_repeat", "context_package_reference", "next",
        "authorizations_still_required", "invalidation_conditions", "claim_boundary", "digest",
    ),
    "team-task-brief/v1": (
        "schema_version", "brief_id", "objective", "current_behavior", "desired_behavior",
        "scope", "out_of_scope", "owning_skill", "execution_locus", "required_identities",
        "required_authorizations", "acceptance_criteria", "context_package_reference",
        "claim_boundary", "digest",
    ),
}


def canonical_json(document: Mapping[str, Any]) -> bytes:
    """Return UTF-8 canonical JSON bytes, omitting only top-level digest."""
    if not isinstance(document, Mapping):
        raise TypeError("document must be a mapping")
    payload = dict(document)
    payload.pop("digest", None)
    _reject_floats(payload, "$")
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_digest(document: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(document)).hexdigest()


def seal_document(document: Mapping[str, Any]) -> Dict[str, Any]:
    sealed = copy.deepcopy(dict(document))
    sealed["digest"] = canonical_digest(sealed)
    return sealed


def validate_document(
    document: Any,
    artifacts_by_digest: Mapping[str, Any] = None,
    fixture_mode: bool = False,
) -> List[Dict[str, str]]:
    """Validate one organization document and all supplied reference content."""
    if not isinstance(document, Mapping):
        return [_error("invalid_type", "$")]
    if artifacts_by_digest is not None and not isinstance(artifacts_by_digest, Mapping):
        return [_error("invalid_type", "$.artifacts_by_digest")]
    artifacts = artifacts_by_digest or {}
    schema = document.get("schema_version")
    if not isinstance(schema, str) or schema not in SCHEMA_VERSIONS:
        return [_error("unsupported_schema_version", "$.schema_version")]

    errors: List[Dict[str, str]] = []
    required = _FIELDS[schema]
    try:
        unknown_fields = sorted(
            (key for key in document if key not in required), key=str
        )
    except TypeError:
        return [_error("invalid_type", "$")]
    for field in unknown_fields:
        errors.append(_error("unknown_field", f"$.{field}"))
    for field in required:
        if field not in document:
            errors.append(_error("missing_required_field", f"$.{field}"))

    if "digest" in document:
        try:
            valid_digest = _valid_digest(document["digest"])
            matches = document["digest"] == canonical_digest(document)
        except (TypeError, ValueError):
            errors.append(_error("invalid_canonical_value", "$"))
        else:
            if not valid_digest or not matches:
                errors.append(_error("digest_mismatch", "$.digest"))

    if schema == "agent-evidence-return/v1":
        errors.extend(_validate_evidence_return(document, artifacts, fixture_mode))
    elif schema == "context-reference-package/v1":
        errors.extend(_validate_context_package(document, artifacts))
    elif schema == "engineering-handoff/v1":
        errors.extend(_validate_handoff(document, artifacts, fixture_mode))
    else:
        errors.extend(_validate_brief(document, artifacts))
    return _deduplicate(errors)


def validate_ledger_profile_applicability(
    characteristics: Mapping[str, Any], adapters: Sequence[str] = ()
) -> List[Dict[str, str]]:
    """Report whether the optional ledger profile has a non-speculative seam."""
    if not isinstance(characteristics, Mapping):
        return [_error("invalid_type", "$.characteristics")]
    try:
        unknown = sorted(
            (key for key in characteristics if key not in OPTIONAL_LEDGER_PROFILE["required_characteristics"]),
            key=str,
        )
    except TypeError:
        return [_error("invalid_type", "$.characteristics")]
    if unknown:
        return [_error("unknown_field", f"$.characteristics.{unknown[0]}")]
    missing = [
        name for name in OPTIONAL_LEDGER_PROFILE["required_characteristics"]
        if characteristics.get(name) is not True
    ]
    if missing:
        return [_error("ledger_profile_not_applicable", f"$.characteristics.{missing[0]}")]
    if (
        not isinstance(adapters, Sequence)
        or isinstance(adapters, (str, bytes))
        or not all(isinstance(adapter, str) and adapter for adapter in adapters)
    ):
        return [_error("ledger_profile_not_applicable", "$.adapters")]
    return []


def _validate_evidence_return(document, artifacts, fixture_mode):
    errors = _nonempty_fields(
        document, ("return_id", "task_id", "producer", "role", "claim_boundary")
    )
    errors.extend(_validate_claim_boundary(document.get("claim_boundary")))
    state = document.get("assignment_state")
    if state not in ASSIGNMENT_STATES:
        errors.append(_error("invalid_value", "$.assignment_state"))
    references = document.get("evidence_references")
    errors.extend(_validate_reference_list(references, "$.evidence_references", artifacts, fixture_mode))
    claims = document.get("claims")
    declared = [
        item.get("digest") for item in references if isinstance(item, Mapping)
    ] if isinstance(references, list) else []
    if not isinstance(claims, list) or not claims:
        errors.append(_error("invalid_value", "$.claims"))
    else:
        for index, claim in enumerate(claims):
            path = f"$.claims[{index}]"
            errors.extend(_validate_object(claim, ("claim_id", "statement", "evidence_reference_digests"), path))
            if not isinstance(claim, Mapping):
                continue
            errors.extend(_nonempty_fields(claim, ("claim_id", "statement"), path))
            digests = claim.get("evidence_reference_digests")
            if not isinstance(digests, list) or not digests:
                errors.append(_error("missing_required_reference", f"{path}.evidence_reference_digests"))
            else:
                errors.extend(_validate_unique_digests(digests, f"{path}.evidence_reference_digests"))
                for ref_index, digest in enumerate(digests):
                    if digest not in declared:
                        errors.append(_error(
                            "unclosed_claim_evidence_reference",
                            f"{path}.evidence_reference_digests[{ref_index}]",
                        ))
    errors.extend(_validate_string_list(document.get("changed_artifacts"), "$.changed_artifacts"))
    errors.extend(_validate_string_list(document.get("unverified_scope"), "$.unverified_scope"))
    blocker = document.get("blocker_reference")
    resume = document.get("resume_point")
    if state in ("failed", "blocked", "not_verified"):
        if blocker is None:
            errors.append(_error("missing_required_reference", "$.blocker_reference"))
        else:
            errors.extend(_validate_reference(blocker, "$.blocker_reference", artifacts, fixture_mode))
        if not _nonempty(resume):
            errors.append(_error("invalid_resume_point", "$.resume_point"))
    else:
        if blocker is not None:
            errors.append(_error("invalid_blocker_reference", "$.blocker_reference"))
        if resume is not None:
            errors.append(_error("invalid_resume_point", "$.resume_point"))
    return errors


def _validate_context_package(document, artifacts):
    errors = _nonempty_fields(document, ("package_id", "owning_skill", "claim_boundary"))
    errors.extend(_validate_claim_boundary(document.get("claim_boundary")))
    if not _valid_timestamp(document.get("created_at")):
        errors.append(_error("invalid_value", "$.created_at"))
    references = document.get("references")
    if not isinstance(references, list) or not references:
        errors.append(_error("invalid_value", "$.references"))
    else:
        ids = []
        for index, reference in enumerate(references):
            path = f"$.references[{index}]"
            fields = ("reference_id", "kind", "uri", "digest", "access", "authority", "execution_locus")
            errors.extend(_validate_object(reference, fields, path))
            if not isinstance(reference, Mapping):
                continue
            errors.extend(_nonempty_fields(
                reference, ("reference_id", "uri", "execution_locus"), path
            ))
            ids.append(reference.get("reference_id"))
            if reference.get("kind") not in (
                "terminology", "repository_navigation", "capability_catalog", "contract",
                "runbook", "case", "prompt",
            ):
                errors.append(_error("invalid_value", f"{path}.kind"))
            if reference.get("access") not in ("required", "optional", "forbidden"):
                errors.append(_error("invalid_value", f"{path}.access"))
            if reference.get("authority") not in ("canonical", "supporting", "historical"):
                errors.append(_error("invalid_value", f"{path}.authority"))
            errors.extend(_validate_resolved_digest(
                reference, path, artifacts, allow_raw_bytes=True
            ))
        if _has_duplicates(ids):
            errors.append(_error("duplicate_reference", "$.references"))
    freshness = document.get("freshness")
    errors.extend(_validate_object(freshness, ("checked_at", "invalidation_conditions"), "$.freshness"))
    if isinstance(freshness, Mapping):
        if not _valid_timestamp(freshness.get("checked_at")):
            errors.append(_error("invalid_value", "$.freshness.checked_at"))
        errors.extend(_validate_string_list(
            freshness.get("invalidation_conditions"), "$.freshness.invalidation_conditions", require_nonempty=True
        ))
    return errors


def _validate_handoff(document, artifacts, fixture_mode):
    errors = _nonempty_fields(
        document, ("handoff_id", "task_id", "objective", "current_state", "claim_boundary")
    )
    errors.extend(_validate_claim_boundary(document.get("claim_boundary")))
    for field in ("fact_baseline_references", "decision_references"):
        errors.extend(_validate_reference_list(document.get(field), f"$.{field}", artifacts, fixture_mode))
    returns = document.get("evidence_return_references")
    errors.extend(_validate_reference_list(returns, "$.evidence_return_references", artifacts, fixture_mode))
    if not isinstance(returns, list) or not returns:
        errors.append(_error("missing_required_reference", "$.evidence_return_references"))
    elif any(
        isinstance(reference, Mapping)
        and reference.get("schema_version") != "agent-evidence-return/v1"
        for reference in returns
    ):
        errors.append(_error("invalid_reference_schema", "$.evidence_return_references"))
    context = document.get("context_package_reference")
    if context is None:
        errors.append(_error("missing_required_reference", "$.context_package_reference"))
    else:
        errors.extend(_validate_reference(context, "$.context_package_reference", artifacts, fixture_mode))
        if isinstance(context, Mapping) and context.get("schema_version") != "context-reference-package/v1":
            errors.append(_error("invalid_reference_schema", "$.context_package_reference"))
    for field in (
        "failed_attempts_not_to_repeat", "authorizations_still_required", "invalidation_conditions"
    ):
        errors.extend(_validate_string_list(document.get(field), f"$.{field}"))
    next_step = document.get("next")
    errors.extend(_validate_object(next_step, ("owner", "action", "criterion", "stop_conditions"), "$.next"))
    if isinstance(next_step, Mapping):
        errors.extend(_nonempty_fields(next_step, ("owner", "action", "criterion"), "$.next"))
        errors.extend(_validate_string_list(next_step.get("stop_conditions"), "$.next.stop_conditions"))
    return errors


def _validate_brief(document, artifacts):
    errors = _nonempty_fields(
        document,
        ("brief_id", "objective", "current_behavior", "desired_behavior", "owning_skill", "execution_locus", "claim_boundary"),
    )
    errors.extend(_validate_claim_boundary(document.get("claim_boundary")))
    for field in ("scope", "out_of_scope", "required_identities", "required_authorizations"):
        errors.extend(_validate_string_list(document.get(field), f"$.{field}"))
    criteria = document.get("acceptance_criteria")
    if not isinstance(criteria, list) or not criteria:
        errors.append(_error("invalid_value", "$.acceptance_criteria"))
    else:
        ids = []
        fields = ("criterion_id", "description", "required_evidence_class", "required_schema_version")
        for index, criterion in enumerate(criteria):
            path = f"$.acceptance_criteria[{index}]"
            errors.extend(_validate_object(criterion, fields, path))
            if not isinstance(criterion, Mapping):
                continue
            ids.append(criterion.get("criterion_id"))
            errors.extend(_nonempty_fields(criterion, fields, path))
            if criterion.get("required_evidence_class") not in EVIDENCE_CLASSES:
                errors.append(_error("invalid_value", f"{path}.required_evidence_class"))
            required_schema = criterion.get("required_schema_version")
            if (
                not isinstance(required_schema, str)
                or _SCHEMA_VERSION.fullmatch(required_schema) is None
                or required_schema in SCHEMA_VERSIONS
            ):
                errors.append(_error("invalid_evidence_schema", f"{path}.required_schema_version"))
        if _has_duplicates(ids):
            errors.append(_error("duplicate_criterion", "$.acceptance_criteria"))
    context = document.get("context_package_reference")
    if context is None:
        errors.append(_error("missing_required_reference", "$.context_package_reference"))
    else:
        errors.extend(_validate_reference(context, "$.context_package_reference", artifacts, False))
        if isinstance(context, Mapping) and context.get("schema_version") != "context-reference-package/v1":
            errors.append(_error("invalid_reference_schema", "$.context_package_reference"))
    return errors


def _validate_reference_list(references, path, artifacts, fixture_mode=False):
    if not isinstance(references, list):
        return [_error("invalid_type", path)]
    errors = []
    digests = []
    for index, reference in enumerate(references):
        errors.extend(_validate_reference(reference, f"{path}[{index}]", artifacts, fixture_mode))
        if isinstance(reference, Mapping):
            digests.append(reference.get("digest"))
    if _has_duplicates(digests):
        errors.append(_error("duplicate_reference", path))
    return errors


def _validate_reference(reference, path, artifacts, fixture_mode=False):
    errors = _validate_object(reference, _REFERENCE_FIELDS, path)
    if not isinstance(reference, Mapping):
        return errors
    errors.extend(_nonempty_fields(reference, ("artifact_id", "schema_version", "uri"), path))
    if not _valid_digest(reference.get("digest")):
        errors.append(_error("invalid_value", f"{path}.digest"))
        return errors
    errors.extend(_validate_resolved_digest(reference, path, artifacts))
    artifact = artifacts.get(reference["digest"])
    if not isinstance(artifact, Mapping):
        return errors
    artifact_id = artifact.get("artifact_id") or artifact.get("return_id") or artifact.get("package_id")
    if artifact_id != reference.get("artifact_id") or artifact.get("schema_version") != reference.get("schema_version"):
        errors.append(_error("reference_identity_mismatch", path))
    if path.startswith("$.evidence_references") and artifact.get("schema_version") in SCHEMA_VERSIONS:
        errors.append(_error("invalid_evidence_schema", path))
    if artifact.get("schema_version") == "qualification-artifact-envelope/v1" or "evidence_class" in artifact:
        try:
            envelope_errors = _qualification_module().validate_envelope(artifact)
        except Exception:
            envelope_errors = [_error("invalid_evidence_artifact", path)]
        if envelope_errors:
            errors.append(_error("invalid_evidence_artifact", path))
        if fixture_mode and (
            artifact.get("evidence_class") != "fixture"
            or artifact.get("authoritativeness") != "non_authoritative"
            or artifact.get("acceptance_eligible") is not False
        ):
            errors.append(_error("fixture_authority_ceiling", path))
    return errors


def _validate_resolved_digest(reference, path, artifacts, allow_raw_bytes=False):
    digest = reference.get("digest") if isinstance(reference, Mapping) else None
    if not _valid_digest(digest):
        return [_error("invalid_value", f"{path}.digest")]
    artifact = artifacts.get(digest)
    if artifact is None:
        return [_error("unresolved_reference", path)]
    try:
        if allow_raw_bytes and isinstance(artifact, bytes):
            current = "sha256:" + hashlib.sha256(artifact).hexdigest()
        elif isinstance(artifact, Mapping):
            current = _artifact_digest(artifact)
        else:
            return [_error("invalid_reference_target", path)]
    except Exception:
        return [_error("invalid_reference_target", path)]
    if current != digest:
        return [_error("stale_reference_digest", path)]
    return []


def _artifact_digest(artifact):
    if artifact.get("schema_version") in SCHEMA_VERSIONS:
        return canonical_digest(artifact)
    return _qualification_module().canonical_digest(artifact)


def _qualification_module():
    path = Path(__file__).with_name("qualification_artifact.py")
    spec = importlib.util.spec_from_file_location("organization_qualification_artifact", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validate_object(value, fields, path):
    if not isinstance(value, Mapping):
        return [_error("invalid_type", path)]
    try:
        errors = [
            _error("unknown_field", f"{path}.{field}")
            for field in sorted((key for key in value if key not in fields), key=str)
        ]
    except TypeError:
        return [_error("invalid_type", path)]
    errors.extend(
        _error("missing_required_field", f"{path}.{field}")
        for field in fields if field not in value
    )
    return errors


def _nonempty_fields(value, fields, path="$"):
    if not isinstance(value, Mapping):
        return []
    return [
        _error("invalid_value", f"{path}.{field}")
        for field in fields if field in value and not _nonempty(value[field])
    ]


def _validate_string_list(value, path, require_nonempty=False):
    if (
        not isinstance(value, list)
        or (require_nonempty and not value)
        or not all(_nonempty(item) for item in value)
        or _has_duplicates(value)
    ):
        return [_error("invalid_value", path)]
    return []


def _validate_claim_boundary(value):
    if not isinstance(value, str) or _CLAIM_BOUNDARY.fullmatch(value) is None:
        return [_error("invalid_claim_boundary", "$.claim_boundary")]
    return []


def _validate_unique_digests(value, path):
    if not all(_valid_digest(item) for item in value) or _has_duplicates(value):
        return [_error("invalid_value", path)]
    return []


def _has_duplicates(values):
    return any(value in values[:index] for index, value in enumerate(values))


def _reject_floats(value, path):
    if isinstance(value, float):
        raise ValueError(f"floating-point value is not canonical at {path}")
    if isinstance(value, Mapping):
        for key, nested in value.items():
            _reject_floats(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_floats(nested, f"{path}[{index}]")


def _valid_timestamp(value):
    if not isinstance(value, str) or not _TIMESTAMP.fullmatch(value):
        return False
    try:
        _datetime.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return True


def _valid_digest(value):
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _nonempty(value):
    return isinstance(value, str) and bool(value)


def _error(code, path):
    return {"code": code, "path": path}


def _deduplicate(errors):
    seen = set()
    result = []
    for error in errors:
        key = (error["code"], error["path"])
        if key not in seen:
            seen.add(key)
            result.append(error)
    return result
