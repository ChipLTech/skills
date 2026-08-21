#!/usr/bin/env python3
"""Read-only assessor for a sealed vLLM-CL publication candidate handoff."""

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


HANDOFF_VERSION = "vllm-cl-publication-candidate-handoff/v1"
ASSESSMENT_VERSION = "vllm-cl-publication-candidate-assessment/v1"
GATE_VERSION = "vllm-cl-publication-gate-evidence/v1"
REBUILT_ARTIFACT_VERSION = "vllm-cl-rebuilt-artifact/v1"
AUTHORIZATION_VERSION = "vllm-cl-publication-authorization/v1"
ARTIFACT_MAP_VERSION = "vllm-cl-publication-artifact-map/v1"
CLAIM_BOUNDARY = (
    "Claim Boundary: assessment establishes only structural candidate, Git, artifact-reference, "
    "gate-freshness, and lease observations at assessment time; it does not establish trusted "
    "authorization, publication eligibility, publication approval, commit, push, rewrite, finalize, "
    "or runtime acceptance."
)
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "references" / "publication-candidate-handoff-v1.schema.json"
ARTIFACT_MAP_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "references" / "publication-artifact-map-v1.schema.json"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REF_RE = re.compile(r"^refs/(?!-)[A-Za-z0-9][A-Za-z0-9._/-]*$")
PATH_RE = re.compile(r"^(?!-)(?!/)(?!.*(?:^|/)\.\.(?:/|$))(?!.*(?:^|/)\.(?:/|$))[^\x00]+$")


def git(root: Path, *args: str, binary: bool = False):
    process = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-c", "diff.external=", "-c", "core.fsmonitor=false", "-C", str(root), "--no-optional-locks", *args],
        check=True,
        capture_output=True,
        text=not binary,
        env={"GIT_CONFIG_NOSYSTEM": "1"},
    )
    return process.stdout


def sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def document_digest(document: dict[str, Any]) -> str:
    payload = {key: value for key, value in document.items() if key != "digest"}
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def repository_snapshot(root: Path) -> dict[str, str]:
    return {
        "head": git(root, "rev-parse", "--verify", "--end-of-options", "HEAD^{commit}").strip(),
        "tree": git(root, "rev-parse", "--verify", "--end-of-options", "HEAD^{tree}").strip(),
        "status_digest": sha256(git(root, "-c", "core.quotePath=false", "status", "--porcelain=v1", "-z", "--untracked-files=all", binary=True)),
        "tracked_diff_digest": sha256(git(root, "diff", "--no-ext-diff", "--binary", "--", binary=True)),
        "index_diff_digest": sha256(git(root, "diff", "--no-ext-diff", "--binary", "--cached", "--", binary=True)),
    }


def is_clean(snapshot: dict[str, str]) -> bool:
    empty = sha256(b"")
    return all(snapshot[key] == empty for key in ("status_digest", "tracked_diff_digest", "index_diff_digest"))


def validate_sha(value: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise ValueError("unsafe Git revision")
    return value


def validate_ref(value: str) -> str:
    components = value.split("/") if isinstance(value, str) else []
    unsafe = (
        not isinstance(value, str) or value.startswith("-") or not REF_RE.fullmatch(value)
        or ".." in value or "@{" in value or "//" in value or value.endswith(("/", "."))
        or any(part.startswith(".") or part.endswith(".lock") for part in components)
        or any(character in value for character in "~^:?*[\\")
    )
    if unsafe:
        raise ValueError("unsafe Git ref")
    return value


def validate_paths(paths: list[str]) -> list[str]:
    if not paths or any(not isinstance(path, str) or path.startswith("-") or not PATH_RE.fullmatch(path) for path in paths):
        raise ValueError("unsafe Git path")
    return paths


def scoped_digest(root: Path, base: str, commit: str, paths: list[str]) -> str:
    return sha256(git(root, "diff", "--no-ext-diff", "--binary", validate_sha(base), validate_sha(commit), "--", *validate_paths(paths), binary=True))


def scoped_tree_digest(root: Path, commit: str, paths: list[str]) -> str:
    return sha256(git(root, "ls-tree", "-r", validate_sha(commit), "--", *validate_paths(paths), binary=True))


def changed_paths(root: Path, base: str, commit: str) -> set[str]:
    output = git(root, "diff", "--no-ext-diff", "--name-only", "-z", validate_sha(base), validate_sha(commit), "--", binary=True)
    return {path.decode() for path in output.split(b"\0") if path}


def merge_base(root: Path, base: str, commit: str) -> str:
    return git(root, "merge-base", "--", validate_sha(base), validate_sha(commit)).strip()


def resolve_ref(root: Path, ref: str) -> str:
    return git(root, "rev-parse", "--verify", "--end-of-options", validate_ref(ref) + "^{commit}").strip()


def path_matches(path: str, scope: str) -> bool:
    normalized = scope.rstrip("/")
    return path == normalized or path.startswith(normalized + "/")


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp lacks timezone")
    return parsed.astimezone(timezone.utc)


def check(code: str, passed: bool, path: str) -> dict[str, str]:
    return {"code": code, "status": "passed" if passed else "blocked", "path": path}


def blocked_report(code: str, path: str, *, error: str | None = None, exit_code: int = 20):
    blocker = check(code, False, path)
    report = {
        "schema_version": ASSESSMENT_VERSION, "status": "blocked", "publication_eligible": False,
        "publication_verification": "not_verified_for_publication", "authorization_status": "human_authorization_required",
        "checks": [blocker], "primary_blocker": blocker, "finalize_action": "none", "claim_boundary": CLAIM_BOUNDARY,
    }
    if error:
        report["error"] = error
    return report, exit_code


def load_artifacts(artifact_map: Path | None, artifact_dir: Path | None) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if (artifact_map is None) == (artifact_dir is None):
        raise ValueError("exactly one of --artifact-map or --artifact-dir is required")
    manifest_path = artifact_map if artifact_map else artifact_dir / "artifact-map.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema = json.loads(ARTIFACT_MAP_SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(manifest), key=lambda error: list(error.path))
    if errors or manifest.get("digest") != document_digest(manifest):
        raise ValueError("artifact map schema or digest is invalid")
    base = manifest_path.parent
    result: dict[str, dict[str, Any]] = {}
    seen_paths: set[str] = set()
    for entry in manifest["entries"]:
        artifact_id, relative = entry["artifact_id"], entry["path"]
        if artifact_id in result or relative in seen_paths:
            raise ValueError("artifact map contains duplicate artifact identity or path")
        artifact_path = (base / relative).resolve()
        if base.resolve() not in artifact_path.parents:
            raise ValueError("artifact path escapes artifact map directory")
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        if (
            artifact.get("artifact_id") != artifact_id
            or artifact.get("schema_version") != entry["schema_version"]
            or artifact.get("digest") != entry["digest"]
            or document_digest(artifact) != entry["digest"]
        ):
            raise ValueError("artifact map entry identity, schema, or digest mismatch")
        result[artifact_id] = artifact
        seen_paths.add(relative)
    return manifest, result


def resolve_artifact(ref: dict[str, str], artifacts: dict[str, dict[str, Any]], version: str) -> tuple[dict[str, Any] | None, str]:
    artifact = artifacts.get(ref["artifact_id"])
    if not isinstance(artifact, dict):
        return None, "missing"
    if document_digest(artifact) != ref["digest"] or artifact.get("digest") != ref["digest"]:
        return None, "digest"
    common = {"schema_version", "artifact_id", "authority_id", "candidate_base_sha", "candidate_commit_sha", "scope_digest", "expires_at", "digest"}
    if version == GATE_VERSION:
        required = common | {"kind", "status", "acceptance_eligible", "artifact_graph_digest", "completed_at"}
        shape_ok = set(artifact) == required and artifact.get("kind") in {"source", "contract", "build", "runtime"} and artifact.get("status") == "passed" and isinstance(artifact.get("acceptance_eligible"), bool)
    elif version == REBUILT_ARTIFACT_VERSION:
        required = common | {"artifact_graph_digest", "built_at"}
        shape_ok = set(artifact) == required
    else:
        required = common | {"producer_authority_id", "action", "authorized", "authorized_at"}
        shape_ok = set(artifact) == required and artifact.get("action") in {"commit", "publication", "rewrite"} and isinstance(artifact.get("authorized"), bool)
    identity_types_ok = (
        isinstance(artifact.get("authority_id"), str) and bool(artifact.get("authority_id"))
        and SHA_RE.fullmatch(str(artifact.get("candidate_base_sha", ""))) is not None
        and SHA_RE.fullmatch(str(artifact.get("candidate_commit_sha", ""))) is not None
        and re.fullmatch(r"sha256:[0-9a-f]{64}", str(artifact.get("scope_digest", ""))) is not None
        and re.fullmatch(r"sha256:[0-9a-f]{64}", str(artifact.get("digest", ""))) is not None
    )
    if artifact.get("schema_version") != version or artifact.get("artifact_id") != ref["artifact_id"] or not shape_ok or not identity_types_ok:
        return None, "schema"
    return artifact, "ok"


def assess(handoff: dict[str, Any], tested_root: Path, candidate_root: Path | None, remote_root: Path, artifact_map: dict[str, Any], artifacts: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], int]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(handoff), key=lambda error: list(error.path))
    if errors:
        path = "$" + "".join(f"[{part!r}]" for part in errors[0].path)
        return blocked_report("handoff.schema_invalid", path)
    if handoff["digest"] != document_digest(handoff):
        return blocked_report("handoff.digest", "$.digest")

    candidate_input = handoff["publication_candidate"]
    if candidate_input is not None:
        try:
            validate_sha(handoff["tested_revision"]["base_sha"]); validate_sha(handoff["tested_revision"]["commit_sha"])
            validate_sha(candidate_input["base_sha"]); validate_sha(candidate_input["commit_sha"])
            validate_paths(candidate_input["included_paths"]); validate_paths(candidate_input["excluded_paths"])
            validate_ref(candidate_input["remote_observation"]["target_base_ref"]); validate_ref(candidate_input["remote_observation"]["pr_tip_ref"])
        except ValueError as error:
            return blocked_report("handoff.unsafe_git_input", "$.publication_candidate", error=str(error))

        if artifact_map["candidate_base_sha"] != candidate_input["base_sha"] or artifact_map["candidate_commit_sha"] != candidate_input["commit_sha"]:
            return blocked_report("artifact_map.identity_mismatch", "$.publication_candidate")
        expected_refs = candidate_input["affected_gate_refs"] + candidate_input["rebuilt_artifact_refs"] + candidate_input["authorization_refs"]
        expected = {(ref["artifact_id"], ref["digest"]) for ref in expected_refs}
        declared = {(entry["artifact_id"], entry["digest"]) for entry in artifact_map["entries"]}
        if expected != declared or len(expected_refs) != len(expected):
            return blocked_report("artifact_map.reference_set_mismatch", "$.publication_candidate")
    elif artifact_map["entries"]:
        return blocked_report("artifact_map.unreferenced_artifact", "$.publication_candidate")

    checks: list[dict[str, str]] = []
    def record(code: str, passed: bool, path: str) -> bool:
        checks.append(check(code, passed, path)); return passed

    record("handoff.digest", True, "$.digest")
    producer = handoff["producer"]
    record("handoff.producer_boundary", producer["produces_handoff_only"] and not producer["self_approval"], "$.producer")
    now = datetime.now(timezone.utc)
    generated, expires = parse_time(handoff["generated_at"]), parse_time(handoff["expires_at"])
    record("handoff.future_generated", generated <= now, "$.generated_at")
    record("handoff.freshness", generated <= now <= expires, "$.expires_at")

    roots = {"tested": tested_root, "remote": remote_root}
    if candidate_root is not None: roots["candidate"] = candidate_root
    before = {name: repository_snapshot(root) for name, root in roots.items()}
    tested, tested_snapshot = handoff["tested_revision"], before["tested"]
    record("tested.head_mismatch", tested["commit_sha"] == tested_snapshot["head"], "$.tested_revision.commit_sha")
    try: actual_tested_base = merge_base(tested_root, tested["base_sha"], tested["commit_sha"])
    except (subprocess.CalledProcessError, ValueError): actual_tested_base = ""
    record("tested.base_mismatch", tested["base_sha"] == actual_tested_base, "$.tested_revision.base_sha")
    record("tested.tree_mismatch", tested["tree_sha"] == tested_snapshot["tree"], "$.tested_revision.tree_sha")
    record("tested.cleanliness_mismatch", tested["worktree_clean"] == is_clean(tested_snapshot), "$.tested_revision.worktree_clean")

    proposed, candidate = handoff["publication_proposed"], handoff["publication_candidate"]
    if not proposed:
        record("candidate.not_proposed", candidate is None and candidate_root is None, "$.publication_candidate")
    else:
        snapshot = before.get("candidate")
        record("candidate.missing", snapshot is not None, "$.publication_candidate")
        if snapshot is not None:
            base, commit = candidate["base_sha"], candidate["commit_sha"]
            included, excluded = candidate["included_paths"], candidate["excluded_paths"]
            record("candidate.dirty", candidate["worktree_clean"] and is_clean(snapshot), "$.publication_candidate.worktree_clean")
            record("candidate.head_mismatch", commit == snapshot["head"], "$.publication_candidate.commit_sha")
            try: actual_base = merge_base(candidate_root, base, commit)
            except (subprocess.CalledProcessError, ValueError): actual_base = ""
            record("candidate.base_mismatch", actual_base == base, "$.publication_candidate.base_sha")
            record("candidate.tree_mismatch", candidate["tree_sha"] == snapshot["tree"], "$.publication_candidate.tree_sha")
            overlap = any(path_matches(left, right) or path_matches(right, left) for left in included for right in excluded)
            record("scope.include_exclude_overlap", not overlap, "$.publication_candidate.included_paths")
            try:
                actual_diff, actual_tree = scoped_digest(candidate_root, base, commit, included), scoped_tree_digest(candidate_root, commit, included)
                paths = changed_paths(candidate_root, base, commit)
            except (subprocess.CalledProcessError, ValueError): actual_diff, actual_tree, paths = "", "", set()
            record("scope.diff_digest_mismatch", candidate["scoped_diff_digest"] == actual_diff, "$.publication_candidate.scoped_diff_digest")
            record("scope.tree_digest_mismatch", candidate["scoped_tree_digest"] == actual_tree, "$.publication_candidate.scoped_tree_digest")
            outside = any(not any(path_matches(path, scope) for scope in included) or any(path_matches(path, scope) for scope in excluded) for path in paths)
            record("scope.excluded_path_changed", not outside, "$.publication_candidate.excluded_paths")
            try: tested_diff = scoped_digest(tested_root, tested["base_sha"], tested["commit_sha"], included)
            except (subprocess.CalledProcessError, ValueError): tested_diff = ""
            equivalence = candidate["patch_equivalence"]
            record("equivalence.tested_diff_mismatch", equivalence["tested_scoped_diff_digest"] == tested_diff, "$.publication_candidate.patch_equivalence.tested_scoped_diff_digest")
            record("equivalence.candidate_diff_mismatch", equivalence["candidate_scoped_diff_digest"] == actual_diff, "$.publication_candidate.patch_equivalence.candidate_scoped_diff_digest")
            record("equivalence.net_diff_mismatch", tested_diff == actual_diff, "$.publication_candidate.patch_equivalence")

            created = parse_time(candidate["created_at"])
            record("candidate.future_created", created <= now, "$.publication_candidate.created_at")
            gates = []
            for index, ref in enumerate(candidate["affected_gate_refs"]):
                gate, reason = resolve_artifact(ref, artifacts, GATE_VERSION)
                record(f"gate.artifact_{reason}", gate is not None, f"$.publication_candidate.affected_gate_refs[{index}]")
                if gate is not None: gates.append(gate)
            scope_binding = sha256(json.dumps({"included_paths": included, "excluded_paths": excluded, "scoped_diff_digest": actual_diff, "scoped_tree_digest": actual_tree}, sort_keys=True, separators=(",", ":")).encode())
            for gate in gates:
                record("gate.identity_mismatch", gate.get("candidate_base_sha") == base and gate.get("candidate_commit_sha") == commit and gate.get("artifact_graph_digest") == candidate["artifact_graph_digest"] and gate.get("scope_digest") == scope_binding, "$.publication_candidate.affected_gate_refs")
                record("gate.authority_missing", isinstance(gate.get("authority_id"), str) and gate.get("authority_id") != producer["authority_id"], "$.publication_candidate.affected_gate_refs")
                record("gate.acceptance_ineligible", gate.get("status") == "passed" and gate.get("acceptance_eligible") is True, "$.publication_candidate.affected_gate_refs")
                completed, gate_expiry = parse_time(gate["completed_at"]), parse_time(gate["expires_at"])
                record("gate.future_completed", completed <= now, "$.publication_candidate.affected_gate_refs")
                record("gate.stale", created <= completed <= now <= gate_expiry, "$.publication_candidate.affected_gate_refs")
            rebuilt = []
            for index, ref in enumerate(candidate["rebuilt_artifact_refs"]):
                artifact, reason = resolve_artifact(ref, artifacts, REBUILT_ARTIFACT_VERSION)
                record(f"rebuilt_artifact.artifact_{reason}", artifact is not None, f"$.publication_candidate.rebuilt_artifact_refs[{index}]")
                if artifact is not None: rebuilt.append(artifact)
            for artifact in rebuilt:
                record("rebuilt_artifact.identity_mismatch", artifact.get("candidate_base_sha") == base and artifact.get("candidate_commit_sha") == commit and artifact.get("artifact_graph_digest") == candidate["artifact_graph_digest"] and artifact.get("scope_digest") == scope_binding, "$.publication_candidate.rebuilt_artifact_refs")
                built, artifact_expiry = parse_time(artifact["built_at"]), parse_time(artifact["expires_at"])
                record("rebuilt_artifact.stale", created <= built <= now <= artifact_expiry, "$.publication_candidate.rebuilt_artifact_refs")
            kinds = {gate.get("kind") for gate in gates}
            record("gate.missing_source_rerun", "source" in kinds, "$.publication_candidate.affected_gate_refs")
            record("gate.missing_build_rerun", bool(rebuilt) and "build" in kinds, "$.publication_candidate.affected_gate_refs")
            record("gate.missing_runtime_rerun", "runtime" in kinds, "$.publication_candidate.affected_gate_refs")
            try:
                newest = max(parse_time(row["built_at"]) for row in rebuilt)
                build_fresh = any(gate.get("kind") == "build" and parse_time(gate["completed_at"]) >= newest for gate in gates)
                runtime_fresh = any(gate.get("kind") == "runtime" and parse_time(gate["completed_at"]) >= newest for gate in gates)
            except (ValueError, KeyError):
                build_fresh = runtime_fresh = False
            record("gate.build_predates_rebuilt_artifact", build_fresh, "$.publication_candidate.affected_gate_refs")
            record("gate.runtime_predates_rebuilt_artifact", runtime_fresh, "$.publication_candidate.affected_gate_refs")

            observation, lease = candidate["remote_observation"], candidate["lease"]
            observed = parse_time(observation["observed_at"])
            record("remote.future_observation", observed <= now, "$.publication_candidate.remote_observation.observed_at")
            record("remote.observation_stale", generated <= observed <= now and observed <= expires, "$.publication_candidate.remote_observation.observed_at")
            try: remote_base, remote_tip = resolve_ref(remote_root, observation["target_base_ref"]), resolve_ref(remote_root, observation["pr_tip_ref"])
            except (subprocess.CalledProcessError, ValueError): remote_base = remote_tip = ""
            record("remote.target_base_moved", observation["target_base_sha"] == remote_base, "$.publication_candidate.remote_observation.target_base_sha")
            record("remote.pr_tip_moved", observation["pr_tip_sha"] == remote_tip, "$.publication_candidate.remote_observation.pr_tip_sha")
            record("remote.candidate_base_mismatch", base == remote_base, "$.publication_candidate.base_sha")
            record("lease.target_base_mismatch", lease["target_base_expected_old_sha"] == remote_base, "$.publication_candidate.lease.target_base_expected_old_sha")
            record("lease.pr_tip_mismatch", lease["pr_tip_expected_old_sha"] == remote_tip, "$.publication_candidate.lease.pr_tip_expected_old_sha")

            for index, ref in enumerate(candidate["authorization_refs"]):
                authorization, reason = resolve_artifact(ref, artifacts, AUTHORIZATION_VERSION)
                record(f"authorization.artifact_{reason}", authorization is not None, f"$.publication_candidate.authorization_refs[{index}]")
                if authorization is None: continue
                identity = authorization.get("candidate_base_sha") == base and authorization.get("candidate_commit_sha") == commit and authorization.get("scope_digest") == scope_binding
                valid_time = parse_time(authorization["authorized_at"]) <= now <= parse_time(authorization["expires_at"])
                record("authorization.binding_mismatch", identity, "$.publication_candidate.authorization_refs")
                record("authorization.expired_or_future", valid_time, "$.publication_candidate.authorization_refs")

    after = {name: repository_snapshot(root) for name, root in roots.items()}
    if before != after: checks.append(check("assessor.repository_modified", False, "$.repository_after"))
    blockers = [row for row in checks if row["status"] == "blocked"]
    report = {
        "schema_version": ASSESSMENT_VERSION, "status": "assessment_complete" if proposed and not blockers else ("not_proposed" if not proposed and not blockers else "blocked"),
        "publication_verification": "not_verified_for_publication", "publication_eligible": False,
        "authorization_status": "human_authorization_required", "checks": checks, "primary_blocker": blockers[0] if blockers else None,
        "handoff_digest": handoff["digest"], "finalize_action": "none", "claim_boundary": CLAIM_BOUNDARY,
        "repository_before": before, "repository_after": after,
    }
    return report, 0 if not blockers else 20


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--handoff", required=True, type=Path)
    parser.add_argument("--tested-root", required=True, type=Path)
    parser.add_argument("--candidate-root", type=Path)
    parser.add_argument("--remote-root", required=True, type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--artifact-map", type=Path)
    group.add_argument("--artifact-dir", type=Path)
    args = parser.parse_args()
    try:
        handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        errors = sorted(Draft202012Validator(schema).iter_errors(handoff), key=lambda error: list(error.path))
        if errors:
            path = "$" + "".join(f"[{part!r}]" for part in errors[0].path)
            report, exit_code = blocked_report("handoff.schema_invalid", path)
        else:
            artifact_map, artifacts = load_artifacts(args.artifact_map, args.artifact_dir)
            report, exit_code = assess(handoff, args.tested_root, args.candidate_root, args.remote_root, artifact_map, artifacts)
    except Exception as error:
        report, exit_code = blocked_report("assessment.invalid_input", "$", error=str(error), exit_code=30)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
