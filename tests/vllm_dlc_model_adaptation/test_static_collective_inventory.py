import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/engineering/model-adaptation/scripts/inventory-vllm-dlc-collectives.py"


def load_module():
    spec = importlib.util.spec_from_file_location("static_collective_inventory", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


INVENTORY = load_module()


class StaticCollectiveInventoryTests(unittest.TestCase):
    def test_current_snapshot_records_fail_closed_routes_and_moe_callers(self):
        result = INVENTORY.inventory(Path("/work/vllm"))
        rows = {row["primitive"]: row for row in result["primitives"]}
        for primitive in ("reduce_scatter", "reduce_scatter_v", "all_gather_v"):
            self.assertTrue(rows[primitive]["fail_closed_unimplemented"])
        self.assertTrue(result["moe_callers"]["all_gather_v"])
        self.assertTrue(result["moe_callers"]["reduce_scatter_v"])
        self.assertTrue(result["moe_callers"]["all_to_all_manager"])
        rows = {row["primitive"] for row in result["primitives"]}
        self.assertIn("all_gather_into_tensor", rows)
        self.assertIn("all_to_all", rows)
        self.assertTrue(all(layer["status"] == "blocked" for layer in result["layers"]))
        self.assertEqual(result["evidence_class"], "static_snapshot")
        self.assertFalse(result["acceptance_eligible"])
        self.assertTrue(result["claim_boundary"].startswith("Claim Boundary:"))

    def test_same_source_bytes_produce_same_digest(self):
        first = INVENTORY.inventory(Path("/work/vllm"))
        second = INVENTORY.inventory(Path("/work/vllm"))
        self.assertEqual(first, second)

    def test_cross_repository_layers_are_static_and_binary_pairing_blocked(self):
        result = INVENTORY.inventory(
            Path("/work/vllm"), Path("/work/pytorch"), Path("/work/DLC_CL"),
            Path("/work/DLC_Custom_Kernel"),
        )
        self.assertEqual({row["layer"] for row in result["layers"]}, {
            "pytorch_process_group", "native_dlc_cl", "custom_kernel"
        })
        self.assertTrue(all(row["blocker"] == "blocked_binary_pairing_unresolved" for row in result["layers"]))


if __name__ == "__main__":
    unittest.main()
