import unittest
from pathlib import Path


KNOWLEDGE_ROOT = Path("/work/chipltech-knowledge-base")
SKILL_ROOT = Path(__file__).resolve().parents[2] / "skills" / "engineering" / "modelzoo-image-validation"


class EnvironmentDocumentAuthorityTests(unittest.TestCase):
    def test_knowledge_documents_route_current_execution_to_owner(self):
        paths = (
            KNOWLEDGE_ROOT / "runtime-debugging" / "environment-setup-and-update.md",
            KNOWLEDGE_ROOT / "runtime-debugging" / "dlc-workstation-env-rebuild.md",
            KNOWLEDGE_ROOT / "prompt-examples" / "dlc-env-setup-environment-bootstrap.md",
            KNOWLEDGE_ROOT / "agent-context" / "new-session-context.md",
        )
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertIn("dlc-env-setup", text)
            self.assertIn("唯一 current executable authority", text)
            for stale_default in ("release_25", "update-v0.11.0", "inc_nsteps", "cd /work/", "python3 setup.py develop"):
                self.assertNotIn(stale_default, text)

    def test_tyd_delivery_does_not_duplicate_rebuild_order(self):
        text = (SKILL_ROOT / "references" / "tyd-delivery.md").read_text(encoding="utf-8")
        self.assertIn("current executable order", text)
        self.assertNotIn("dlc-thunk -> LLVM -> DLCsim", text)


if __name__ == "__main__":
    unittest.main()
