import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from importlib import metadata
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "scripts" / "qualify-vllm-dlc-dependencies.py"
VALIDATOR = ROOT / "scripts" / "validate-vllm-dlc-contracts.py"
RUNNER = ROOT / "scripts" / "run-vllm-dlc-smoke.py"
POLICY = ROOT / "config" / "vllm-dlc" / "ticket06-dependency-exceptions.json"
MAIN_TO_MAIN_POLICY = (
    ROOT / "config" / "vllm-dlc" / "ticket06-main-to-main-operational-policy.json"
)
EXPECTED_KEYS = {
    "compatibility_exceptions",
    "dependencies",
    "imports",
    "metadata_checks",
    "model_started",
    "native_modules",
    "reasons",
    "requirements_path",
    "schema_version",
    "status",
}


class DependencyQualificationCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        qualifier_spec = importlib.util.spec_from_file_location(
            "dependency_qualifier", CLI
        )
        assert qualifier_spec is not None and qualifier_spec.loader is not None
        cls.qualifier = importlib.util.module_from_spec(qualifier_spec)
        qualifier_spec.loader.exec_module(cls.qualifier)

    def run_cli(
        self,
        requirement: str,
        *,
        vllm_root: Path = Path("/work/vllm"),
        vllm_dlc_root: Path = Path("/work/vllm-dlc"),
    ) -> subprocess.CompletedProcess[str]:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt") as fixture:
            fixture.write(requirement + "\n")
            fixture.flush()
            return subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "--requirements",
                    fixture.name,
                    "--exception-policy",
                    str(POLICY),
                    "--expected-vllm-root",
                    str(vllm_root),
                    "--expected-vllm-dlc-root",
                    str(vllm_dlc_root),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )

    def test_current_environment_passes_with_minimal_exact_pin(self) -> None:
        result = self.run_cli(f"packaging=={metadata.version('packaging')}")

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(set(report), EXPECTED_KEYS)
        self.assertEqual(report["status"], "passed")
        self.assertIs(report["model_started"], False)
        self.assertEqual(report["reasons"], [])
        self.assertEqual(
            report["compatibility_exceptions"],
            [self.qualifier.EXPECTED_EXCEPTION],
        )
        self.assertTrue(report["metadata_checks"])
        self.assertTrue(all(item["passed"] for item in report["imports"]))
        self.assertTrue(all(item["passed"] for item in report["native_modules"]))

    def test_version_mismatch_blocks(self) -> None:
        result = self.run_cli("packaging==0")

        self.assertEqual(result.returncode, 20, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(set(report), EXPECTED_KEYS)
        self.assertEqual(report["status"], "blocked")
        self.assertIs(report["model_started"], False)
        self.assertEqual(report["reasons"][0]["code"], "dependency.version_mismatch")

    def test_unpinned_requirement_blocks(self) -> None:
        result = self.run_cli("packaging>=1")

        self.assertEqual(result.returncode, 20, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reasons"][0]["code"], "requirements.not_exact_pin")

    def test_wrong_native_root_blocks(self) -> None:
        result = self.run_cli(
            f"packaging=={metadata.version('packaging')}",
            vllm_root=Path("/tmp/kilo/not-vllm"),
        )

        self.assertEqual(result.returncode, 20, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "blocked")
        self.assertIs(report["model_started"], False)
        self.assertIn(
            "native_module.unexpected_origin",
            [item["code"] for item in report["reasons"]],
        )

    def metadata_result(
        self,
        requirements: dict[str, list[str]],
        versions: dict[str, str],
        *,
        approved: bool,
    ) -> tuple[list[dict[str, object]], list[dict[str, str]], list[dict[str, object]]]:
        def requires(distribution: str) -> list[str]:
            return requirements[distribution]

        def version(distribution: str) -> str:
            try:
                return versions[distribution]
            except KeyError as error:
                raise metadata.PackageNotFoundError(distribution) from error

        with (
            mock.patch.object(self.qualifier.metadata, "requires", side_effect=requires),
            mock.patch.object(self.qualifier.metadata, "version", side_effect=version),
        ):
            return self.qualifier.qualify_metadata(
                self.qualifier.EXPECTED_EXCEPTION if approved else None
            )

    def test_unapproved_metadata_mismatch_blocks(self) -> None:
        checks, exceptions, reasons = self.metadata_result(
            {
                "vllm": ["opencv-python-headless>=4.13.0"],
                "vllm-dlc": ["opencv-python-headless<=4.11.0.86"],
            },
            {"opencv-python-headless": "4.11.0.86"},
            approved=False,
        )

        self.assertEqual(exceptions, [])
        self.assertEqual(len(checks), 2)
        self.assertEqual([item["code"] for item in reasons], ["metadata.requirement_unsatisfied"])

    def test_exact_metadata_exception_passes(self) -> None:
        checks, exceptions, reasons = self.metadata_result(
            {
                "vllm": [
                    "optional-package; extra == 'audio'",
                    "opencv-python-headless>=4.13.0",
                ],
                "vllm-dlc": ["opencv-python-headless<=4.11.0.86"],
            },
            {"opencv-python-headless": "4.11.0.86"},
            approved=True,
        )

        self.assertEqual(exceptions, [self.qualifier.EXPECTED_EXCEPTION])
        self.assertEqual(reasons, [])
        self.assertEqual(len(checks), 2)

    def test_extra_metadata_mismatch_blocks(self) -> None:
        _, exceptions, reasons = self.metadata_result(
            {
                "vllm": [
                    "opencv-python-headless>=4.13.0",
                    "requests>=999",
                ],
                "vllm-dlc": ["opencv-python-headless<=4.11.0.86"],
            },
            {
                "opencv-python-headless": "4.11.0.86",
                "requests": "2.0.0",
            },
            approved=True,
        )

        self.assertEqual(exceptions, [self.qualifier.EXPECTED_EXCEPTION])
        self.assertEqual([item["subject"] for item in reasons], ["vllm:requests"])

    def test_changed_policy_blocks(self) -> None:
        policy = json.loads(POLICY.read_text())
        policy["exception"]["installed_version"] = "4.11.0.85"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as fixture:
            json.dump(policy, fixture)
            fixture.flush()
            exception, reasons = self.qualifier.read_exception_policy(Path(fixture.name))

        self.assertIsNone(exception)
        self.assertEqual([item["code"] for item in reasons], ["exception_policy.invalid"])


class DependencyQualificationCampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        validator_spec = importlib.util.spec_from_file_location(
            "dependency_campaign_validator", VALIDATOR
        )
        assert validator_spec is not None and validator_spec.loader is not None
        cls.validator = importlib.util.module_from_spec(validator_spec)
        validator_spec.loader.exec_module(cls.validator)

        runner_spec = importlib.util.spec_from_file_location(
            "dependency_campaign_runner", RUNNER
        )
        assert runner_spec is not None and runner_spec.loader is not None
        cls.runner = importlib.util.module_from_spec(runner_spec)
        runner_spec.loader.exec_module(cls.runner)

    def qualification(self) -> dict[str, object]:
        return {
            "compatibility_exceptions": [{
                "dependency": "opencv-python-headless",
                "distribution": "vllm",
                "installed_version": "4.11.0.86",
                "rationale": "vllm-dlc requires <=4.11.0.86 to preserve numpy<2",
                "requirement": "opencv-python-headless>=4.13.0",
                "vllm_dlc_requirement": "opencv-python-headless<=4.11.0.86",
            }],
            "dependencies": [{
                "distribution": "packaging",
                "expected_version": "25.0",
                "installed_version": "25.0",
            }],
            "imports": [{"name": "vllm_dlc", "passed": True}],
            "metadata_checks": [
                {
                    "compatibility_exception": True,
                    "dependency": "opencv-python-headless",
                    "distribution": "vllm",
                    "installed_version": "4.11.0.86",
                    "requirement": "opencv-python-headless>=4.13.0",
                    "satisfied": False,
                },
                {
                    "compatibility_exception": False,
                    "dependency": "opencv-python-headless",
                    "distribution": "vllm-dlc",
                    "installed_version": "4.11.0.86",
                    "requirement": "opencv-python-headless<=4.11.0.86",
                    "satisfied": True,
                },
            ],
            "model_started": False,
            "native_modules": [
                {
                    "expected_root": "/work/vllm",
                    "name": "vllm._C",
                    "origin": "/work/vllm/vllm/_C.so",
                    "passed": True,
                },
                {
                    "expected_root": "/work/vllm-dlc",
                    "name": "vllm_dlc.vllm_dlc_C",
                    "origin": "/work/vllm-dlc/vllm_dlc/vllm_dlc_C.so",
                    "passed": True,
                },
            ],
            "reasons": [],
            "requirements_path": "/work/skills/requirements-vllm-dlc-contracts.txt",
            "schema_version": "vllm-dlc-dependency-qualification/v1",
            "status": "passed",
        }

    def validate(self, document: dict[str, object]) -> bool:
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            path = Path(directory) / "qualification.json"
            path.write_text(json.dumps(document))
            return self.validator.validate_dependency_qualification(
                path, ["/work/vllm", "/work/vllm-dlc"]
            )

    def test_operational_campaign_requires_dependency_closure_entries(self) -> None:
        required = {
            "dependency_qualifier",
            "dependency_requirements",
            "dependency_exception_policy",
            "dependency_qualification",
        }

        self.assertTrue(required.issubset(self.validator.OPERATIONAL_CAMPAIGN_REQUIRED_IDS))
        self.assertEqual(
            self.runner.CAMPAIGN_REQUIRED_IDS,
            self.validator.OPERATIONAL_CAMPAIGN_REQUIRED_IDS,
        )
        self.assertEqual(
            self.validator.DEPENDENCY_EXCEPTION_POLICY_PATH,
            POLICY.resolve(),
        )
        self.assertTrue(
            self.validator.validate_dependency_exception_policy(POLICY.resolve())
        )
        self.assertEqual(self.validator.DEPENDENCY_QUALIFIER_PATH, CLI.resolve())
        self.assertEqual(
            self.validator.DEPENDENCY_REQUIREMENTS_PATH,
            (ROOT / "requirements-vllm-dlc-contracts.txt").resolve(),
        )

    def test_operational_campaign_requires_exact_main_to_main_policy(self) -> None:
        self.assertIn(
            "main_to_main_operational_policy",
            self.validator.OPERATIONAL_CAMPAIGN_REQUIRED_IDS,
        )
        self.assertEqual(
            self.runner.CAMPAIGN_REQUIRED_IDS,
            self.validator.OPERATIONAL_CAMPAIGN_REQUIRED_IDS,
        )
        self.assertEqual(
            self.validator.MAIN_TO_MAIN_OPERATIONAL_POLICY_PATH,
            MAIN_TO_MAIN_POLICY.resolve(),
        )
        self.assertTrue(
            self.validator.validate_main_to_main_operational_policy(
                json.loads(MAIN_TO_MAIN_POLICY.read_bytes())
            )
        )

    def test_offline_qualification_accepts_exact_passed_report(self) -> None:
        self.assertTrue(self.validate(self.qualification()))

    def test_offline_qualification_rejects_non_closing_reports(self) -> None:
        mutations = {
            "extra schema field": lambda report: report.update(extra=True),
            "wrong schema": lambda report: report.update(schema_version="v2"),
            "blocked status": lambda report: report.update(status="blocked"),
            "model started": lambda report: report.update(model_started=True),
            "reason present": lambda report: report.update(reasons=[{"code": "failed"}]),
            "wrong requirements": lambda report: report.update(
                requirements_path="/tmp/kilo/requirements.txt"
            ),
            "version mismatch": lambda report: report["dependencies"][0].update(
                installed_version="24.0"
            ),
            "failed import": lambda report: report["imports"][0].update(passed=False),
            "missing metadata": lambda report: report.update(metadata_checks=[]),
            "extra exception": lambda report: report["compatibility_exceptions"].append(
                dict(report["compatibility_exceptions"][0])
            ),
            "changed exception": lambda report: report["compatibility_exceptions"][0].update(
                installed_version="4.11.0.85"
            ),
            "unapproved metadata mismatch": lambda report: report["metadata_checks"].append({
                "compatibility_exception": False,
                "dependency": "requests",
                "distribution": "vllm",
                "installed_version": "2.0.0",
                "requirement": "requests>=999",
                "satisfied": False,
            }),
            "failed native": lambda report: report["native_modules"][0].update(
                passed=False
            ),
            "native outside guards": lambda report: report["native_modules"][0].update(
                origin="/tmp/kilo/vllm/_C.so"
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                report = self.qualification()
                mutate(report)
                self.assertFalse(self.validate(report))


if __name__ == "__main__":
    unittest.main()
