import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_ROOT = Path("/work/chipltech-knowledge-base")
IDENTITY = "pytorch-dlc-plugin-migration"


class PyTorchDLCPluginMigrationPublicationTests(unittest.TestCase):
    def test_publication_surfaces_match_frontmatter(self):
        skill = ROOT / "skills" / "engineering" / IDENTITY / "SKILL.md"
        text = skill.read_text(encoding="utf-8")
        frontmatter = yaml.safe_load(text.split("---", 2)[1])
        description = frontmatter["description"]
        self.assertEqual(frontmatter["name"], IDENTITY)
        self.assertIn(
            f"[`{IDENTITY}`](./skills/engineering/{IDENTITY}/SKILL.md)",
            (ROOT / "README.md").read_text(encoding="utf-8"),
        )
        self.assertIn(
            f"[{IDENTITY}](./{IDENTITY}/SKILL.md)** — {description}",
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
        manifest = yaml.safe_load(
            (ROOT / "SKILLHUB.yaml").read_text(encoding="utf-8")
        )
        rows = [row for row in manifest["skills"] if row["name"] == IDENTITY]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["description"], description)
        self.assertEqual(rows[0]["files"], ["SKILL.md", "agents/", "references/", "scripts/"])

    def test_skill_preserves_semantics_and_evidence_boundaries(self):
        text = (
            ROOT / "skills" / "engineering" / IDENTITY / "SKILL.md"
        ).read_text(encoding="utf-8")
        for required in (
            "PrivateUse1",
            "Public Operator Schema",
            "KernelDesc Descriptor ABI",
            "DLC Custom Kernel Entry ABI",
            "CPU computation fallback",
            "blocked_missing_production_semantics",
            "direct_repository_evidence",
            "artifact path/hash",
            "blocked_cleanup_incomplete",
            "Aggregate deterministically",
            "implementation_complete_tests_deferred",
            "Claim Boundary",
        ):
            self.assertIn(required, text)
        self.assertNotIn("/work/chipltech-knowledge-base", text)

    def test_skill_and_prompt_require_source_classification_before_reference_use(self):
        skill = (ROOT / "skills" / "engineering" / IDENTITY / "SKILL.md").read_text(encoding="utf-8")
        prompt = (KNOWLEDGE_ROOT / "prompt-examples" / "pytorch-dlc-plugin-migration-prompts.md").read_text(encoding="utf-8")
        for text in (skill, prompt):
            for required in (
                "source classification gate",
                "source locator",
                "revision or SHA-256",
                "license metadata",
                "intended use",
                "disposition",
                "blocked_legal_boundary",
                "independent DLC-native specification",
            ):
                self.assertIn(required, text)
            self.assertIn("production PyTorch DLC Backend", text)
            self.assertIn("不得复制、翻译或机械改写", text)
            self.assertIn("关键词只触发 review", text)

    def test_default_project_install_creates_wrapper(self):
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
            self.assertTrue((installed / "references" / "plugin-migration-result-v1.schema.json").is_file())
            self.assertTrue((installed / "scripts" / "evaluate-plugin-migration.py").is_file())
            wrapper = (
                Path(directory) / ".kilo" / "command" / f"{IDENTITY}.md"
            ).read_text(encoding="utf-8")
            self.assertIn(f"请使用 `{IDENTITY}` skill", wrapper)
            self.assertIn("$ARGUMENTS", wrapper)


if __name__ == "__main__":
    unittest.main()
