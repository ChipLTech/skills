import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LINKER = ROOT / "scripts" / "link-kilo-skills.sh"
OWNERSHIP_MARKER = "kilo-generated-wrapper: mattpocock-skills/link-kilo-skills.sh/v2"


class KiloLinkerSafetyTests(unittest.TestCase):
    def run_linker(self, project: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(LINKER), "--project", str(project), "--with-commands", *extra],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_default_install_links_ticket07_skills_and_wrappers(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            project = Path(directory)
            result = self.run_linker(project)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            for identity in ("model-adaptation", "main-to-main-upgrade"):
                skill = project / ".kilo" / "skills" / identity
                command = project / ".kilo" / "command" / f"{identity}.md"
                self.assertTrue(skill.is_dir(), identity)
                self.assertFalse(skill.is_symlink(), identity)
                self.assertEqual(
                    (skill / ".kilo-link-source").read_text(encoding="utf-8"),
                    str(ROOT / "skills" / "engineering" / identity) + "\n",
                )
                self.assertTrue((skill / "SKILL.md").is_file(), identity)
                wrapper = command.read_text(encoding="utf-8")
                self.assertIn(OWNERSHIP_MARKER, wrapper)
                self.assertIn(f"请使用 `{identity}` skill", wrapper)
                self.assertIn("$ARGUMENTS", wrapper)

    def test_linker_is_idempotent_for_owned_install(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            project = Path(directory)
            first = self.run_linker(project)
            before = self.inventory(project / ".kilo")
            second = self.run_linker(project)
            after = self.inventory(project / ".kilo")

            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
            self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
            self.assertEqual(before, after)

    def test_owned_project_skill_directory_refreshes_from_source(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            project = Path(directory)
            first = self.run_linker(project)
            skill = project / ".kilo" / "skills" / "model-adaptation"
            expected = (ROOT / "skills" / "engineering" / "model-adaptation" / "SKILL.md").read_text(encoding="utf-8")
            (skill / "SKILL.md").write_text("stale copy\n", encoding="utf-8")

            second = self.run_linker(project)

            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
            self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
            self.assertEqual((skill / "SKILL.md").read_text(encoding="utf-8"), expected)

    def test_custom_dest_without_commands_does_not_require_command_dest(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            destination = Path(directory) / "skills"

            result = subprocess.run(
                [str(LINKER), "--dest", str(destination)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertTrue((destination / "model-adaptation").is_symlink())
            self.assertFalse((Path(directory) / "command").exists())

    def test_existing_real_skill_directory_and_custom_command_survive(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            project = Path(directory)
            skill = project / ".kilo" / "skills" / "model-adaptation"
            command = project / ".kilo" / "command" / "model-adaptation.md"
            skill.mkdir(parents=True)
            command.parent.mkdir(parents=True)
            command.write_text("custom command\n", encoding="utf-8")

            result = self.run_linker(project)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertTrue(skill.is_dir())
            self.assertFalse(skill.is_symlink())
            self.assertEqual(command.read_text(encoding="utf-8"), "custom command\n")

    def test_symlinked_destination_chain_fails_closed(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            root = Path(directory)
            project = root / "project"
            outside = root / "outside"
            project.mkdir()
            outside.mkdir()
            (project / ".kilo").symlink_to(outside, target_is_directory=True)

            result = self.run_linker(project)

            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertFalse((outside / "skills" / "model-adaptation").exists())

    @staticmethod
    def inventory(root: Path) -> list[tuple[str, str, str]]:
        rows = []
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                rows.append((relative, "symlink", os.readlink(path)))
            elif path.is_file():
                rows.append((relative, "file", path.read_text(encoding="utf-8")))
            elif path.is_dir():
                rows.append((relative, "directory", ""))
        return rows


if __name__ == "__main__":
    unittest.main()
