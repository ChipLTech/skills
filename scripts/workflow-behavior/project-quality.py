#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def main():
    try:
        run = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (IndexError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"schema": "workflow-behavior-quality-view/v1", "terminal_state": "invalid_run", "problems": [str(error)]}, sort_keys=True))
        return 3
    if not isinstance(run, dict) or run.get("schema") != "workflow-behavior-run-result/v1" or not isinstance(run.get("cases"), list):
        print(json.dumps({"schema": "workflow-behavior-quality-view/v1", "terminal_state": "invalid_run", "problems": ["run_contract"]}, sort_keys=True))
        return 3
    projection = {
        "schema": "workflow-behavior-quality-view/v1",
        "terminal_state": "projected",
        "behavior": [],
        "contract_static": [],
        "fixture_authority": "never_authoritative",
        "claims": ["software_contract_observation", "claim_boundary_preservation"],
        "claim_boundary": "Claim Boundary: quality projection does not establish runtime acceptance or fixture authority.",
    }
    for case in run["cases"]:
        row = {
            "workflow": case["workflow"],
            "state": case.get("owner_terminal_state") or case["terminal_state"],
            "reason": case.get("owner_reason"),
            "dimensions": case.get("owner_dimensions", {}),
            "blocker": case.get("owner_blocker"),
            "resume_point": case.get("owner_resume_point"),
            "claim_boundary_preserved": case["claim_boundary_preserved"],
            "fixture_authority": "fixture_only",
        }
        if case["quality_kind"] == "behavior":
            observed = [action for action in case["forbidden_actions"] if action == "workspace_mutation"]
            not_reported = [action for action in case["forbidden_actions"] if action != "workspace_mutation"]
            row.update(
                forbidden_action_preserved=False,
                quality={"observed": observed, "not_reported": not_reported},
            )
        projection[case["quality_kind"]].append(row)
    print(json.dumps(projection, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
