#!/usr/bin/env python3
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def run(argv, normalize_claim_boundary=False):
    process = subprocess.run(argv, capture_output=True, text=True, check=False, shell=False)
    stdout = process.stdout
    if normalize_claim_boundary:
        try:
            document = json.loads(stdout)
        except json.JSONDecodeError:
            pass
        else:
            boundary = document.get("claim_boundary")
            if isinstance(boundary, str) and "Claim Boundary:" not in boundary:
                document["claim_boundary"] = "Claim Boundary: " + boundary
                stdout = json.dumps(document, sort_keys=True)
    sys.stdout.write(stdout)
    sys.stderr.write(process.stderr)
    return process.returncode


def sealed(document):
    document["digest"] = "sha256:" + hashlib.sha256(
        json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return document


def plugin_migration(fixture):
    owner = ROOT / "skills/engineering/pytorch-dlc-plugin-migration/scripts/evaluate-plugin-migration.py"
    value = json.loads(fixture.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
        root = Path(directory)
        for field, item in value.items():
            if isinstance(item, dict) and "artifact_path" in item:
                artifact = root / f"{field}.txt"
                artifact.write_text(field, encoding="utf-8")
                item["artifact_path"] = str(artifact)
                item["artifact_id"] = "sha256:" + hashlib.sha256(field.encode()).hexdigest()
        contract = root / "contract.json"
        contract.write_text(json.dumps(value), encoding="utf-8")
        return run([sys.executable, str(owner), str(contract)], normalize_claim_boundary=True)


def report_routing(fixture):
    owner = ROOT / "skills/engineering/model-adaptation/scripts/route-model-adaptation-request.py"
    value = json.loads(fixture.read_text(encoding="utf-8"))
    report = json.dumps(
        {
            "route_feasibility": "not_verified",
            "adaptation_completion": "not_verified",
            "stable_delivery": "not_verified",
            "claim_boundary": "Claim Boundary: report-only creates no execution evidence.",
        },
        sort_keys=True,
    ).encode()
    with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
        root = Path(directory)
        artifacts = []
        for name, content in (("evidence.txt", b"evidence"), ("summary.json", report), ("attachment.json", report)):
            path = root / name
            path.write_bytes(content)
            artifacts.append({"path": str(path), "sha256": hashlib.sha256(content).hexdigest()})
        value.update(
            evidence_artifacts=artifacts[:1],
            decision_summary_artifact=artifacts[1],
            technical_attachment_artifact=artifacts[2],
        )
        contract = root / "request.json"
        contract.write_text(json.dumps(value), encoding="utf-8")
        return run([sys.executable, str(owner), str(contract)], normalize_claim_boundary=True)


def topology_selection(_fixture):
    owner = ROOT / "skills/engineering/model-adaptation/scripts/validate-vllm-cl-qualification.py"
    templates = ROOT / "tests/vllm_cl_model_adaptation/fixtures/distributed-collective"
    spec = importlib.util.spec_from_file_location("topology_owner", owner)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    document = json.loads((templates / "qualified-controlled-template.json").read_text(encoding="utf-8"))
    selection = json.loads((templates / "qualified-controlled-v2-base.json").read_text(encoding="utf-8"))
    document["schema_version"] = "vllm-cl-distributed-collective-qualification/v2"
    for route in document["qualification"]["route_inventory"]:
        route["selection"] = None
    route = document["qualification"]["route_inventory"][2]
    route.update(rank_order=[1, 0], selection=selection)
    module.refresh_selection_digests(selection, route)
    document["digest"] = module.artifact_digest(document)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", dir="/tmp/kilo") as contract:
        json.dump(document, contract)
        contract.flush()
        return run([sys.executable, str(owner), contract.name])


def contract_static(fixture):
    value = json.loads(fixture.read_text(encoding="utf-8"))
    source = (ROOT / value["source"]).read_text(encoding="utf-8")
    passed = all(term in source for term in value["required_terms"])
    print(
        json.dumps(
            {
                "terminal_state": "contract_present" if passed else "contract_missing",
                "claim_boundary": "Claim Boundary: static source structure is not executable workflow behavior.",
                "authoritative": False,
            },
            sort_keys=True,
        )
    )
    return 0 if passed else 2


def publication_not_proposed(_fixture):
    helper = ROOT / "tests/vllm_cl_main_to_main/test_publication_candidate.py"
    spec = importlib.util.spec_from_file_location("publication_candidate_test_helper", helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    case = module.PublicationCandidateAssessorTests("test_no_proposal_accepts_recorded_dirty_tested_revision")
    case.setUp()
    try:
        document = json.loads((module.FIXTURES / "not-proposed.json").read_text(encoding="utf-8"))
        now = datetime.now(timezone.utc).replace(microsecond=0)
        document.update(
            generated_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            expires_at=(now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        document["tested_revision"].update(
            base_sha=case.base_sha,
            commit_sha=case.tested_sha,
            tree_sha=module.run_git(case.tested, "rev-parse", "HEAD^{tree}"),
            worktree_clean=True,
        )
        document["digest"] = module.seal(document)
        case.handoff, case.artifacts = document, {}
        result = case.assess(candidate_root=False)
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        return result.returncode
    finally:
        case.doCleanups()


def publication_stale_lease(_fixture):
    helper = ROOT / "tests/vllm_cl_main_to_main/test_publication_candidate.py"
    spec = importlib.util.spec_from_file_location("publication_candidate_test_helper", helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    case = module.PublicationCandidateAssessorTests("test_future_gate_and_stale_or_future_remote_observation_block")
    case.setUp()
    try:
        result = case.assess(
            lambda document: document["publication_candidate"]["lease"].update(
                target_base_expected_old_sha="f" * 40
            )
        )
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        return result.returncode
    finally:
        case.doCleanups()


MODES = {
    "plugin-migration": plugin_migration,
    "report-routing": report_routing,
    "topology-selection": topology_selection,
    "contract-static": contract_static,
    "publication-not-proposed": publication_not_proposed,
    "publication-stale-lease": publication_stale_lease,
}


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in MODES:
        return 3
    return MODES[sys.argv[1]](Path(sys.argv[2]))


if __name__ == "__main__":
    raise SystemExit(main())
