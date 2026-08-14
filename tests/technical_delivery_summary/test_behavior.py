import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "engineering" / "technical-delivery-summary" / "scripts" / "format-delivery-summary.py"


class TechnicalDeliverySummaryBehaviorTests(unittest.TestCase):
    def test_chipltech_delivery_verbs_preserve_claim_boundary(self):
        cases = {
            "source_only": "source 中已实现",
            "build_only": "已完成 build",
            "historical_smoke": "历史 smoke 记录显示",
            "merged_not_released": "已合入",
            "released_not_validated": "已发布",
            "performance_workload": "已在声明 workload 下测得性能",
        }
        for evidence, verb in cases.items():
            with self.subTest(evidence=evidence):
                result = subprocess.run(["python3", str(SCRIPT), evidence, "目标能力"], capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertIn(verb, report["summary"])
                self.assertTrue(report["claim_boundary"].startswith("Claim Boundary:"))
                self.assertFalse(report["qualification_artifact_created"])


if __name__ == "__main__":
    unittest.main()
