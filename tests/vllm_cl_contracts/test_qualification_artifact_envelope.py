import copy
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "skills/engineering/chipltech-context/scripts/qualification_artifact.py"
FIXTURES = Path(__file__).with_name("fixtures") / "qualification-artifact-envelope"


def load_module(path=MODULE, name="qualification_artifact"):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QualificationArtifactEnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.contract = load_module()
        self.document = json.loads((FIXTURES / "positive.json").read_text())
        self.document = self.contract.seal_envelope(self.document)

    def test_canonical_digest_omits_digest_and_is_independently_known(self):
        tiny = {"schema_version": "x/v1", "digest": "ignored", "value": "é"}
        expected = "sha256:" + hashlib.sha256(
            '{"schema_version":"x/v1","value":"é"}'.encode("utf-8")
        ).hexdigest()
        self.assertEqual(self.contract.canonical_digest(tiny), expected)
        tiny["digest"] = "also-ignored"
        self.assertEqual(self.contract.canonical_digest(tiny), expected)

    def test_valid_envelope_is_closed_world(self):
        fixture = json.loads((FIXTURES / "positive.json").read_text())
        self.assertEqual(self.contract.validate_envelope(fixture), [])
        self.assertEqual(self.contract.validate_envelope(self.document), [])
        mutated = copy.deepcopy(self.document)
        mutated["surprise"] = True
        self.assertEqual(
            self.contract.validate_envelope(self.contract.seal_envelope(mutated))[0],
            {"code": "unknown_field", "path": "$.surprise"},
        )
        nested = copy.deepcopy(self.document)
        nested["subject_identity"]["hardware"]["serial_number"] = "secret"
        self.assertIn(
            {"code": "unknown_field", "path": "$.subject_identity.hardware.serial_number"},
            self.contract.validate_envelope(self.contract.seal_envelope(nested)),
        )

    def test_topic_validator_must_explicitly_declare_extension_field(self):
        topic = copy.deepcopy(self.document)
        topic["qualification"] = {"route": "fixture"}
        sealed = self.contract.seal_envelope(topic)
        self.assertIn(
            {"code": "unknown_field", "path": "$.qualification"},
            self.contract.validate_envelope(sealed),
        )
        self.assertEqual(
            self.contract.validate_envelope(sealed, ("qualification",)), []
        )

    def test_model_tokenizer_and_processor_accept_revision_or_digest(self):
        document = copy.deepcopy(self.document)
        document["subject_identity"]["model"].update(
            revision="model-revision", digest=None
        )
        document["subject_identity"]["tokenizer"].update(
            revision="tokenizer-revision", digest=None
        )
        document["subject_identity"]["processor"] = {
            "revision": "processor-revision",
            "digest": None,
        }
        self.assertEqual(
            self.contract.validate_envelope(self.contract.seal_envelope(document)), []
        )

    def test_missing_identity_has_precise_deterministic_blockers(self):
        identity = copy.deepcopy(self.document["subject_identity"])
        del identity["source"]
        del identity["capability_policy"]
        self.assertEqual(
            self.contract.identity_blockers(identity),
            [
                {"status": "blocked", "code": "missing_identity", "path": "$.subject_identity.source"},
                {"status": "blocked", "code": "missing_identity", "path": "$.subject_identity.capability_policy"},
            ],
        )

    def test_blocked_envelope_may_preserve_unavailable_identity_as_null(self):
        blocked = copy.deepcopy(self.document)
        blocked["subject_identity"]["native_binary"] = None
        blocker = {
            "status": "blocked", "code": "missing_identity",
            "path": "$.subject_identity.native_binary",
        }
        blocked.update(
            status="blocked", blockers=[blocker], primary_blocker=blocker,
            resume_point="$.subject_identity.native_binary",
        )
        self.assertEqual(
            self.contract.validate_envelope(self.contract.seal_envelope(blocked)), []
        )

    def test_static_snapshot_is_explicit_and_never_acceptance_eligible(self):
        static = copy.deepcopy(self.document)
        static["subject_identity"]["source"] = {
            "kind": "static_snapshot",
            "repository": None,
            "revision": None,
            "dirty": None,
            "snapshot_digest": "sha256:" + "a" * 64,
        }
        static["evidence_class"] = "static_snapshot"
        static["claim_boundary"] = "Proves only the bytes in the source snapshot."
        self.assertEqual(self.contract.validate_envelope(self.contract.seal_envelope(static)), [])

        promoted = copy.deepcopy(static)
        promoted["evidence_class"] = "qualification"
        errors = self.contract.validate_envelope(self.contract.seal_envelope(promoted))
        self.assertIn({"code": "static_snapshot_boundary", "path": "$.evidence_class"}, errors)

        operational = copy.deepcopy(static)
        operational["authoritativeness"] = "operational"
        errors = self.contract.validate_envelope(self.contract.seal_envelope(operational))
        self.assertIn(
            {"code": "static_snapshot_boundary", "path": "$.authoritativeness"},
            errors,
        )

    def test_policy_controls_evidence_authority_and_acceptance_independently(self):
        cases = [
            ("unknown/producer", "fixture", "non_authoritative", False, "unknown_producer"),
            ("diagnosing-bugs/qualification-artifact-validator", "formal_acceptance", "non_authoritative", False, "producer_evidence_exceeded"),
            ("diagnosing-bugs/qualification-artifact-validator", "fixture", "authoritative", False, "producer_authority_exceeded"),
            ("diagnosing-bugs/qualification-artifact-validator", "fixture", "non_authoritative", True, "producer_acceptance_forbidden"),
        ]
        for producer, evidence, authority, eligible, code in cases:
            with self.subTest(code=code):
                document = copy.deepcopy(self.document)
                document.update(
                    producer=producer,
                    evidence_class=evidence,
                    authoritativeness=authority,
                    acceptance_eligible=eligible,
                )
                errors = self.contract.validate_envelope(self.contract.seal_envelope(document))
                self.assertEqual(errors[0]["code"], code)

        collector = copy.deepcopy(self.document)
        collector.update(
            schema_version="vllm-cl-live-identity/v1",
            producer="model-adaptation/live-identity-collector",
            evidence_class="operational_only",
            authoritativeness="operational",
            acceptance_eligible=False,
            collection={},
        )
        errors = self.contract.validate_envelope(
            self.contract.seal_envelope(collector), ("collection",)
        )
        self.assertIn(
            {"code": "producer_authority_exceeded", "path": "$.authoritativeness"},
            errors,
        )

    def test_blocker_aggregation_is_order_independent(self):
        blockers = [
            {"status": "blocked", "code": "missing_hardware", "path": "$.subject_identity.hardware"},
            {"status": "not_verified", "code": "missing_identity", "path": "$.subject_identity.source"},
            {"status": "failed", "code": "failed_assertion", "path": "$.results.correctness"},
        ]
        expected = ("failed", blockers[2])
        self.assertEqual(self.contract.aggregate_blockers(blockers), expected)
        self.assertEqual(self.contract.aggregate_blockers(list(reversed(blockers))), expected)

        document = copy.deepcopy(self.document)
        document.update(blockers=blockers, primary_blocker=blockers[2], status="failed")
        self.assertEqual(self.contract.validate_envelope(self.contract.seal_envelope(document)), [])

    def test_invalid_canonical_value_and_duplicate_blockers_fail_closed(self):
        invalid_float = copy.deepcopy(self.document)
        invalid_float["artifact_id"] = 1.5
        self.assertIn(
            {"code": "invalid_canonical_value", "path": "$"},
            self.contract.validate_envelope(invalid_float),
        )

        blocker = {"status": "blocked", "code": "missing_identity", "path": "$.x"}
        duplicate = copy.deepcopy(self.document)
        duplicate.update(
            blockers=[blocker, copy.deepcopy(blocker)],
            primary_blocker=blocker,
            status="blocked",
        )
        self.assertIn(
            {"code": "duplicate_blocker", "path": "$.blockers"},
            self.contract.validate_envelope(self.contract.seal_envelope(duplicate)),
        )

    def test_every_identity_class_invalidates_stale_evidence(self):
        identity = self.document["subject_identity"]
        for field in self.contract.IDENTITY_FIELDS:
            with self.subTest(field=field):
                current = copy.deepcopy(identity)
                if field == "processor":
                    current[field] = {"digest": "sha256:" + "b" * 64, "revision": None}
                elif field == "capability_policy":
                    current[field]["version"] = "v2"
                else:
                    current[field] = None
                stale = self.contract.stale_identity_blockers(identity, current)
                self.assertEqual(stale[0]["path"], f"$.subject_identity.{field}")

        missing_processor = copy.deepcopy(identity)
        del missing_processor["processor"]
        self.assertEqual(
            self.contract.stale_identity_blockers(identity, missing_processor),
            [
                {
                    "status": "not_verified",
                    "code": "stale_identity",
                    "path": "$.subject_identity.processor",
                }
            ],
        )

    def test_versioned_policy_exclusion_fails_closed(self):
        excluded = json.loads((FIXTURES / "policy-excluded-schema.json").read_text())
        excluded["subject_identity"] = copy.deepcopy(self.document["subject_identity"])
        errors = self.contract.validate_envelope(self.contract.seal_envelope(excluded))
        self.assertEqual(
            errors[0],
            {"code": "producer_schema_excluded", "path": "$.schema_version"},
        )

    def test_distributed_collective_producers_allow_exact_v1_and_v2(self):
        for producer in (
            "model-adaptation/distributed-collective-fixture",
            "model-adaptation/dlccl-qualification-runner",
            "model-adaptation/qualification-runner",
        ):
            schemas = self.contract.PRODUCER_POLICY["producers"][producer]["schemas"]
            self.assertIn("vllm-cl-distributed-collective-qualification/v1", schemas)
            self.assertIn("vllm-cl-distributed-collective-qualification/v2", schemas)

    def test_topic_v2_requires_an_exact_consumer_allowlist(self):
        document = copy.deepcopy(self.document)
        document["schema_version"] = (
            "vllm-cl-distributed-collective-qualification/v2"
        )
        document["producer"] = "model-adaptation/distributed-collective-fixture"
        document["evidence_class"] = "fixture"
        document["authoritativeness"] = "non_authoritative"
        document["acceptance_eligible"] = False
        sealed = self.contract.seal_envelope(document)

        self.assertIn(
            {"code": "unsupported_schema_version", "path": "$.schema_version"},
            self.contract.validate_envelope(sealed),
        )
        self.assertEqual(
            self.contract.validate_envelope(
                sealed,
                accepted_schema_versions=(
                    "vllm-cl-distributed-collective-qualification/v2",
                ),
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
