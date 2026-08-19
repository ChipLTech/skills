import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
OWNERSHIP_MARKER = "kilo-generated-wrapper: mattpocock-skills/link-kilo-skills.sh/v2"
IMPORTED = {
    "codebase-design",
    "domain-modeling",
    "wizard",
    "grilling",
    "to-questionnaire",
    "wait-what",
    "writing-for-agents",
}


def frontmatter(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])


class UpstreamV12PublicationTests(unittest.TestCase):
    @staticmethod
    def run_linker(project: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                str(ROOT / "scripts" / "link-kilo-skills.sh"),
                "--project",
                str(project),
                "--with-commands",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    def test_promoted_directories_match_plugin(self):
        promoted = {
            skill.parent.name
            for bucket in ("engineering", "productivity")
            for skill in (ROOT / "skills" / bucket).glob("*/SKILL.md")
        }
        plugin = json.loads(
            (ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        published = {Path(entry).name for entry in plugin["skills"]}

        self.assertEqual(len(promoted), 37)
        self.assertEqual(promoted, published)
        self.assertTrue(IMPORTED <= promoted)
        self.assertNotIn("writing-great-skills", promoted)

    def test_imported_skills_have_consistent_publication_metadata(self):
        manifest = yaml.safe_load((ROOT / "SKILLHUB.yaml").read_text(encoding="utf-8"))
        rows = {row["name"]: row for row in manifest["skills"]}

        for identity in IMPORTED:
            with self.subTest(skill=identity):
                candidates = list((ROOT / "skills").glob(f"*/{identity}/SKILL.md"))
                self.assertEqual(len(candidates), 1)
                skill_md = candidates[0]
                metadata = frontmatter(skill_md)
                self.assertEqual(metadata["name"], identity)
                self.assertEqual(rows[identity]["description"], metadata["description"])
                self.assertTrue((skill_md.parent / "agents" / "openai.yaml").is_file())
                for declared in rows[identity]["files"]:
                    self.assertTrue((skill_md.parent / declared.rstrip("/")).exists(), declared)

    def test_skillhub_matches_all_non_deprecated_packages(self):
        expected = {
            skill.parent.name
            for skill in (ROOT / "skills").glob("*/*/SKILL.md")
            if "deprecated" not in skill.parts
        }
        manifest = yaml.safe_load((ROOT / "SKILLHUB.yaml").read_text(encoding="utf-8"))
        rows = manifest["skills"]
        published = {row["name"] for row in rows}

        self.assertEqual(len(rows), len(published))
        self.assertEqual(expected, published)
        for row in rows:
            self.assertTrue((ROOT / row["path"] / "SKILL.md").is_file(), row["name"])

    def test_invocation_policy_matches_frontmatter_for_promoted_skills(self):
        for bucket in ("engineering", "productivity"):
            for skill_md in (ROOT / "skills" / bucket).glob("*/SKILL.md"):
                with self.subTest(skill=skill_md.parent.name):
                    metadata = frontmatter(skill_md)
                    openai_path = skill_md.parent / "agents" / "openai.yaml"
                    self.assertTrue(openai_path.is_file())
                    openai = yaml.safe_load(openai_path.read_text(encoding="utf-8")) or {}
                    user_invoked = metadata.get("disable-model-invocation") is True
                    implicit_disabled = (
                        openai.get("policy", {}).get("allow_implicit_invocation") is False
                    )
                    self.assertEqual(user_invoked, implicit_disabled)

    def test_router_and_chipltech_boundary_cover_v1_2(self):
        router_path = (
            ROOT / "skills" / "engineering" / "ask-matt" / "SKILL.md"
        )
        router = router_path.read_text(encoding="utf-8")
        context = (
            ROOT / "skills" / "engineering" / "chipltech-context" / "SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertNotIn("disable-model-invocation", frontmatter(router_path))
        self.assertIn("same parent directory as the Skills repository", router)
        self.assertIn("prompt-examples/", router)
        self.assertIn("Actually load that Skill", router)
        for identity in IMPORTED | {
            "chipltech-context",
            "technical-delivery-summary",
            "technical-issue-summary",
        }:
            self.assertIn(f"`/{identity}`", router, identity)
        self.assertIn("Generic Skill Boundary", context)
        self.assertIn("active business workspace's project context", context)
        self.assertIn("not business execution or runtime Evidence", context)

    def test_v1_2_surface_has_docs_pages_and_no_retired_page(self):
        changed = {
            "codebase-design",
            "domain-modeling",
            "wizard",
            "grilling",
            "to-questionnaire",
            "wait-what",
            "writing-for-agents",
            "tdd",
            "grill-with-docs",
            "improve-codebase-architecture",
            "prototype",
            "ask-matt",
        }
        pages = {
            path.stem
            for bucket in ("engineering", "productivity")
            for path in (ROOT / "docs" / bucket).glob("*.md")
        }

        self.assertTrue(changed <= pages)
        self.assertNotIn("writing-great-skills", pages)
        for page in pages:
            self.assertTrue(
                (ROOT / "skills" / "engineering" / page).is_dir()
                or (ROOT / "skills" / "productivity" / page).is_dir(),
                page,
            )

    def test_kilo_project_install_contains_imported_skills_and_retires_old_name(self):
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
            installed = Path(directory) / ".kilo" / "skills"
            self.assertEqual(
                len([path for path in installed.iterdir() if not path.name.startswith(".")]),
                41,
            )
            for identity in IMPORTED:
                self.assertTrue((installed / identity / "SKILL.md").is_file(), identity)
            self.assertFalse((installed / "writing-great-skills").exists())

    def test_linker_migrates_a_pre_existing_retired_install(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            project = Path(directory)
            retired_skill = project / ".kilo" / "skills" / "writing-great-skills"
            retired_skill.mkdir(parents=True)
            (retired_skill / "SKILL.md").write_text("stale retired copy\n", encoding="utf-8")
            (retired_skill / ".kilo-link-source").write_text(
                str(ROOT / "skills" / "productivity" / "writing-great-skills") + "\n",
                encoding="utf-8",
            )
            wrapper = project / ".kilo" / "command" / "writing-great-skills.md"
            wrapper.parent.mkdir(parents=True)
            wrapper.write_text(
                f"<!-- {OWNERSHIP_MARKER} -->\nretired wrapper\n", encoding="utf-8"
            )

            result = self.run_linker(project)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertFalse(retired_skill.exists())
            self.assertFalse(wrapper.exists())

    def test_linker_preserves_user_owned_retired_name(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            project = Path(directory)
            user_skill = project / ".kilo" / "skills" / "writing-great-skills"
            user_skill.mkdir(parents=True)
            (user_skill / "SKILL.md").write_text("user owned\n", encoding="utf-8")

            result = self.run_linker(project)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertTrue(user_skill.is_dir())
            self.assertEqual((user_skill / "SKILL.md").read_text(encoding="utf-8"), "user owned\n")


if __name__ == "__main__":
    unittest.main()
