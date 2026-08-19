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

    def test_accelerator_repro_is_identity_and_failure_boundary_bound(self):
        skill = (
            ROOT / "skills" / "engineering" / IDENTITY / "SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertIn("**Identity-bound**", skill)
        self.assertIn("last successful lifecycle stage and first fatal boundary", skill)

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
            for relative in (
                "references/profiling-evidence-contract.md",
                "references/perf-breakdown.md",
                "references/kernel-summary-export.md",
                "scripts/validate-dlc-profile-artifacts.py",
                "scripts/analyze-dlc-profile.py",
                "scripts/export-dlc-kernel-csv.py",
                "scripts/_generated_contracts/qualification_artifact.py",
            ):
                self.assertTrue((installed / relative).is_file(), relative)

    def test_profile_contracts_are_linked_and_fail_closed(self):
        skill_root = ROOT / "skills" / "engineering" / IDENTITY
        skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("references/profiling-evidence-contract.md", skill)
        self.assertIn("references/perf-breakdown.md", skill)
        self.assertIn("references/kernel-summary-export.md", skill)
        profile = (skill_root / "references/profiling-evidence-contract.md").read_text(encoding="utf-8")
        breakdown = (skill_root / "references/perf-breakdown.md").read_text(encoding="utf-8")
        for required in ("read-only", "not OS PID/TID", "acceptance-ineligible", "Claim Boundary:"):
            self.assertIn(required, profile)
        for required in ("unmatched", "residual", "companion semantic producer", "Claim Boundary:"):
            self.assertIn(required, breakdown)

        kernel_summary = (skill_root / "references/kernel-summary-export.md").read_text(encoding="utf-8")
        for required in ("only `operators.csv`", "1400 MHz", "produces no", "Claim Boundary:"):
            self.assertIn(required, kernel_summary)


if __name__ == "__main__":
    unittest.main()
