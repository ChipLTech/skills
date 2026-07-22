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
        "blocked_missing_asset",
        "blocked_unqualified_daily_base",
        "blocked_unresolved_runtime_contract",
        "blocked_missing_hardware",
        "blocked_missing_authorization",
        "blocked_missing_qualified_dlc_base",
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
        self.assertEqual(rows[0]["files"], ["SKILL.md", "agents/", "references/", "scripts/"])
        self.assertIn(IDENTITY, (ROOT / "README.zh-CN.md").read_text(encoding="utf-8"))

    def test_skill_document_locks_public_cross_repository_contract(self):
        text = (ROOT / "skills" / "engineering" / IDENTITY / "SKILL.md").read_text(encoding="utf-8")
        runtime = (ROOT / "skills" / "engineering" / IDENTITY / "references" / "runtime-qualification.md").read_text(encoding="utf-8")
        tyd = (ROOT / "skills" / "engineering" / IDENTITY / "references" / "tyd-delivery.md").read_text(encoding="utf-8")
        self.assertIn("modelzoo-reference-record/v1", text)
        self.assertIn("ordinary daily base", text)
        self.assertIn("benchmark_workload_pass", text)
        self.assertIn("benchmark_stability_baseline_pass", text)
        self.assertIn("intentionally_not_executed_on_dlc_gen1", text)
        self.assertIn("driver API", text)
        self.assertIn("partial clone", text)
        self.assertIn("source and binary hashes", text)
        self.assertIn("modelzoo_claims", text)
        self.assertIn("execution_evidence", text)
        for blocker in self.PUBLIC_BLOCKERS:
            self.assertIn(blocker, text)
        blocker_section = text.split("Workflow blockers:", 1)[1]
        blocker_block = blocker_section.split("```text", 1)[1].split("```", 1)[0]
        self.assertEqual({line.strip() for line in blocker_block.splitlines() if line.strip()}, self.PUBLIC_BLOCKERS)
        self.assertIn("HF_HUB_OFFLINE=1", runtime)
        self.assertIn("TRANSFORMERS_OFFLINE=1", runtime)
        self.assertIn("GIT_CONFIG_GLOBAL", runtime)
        self.assertIn("blocked_missing_qualified_dlc_base", tyd)
        self.assertIn("Host driver API", tyd)
        stale = {
            "test-observation-public-key",
            "component-root",
            "preflight",
            "blocked_model_not_found",
            "blocked_ambiguous_model",
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
            self.assertTrue((installed / "references" / "runtime-qualification.md").is_file())
            self.assertTrue((installed / "references" / "tyd-delivery.md").is_file())
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
