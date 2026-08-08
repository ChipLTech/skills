import hashlib
import importlib.util
import subprocess
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CANONICAL_MODULE = ROOT / "skills/engineering/chipltech-context/scripts/qualification_artifact.py"
CANONICAL_SCHEMA = ROOT / "skills/engineering/chipltech-context/contracts/qualification-artifact-envelope-v1.schema.json"
SYNC = ROOT / "scripts/sync-qualification-artifact-contracts.py"
CONSUMERS = ("diagnosing-bugs", "model-adaptation")


class GeneratedContractCopyTests(unittest.TestCase):
    def test_generated_copies_are_byte_identical_and_independently_importable(self):
        for consumer in CONSUMERS:
            with self.subTest(consumer=consumer):
                generated = ROOT / f"skills/engineering/{consumer}/scripts/_generated_contracts"
                self.assertEqual(
                    hashlib.sha256((generated / CANONICAL_MODULE.name).read_bytes()).digest(),
                    hashlib.sha256(CANONICAL_MODULE.read_bytes()).digest(),
                )
                self.assertEqual(
                    hashlib.sha256((generated / CANONICAL_SCHEMA.name).read_bytes()).digest(),
                    hashlib.sha256(CANONICAL_SCHEMA.read_bytes()).digest(),
                )
                script = (
                    "import importlib.util; "
                    f"p={str(generated / CANONICAL_MODULE.name)!r}; "
                    "s=importlib.util.spec_from_file_location('bundled', p); "
                    "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
                    "assert m.ENVELOPE_VERSION == 'qualification-artifact-envelope/v1'"
                )
                result = subprocess.run(
                    [sys.executable, "-I", "-c", script], capture_output=True, text=True
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_sync_check_detects_no_digest_drift(self):
        result = subprocess.run(
            [sys.executable, str(SYNC), "--check"], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_sync_check_rejects_digest_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            canonical_contracts = root / "skills/engineering/chipltech-context/contracts"
            canonical_scripts = root / "skills/engineering/chipltech-context/scripts"
            canonical_contracts.mkdir(parents=True)
            canonical_scripts.mkdir(parents=True)
            shutil.copyfile(CANONICAL_SCHEMA, canonical_contracts / CANONICAL_SCHEMA.name)
            shutil.copyfile(CANONICAL_MODULE, canonical_scripts / CANONICAL_MODULE.name)
            generated = root / "skills/engineering/diagnosing-bugs/scripts/_generated_contracts"
            generated.mkdir(parents=True)
            (generated / CANONICAL_SCHEMA.name).write_bytes(CANONICAL_SCHEMA.read_bytes())
            (generated / CANONICAL_MODULE.name).write_text("drift\n")

            result = subprocess.run(
                [sys.executable, str(SYNC), "--check", "--root", str(root)],
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("generated contract drift", result.stderr)


if __name__ == "__main__":
    unittest.main()
