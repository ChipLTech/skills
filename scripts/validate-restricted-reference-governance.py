#!/usr/bin/env python3
"""Validate restricted-reference governance against actual publication surfaces."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Iterable


SCHEMA_VERSION = "restricted-reference-governance/v1"
REVIEW_TERMS = ("torch_npu", "msprof", "npugraph_ex", "PA_NZ", "AIC", "AIV")
SCANNED_ROLES = {
    "agent_instruction",
    "bundled_reference",
    "executable_script",
    "schema",
    "skill_instruction",
    "template",
}
NON_EXECUTION_ROLES = {
    "catalog_metadata",
    "governance_record",
    "installation_metadata",
    "investigation_record",
    "negative_fixture",
}
TOP_KEYS = {"schema_version", "legal_review", "raci", "source_register", "review_allowlist"}
LEGAL_KEYS = {"status", "owner", "review_date", "decision_reference", "boundary"}
RACI_KEYS = {
    "accountable",
    "legal_reviewer",
    "restricted_reference_reviewer",
    "independent_specification_author",
    "implementation_author",
    "publication_reviewer",
    "separation_rule",
}
SOURCE_KEYS = {
    "id",
    "source_locator",
    "source_revision_or_sha256",
    "license_metadata",
    "classification",
    "permitted_use",
    "prohibited_use",
    "reviewer",
    "review_date",
    "disposition",
    "restricted_matches",
}
ALLOWLIST_KEYS = {"path", "match", "reason", "owner", "review_date"}
CLASSIFICATIONS = {"chipltech_owned", "public_permissive", "external_restricted", "unknown"}
DISPOSITIONS = {"approved", "review_only", "prohibited", "blocked_legal_boundary"}
LEGAL_STATUSES = {"approved", "approved_governance_only", "pending", "rejected", "not_required"}


class GovernanceError(ValueError):
    pass


def sha256_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def require_exact_keys(value: dict, expected: set[str], location: str) -> None:
    if set(value) != expected:
        raise GovernanceError(
            f"{location} keys must be {sorted(expected)}; got {sorted(value)}"
        )


def require_text(value: object, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GovernanceError(f"{location} must be a non-empty string")
    return value


def validate_date(value: object, location: str) -> None:
    text = require_text(value, location)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise GovernanceError(f"{location} must be an ISO date")


def validate_relative_path(value: object, location: str) -> str:
    text = require_text(value, location)
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts or text != path.as_posix():
        raise GovernanceError(f"{location} must be a normalized relative path")
    if any(character in text for character in "*?[]{}"):
        raise GovernanceError(f"{location} must not contain glob syntax")
    return text


def validate_governance(document: object) -> dict:
    if not isinstance(document, dict):
        raise GovernanceError("governance document must be an object")
    require_exact_keys(document, TOP_KEYS, "governance")
    if document["schema_version"] != SCHEMA_VERSION:
        raise GovernanceError(f"schema_version must be {SCHEMA_VERSION}")

    legal = document["legal_review"]
    if not isinstance(legal, dict):
        raise GovernanceError("legal_review must be an object")
    require_exact_keys(legal, LEGAL_KEYS, "legal_review")
    if legal["status"] not in LEGAL_STATUSES:
        raise GovernanceError("legal_review.status is invalid")
    require_text(legal["owner"], "legal_review.owner")
    validate_date(legal["review_date"], "legal_review.review_date")
    require_text(legal["decision_reference"], "legal_review.decision_reference")
    require_text(legal["boundary"], "legal_review.boundary")

    raci = document["raci"]
    if not isinstance(raci, dict):
        raise GovernanceError("raci must be an object")
    require_exact_keys(raci, RACI_KEYS, "raci")
    for key, value in raci.items():
        require_text(value, f"raci.{key}")

    sources = document["source_register"]
    if not isinstance(sources, list):
        raise GovernanceError("source_register must be an array")
    source_ids: set[str] = set()
    for index, source in enumerate(sources):
        location = f"source_register[{index}]"
        if not isinstance(source, dict):
            raise GovernanceError(f"{location} must be an object")
        require_exact_keys(source, SOURCE_KEYS, location)
        source_id = require_text(source["id"], f"{location}.id")
        if source_id in source_ids:
            raise GovernanceError(f"duplicate source id: {source_id}")
        source_ids.add(source_id)
        for key in (
            "source_locator",
            "source_revision_or_sha256",
            "license_metadata",
            "permitted_use",
            "prohibited_use",
            "reviewer",
        ):
            require_text(source[key], f"{location}.{key}")
        identity = source["source_revision_or_sha256"]
        if identity.startswith("sha256:") and not re.fullmatch(r"sha256:[0-9a-f]{64}", identity):
            raise GovernanceError(f"{location}.source_revision_or_sha256 has an invalid SHA-256")
        validate_date(source["review_date"], f"{location}.review_date")
        if source["classification"] not in CLASSIFICATIONS:
            raise GovernanceError(f"{location}.classification is invalid")
        if source["disposition"] not in DISPOSITIONS:
            raise GovernanceError(f"{location}.disposition is invalid")
        matches = source["restricted_matches"]
        if not isinstance(matches, list) or not matches:
            raise GovernanceError(f"{location}.restricted_matches must be non-empty")
        if len(matches) != len(set(matches)):
            raise GovernanceError(f"{location}.restricted_matches contains duplicates")
        for match in matches:
            require_text(match, f"{location}.restricted_matches")

    allowlist = document["review_allowlist"]
    if not isinstance(allowlist, list):
        raise GovernanceError("review_allowlist must be an array")
    identities: set[tuple[str, str]] = set()
    for index, item in enumerate(allowlist):
        location = f"review_allowlist[{index}]"
        if not isinstance(item, dict):
            raise GovernanceError(f"{location} must be an object")
        require_exact_keys(item, ALLOWLIST_KEYS, location)
        path = validate_relative_path(item["path"], f"{location}.path")
        match = require_text(item["match"], f"{location}.match")
        require_text(item["reason"], f"{location}.reason")
        require_text(item["owner"], f"{location}.owner")
        validate_date(item["review_date"], f"{location}.review_date")
        if (path, match) in identities:
            raise GovernanceError(f"duplicate allowlist entry: {path} / {match}")
        identities.add((path, match))
    return document


def classify(path: str) -> str:
    relative = PurePosixPath(path)
    name = relative.name.lower()
    parts = set(relative.parts)
    if relative.name == ".kilo-link-source":
        return "installation_metadata"
    if relative.name == "SKILL.md":
        return "skill_instruction"
    if "agents" in parts and relative.suffix.lower() in {".yaml", ".yml", ".md"}:
        return "agent_instruction"
    if "scripts" in parts or relative.suffix.lower() in {".py", ".sh", ".bash"}:
        return "executable_script"
    if name.endswith(".schema.json") or "schemas" in parts:
        return "schema"
    if "templates" in parts or "prompts" in parts or "prompt-examples" in parts:
        return "template"
    if "references" in parts or name == "knowledge.md":
        return "bundled_reference"
    return "bundled_reference"


def safe_files(root: Path, selected: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    resolved_root = root.resolve()
    for selected_path in selected:
        if selected_path.is_symlink():
            raise GovernanceError(f"symlink package member is not allowed: {selected_path}")
        candidates = [selected_path] if selected_path.is_file() else selected_path.rglob("*")
        for path in candidates:
            if path.name == "__pycache__" or "__pycache__" in path.parts:
                continue
            if path.suffix in {".pyc", ".pyo"}:
                continue
            if path.is_symlink():
                raise GovernanceError(f"symlink package member is not allowed: {path}")
            if not path.is_file():
                continue
            try:
                path.resolve().relative_to(resolved_root)
            except ValueError as error:
                raise GovernanceError(f"package member escapes root: {path}") from error
            files.append(path)
    return sorted(set(files), key=lambda item: item.as_posix())


def entry(channel: str, package: str, source_path: str, destination_path: str, content: bytes) -> dict:
    return {
        "channel": channel,
        "package": package,
        "source_path": source_path,
        "destination_path": destination_path,
        "role": classify(destination_path),
        "sha256": sha256_bytes(content),
    }


def skill_roots(root: Path, buckets: Iterable[str]) -> list[Path]:
    roots = []
    for bucket in buckets:
        roots.extend(path.parent for path in (root / "skills" / bucket).glob("*/SKILL.md"))
    return sorted(roots, key=lambda item: item.as_posix())


def add_skill_tree(entries: list[dict], root: Path, channel: str, skill_root: Path) -> None:
    package = skill_root.name
    for path in safe_files(skill_root, [skill_root]):
        member = path.relative_to(skill_root).as_posix()
        entries.append(
            entry(
                channel,
                package,
                path.relative_to(root).as_posix(),
                f"skills/{package}/{member}",
                path.read_bytes(),
            )
        )


def parse_skillhub(path: Path) -> list[dict]:
    rows: list[dict] = []
    current: dict | None = None
    in_files = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("- name:"):
            if current:
                rows.append(current)
            current = {"name": stripped.split(":", 1)[1].strip().strip('"\''), "files": []}
            in_files = False
        elif current is not None and stripped.startswith("path:"):
            current["path"] = stripped.split(":", 1)[1].strip().strip('"\'')
        elif current is not None and stripped == "files:":
            in_files = True
        elif current is not None and in_files and stripped.startswith("- "):
            current["files"].append(stripped[2:].strip().strip('"\''))
    if current:
        rows.append(current)
    for row in rows:
        if "path" not in row or not row["files"]:
            raise GovernanceError(f"invalid SkillHub entry: {row.get('name', '<unknown>')}")
    return rows


def build_manifest(root: Path) -> list[dict]:
    root = root.resolve()
    entries: list[dict] = []

    default_roots = skill_roots(root, ("engineering", "productivity", "misc"))
    for channel in ("kilo_global_default", "kilo_project_default"):
        for package_root in default_roots:
            add_skill_tree(entries, root, channel, package_root)

    with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
        project = Path(directory)
        result = subprocess.run(
            [str(root / "scripts" / "link-kilo-skills.sh"), "--project", str(project), "--with-commands"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise GovernanceError(f"Kilo manifest install failed: {result.stderr}{result.stdout}")
        installed_root = project / ".kilo"
        actual = safe_files(installed_root, [installed_root])
        expected_destinations = {
            item["destination_path"]
            for item in entries
            if item["channel"] == "kilo_project_default"
        }
        actual_copied_destinations = {
            path.relative_to(installed_root).as_posix()
            for path in actual
            if not path.relative_to(installed_root).as_posix().startswith("command/")
            and not path.relative_to(installed_root).as_posix().endswith("/.kilo-link-source")
        }
        if actual_copied_destinations != expected_destinations:
            missing = sorted(expected_destinations - actual_copied_destinations)
            extra = sorted(actual_copied_destinations - expected_destinations)
            raise GovernanceError(f"Kilo project manifest mismatch; missing={missing}, extra={extra}")
        for path in actual:
            relative = path.relative_to(installed_root).as_posix()
            if relative.startswith("command/"):
                package = Path(relative).stem
                item = entry(
                    "kilo_project_default",
                    package,
                    "scripts/link-kilo-skills.sh#generated-command-wrapper",
                    relative,
                    path.read_bytes(),
                )
                item["role"] = "template"
                entries.append(item)
            elif relative.endswith("/.kilo-link-source"):
                package = PurePosixPath(relative).parts[1]
                item = entry(
                    "kilo_project_default", package, "scripts/link-kilo-skills.sh", relative, path.read_bytes()
                )
                item["role"] = "installation_metadata"
                entries.append(item)
            elif relative not in expected_destinations:
                raise GovernanceError(f"unclassified Kilo project install member: {relative}")

    all_non_deprecated = []
    for bucket in sorted(path for path in (root / "skills").iterdir() if path.is_dir() and path.name != "deprecated"):
        all_non_deprecated.extend(path.parent for path in bucket.glob("*/SKILL.md"))
    for package_root in sorted(all_non_deprecated, key=lambda item: item.as_posix()):
        add_skill_tree(entries, root, "claude_agent_linker", package_root)

    plugin = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    if set(plugin) != {"name", "skills"} or not isinstance(plugin["skills"], list):
        raise GovernanceError("plugin.json has an unsupported shape")
    for value in plugin["skills"]:
        relative = validate_relative_path(value.removeprefix("./"), "plugin skill path")
        package_root = root / relative
        if not (package_root / "SKILL.md").is_file():
            raise GovernanceError(f"plugin skill does not exist: {relative}")
        add_skill_tree(entries, root, "plugin", package_root)

    for row in parse_skillhub(root / "SKILLHUB.yaml"):
        package_root = root / validate_relative_path(row["path"], "SkillHub path")
        selected = []
        for member in row["files"]:
            member_path = package_root / validate_relative_path(member.rstrip("/"), "SkillHub member")
            if not member_path.exists():
                raise GovernanceError(f"SkillHub member does not exist: {member_path}")
            selected.append(member_path)
        for path in safe_files(package_root, selected):
            member = path.relative_to(package_root).as_posix()
            entries.append(
                entry(
                    "skillhub",
                    row["name"],
                    path.relative_to(root).as_posix(),
                    f"skills/{row['name']}/{member}",
                    path.read_bytes(),
                )
            )

    entries.sort(
        key=lambda item: (
            item["channel"],
            item["destination_path"],
            item["package"],
            item["source_path"],
        )
    )
    identities = [(item["channel"], item["destination_path"]) for item in entries]
    if len(identities) != len(set(identities)):
        raise GovernanceError("manifest contains duplicate channel destination paths")
    return entries


def legal_blockers(governance: dict) -> list[dict]:
    blockers = []
    if governance["legal_review"]["status"] in {"pending", "rejected"}:
        blockers.append({"kind": "legal_review", "id": "repository-governance"})
    for source in governance["source_register"]:
        if source["classification"] == "unknown" or source["disposition"] == "blocked_legal_boundary":
            blockers.append({"kind": "source", "id": source["id"]})
    return sorted(blockers, key=lambda item: (item["kind"], item["id"]))


def scan_entries(entries: list[dict], governance: dict, contents: dict[str, bytes]) -> list[dict]:
    allowed = {(item["path"], item["match"]) for item in governance["review_allowlist"]}
    restricted = []
    restricted_digests = []
    for source in governance["source_register"]:
        if source["classification"] == "external_restricted" and source["disposition"] in {
            "prohibited",
            "blocked_legal_boundary",
        }:
            restricted.extend((source["id"], match) for match in source["restricted_matches"])
            if source["source_revision_or_sha256"].startswith("sha256:"):
                restricted_digests.append((source["id"], source["source_revision_or_sha256"]))

    findings = []
    for item in entries:
        if item["role"] not in SCANNED_ROLES:
            continue
        content = contents.get(f"{item['channel']}:{item['destination_path']}")
        if content is None:
            content = contents.get(item["source_path"])
        if content is None:
            continue
        text = content.decode("utf-8", errors="replace")
        digest = sha256_bytes(content)
        for source_id, restricted_digest in restricted_digests:
            if digest == restricted_digest and (item["destination_path"], restricted_digest) not in allowed:
                findings.append(
                    {
                        "channel": item["channel"],
                        "kind": "prohibited_import",
                        "path": item["destination_path"],
                        "match": restricted_digest,
                        "role": item["role"],
                        "source_id": source_id,
                    }
                )
        for source_id, match in restricted:
            if match in text and (item["destination_path"], match) not in allowed:
                findings.append(
                    {
                        "channel": item["channel"],
                        "kind": "prohibited_import",
                        "path": item["destination_path"],
                        "match": match,
                        "role": item["role"],
                        "source_id": source_id,
                    }
                )
        for term in REVIEW_TERMS:
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])", text):
                if (item["destination_path"], term) not in allowed:
                    findings.append(
                        {
                            "channel": item["channel"],
                            "kind": "review_required",
                            "path": item["destination_path"],
                            "match": term,
                            "role": item["role"],
                        }
                    )
    return sorted(findings, key=lambda item: (item["kind"], item["path"], item["match"]))


def validate(root: Path, config_path: Path) -> dict:
    governance = validate_governance(json.loads(config_path.read_text(encoding="utf-8")))
    manifest = build_manifest(root)
    contents = {
        item["source_path"]: (root / item["source_path"]).read_bytes()
        for item in manifest
        if not item["source_path"].startswith("scripts/link-kilo-skills.sh#")
        and (root / item["source_path"]).is_file()
    }
    for item in manifest:
        if item["source_path"] != "scripts/link-kilo-skills.sh#generated-command-wrapper":
            continue
        skill_path = root / "skills" / "engineering" / item["package"] / "SKILL.md"
        if not skill_path.is_file():
            for bucket in ("productivity", "misc"):
                candidate = root / "skills" / bucket / item["package"] / "SKILL.md"
                if candidate.is_file():
                    skill_path = candidate
                    break
        description = ""
        in_frontmatter = False
        for line in skill_path.read_text(encoding="utf-8").splitlines():
            if line == "---":
                if in_frontmatter:
                    break
                in_frontmatter = True
            elif in_frontmatter and line.startswith("description:"):
                description = line.split(":", 1)[1].strip()
                break
        wrapper = (
            f"---\ndescription: {description}\n---\n\n"
            "<!-- kilo-generated-wrapper: mattpocock-skills/link-kilo-skills.sh/v2 -->\n\n"
            f"请使用 `{item['package']}` skill，严格按它的流程处理下面的问题：\n\n$ARGUMENTS\n"
        ).rstrip("\n").encode()
        if sha256_bytes(wrapper) != item["sha256"]:
            raise GovernanceError(f"generated wrapper reconstruction mismatch: {item['package']}")
        contents[f"{item['channel']}:{item['destination_path']}"] = wrapper
    findings = scan_entries(manifest, governance, contents)
    blockers = legal_blockers(governance)
    if blockers:
        status = "blocked_legal_boundary"
    elif any(item["kind"] == "prohibited_import" for item in findings):
        status = "prohibited_import"
    elif findings:
        status = "review_required"
    else:
        status = "passed"
    return {
        "schema_version": "restricted-reference-governance-result/v1",
        "status": status,
        "legal_blockers": blockers,
        "findings": findings,
        "manifest": manifest,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skills-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    config = args.config or args.skills_root / "config" / "restricted-reference-governance.json"
    try:
        result = validate(args.skills_root, config)
    except (GovernanceError, json.JSONDecodeError, OSError) as error:
        result = {
            "schema_version": "restricted-reference-governance-result/v1",
            "status": "invalid_governance",
            "error": str(error),
        }
    print(canonical_bytes(result).decode(), end="")
    return 0 if result["status"] in {"passed", "review_required"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
