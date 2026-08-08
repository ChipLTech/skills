#!/usr/bin/env python3
"""Collect a read-only, byte-bound Qualification Artifact identity envelope."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Mapping


CONTRACT_PATH = Path(__file__).with_name("_generated_contracts") / "qualification_artifact.py"
SPEC = importlib.util.spec_from_file_location("live_identity_contract", CONTRACT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("missing generated qualification artifact contract")
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)
PACKAGE_PROVIDER_PATH = Path(__file__).with_name("observe-python-package-identity.py")
PACKAGE_PROVIDER_SPEC = importlib.util.spec_from_file_location(
    "live_identity_package_provider", PACKAGE_PROVIDER_PATH
)
if PACKAGE_PROVIDER_SPEC is None or PACKAGE_PROVIDER_SPEC.loader is None:
    raise RuntimeError("missing package identity provider")
PACKAGE_PROVIDER = importlib.util.module_from_spec(PACKAGE_PROVIDER_SPEC)
PACKAGE_PROVIDER_SPEC.loader.exec_module(PACKAGE_PROVIDER)

SPEC_SCHEMA = "vllm-dlc-live-identity-collector-spec/v1"
ARTIFACT_SCHEMA = "vllm-dlc-live-identity/v1"
COLLECTOR_VERSION = "1.0.0"
TOP_LEVEL_FIELDS = {
    "schema_version", "artifact_id", "created_at", "source",
    "installed_package", "native_binary", "image", "runtime", "driver",
    "toolchain", "model", "tokenizer", "processor", "workload", "hardware",
    "capability_policy",
}
FIELD_SHAPES = {
    "source": {"kind", "root"},
    "installed_package": {"name", "version", "path", "metadata_path"},
    "native_binary": {"path"},
    "image": {"image_id", "identity_path", "metadata_path"},
    "runtime": {"name", "version", "path", "metadata_path"},
    "driver": {"name", "version", "path", "metadata_path"},
    "toolchain": {"name", "version", "path", "metadata_path"},
    "model": {"model_id", "revision", "path", "metadata_path"},
    "tokenizer": {"revision", "path", "metadata_path"},
    "processor": {"revision", "path", "metadata_path"},
    "workload": {"path"},
    "hardware": {"generation", "topology_path", "metadata_path"},
    "capability_policy": {"policy_id", "version", "path", "metadata_path"},
}
PACKAGE_PROVIDER_SHAPE = {"provider_seal_path", "package_name", "search_paths"}


class CollectionError(Exception):
    def __init__(self, code: str, path: str):
        super().__init__(code)
        self.code = code
        self.path = path


def _sha256(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _frame(kind: bytes, name: bytes, payload: bytes) -> bytes:
    return b"".join(
        len(value).to_bytes(8, "big") + value for value in (kind, name, payload)
    )


def _path_digest(path_value: Any, field_path: str) -> tuple[str, str]:
    if not isinstance(path_value, str) or not path_value.startswith("/"):
        raise CollectionError("blocked_invalid_collector_path", field_path)
    path = Path(path_value)
    try:
        path.lstat()
    except OSError as error:
        raise CollectionError("blocked_missing_identity_path", field_path) from error

    try:
        resolved_root = path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise CollectionError("blocked_identity_symlink_cycle", field_path) from error
    if path.is_symlink():
        try:
            resolved_root.relative_to(path.parent.resolve())
        except ValueError as error:
            raise CollectionError("blocked_identity_symlink_escape", field_path) from error
    boundary = resolved_root if resolved_root.is_dir() else resolved_root.parent
    active: set[tuple[int, int]] = set()

    def entry_bytes(entry: Path, relative: bytes) -> bytes:
        if entry.is_symlink():
            target = os.fsencode(os.readlink(entry))
            try:
                target_content = entry.resolve(strict=True)
                target_content.relative_to(boundary)
            except (OSError, RuntimeError) as error:
                raise CollectionError("blocked_broken_identity_symlink", field_path) from error
            except ValueError as error:
                raise CollectionError("blocked_identity_symlink_escape", field_path) from error
            return _frame(b"symlink", relative, target) + digest_entry(target_content, b"@target")
        if entry.is_dir():
            return digest_entry(entry, relative)
        if entry.is_file():
            return _frame(b"file", relative, entry.read_bytes())
        raise CollectionError("blocked_unsupported_identity_path", field_path)

    def digest_entry(entry: Path, relative: bytes) -> bytes:
        if not entry.is_dir() or entry.is_symlink():
            return entry_bytes(entry, relative)
        stat = entry.stat()
        inode = (stat.st_dev, stat.st_ino)
        if inode in active:
            raise CollectionError("blocked_identity_symlink_cycle", field_path)
        active.add(inode)
        try:
            children = b"".join(
                entry_bytes(child, relative + b"/" + os.fsencode(child.name))
                for child in sorted(entry.iterdir(), key=lambda item: os.fsencode(item.name))
            )
            return _frame(b"directory", relative, children)
        finally:
            active.remove(inode)

    first = entry_bytes(path, b".")
    second = entry_bytes(path, b".")
    if first != second:
        raise CollectionError("blocked_unstable_identity_path", field_path)
    return str(path.absolute()), _sha256(first)


def _metadata(spec: Mapping[str, Any], field: str, expected: Mapping[str, str]) -> str:
    metadata_path = spec[field].get("metadata_path")
    field_path = f"$.{field}.metadata_path"
    path, digest = _path_digest(metadata_path, field_path)
    try:
        first = Path(path).read_bytes()
        second = Path(path).read_bytes()
        if first != second or _path_digest(metadata_path, field_path)[1] != digest:
            raise CollectionError("blocked_unstable_identity_path", field_path)
        document = json.loads(first.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CollectionError("blocked_invalid_identity_metadata", f"$.{field}.metadata_path") from error
    if not isinstance(document, Mapping) or dict(document) != dict(expected):
        raise CollectionError("blocked_identity_metadata_mismatch", f"$.{field}.metadata_path")
    return digest


def _combined_digest(*digests: str) -> str:
    return _sha256(
        json.dumps(list(digests), sort_keys=True, separators=(",", ":")).encode()
    )


def _git(root_value: Any) -> tuple[dict[str, Any], bytes]:
    root_path, _ = _path_digest(root_value, "$.source.root")
    root = Path(root_path).resolve()
    try:
        top = Path(subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()).resolve()
        revision = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD^{commit}"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            check=True, capture_output=True,
        ).stdout
        tree = subprocess.run(
            ["git", "-C", str(root), "ls-tree", "-r", "-z", "HEAD"],
            check=True, capture_output=True,
        ).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise CollectionError("blocked_invalid_source_repository", "$.source.root") from error
    if top != root:
        raise CollectionError("blocked_non_authoritative_repository_root", "$.source.root")
    records = [row for row in tree.split(b"\0") if row]
    if any(record.split(b"\t", 1)[0].split(b" ")[1] == b"commit" for record in records):
        raise CollectionError("blocked_source_submodule_identity", "$.source.root")
    if status:
        raise CollectionError("blocked_dirty_source_repository", "$.source.root")
    for record in records:
        metadata, raw_name = record.split(b"\t", 1)
        mode, object_type, expected_blob = metadata.split(b" ")
        if object_type == b"commit":
            raise CollectionError("blocked_source_submodule_identity", "$.source.root")
        if object_type != b"blob":
            raise CollectionError("blocked_unsupported_source_entry", "$.source.root")
        tracked = root / raw_name.decode("utf-8", errors="surrogateescape")
        if not tracked.exists() and not tracked.is_symlink():
            raise CollectionError("blocked_dirty_source_repository", "$.source.root")
        try:
            actual_blob = subprocess.run(
                ["git", "-C", str(root), "hash-object", "--no-filters", "--", str(tracked)],
                check=True, capture_output=True,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError) as error:
            raise CollectionError("blocked_dirty_source_repository", "$.source.root") from error
        expected_mode = b"120000" if tracked.is_symlink() else b"100755" if os.access(tracked, os.X_OK) else b"100644"
        if actual_blob != expected_blob or mode != expected_mode:
            raise CollectionError("blocked_dirty_source_repository", "$.source.root")
    revision_after = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD^{commit}"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if revision_after != revision:
        raise CollectionError("blocked_unstable_source_repository", "$.source.root")
    return {
        "kind": "git", "repository": str(root), "revision": revision,
        "dirty": False, "snapshot_digest": None,
    }, status


def _validate_spec(spec: Any) -> Mapping[str, Any]:
    if not isinstance(spec, Mapping):
        raise CollectionError("blocked_invalid_collector_spec", "$")
    unknown = sorted(set(spec) - TOP_LEVEL_FIELDS)
    if unknown:
        raise CollectionError("blocked_unknown_collector_field", f"$.{unknown[0]}")
    missing = [field for field in TOP_LEVEL_FIELDS if field not in spec]
    if missing:
        raise CollectionError("blocked_missing_collector_input", f"$.{sorted(missing)[0]}")
    if spec["schema_version"] != SPEC_SCHEMA:
        raise CollectionError("blocked_unsupported_collector_schema", "$.schema_version")
    for field, shape in FIELD_SHAPES.items():
        value = spec[field]
        if field == "processor" and value is None:
            continue
        if not isinstance(value, Mapping):
            raise CollectionError("blocked_invalid_collector_input", f"$.{field}")
        if field == "installed_package" and set(value) == PACKAGE_PROVIDER_SHAPE:
            search_paths = value.get("search_paths")
            if (
                not isinstance(search_paths, list)
                or not search_paths
                or not all(isinstance(path, str) and path.startswith("/") for path in search_paths)
            ):
                raise CollectionError(
                    "blocked_invalid_collector_input", "$.installed_package.search_paths"
                )
            continue
        unknown_nested = sorted(set(value) - shape)
        missing_nested = sorted(shape - set(value))
        if unknown_nested:
            raise CollectionError("blocked_unknown_collector_field", f"$.{field}.{unknown_nested[0]}")
        if missing_nested:
            raise CollectionError("blocked_missing_collector_input", f"$.{field}.{missing_nested[0]}")
    return spec


def _blocked(code: str, path: str) -> dict[str, Any]:
    precise = {"status": "blocked", "code": code, "path": path}
    identity = {field: None for field in CONTRACT.IDENTITY_FIELDS}
    missing = [
        {"status": "blocked", "code": "missing_identity", "path": f"$.subject_identity.{field}"}
        for field in CONTRACT.IDENTITY_FIELDS if field != "processor"
    ]
    blockers = [precise, *missing]
    status, primary = CONTRACT.aggregate_blockers(blockers)
    return CONTRACT.seal_envelope({
        "schema_version": ARTIFACT_SCHEMA,
        "artifact_id": "blocked-live-identity-collection",
        "producer": "model-adaptation/live-identity-collector",
        "producer_version": COLLECTOR_VERSION,
        "created_at": "1970-01-01T00:00:00Z",
        "subject_identity": identity,
        "input_artifact_digests": [],
        "evidence_class": "static_snapshot",
        "authoritativeness": "non_authoritative",
        "acceptance_eligible": False,
        "status": status,
        "blockers": blockers,
        "primary_blocker": primary,
        "resume_point": path,
        "claim_boundary": "Claim Boundary: no complete live identity was collected.",
        "unverified_scope": list(CONTRACT.IDENTITY_FIELDS),
        "collection": {"collector_spec_digest": None, "observed_paths": {}},
    })


def _package_provider_identity(
    provider_spec: Mapping[str, Any], observed_paths: dict[str, str]
) -> tuple[dict[str, Any], str]:
    seal_path, _ = _path_digest(
        provider_spec["provider_seal_path"],
        "$.installed_package.provider_seal_path",
    )
    observed_paths["installed_package_provider_seal"] = seal_path
    try:
        document = json.loads(Path(seal_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CollectionError(
            "blocked_invalid_package_provider_seal",
            "$.installed_package.provider_seal_path",
        ) from error
    if PACKAGE_PROVIDER.CONTRACT.validate(document):
        raise CollectionError(
            "blocked_invalid_package_provider_seal",
            "$.installed_package.provider_seal_path",
        )
    expected_provider_identity = PACKAGE_PROVIDER.provider_identity()
    if (
        document.get("provider", {}).get("id") != PACKAGE_PROVIDER.PROVIDER_ID
        or document.get("provider", {}).get("version") != PACKAGE_PROVIDER.PROVIDER_VERSION
        or document.get("provider", {}).get("identity_digest") != expected_provider_identity
        or document.get("subject_class") != "installed_package"
        or document.get("status") != "not_verified"
        or document.get("authoritativeness") != "operational"
        or document.get("primary_blocker", {}).get("code")
        != "blocked_missing_atomic_package_generation"
    ):
        raise CollectionError(
            "blocked_non_operational_package_provider_seal",
            "$.installed_package.provider_seal_path",
        )
    now = datetime.datetime.now(datetime.timezone.utc)
    observed_at = datetime.datetime.fromisoformat(
        document["observed_at"][:-1] + "+00:00"
    )
    expires_at = datetime.datetime.fromisoformat(
        document["expires_at"][:-1] + "+00:00"
    )
    if now < observed_at:
        raise CollectionError(
            "blocked_future_package_provider_observation",
            "$.installed_package.provider_seal_path",
        )
    if now >= expires_at:
        raise CollectionError(
            "blocked_expired_package_provider_seal",
            "$.installed_package.provider_seal_path",
        )
    current = PACKAGE_PROVIDER.observe(
        provider_spec["package_name"],
        [Path(path) for path in provider_spec["search_paths"]],
        document["seal_id"],
        document["observed_at"],
        document["expires_at"],
    )
    if current.get("digest") != document.get("digest"):
        raise CollectionError(
            "blocked_stale_package_provider_seal",
            "$.installed_package.provider_seal_path",
        )
    value = document["observed_value"]
    return {
        "name": value["name"],
        "version": value["version"],
        "path": value["path"],
        "digest": value["digest"],
    }, document["digest"]


def collect(spec_value: Any, _stability_check: bool = True) -> dict[str, Any]:
    try:
        spec = _validate_spec(spec_value)
        source_kind = spec["source"].get("kind")
        if source_kind == "git":
            source, _ = _git(spec["source"]["root"])
            evidence_class = "operational_only"
            # Path and metadata observations are live but not authoritative
            # package/image/runtime/hardware provider attestations.
            authoritativeness = "non_authoritative"
        elif source_kind == "static_snapshot":
            root, digest = _path_digest(spec["source"]["root"], "$.source.root")
            source = {"kind": "static_snapshot", "repository": None, "revision": None, "dirty": None, "snapshot_digest": digest}
            evidence_class = "static_snapshot"
            authoritativeness = "non_authoritative"
        else:
            raise CollectionError("blocked_invalid_source_kind", "$.source.kind")

        observed_paths: dict[str, str] = {}

        def observed(field: str, key: str = "path") -> str:
            path, digest = _path_digest(spec[field][key], f"$.{field}.{key}")
            observed_paths[field] = path
            return digest

        def observed_metadata(
            field: str, expected: Mapping[str, str], key: str = "path"
        ) -> str:
            payload_digest = observed(field, key)
            metadata_digest = _metadata(spec, field, expected)
            return _combined_digest(payload_digest, metadata_digest)

        provider_seal_digest = None
        if set(spec["installed_package"]) == PACKAGE_PROVIDER_SHAPE:
            installed_package, provider_seal_digest = _package_provider_identity(
                spec["installed_package"], observed_paths
            )
        else:
            installed_package = {
                "name": spec["installed_package"]["name"],
                "version": spec["installed_package"]["version"],
                "path": _path_digest(
                    spec["installed_package"]["path"], "$.installed_package.path"
                )[0],
                "digest": observed_metadata(
                    "installed_package",
                    {
                        "name": spec["installed_package"]["name"],
                        "version": spec["installed_package"]["version"],
                    },
                ),
            }

        identity = {
            "source": source,
            "installed_package": installed_package,
            "native_binary": {"digest": observed("native_binary")},
            "image": {"image_id": spec["image"]["image_id"], "digest": observed_metadata("image", {"image_id": spec["image"]["image_id"]}, "identity_path")},
            "runtime": {"name": spec["runtime"]["name"], "version": spec["runtime"]["version"], "digest": observed_metadata("runtime", {"name": spec["runtime"]["name"], "version": spec["runtime"]["version"]})},
            "driver": {"name": spec["driver"]["name"], "version": spec["driver"]["version"], "digest": observed_metadata("driver", {"name": spec["driver"]["name"], "version": spec["driver"]["version"]})},
            "toolchain": {"name": spec["toolchain"]["name"], "version": spec["toolchain"]["version"], "digest": observed_metadata("toolchain", {"name": spec["toolchain"]["name"], "version": spec["toolchain"]["version"]})},
            "model": {"model_id": spec["model"]["model_id"], "revision": spec["model"]["revision"], "digest": observed_metadata("model", {"model_id": spec["model"]["model_id"], "revision": spec["model"]["revision"]})},
            "tokenizer": {"revision": spec["tokenizer"]["revision"], "digest": observed_metadata("tokenizer", {"revision": spec["tokenizer"]["revision"]})},
            "processor": None if spec["processor"] is None else {"revision": spec["processor"]["revision"], "digest": observed_metadata("processor", {"revision": spec["processor"]["revision"]})},
            "workload": {"digest": observed("workload")},
            "hardware": {"generation": spec["hardware"]["generation"], "topology_digest": observed_metadata("hardware", {"generation": spec["hardware"]["generation"]}, "topology_path")},
            "capability_policy": {"policy_id": spec["capability_policy"]["policy_id"], "version": spec["capability_policy"]["version"], "digest": observed_metadata("capability_policy", {"policy_id": spec["capability_policy"]["policy_id"], "version": spec["capability_policy"]["version"]})},
        }
        spec_digest = _sha256(json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
        document = {
            "schema_version": ARTIFACT_SCHEMA,
            "artifact_id": spec["artifact_id"],
            "producer": "model-adaptation/live-identity-collector",
            "producer_version": COLLECTOR_VERSION,
            "created_at": spec["created_at"],
            "subject_identity": identity,
            "input_artifact_digests": [
                spec_digest,
                *([provider_seal_digest] if provider_seal_digest is not None else []),
            ],
            "evidence_class": evidence_class,
            "authoritativeness": authoritativeness,
            "acceptance_eligible": False,
            "status": "not_verified",
            "blockers": [{"status": "not_verified", "code": "blocked_non_atomic_identity_snapshot", "path": "$.subject_identity"}],
            "primary_blocker": {"status": "not_verified", "code": "blocked_non_atomic_identity_snapshot", "path": "$.subject_identity"},
            "resume_point": "authoritative_atomic_identity_provider",
            "claim_boundary": (
                "Claim Boundary: read-only live path and caller-selected metadata identities were byte-bound as non-authoritative operational-only evidence; package/image/runtime/hardware authority, runtime behavior, authorization, collective correctness, and formal acceptance were not established."
                if source_kind == "git" else
                "Claim Boundary: read-only static source and path snapshots were byte-bound; live runtime identity and acceptance were not established."
            ),
            "unverified_scope": ["authorization", "runtime_behavior", "collective_correctness", "formal_acceptance"],
            "collection": {"collector_spec_digest": spec_digest, "observed_paths": observed_paths},
        }
        if source_kind == "git":
            source_after, _ = _git(spec["source"]["root"])
            if source_after != source:
                return _blocked("blocked_unstable_source_repository", "$.source.root")
        sealed = CONTRACT.seal_envelope(document)
        errors = CONTRACT.validate_envelope(sealed, ("collection",))
        if errors:
            return _blocked("blocked_invalid_collected_identity", errors[0]["path"])
        if _stability_check:
            verification = collect(spec_value, _stability_check=False)
            if verification.get("digest") != sealed.get("digest"):
                return _blocked("blocked_unstable_identity_set", "$.subject_identity")
            return verification
        return sealed
    except CollectionError as error:
        return _blocked(error.code, error.path)
    except (OSError, TypeError, ValueError, subprocess.SubprocessError):
        return _blocked("blocked_identity_collection_failed", "$")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        result = _blocked("blocked_invalid_collector_spec", "$")
    else:
        result = collect(spec)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "reason_code": result["primary_blocker"]["code"] if result.get("primary_blocker") else "passed"}, sort_keys=True))
    return 0 if result["status"] == "passed" else 20


if __name__ == "__main__":
    raise SystemExit(main())
