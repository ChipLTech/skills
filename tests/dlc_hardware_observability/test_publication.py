import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
IDENTITY = "dlc-hardware-observability"


class DLCHardwareObservabilityPublicationTests(unittest.TestCase):
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
            (ROOT / "skills" / "engineering" / "README.md").read_text(encoding="utf-8"),
        )
        plugin = json.loads(
            (ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(plugin["skills"].count(f"./skills/engineering/{IDENTITY}"), 1)
        manifest = yaml.safe_load((ROOT / "SKILLHUB.yaml").read_text(encoding="utf-8"))
        rows = [row for row in manifest["skills"] if row["name"] == IDENTITY]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["description"], description)
        self.assertEqual(
            rows[0]["files"], ["SKILL.md", "agents/", "references/", "scripts/"]
        )
        self.assertIn(
            f"/{IDENTITY}",
            (ROOT / "kilo-code-installation-and-validation.md").read_text(encoding="utf-8"),
        )

    def test_contract_is_query_only_and_fail_closed(self):
        root = ROOT / "skills" / "engineering" / IDENTITY
        text = (root / "SKILL.md").read_text(encoding="utf-8")
        reference = (root / "references" / "observation-contract.md").read_text(
            encoding="utf-8"
        )
        package = "\n".join((text, reference))
        for required in (
            "before_launch",
            "after_ready",
            "during_request",
            "after_cleanup",
            "blocked_missing_observability",
            "vllm-dlc-smi-observation/v1",
            "Shared Hosts need not reach global zero",
            "does not independently prove C1b",
            "Do not recreate the normalized schema manually",
        ):
            self.assertIn(required, package)
        for forbidden in ("cltech_smi -sr", "cltech_smi -hr", "sudo reboot", "rmmod"):
            self.assertNotIn(forbidden, package)

    def test_project_install_copies_reference_and_wrapper(self):
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
            self.assertTrue((installed / "references" / "observation-contract.md").is_file())
            self.assertTrue((installed / "scripts" / "observe-cltech-smi.py").is_file())
            self.assertTrue(
                (installed / "scripts" / "qualify-vllm-dlc-smi-environment.py").is_file()
            )
            wrapper = Path(directory) / ".kilo" / "command" / f"{IDENTITY}.md"
            self.assertIn(f"请使用 `{IDENTITY}` skill", wrapper.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
