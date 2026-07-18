import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "scripts" / "build-vllm-dlc-long-prefix.py"


def load_builder():
    spec = importlib.util.spec_from_file_location("build_vllm_dlc_long_prefix", BUILDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LongPrefixTests(unittest.TestCase):
    def test_multi_token_units_produce_shortest_prefix_over_threshold(self):
        builder = load_builder()
        encode = lambda value: list(range(len(value.split()) * 5))

        prompt, token_ids = builder.build_long_prefix(
            encode,
            threshold=1024,
            maximum=8191,
        )

        self.assertEqual(len(token_ids), 1025)
        self.assertEqual(len(prompt.split()), 205)
        self.assertEqual(
            len(encode(" ".join(f"operational-{index}" for index in range(204)))),
            1020,
        )

    def test_fixture_preserves_exact_1025_whitespace_tokens(self):
        builder = load_builder()
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            tokenizer = Path(directory)
            (tokenizer / "fixture-tokenizer.json").write_text(json.dumps({
                "schema_version": "vllm-dlc-fixture-whitespace-tokenizer/v1"
            }))
            output = io.StringIO()
            arguments = [
                str(BUILDER),
                "--tokenizer-path", str(tokenizer),
                "--threshold", "1024",
                "--context-limit", "8192",
                "--output-allowance", "1",
                "--fixture",
            ]

            with mock.patch.object(sys, "argv", arguments), redirect_stdout(output):
                self.assertEqual(builder.main(), 0)

        proof = json.loads(output.getvalue())
        self.assertEqual(proof["prompt_token_count"], 1025)
        self.assertEqual(
            proof["prompt"],
            " ".join(f"operational-{index}" for index in range(1025)),
        )

    def test_bounded_scan_recovers_hidden_earlier_crossing(self):
        builder = load_builder()

        def encode(value):
            unit_count = len(value.split())
            return list(range(11 if unit_count == 3 else unit_count))

        prompt, token_ids = builder.build_long_prefix(encode, threshold=10, maximum=20)

        self.assertEqual(len(prompt.split()), 3)
        self.assertEqual(len(token_ids), 11)

    def test_non_monotonic_boundary_fails_closed_beyond_bounded_scan(self):
        builder = load_builder()

        def encode(value):
            unit_count = len(value.split())
            return list(range(101 if unit_count == 90 else unit_count))

        with self.assertRaisesRegex(ValueError, "cannot prove minimal prefix"):
            builder.build_long_prefix(encode, threshold=100, maximum=200)

    def test_unstable_reencode_fails_closed(self):
        builder = load_builder()
        calls = {}

        def encode(value):
            calls[value] = calls.get(value, 0) + 1
            count = len(value.split())
            if count == 11 and calls[value] > 1:
                count += 1
            return list(range(count))

        with self.assertRaisesRegex(ValueError, "deterministic valid boundary"):
            builder.build_long_prefix(encode, threshold=10, maximum=20)

    def test_minimal_crossing_must_fit_context_budget(self):
        builder = load_builder()

        with self.assertRaisesRegex(ValueError, "deterministic valid boundary"):
            builder.build_long_prefix(
                lambda value: list(range(len(value.split()) * 6)),
                threshold=10,
                maximum=11,
            )


if __name__ == "__main__":
    unittest.main()
