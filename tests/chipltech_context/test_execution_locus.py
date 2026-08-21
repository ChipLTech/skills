import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTEXT = (ROOT / "CONTEXT.md").read_text(encoding="utf-8")
ROUTER = (
    ROOT / "skills/engineering/chipltech-context/SKILL.md"
).read_text(encoding="utf-8")
MODEL_ADAPTATION = (
    ROOT / "skills/engineering/model-adaptation/SKILL.md"
).read_text(encoding="utf-8")
SCRIPT = ROOT / "skills/engineering/chipltech-context/scripts/execution_locus.py"


def load_classifier():
    spec = importlib.util.spec_from_file_location("execution_locus", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


CLASSIFIER = load_classifier()


class ExecutionLocusContractTests(unittest.TestCase):
    def test_global_context_binds_paths_to_an_execution_locus(self):
        self.assertIn("execution locus + absolute path", CONTEXT)
        self.assertIn("Host absence of a container coordinate", CONTEXT)
        self.assertIn("unmet test harness/container precondition", CONTEXT)

    def test_router_does_not_reclassify_host_lookup_as_missing_asset(self):
        self.assertIn("/work/...", ROUTER)
        self.assertIn("blocked_missing_container_contract", ROUTER)
        self.assertIn("not repository or model absence", ROUTER)
        self.assertIn("lookalike Host path is not a substitute", ROUTER)

    def test_model_preflight_distinguishes_container_and_mount_identity(self):
        self.assertIn("Container Execution Contract", MODEL_ADAPTATION)
        self.assertIn("Host absence does not establish asset absence", MODEL_ADAPTATION)
        self.assertIn("image-internal and container-volume assets", MODEL_ADAPTATION)

    def test_unavailable_container_path_does_not_become_missing_asset(self):
        result = CLASSIFIER.classify_path("container", "/work/vllm")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["blocker"], "blocked_missing_container_contract")
        self.assertEqual(result["asset_state"], "not_verified")
        self.assertEqual(result["repository_state"], "not_verified")

    def test_host_path_and_container_mount_are_distinct_coordinates(self):
        host = CLASSIFIER.classify_path("host", "/home/user/vllm")
        container = CLASSIFIER.classify_path(
            "container",
            "/work/vllm",
            container_available=True,
            mount_source="/home/user/vllm",
        )
        self.assertEqual(host["path_coordinate"]["execution_locus"], "host")
        self.assertEqual(
            container["path_coordinate"]["execution_locus"], "container"
        )
        self.assertEqual(
            container["mount_mapping"]["host_source"], "/home/user/vllm"
        )


if __name__ == "__main__":
    unittest.main()
