import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/engineering/chipltech-context/scripts/repository_guard.py"


def load_guard():
    spec = importlib.util.spec_from_file_location("repository_guard", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


GUARD = load_guard()


class RepositoryGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir="/tmp/kilo")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "authoritative"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "identity.txt").write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "identity.txt"], check=True)
        subprocess.run(
            ["git", "-C", str(self.root), "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"],
            check=True,
        )

    def test_injected_temporary_git_root_is_authoritative(self):
        result = GUARD.repository_snapshot(self.root)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["canonical_root"], str(self.root.resolve()))
        self.assertEqual(len(result["head"]), 40)
        self.assertFalse(result["dirty"])

    def test_nested_and_missing_roots_fail_closed(self):
        nested = self.root / "nested"
        nested.mkdir()
        self.assertEqual(
            GUARD.repository_snapshot(nested)["blocker"],
            "blocked_non_authoritative_repository_root",
        )
        self.assertEqual(
            GUARD.repository_snapshot(self.root / "absent")["blocker"],
            "blocked_missing_repository",
        )

    def test_dirty_state_changes_snapshot_identity(self):
        before = GUARD.repository_snapshot(self.root)
        (self.root / "identity.txt").write_text("changed\n", encoding="utf-8")
        after = GUARD.repository_snapshot(self.root)
        self.assertFalse(before["dirty"])
        self.assertTrue(after["dirty"])
        self.assertNotEqual(before["status_digest"], after["status_digest"])
        (self.root / "identity.txt").write_text("changed again\n", encoding="utf-8")
        changed_again = GUARD.repository_snapshot(self.root)
        self.assertNotEqual(after["status_digest"], changed_again["status_digest"])

    def test_untracked_content_changes_snapshot_identity(self):
        path = self.root / "untracked.txt"
        path.write_text("one\n", encoding="utf-8")
        first = GUARD.repository_snapshot(self.root)
        path.write_text("two\n", encoding="utf-8")
        second = GUARD.repository_snapshot(self.root)
        self.assertNotEqual(first["status_digest"], second["status_digest"])

    def test_untracked_symlink_hashes_link_target_without_dereference(self):
        first_target = self.root / "first.txt"
        second_target = self.root / "second.txt"
        first_target.write_text("same\n", encoding="utf-8")
        second_target.write_text("same\n", encoding="utf-8")
        link = self.root / "link"
        link.symlink_to(first_target.name)
        first = GUARD.repository_snapshot(self.root)
        link.unlink()
        link.symlink_to(second_target.name)
        second = GUARD.repository_snapshot(self.root)
        self.assertNotEqual(first["status_digest"], second["status_digest"])
        link.unlink()
        link.symlink_to("missing.txt")
        broken = GUARD.repository_snapshot(self.root)
        self.assertTrue(broken["dirty"])


if __name__ == "__main__":
    unittest.main()
