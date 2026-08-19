import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class VllmClSkillBoundaryTests(unittest.TestCase):
    def skill_text(self, identity: str, filename: str = "SKILL.md") -> str:
        return (
            ROOT / "skills" / "engineering" / identity / filename
        ).read_text(encoding="utf-8")

    def test_model_adaptation_separates_schema_descriptor_and_kernel_abi(self):
        skill = self.skill_text("model-adaptation")
        knowledge = self.skill_text("model-adaptation", "knowledge.md")

        self.assertIn("routing metadata", skill)
        self.assertIn("pairing-only findings", skill)
        self.assertIn("ordered KernelDesc descriptor ABI", skill)
        self.assertIn("public operator schema is the caller contract", knowledge)
        self.assertIn("does not prove that its descriptor slot is absent", knowledge)

    def test_main_to_main_separates_source_absence_from_runtime_necessity(self):
        skill = self.skill_text("main-to-main-upgrade")
        knowledge = self.skill_text("main-to-main-upgrade", "knowledge.md")

        self.assertIn("Exact-HEAD static absence", skill)
        self.assertIn("remains a validation assignment", skill)
        self.assertIn("artifact pairing only", skill)
        self.assertIn("expected_dependency_ids", skill)
        self.assertIn("v1 has no separate necessity-verdict field", skill)
        self.assertIn("Exact-HEAD static inspection can establish", knowledge)
        self.assertIn("identity closure without eligible bounded diagnosis", knowledge)
        self.assertIn("artifact or ABI pairing", knowledge)

    def test_environment_setup_seals_execution_artifact_identities(self):
        skill = self.skill_text("dlc-env-setup")

        self.assertIn("PyTorch distribution/wheel/import/native extension", skill)
        self.assertIn("DLC Custom Kernel binary", skill)
        self.assertIn("unavailable identities remain explicit", skill)


if __name__ == "__main__":
    unittest.main()
