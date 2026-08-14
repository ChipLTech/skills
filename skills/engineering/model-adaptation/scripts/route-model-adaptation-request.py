#!/usr/bin/env python3
import hashlib
import json
import re
import sys
from pathlib import Path


FIELDS = {"schema", "request_text", "evidence_artifacts", "evidence_state", "audience", "decision_questions", "decision_summary_artifact", "technical_attachment_artifact"}
EXECUTION_TERMS = ("适配", "运行", "build", "install", "device", "benchmark", "修改", "execute", "serve")
REPORT_TERMS = ("整理已有", "existing evidence", "形成报告", "analysis summary", "Decision Summary")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def output(state, route, resume, exit_code):
    print(json.dumps({"schema": "io.chipltech.model-adaptation-route-result/v1", "route": route, "terminal_state": state, "resume_requirements": resume, "forbidden_actions": ["build", "install", "device_execution", "benchmark", "workspace_mutation"] if route == "report_only" else [], "claim_boundary": "Report-only reorganizes existing evidence and creates no adaptation, runtime, performance, or acceptance evidence."}, sort_keys=True))
    return exit_code


def valid_artifact(item):
    if not isinstance(item, dict) or set(item) != {"path", "sha256"} or not isinstance(item["path"], str) or not isinstance(item["sha256"], str) or not SHA256.fullmatch(item["sha256"]):
        return False
    try:
        return hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest() == item["sha256"]
    except OSError:
        return False


def valid_report_artifact(item):
    if not valid_artifact(item):
        return False
    try:
        report = json.loads(Path(item["path"]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(report, dict) and set(report) == {"route_feasibility", "adaptation_completion", "stable_delivery", "claim_boundary"} and isinstance(report["claim_boundary"], str) and report["claim_boundary"].startswith("Claim Boundary:")


def main():
    try:
        value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (IndexError, OSError, json.JSONDecodeError) as error:
        return output("invalid_contract", "unknown", [str(error)], 3)
    if not isinstance(value, dict) or set(value) != FIELDS or value.get("schema") != "io.chipltech.model-adaptation-request/v1":
        return output("invalid_contract", "unknown", ["closed_world_fields"], 3)
    if not isinstance(value["request_text"], str) or not isinstance(value["audience"], str) or not isinstance(value["evidence_artifacts"], list) or not isinstance(value["decision_questions"], list) or not all(isinstance(item, str) and item for item in value["decision_questions"]):
        return output("invalid_contract", "unknown", ["field_types"], 3)
    text = value["request_text"]
    lowered = text.lower()
    if any(term in lowered for term in EXECUTION_TERMS):
        return output("execution_preflight_required", "execution", ["execution workflow inputs and authorization"], 0)
    if not any(term in text for term in REPORT_TERMS) or not value["audience"] or not value["decision_questions"]:
        return output("blocked_missing_reader_contract", "report_only", ["audience", "decision_questions", "unambiguous report request"], 2)
    if value["evidence_state"] == "conflicting":
        return output("blocked_conflicting_evidence", "report_only", ["conflict resolution evidence"], 2)
    reports = (value["decision_summary_artifact"], value["technical_attachment_artifact"])
    if value["evidence_state"] != "available" or not value["evidence_artifacts"] or not all(valid_artifact(item) for item in value["evidence_artifacts"]) or not all(valid_report_artifact(item) for item in reports):
        return output("blocked_missing_evidence", "report_only", ["digest-bound evidence, Decision Summary, and Technical Attachment artifacts"], 2)
    return output("report_complete", "report_only", [], 0)


if __name__ == "__main__":
    raise SystemExit(main())
