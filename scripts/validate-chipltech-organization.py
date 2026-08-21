#!/usr/bin/env python3
"""Validate Chipltech capability and lesson reference closure."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KNOWLEDGE_ROOT = ROOT.parent / "chipltech-knowledge-base"
CAPABILITY_MANIFEST = Path("agent-context/capability-manifest.yaml")
LESSON_INDEX = Path("validated-lessons/index.yaml")
BEHAVIOR_MANIFEST = Path("tests/workflow_behavior/fixtures/representative-manifest.json")
ORGANIZATION_CONTRACTS = (
    "agent-evidence-return-v1.schema.json",
    "engineering-handoff-v1.schema.json",
    "context-reference-package-v1.schema.json",
    "team-task-brief-v1.schema.json",
)


def _anchor(heading: str) -> str:
    value = heading.strip().lower()
    value = re.sub(r"[^\w\-\u4e00-\u9fff ]", "", value)
    return re.sub(r"[\s-]+", "-", value).strip("-")


def _headings(path: Path) -> set[str]:
    headings = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if match:
            headings.add(_anchor(match.group(1)))
    return headings


def _section_text(path: Path, anchor: str) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    collecting = False
    section_level = 0
    selected: list[str] = []
    for line in lines:
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            level = len(match.group(1))
            if collecting and level <= section_level:
                break
            if _anchor(match.group(2)) == anchor:
                collecting = True
                section_level = level
        if collecting:
            selected.append(line)
    return "\n".join(selected)


def _contained_path(root: Path, path_text: str) -> Path:
    relative = Path(path_text)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("reference containment")
    resolved_root = root.resolve()
    resolved = (resolved_root / relative).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError("reference containment")
    return resolved


def _resolve_ref(ref: str, skills_root: Path, knowledge_root: Path) -> tuple[Path, str]:
    if not isinstance(ref, str) or not ref:
        raise ValueError("reference containment")
    path_text, _, anchor = ref.partition("#")
    path_text = path_text.partition("::")[0]
    if path_text == "SKILLHUB.yaml" or path_text.startswith(("skills/", "tests/", "scripts/")):
        return _contained_path(skills_root, path_text), anchor
    return _contained_path(knowledge_root, path_text), anchor


def _check_ref(
    ref: str,
    label: str,
    skills_root: Path,
    knowledge_root: Path,
    errors: list[str],
) -> None:
    try:
        path, anchor = _resolve_ref(ref, skills_root, knowledge_root)
    except (TypeError, ValueError, OSError):
        errors.append(f"{label} reference escapes its root: {ref}")
        return
    if not path.is_file():
        errors.append(f"{label} references missing file: {ref}")
        return
    if anchor and anchor not in _headings(path):
        errors.append(f"{label} references missing heading: {ref}")


def _qualified_test_text(ref: str, skills_root: Path) -> str | None:
    parts = ref.split("::")
    if len(parts) != 3:
        return None
    try:
        path = _contained_path(skills_root, parts[0])
    except (TypeError, ValueError, OSError):
        return None
    if not path.is_file():
        return None
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return None
    class_name, method_name = parts[1:]
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == method_name:
                    return ast.get_source_segment(path.read_text(encoding="utf-8"), child)
    return None


def _load_yaml(path: Path, errors: list[str]) -> dict:
    if not path.is_file():
        errors.append(f"missing required manifest: {path}")
        return {}
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        errors.append(f"invalid YAML {path}: {error}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"manifest must be a mapping: {path}")
        return {}
    return value


def _source_tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return "sha256:" + digest.hexdigest()


def _load_behavior_run(
    path: Path | None,
    errors: list[str],
    expected_manifest_digest: str | None = None,
    expected_cases: set[tuple[str, str]] | None = None,
    expected_case_ids: list[str] | None = None,
    expected_source_digest: str | None = None,
) -> tuple[str, list[str]]:
    if path is None:
        return "not_reported", []
    try:
        run = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"invalid behavior run result {path}: {error}")
        return "failed", []
    if (
        not isinstance(run, dict)
        or run.get("schema") != "workflow-behavior-run-result/v1"
        or run.get("terminal_state") not in {"suite_passed", "suite_failed"}
        or not isinstance(run.get("run_binding"), dict)
        or not isinstance(run.get("cases"), list)
        or not run.get("cases")
        or run.get("authoritative") is not False
        or run.get("runtime_acceptance") is not False
        or not isinstance(run.get("problems"), list)
        or not isinstance(run.get("claim_boundary"), str)
    ):
        errors.append(f"invalid behavior run result contract: {path}")
        return "failed", []
    workflows = []
    actual_cases: list[tuple[str, str]] = []
    malformed = False
    for case in run["cases"]:
        if not isinstance(case, dict):
            malformed = True
            continue
        if (
            not isinstance(case.get("id"), str)
            or not case.get("id")
            or case.get("quality_kind") not in {"behavior", "contract_static"}
            or case.get("terminal_state") not in {
                "passed", "assertion_failed", "execution_failed"
            }
            or case.get("authoritative") is not False
            or case.get("runtime_acceptance") is not False
            or not isinstance(case.get("claim_boundary_preserved"), bool)
            or not isinstance(case.get("forbidden_actions"), list)
            or not isinstance(case.get("workspace_mutation_observed"), bool)
        ):
            malformed = True
            continue
        workflow = case.get("workflow")
        if not isinstance(workflow, str) or not workflow:
            malformed = True
        else:
            actual_cases.append((case["id"], workflow))
        if (
            case.get("quality_kind") == "behavior"
            and isinstance(workflow, str)
            and workflow
            and case.get("terminal_state") == "passed"
        ):
            workflows.append(workflow)
    if malformed:
        errors.append(f"invalid behavior run case contract: {path}")
        return "failed", sorted(set(workflows))
    binding = run["run_binding"]
    if (
        set(binding) != {
            "manifest_digest",
            "case_ids",
            "repository_head",
            "repository_status_digest",
            "repository_snapshot_digest",
            "repository_source_digest",
        }
        or not isinstance(binding.get("manifest_digest"), str)
        or not isinstance(binding.get("case_ids"), list)
        or not all(isinstance(item, str) for item in binding.get("case_ids", []))
        or re.fullmatch(r"sha256:[0-9a-f]{64}", str(binding.get("repository_source_digest", ""))) is None
    ):
        errors.append(f"invalid behavior run binding contract: {path}")
        return "failed", sorted(set(workflows))
    if (
        expected_manifest_digest is None
        or expected_cases is None
        or expected_case_ids is None
    ):
        errors.append("canonical behavior manifest was not available")
        return "failed", sorted(set(workflows))
    passed = (
        binding["manifest_digest"] == expected_manifest_digest
        and binding["case_ids"] == expected_case_ids
        and binding["repository_source_digest"] == expected_source_digest
        and len(actual_cases) == len(set(actual_cases))
        and set(actual_cases) == expected_cases
        and run["terminal_state"] == "suite_passed"
        and all(
            case.get("terminal_state") == "passed"
            and case.get("workspace_mutation_observed") is False
            and case.get("claim_boundary_preserved") is True
            for case in run["cases"]
        )
    )
    return ("passed" if passed else "failed"), sorted(set(workflows))


def validate_organization(
    skills_root: Path,
    knowledge_root: Path,
    behavior_run: Path | None = None,
) -> dict:
    skills_root = skills_root.resolve()
    knowledge_root = knowledge_root.resolve()
    errors: list[str] = []
    source_digest = _source_tree_digest(skills_root)

    for required in (knowledge_root / "CONTEXT.md", knowledge_root / "README.md"):
        if not required.is_file():
            errors.append(f"missing knowledge root marker: {required}")
    if not (skills_root / "skills").is_dir():
        errors.append(f"missing skills root marker: {skills_root / 'skills'}")

    capabilities_doc = _load_yaml(knowledge_root / CAPABILITY_MANIFEST, errors)
    lessons_doc = _load_yaml(knowledge_root / LESSON_INDEX, errors)
    publication = _load_yaml(skills_root / "SKILLHUB.yaml", errors)
    behavior_workflows: set[str] = set()
    behavior_cases: set[tuple[str, str]] = set()
    behavior_case_ids: list[str] = []
    behavior_manifest_digest: str | None = None
    behavior_path = skills_root / BEHAVIOR_MANIFEST
    if not behavior_path.is_file():
        errors.append(f"missing behavior manifest: {behavior_path}")
    else:
        try:
            behavior = json.loads(behavior_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            errors.append(f"invalid behavior manifest: {error}")
        else:
            if not isinstance(behavior, dict):
                errors.append("behavior manifest must be a mapping")
            elif behavior.get("schema") != "workflow-behavior-manifest/v1":
                errors.append("behavior manifest schema mismatch")
            elif not isinstance(behavior.get("cases"), list):
                errors.append("behavior manifest cases must be a list")
            else:
                behavior_manifest_digest = "sha256:" + hashlib.sha256(
                    behavior_path.read_bytes()
                ).hexdigest()
                malformed_behavior_cases = False
                for row in behavior["cases"]:
                    if (
                        not isinstance(row, dict)
                        or not isinstance(row.get("id"), str)
                        or not row.get("id")
                        or not isinstance(row.get("workflow"), str)
                        or not row.get("workflow")
                    ):
                        malformed_behavior_cases = True
                        continue
                    behavior_cases.add((row["id"], row["workflow"]))
                    behavior_case_ids.append(row["id"])
                if malformed_behavior_cases or len(behavior_cases) != len(behavior["cases"]):
                    errors.append("behavior manifest cases must have unique string id/workflow pairs")
                behavior_workflows = {
                    row.get("workflow")
                    for row in behavior["cases"]
                    if isinstance(row, dict)
                    and row.get("quality_kind") == "behavior"
                    and isinstance(row.get("workflow"), str)
                    and row.get("workflow")
                }
    contract_root = skills_root / "skills/engineering/chipltech-context/contracts"
    missing_organization_contracts = [
        name for name in ORGANIZATION_CONTRACTS
        if not (contract_root / name).is_file()
    ]
    for name in missing_organization_contracts:
        errors.append(f"missing organization contract: {name}")
    publication_rows = publication.get("skills", [])
    if not isinstance(publication_rows, list):
        errors.append("SKILLHUB skills must be a list")
        publication_rows = []
    published = {}
    for row in publication_rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if isinstance(name, str) and name:
            published[name] = row
        elif name is not None:
            errors.append("SKILLHUB skill name must be a non-empty string")

    if capabilities_doc.get("schema") != "chipltech-capability-catalog/v1":
        errors.append("capability manifest schema must be chipltech-capability-catalog/v1")
    capabilities = capabilities_doc.get("capabilities", [])
    if not isinstance(capabilities, list):
        errors.append("capabilities must be a list")
        capabilities = []
    seen_capabilities: set[str] = set()
    capability_ref_fields = (
        "quickstart_ref",
        "owner_contract_ref",
        "minimum_inputs_ref",
        "negative_scope_ref",
        "hardware_authorization_ref",
        "terminal_states_ref",
        "claim_boundary_ref",
        "publication_ref",
    )
    for row in capabilities:
        if not isinstance(row, dict):
            errors.append("capability row must be a mapping")
            continue
        capability_id = row.get("capability_id", "<missing capability_id>")
        if not re.fullmatch(r"cap\.[a-z0-9.-]+", str(capability_id)):
            errors.append(f"invalid capability_id: {capability_id}")
        if isinstance(capability_id, str) and capability_id in seen_capabilities:
            errors.append(f"duplicate capability_id: {capability_id}")
        if isinstance(capability_id, str):
            seen_capabilities.add(capability_id)
        if not row.get("human_entry"):
            errors.append(f"{capability_id} missing human_entry")
        owner = row.get("owner_skill")
        if not isinstance(owner, str) or owner not in published:
            errors.append(f"{capability_id} owner {owner!r} is missing from SKILLHUB.yaml")
        for field in capability_ref_fields:
            ref = row.get(field)
            if not isinstance(ref, str) or not ref:
                errors.append(f"{capability_id} missing {field}")
                continue
            _check_ref(ref, f"{capability_id}.{field}", skills_root, knowledge_root, errors)
        contract = row.get("owner_contract_ref", "")
        if not isinstance(contract, str):
            contract = ""
        if owner and f"/{owner}/SKILL.md" not in contract:
            errors.append(f"{capability_id} owner contract does not match owner {owner}")
        if owner in published:
            expected_path = str(Path(contract).parent)
            if published[owner].get("path") != expected_path:
                errors.append(
                    f"{capability_id} SKILLHUB path does not match owner contract: "
                    f"{published[owner].get('path')!r} != {expected_path!r}"
                )
        quickstart_ref = row.get("quickstart_ref", "")
        if not isinstance(quickstart_ref, str):
            quickstart_ref = ""
        quickstart_path, _, quickstart_anchor = quickstart_ref.partition("#")
        if quickstart_path and quickstart_anchor:
            try:
                path = _contained_path(knowledge_root, quickstart_path)
            except (TypeError, ValueError, OSError):
                path = None
            if path is not None and path.is_file() and str(capability_id) not in _section_text(
                path, quickstart_anchor
            ):
                errors.append(
                    f"{capability_id} is not published in its Quickstart section"
                )
        if row.get("publication_ref") != "SKILLHUB.yaml":
            errors.append(f"{capability_id} publication_ref must be SKILLHUB.yaml")

    catalog_ref = capabilities_doc.get("catalog_ref")
    if not isinstance(catalog_ref, str) or not catalog_ref:
        errors.append("capability manifest missing catalog_ref")
    else:
        try:
            catalog_path = _contained_path(knowledge_root, catalog_ref)
        except (TypeError, ValueError, OSError):
            errors.append(f"capability catalog reference escapes knowledge root: {catalog_ref}")
            catalog_path = None
        if catalog_path is not None and not catalog_path.is_file():
            errors.append(f"capability catalog references missing file: {catalog_ref}")
        elif catalog_path is not None:
            quickstart_ids = re.findall(
                r"^Capability ID:\s*`(cap\.[a-z0-9.-]+)`\s*$",
                catalog_path.read_text(encoding="utf-8"),
                flags=re.MULTILINE,
            )
            duplicate_quickstart_ids = sorted(
                capability_id
                for capability_id in set(quickstart_ids)
                if quickstart_ids.count(capability_id) > 1
            )
            if duplicate_quickstart_ids:
                errors.append(
                    "duplicate Quickstart Capability IDs: "
                    + ", ".join(duplicate_quickstart_ids)
                )
            quickstart_set = set(quickstart_ids)
            if quickstart_set != seen_capabilities:
                missing_from_manifest = sorted(quickstart_set - seen_capabilities)
                missing_from_quickstart = sorted(seen_capabilities - quickstart_set)
                errors.append(
                    "Quickstart Capability ID set must equal manifest; "
                    f"missing from manifest={missing_from_manifest}, "
                    f"missing from Quickstart={missing_from_quickstart}"
                )

    if lessons_doc.get("schema") != "chipltech-validated-lesson-index/v1":
        errors.append("lesson index schema must be chipltech-validated-lesson-index/v1")
    if lessons_doc.get("unlisted_case_default") != "historical_unreviewed":
        errors.append("unlisted cases must default to historical_unreviewed")
    lessons = lessons_doc.get("lessons", [])
    if not isinstance(lessons, list):
        errors.append("lessons must be a list")
        lessons = []
    seen_lessons: set[str] = set()
    lesson_required = (
        "statement",
        "identity_scope",
        "applies_to",
        "does_not_apply_to",
        "evidence_class",
        "validation_method",
        "counterexample",
        "owner_skill",
        "review_date",
        "claim_boundary",
    )
    for row in lessons:
        if not isinstance(row, dict):
            errors.append("lesson row must be a mapping")
            continue
        lesson_id = row.get("lesson_id", "<missing lesson_id>")
        if not re.fullmatch(r"lesson\.[a-z0-9.-]+", str(lesson_id)):
            errors.append(f"invalid lesson_id: {lesson_id}")
        if isinstance(lesson_id, str) and lesson_id in seen_lessons:
            errors.append(f"duplicate lesson_id: {lesson_id}")
        if isinstance(lesson_id, str):
            seen_lessons.add(lesson_id)
        if row.get("status") not in {
            "candidate", "reviewed", "validated", "contractual",
            "superseded", "withdrawn",
        }:
            errors.append(f"{lesson_id} has invalid lifecycle status")
        for field in lesson_required:
            if not row.get(field):
                errors.append(f"{lesson_id} missing {field}")
        if not isinstance(row.get("owner_skill"), str) or row.get("owner_skill") not in published:
            errors.append(f"{lesson_id} owner is missing from SKILLHUB.yaml")
        if row.get("evidence_class") == "runtime_observation":
            errors.append(f"{lesson_id} upgrades historical case to runtime_observation")
        claim_boundary = str(row.get("claim_boundary", "")).lower()
        if "does not" not in claim_boundary:
            errors.append(f"{lesson_id} claim boundary must state what it does not establish")
        for field in ("source_cases", "evidence_refs", "rule_refs", "test_refs"):
            refs = row.get(field)
            if not isinstance(refs, list) or not refs:
                errors.append(f"{lesson_id} missing non-empty {field}")
                continue
            for ref in refs:
                _check_ref(str(ref), f"{lesson_id}.{field}", skills_root, knowledge_root, errors)
        if row.get("status") == "validated":
            for ref in row.get("test_refs", []):
                test_text = _qualified_test_text(str(ref), skills_root)
                if test_text is None:
                    errors.append(
                        f"{lesson_id} validated test_ref must identify an existing "
                        f"file::Class::test_method: {ref}"
                    )
                    continue
                statement = str(row.get("statement", ""))
                if str(lesson_id) not in test_text or statement not in test_text:
                    errors.append(
                        f"{lesson_id} validated test {ref} must contain the exact "
                        "lesson ID and statement"
                    )
                if "self.assert_lesson_contract(" not in test_text:
                    errors.append(
                        f"{lesson_id} validated test {ref} must execute assert_lesson_contract"
                    )

    structural_passed = not errors
    behavior_status, executed_behavior_workflows = _load_behavior_run(
        behavior_run.resolve() if behavior_run is not None else None,
        errors,
        behavior_manifest_digest,
        behavior_cases,
        behavior_case_ids,
        source_digest,
    )
    if behavior_run is not None and behavior_status != "passed":
        errors.append(f"behavior run did not pass: {behavior_run.resolve()}")
    quality_view = {
        "schema": "chipltech-capability-quality-view/v1",
        "levels": {
            "L1": {
                "meaning": "publication, catalog, owner, and reference closure",
                "status": "passed" if structural_passed else "failed",
                "capability_count": len(capabilities),
            },
            "L2": {
                "meaning": "completed representative deterministic workflow behavior run",
                "status": behavior_status,
                "declared_workflows": sorted(behavior_workflows),
                "executed_workflows": executed_behavior_workflows,
            },
            "L3": {
                "meaning": "organization schema, validator, fixture, and generated-copy closure",
                "status": "not_reported",
                "contracts": list(ORGANIZATION_CONTRACTS),
                "failed_checks": [],
            },
            "ST": {
                "meaning": "semantic user-prompt and claim-evaluation quality",
                "status": "not_reported",
            },
            "Hardware": {
                "meaning": "task-owned Real DLC Hardware evidence",
                "status": "not_reported",
            },
        },
        "runtime_quality": "not_reported",
        "claim_boundary": (
            "Source quality and fixture coverage only; this view does not establish "
            "task runtime, Real DLC Hardware, model, performance, acceptance, or release evidence."
        ),
    }
    return {
        "schema": "chipltech-organization-validation/v1",
        "skills_root": str(skills_root),
        "knowledge_root": str(knowledge_root),
        "capability_count": len(capabilities),
        "validated_lesson_count": sum(
            row.get("status") == "validated" for row in lessons if isinstance(row, dict)
        ),
        "errors": errors,
        "passed": not errors,
        "quality_view": quality_view,
        "claim_boundary": (
            "Structural closure only; this validation does not establish runtime, "
            "Real DLC Hardware, model, performance, acceptance, or release evidence."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skills-root", type=Path, default=ROOT)
    parser.add_argument("--knowledge-root", type=Path, default=DEFAULT_KNOWLEDGE_ROOT)
    parser.add_argument(
        "--behavior-run",
        type=Path,
        help="Completed workflow-behavior-run-result/v1 artifact from run-manifest.py",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = validate_organization(
        args.skills_root, args.knowledge_root, behavior_run=args.behavior_run
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        status = "PASS" if report["passed"] else "FAIL"
        print(f"{status}: {report['capability_count']} capabilities, "
              f"{report['validated_lesson_count']} validated lessons")
        for error in report["errors"]:
            print(f"- {error}")
        print(f"Claim Boundary: {report['claim_boundary']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
