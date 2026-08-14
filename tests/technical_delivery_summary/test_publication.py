import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_ROOT = Path("/work/chipltech-knowledge-base")
IDENTITY = "technical-delivery-summary"


class TechnicalDeliverySummaryPublicationTests(unittest.TestCase):
    def test_publication_surfaces_match_frontmatter(self):
        skill_path = ROOT / "skills" / "engineering" / IDENTITY / "SKILL.md"
        skill_text = skill_path.read_text(encoding="utf-8")
        frontmatter = yaml.safe_load(skill_text.split("---", 2)[1])

        self.assertEqual(frontmatter["name"], IDENTITY)
        self.assertNotIn("disable-model-invocation", frontmatter)
        self.assertIn(
            f"[`{IDENTITY}`](./skills/engineering/{IDENTITY}/SKILL.md)",
            (ROOT / "README.md").read_text(encoding="utf-8"),
        )
        self.assertIn(
            f"[{IDENTITY}](./{IDENTITY}/SKILL.md)** — {frontmatter['description']}",
            (ROOT / "skills" / "engineering" / "README.md").read_text(
                encoding="utf-8"
            ),
        )

        plugin = json.loads(
            (ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            plugin["skills"].count(f"./skills/engineering/{IDENTITY}"), 1
        )

        manifest = yaml.safe_load((ROOT / "SKILLHUB.yaml").read_text(encoding="utf-8"))
        rows = [row for row in manifest["skills"] if row["name"] == IDENTITY]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["description"], frontmatter["description"])
        self.assertEqual(rows[0]["files"], ["SKILL.md", "agents/", "scripts/"])

    def test_project_install_copies_skill_and_wrapper(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            result = subprocess.run(
                [
                    str(ROOT / "scripts" / "link-kilo-skills.sh"),
                    "--project",
                    directory,
                    "--with-commands",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            installed = Path(directory) / ".kilo" / "skills" / IDENTITY
            self.assertTrue((installed / "SKILL.md").is_file())
            self.assertTrue((installed / "agents" / "openai.yaml").is_file())
            self.assertTrue((installed / "scripts" / "format-delivery-summary.py").is_file())
            wrapper = Path(directory) / ".kilo" / "command" / f"{IDENTITY}.md"
            self.assertIn(f"请使用 `{IDENTITY}` skill", wrapper.read_text(encoding="utf-8"))

    def test_summary_contract_preserves_delivery_boundaries(self):
        skill = (
            ROOT / "skills" / "engineering" / IDENTITY / "SKILL.md"
        ).read_text(encoding="utf-8")
        for required in (
            "Implemented",
            "Integrated",
            "Validated",
            "Merged",
            "Released",
            "capability spine",
            "Object",
            "Behavior",
            "Basis or condition",
            "Outcome",
            "subtraction test",
            "foundation/technical-delivery-summary.md",
            "Claim Boundary",
        ):
            self.assertIn(required, skill)

        self.assertIn("independent evidence dimensions", skill)
        self.assertIn("merge does not establish release", skill)
        self.assertIn("release does not establish validation", skill)
        self.assertIn("`diagnosing-bugs` for unresolved failures", skill)
        self.assertNotIn("merged, published, deployed", skill)
        self.assertIn("literal `Claim Boundary:` line", skill)
        self.assertIn("does not create a Qualification Artifact", skill)

        router = (
            ROOT / "skills" / "engineering" / "chipltech-context" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn(f"`{IDENTITY}`", router)

    def test_historical_cases_are_not_inherited_as_current_evidence(self):
        for name in (
            "qknorm-topology-aware-allreduce-selection.md",
            "host-api22-fullstack-main-to-main-update.md",
            "model-adaptation-analysis-report-production.md",
        ):
            text = (KNOWLEDGE_ROOT / "case-studies" / name).read_text(encoding="utf-8")
            self.assertIn("Evidence status:", text)
            self.assertIn("historical_report_derived_observation", text)
            self.assertIn("identity_unavailable", text)
            self.assertIn("不可继承", text)


if __name__ == "__main__":
    unittest.main()
