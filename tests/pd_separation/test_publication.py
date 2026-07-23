import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
IDENTITY = "pd-separation"


class PDSeparationPublicationTests(unittest.TestCase):
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
        self.assertEqual(rows[0]["files"], ["SKILL.md", "agents/", "references/"])
        agent = yaml.safe_load((ROOT / "skills" / "engineering" / IDENTITY / "agents" / "openai.yaml").read_text(encoding="utf-8"))["interface"]
        self.assertIn("Qualify", agent["short_description"])
        for term in ("transport", "content-checked payload", "request-correlated", "recovery"):
            self.assertIn(term, agent["default_prompt"])
        chinese_readme = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        for capability in (f"/{IDENTITY}", "先验证 transport", "qualified TCP", "lyp_full", "dlccl_direct", "site recovery evidence"):
            self.assertIn(capability, chinese_readme)
        self.assertIn(f"skills/{IDENTITY} -> <repo>/skills/engineering/{IDENTITY}", chinese_readme)
        self.assertIn(f"command/{IDENTITY}.md", chinese_readme)

    def test_skill_locks_transport_and_claim_boundaries(self):
        skill_root = ROOT / "skills" / "engineering" / IDENTITY
        text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        adaptation = (skill_root / "references" / "dlc-adaptation.md").read_text(encoding="utf-8")
        deployment = (skill_root / "references" / "deployment-and-troubleshooting.md").read_text(encoding="utf-8")
        for required in ("request-correlated", "single_node_tcp", "single_node_lyp_full", "single_node_dlccl_direct", "cross_machine_tcp", "blocked_transport_unqualified", "blocked_cleanup_incomplete", "transport qualification", "site recovery", "package/source/build-artifact", "Device execution never authorizes", "HTTP 200", "Cross-machine deployment defaults to TCP", "docker exec"):
            self.assertIn(required, text)
        self.assertIn("CPU-Staging Lifecycle", adaptation)
        self.assertIn("KV Cache Layout Contract", adaptation)
        self.assertIn("Transport Qualification Gate", adaptation)
        self.assertIn("Native Direct DLCCL Lifecycle", adaptation)
        self.assertIn("process-local `dlc:0`", adaptation)
        self.assertIn("legacy `lyp`", text)
        self.assertIn("Host-maintenance", deployment)
        self.assertIn("pre-existing workload", deployment)
        self.assertIn("capability-derived readiness", deployment)
        self.assertIn("Only step 7 closes KV transfer", deployment)
        public_package = "\n".join((text, adaptation, deployment))
        for unsafe in ("hangzhou-office-harbor", "177.177.177.153", "177.177.177.154", "rmmod chipltech", "kill -KILL"):
            self.assertNotIn(unsafe, public_package)

    def test_default_project_install_copies_references_and_wrapper(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            result = subprocess.run([str(ROOT / "scripts" / "link-kilo-skills.sh"), "--project", directory, "--with-commands"], capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            installed = Path(directory) / ".kilo" / "skills" / IDENTITY
            self.assertTrue((installed / "SKILL.md").is_file())
            self.assertTrue((installed / "references" / "dlc-adaptation.md").is_file())
            self.assertTrue((installed / "references" / "deployment-and-troubleshooting.md").is_file())
            wrapper = (Path(directory) / ".kilo" / "command" / f"{IDENTITY}.md").read_text(encoding="utf-8")
            self.assertIn(f"请使用 `{IDENTITY}` skill", wrapper)
            self.assertIn("$ARGUMENTS", wrapper)


if __name__ == "__main__":
    unittest.main()
