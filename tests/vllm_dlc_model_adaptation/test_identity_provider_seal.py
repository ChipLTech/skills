import datetime
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "skills/engineering/model-adaptation/scripts/identity_provider_seal.py"


def load_module():
    spec = importlib.util.spec_from_file_location("identity_provider_seal", MODULE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class IdentityProviderSealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = load_module()

    def seal(self):
        provider_identity = self.contract.expected_provider_identity(
            self.contract.PACKAGE_PROVIDER_ID,
            self.contract.PACKAGE_PROVIDER_VERSION,
        )
        return self.contract.seal({
            "schema_version": "vllm-dlc-identity-provider-seal/v1",
            "seal_id": "package-fixture",
            "provider": {
                "id": "model-adaptation/python-package-identity-provider",
                "version": "1.0.0",
                "identity_digest": provider_identity,
            },
            "subject_class": "installed_package",
            "observed_value": {
                "name": "fixture-package",
                "version": "1.2.3",
                "path": "/immutable/package",
                "digest": "sha256:" + "2" * 64,
                "native_binary_digests": [],
            },
            "generation": {
                "kind": "transaction_id",
                "value": "fixture-generation-1",
                "atomic": True,
            },
            "observed_at": "2026-08-08T00:00:00Z",
            "expires_at": "2026-08-09T00:00:00Z",
            "raw_evidence_digest": "sha256:" + "3" * 64,
            "authoritativeness": "authoritative",
            "status": "passed",
            "blockers": [],
            "primary_blocker": None,
            "claim_boundary": "Claim Boundary: package identity only.",
            "unverified_scope": ["image", "runtime", "hardware"],
        })

    def test_validates_closed_world_authoritative_atomic_seal(self):
        document = self.seal()
        trusted = {
            document["provider"]["id"] + "@" + document["provider"]["version"]:
            document["provider"]["identity_digest"]
        }
        self.assertIn(
            {"code": "authenticated_provider_seal_unavailable", "path": "$.authoritativeness"},
            self.contract.validate(document, trusted),
        )

        self.assertIn(
            {"code": "untrusted_provider_identity", "path": "$.provider.identity_digest"},
            self.contract.validate(document),
        )

        document["surprise"] = True
        self.assertIn(
            {"code": "unknown_field", "path": "$.surprise"},
            self.contract.validate(document, trusted),
        )

    def test_rejects_wrong_scope_non_atomic_generation_and_digest_tampering(self):
        wrong_scope = self.seal()
        wrong_scope["subject_class"] = "hardware"
        wrong_scope["digest"] = self.contract.digest(wrong_scope)
        self.assertIn(
            {"code": "provider_scope_mismatch", "path": "$.subject_class"},
            self.contract.validate(wrong_scope),
        )

        non_atomic = self.seal()
        non_atomic["generation"]["atomic"] = False
        non_atomic["digest"] = self.contract.digest(non_atomic)
        self.assertIn(
            {"code": "authoritative_generation_not_atomic", "path": "$.generation.atomic"},
            self.contract.validate(non_atomic),
        )

        content_snapshot = self.seal()
        content_snapshot["generation"]["kind"] = "content_snapshot"
        content_snapshot["digest"] = self.contract.digest(content_snapshot)
        self.assertIn(
            {"code": "content_snapshot_not_atomic", "path": "$.generation.atomic"},
            self.contract.validate(content_snapshot),
        )

        tampered = self.seal()
        tampered["observed_value"]["version"] = "9.9.9"
        self.assertIn(
            {"code": "digest_mismatch", "path": "$.digest"},
            self.contract.validate(tampered),
        )

    def test_expiry_and_replay_generation_fail_closed(self):
        document = self.seal()
        trusted = {
            document["provider"]["id"] + "@" + document["provider"]["version"]:
            document["provider"]["identity_digest"]
        }
        with self.assertRaisesRegex(ValueError, "blocked_missing_authenticated_provider_seal"):
            self.contract.verify(
                document, "installed_package", self.clock(2026, 8, 8, 12), trusted,
                current_generation="fixture-generation-1",
            )
        with self.assertRaisesRegex(ValueError, "blocked_expired_provider_seal"):
            self.contract.verify(
                document, "installed_package", self.clock(2026, 8, 9), trusted,
                current_generation="fixture-generation-1",
            )
        with self.assertRaisesRegex(ValueError, "blocked_future_provider_observation"):
            self.contract.verify(
                document, "installed_package", self.clock(2026, 8, 7), trusted,
                current_generation="fixture-generation-1",
            )
        with self.assertRaisesRegex(ValueError, "blocked_missing_current_provider_generation"):
            self.contract.verify(
                document, "installed_package", self.clock(2026, 8, 8, 12), trusted
            )
        with self.assertRaisesRegex(ValueError, "blocked_stale_provider_generation"):
            self.contract.verify(
                document,
                "installed_package",
                self.clock(2026, 8, 8, 12),
                trusted,
                current_generation="fixture-generation-2",
            )

    @staticmethod
    def clock(year, month, day, hour=0):
        return lambda: datetime.datetime(
            year, month, day, hour, tzinfo=datetime.timezone.utc
        )

    def test_verifier_rejects_untrusted_clock_values(self):
        document = self.seal()
        trusted = {
            document["provider"]["id"] + "@" + document["provider"]["version"]:
            document["provider"]["identity_digest"]
        }
        for clock in (
            lambda: datetime.datetime(2026, 8, 8),
            lambda: "2026-08-08T00:00:00Z",
        ):
            with self.subTest(clock=clock):
                with self.assertRaisesRegex(
                    ValueError, "blocked_invalid_clock_context"
                ):
                    self.contract.verify(
                        document,
                        "installed_package",
                        clock,
                        trusted,
                        current_generation="fixture-generation-1",
                    )

    def test_observed_package_value_is_closed_world(self):
        document = self.seal()
        document["observed_value"] = {}
        document["digest"] = self.contract.digest(document)
        self.assertIn(
            {"code": "missing_required_field", "path": "$.observed_value.name"},
            self.contract.validate(document),
        )

        blocked = self.seal()
        blocked["status"] = "blocked"
        blocked["authoritativeness"] = "non_authoritative"
        blocked["blockers"] = [{
            "status": "blocked", "code": "blocked_fixture", "path": "$"
        }]
        blocked["primary_blocker"] = blocked["blockers"][0]
        blocked["observed_value"] = {"surprise": True}
        blocked["digest"] = self.contract.digest(blocked)
        self.assertIn(
            {"code": "unknown_field", "path": "$.observed_value.surprise"},
            self.contract.validate(blocked),
        )

    def test_provider_version_and_code_identity_are_exact(self):
        wrong_version = self.seal()
        wrong_version["provider"]["version"] = "9.9.9"
        wrong_version["digest"] = self.contract.digest(wrong_version)
        self.assertIn(
            {"code": "unsupported_provider_version", "path": "$.provider.version"},
            self.contract.validate(wrong_version),
        )

        wrong_identity = self.seal()
        wrong_identity["provider"]["identity_digest"] = "sha256:" + "f" * 64
        wrong_identity["digest"] = self.contract.digest(wrong_identity)
        self.assertIn(
            {"code": "provider_identity_mismatch", "path": "$.provider.identity_digest"},
            self.contract.validate(wrong_identity),
        )


if __name__ == "__main__":
    unittest.main()
