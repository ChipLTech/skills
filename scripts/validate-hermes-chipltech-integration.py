#!/usr/bin/env python3
"""Run live, routing-only acceptance checks for the Chipltech Hermes profile."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KNOWLEDGE_ROOT = ROOT.parent / "chipltech-knowledge-base"

SCENARIOS = (
    {
        "name": "environment_repair",
        "owner": "dlc-env-setup",
        "knowledge": "runtime-debugging/dlc-workstation-env-rebuild.md",
        "blocker": "blocked_missing_repository",
        "request": (
            "I need to repair a DLC workstation, but no repository locations "
            "or workspace roots were provided."
        ),
    },
    {
        "name": "model_adaptation",
        "owner": "model-adaptation",
        "knowledge": "vllm-dlc/model-adaptation-and-main-to-main-decisions.md",
        "blocker": "blocked_missing_asset",
        "request": (
            "I need to adapt a model for DLC Platform, but no model name, local "
            "model path, revision, or deployment profile was provided."
        ),
    },
    {
        "name": "model_qualification",
        "owner": "modelzoo-image-validation",
        "knowledge": "vllm-dlc/modelzoo-driven-dlc-tyd-image-contract.md",
        "blocker": "blocked_missing_asset",
        "request": (
            "I need runtime-first local model qualification, but no model name "
            "or absolute local model directory was provided."
        ),
    },
    {
        "name": "pd_separation",
        "owner": "pd-separation",
        "knowledge": "vllm-dlc/prefill-decode-separation.md",
        "blocker": "blocked_missing_contract",
        "request": (
            "I need Prefill/Decode separation, but no model path, topology, "
            "devices, endpoints, or authorization was provided."
        ),
    },
    {
        "name": "pytorch_dlc_plugin_migration",
        "owner": "pytorch-dlc-plugin-migration",
        "knowledge": "prompt-examples/pytorch-dlc-plugin-migration-prompts.md",
        "blocker": "blocked_ambiguous_source",
        "request": (
            "I need to migrate a production PyTorch DLC Backend component to "
            "PrivateUse1, but no source roots, migration slice, or authorization "
            "was provided."
        ),
    },
)


def _strip_ansi(value: str) -> str:
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)


def _command(
    argv: list[str], *, cwd: Path | None = None, timeout: int
) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.returncode, result.stdout, result.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        return 127, "", f"{type(error).__name__}: {error}"


def _answer_and_trace(output: str) -> tuple[str, str]:
    marker = "╭─ ⚕ Hermes"
    if marker not in output:
        return output, ""
    trace, rendered = output.split(marker, 1)
    answer = rendered.split("╰", 1)[0]
    return trace, answer


def _run(command: str, scenario: dict[str, str], workdir: Path, timeout: int) -> dict:
    prompt = (
        "Use chipltech-context for routing only. "
        f"{scenario['request']} "
        f"You must actually load {scenario['owner']} before returning its blocker. "
        "Return the selected knowledge path, execution skill, earliest terminal "
        "blocker, and Claim Boundary. Do not execute commands or modify files."
    )
    returncode, stdout, stderr = _command(
        [command, "chat", "-q", prompt],
        cwd=workdir,
        timeout=timeout,
    )
    output = _strip_ansi(stdout + stderr)
    trace, answer = _answer_and_trace(output)

    def loaded(identity: str) -> bool:
        return bool(
            re.search(
                rf"^\s*┊\s*📚\s+skill\s+{re.escape(identity)}\b",
                trace,
                re.MULTILINE,
            )
        )

    checks = {
        "command_succeeded": returncode == 0,
        "router_loaded": loaded("chipltech-context"),
        "owner_loaded": loaded(scenario["owner"]),
        "knowledge_selected": scenario["knowledge"] in answer,
        "blocker_selected": scenario["blocker"] in answer,
        "claim_boundary_reported": bool(
            re.search(r"claim\s+boundary\s*:", answer, re.IGNORECASE)
        ),
    }
    return {
        "name": scenario["name"],
        "owner": scenario["owner"],
        "knowledge": scenario["knowledge"],
        "blocker": scenario["blocker"],
        "checks": checks,
        "passed": all(checks.values()),
        "returncode": returncode,
        "error": stderr.strip() if returncode else "",
    }


def _config_value(command: str, key: str, timeout: int, *, json_value=False):
    argv = [command, "config", "get", key]
    if json_value:
        argv.append("--json")
    returncode, stdout, stderr = _command(argv, timeout=timeout)
    if returncode:
        return None, stderr.strip()
    if not json_value:
        return stdout.strip(), ""
    try:
        return json.loads(stdout), ""
    except json.JSONDecodeError as error:
        return None, f"JSONDecodeError: {error}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--command", default="chipltech-engineering")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--knowledge-root", type=Path, default=DEFAULT_KNOWLEDGE_ROOT)
    parser.add_argument("--skills-root", type=Path, default=ROOT)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--provider", default="custom")
    args = parser.parse_args()

    skills_root = args.skills_root.resolve()
    knowledge_root = args.knowledge_root.resolve()
    expected_external_dirs = [
        str(skills_root / "skills" / category)
        for category in ("engineering", "productivity", "misc")
    ]
    values = {}
    errors = {}
    for key, json_value in (
        ("terminal.cwd", False),
        ("model.default", False),
        ("model.provider", False),
        ("skills.external_dirs", True),
        ("skills.config", True),
    ):
        values[key], errors[key] = _config_value(
            args.command, key, args.timeout, json_value=json_value
        )

    profile_checks = {
        "dynamic_workspace": values["terminal.cwd"] == ".",
        "model_matches": values["model.default"] == args.model,
        "provider_matches": values["model.provider"] == args.provider,
        "stable_external_dirs_match": values["skills.external_dirs"]
        == expected_external_dirs,
        "knowledge_root_matches": (
            values["skills.config"] or {}
        ).get("chipltech_kb", {}).get("path")
        == str(knowledge_root),
        "skills_root_matches": (
            values["skills.config"] or {}
        ).get("chipltech_skills", {}).get("path")
        == str(skills_root),
        "knowledge_root_readable": (knowledge_root / "CONTEXT.md").is_file(),
        "skills_root_readable": (
            skills_root / "skills" / "engineering" / "chipltech-context" / "SKILL.md"
        ).is_file(),
    }

    with tempfile.TemporaryDirectory(prefix="hermes-chipltech-") as directory:
        workdir = Path(directory)
        scenarios = [
            _run(args.command, scenario, workdir, args.timeout)
            for scenario in SCENARIOS
        ]

    report = {
        "schema": "hermes-chipltech-acceptance/v1",
        "profile_command": args.command,
        "profile_checks": profile_checks,
        "profile_errors": {key: value for key, value in errors.items() if value},
        "scenarios": scenarios,
        "passed": all(profile_checks.values()) and all(
            row["passed"] for row in scenarios
        ),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
