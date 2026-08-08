#!/usr/bin/env python3
"""Observe installed Python package bytes without claiming atomic authority."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
from typing import Any, Callable, Iterable


CONTRACT_PATH = Path(__file__).with_name("identity_provider_seal.py")
SPEC = importlib.util.spec_from_file_location("identity_provider_seal", CONTRACT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("missing identity provider seal contract")
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)

PROVIDER_ID = CONTRACT.PACKAGE_PROVIDER_ID
PROVIDER_VERSION = CONTRACT.PACKAGE_PROVIDER_VERSION
NATIVE_SUFFIXES = {".so", ".dll", ".dylib", ".pyd"}


class ObservationError(Exception):
    def __init__(self, code: str, path: str):
        super().__init__(code)
        self.code = code
        self.path = path


def _sha256(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _frame(name: str, content: bytes) -> bytes:
    raw_name = name.encode("utf-8", errors="surrogateescape")
    return len(raw_name).to_bytes(8, "big") + raw_name + len(content).to_bytes(8, "big") + content


def _normalized(name: str) -> str:
    return name.lower().replace("-", "_").replace(".", "_")


def _distribution(name: str, search_paths: Iterable[Path]) -> importlib.metadata.Distribution:
    matches = [
        distribution
        for distribution in importlib.metadata.Distribution.discover(path=[str(path) for path in search_paths])
        if _normalized(distribution.metadata.get("Name", "")) == _normalized(name)
    ]
    if len(matches) != 1:
        raise ObservationError("blocked_package_distribution_not_unique", "$.package_name")
    return matches[0]


def provider_identity() -> str:
    return CONTRACT.code_identity(CONTRACT_PATH, Path(__file__))


def _reject_symlink_path(path: Path, roots: list[Path]) -> None:
    matching_roots = [root for root in roots if path == root or path.is_relative_to(root)]
    if len(matching_roots) != 1:
        raise ObservationError("blocked_package_binary_pairing_unresolved", "$.distribution_record")
    root = matching_roots[0]
    current = path
    while current != root:
        if current.is_symlink():
            raise ObservationError("blocked_package_binary_pairing_unresolved", "$.distribution_record")
        current = current.parent


def _snapshot(name: str, search_paths: Iterable[Path]) -> dict[str, Any]:
    roots = [path.resolve(strict=True) for path in search_paths]
    distribution = _distribution(name, roots)
    distribution_path = getattr(distribution, "_path", None)
    if not isinstance(distribution_path, Path):
        raise ObservationError("blocked_package_binary_pairing_unresolved", "$.distribution_metadata")
    dist_info = distribution_path.absolute()
    _reject_symlink_path(dist_info, roots)
    expected_metadata_paths = {dist_info / "METADATA", dist_info / "RECORD"}
    data_root = dist_info.with_name(dist_info.name.removesuffix(".dist-info") + ".data")
    observed_name = distribution.metadata.get("Name")
    version = distribution.metadata.get("Version")
    files = distribution.files
    if not observed_name or not version or files is None:
        raise ObservationError("blocked_package_binary_pairing_unresolved", "$.distribution_metadata")

    records = []
    recorded_paths: set[Path] = set()
    package_roots: set[Path] = set()
    native_digests = []
    for relative in sorted(files, key=lambda value: str(value)):
        relative_path = Path(str(relative))
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ObservationError("blocked_package_binary_pairing_unresolved", "$.distribution_record")
        first = relative_path.parts[0] if relative_path.parts else ""
        if first.endswith(".dist-info") and first != dist_info.name:
            raise ObservationError("blocked_package_binary_pairing_unresolved", "$.distribution_record")
        if first.endswith(".data") and first != data_root.name:
            raise ObservationError("blocked_package_binary_pairing_unresolved", "$.distribution_record")
        located = Path(distribution.locate_file(relative)).absolute()
        _reject_symlink_path(located, roots)
        if not located.is_file():
            raise ObservationError("blocked_package_binary_pairing_unresolved", "$.distribution_record")
        content = located.read_bytes()
        recorded_paths.add(located)
        records.append(_frame(relative_path.as_posix(), content))
        if first and not first.endswith(".dist-info") and not first.endswith(".data"):
            package_roots.add(Path(distribution.locate_file(first)).resolve(strict=True))
        if located.suffix.lower() in NATIVE_SUFFIXES:
            native_digests.append({"path": str(located), "digest": _sha256(content)})
    if not expected_metadata_paths.issubset(recorded_paths) or len(package_roots) != 1:
        raise ObservationError("blocked_package_binary_pairing_unresolved", "$.distribution_record")
    package_root = next(iter(package_roots))
    try:
        package_entries = list(package_root.rglob("*"))
        if package_root.is_symlink() or any(path.is_symlink() for path in package_entries):
            raise ObservationError(
                "blocked_package_binary_pairing_unresolved", "$.distribution_record"
            )
        actual_package_files = {path.absolute() for path in package_entries if path.is_file()}
    except (OSError, RuntimeError) as error:
        raise ObservationError(
            "blocked_package_binary_pairing_unresolved", "$.distribution_record"
        ) from error
    if any(not path.is_relative_to(package_root) for path in actual_package_files):
        raise ObservationError("blocked_package_binary_pairing_unresolved", "$.distribution_record")
    recorded_package_files = {
        path for path in recorded_paths if path.is_relative_to(package_root)
    }
    if actual_package_files != recorded_package_files:
        raise ObservationError("blocked_package_binary_pairing_unresolved", "$.distribution_record")
    try:
        dist_info_entries = list(dist_info.rglob("*"))
        if dist_info.is_symlink() or any(path.is_symlink() for path in dist_info_entries):
            raise ObservationError(
                "blocked_package_binary_pairing_unresolved", "$.distribution_record"
            )
        actual_dist_info_files = {
            path.absolute() for path in dist_info_entries if path.is_file()
        }
    except (OSError, RuntimeError) as error:
        raise ObservationError(
            "blocked_package_binary_pairing_unresolved", "$.distribution_record"
        ) from error
    recorded_dist_info_files = {
        path for path in recorded_paths if path.is_relative_to(dist_info)
    }
    if actual_dist_info_files != recorded_dist_info_files:
        raise ObservationError("blocked_package_binary_pairing_unresolved", "$.distribution_record")
    recorded_data_files = {
        path for path in recorded_paths if path.is_relative_to(data_root)
    }
    if data_root.exists() or recorded_data_files:
        try:
            data_entries = list(data_root.rglob("*"))
            if data_root.is_symlink() or any(path.is_symlink() for path in data_entries):
                raise ObservationError(
                    "blocked_package_binary_pairing_unresolved", "$.distribution_record"
                )
            actual_data_files = {
                path.absolute() for path in data_entries if path.is_file()
            }
        except (OSError, RuntimeError) as error:
            raise ObservationError(
                "blocked_package_binary_pairing_unresolved", "$.distribution_record"
            ) from error
        if actual_data_files != recorded_data_files:
            raise ObservationError(
                "blocked_package_binary_pairing_unresolved", "$.distribution_record"
            )
    raw = b"".join(records)
    package_digest = _sha256(raw)
    return {
        "observed_value": {
            "name": observed_name,
            "version": version,
            "path": str(package_root),
            "digest": package_digest,
            "native_binary_digests": native_digests,
        },
        "generation": package_digest,
        "raw_evidence_digest": _sha256(raw),
    }


def observe(
    package_name: str,
    search_paths: Iterable[Path],
    seal_id: str,
    observed_at: str,
    expires_at: str,
    between_snapshots: Callable[[], None] | None = None,
) -> dict[str, Any]:
    try:
        first = _snapshot(package_name, search_paths)
        if between_snapshots is not None:
            between_snapshots()
        second = _snapshot(package_name, search_paths)
        stable = first == second
        blocker = {
            "status": "not_verified",
            "code": "blocked_missing_atomic_package_generation" if stable else "blocked_unstable_package_identity",
            "path": "$.generation",
        }
        snapshot = second
    except (OSError, UnicodeError, importlib.metadata.PackageNotFoundError, ObservationError) as error:
        code = error.code if isinstance(error, ObservationError) else "blocked_package_identity_observation_failed"
        path = error.path if isinstance(error, ObservationError) else "$"
        blocker = {"status": "blocked", "code": code, "path": path}
        snapshot = {
            "observed_value": {},
            "generation": _sha256(b"unavailable"),
            "raw_evidence_digest": _sha256(b"unavailable"),
        }
    identity_digest = provider_identity()
    return CONTRACT.seal({
        "schema_version": CONTRACT.SCHEMA_VERSION,
        "seal_id": seal_id,
        "provider": {
            "id": PROVIDER_ID,
            "version": PROVIDER_VERSION,
            "identity_digest": identity_digest,
        },
        "subject_class": "installed_package",
        "observed_value": snapshot["observed_value"],
        "generation": {
            "kind": "content_snapshot",
            "value": snapshot["generation"],
            "atomic": False,
        },
        "observed_at": observed_at,
        "expires_at": expires_at,
        "raw_evidence_digest": snapshot["raw_evidence_digest"],
        "authoritativeness": "operational" if blocker["status"] == "not_verified" else "non_authoritative",
        "status": blocker["status"],
        "blockers": [blocker],
        "primary_blocker": blocker,
        "claim_boundary": "Claim Boundary: installed Python distribution metadata and recorded files were byte-bound; the installation database supplied no atomic generation, so authoritative package identity was not established.",
        "unverified_scope": [
            "atomic_package_generation", "source", "image", "runtime", "driver",
            "toolchain", "model", "tokenizer", "processor", "workload", "hardware",
            "capability_policy", "formal_acceptance",
        ],
    })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_name")
    parser.add_argument("output", type=Path)
    parser.add_argument("--search-path", action="append", required=True, type=Path)
    parser.add_argument("--seal-id", required=True)
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--expires-at", required=True)
    args = parser.parse_args()
    result = observe(
        args.package_name, args.search_path, args.seal_id, args.observed_at, args.expires_at
    )
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": result["status"], "reason_code": result["primary_blocker"]["code"]}, sort_keys=True))
    return 0 if result["status"] == "passed" else 20


if __name__ == "__main__":
    raise SystemExit(main())
