#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from manifest_contract import ManifestError, contained_path, load_manifest, output


ADAPTER_COMMANDS = {
    "pd-gates": ("skills/engineering/pd-separation/scripts/evaluate-pd-gates.py", "${fixture}"),
    "plugin-migration": ("scripts/workflow-behavior/invoke-representative-owner.py", "plugin-migration", "${fixture}"),
    "report-routing": ("scripts/workflow-behavior/invoke-representative-owner.py", "report-routing", "${fixture}"),
    "delivery-summary": ("skills/engineering/technical-delivery-summary/scripts/format-delivery-summary.py", "source_only", "目标能力"),
    "topology-selection": ("scripts/workflow-behavior/invoke-representative-owner.py", "topology-selection", "${fixture}"),
    "contract-static": ("scripts/workflow-behavior/invoke-representative-owner.py", "contract-static", "${fixture}"),
    "publication-not-proposed": ("scripts/workflow-behavior/invoke-representative-owner.py", "publication-not-proposed", "${fixture}"),
    "publication-stale-lease": ("scripts/workflow-behavior/invoke-representative-owner.py", "publication-stale-lease", "${fixture}"),
    "test-fixture-owner": ("tests/workflow_behavior/fixture_owner.py", "observe", "${repo_root}"),
}
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
GIT_ENV = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_OPTIONAL_LOCKS": "0",
}


def git_environment():
    return {**{key: value for key, value in os.environ.items() if not key.startswith("GIT_")}, **GIT_ENV}


def git(repo_root, *arguments, binary=False):
    return subprocess.run(
        [
            "git",
            "--no-optional-locks",
            "-c", "core.hooksPath=/dev/null",
            "-c", "core.fsmonitor=false",
            "-c", "core.untrackedCache=false",
            "-C", str(repo_root),
            *arguments,
        ],
        capture_output=True,
        check=True,
        env=git_environment(),
        text=not binary,
        shell=False,
    ).stdout


def repository_snapshot(repo_root):
    paths = git(repo_root, "ls-files", "--cached", "--others", "--exclude-standard", "-z", binary=True)
    content = hashlib.sha256()
    for raw_path in sorted(item for item in paths.split(b"\0") if item):
        relative = raw_path.decode("utf-8", errors="surrogateescape")
        path = repo_root / relative
        content.update(raw_path + b"\0")
        if path.is_symlink():
            content.update(b"symlink\0" + os.readlink(path).encode("utf-8", errors="surrogateescape"))
        elif path.is_file():
            content.update(hashlib.sha256(path.read_bytes()).digest())
        else:
            content.update(b"missing")
    snapshot = {
        "head": git(repo_root, "rev-parse", "HEAD").strip(),
        "status": hashlib.sha256(git(repo_root, "status", "--porcelain=v1", "-z", "--untracked-files=all", binary=True)).hexdigest(),
        "tracked_diff": hashlib.sha256(git(repo_root, "diff", "--binary", binary=True)).hexdigest(),
        "index_diff": hashlib.sha256(git(repo_root, "diff", "--binary", "--cached", binary=True)).hexdigest(),
        "workspace_content": content.hexdigest(),
    }
    snapshot["snapshot_digest"] = canonical_digest(snapshot)
    return snapshot


def canonical_digest(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def source_tree_digest(repo_root):
    digest = hashlib.sha256()
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(repo_root).as_posix().encode("utf-8")
        digest.update(relative + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return "sha256:" + digest.hexdigest()


def claim_boundary_preserved(document):
    if not isinstance(document, dict):
        return False
    boundary = document.get("claim_boundary")
    if not isinstance(boundary, str) or "Claim Boundary:" not in boundary:
        return False
    normalized = boundary.lower()
    return bool(re.search(r"\bno\b.*\b(?:is|are|was|were)\s+(?:verified|established|proven)\b", normalized)) or any(
        marker in normalized
        for marker in (
            "does not establish",
            "does not prove",
            "does not authenticate",
            "does not create",
            "creates no",
            "is not executable",
            "never authoritative",
            "未声明",
            "未验证",
        )
    )


def adapter_argv(adapter, fixture, repo_root):
    relative_owner, *arguments = ADAPTER_COMMANDS[adapter]
    owner = (repo_root / relative_owner).resolve()
    if not owner.is_relative_to(repo_root) or not owner.is_file():
        raise ManifestError("adapter_owner")
    replacements = {"${fixture}": str(fixture), "${repo_root}": str(repo_root)}
    return [sys.executable, str(owner), *(replacements.get(argument, argument) for argument in arguments)]


def resolve_path(document, path):
    current = document
    for part in path[2:].split("."):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(path)
        current = current[part]
    return current


def assertion_passes(document, assertion):
    try:
        actual = resolve_path(document, assertion["path"])
    except KeyError:
        return False
    expected = assertion["value"]
    if assertion["op"] == "equals":
        return actual == expected
    if assertion["op"] == "contains":
        if isinstance(actual, str):
            return isinstance(expected, str) and expected in actual
        if isinstance(actual, list):
            return expected in actual
        return isinstance(actual, dict) and isinstance(expected, str) and expected in actual
    return isinstance(actual, str) and isinstance(expected, str) and actual.startswith(expected)


def owner_blocker(document):
    blocker = document.get("blocker") or document.get("primary_blocker")
    if isinstance(blocker, dict):
        blocker = blocker.get("code")
    state = document.get("status", document.get("terminal_state"))
    return blocker or (document.get("reason", document.get("reason_code")) if state in {"blocked", "not_verified"} else None)


def run_case(case, fixture_root, repo_root):
    fixture = contained_path(fixture_root, case["fixture"])
    try:
        argv = adapter_argv(case["adapter"], fixture, repo_root)
        before = repository_snapshot(repo_root)
        process = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        after = repository_snapshot(repo_root)
    except (ManifestError, OSError, subprocess.CalledProcessError) as error:
        return {"id": case["id"], "workflow": case["workflow"], "quality_kind": case["quality_kind"], "terminal_state": "execution_failed", "reason": str(error)}
    try:
        document = json.loads(process.stdout)
    except json.JSONDecodeError:
        document = None
    failures = []
    if process.returncode not in case["expected_exit_codes"]:
        failures.append("exit_code")
    if not isinstance(document, dict):
        failures.append("machine_json")
    else:
        failures.extend(assertion["path"] for assertion in case["assertions"] if not assertion_passes(document, assertion))
    return {
        "id": case["id"],
        "workflow": case["workflow"],
        "quality_kind": case["quality_kind"],
        "terminal_state": "assertion_failed" if failures else "passed",
        "owner_terminal_state": document.get("terminal_state", document.get("status")) if isinstance(document, dict) else None,
        "owner_reason": document.get("reason", document.get("reason_code")) if isinstance(document, dict) else None,
        "owner_dimensions": document.get("dimensions", {}) if isinstance(document, dict) else {},
        "owner_blocker": owner_blocker(document) if isinstance(document, dict) else None,
        "owner_resume_point": document.get("resume_point", document.get("resume_from")) if isinstance(document, dict) else None,
        "failures": failures,
        "observed_exit_code": process.returncode,
        "fixture_authority": case["fixture_authority"],
        "forbidden_actions": case["forbidden_actions"],
        "workspace_mutation_observed": before != after,
        "repository_before": before,
        "repository_after": after,
        "claim_boundary_preserved": claim_boundary_preserved(document),
        "authoritative": False,
        "runtime_acceptance": False,
    }


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--repo-root", required=True, type=Path)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    if repo_root != REPOSITORY_ROOT:
        print(json.dumps(output("invalid_repository_root", ["repository_root"]), sort_keys=True))
        return 3
    try:
        manifest_path = args.manifest.resolve()
        value, fixture_root = load_manifest(manifest_path)
    except ManifestError as error:
        print(json.dumps(output("invalid_manifest", [str(error)]), sort_keys=True))
        return 3
    cases = [run_case(case, fixture_root, repo_root) for case in value["cases"]]
    passed = all(case["terminal_state"] == "passed" for case in cases)
    repository = repository_snapshot(repo_root)
    print(json.dumps(output(
        "suite_passed" if passed else "suite_failed",
        run_binding={
            "manifest_digest": "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "case_ids": [case["id"] for case in value["cases"]],
            "repository_head": repository["head"],
            "repository_status_digest": repository["status"],
            "repository_snapshot_digest": repository["snapshot_digest"],
            "repository_source_digest": source_tree_digest(repo_root),
        },
        cases=cases,
    ), sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
