import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "engineering" / "diagnosing-bugs" / "scripts" / "validate-dlc-profile-artifacts.py"
FIXED_TRACE = Path("/work/tmp/13/syn_trace_140250241746752.json")
FIXED_DIGEST = "sha256:14a236468794c6faca0f85453693b99c1a2b30fbe8bd9e0824276d4d0138e48e"
FIXTURE_TRACE = b'{"traceEvents":[{"name":"x","ph":"X","pid":1,"tid":"track","ts":0,"dur":1,"args":{}}]}'


def load_script():
    spec = importlib.util.spec_from_file_location("profile_validator_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_script()


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def identity():
    d = "sha256:" + "1" * 64
    return {
        "source": {"kind": "git", "repository": "repo", "revision": "2" * 40, "dirty": False, "snapshot_digest": None},
        "installed_package": {"name": "torch", "version": "1", "path": "/pkg", "digest": d},
        "native_binary": {"digest": d},
        "image": {"image_id": "image", "digest": d},
        "runtime": {"name": "DLC Runtime", "version": "1", "digest": d},
        "driver": {"name": "dlc-thunk", "version": "1", "digest": d},
        "toolchain": {"name": "toolchain", "version": "1", "digest": d},
        "model": {"model_id": "model", "revision": "rev", "digest": None},
        "tokenizer": {"revision": "rev", "digest": None},
        "processor": None,
        "workload": {"digest": d},
        "hardware": {"generation": "DLC Chip", "topology_digest": d},
        "capability_policy": {"policy_id": "profile", "version": "v1", "digest": d},
    }


def manifest(trace_path, trace_digest):
    d = "sha256:" + "3" * 64
    row = {
        "schema_version": "dlc-profile-evidence-manifest/v1",
        "artifact_id": "profile-1",
        "producer": "diagnosing-bugs/profile-artifact-validator",
        "producer_version": "1.0.0",
        "created_at": "2026-08-08T00:00:00Z",
        "subject_identity": identity(),
        "input_artifact_digests": [trace_digest],
        "evidence_class": "diagnostic",
        "authoritativeness": "non_authoritative",
        "acceptance_eligible": False,
        "status": "passed",
        "blockers": [],
        "primary_blocker": None,
        "resume_point": None,
        "unverified_scope": ["request", "phase", "rank", "device", "formal_benchmark"],
        "trace": {"path": str(trace_path), "digest": trace_digest, "schema": "chrome-trace-event-json/v1", "time_unit": "us"},
        "acquisition": {"entry": "existing_trace_artifact", "config_digest": d, "evidence_sources": ["trace_file_bytes"]},
        "expected_localization_scopes": {"trace_track": True, "request": False, "phase": False, "rank": False, "device": False},
        "semantic_producer": None,
        "diagnostic_epoch": "diagnostic",
        "profiler_perturbation": ["trace_instrumentation"],
        "hardware_counters": {"state": "not_verified", "artifact_path": None, "artifact_digest": None},
        "smi_reference": None,
        "cleanup_reference": None,
        "claim_boundary": "diagnostic localization only",
    }
    return VALIDATOR._CONTRACT.seal_envelope(row)


def semantic_artifact(row, scopes, request_event_bindings=None):
    artifact = {
        "schema_version": "dlc-profile-semantic-artifact/v1",
        "artifact_id": "semantic-1",
        "producer": "diagnosing-bugs/profile-semantic-producer",
        "producer_version": "1.0.0",
        "created_at": row["created_at"],
        "subject_identity": copy.deepcopy(row["subject_identity"]),
        "input_artifact_digests": [row["trace"]["digest"]],
        "evidence_class": "diagnostic",
        "authoritativeness": "non_authoritative",
        "acceptance_eligible": False,
        "status": "passed",
        "blockers": [],
        "primary_blocker": None,
        "resume_point": None,
        "claim_boundary": "semantic localization only",
        "unverified_scope": [scope for scope in VALIDATOR.SCOPES[1:] if scope not in scopes],
        "trace_digest": row["trace"]["digest"],
        "workload_digest": row["subject_identity"]["workload"]["digest"],
        "diagnostic_epoch": row["diagnostic_epoch"],
        "localization_scopes": list(scopes),
        "request_event_bindings": request_event_bindings or ([{
            "request_id": "request-1", "name": "x", "pid": 1,
            "tid": "track", "ts": 0, "dur": 1,
        }] if "request" in scopes else []),
    }
    return VALIDATOR._CONTRACT.seal_envelope(artifact)


class ProfileArtifactTests(unittest.TestCase):
    def test_fixed_trace_byte_identity_and_r1(self):
        row = manifest(FIXED_TRACE, FIXED_DIGEST)
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            manifest_path = Path(directory) / "manifest.json"
            manifest_path.write_text(json.dumps(row), encoding="utf-8")
            result = VALIDATOR.validate_profile(row, manifest_path)
        if FIXED_TRACE.is_file():
            self.assertEqual(digest(FIXED_TRACE), FIXED_DIGEST)
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["trace_syntax_valid"], "passed")
            self.assertEqual(result["trace_byte_identity_valid"], "passed")
            self.assertEqual(result["valid_for_trace_track_localization"], "passed")
            self.assertEqual(result["valid_for_request_localization"], "not_verified")
        else:
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["primary_blocker"]["code"], "blocked_missing_profile_artifact")

    def test_missing_external_artifact_reports_stable_blocker(self):
        row = manifest("/work/tmp/13/absent-profile.json", FIXED_DIGEST)
        result = VALIDATOR.validate_profile(row, Path("/tmp/kilo/manifest.json"))
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["primary_blocker"]["code"], "blocked_missing_profile_artifact")
        self.assertEqual(result["resume_point"], "supply_or_reseal_profile_artifact")

    def test_hash_mismatch_separates_syntax_from_byte_identity(self):
        if not FIXED_TRACE.is_file():
            self.skipTest("fixed profile artifact absent")
        row = manifest(FIXED_TRACE, "sha256:" + "0" * 64)
        result = VALIDATOR.validate_profile(row, Path("/tmp/kilo/manifest.json"))
        self.assertEqual(result["trace_syntax_valid"], "passed")
        self.assertEqual(result["trace_byte_identity_valid"], "failed")
        self.assertEqual(result["valid_for_trace_track_localization"], "failed")
        self.assertIn("trace_digest_mismatch", [item["code"] for item in result["blockers"]])

    def test_manifest_is_closed_world(self):
        row = manifest(FIXED_TRACE, FIXED_DIGEST)
        row["surprise"] = True
        problems = VALIDATOR.validate_manifest_shape(row)
        self.assertIn({"status": "failed", "code": "unknown_field", "path": "$.surprise"}, problems)

    def test_float_manifest_returns_machine_failure_not_traceback(self):
        row = manifest(FIXED_TRACE, FIXED_DIGEST)
        row["profiler_perturbation"] = [1.5]
        result = VALIDATOR.validate_profile(row, Path("/tmp/kilo/manifest.json"))
        self.assertEqual(result["status"], "failed")
        self.assertIn("invalid_canonical_value", [item["code"] for item in result["blockers"]])

    def test_manifest_and_result_interoperate_with_shared_envelope(self):
        row = manifest(FIXED_TRACE, FIXED_DIGEST)
        self.assertEqual(VALIDATOR._CONTRACT.validate_envelope(row, VALIDATOR.MANIFEST_EXTENSION_FIELDS), [])
        result = VALIDATOR.validate_profile(row, Path("/tmp/kilo/manifest.json"))
        self.assertEqual(VALIDATOR._CONTRACT.validate_envelope(result, VALIDATOR.RESULT_EXTENSION_FIELDS), [])

    def test_malformed_trace_is_syntax_failure(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            trace = Path(directory) / "trace.json"
            trace.write_text("{", encoding="utf-8")
            row = manifest(trace, digest(trace))
            result = VALIDATOR.validate_profile(row, Path(directory) / "manifest.json")
        self.assertEqual(result["trace_syntax_valid"], "failed")
        self.assertEqual(result["trace_byte_identity_valid"], "passed")

    def test_success_stub_and_formal_benchmark_fail_closed(self):
        row = manifest(FIXED_TRACE, FIXED_DIGEST)
        row["acquisition"]["evidence_sources"] = ["profiler_start_success"]
        row["diagnostic_epoch"] = "formal_baseline"
        codes = [item["code"] for item in VALIDATOR.validate_manifest_shape(row)]
        self.assertIn("unsupported_success_stub_not_evidence", codes)
        self.assertIn("diagnostic_cannot_be_formal_benchmark", codes)

    def test_claimed_scope_without_semantic_producer_fails_only_scope(self):
        if not FIXED_TRACE.is_file():
            self.skipTest("fixed profile artifact absent")
        row = manifest(FIXED_TRACE, FIXED_DIGEST)
        row["expected_localization_scopes"]["request"] = True
        result = VALIDATOR.validate_profile(row, Path("/tmp/kilo/manifest.json"))
        self.assertEqual(result["trace_syntax_valid"], "passed")
        self.assertEqual(result["valid_for_trace_track_localization"], "passed")
        self.assertEqual(result["valid_for_request_localization"], "failed")

    def test_semantic_scopes_come_only_from_validated_companion_contents(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            trace = Path(directory) / "trace.json"
            trace.write_bytes(FIXTURE_TRACE)
            row = manifest(trace, digest(trace))
            companion = semantic_artifact(row, ["request"])
            semantic_path = Path(directory) / "semantic.json"
            semantic_path.write_text(json.dumps(companion), encoding="utf-8")
            row["semantic_producer"] = {
                "producer": companion["producer"],
                "artifact_path": str(semantic_path),
                "artifact_digest": digest(semantic_path),
            }
            row["input_artifact_digests"].append(row["semantic_producer"]["artifact_digest"])
            row["expected_localization_scopes"]["request"] = True
            row = VALIDATOR._CONTRACT.seal_envelope(row)
            result = VALIDATOR.validate_profile(row, Path(directory) / "manifest.json")
            self.assertEqual(result["valid_for_request_localization"], "passed")

            arbitrary = {"scopes": ["request"]}
            semantic_path.write_text(json.dumps(arbitrary), encoding="utf-8")
            row["semantic_producer"]["artifact_digest"] = digest(semantic_path)
            row["input_artifact_digests"][1] = row["semantic_producer"]["artifact_digest"]
            row = VALIDATOR._CONTRACT.seal_envelope(row)
            rejected = VALIDATOR.validate_profile(row, Path(directory) / "manifest.json")
            self.assertEqual(rejected["valid_for_request_localization"], "failed")
            self.assertIn("invalid_semantic_artifact", [item["code"] for item in rejected["blockers"]])

    def test_semantic_companion_rejects_wrong_trace_workload_identity_and_epoch(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            trace = Path(directory) / "trace.json"
            trace.write_bytes(FIXTURE_TRACE)
            row = manifest(trace, digest(trace))
            for field in ("trace_digest", "workload_digest", "subject_identity", "diagnostic_epoch"):
                with self.subTest(field=field):
                    companion = semantic_artifact(row, ["request"])
                    if field == "subject_identity":
                        companion[field]["runtime"]["version"] = "other"
                    else:
                        companion[field] = "diagnostic-other" if field == "diagnostic_epoch" else "sha256:" + "9" * 64
                    companion = VALIDATOR._CONTRACT.seal_envelope(companion)
                    semantic_path = Path(directory) / "semantic.json"
                    semantic_path.write_text(json.dumps(companion), encoding="utf-8")
                    candidate = copy.deepcopy(row)
                    candidate["semantic_producer"] = {"producer": companion["producer"], "artifact_path": str(semantic_path), "artifact_digest": digest(semantic_path)}
                    candidate["input_artifact_digests"].append(candidate["semantic_producer"]["artifact_digest"])
                    candidate["expected_localization_scopes"]["request"] = True
                    candidate = VALIDATOR._CONTRACT.seal_envelope(candidate)
                    result = VALIDATOR.validate_profile(candidate, Path(directory) / "manifest.json")
                    self.assertEqual(result["valid_for_request_localization"], "failed")
                    self.assertIn("semantic_binding_mismatch", [item["code"] for item in result["blockers"]])

    def test_v1_semantic_artifact_cannot_claim_phase_rank_or_device(self):
        row = manifest("/tmp/kilo/missing.json", "sha256:" + "0" * 64)
        for scope in ("phase", "rank", "device"):
            companion = semantic_artifact(row, [scope])
            problems, scopes = VALIDATOR._validate_semantic_artifact(
                companion, row, companion["producer"]
            )
            self.assertEqual(scopes, ())
            self.assertIn("invalid_semantic_artifact", [item["code"] for item in problems])

    def test_trace_complete_event_rejects_bool_negative_and_null_track_values(self):
        base = {"name": "x", "ph": "X", "pid": 1, "tid": "track", "ts": 0, "dur": 1, "args": {}}
        for field, value in (("ts", True), ("ts", -1), ("dur", False), ("dur", -1), ("pid", None), ("pid", True), ("tid", None), ("tid", False)):
            with self.subTest(field=field, value=value):
                event = copy.deepcopy(base)
                event[field] = value
                problems, complete = VALIDATOR.validate_trace_document({"traceEvents": [event]})
                self.assertEqual(complete, [])
                self.assertTrue(problems)

    def test_missing_generated_contract_is_one_isolated_failure(self):
        row = manifest(FIXED_TRACE, FIXED_DIGEST)
        contract = VALIDATOR._CONTRACT
        try:
            VALIDATOR._CONTRACT = None
            self.assertEqual(
                VALIDATOR.validate_manifest_shape(row),
                [{"status": "blocked", "code": "missing_generated_contract", "path": "$._generated_contracts.qualification_artifact"}],
            )
        finally:
            VALIDATOR._CONTRACT = contract

    def test_stale_identity_invalidates_old_result(self):
        if not FIXED_TRACE.is_file():
            self.skipTest("fixed profile artifact absent")
        row = manifest(FIXED_TRACE, FIXED_DIGEST)
        current = copy.deepcopy(row["subject_identity"])
        current["workload"] = {"digest": "sha256:" + "9" * 64}
        result = VALIDATOR.validate_profile(row, Path("/tmp/kilo/manifest.json"), current)
        stale = [item for item in result["blockers"] if item["code"] == "stale_identity"]
        self.assertEqual(stale, [{"status": "not_verified", "code": "stale_identity", "path": "$.subject_identity.workload"}])
        self.assertEqual(result["status"], "not_verified")


if __name__ == "__main__":
    unittest.main()
