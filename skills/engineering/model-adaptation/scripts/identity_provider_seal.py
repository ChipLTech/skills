#!/usr/bin/env python3
"""Canonical contract for closed-world DLC identity provider seals."""

from __future__ import annotations

import copy
import datetime
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "vllm-dlc-identity-provider-seal/v1"
TOP_LEVEL_FIELDS = {
    "schema_version", "seal_id", "provider", "subject_class", "observed_value",
    "generation", "observed_at", "expires_at", "raw_evidence_digest",
    "authoritativeness", "status", "blockers", "primary_blocker",
    "claim_boundary", "unverified_scope", "digest",
}
PROVIDER_FIELDS = {"id", "version", "identity_digest"}
GENERATION_FIELDS = {"kind", "value", "atomic"}
SUBJECT_CLASSES = {
    "source", "installed_package", "native_binary", "image", "runtime", "driver",
    "toolchain", "model", "tokenizer", "processor", "workload", "hardware",
    "capability_policy",
}
PROVIDER_SCOPES = {
    "model-adaptation/python-package-identity-provider": {"installed_package"},
}
PACKAGE_PROVIDER_ID = "model-adaptation/python-package-identity-provider"
PACKAGE_PROVIDER_VERSION = "1.0.0"
OBSERVED_VALUE_FIELDS = {
    "installed_package": {"name", "version", "path", "digest", "native_binary_digests"},
}
AUTHORITATIVENESS = {"non_authoritative", "operational", "authoritative"}
STATUSES = {"passed", "blocked", "not_verified"}
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z$"
)


def canonical(document: Mapping[str, Any]) -> bytes:
    payload = copy.deepcopy(dict(document))
    payload.pop("digest", None)
    _reject_floats(payload)
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def digest(document: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical(document)).hexdigest()


def seal(document: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(document))
    result["digest"] = digest(result)
    return result


def code_identity(contract_path: Path, provider_path: Path) -> str:
    framed = b""
    for name, path in (
        (b"identity_provider_seal.py", contract_path),
        (b"observe-python-package-identity.py", provider_path),
    ):
        content = path.read_bytes()
        framed += len(name).to_bytes(8, "big") + name
        framed += len(content).to_bytes(8, "big") + content
    return "sha256:" + hashlib.sha256(framed).hexdigest()


def expected_provider_identity(provider_id: str, provider_version: str) -> str | None:
    if (provider_id, provider_version) != (
        PACKAGE_PROVIDER_ID,
        PACKAGE_PROVIDER_VERSION,
    ):
        return None
    return code_identity(
        Path(__file__), Path(__file__).with_name("observe-python-package-identity.py")
    )


def validate(
    document: Any, trusted_provider_identities: Mapping[str, str] | None = None
) -> list[dict[str, str]]:
    if not isinstance(document, Mapping):
        return [_error("invalid_type", "$")]
    errors: list[dict[str, str]] = []
    for field in sorted(set(document) - TOP_LEVEL_FIELDS):
        errors.append(_error("unknown_field", f"$.{field}"))
    for field in sorted(TOP_LEVEL_FIELDS - set(document)):
        errors.append(_error("missing_required_field", f"$.{field}"))
    if document.get("schema_version") != SCHEMA_VERSION:
        errors.append(_error("unsupported_schema_version", "$.schema_version"))

    provider = document.get("provider")
    if not isinstance(provider, Mapping):
        errors.append(_error("invalid_type", "$.provider"))
    else:
        errors.extend(_shape_errors(provider, PROVIDER_FIELDS, "$.provider"))
        if provider.get("id") not in PROVIDER_SCOPES:
            errors.append(_error("unknown_provider", "$.provider.id"))
        if not isinstance(provider.get("version"), str) or not VERSION.fullmatch(provider["version"]):
            errors.append(_error("invalid_value", "$.provider.version"))
        if not _valid_digest(provider.get("identity_digest")):
            errors.append(_error("invalid_value", "$.provider.identity_digest"))
        expected_identity = expected_provider_identity(
            provider.get("id"), provider.get("version")
        )
        if expected_identity is None:
            errors.append(_error("unsupported_provider_version", "$.provider.version"))
        elif provider.get("identity_digest") != expected_identity:
            errors.append(_error("provider_identity_mismatch", "$.provider.identity_digest"))

    subject = document.get("subject_class")
    if subject not in SUBJECT_CLASSES:
        errors.append(_error("invalid_value", "$.subject_class"))
    if isinstance(provider, Mapping) and provider.get("id") in PROVIDER_SCOPES:
        if subject not in PROVIDER_SCOPES[provider["id"]]:
            errors.append(_error("provider_scope_mismatch", "$.subject_class"))

    generation = document.get("generation")
    if not isinstance(generation, Mapping):
        errors.append(_error("invalid_type", "$.generation"))
    else:
        errors.extend(_shape_errors(generation, GENERATION_FIELDS, "$.generation"))
        if generation.get("kind") not in {"transaction_id", "immutable_generation", "content_snapshot"}:
            errors.append(_error("invalid_value", "$.generation.kind"))
        if not _nonempty(generation.get("value")):
            errors.append(_error("invalid_value", "$.generation.value"))
        if not isinstance(generation.get("atomic"), bool):
            errors.append(_error("invalid_type", "$.generation.atomic"))
        if generation.get("kind") == "content_snapshot" and generation.get("atomic") is not False:
            errors.append(_error("content_snapshot_not_atomic", "$.generation.atomic"))

    authority = document.get("authoritativeness")
    status = document.get("status")
    if authority not in AUTHORITATIVENESS:
        errors.append(_error("invalid_value", "$.authoritativeness"))
    if status not in STATUSES:
        errors.append(_error("invalid_value", "$.status"))
    if authority == "authoritative" and isinstance(generation, Mapping) and generation.get("atomic") is not True:
        errors.append(_error("authoritative_generation_not_atomic", "$.generation.atomic"))
    if authority == "authoritative" and isinstance(provider, Mapping):
        trust_key = f"{provider.get('id')}@{provider.get('version')}"
        trusted_digest = (trusted_provider_identities or {}).get(trust_key)
        if trusted_digest != provider.get("identity_digest"):
            errors.append(_error("untrusted_provider_identity", "$.provider.identity_digest"))
        errors.append(
            _error(
                "authenticated_provider_seal_unavailable",
                "$.authoritativeness",
            )
        )
    if status == "passed" and authority != "authoritative":
        errors.append(_error("passed_requires_authoritative_provider", "$.authoritativeness"))
    if authority == "authoritative" and status != "passed":
        errors.append(_error("authoritative_provider_must_pass", "$.status"))

    for field in ("observed_at", "expires_at"):
        if not _valid_timestamp(document.get(field)):
            errors.append(_error("invalid_value", f"$.{field}"))
    if _valid_timestamp(document.get("observed_at")) and _valid_timestamp(document.get("expires_at")):
        if _parse_time(document["expires_at"]) <= _parse_time(document["observed_at"]):
            errors.append(_error("invalid_expiry", "$.expires_at"))
    if not _valid_digest(document.get("raw_evidence_digest")):
        errors.append(_error("invalid_value", "$.raw_evidence_digest"))
    observed_value = document.get("observed_value")
    if not isinstance(observed_value, Mapping):
        errors.append(_error("invalid_type", "$.observed_value"))
    elif subject in OBSERVED_VALUE_FIELDS:
        allowed_fields = OBSERVED_VALUE_FIELDS[subject]
        for field in sorted(set(observed_value) - allowed_fields):
            errors.append(_error("unknown_field", f"$.observed_value.{field}"))
        if status != "blocked":
            for field in sorted(allowed_fields - set(observed_value)):
                errors.append(
                    _error("missing_required_field", f"$.observed_value.{field}")
                )
            errors.extend(_validate_installed_package(observed_value))
    if not _nonempty(document.get("seal_id")):
        errors.append(_error("invalid_value", "$.seal_id"))
    if not isinstance(document.get("claim_boundary"), str) or not document["claim_boundary"].startswith("Claim Boundary:"):
        errors.append(_error("invalid_value", "$.claim_boundary"))
    scope = document.get("unverified_scope")
    if not isinstance(scope, list) or not all(_nonempty(value) for value in scope) or len(scope or []) != len(set(scope or [])):
        errors.append(_error("invalid_value", "$.unverified_scope"))
    errors.extend(_validate_blockers(document))
    if not _valid_digest(document.get("digest")) or document.get("digest") != digest(document):
        errors.append(_error("digest_mismatch", "$.digest"))
    return _deduplicate(errors)


def verify(
    document: Any,
    expected_subject_class: str,
    now: str,
    trusted_provider_identities: Mapping[str, str],
    current_generation: str | None = None,
) -> Mapping[str, Any]:
    errors = validate(document, trusted_provider_identities)
    if any(
        error["code"] != "authenticated_provider_seal_unavailable"
        for error in errors
    ):
        raise ValueError("blocked_invalid_provider_seal")
    if document["subject_class"] != expected_subject_class:
        raise ValueError("blocked_wrong_provider_scope")
    if _parse_time(now) < _parse_time(document["observed_at"]):
        raise ValueError("blocked_future_provider_observation")
    if _parse_time(now) >= _parse_time(document["expires_at"]):
        raise ValueError("blocked_expired_provider_seal")
    if current_generation is None:
        raise ValueError("blocked_missing_current_provider_generation")
    if current_generation != document["generation"]["value"]:
        raise ValueError("blocked_stale_provider_generation")
    if any(
        error["code"] == "authenticated_provider_seal_unavailable"
        for error in errors
    ):
        raise ValueError("blocked_missing_authenticated_provider_seal")
    if document["status"] != "passed" or document["authoritativeness"] != "authoritative":
        raise ValueError("blocked_missing_authoritative_identity_provider")
    return document["observed_value"]


def _validate_installed_package(value: Mapping[str, Any]) -> list[dict[str, str]]:
    errors = []
    for field in ("name", "version"):
        if not _nonempty(value.get(field)):
            errors.append(_error("invalid_value", f"$.observed_value.{field}"))
    path = value.get("path")
    if not isinstance(path, str) or not path.startswith("/"):
        errors.append(_error("invalid_value", "$.observed_value.path"))
    if not _valid_digest(value.get("digest")):
        errors.append(_error("invalid_value", "$.observed_value.digest"))
    binaries = value.get("native_binary_digests")
    if not isinstance(binaries, list):
        errors.append(_error("invalid_type", "$.observed_value.native_binary_digests"))
    else:
        serialized = []
        for index, binary in enumerate(binaries):
            binary_path = f"$.observed_value.native_binary_digests[{index}]"
            if not isinstance(binary, Mapping) or set(binary) != {"path", "digest"}:
                errors.append(_error("invalid_value", binary_path))
                continue
            if not isinstance(binary["path"], str) or not binary["path"].startswith("/"):
                errors.append(_error("invalid_value", f"{binary_path}.path"))
            if not _valid_digest(binary["digest"]):
                errors.append(_error("invalid_value", f"{binary_path}.digest"))
            serialized.append(json.dumps(binary, sort_keys=True, separators=(",", ":")))
        if len(serialized) != len(set(serialized)):
            errors.append(_error("duplicate_value", "$.observed_value.native_binary_digests"))
    return errors


def _validate_blockers(document: Mapping[str, Any]) -> list[dict[str, str]]:
    errors = []
    blockers = document.get("blockers")
    if not isinstance(blockers, list) or not all(_is_blocker(item) for item in blockers):
        return [_error("invalid_blockers", "$.blockers")]
    expected_primary = min(
        blockers,
        key=lambda item: ({"blocked": 0, "not_verified": 1}[item["status"]], item["code"], item["path"]),
    ) if blockers else None
    if document.get("primary_blocker") != expected_primary:
        errors.append(_error("inconsistent_primary_blocker", "$.primary_blocker"))
    if blockers and document.get("status") != expected_primary["status"]:
        errors.append(_error("inconsistent_status", "$.status"))
    if not blockers and document.get("status") != "passed":
        errors.append(_error("inconsistent_status", "$.status"))
    return errors


def _shape_errors(value: Mapping[str, Any], expected: set[str], path: str) -> list[dict[str, str]]:
    return [
        *[_error("unknown_field", f"{path}.{field}") for field in sorted(set(value) - expected)],
        *[_error("missing_required_field", f"{path}.{field}") for field in sorted(expected - set(value))],
    ]


def _is_blocker(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == {"status", "code", "path"}
        and value["status"] in {"blocked", "not_verified"}
        and _nonempty(value["code"])
        and isinstance(value["path"], str)
        and value["path"].startswith("$")
    )


def _parse_time(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value[:-1] + "+00:00")


def _valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not TIMESTAMP.fullmatch(value):
        return False
    try:
        _parse_time(value)
    except ValueError:
        return False
    return True


def _valid_digest(value: Any) -> bool:
    return isinstance(value, str) and DIGEST.fullmatch(value) is not None


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _reject_floats(value: Any) -> None:
    if isinstance(value, float):
        raise ValueError("floating-point values are not canonical")
    if isinstance(value, Mapping):
        for nested in value.values():
            _reject_floats(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_floats(nested)


def _error(code: str, path: str) -> dict[str, str]:
    return {"code": code, "path": path}


def _deduplicate(errors: list[dict[str, str]]) -> list[dict[str, str]]:
    result = []
    seen = set()
    for error in errors:
        key = (error["code"], error["path"])
        if key not in seen:
            seen.add(key)
            result.append(error)
    return result
