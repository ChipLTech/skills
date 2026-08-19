import datetime
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/engineering/model-adaptation/scripts/collect-vllm-cl-live-identity.py"
ATTESTER_SCRIPT = ROOT / "skills/engineering/model-adaptation/scripts/attest-vllm-cl-qualification.py"
PACKAGE_PROVIDER_SCRIPT = ROOT / "skills/engineering/model-adaptation/scripts/observe-python-package-identity.py"


def load_module():
    spec = importlib.util.spec_from_file_location("live_identity_collector", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_attester():
    spec = importlib.util.spec_from_file_location("live_identity_attester", ATTESTER_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_package_provider():
    spec = importlib.util.spec_from_file_location("package_identity_provider_fixture", PACKAGE_PROVIDER_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class LiveIdentityCollectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.collector = load_module()
        cls.attester = load_attester()
        cls.package_provider = load_package_provider()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir="/tmp/kilo")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.source)], check=True)
        (self.source / "source.txt").write_text("source\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.source), "add", "source.txt"], check=True)
        subprocess.run([
            "git", "-C", str(self.source), "-c", "user.name=fixture", "-c",
            "user.email=fixture@example.invalid", "commit", "-qm", "fixture",
        ], check=True)
        self.paths = {}
        for name in (
            "package", "native", "image", "runtime", "driver", "toolchain",
            "model", "tokenizer", "processor", "workload", "topology", "policy",
        ):
            path = self.root / name
            path.write_text(name + "\n", encoding="utf-8")
            self.paths[name] = str(path)
        self.metadata = {}
        metadata_values = {
            "package": {"name": "vllm", "version": "1.0"},
            "image": {"image_id": "image-fixture"},
            "runtime": {"name": "DLC Runtime", "version": "1"},
            "driver": {"name": "dlc-thunk", "version": "1"},
            "toolchain": {"name": "toolchain", "version": "1"},
            "model": {"model_id": "model", "revision": "rev"},
            "tokenizer": {"revision": "rev"},
            "processor": {"revision": "rev"},
            "hardware": {"generation": "DLC Chip"},
            "policy": {"policy_id": "distributed", "version": "v1"},
        }
        for name, value in metadata_values.items():
            path = self.root / f"{name}-metadata.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            self.metadata[name] = str(path)

    def spec(self):
        return {
            "schema_version": "vllm-cl-live-identity-collector-spec/v1",
            "artifact_id": "live-identity-fixture",
            "created_at": "2026-08-08T00:00:00Z",
            "source": {"kind": "git", "root": str(self.source)},
            "installed_package": {"name": "vllm", "version": "1.0", "path": self.paths["package"], "metadata_path": self.metadata["package"]},
            "native_binary": {"path": self.paths["native"]},
            "image": {"image_id": "image-fixture", "identity_path": self.paths["image"], "metadata_path": self.metadata["image"]},
            "runtime": {"name": "DLC Runtime", "version": "1", "path": self.paths["runtime"], "metadata_path": self.metadata["runtime"]},
            "driver": {"name": "dlc-thunk", "version": "1", "path": self.paths["driver"], "metadata_path": self.metadata["driver"]},
            "toolchain": {"name": "toolchain", "version": "1", "path": self.paths["toolchain"], "metadata_path": self.metadata["toolchain"]},
            "model": {"model_id": "model", "revision": "rev", "path": self.paths["model"], "metadata_path": self.metadata["model"]},
            "tokenizer": {"revision": "rev", "path": self.paths["tokenizer"], "metadata_path": self.metadata["tokenizer"]},
            "processor": {"revision": "rev", "path": self.paths["processor"], "metadata_path": self.metadata["processor"]},
            "workload": {"path": self.paths["workload"]},
            "hardware": {"generation": "DLC Chip", "topology_path": self.paths["topology"], "metadata_path": self.metadata["hardware"]},
            "capability_policy": {"policy_id": "distributed", "version": "v1", "path": self.paths["policy"], "metadata_path": self.metadata["policy"]},
        }

    def test_collects_complete_closed_world_identity(self):
        result = self.collector.collect(self.spec())
        self.assertEqual(result["status"], "not_verified")
        self.assertEqual(result["primary_blocker"]["code"], "blocked_non_atomic_identity_snapshot")
        self.assertEqual(result["evidence_class"], "operational_only")
        self.assertEqual(result["authoritativeness"], "non_authoritative")
        self.assertEqual(self.collector.CONTRACT.validate_envelope(result, ("collection",)), [])
        self.assertTrue(result["claim_boundary"].startswith("Claim Boundary:"))
        self.assertEqual(set(result["subject_identity"]), set(self.collector.CONTRACT.IDENTITY_FIELDS))

    def test_each_identity_byte_change_makes_prior_collector_stale(self):
        first = self.collector.collect(self.spec())
        identity_paths = (
            "package", "native", "image", "runtime", "driver", "toolchain",
            "model", "tokenizer", "processor", "workload", "topology", "policy",
        )
        for name in identity_paths:
            with self.subTest(name=name):
                path = Path(self.paths[name])
                original = path.read_text(encoding="utf-8")
                path.write_text(original + "changed\n", encoding="utf-8")
                changed = self.collector.collect(self.spec())
                blockers = self.collector.CONTRACT.stale_identity_blockers(
                    first["subject_identity"], changed["subject_identity"]
                )
                self.assertTrue(blockers, name)
                path.write_text(original, encoding="utf-8")

    def test_source_commit_and_each_metadata_change_make_prior_collector_stale(self):
        first = self.collector.collect(self.spec())
        (self.source / "source.txt").write_text("next source\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.source), "add", "source.txt"], check=True)
        subprocess.run([
            "git", "-C", str(self.source), "-c", "user.name=fixture", "-c",
            "user.email=fixture@example.invalid", "commit", "-qm", "next",
        ], check=True)
        changed_source = self.collector.collect(self.spec())
        self.assertTrue(self.collector.CONTRACT.stale_identity_blockers(
            first["subject_identity"], changed_source["subject_identity"]
        ))

        baseline = changed_source
        for name, metadata_path in self.metadata.items():
            with self.subTest(metadata=name):
                path = Path(metadata_path)
                original = path.read_text(encoding="utf-8")
                document = json.loads(original)
                key = sorted(document)[0]
                document[key] = str(document[key]) + "-changed"
                path.write_text(json.dumps(document), encoding="utf-8")
                result = self.collector.collect(self.spec())
                self.assertEqual(
                    result["primary_blocker"]["code"],
                    "blocked_identity_metadata_mismatch",
                )
                path.write_text(original, encoding="utf-8")

    def test_dirty_git_and_missing_identity_fail_closed(self):
        (self.source / "source.txt").write_text("dirty\n", encoding="utf-8")
        dirty = self.collector.collect(self.spec())
        self.assertEqual(dirty["status"], "blocked")
        self.assertEqual(dirty["primary_blocker"]["code"], "blocked_dirty_source_repository")

        missing_spec = self.spec()
        del missing_spec["native_binary"]
        missing = self.collector.collect(missing_spec)
        self.assertEqual(missing["status"], "blocked")
        self.assertEqual(missing["primary_blocker"]["code"], "blocked_missing_collector_input")
        self.assertEqual(
            self.collector.CONTRACT.validate_envelope(missing, ("collection",)), []
        )

    def test_skip_worktree_cannot_hide_source_drift(self):
        subprocess.run([
            "git", "-C", str(self.source), "update-index", "--skip-worktree",
            "source.txt",
        ], check=True)
        (self.source / "source.txt").write_text("hidden drift\n", encoding="utf-8")
        result = self.collector.collect(self.spec())
        self.assertEqual(result["primary_blocker"]["code"], "blocked_dirty_source_repository")

    def test_source_submodule_requires_independent_identity(self):
        subprocess.run([
            "git", "-C", str(self.source), "update-index", "--add", "--cacheinfo",
            "160000," + "1" * 40 + ",vendor",
        ], check=True)
        subprocess.run([
            "git", "-C", str(self.source), "-c", "user.name=fixture", "-c",
            "user.email=fixture@example.invalid", "commit", "-qm", "gitlink",
        ], check=True)
        result = self.collector.collect(self.spec())
        self.assertEqual(result["primary_blocker"]["code"], "blocked_source_submodule_identity")

    def test_static_snapshot_is_never_operational(self):
        spec = self.spec()
        spec["source"] = {"kind": "static_snapshot", "root": str(self.source)}
        result = self.collector.collect(spec)
        self.assertEqual(result["status"], "not_verified")
        self.assertEqual(result["evidence_class"], "static_snapshot")
        self.assertEqual(result["authoritativeness"], "non_authoritative")
        self.assertFalse(result["acceptance_eligible"])

    def test_unknown_field_and_symlink_target_drift_are_deterministic(self):
        unknown = self.spec()
        unknown["surprise"] = True
        result = self.collector.collect(unknown)
        self.assertEqual(result["primary_blocker"]["code"], "blocked_unknown_collector_field")

        first_target = self.root / "first"
        second_target = self.root / "second"
        first_target.write_text("same\n", encoding="utf-8")
        second_target.write_text("same\n", encoding="utf-8")
        link = self.root / "package-link"
        link.symlink_to(first_target.name)
        spec = self.spec()
        spec["installed_package"]["path"] = str(link)
        first = self.collector.collect(spec)
        link.unlink()
        link.symlink_to(second_target.name)
        second = self.collector.collect(spec)
        self.assertNotEqual(
            first["subject_identity"]["installed_package"]["digest"],
            second["subject_identity"]["installed_package"]["digest"],
        )

    def test_directory_framing_and_symlink_boundaries_fail_closed(self):
        first_tree = self.root / "tree-a"
        second_tree = self.root / "tree-b"
        first_tree.mkdir()
        second_tree.mkdir()
        (first_tree / "a").write_bytes(b"x\0F\0./b\0y")
        (second_tree / "a").write_bytes(b"x")
        (second_tree / "b").write_bytes(b"y")
        self.assertNotEqual(
            self.collector._path_digest(str(first_tree), "$.fixture")[1],
            self.collector._path_digest(str(second_tree), "$.fixture")[1],
        )

        cycle = self.root / "cycle"
        cycle.mkdir()
        (cycle / "self").symlink_to(".")
        spec = self.spec()
        spec["installed_package"]["path"] = str(cycle)
        result = self.collector.collect(spec)
        self.assertEqual(result["primary_blocker"]["code"], "blocked_identity_symlink_cycle")

        outside = self.root.parent / "outside-live-identity"
        outside.write_text("outside\n", encoding="utf-8")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        escape = self.root / "escape"
        escape.symlink_to(outside)
        spec = self.spec()
        spec["installed_package"]["path"] = str(escape)
        result = self.collector.collect(spec)
        self.assertEqual(result["primary_blocker"]["code"], "blocked_identity_symlink_escape")

    def test_invalid_scalar_or_metadata_mismatch_never_passes(self):
        invalid = self.spec()
        invalid["artifact_id"] = ""
        result = self.collector.collect(invalid)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["primary_blocker"]["code"], "blocked_invalid_collected_identity")

        mismatch = self.spec()
        mismatch["runtime"]["version"] = "other"
        result = self.collector.collect(mismatch)
        self.assertEqual(result["primary_blocker"]["code"], "blocked_identity_metadata_mismatch")

    def test_attester_recollects_live_identity_and_rejects_replay(self):
        spec = self.spec()
        collected = self.collector.collect(spec)
        artifact_path = self.root / "collected.json"
        spec_path = self.root / "collector-spec.json"
        artifact_path.write_text(json.dumps(collected), encoding="utf-8")
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        identity = self.attester.validate_live_identity(artifact_path, spec_path)
        self.assertEqual(identity, collected["subject_identity"])

        Path(self.paths["runtime"]).write_text("runtime changed\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "blocked_stale_live_identity"):
            self.attester.validate_live_identity(artifact_path, spec_path)

    def test_attester_rejects_static_snapshot_and_tampered_collector(self):
        spec = self.spec()
        spec["source"] = {"kind": "static_snapshot", "root": str(self.source)}
        collected = self.collector.collect(spec)
        artifact_path = self.root / "collected.json"
        spec_path = self.root / "collector-spec.json"
        artifact_path.write_text(json.dumps(collected), encoding="utf-8")
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "blocked_non_operational_live_identity"):
            self.attester.validate_live_identity(artifact_path, spec_path)

        live_spec = self.spec()
        live = self.collector.collect(live_spec)
        live["subject_identity"]["runtime"]["version"] = "tampered"
        artifact_path.write_text(json.dumps(live), encoding="utf-8")
        spec_path.write_text(json.dumps(live_spec), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "blocked_invalid_live_identity_artifact"):
            self.attester.validate_live_identity(artifact_path, spec_path)

    def test_consumes_reobserved_package_provider_seal_without_upgrading_authority(self):
        package = self.root / "provider_package"
        dist_info = self.root / "provider_package-2.0.dist-info"
        package.mkdir()
        dist_info.mkdir()
        (package / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
        (package / "native.so").write_bytes(b"native\n")
        (dist_info / "METADATA").write_text(
            "Metadata-Version: 2.1\nName: provider-package\nVersion: 2.0\n",
            encoding="utf-8",
        )
        (dist_info / "RECORD").write_text(
            "provider_package/__init__.py,,\n"
            "provider_package/native.so,,\n"
            "provider_package-2.0.dist-info/METADATA,,\n"
            "provider_package-2.0.dist-info/RECORD,,\n",
            encoding="utf-8",
        )
        seal = self.package_provider.observe(
            "provider-package", [self.root], "provider-package-seal",
            "2026-08-08T00:00:00Z", "2026-08-09T00:00:00Z",
        )
        seal_path = self.root / "package-provider-seal.json"
        seal_path.write_text(json.dumps(seal), encoding="utf-8")
        spec = self.spec()
        spec["installed_package"] = {
            "provider_seal_path": str(seal_path),
            "package_name": "provider-package",
            "search_paths": [str(self.root)],
        }

        clock_calls = []

        def valid_clock():
            clock_calls.append(None)
            return datetime.datetime(
                2026, 8, 8, 12, tzinfo=datetime.timezone.utc
            )

        result = self.collector.collect(spec, clock=valid_clock)

        self.assertEqual(result["status"], "not_verified")
        self.assertEqual(result["authoritativeness"], "non_authoritative")
        self.assertFalse(result["acceptance_eligible"])
        self.assertEqual(result["subject_identity"]["installed_package"]["name"], "provider-package")
        self.assertIn(seal["digest"], result["input_artifact_digests"])
        self.assertEqual(len(clock_calls), 1)

        (package / "native.so").write_bytes(b"changed\n")
        stale = self.collector.collect(spec, clock=valid_clock)
        self.assertEqual(stale["status"], "blocked")
        self.assertEqual(stale["primary_blocker"]["code"], "blocked_stale_package_provider_seal")

        expired = self.package_provider.observe(
            "provider-package", [self.root], "expired-package-seal",
            "2026-08-06T00:00:00Z", "2026-08-07T00:00:00Z",
        )
        seal_path.write_text(json.dumps(expired), encoding="utf-8")
        expired_result = self.collector.collect(spec, clock=valid_clock)
        self.assertEqual(expired_result["status"], "blocked")
        self.assertEqual(
            expired_result["primary_blocker"]["code"],
            "blocked_expired_package_provider_seal",
        )

        future = self.package_provider.observe(
            "provider-package", [self.root], "future-package-seal",
            "2099-08-06T00:00:00Z", "2099-08-07T00:00:00Z",
        )
        seal_path.write_text(json.dumps(future), encoding="utf-8")
        future_result = self.collector.collect(spec, clock=valid_clock)
        self.assertEqual(future_result["status"], "blocked")
        self.assertEqual(
            future_result["primary_blocker"]["code"],
            "blocked_future_package_provider_observation",
        )

        exact_expiry = self.package_provider.observe(
            "provider-package", [self.root], "exact-expiry-package-seal",
            "2026-08-08T00:00:00Z", "2026-08-08T12:00:00Z",
        )
        seal_path.write_text(json.dumps(exact_expiry), encoding="utf-8")
        exact_expiry_result = self.collector.collect(spec, clock=valid_clock)
        self.assertEqual(exact_expiry_result["status"], "blocked")
        self.assertEqual(
            exact_expiry_result["primary_blocker"]["code"],
            "blocked_expired_package_provider_seal",
        )

    def test_cli_does_not_expose_a_clock_rollback_option(self):
        result = subprocess.run(
            ["python3", str(SCRIPT), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertNotIn("--now", result.stdout)

    def test_invalid_library_clock_fails_closed(self):
        for clock in (
            lambda: datetime.datetime(2026, 8, 8),
            lambda: "2026-08-08T00:00:00Z",
            lambda: (_ for _ in ()).throw(RuntimeError("clock failed")),
        ):
            with self.subTest(clock=clock):
                result = self.collector.collect(self.spec(), clock=clock)
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(
                    result["primary_blocker"]["code"],
                    "blocked_invalid_clock_context",
                )


if __name__ == "__main__":
    unittest.main()
