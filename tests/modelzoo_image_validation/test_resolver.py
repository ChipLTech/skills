import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "skills/engineering/modelzoo-image-validation/scripts/resolve-modelzoo.py"
FIXTURES = Path(__file__).with_name("fixtures")


class ModelZooResolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(dir="/tmp/kilo")
        cls.workspace = Path(cls.temporary.name)
        cls.roots = {}
        for source in sorted(path for path in FIXTURES.iterdir() if path.is_dir()):
            target = cls.workspace / source.name
            shutil.copytree(source, target)
            cls.roots[source.name] = target
            cls.git(target, "init", "--quiet")
            cls.git(target, "remote", "add", "origin", f"file://{target}")
            cls.git(target, "add", ".")
            cls.git(target, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "fixture")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @staticmethod
    def git(root, *arguments):
        return subprocess.run(["git", "-C", str(root), *arguments], capture_output=True, text=True, check=True)

    def run_cli(self, fixture, model, *extra):
        return subprocess.run(
            [sys.executable, str(CLI), "--modelzoo-root", str(self.roots[fixture]), "--model", model, *extra],
            capture_output=True,
            text=True,
            check=False,
        )

    def report(self, fixture, model, *extra):
        result = self.run_cli(fixture, model, *extra)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def test_complete_reference_is_deterministic(self):
        first = self.run_cli("complete zoo", "Complete-7B", "--framework", "vllm")
        second = self.run_cli("complete zoo", "Complete-7B", "--framework", "vllm")
        self.assertEqual(first.stdout, second.stdout)
        report = json.loads(first.stdout)
        self.assertEqual(report["schema"], "modelzoo-reference-record/v1")
        self.assertEqual(report["reference_status"], "modelzoo_reference_resolved")
        self.assertEqual(report["functional_effect"], "none")
        self.assertEqual(report["reference_id"], self.reference_digest(report))

    def test_missing_and_ambiguous_are_nonblocking_reference_states(self):
        missing = self.report("complete zoo", "Absent")
        ambiguous = self.report("ambiguous", "Duplicate")
        selected = self.report("ambiguous", "Duplicate", "--framework", "vllm")
        self.assertEqual(missing["reference_status"], "modelzoo_reference_unavailable")
        self.assertEqual(ambiguous["reference_status"], "modelzoo_reference_ambiguous")
        self.assertEqual(selected["selection"]["framework"], "vllm")
        self.assertNotEqual(selected["reference_status"], "modelzoo_reference_ambiguous")

    def test_malformed_and_infer_false_are_reference_states(self):
        malformed = self.report("malformed", "Broken", "--framework", "vllm")
        alias = self.report("unsafe-yaml", "Unsafe", "--framework", "vllm")
        noncanonical = self.report("noncanonical-bool", "Noncanonical", "--framework", "vllm")
        wrong_type = self.report("wrong-type", "Wrong-Type", "--framework", "vllm")
        infer_false = self.report("infer-false", "No-Infer", "--framework", "vllm")
        self.assertEqual(malformed["reference_status"], "modelzoo_reference_malformed")
        self.assertEqual(alias["reference_status"], "modelzoo_reference_malformed")
        self.assertEqual(noncanonical["reference_status"], "modelzoo_reference_malformed")
        self.assertEqual(wrong_type["reference_status"], "modelzoo_reference_malformed")
        self.assertEqual(infer_false["reference_status"], "modelzoo_reference_incomplete")
        self.assertIn("historical_modelzoo_negative_claim", infer_false["reference"]["diagnostics"])

    def test_readme_absence_and_sparse_content_are_incomplete(self):
        absent = self.report("readme-absent", "No-Readme", "--framework", "vllm")
        sparse = self.report("missing-readme-fields", "Sparse", "--framework", "vllm")
        self.assertEqual(absent["reference_status"], "modelzoo_reference_incomplete")
        self.assertIsNone(absent["reference"]["readme"]["path"])
        self.assertEqual(sparse["reference_status"], "modelzoo_reference_incomplete")

    def test_sensitive_values_and_remote_credentials_are_not_serialized(self):
        readme = self.roots["sensitive"] / "vllm/models/Sensitive/README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\nexport API_KEY=another-secret\n", encoding="utf-8")
        self.git(self.roots["sensitive"], "add", ".")
        self.git(self.roots["sensitive"], "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "sensitive")
        self.git(self.roots["sensitive"], "remote", "set-url", "origin", "https://user:super-secret@example.invalid/ModelZoo.git")
        serialized = json.dumps(self.report("sensitive", "Sensitive", "--framework", "vllm"))
        self.assertNotIn("super-secret", serialized)
        self.assertNotIn("another-secret", serialized)
        self.assertNotIn("192.168.1.20", serialized)
        self.assertIn("<redacted>", serialized)

    def test_source_tree_remains_byte_identical(self):
        before = self.tree_digest(self.roots["complete zoo"])
        self.report("complete zoo", "Complete-7B", "--framework", "vllm")
        self.assertEqual(before, self.tree_digest(self.roots["complete zoo"]))

    def test_non_git_root_is_incomplete_reference_not_runtime_blocker(self):
        root = self.workspace / "plain-zoo"
        shutil.copytree(self.roots["complete zoo"], root)
        shutil.rmtree(root / ".git")
        result = subprocess.run(
            [sys.executable, str(CLI), "--modelzoo-root", str(root), "--model", "Complete-7B", "--framework", "vllm"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(report["reference_status"], "modelzoo_reference_incomplete")
        self.assertIn("modelzoo_git_identity_unavailable", report["reference"]["diagnostics"])

    @staticmethod
    def reference_digest(document):
        modelzoo = document["modelzoo"]
        payload = {
            "inputs": document["inputs"],
            "modelzoo": {key: modelzoo[key] for key in ("available", "remote", "branch_or_tag", "head")},
            "candidates": document["candidates"],
            "selection": document["selection"],
            "reference": document["reference"],
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def tree_digest(root):
        digest = hashlib.sha256()
        for path in sorted(path for path in root.rglob("*") if path.is_file() and ".git" not in path.parts):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()


if __name__ == "__main__":
    unittest.main()
