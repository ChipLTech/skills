#!/usr/bin/env python3
"""Resolve optional ModelZoo reference evidence without runtime qualification."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import yaml

SCHEMA = "modelzoo-reference-record/v1"
SENSITIVE = re.compile(r"TOKEN|KEY|SECRET|PASSWORD|CREDENTIAL|AUTH", re.I)
SHA = re.compile(r"\b[0-9a-f]{40}\b", re.I)
EXPORT = re.compile(r"^\s*export\s+([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.M)
ABS_PATH = re.compile(r"(?<![\w.-])/(?:[^\s`'\"<>]+)")
IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")


class StrictLoader(yaml.SafeLoader):
    pass


def strict_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise yaml.constructor.ConstructorError(None, None, f"duplicate key: {key}", key_node.start_mark)
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, strict_mapping)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def safe_remote(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme and parsed.hostname:
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            return None
        host = parsed.hostname + (f":{parsed.port}" if parsed.port else "")
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    return value if "@" in value and ":" in value and not SENSITIVE.search(value) else None


def git_identity(root: Path) -> dict:
    def run(*args: str) -> str | None:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
        return result.stdout.strip() if result.returncode == 0 else None

    top = run("rev-parse", "--show-toplevel")
    if not top:
        return {"available": False, "git_root": None, "remote": None, "branch_or_tag": None, "head": None, "dirty_observation": None}
    return {
        "available": True,
        "git_root": str(Path(top).resolve()),
        "remote": safe_remote(run("remote", "get-url", "origin")),
        "branch_or_tag": run("branch", "--show-current") or run("describe", "--tags", "--exact-match"),
        "head": run("rev-parse", "HEAD"),
        "dirty_observation": run("status", "--short"),
    }


def load_metadata(path: Path) -> tuple[dict | None, list[str]]:
    try:
        text = path.read_text(encoding="utf-8")
        if re.search(r"(^|\s)[&*][A-Za-z0-9_-]+", text):
            raise ValueError("yaml_alias_not_allowed")
        fields = yaml.load(text, Loader=StrictLoader)
        if not isinstance(fields, dict):
            raise ValueError("metadata_not_mapping")
        diagnostics = []
        for key in ("Infer", "Train"):
            match = re.search(rf"^\s*{key}\s*:\s*([^#\n]+)", text, re.M)
            if match and match.group(1).strip() not in ("true", "false"):
                diagnostics.append(f"noncanonical_boolean:{key}")
        for key, expected in (("Name", str), ("Infer", bool), ("Train", bool)):
            if key not in fields or not isinstance(fields[key], expected):
                diagnostics.append(f"missing_or_invalid:{key}")
        return fields, diagnostics
    except (OSError, UnicodeError, yaml.YAMLError, ValueError) as error:
        return None, [f"malformed:{type(error).__name__}:{error}"]


def discover(root: Path, model: str) -> list[dict]:
    candidates = []
    for pattern in ("**/metafile.yml", "**/metafile.yaml"):
        for path in root.glob(pattern):
            fields, diagnostics = load_metadata(path)
            if fields is None:
                raw = path.read_text(encoding="utf-8", errors="replace")
                match = re.search(r"^Name:\s*([^#\n]+)", raw, re.M)
                if not match or match.group(1).strip().strip("'\"") != model:
                    continue
            elif fields.get("Name") != model:
                continue
            relative = path.relative_to(root).as_posix()
            candidates.append({
                "framework": Path(relative).parts[0] if len(Path(relative).parts) > 1 else None,
                "model_directory": Path(relative).parent.as_posix(),
                "metafile_path": relative,
                "metafile_sha256": digest(path),
                "fields": fields,
                "diagnostics": diagnostics,
            })
    return sorted(candidates, key=lambda row: (row["framework"] or "", row["model_directory"], row["metafile_path"]))


def readme_reference(root: Path, candidate: dict) -> dict:
    directory = root / candidate["model_directory"]
    path = next((directory / name for name in ("README.md", "README.MD", "readme.md") if (directory / name).is_file()), None)
    if path is None:
        return {"path": None, "sha256": None, "claims": {}, "missing": ["readme"]}
    text = path.read_text(encoding="utf-8", errors="replace")
    environment = {}
    for key, value in EXPORT.findall(text):
        environment[key] = "<redacted>" if SENSITIVE.search(key) else value.strip().strip("'\"")
    commands = []
    for block in re.findall(r"```(?:bash|sh)?\s*\n(.*?)```", text, re.S | re.I):
        command = " ".join(line.strip() for line in block.splitlines() if line.strip())
        if command:
            commands.append(redact_command(command))
    claims = {
        "component_full_shas": sorted(set(SHA.findall(text))),
        "environment": dict(sorted(environment.items())),
        "absolute_paths": sorted({path for path in ABS_PATH.findall(text) if not SENSITIVE.search(path)}),
        "commands": sorted(set(commands)),
    }
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": digest(path),
        "claims": claims,
        "missing": sorted(key for key, value in claims.items() if not value),
    }


def reference_id(document: dict) -> str:
    modelzoo = document["modelzoo"]
    payload = {
        "inputs": document["inputs"],
        "modelzoo": {key: modelzoo[key] for key in ("available", "remote", "branch_or_tag", "head")},
        "candidates": document["candidates"],
        "selection": document["selection"],
        "reference": document["reference"],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def redact_command(command: str) -> str:
    command = IPV4.sub("<redacted-host>", command)
    command = re.sub(
        r"(?i)(--api-key|--token|--password|--secret)(?:\s+|=)([^\s]+)",
        r"\1 <redacted>",
        command,
    )
    command = re.sub(
        r"(?i)(Authorization\s*:\s*(?:Bearer|Basic)\s+)[^\s\"']+",
        r"\1<redacted>",
        command,
    )
    return re.sub(
        r"(?i)\b([A-Za-z_][A-Za-z0-9_]*(?:TOKEN|KEY|SECRET|PASSWORD|CREDENTIAL|AUTH)[A-Za-z0-9_]*)=([^\s]+)",
        r"\1=<redacted>",
        command,
    )


def resolve(root: Path, model: str, framework: str | None) -> dict:
    document = {
        "schema": SCHEMA,
        "reference_id": None,
        "reference_status": None,
        "inputs": {"model_name": model, "framework_selector": framework},
        "modelzoo": {"root": str(root.resolve()), **git_identity(root)},
        "candidates": [],
        "selection": None,
        "reference": {"metafile": None, "readme": None, "claims": {}, "diagnostics": []},
        "functional_effect": "none",
    }
    if not root.is_dir():
        document["reference_status"] = "modelzoo_reference_unavailable"
        document["reference"]["diagnostics"] = ["modelzoo_root_unavailable"]
    else:
        candidates = discover(root, model)
        document["candidates"] = candidates
        selected = [row for row in candidates if framework is None or row["framework"] == framework]
        if not candidates:
            document["reference_status"] = "modelzoo_reference_unavailable"
            document["reference"]["diagnostics"] = ["exact_name_not_found"]
        elif len(selected) != 1:
            document["reference_status"] = "modelzoo_reference_ambiguous"
            document["reference"]["diagnostics"] = ["selector_did_not_resolve_unique_candidate"]
        else:
            candidate = selected[0]
            document["selection"] = {key: candidate[key] for key in ("framework", "model_directory", "metafile_path")}
            document["reference"]["metafile"] = {"path": candidate["metafile_path"], "sha256": candidate["metafile_sha256"], "fields": candidate["fields"]}
            document["reference"]["diagnostics"] = list(candidate["diagnostics"])
            readme = readme_reference(root, candidate)
            document["reference"]["readme"] = {"path": readme["path"], "sha256": readme["sha256"]}
            document["reference"]["claims"] = readme["claims"]
            document["reference"]["diagnostics"].extend(f"missing:{key}" for key in readme["missing"])
            if candidate["fields"] is None or candidate["diagnostics"]:
                document["reference_status"] = "modelzoo_reference_malformed"
            elif not document["modelzoo"]["available"] or readme["missing"] or candidate["fields"].get("Infer") is False:
                document["reference_status"] = "modelzoo_reference_incomplete"
                if not document["modelzoo"]["available"]:
                    document["reference"]["diagnostics"].append("modelzoo_git_identity_unavailable")
                if candidate["fields"].get("Infer") is False:
                    document["reference"]["diagnostics"].append("historical_modelzoo_negative_claim")
            else:
                document["reference_status"] = "modelzoo_reference_resolved"
    document["reference"]["diagnostics"] = sorted(set(document["reference"]["diagnostics"]))
    document["reference_id"] = reference_id(document)
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--framework")
    parser.add_argument("--modelzoo-root", default="/home/xuansun/ModelZoo")
    args = parser.parse_args()
    try:
        print(json.dumps(resolve(Path(args.modelzoo_root), args.model, args.framework), ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except Exception as error:
        print(json.dumps({"schema": SCHEMA, "internal_error": type(error).__name__}, sort_keys=True))
        return 70


if __name__ == "__main__":
    sys.exit(main())
