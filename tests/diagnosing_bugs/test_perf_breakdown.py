import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from test_profile_artifacts import FIXED_DIGEST, FIXED_TRACE, manifest, semantic_artifact


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "engineering" / "diagnosing-bugs" / "scripts" / "analyze-dlc-profile.py"
FIXTURE = Path(__file__).with_name("fixtures") / "perf-breakdown" / "nested-overlap.json"


def load_script():
    spec = importlib.util.spec_from_file_location("profile_analyzer_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


ANALYZER = load_script()


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class PerfBreakdownTests(unittest.TestCase):
    def test_nested_overlap_uses_non_overlapping_coverage(self):
        row = manifest(FIXTURE, digest(FIXTURE))
        result = ANALYZER.analyze(row, Path("/tmp/kilo/manifest.json"), "parent")
        self.assertEqual(result["status"], "passed")
        self.assertEqual([item["name"] for item in result["components"]], ["child-a", "child-b"])
        self.assertEqual(result["non_overlapping_coverage"]["duration"]["trace_units"], 70)
        self.assertEqual(result["non_overlapping_coverage"]["basis_points_of_parent"], 7000)
        self.assertEqual(result["overlap"]["duration"]["trace_units"], 20)
        self.assertEqual(result["residual"]["duration"]["trace_units"], 30)
        self.assertEqual(result["residual"]["duration"]["nanoseconds"], 30000)
        self.assertEqual(result["unmatched_intervals"], [
            {"start_trace_units": 0, "end_trace_units": 10, "duration": {"trace_units": 10, "nanoseconds": 10000}},
            {"start_trace_units": 80, "end_trace_units": 100, "duration": {"trace_units": 20, "nanoseconds": 20000}},
        ])
        relations = {(item["name"], item["relation"]) for item in result["unmatched_events"]}
        self.assertIn(("nested", "nested_descendant"), relations)
        self.assertIn(("other-track", "overlapping_other_trace_track"), relations)
        self.assertEqual(result["identity"]["rank"], None)
        self.assertEqual(result["identity"]["device"], None)
        self.assertIn("never proof of duplicate execution", result["residual"]["interpretation"])

    def test_output_is_deterministic_and_canonically_digested(self):
        row = manifest(FIXTURE, digest(FIXTURE))
        first = ANALYZER.analyze(row, Path("/tmp/kilo/manifest.json"), "parent")
        second = ANALYZER.analyze(row, Path("/tmp/kilo/manifest.json"), "parent")
        self.assertEqual(first, second)
        self.assertEqual(first["digest"], ANALYZER.VALIDATOR.canonical_digest(first))
        self.assertEqual(
            ANALYZER.VALIDATOR._CONTRACT.validate_envelope(first, ANALYZER.BREAKDOWN_EXTENSION_FIELDS),
            [],
        )

    def test_request_breakdown_requires_companion_semantic_producer(self):
        row = manifest(FIXTURE, digest(FIXTURE))
        result = ANALYZER.analyze(row, Path("/tmp/kilo/manifest.json"), "parent", scope="request")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["primary_blocker"]["code"], "request_scope_requires_companion_semantic_producer")

    def test_request_breakdown_requires_exact_parent_event_binding(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            root = Path(directory)
            trace = root / "trace.json"
            trace.write_bytes(FIXTURE.read_bytes())
            row = manifest(trace, digest(trace))
            companion = semantic_artifact(row, ["request"], [{
                "request_id": "request-1", "name": "different", "pid": 1,
                "tid": "main", "ts": 0, "dur": 100,
            }])
            semantic_path = root / "semantic.json"
            semantic_path.write_text(json.dumps(companion), encoding="utf-8")
            row["semantic_producer"] = {
                "producer": companion["producer"], "artifact_path": str(semantic_path),
                "artifact_digest": digest(semantic_path),
            }
            row["input_artifact_digests"].append(row["semantic_producer"]["artifact_digest"])
            row["expected_localization_scopes"]["request"] = True
            row = ANALYZER.VALIDATOR._CONTRACT.seal_envelope(row)
            result = ANALYZER.analyze(row, root / "manifest.json", "parent", scope="request")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["primary_blocker"]["code"], "request_event_binding_required")

    def test_parent_without_component_fails_closed(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            trace = Path(directory) / "aggregate-only.json"
            trace.write_text(json.dumps({"traceEvents": [
                {"name": "aggregate", "ph": "X", "pid": "track", "tid": "thread", "ts": 0, "dur": 10, "args": {}}
            ]}), encoding="utf-8")
            row = manifest(trace, digest(trace))
            result = ANALYZER.analyze(row, Path(directory) / "manifest.json", "aggregate")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["primary_blocker"]["code"], "missing_trace_track_component")
        self.assertEqual(
            ANALYZER.VALIDATOR._CONTRACT.validate_envelope(result, ANALYZER.BREAKDOWN_EXTENSION_FIELDS),
            [],
        )

    def test_zero_duration_parent_or_component_fails_closed(self):
        for parent_duration, child_duration, code in (
            (0, 0, "non_positive_parent_duration"),
            (10, 0, "non_positive_component_duration"),
        ):
            with self.subTest(code=code), tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
                trace = Path(directory) / "zero.json"
                trace.write_text(json.dumps({"traceEvents": [
                    {"name": "parent", "ph": "X", "pid": 1, "tid": 1, "ts": 0, "dur": parent_duration, "args": {}},
                    {"name": "child", "ph": "X", "pid": 1, "tid": 1, "ts": 0, "dur": child_duration, "args": {}},
                ]}), encoding="utf-8")
                row = manifest(trace, digest(trace))
                result = ANALYZER.analyze(row, Path(directory) / "manifest.json", "parent")
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["primary_blocker"]["code"], code)

    def test_fixed_trace_parent_and_kernel_timing(self):
        if not FIXED_TRACE.is_file():
            row = manifest(FIXED_TRACE, FIXED_DIGEST)
            result = ANALYZER.analyze(row, Path("/tmp/kilo/manifest.json"), "aten::custom_normal")
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["primary_blocker"]["code"], "r1_trace_track_validation_required")
            return
        self.assertEqual(digest(FIXED_TRACE), FIXED_DIGEST)
        row = manifest(FIXED_TRACE, FIXED_DIGEST)
        first = ANALYZER.analyze(row, Path("/tmp/kilo/manifest.json"), "aten::custom_normal", 0)
        second = ANALYZER.analyze(row, Path("/tmp/kilo/manifest.json"), "aten::custom_normal", 0)
        self.assertEqual(first, second)
        self.assertEqual(first["parent"]["duration"], {"trace_units": 4588950, "nanoseconds": 4588950000})
        kernel = next(item for item in first["unmatched_events"] if item["name"] == "custom_normal_bf16")
        self.assertEqual(kernel["duration"], {"trace_units": 8, "nanoseconds": 8000})
        self.assertEqual(kernel["relation"], "overlapping_other_trace_track")


if __name__ == "__main__":
    unittest.main()
