import json
from pathlib import Path


MANIFEST_FIELDS = {"schema", "fixture_root", "cases"}
CASE_FIELDS = {
    "id",
    "workflow",
    "quality_kind",
    "fixture",
    "adapter",
    "expected_exit_codes",
    "assertions",
    "fixture_authority",
    "forbidden_actions",
}
ASSERTION_FIELDS = {"path", "op", "value"}
ASSERTION_OPS = {"equals", "contains", "starts_with"}
QUALITY_KINDS = {"behavior", "contract_static"}
ADAPTERS = {
    "pd-gates",
    "plugin-migration",
    "report-routing",
    "delivery-summary",
    "topology-selection",
    "contract-static",
    "publication-not-proposed",
    "publication-stale-lease",
    "test-fixture-owner",
}


class ManifestError(ValueError):
    pass


def contained_path(root, relative):
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ManifestError("fixture_containment")
    resolved_root = root.resolve()
    resolved = (resolved_root / relative).resolve()
    if not resolved.is_relative_to(resolved_root) or not resolved.is_file():
        raise ManifestError("fixture_containment")
    return resolved


def load_manifest(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ManifestError("manifest_json") from error
    if not isinstance(value, dict) or set(value) != MANIFEST_FIELDS:
        raise ManifestError("closed_world_manifest")
    if not isinstance(value["schema"], str) or value["schema"] != "workflow-behavior-manifest/v1":
        raise ManifestError("schema")
    if not isinstance(value["fixture_root"], str) or Path(value["fixture_root"]).is_absolute():
        raise ManifestError("fixture_containment")
    fixture_root = (path.parent / value["fixture_root"]).resolve()
    if not fixture_root.is_relative_to(path.parent.resolve()) or not fixture_root.is_dir():
        raise ManifestError("fixture_containment")
    if not isinstance(value["cases"], list) or not value["cases"]:
        raise ManifestError("cases")
    identifiers = set()
    for case in value["cases"]:
        validate_case(case, fixture_root, identifiers)
    return value, fixture_root


def validate_case(case, fixture_root, identifiers):
    if not isinstance(case, dict) or set(case) != CASE_FIELDS:
        raise ManifestError("closed_world_case")
    if not isinstance(case["id"], str) or not case["id"] or case["id"] in identifiers:
        raise ManifestError("case_id")
    identifiers.add(case["id"])
    if not isinstance(case["workflow"], str) or not case["workflow"]:
        raise ManifestError("workflow")
    if not isinstance(case["quality_kind"], str) or case["quality_kind"] not in QUALITY_KINDS:
        raise ManifestError("quality_kind")
    contained_path(fixture_root, case["fixture"])
    if not isinstance(case["adapter"], str) or case["adapter"] not in ADAPTERS:
        raise ManifestError("adapter_allowlist")
    exits = case["expected_exit_codes"]
    if not isinstance(exits, list) or not exits or not all(type(item) is int and 0 <= item <= 255 for item in exits):
        raise ManifestError("expected_exit_codes")
    if len(exits) != len(set(exits)):
        raise ManifestError("expected_exit_codes")
    assertions = case["assertions"]
    if not isinstance(assertions, list) or not assertions:
        raise ManifestError("assertions")
    for assertion in assertions:
        if not isinstance(assertion, dict) or set(assertion) != ASSERTION_FIELDS:
            raise ManifestError("closed_world_assertion")
        if (
            not isinstance(assertion["path"], str)
            or not assertion["path"].startswith("$.")
            or not isinstance(assertion["op"], str)
            or assertion["op"] not in ASSERTION_OPS
        ):
            raise ManifestError("assertion")
        if assertion["op"] == "starts_with" and not isinstance(assertion["value"], str):
            raise ManifestError("assertion")
    if case["fixture_authority"] != "fixture_only":
        raise ManifestError("fixture_authority")
    forbidden = case["forbidden_actions"]
    if not isinstance(forbidden, list) or not forbidden or not all(isinstance(item, str) and item for item in forbidden):
        raise ManifestError("forbidden_actions")
    if len(forbidden) != len(set(forbidden)):
        raise ManifestError("forbidden_actions")


def output(state, problems=None, **fields):
    return {
        "schema": "workflow-behavior-run-result/v1",
        "terminal_state": state,
        "problems": problems or [],
        "authoritative": False,
        "runtime_acceptance": False,
        "claim_boundary": (
            "Claim Boundary: behavior fixtures verify software contracts only; this does not establish "
            "authoritative runtime, publication, topology, migration, PD, or delivery evidence."
        ),
        **fields,
    }
