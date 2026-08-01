import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
IDENTITY = "diagnosing-bugs"


class DiagnosingBugsPublicationTests(unittest.TestCase):
    def test_hierarchical_performance_reference_is_published(self):
        skill_root = ROOT / "skills" / "engineering" / IDENTITY
        skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        reference = (
            skill_root / "references" / "hierarchical-performance-diagnosis.md"
        ).read_text(encoding="utf-8")
        manifest = yaml.safe_load((ROOT / "SKILLHUB.yaml").read_text(encoding="utf-8"))
        row = next(item for item in manifest["skills"] if item["name"] == IDENTITY)

        self.assertIn("references/hierarchical-performance-diagnosis.md", skill)
        self.assertIn("references/", row["files"])
        for required in (
            "Uninstrumented profile",
            "Diagnostic profile",
            "Localize Top-Down",
            "Reconcile Adjacent Boundaries",
            "invocation count",
            "shape",
            "stride/layout",
            "contiguity",
            "storage identity",
            "storage offset",
            "logical view relationship",
            "rank/device",
            "Remove temporary synchronization",
        ):
            self.assertIn(required, reference)
        self.assertNotIn("forward_includes_kv_cache_update", reference)

    def test_project_install_copies_performance_reference(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            result = subprocess.run(
                [
                    str(ROOT / "scripts" / "link-kilo-skills.sh"),
                    "--project",
                    directory,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            installed = Path(directory) / ".kilo" / "skills" / IDENTITY
            self.assertTrue(
                (installed / "references" / "hierarchical-performance-diagnosis.md").is_file()
            )


if __name__ == "__main__":
    unittest.main()
