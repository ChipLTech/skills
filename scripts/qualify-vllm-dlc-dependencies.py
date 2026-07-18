#!/usr/bin/env python3
"""Qualify pinned vLLM-DLC launch dependencies without loading a model."""

import argparse
import contextlib
import importlib
import io
import json
import sys
from importlib import metadata
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version


DEFAULT_REQUIREMENTS = Path("/work/skills/requirements-vllm-dlc-contracts.txt")
IMPORTS = (
    ("NamedToolChoice", "mistral_common.protocol.instruct.tool_calls", "NamedToolChoice"),
    ("vllm.entrypoints.openai.api_server", "vllm.entrypoints.openai.api_server", None),
    ("vllm_dlc", "vllm_dlc", None),
    ("transformers.AutoTokenizer", "transformers", "AutoTokenizer"),
    ("cv2", "cv2", None),
    ("ijson", "ijson", None),
    ("model_hosting_container_standards", "model_hosting_container_standards", None),
)
NATIVE_MODULES = (
    ("vllm._C", "vllm"),
    ("vllm_dlc.vllm_dlc_C", "vllm_dlc"),
)
SCHEMA_VERSION = "vllm-dlc-dependency-qualification/v1"
POLICY_SCHEMA_VERSION = "vllm-dlc-dependency-exception-policy/v1"
METADATA_DISTRIBUTIONS = ("vllm", "vllm-dlc")
EXPECTED_EXCEPTION = {
    "dependency": "opencv-python-headless",
    "distribution": "vllm",
    "installed_version": "4.11.0.86",
    "rationale": "vllm-dlc requires <=4.11.0.86 to preserve numpy<2",
    "requirement": "opencv-python-headless>=4.13.0",
    "vllm_dlc_requirement": "opencv-python-headless<=4.11.0.86",
}


def reason(code: str, subject: str, **details: str) -> dict[str, object]:
    return {
        "code": code,
        "distribution": details.get("distribution"),
        "error": details.get("error"),
        "expected_root": details.get("expected_root"),
        "expected_version": details.get("expected_version"),
        "installed_version": details.get("installed_version"),
        "origin": details.get("origin"),
        "requirement": details.get("requirement"),
        "subject": subject,
    }


def read_requirements(path: Path) -> tuple[list[dict[str, str | None]], list[dict[str, object]]]:
    dependencies = []
    reasons = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        return dependencies, [reason("requirements.unreadable", str(path), error=type(error).__name__)]

    seen = set()
    for line_number, raw_line in enumerate(lines, start=1):
        value = raw_line.strip()
        if not value or value.startswith("#"):
            continue
        subject = f"line:{line_number}"
        try:
            requirement = Requirement(value)
        except InvalidRequirement:
            reasons.append(reason("requirements.invalid", subject, requirement=value))
            continue
        exact_versions = [
            specifier.version for specifier in requirement.specifier
            if specifier.operator == "==" and not specifier.version.endswith(".*")
        ]
        if (
            requirement.url is not None
            or requirement.marker is not None
            or len(requirement.specifier) != 1
            or len(exact_versions) != 1
        ):
            reasons.append(reason("requirements.not_exact_pin", subject, requirement=value))
            continue
        name = canonicalize_name(requirement.name)
        if name in seen:
            reasons.append(reason("requirements.duplicate", subject, distribution=name))
            continue
        seen.add(name)
        expected = exact_versions[0]
        try:
            installed = metadata.version(requirement.name)
        except metadata.PackageNotFoundError:
            installed = None
            reasons.append(reason(
                "dependency.not_installed", name, expected_version=expected,
            ))
        else:
            try:
                matches = Version(installed) == Version(expected)
            except InvalidVersion:
                matches = installed == expected
            if not matches:
                reasons.append(reason(
                    "dependency.version_mismatch", name,
                    expected_version=expected, installed_version=installed,
                ))
        dependencies.append({
            "distribution": name,
            "expected_version": expected,
            "installed_version": installed,
        })
    return dependencies, reasons


def read_exception_policy(
    path: Path | None,
) -> tuple[dict[str, str] | None, list[dict[str, object]]]:
    if path is None:
        return None, []
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return None, [reason("exception_policy.unreadable", str(path), error=type(error).__name__)]
    if (
        not isinstance(document, dict)
        or set(document) != {"exception", "schema_version"}
        or document.get("schema_version") != POLICY_SCHEMA_VERSION
        or document.get("exception") != EXPECTED_EXCEPTION
    ):
        return None, [reason("exception_policy.invalid", str(path))]
    return document["exception"], []


def qualify_metadata(
    exception: dict[str, str] | None,
) -> tuple[list[dict[str, object]], list[dict[str, str]], list[dict[str, object]]]:
    checks = []
    exceptions = []
    reasons = []
    active_requirements: dict[str, set[str]] = {}

    for distribution in METADATA_DISTRIBUTIONS:
        try:
            raw_requirements = metadata.requires(distribution) or []
        except metadata.PackageNotFoundError:
            reasons.append(reason("metadata.distribution_not_installed", distribution))
            continue
        active_requirements[distribution] = set()
        for raw_requirement in raw_requirements:
            try:
                requirement = Requirement(raw_requirement)
            except InvalidRequirement:
                reasons.append(reason(
                    "metadata.invalid_requirement", distribution,
                    distribution=distribution, requirement=raw_requirement,
                ))
                continue
            if requirement.marker is not None and not requirement.marker.evaluate({"extra": ""}):
                continue

            requirement_text = str(requirement)
            dependency = canonicalize_name(requirement.name)
            active_requirements[distribution].add(requirement_text)
            try:
                installed = metadata.version(requirement.name)
            except metadata.PackageNotFoundError:
                installed = None
                satisfied = False
            else:
                try:
                    satisfied = (
                        requirement.url is None
                        and requirement.specifier.contains(installed, prereleases=True)
                    )
                except InvalidVersion:
                    satisfied = False
            check = {
                "compatibility_exception": False,
                "dependency": dependency,
                "distribution": distribution,
                "installed_version": installed,
                "requirement": requirement_text,
                "satisfied": satisfied,
            }
            checks.append(check)

    for check in checks:
        if check["satisfied"]:
            continue
        matches_exception = (
            exception is not None
            and check["distribution"] == exception["distribution"]
            and check["dependency"] == exception["dependency"]
            and check["requirement"] == exception["requirement"]
            and check["installed_version"] == exception["installed_version"]
            and exception["vllm_dlc_requirement"]
            in active_requirements.get("vllm-dlc", set())
            and any(
                candidate["distribution"] == "vllm-dlc"
                and candidate["requirement"] == exception["vllm_dlc_requirement"]
                and candidate["installed_version"] == exception["installed_version"]
                and candidate["satisfied"] is True
                for candidate in checks
            )
        )
        if matches_exception:
            check["compatibility_exception"] = True
            exceptions.append(exception)
        else:
            reasons.append(reason(
                "metadata.requirement_unsatisfied",
                f"{check['distribution']}:{check['dependency']}",
                distribution=str(check["distribution"]),
                installed_version=check["installed_version"],
                requirement=str(check["requirement"]),
            ))
    return checks, exceptions, reasons


def qualify_imports() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    imports = []
    reasons = []
    for label, module_name, attribute in IMPORTS:
        try:
            with (
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                module = importlib.import_module(module_name)
                if attribute is not None:
                    getattr(module, attribute)
        except Exception as error:  # Import-time failures can come from native dependencies.
            imports.append({"name": label, "passed": False})
            reasons.append(reason("import.failed", label, error=type(error).__name__))
        else:
            imports.append({"name": label, "passed": True})
    return imports, reasons


def qualify_native_modules(
    expected_vllm_root: Path,
    expected_vllm_dlc_root: Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    roots = {
        "vllm": expected_vllm_root.resolve(),
        "vllm_dlc": expected_vllm_dlc_root.resolve(),
    }
    modules = []
    reasons = []
    for module_name, root_name in NATIVE_MODULES:
        origin = None
        passed = False
        try:
            with (
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                module = importlib.import_module(module_name)
            module_file = getattr(module, "__file__", None)
            if module_file is None:
                raise ValueError("module has no file origin")
            resolved_origin = Path(module_file).resolve()
            origin = str(resolved_origin)
            resolved_origin.relative_to(roots[root_name])
            passed = True
        except ValueError:
            reasons.append(reason(
                "native_module.unexpected_origin", module_name,
                expected_root=str(roots[root_name]), origin=origin,
            ))
        except Exception as error:  # Native loading errors must block qualification.
            reasons.append(reason(
                "native_module.import_failed", module_name, error=type(error).__name__,
            ))
        modules.append({
            "expected_root": str(roots[root_name]),
            "name": module_name,
            "origin": origin,
            "passed": passed,
        })
    return modules, reasons


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--requirements", type=Path, default=DEFAULT_REQUIREMENTS)
    parser.add_argument("--exception-policy", type=Path)
    parser.add_argument("--expected-vllm-root", type=Path, default=Path("/work/vllm"))
    parser.add_argument("--expected-vllm-dlc-root", type=Path, default=Path("/work/vllm-dlc"))
    arguments = parser.parse_args()

    dependencies, reasons = read_requirements(arguments.requirements)
    exception, policy_reasons = read_exception_policy(arguments.exception_policy)
    metadata_checks, compatibility_exceptions, metadata_reasons = qualify_metadata(exception)
    reasons.extend(policy_reasons)
    reasons.extend(metadata_reasons)
    imports, import_reasons = qualify_imports()
    native_modules, native_reasons = qualify_native_modules(
        arguments.expected_vllm_root,
        arguments.expected_vllm_dlc_root,
    )
    reasons.extend(import_reasons)
    reasons.extend(native_reasons)
    status = "blocked" if reasons else "passed"
    report = {
        "compatibility_exceptions": compatibility_exceptions,
        "dependencies": dependencies,
        "imports": imports,
        "metadata_checks": metadata_checks,
        "model_started": False,
        "native_modules": native_modules,
        "reasons": reasons,
        "requirements_path": str(arguments.requirements.resolve()),
        "schema_version": SCHEMA_VERSION,
        "status": status,
    }
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 20 if reasons else 0


if __name__ == "__main__":
    raise SystemExit(main())
