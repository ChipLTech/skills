#!/usr/bin/env python3
"""Validate stable vLLM-DLC skill publication surfaces."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml


SKILLS = ("model-adaptation", "main-to-main-upgrade")
CONTRACT_VERSION = "vllm-dlc-contract/v1"


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def parse_frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        raise ValueError(f"missing frontmatter: {path}")
    document = yaml.safe_load(match.group(1))
    if not isinstance(document, dict):
        raise ValueError(f"invalid frontmatter: {path}")
    return document


def markdown_entry(path: Path, identity: str) -> dict[str, str]:
    pattern = re.compile(
        rf"^- \*\*\[{re.escape(identity)}\]\((?P<link>[^)]+)\)\*\* — (?P<description>.+)$",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(path.read_text(encoding="utf-8")))
    if len(matches) != 1:
        raise ValueError(f"expected exactly one catalog entry for {identity} in {path}")
    return matches[0].groupdict()


def skillhub_entry(path: Path, identity: str) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    rows = [row for row in document.get("skills", []) if row.get("name") == identity]
    if len(rows) != 1:
        raise ValueError(f"expected exactly one SkillHub entry for {identity}")
    return rows[0]


def repository_snapshot(root: Path) -> dict[str, str]:
    def git(*args: str, binary: bool = False):
        process = subprocess.run(
            ["/usr/bin/git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=not binary,
        )
        return process.stdout

    status = git("-c", "core.quotePath=false", "status", "--porcelain=v1", "-z", "--untracked-files=all", binary=True)
    diff = git("diff", "--binary", binary=True)
    index = git("diff", "--binary", "--cached", binary=True)
    return {
        "branch": git("branch", "--show-current").strip(),
        "head": git("rev-parse", "HEAD").strip(),
        "status_digest": "sha256:" + hashlib.sha256(status).hexdigest(),
        "tracked_diff_digest": "sha256:" + hashlib.sha256(diff).hexdigest(),
        "index_diff_digest": "sha256:" + hashlib.sha256(index).hexdigest(),
    }


def expected_wrapper(identity: str, description: str) -> str:
    return (
        "---\n"
        f"description: {description}\n"
        "---\n\n"
        "<!-- kilo-generated-wrapper: mattpocock-skills/link-kilo-skills.sh/v2 -->\n\n"
        f"请使用 `{identity}` skill，严格按它的流程处理下面的问题：\n\n"
        "$ARGUMENTS\n"
    )


def validate_skill(args: argparse.Namespace, identity: str) -> dict[str, Any]:
    skills_root = args.skills_root.resolve()
    stable_root = skills_root / "skills" / "engineering" / identity
    in_progress_root = skills_root / "skills" / "in-progress" / identity
    skill_md = stable_root / "SKILL.md"
    agent_yaml = stable_root / "agents" / "openai.yaml"
    knowledge_md = stable_root / "knowledge.md"
    if not stable_root.is_dir() or in_progress_root.exists():
        raise ValueError(f"stable identity mismatch for {identity}")
    for path in (skill_md, agent_yaml, knowledge_md):
        if not path.is_file():
            raise ValueError(f"missing package file: {path}")
    frontmatter = parse_frontmatter(skill_md)
    description = frontmatter.get("description")
    if frontmatter.get("name") != identity or not isinstance(description, str) or not description:
        raise ValueError(f"invalid frontmatter for {identity}")
    if frontmatter.get("disable-model-invocation") is True:
        raise ValueError(f"model invocation disabled for {identity}")
    agent = yaml.safe_load(agent_yaml.read_text(encoding="utf-8"))
    prompt = agent.get("interface", {}).get("default_prompt", "") if isinstance(agent, dict) else ""
    required_terms = {
        "model-adaptation": ("specific", "incompatible", "attention", "upstream alignment", "environment rebuild", "single-operator", "compile", "smoke-only"),
        "main-to-main-upgrade": ("exact upstream", "verified vllm alignment", "compatibility-impact", "standalone", "environment rebuild", "single-operator", "compile", "release", "smoke-only"),
    }[identity]
    if any(term not in prompt.lower() for term in required_terms):
        raise ValueError(f"agent prompt boundary mismatch for {identity}")
    if CONTRACT_VERSION not in skill_md.read_text(encoding="utf-8") or CONTRACT_VERSION not in knowledge_md.read_text(encoding="utf-8"):
        raise ValueError(f"missing shared contract marker for {identity}")

    top = markdown_entry(skills_root / "README.md", identity)
    engineering = markdown_entry(skills_root / "skills" / "engineering" / "README.md", identity)
    expected_top_link = f"./skills/engineering/{identity}/SKILL.md"
    expected_eng_link = f"./{identity}/SKILL.md"
    if top != {"link": expected_top_link, "description": description}:
        raise ValueError(f"top-level catalog mismatch for {identity}")
    if engineering != {"link": expected_eng_link, "description": description}:
        raise ValueError(f"engineering catalog mismatch for {identity}")

    plugin = json.loads((skills_root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    plugin_path = f"./skills/engineering/{identity}"
    if plugin.get("skills", []).count(plugin_path) != 1:
        raise ValueError(f"plugin mismatch for {identity}")
    hub = skillhub_entry(skills_root / "SKILLHUB.yaml", identity)
    if hub.get("path") != f"skills/engineering/{identity}" or hub.get("description") != description:
        raise ValueError(f"SkillHub mismatch for {identity}")
    for member in ("SKILL.md", "agents/", "knowledge.md"):
        if member not in hub.get("files", []):
            raise ValueError(f"SkillHub files mismatch for {identity}")
    docs = (skills_root / "README.zh-CN.md").read_text(encoding="utf-8")
    if identity not in docs or f"/{identity}" not in docs or "不需要 `--all`" not in docs:
        raise ValueError(f"installation docs mismatch for {identity}")
    linker = (skills_root / "scripts" / "link-kilo-skills.sh").read_text(encoding="utf-8")
    if "kilo-generated-wrapper: mattpocock-skills/link-kilo-skills.sh/v2" not in linker:
        raise ValueError("linker wrapper ownership marker missing")

    return {
        "skill_identity": identity,
        "stable_path": f"skills/engineering/{identity}",
        "duplicate_in_progress_identity": False,
        "frontmatter": {"name": identity, "description": description},
        "agent": {"default_prompt_digest": "sha256:" + hashlib.sha256(prompt.encode()).hexdigest()},
        "catalogs": {
            "top_level": {"description": top["description"], "link": top["link"]},
            "engineering": {"description": engineering["description"], "link": engineering["link"]},
        },
        "plugin": {"path": plugin_path},
        "skillhub": {"description": hub["description"], "files": hub["files"], "path": hub["path"]},
        "linker": {"default_selected": True},
        "wrapper": {
            "generated_from_frontmatter": True,
            "expected_digest": "sha256:" + hashlib.sha256(expected_wrapper(identity, description).encode()).hexdigest(),
        },
        "digests": {
            "skill": sha256_file(skill_md),
            "agent": sha256_file(agent_yaml),
            "knowledge": sha256_file(knowledge_md),
        },
    }


def emit(report: dict[str, Any]) -> None:
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--skills-root", required=True, type=Path)
    parser.add_argument("--knowledge-root", required=True, type=Path)
    parser.add_argument("--vllm-root", required=True, type=Path)
    parser.add_argument("--vllm-dlc-root", required=True, type=Path)
    subparsers = parser.add_subparsers(dest="target", required=True)
    live = subparsers.add_parser("live-package")
    live.add_argument("skill_identity", choices=SKILLS)
    subparsers.add_parser("publication-surface-inventory")
    args = parser.parse_args()

    before = {"vllm": repository_snapshot(args.vllm_root), "vllm_dlc": repository_snapshot(args.vllm_dlc_root)}
    try:
        if args.target == "live-package":
            skill = validate_skill(args, args.skill_identity)
            report = {"contract_version": CONTRACT_VERSION, "overall_status": "passed", **skill}
        else:
            skills = [validate_skill(args, identity) for identity in SKILLS]
            report = {
                "contract_version": CONTRACT_VERSION,
                "overall_status": "passed",
                "skills": skills,
                "surface_digests": {
                    str(path): sha256_file(path)
                    for path in (
                        args.skills_root / "README.md",
                        args.skills_root / "skills" / "engineering" / "README.md",
                        args.skills_root / ".claude-plugin" / "plugin.json",
                        args.skills_root / "SKILLHUB.yaml",
                        args.skills_root / "scripts" / "link-kilo-skills.sh",
                        args.skills_root / "README.zh-CN.md",
                    )
                },
            }
    except Exception as error:
        after = {"vllm": repository_snapshot(args.vllm_root), "vllm_dlc": repository_snapshot(args.vllm_dlc_root)}
        emit({
            "contract_version": CONTRACT_VERSION,
            "overall_status": "failed",
            "error": str(error),
            "repository_before": before,
            "repository_after": after,
        })
        return 30
    after = {"vllm": repository_snapshot(args.vllm_root), "vllm_dlc": repository_snapshot(args.vllm_dlc_root)}
    report["repository_before"] = before
    report["repository_after"] = after
    emit(report)
    return 0 if before == after else 50


if __name__ == "__main__":
    raise SystemExit(main())
