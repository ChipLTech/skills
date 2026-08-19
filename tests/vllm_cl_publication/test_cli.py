import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "scripts" / "validate-vllm-cl-publication.py"


class VllmClPublicationCliTests(unittest.TestCase):
    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(CLI),
                "--skills-root",
                str(ROOT),
                "--knowledge-root",
                "/work/chipltech-knowledge-base",
                "--vllm-root",
                "/work/vllm",
                "--vllm-cl-root",
                "/work/vllm-cl",
                *arguments,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def assert_passes_live_package(self, identity: str) -> dict:
        result = self.run_cli("live-package", identity)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["overall_status"], "passed")
        self.assertEqual(report["skill_identity"], identity)
        self.assertEqual(report["stable_path"], f"skills/engineering/{identity}")
        self.assertFalse(report["duplicate_in_progress_identity"])
        self.assertEqual(report["frontmatter"]["name"], identity)
        self.assertTrue(report["catalogs"]["top_level"]["description"])
        self.assertEqual(
            report["catalogs"]["top_level"]["link"],
            f"./skills/engineering/{identity}/SKILL.md",
        )
        self.assertEqual(report["catalogs"]["engineering"]["description"], report["frontmatter"]["description"])
        self.assertEqual(report["skillhub"]["description"], report["frontmatter"]["description"])
        self.assertIn("SKILL.md", report["skillhub"]["files"])
        self.assertIn("agents/", report["skillhub"]["files"])
        self.assertIn("knowledge.md", report["skillhub"]["files"])
        self.assertTrue(report["linker"]["default_selected"])
        self.assertTrue(report["wrapper"]["generated_from_frontmatter"])
        return report

    def test_model_adaptation_is_structurally_published(self):
        report = self.assert_passes_live_package("model-adaptation")
        assets = report["digests"]["qualification_assets"]
        self.assertIn("scripts/collect-vllm-cl-live-identity.py", assets)
        self.assertIn("scripts/identity_provider_seal.py", assets)
        self.assertIn("scripts/observe-python-package-identity.py", assets)
        self.assertIn("references/identity-provider-seal-v1.schema.json", assets)
        self.assertIn("scripts/attest-vllm-cl-qualification.py", assets)
        self.assertIn("scripts/_generated_contracts/qualification_artifact.py", assets)
        self.assertIn("scripts/_generated_contracts/qualification-artifact-envelope-v1.schema.json", assets)
        self.assertIn("scripts/_generated_contracts/vllm-cl-collective-selection-v1.schema.json", assets)
        self.assertTrue(all(value.startswith("sha256:") for value in assets.values()))

    def test_main_to_main_upgrade_is_structurally_published(self):
        self.assert_passes_live_package("main-to-main-upgrade")

    def test_publication_surface_inventory_reports_both_skills_once(self):
        result = self.run_cli("publication-surface-inventory")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["overall_status"], "passed")
        self.assertEqual(
            [row["skill_identity"] for row in report["skills"]],
            ["model-adaptation", "main-to-main-upgrade"],
        )
        for row in report["skills"]:
            self.assertEqual(row["stable_path"], f"skills/engineering/{row['skill_identity']}")
            self.assertFalse(row["duplicate_in_progress_identity"])


if __name__ == "__main__":
    unittest.main()
