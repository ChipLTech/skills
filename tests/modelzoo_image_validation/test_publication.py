import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
IDENTITY = "modelzoo-image-validation"


class ModelZooPublicationTests(unittest.TestCase):
    PUBLIC_BLOCKERS = {
        "blocked_model_not_found",
        "blocked_ambiguous_model",
        "blocked_malformed_metadata",
        "blocked_missing_required_field",
        "blocked_conflicting_source_claims",
        "blocked_missing_asset",
        "blocked_unresolved_component_ref",
        "blocked_missing_hardware",
        "blocked_missing_authorization",
        "blocked_unsupported_framework",
        "blocked_cleanup_incomplete",
    }

    def test_publication_surfaces_match_frontmatter(self):
        skill = ROOT / "skills" / "engineering" / IDENTITY / "SKILL.md"
        text = skill.read_text(encoding="utf-8")
        frontmatter = yaml.safe_load(text.split("---", 2)[1])
        description = frontmatter["description"]
        self.assertEqual(frontmatter["name"], IDENTITY)
        self.assertIn(f"[{IDENTITY}](./skills/engineering/{IDENTITY}/SKILL.md)** — {description}", (ROOT / "README.md").read_text(encoding="utf-8"))
        self.assertIn(f"[{IDENTITY}](./{IDENTITY}/SKILL.md)** — {description}", (ROOT / "skills" / "engineering" / "README.md").read_text(encoding="utf-8"))
        plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(plugin["skills"].count(f"./skills/engineering/{IDENTITY}"), 1)
        manifest = yaml.safe_load((ROOT / "SKILLHUB.yaml").read_text(encoding="utf-8"))
        rows = [row for row in manifest["skills"] if row["name"] == IDENTITY]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["description"], description)
        self.assertEqual(rows[0]["files"], ["SKILL.md", "agents/", "scripts/"])
        self.assertIn(IDENTITY, (ROOT / "README.zh-CN.md").read_text(encoding="utf-8"))

    def test_skill_document_locks_public_cross_repository_contract(self):
        text = (ROOT / "skills" / "engineering" / IDENTITY / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("modelzoo-dlc-tyd-resolved-manifest/v1", text)
        self.assertIn("modelzoo-dlc-tyd-validation-report/v1", text)
        self.assertIn("`vllm/v1`", text)
        self.assertIn("DLC_Custom_Kernel Repository", text)
        self.assertIn("intentionally_not_executed_on_dlc_gen1", text)
        self.assertIn("modelzoo_claims", text)
        self.assertIn("execution_evidence", text)
        for blocker in self.PUBLIC_BLOCKERS:
            self.assertIn(f"`{blocker}`", text)
        stale = {
            "blocked_missing_model",
            "blocked_malformed_yaml",
            "blocked_malformed_schema",
            "blocked_conflicting_evidence",
            "blocked_inference_not_declared",
            "modelzoo-image-validation-resolver/v1",
        }
        for value in stale:
            self.assertNotIn(value, text)

    def test_default_project_install_copies_skill_script_and_wrapper(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            project = Path(directory)
            result = subprocess.run(
                [str(ROOT / "scripts" / "link-kilo-skills.sh"), "--project", str(project), "--with-commands"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            installed = project / ".kilo" / "skills" / IDENTITY
            self.assertTrue((installed / "SKILL.md").is_file())
            self.assertTrue((installed / "scripts" / "resolve-modelzoo.py").is_file())
            wrapper = (project / ".kilo" / "command" / f"{IDENTITY}.md").read_text(encoding="utf-8")
            self.assertIn(f"请使用 `{IDENTITY}` skill", wrapper)
            self.assertIn("$ARGUMENTS", wrapper)

    def test_project_install_excludes_generated_python_bytecode(self):
        source_cache = ROOT / "skills" / "engineering" / IDENTITY / "scripts" / "__pycache__"
        source_cache.mkdir(exist_ok=True)
        generated = source_cache / "resolver-fixture.pyc"
        generated.write_bytes(b"\x00\xffgenerated")
        try:
            with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
                result = subprocess.run(
                    [str(ROOT / "scripts" / "link-kilo-skills.sh"), "--project", directory, "--with-commands"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                installed = Path(directory) / ".kilo" / "skills" / IDENTITY
                self.assertFalse((installed / "scripts" / "__pycache__").exists())
        finally:
            generated.unlink(missing_ok=True)
            if not any(source_cache.iterdir()):
                source_cache.rmdir()


if __name__ == "__main__":
    unittest.main()
