import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/engineering/diagnosing-bugs/scripts/export-dlc-kernel-csv.py"
TOOL = Path("/home/xuansun/llama2-fine-tune/tool.py")
SEPARATOR = "───────────────────────────────────────────────────────────────────────────────────"


class KernelSummaryTests(unittest.TestCase):
    def run_export(self, text: str):
        temporary = tempfile.TemporaryDirectory(dir="/tmp/kilo")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        log = root / "syn_test.ansi"
        output = root / "summary"
        log.write_text(text, encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(log),
                "--tool",
                str(TOOL),
                "--output-dir",
                str(output),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        return result, output

    def test_exports_only_csv_at_tool_frequency(self):
        text = "".join(
            (
                f"{SEPARATOR} launch  custom_alpha x\n",
                "shape=1x2\n",
                f"{SEPARATOR} cycles: 1400  ops: 2800  bytes: 1400  crt: 700\n",
                f"{SEPARATOR} launch  custom_beta x\n",
                "shape=2x2\n",
                f"{SEPARATOR} cycles: 2800  ops: 2800  bytes: 5600  crt: 1400\n",
                f"{SEPARATOR} launch  custom_alpha x\n",
                "shape=1x2\n",
                f"{SEPARATOR} cycles: 1400  ops: 1400  bytes: 2800  crt: 700\n",
            )
        )
        result, output = self.run_export(text)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual([path.name for path in output.iterdir()], ["operators.csv"])
        with (output / "operators.csv").open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual([row["kernel_name"] for row in rows], ["custom_alpha", "custom_beta"])
        self.assertEqual(rows[0]["calls"], "2")
        self.assertEqual(rows[0]["total_cycles"], "2800")
        self.assertEqual(rows[0]["total_time_us"], "2.000000")
        self.assertEqual(rows[0]["clock_mhz"], "1400")
        result_document = json.loads(result.stdout)
        self.assertEqual(result_document["clock_mhz"], 1400)
        self.assertEqual(result_document["launch_count"], 3)
        self.assertEqual(result_document["kernel_count"], 2)
        self.assertIn("sha256:", result_document["operator_csv"]["digest"])

    def test_empty_log_fails_without_partial_outputs(self):
        result, output = self.run_export("no launches\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no DLCSynapse kernel launches", result.stdout)
        self.assertFalse((output / "operators.csv").exists())


if __name__ == "__main__":
    unittest.main()
