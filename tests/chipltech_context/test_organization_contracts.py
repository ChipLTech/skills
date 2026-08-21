import copy
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "skills/engineering/chipltech-context/scripts/organization_contracts.py"
QUALIFICATION_MODULE = ROOT / "skills/engineering/chipltech-context/scripts/qualification_artifact.py"
FIXTURES = Path(__file__).with_name("fixtures") / "organization-contracts"
ENVELOPE_FIXTURE = ROOT / "tests/vllm_cl_contracts/fixtures/qualification-artifact-envelope/positive.json"
CONTEXT_TARGET = ROOT / "skills/engineering/chipltech-context/contracts/qualification-artifact-envelope-v1.schema.json"


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OrganizationContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = load_module(MODULE, "organization_contracts")
        self.qualification = load_module(QUALIFICATION_MODULE, "qualification_artifact_test")
        self.evidence = self.qualification.seal_envelope(
            json.loads(ENVELOPE_FIXTURE.read_text(encoding="utf-8"))
        )
        self.context_target = CONTEXT_TARGET.read_bytes()
        self.context_target_digest = "sha256:" + hashlib.sha256(self.context_target).hexdigest()
        self.context = self._fixture("context-reference-package.json")
        self.context["references"][0]["digest"] = self.context_target_digest
        self.context = self.contract.seal_document(self.context)
        self.return_document = self._fixture("agent-evidence-return.json")
        reference = self._reference(self.evidence)
        self.return_document["evidence_references"] = [reference]
        self.return_document["claims"][0]["evidence_reference_digests"] = [
            reference["digest"]
        ]
        self.return_document = self.contract.seal_document(self.return_document)
        self.handoff = self._fixture("engineering-handoff.json")
        self.handoff["fact_baseline_references"] = [reference]
        self.handoff["evidence_return_references"] = [
            self._reference(self.return_document)
        ]
        self.handoff["context_package_reference"] = self._reference(self.context)
        self.handoff = self.contract.seal_document(self.handoff)
        self.brief = self._fixture("team-task-brief.json")
        self.brief["context_package_reference"] = self._reference(self.context)
        self.brief = self.contract.seal_document(self.brief)
        self.artifacts = {
            document["digest"]: document
            for document in (self.evidence, self.context, self.return_document)
        }
        self.artifacts[self.context_target_digest] = self.context_target

    def _fixture(self, name):
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    @staticmethod
    def _reference(document):
        return {
            "artifact_id": document.get("artifact_id")
            or document.get("return_id")
            or document.get("package_id"),
            "schema_version": document["schema_version"],
            "uri": "artifact://" + (
                document.get("artifact_id")
                or document.get("return_id")
                or document.get("package_id")
            ),
            "digest": document["digest"],
        }

    def test_canonical_digest_is_known_and_omits_only_top_level_digest(self):
        tiny = {"schema_version": "agent-evidence-return/v1", "value": "é", "digest": "ignored"}
        expected = "sha256:" + hashlib.sha256(
            '{"schema_version":"agent-evidence-return/v1","value":"é"}'.encode("utf-8")
        ).hexdigest()
        self.assertEqual(self.contract.canonical_digest(tiny), expected)

    def test_four_positive_contracts_are_closed_world_and_reference_closed(self):
        for document in (self.return_document, self.context, self.handoff, self.brief):
            with self.subTest(schema=document["schema_version"]):
                schema_path = ROOT / "skills/engineering/chipltech-context/contracts" / (
                    document["schema_version"].split("/")[0] + "-v1.schema.json"
                )
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
                self.assertEqual(
                    list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(document)),
                    [],
                )
                self.assertEqual(
                    self.contract.validate_document(document, self.artifacts), []
                )
                unknown = copy.deepcopy(document)
                unknown["surprise"] = True
                unknown = self.contract.seal_document(unknown)
                self.assertIn(
                    {"code": "unknown_field", "path": "$.surprise"},
                    self.contract.validate_document(unknown, self.artifacts),
                )

    def test_claim_boundary_literal_prefix_and_semantics_are_required(self):
        for document in (self.return_document, self.context, self.handoff, self.brief):
            with self.subTest(schema=document["schema_version"]):
                invalid = copy.deepcopy(document)
                invalid["claim_boundary"] = "Does not establish runtime Evidence."
                invalid = self.contract.seal_document(invalid)
                self.assertIn(
                    {"code": "invalid_claim_boundary", "path": "$.claim_boundary"},
                    self.contract.validate_document(invalid, self.artifacts),
                )

    def test_context_timestamps_require_valid_utc_z_in_schema_and_validator(self):
        schema = json.loads(
            (ROOT / "skills/engineering/chipltech-context/contracts/context-reference-package-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        for timestamp in ("2026-08-21T08:00:00+00:00", "2026-02-30T08:00:00Z"):
            with self.subTest(timestamp=timestamp):
                invalid = copy.deepcopy(self.context)
                invalid["created_at"] = timestamp
                invalid = self.contract.seal_document(invalid)
                if not timestamp.endswith("Z"):
                    self.assertTrue(list(validator.iter_errors(invalid)))
                self.assertIn(
                    {"code": "invalid_value", "path": "$.created_at"},
                    self.contract.validate_document(invalid, self.artifacts),
                )

    def test_claims_must_close_over_declared_evidence_references(self):
        document = copy.deepcopy(self.return_document)
        document["claims"][0]["evidence_reference_digests"] = ["sha256:" + "f" * 64]
        errors = self.contract.validate_document(
            self.contract.seal_document(document), self.artifacts
        )
        self.assertIn(
            {
                "code": "unclosed_claim_evidence_reference",
                "path": "$.claims[0].evidence_reference_digests[0]",
            },
            errors,
        )

    def test_handoff_requires_evidence_return_and_context_reference_closure(self):
        document = copy.deepcopy(self.handoff)
        document["evidence_return_references"] = []
        document["context_package_reference"]["digest"] = "sha256:" + "f" * 64
        errors = self.contract.validate_document(
            self.contract.seal_document(document), self.artifacts
        )
        self.assertIn(
            {"code": "missing_required_reference", "path": "$.evidence_return_references"},
            errors,
        )
        self.assertIn(
            {"code": "unresolved_reference", "path": "$.context_package_reference"},
            errors,
        )

    def test_brief_acceptance_criteria_require_evidence_class_and_schema(self):
        document = copy.deepcopy(self.brief)
        del document["acceptance_criteria"][0]["required_schema_version"]
        errors = self.contract.validate_document(
            self.contract.seal_document(document), self.artifacts
        )
        self.assertIn(
            {
                "code": "missing_required_field",
                "path": "$.acceptance_criteria[0].required_schema_version",
            },
            errors,
        )

    def test_assignment_resume_and_blocker_rules_fail_closed(self):
        document = copy.deepcopy(self.return_document)
        document["assignment_state"] = "blocked"
        errors = self.contract.validate_document(
            self.contract.seal_document(document), self.artifacts
        )
        self.assertIn({"code": "invalid_resume_point", "path": "$.resume_point"}, errors)
        self.assertIn(
            {"code": "missing_required_reference", "path": "$.blocker_reference"},
            errors,
        )

        passed_with_resume = copy.deepcopy(self.return_document)
        passed_with_resume["resume_point"] = "retry"
        self.assertIn(
            {"code": "invalid_resume_point", "path": "$.resume_point"},
            self.contract.validate_document(
                self.contract.seal_document(passed_with_resume), self.artifacts
            ),
        )

    def test_reference_content_and_stale_digest_are_rejected(self):
        stale_artifacts = dict(self.artifacts)
        stale = copy.deepcopy(self.evidence)
        stale["claim_boundary"] = "Changed after sealing."
        stale_artifacts[self.evidence["digest"]] = stale
        errors = self.contract.validate_document(self.return_document, stale_artifacts)
        self.assertIn(
            {"code": "stale_reference_digest", "path": "$.evidence_references[0]"},
            errors,
        )

        mismatched = copy.deepcopy(self.evidence)
        mismatched["artifact_id"] = "other-artifact"
        mismatched = self.qualification.seal_envelope(mismatched)
        artifacts = dict(self.artifacts)
        artifacts[self.evidence["digest"]] = mismatched
        errors = self.contract.validate_document(self.return_document, artifacts)
        self.assertIn(
            {"code": "reference_identity_mismatch", "path": "$.evidence_references[0]"},
            errors,
        )

    def test_raw_bytes_are_only_context_package_document_targets(self):
        raw = b"ordinary context document"
        digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        reference = {
            "artifact_id": "raw-document",
            "schema_version": "plain-document/v1",
            "uri": "file:///document.md",
            "digest": digest,
        }
        context = copy.deepcopy(self.context)
        context["references"][0].update(
            reference_id="raw-document",
            kind="runbook",
            uri=reference["uri"],
            digest=digest,
        )
        context = self.contract.seal_document(context)
        self.assertEqual(self.contract.validate_document(context, {digest: raw}), [])

        evidence_return = copy.deepcopy(self.return_document)
        evidence_return["evidence_references"] = [reference]
        evidence_return["claims"][0]["evidence_reference_digests"] = [digest]
        errors = self.contract.validate_document(
            self.contract.seal_document(evidence_return), {digest: raw}
        )
        self.assertIn(
            {"code": "invalid_reference_target", "path": "$.evidence_references[0]"},
            errors,
        )

        handoff = copy.deepcopy(self.handoff)
        handoff["fact_baseline_references"] = [reference]
        errors = self.contract.validate_document(
            self.contract.seal_document(handoff), {**self.artifacts, digest: raw}
        )
        self.assertIn(
            {"code": "invalid_reference_target", "path": "$.fact_baseline_references[0]"},
            errors,
        )

    def test_evidence_references_require_mappings(self):
        document = copy.deepcopy(self.return_document)
        document["evidence_references"] = [self.evidence["digest"]]
        document["claims"][0]["evidence_reference_digests"] = [self.evidence["digest"]]
        errors = self.contract.validate_document(
            self.contract.seal_document(document), self.artifacts
        )
        self.assertIn(
            {"code": "invalid_type", "path": "$.evidence_references[0]"}, errors
        )

    def test_qualification_validator_exceptions_normalize_to_invalid_artifact(self):
        class BrokenQualification:
            @staticmethod
            def canonical_digest(document):
                return document["digest"]

            @staticmethod
            def validate_envelope(document):
                raise RuntimeError("malformed extension")

        original = self.contract._qualification_module
        self.contract._qualification_module = lambda: BrokenQualification
        try:
            errors = self.contract.validate_document(
                self.return_document, self.artifacts
            )
        finally:
            self.contract._qualification_module = original
        self.assertIn(
            {"code": "invalid_evidence_artifact", "path": "$.evidence_references[0]"},
            errors,
        )

    def test_fixture_mode_reuses_envelope_authority_ceiling(self):
        promoted = copy.deepcopy(self.evidence)
        promoted.update(
            producer="modelzoo-image-validation/formal-qualification-runner",
            schema_version="vllm-cl-model-precision-qualification/v1",
            evidence_class="formal_acceptance",
            authoritativeness="authoritative",
            acceptance_eligible=True,
        )
        promoted = self.qualification.seal_envelope(promoted)
        document = copy.deepcopy(self.return_document)
        document["evidence_references"] = [self._reference(promoted)]
        document["claims"][0]["evidence_reference_digests"] = [promoted["digest"]]
        document = self.contract.seal_document(document)
        errors = self.contract.validate_document(
            document, {promoted["digest"]: promoted}, fixture_mode=True
        )
        self.assertIn(
            {"code": "fixture_authority_ceiling", "path": "$.evidence_references[0]"},
            errors,
        )

    def test_optional_ledger_profile_uses_real_resumable_multi_round_scenario(self):
        self.assertEqual(
            self.contract.OPTIONAL_LEDGER_PROFILE,
            {
                "profile_id": "task-plan-round-ledger/v1",
                "required_characteristics": (
                    "multiple_candidates", "multiple_rounds", "resumable", "real_scenario"
                ),
            },
        )
        self.assertEqual(
            self.contract.validate_ledger_profile_applicability(
                {
                    "multiple_candidates": True,
                    "multiple_rounds": True,
                    "resumable": True,
                    "real_scenario": True,
                },
                ("model-adaptation",),
            ),
            [],
        )

    def test_yaml_json_shaped_wrong_types_fail_without_exceptions(self):
        invalid = copy.deepcopy(self.return_document)
        invalid["schema_version"] = ["agent-evidence-return/v1"]
        self.assertEqual(
            self.contract.validate_document(invalid),
            [{"code": "unsupported_schema_version", "path": "$.schema_version"}],
        )
        invalid = copy.deepcopy(self.return_document)
        invalid["changed_artifacts"] = [["not", "a", "string"]]
        errors = self.contract.validate_document(self.contract.seal_document(invalid), self.artifacts)
        self.assertIn({"code": "invalid_value", "path": "$.changed_artifacts"}, errors)
        invalid = copy.deepcopy(self.return_document)
        invalid["evidence_references"] = [b"raw"]
        errors = self.contract.validate_document(invalid, {"bad": ["shape"]})
        self.assertIn({"code": "invalid_type", "path": "$.evidence_references[0]"}, errors)


if __name__ == "__main__":
    unittest.main()
