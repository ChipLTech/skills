import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/engineering/model-adaptation/scripts/attest-vllm-dlc-qualification.py"
FIXTURE = Path(__file__).with_name("fixtures") / "distributed-collective" / "qualified-controlled-template.json"


def load_module():
    spec = importlib.util.spec_from_file_location("qualification_attester", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


ATTESTER = load_module()


class QualificationAttesterTests(unittest.TestCase):
    def test_controlled_or_blocked_artifact_cannot_be_attested(self):
        artifact = json.loads(FIXTURE.read_text(encoding="utf-8"))
        artifact["digest"] = ATTESTER.VALIDATOR.artifact_digest(artifact)
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            root = Path(directory)
            artifact_path = root / "artifact.json"
            identity_path = root / "identity.json"
            collector_spec_path = root / "collector-spec.json"
            artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
            identity_path.write_text(json.dumps(artifact["subject_identity"]), encoding="utf-8")
            collector_spec_path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "blocked_invalid_live_identity_artifact"):
                ATTESTER.attest(
                    artifact_path, identity_path, collector_spec_path,
                    ["all_reduce", "moe_dispatch", "moe_combine"], 2,
                )


if __name__ == "__main__":
    unittest.main()
