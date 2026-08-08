import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/engineering/model-adaptation/scripts/observe-python-package-identity.py"


def load_module():
    spec = importlib.util.spec_from_file_location("package_identity_provider", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PackageIdentityProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provider = load_module()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir="/tmp/kilo")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.package = self.root / "fixture_package"
        self.dist_info = self.root / "fixture_package-1.2.3.dist-info"
        self.package.mkdir()
        self.dist_info.mkdir()
        (self.package / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
        (self.package / "native.so").write_bytes(b"native-fixture\n")
        (self.dist_info / "METADATA").write_text(
            "Metadata-Version: 2.1\nName: fixture-package\nVersion: 1.2.3\n",
            encoding="utf-8",
        )
        (self.dist_info / "RECORD").write_text(
            "fixture_package/__init__.py,,\n"
            "fixture_package/native.so,,\n"
            "fixture_package-1.2.3.dist-info/METADATA,,\n"
            "fixture_package-1.2.3.dist-info/RECORD,,\n",
            encoding="utf-8",
        )

    def observe(self):
        return self.provider.observe(
            "fixture-package",
            [self.root],
            "package-fixture",
            "2026-08-08T00:00:00Z",
            "2026-08-09T00:00:00Z",
        )

    def test_reads_name_version_path_and_binaries_from_distribution_metadata(self):
        result = self.observe()
        value = result["observed_value"]
        self.assertEqual(value["name"], "fixture-package")
        self.assertEqual(value["version"], "1.2.3")
        self.assertEqual(value["path"], str(self.package))
        self.assertEqual(len(value["native_binary_digests"]), 1)
        self.assertEqual(result["subject_class"], "installed_package")
        self.assertEqual(result["authoritativeness"], "operational")
        self.assertEqual(result["status"], "not_verified")
        self.assertEqual(
            result["primary_blocker"]["code"],
            "blocked_missing_atomic_package_generation",
        )
        self.assertEqual(self.provider.CONTRACT.validate(result), [])

    def test_caller_sidecar_cannot_forge_package_metadata(self):
        (self.root / "caller-metadata.json").write_text(
            json.dumps({"name": "forged", "version": "99"}), encoding="utf-8"
        )
        result = self.observe()
        self.assertEqual(result["observed_value"]["name"], "fixture-package")
        self.assertEqual(result["observed_value"]["version"], "1.2.3")

    def test_package_metadata_path_and_binary_changes_make_prior_seal_stale(self):
        baseline = self.observe()
        for path in (
            self.package / "__init__.py",
            self.package / "native.so",
            self.dist_info / "METADATA",
            self.dist_info / "RECORD",
        ):
            with self.subTest(path=path.name):
                original = path.read_bytes()
                path.write_bytes(original + b"changed\n")
                changed = self.observe()
                self.assertNotEqual(baseline["generation"]["value"], changed["generation"]["value"])
                self.assertNotEqual(baseline["digest"], changed["digest"])
                path.write_bytes(original)

    def test_mutation_during_observation_never_produces_authoritative_pass(self):
        def mutate():
            (self.package / "native.so").write_bytes(b"mutated\n")

        result = self.provider.observe(
            "fixture-package",
            [self.root],
            "package-fixture",
            "2026-08-08T00:00:00Z",
            "2026-08-09T00:00:00Z",
            between_snapshots=mutate,
        )
        self.assertNotEqual(result["status"], "passed")
        self.assertNotEqual(result["authoritativeness"], "authoritative")
        self.assertEqual(result["primary_blocker"]["code"], "blocked_unstable_package_identity")

    def test_missing_record_or_unpaired_record_path_fails_closed(self):
        (self.dist_info / "RECORD").unlink()
        missing = self.observe()
        self.assertEqual(
            missing["primary_blocker"]["code"],
            "blocked_package_binary_pairing_unresolved",
        )

        (self.dist_info / "RECORD").write_text("../outside.so,,\n", encoding="utf-8")
        outside = self.observe()
        self.assertEqual(
            outside["primary_blocker"]["code"],
            "blocked_package_binary_pairing_unresolved",
        )

    def test_unrecorded_package_or_native_file_fails_closed(self):
        for name, content in (("injected.py", b"VALUE = 2\n"), ("hidden.so", b"native\n")):
            with self.subTest(name=name):
                path = self.package / name
                path.write_bytes(content)
                result = self.observe()
                self.assertEqual(
                    result["primary_blocker"]["code"],
                    "blocked_package_binary_pairing_unresolved",
                )
                path.unlink()

    def test_record_must_bind_itself_and_metadata(self):
        record = self.dist_info / "RECORD"
        original = record.read_text(encoding="utf-8")
        for omitted in (
            "fixture_package-1.2.3.dist-info/METADATA,,\n",
            "fixture_package-1.2.3.dist-info/RECORD,,\n",
        ):
            with self.subTest(omitted=omitted):
                record.write_text(original.replace(omitted, ""), encoding="utf-8")
                result = self.observe()
                self.assertEqual(
                    result["primary_blocker"]["code"],
                    "blocked_package_binary_pairing_unresolved",
                )
                record.write_text(original, encoding="utf-8")

    def test_other_distribution_metadata_cannot_replace_current_metadata(self):
        other = self.root / "other-1.0.dist-info"
        other.mkdir()
        (other / "METADATA").write_text("Name: other\nVersion: 1.0\n", encoding="utf-8")
        (other / "RECORD").write_text("", encoding="utf-8")
        record = self.dist_info / "RECORD"
        record.write_text(
            "fixture_package/__init__.py,,\n"
            "fixture_package/native.so,,\n"
            "other-1.0.dist-info/METADATA,,\n"
            "other-1.0.dist-info/RECORD,,\n",
            encoding="utf-8",
        )
        result = self.observe()
        self.assertEqual(
            result["primary_blocker"]["code"],
            "blocked_package_binary_pairing_unresolved",
        )

    def test_cross_distribution_record_entry_fails_closed(self):
        other = self.root / "other-1.0.dist-info"
        other.mkdir()
        (other / "entry_points.txt").write_text("[fixture]\n", encoding="utf-8")
        record = self.dist_info / "RECORD"
        record.write_text(
            record.read_text(encoding="utf-8")
            + "other-1.0.dist-info/entry_points.txt,,\n",
            encoding="utf-8",
        )
        result = self.observe()
        self.assertEqual(
            result["primary_blocker"]["code"],
            "blocked_package_binary_pairing_unresolved",
        )

    def test_unrecorded_distribution_metadata_fails_closed(self):
        extra = self.dist_info / "entry_points.txt"
        extra.write_text("[fixture]\n", encoding="utf-8")
        result = self.observe()
        self.assertEqual(
            result["primary_blocker"]["code"],
            "blocked_package_binary_pairing_unresolved",
        )

    def test_unrecorded_distribution_data_fails_closed(self):
        data = self.root / "fixture_package-1.2.3.data" / "scripts"
        data.mkdir(parents=True)
        (data / "fixture-tool").write_text("tool\n", encoding="utf-8")
        result = self.observe()
        self.assertEqual(
            result["primary_blocker"]["code"],
            "blocked_package_binary_pairing_unresolved",
        )

    def test_cross_distribution_data_record_fails_closed(self):
        data = self.root / "other-1.0.data" / "scripts"
        data.mkdir(parents=True)
        (data / "other-tool").write_text("tool\n", encoding="utf-8")
        record = self.dist_info / "RECORD"
        record.write_text(
            record.read_text(encoding="utf-8")
            + "other-1.0.data/scripts/other-tool,,\n",
            encoding="utf-8",
        )
        result = self.observe()
        self.assertEqual(
            result["primary_blocker"]["code"],
            "blocked_package_binary_pairing_unresolved",
        )

    def test_package_symlink_alias_fails_closed(self):
        real = self.package / "real.py"
        alias = self.package / "alias.py"
        real.write_text("VALUE = 1\n", encoding="utf-8")
        alias.symlink_to(real.name)
        record = self.dist_info / "RECORD"
        record.write_text(
            record.read_text(encoding="utf-8") + "fixture_package/alias.py,,\n",
            encoding="utf-8",
        )
        result = self.observe()
        self.assertEqual(
            result["primary_blocker"]["code"],
            "blocked_package_binary_pairing_unresolved",
        )

    def test_installed_cli_runs_independently_and_writes_canonical_seal(self):
        output = self.root / "package-seal.json"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "fixture-package",
                str(output),
                "--search-path",
                str(self.root),
                "--seal-id",
                "package-fixture",
                "--observed-at",
                "2026-08-08T00:00:00Z",
                "--expires-at",
                "2026-08-09T00:00:00Z",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 20, result.stderr + result.stdout)
        document = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(document["status"], "not_verified")
        self.assertEqual(self.provider.CONTRACT.validate(document), [])


if __name__ == "__main__":
    unittest.main()
