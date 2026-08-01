import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
IDENTITY = "chipltech-context"


class ChipltechContextPublicationTests(unittest.TestCase):
    def test_publication_surfaces_match_frontmatter(self):
        skill_root = ROOT / "skills" / "engineering" / IDENTITY
        skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        frontmatter = yaml.safe_load(skill_text.split("---", 2)[1])
        description = frontmatter["description"]

        self.assertEqual(frontmatter["name"], IDENTITY)
        config = frontmatter["metadata"]["hermes"]["config"]
        self.assertEqual(
            [entry["key"] for entry in config],
            ["chipltech_kb.path", "chipltech_skills.path"],
        )
        self.assertTrue(all("default" not in entry for entry in config))
        self.assertNotIn("disable-model-invocation", frontmatter)
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

        manifest = yaml.safe_load((ROOT / "SKILLHUB.yaml").read_text(encoding="utf-8"))
        rows = [row for row in manifest["skills"] if row["name"] == IDENTITY]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["description"], description)
        self.assertEqual(rows[0]["files"], ["SKILL.md", "agents/"])

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
            wrapper = Path(directory) / ".kilo" / "command" / f"{IDENTITY}.md"
            self.assertIn(f"请使用 `{IDENTITY}` skill", wrapper.read_text(encoding="utf-8"))

    def test_router_contract_is_evidence_first_and_read_only(self):
        text = (
            ROOT / "skills" / "engineering" / IDENTITY / "SKILL.md"
        ).read_text(encoding="utf-8")
        for required in (
            "CONTEXT.md",
            "README.md",
            "prompt-examples/all-supported-capabilities-quickstart.md",
            "repository-relative path",
            "direct repository evidence",
            "runtime observation",
            "inference",
            "missing evidence",
            "read-only",
            "blocked_ambiguous_knowledge_root",
            "blocked_conflicting_authority",
            "Claim Boundary:",
        ):
            self.assertIn(required, text)

    def test_representative_flows_do_not_fix_the_knowledge_root(self):
        for identity in (
            "dlc-env-setup",
            "model-adaptation",
            "modelzoo-image-validation",
            "pd-separation",
        ):
            text = (
                ROOT / "skills" / "engineering" / identity / "SKILL.md"
            ).read_text(encoding="utf-8")
            self.assertNotIn("/work/chipltech-knowledge-base", text, identity)

    def test_representative_route_and_blocker_matrix(self):
        router = (
            ROOT / "skills" / "engineering" / IDENTITY / "SKILL.md"
        ).read_text(encoding="utf-8")
        matrix = (
            (
                "dlc-env-setup",
                "runtime-debugging/",
                "blocked_missing_repository",
            ),
            (
                "model-adaptation",
                "vllm-dlc/model-adaptation-and-main-to-main-decisions.md",
                "blocked_missing_asset",
            ),
            (
                "modelzoo-image-validation",
                "vllm-dlc/modelzoo-driven-dlc-tyd-image-contract.md",
                "blocked_missing_asset",
            ),
            (
                "pd-separation",
                "vllm-dlc/prefill-decode-separation.md",
                "blocked_missing_contract",
            ),
        )
        for skill_name, knowledge_path, blocker in matrix:
            with self.subTest(skill=skill_name):
                route_row = next(
                    line
                    for line in router.splitlines()
                    if line.startswith("|") and f"`{skill_name}`" in line
                )
                self.assertIn(knowledge_path, route_row)
                owner = (
                    ROOT / "skills" / "engineering" / skill_name / "SKILL.md"
                ).read_text(encoding="utf-8")
                self.assertIn(blocker, owner)

        self.assertTrue(
            (ROOT / "scripts" / "validate-hermes-chipltech-integration.py").is_file()
        )

    def test_performance_regression_routes_to_diagnosis(self):
        router = (
            ROOT / "skills" / "engineering" / IDENTITY / "SKILL.md"
        ).read_text(encoding="utf-8")
        route_row = next(
            line
            for line in router.splitlines()
            if line.startswith("|") and "Model-serving performance regression" in line
        )
        self.assertIn("runtime-debugging/performance-profiling.md", route_row)
        self.assertIn("nearest performance case study", route_row)
        self.assertIn("`diagnosing-bugs`", route_row)
        self.assertIn("route the smallest compatibility action to `model-adaptation`", router)


if __name__ == "__main__":
    unittest.main()
