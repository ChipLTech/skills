import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "engineering" / "dlc-env-setup" / "scripts" / "stack-preflight.py"
TEST_IMAGE_ID = "sha256:" + "b" * 64
CRT_FILES = (
    "dlc_crt.hex",
    "dlc_crt_xys1.hex",
    "dlc_crt_cmem.hex",
    "dlc_crt_cmem_xys1.hex",
)


class StackPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.crt_dir = self.root / "crt"
        self.crt_dir.mkdir()
        for index, name in enumerate(CRT_FILES):
            (self.crt_dir / name).write_bytes(b"0DLC" + bytes([index]) * 32)
        self.kernel = self.root / "libcustom_dlc_perf_lib.so"
        self.kernel.write_bytes(b"kernel")
        self.policy = self.root / "policy.json"
        self.write_policy("approved")

    def tearDown(self):
        self.temp_dir.cleanup()

    def identity(self):
        return {
            "crt": {
                name: {
                    "sha256": hashlib.sha256((self.crt_dir / name).read_bytes()).hexdigest(),
                    "size": (self.crt_dir / name).stat().st_size,
                }
                for name in CRT_FILES
            },
            "kernel_library_sha256": hashlib.sha256(self.kernel.read_bytes()).hexdigest(),
            "marker_hex": (self.crt_dir / CRT_FILES[0]).read_bytes()[:4].hex(),
        }

    def write_policy(self, status):
        identity = self.identity()
        self.policy.write_text(
            json.dumps(
                {
                    "schema": "io.chipltech.stack-compatibility-policy/v1",
                    "profiles": [
                        {
                            "profile_id": "test-profile",
                            "status": status,
                            "target": "dlc",
                            "marker_hex": identity["marker_hex"],
                            "driver_api": 20,
                            "runtime_api": 20,
                            "crt": identity["crt"],
                            "kernel_library_sha256": identity["kernel_library_sha256"],
                            "llvm_sha": "a" * 40,
                            "qualification_evidence": "artifact://test-profile-cold-c1b",
                            "image_ids": [TEST_IMAGE_ID],
                        }
                    ],
                }
            )
        )

    def run_preflight(self, *extra_args):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--policy",
                str(self.policy),
                "--image-id",
                TEST_IMAGE_ID,
                "--target",
                "dlc",
                "--driver-api",
                "20",
                "--runtime-api",
                "20",
                "--crt-dir",
                str(self.crt_dir),
                "--kernel-library",
                str(self.kernel),
                "--llvm-sha",
                "a" * 40,
                *extra_args,
            ],
            capture_output=True,
            check=False,
            text=True,
        )

    def test_exact_approved_profile_passes(self):
        result = self.run_preflight()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["reason_code"], "approved_profile")

    def test_known_bad_profile_is_rejected(self):
        self.write_policy("revoked")

        result = self.run_preflight()

        self.assertEqual(result.returncode, 5)
        self.assertEqual(json.loads(result.stdout)["reason_code"], "known_bad_profile")

    def test_known_bad_unmarked_crt_profile_is_identified(self):
        for path in self.crt_dir.iterdir():
            path.write_bytes(b"\0\0\0\0" + path.read_bytes()[4:])
        self.write_policy("revoked")

        result = self.run_preflight()

        self.assertEqual(result.returncode, 5)
        self.assertEqual(json.loads(result.stdout)["reason_code"], "known_bad_profile")

    def test_unknown_profile_fails_closed(self):
        self.kernel.write_bytes(b"different-kernel")

        result = self.run_preflight()

        self.assertEqual(result.returncode, 6)
        self.assertEqual(json.loads(result.stdout)["reason_code"], "unknown_profile")

    def test_driver_runtime_api_mismatch_is_rejected_before_policy_lookup(self):
        result = self.run_preflight("--runtime-api", "21")

        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["reason_code"], "driver_runtime_api_mismatch")

    def test_missing_or_extra_crt_fails_closed(self):
        for mutation in ("missing", "extra"):
            with self.subTest(mutation=mutation):
                if mutation == "missing":
                    path = self.crt_dir / CRT_FILES[0]
                    data = path.read_bytes()
                    path.unlink()
                else:
                    path = self.crt_dir / "dlc_crt_extra.hex"
                    path.write_bytes(b"0DLCextra")
                    data = None
                result = self.run_preflight()
                self.assertEqual(result.returncode, 3)
                self.assertEqual(json.loads(result.stdout)["reason_code"], "crt_bundle_incomplete")
                path.unlink(missing_ok=True)
                if data is not None:
                    path.write_bytes(data)

    def test_mutable_image_identity_is_rejected(self):
        result = self.run_preflight("--image-id", "daily:latest")

        self.assertEqual(result.returncode, 11)
        self.assertEqual(json.loads(result.stdout)["reason_code"], "identity_unavailable")

    def test_policy_cannot_approve_wrong_target_marker(self):
        policy = json.loads(self.policy.read_text())
        policy["profiles"][0]["marker_hex"] = "00000000"
        self.policy.write_text(json.dumps(policy))

        result = self.run_preflight()

        self.assertEqual(result.returncode, 10)
        self.assertEqual(json.loads(result.stdout)["reason_code"], "invalid_policy")

    def test_approval_is_bound_to_immutable_image_id(self):
        result = self.run_preflight("--image-id", "sha256:" + "c" * 64)

        self.assertEqual(result.returncode, 6)
        self.assertEqual(json.loads(result.stdout)["reason_code"], "unknown_profile")

    def test_duplicate_identity_profiles_are_rejected(self):
        policy = json.loads(self.policy.read_text())
        duplicate = json.loads(json.dumps(policy["profiles"][0]))
        duplicate["profile_id"] = "duplicate-profile"
        policy["profiles"].append(duplicate)
        self.policy.write_text(json.dumps(policy))

        result = self.run_preflight()

        self.assertEqual(result.returncode, 10)
        self.assertEqual(json.loads(result.stdout)["reason_code"], "invalid_policy")

    def test_malformed_policy_does_not_crash(self):
        self.policy.write_text('{"schema":"io.chipltech.stack-compatibility-policy/v1","profiles":[{"profile_id":"x","status":"approved","crt":null}]}')

        result = self.run_preflight()

        self.assertEqual(result.returncode, 10)
        self.assertEqual(json.loads(result.stdout)["reason_code"], "invalid_policy")

    def test_usage_error_emits_structured_json(self):
        result = self.run_preflight("--image-id")

        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["reason_code"], "invalid_arguments")

    def test_revoked_profile_scoped_to_other_image_does_not_revoke(self):
        self.write_policy("revoked")
        policy = json.loads(self.policy.read_text())
        policy["profiles"][0]["image_ids"] = ["sha256:" + "c" * 64]
        self.policy.write_text(json.dumps(policy))

        result = self.run_preflight()

        self.assertEqual(result.returncode, 6)
        self.assertEqual(json.loads(result.stdout)["reason_code"], "unknown_profile")


if __name__ == "__main__":
    unittest.main()
