import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "scripts" / "validate-vllm-dlc-contracts.py"
FIXTURES = Path(__file__).with_name("fixtures")
KNOWLEDGE_ROOT = Path("/work/chipltech-knowledge-base")


class KnowledgeCliTests(unittest.TestCase):
    def run_cli(
        self, target: str, fixture: Path, knowledge_root: Path = KNOWLEDGE_ROOT
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(CLI),
                "--skills-root",
                str(ROOT),
                "--knowledge-root",
                str(knowledge_root),
                "--vllm-dlc-root",
                "/work/vllm-dlc",
                target,
                str(fixture),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def copied_package(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "knowledge"
        for relative in (
            "CONTEXT.md",
            "README.md",
            "vllm-dlc/model-adaptation-and-main-to-main-decisions.md",
            "prompt-examples/vllm-dlc-model-adaptation.md",
            "prompt-examples/vllm-dlc-main-to-main-upgrade.md",
        ):
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(KNOWLEDGE_ROOT / relative, destination)
        manifest = Path(temporary.name) / "knowledge-package.json"
        shutil.copy2(FIXTURES / "knowledge-package.json", manifest)
        return root, manifest

    def test_real_knowledge_package_is_discoverable_and_governed(self):
        result = self.run_cli("knowledge-package", FIXTURES / "knowledge-package.json")

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"][0]["code"], "knowledge_package.valid")
        self.assertEqual(
            set(report["documents"]),
            {
                "entry_point",
                "decision_record",
                "model_adaptation_prompt",
                "main_to_main_prompt",
            },
        )
        self.assertEqual(len(report["required_links"]), 3)
        self.assertEqual(len(report["evidence_classes"]), 6)
        self.assertEqual(
            report["prompt_identities"],
            {
                "model_adaptation_prompt": "model-adaptation",
                "main_to_main_prompt": "main-to-main-upgrade",
            },
        )
        self.assertEqual(report["repository_before"], report["repository_after"])

    def test_prompt_dry_run_is_deterministic_and_never_executes(self):
        fixture = FIXTURES / "prompt-dry-run.json"
        first = self.run_cli("prompt-dry-run", fixture)
        second = self.run_cli("prompt-dry-run", fixture)

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        report = json.loads(first.stdout)
        cases = {row["id"]: row for row in report["transcripts"]}
        model = cases["model-adaptation-missing-inputs"]
        main = cases["main-to-main-missing-target"]
        self.assertEqual(model["selected_skill"], "model-adaptation")
        self.assertEqual(model["reason_code"], "blocked_missing_asset")
        self.assertIn("model_id", model["missing_inputs"])
        self.assertEqual(main["selected_skill"], "main-to-main-upgrade")
        self.assertEqual(main["reason_code"], "blocked_missing_target")
        self.assertIn("target_vllm_full_sha", main["missing_inputs"])
        for transcript in cases.values():
            self.assertFalse(transcript["runner_invoked"])
            self.assertFalse(transcript["acceptance_eligible"])
            self.assertFalse(transcript["finalize_eligible"])
            self.assertEqual(
                set(transcript["evidence_states"].values()), {"not_verified"}
            )
        self.assertNotIn("model_id", cases["model-adaptation-partial-inputs"]["missing_inputs"])
        self.assertNotIn("target_vllm_full_sha", cases["main-to-main-partial-inputs"]["missing_inputs"])
        self.assertEqual(
            cases["main-to-main-partial-inputs"]["reason_code"],
            "blocked_missing_contract",
        )
        for transcript in cases.values():
            self.assertEqual(
                transcript["repository_before"], transcript["repository_after"]
            )

    def test_governed_documents_reuse_duplicate_quality_gate_with_role_context(self):
        additions = [
            "```bash\npython3 smoke-runner.py --run-spec input.json\n```",
            "$ curl http://localhost/example",
            "Use /v1/models for readiness.",
            "Assert response.json is valid.",
            "Acceptance requires prefill_chunk_count > 1.",
            "Assert triton_executed == false.",
        ]
        for addition in additions:
            with self.subTest(addition=addition):
                root, manifest = self.copied_package()
                prompt = root / "prompt-examples/vllm-dlc-model-adaptation.md"
                prompt.write_text(prompt.read_text() + "\n" + addition + "\n")
                result = self.run_cli("knowledge-package", manifest, root)
                self.assertEqual(result.returncode, 40, result.stdout)
                check = json.loads(result.stdout)["checks"][0]
                self.assertEqual(check["code"], "quality_gate.duplicated")
                self.assertEqual(check["role"], "model_adaptation_prompt")
                self.assertEqual(check["path"], "prompt-examples/vllm-dlc-model-adaptation.md")

    def test_explanatory_quality_gate_prose_is_allowed(self):
        root, manifest = self.copied_package()
        prompt = root / "prompt-examples/vllm-dlc-model-adaptation.md"
        prompt.write_text(
            prompt.read_text()
            + "\nHTTP success alone is insufficient; executable assertions remain shared.\n"
        )
        result = self.run_cli("knowledge-package", manifest, root)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_manifest_is_closed_world_and_paths_stay_beneath_root(self):
        mutations = [
            (lambda value: value.update(extra=True), "documentation.unknown_field"),
            (lambda value: value["documents"].update(extra="README.md"), "documentation.unknown_field"),
            (lambda value: value["documents"].update(decision_record="../outside.md"), "documentation.invalid_path"),
            (lambda value: value["documents"].update(decision_record="/tmp/outside.md"), "documentation.invalid_path"),
            (lambda value: value["documents"].update(decision_record="README.md"), "documentation.invalid_path"),
        ]
        for mutate, code in mutations:
            with self.subTest(code=code):
                document = json.loads((FIXTURES / "knowledge-package.json").read_text())
                mutate(document)
                with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as fixture:
                    json.dump(document, fixture)
                    fixture.flush()
                    result = self.run_cli("knowledge-package", Path(fixture.name))
                self.assertEqual(result.returncode, 20, result.stdout)
                self.assertEqual(json.loads(result.stdout)["checks"][0]["code"], code)

    def test_required_and_local_links_must_resolve(self):
        root, manifest = self.copied_package()
        readme = root / "README.md"
        readme.write_text(readme.read_text().replace("prompt-examples/vllm-dlc-model-adaptation.md", "prompt-examples/missing.md"))
        missing = self.run_cli("knowledge-package", manifest, root)
        self.assertEqual(missing.returncode, 20, missing.stdout)
        self.assertEqual(json.loads(missing.stdout)["checks"][0]["code"], "link.required_missing")

        root, manifest = self.copied_package()
        decision = root / "vllm-dlc/model-adaptation-and-main-to-main-decisions.md"
        decision.write_text(decision.read_text() + "\n[missing](missing.md)\n")
        unresolved = self.run_cli("knowledge-package", manifest, root)
        self.assertEqual(unresolved.returncode, 20, unresolved.stdout)
        self.assertEqual(json.loads(unresolved.stdout)["checks"][0]["code"], "link.unresolved")

    def test_escaping_symlink_is_rejected(self):
        root, manifest = self.copied_package()
        prompt = root / "prompt-examples/vllm-dlc-model-adaptation.md"
        prompt.unlink()
        prompt.symlink_to("/etc/passwd")
        result = self.run_cli("knowledge-package", manifest, root)
        self.assertEqual(result.returncode, 20, result.stdout)
        self.assertEqual(json.loads(result.stdout)["checks"][0]["code"], "link.outside_root")

    def test_prompt_frontmatter_is_exact_and_rejects_unsupported_claims(self):
        mutations = [
            (lambda text: text.replace("hardware_evidence: not_verified", "hardware_evidence: passed"), "prompt.invalid"),
            (lambda text: text.replace("prompt_schema: vllm-dlc-reusable-prompt/v1", "prompt_schema: v2"), "prompt.invalid"),
            (lambda text: text.replace("skill_identity: model-adaptation", "skill_identity: invented-owner"), "prompt.invalid"),
            (lambda text: text.replace("shared_contract: vllm-dlc-contract/v1", "shared_contract: missing"), "prompt.invalid"),
            (lambda text: text.replace("hardware_evidence: not_verified", "hardware_evidence: not_verified\nunknown: value"), "prompt.invalid"),
            (lambda text: text.replace("skill_identity: model-adaptation", "skill_identity: model-adaptation\nskill_identity: model-adaptation"), "prompt.invalid"),
        ]
        for mutate, code in mutations:
            with self.subTest(mutation=repr(mutate)):
                root, manifest = self.copied_package()
                prompt = root / "prompt-examples/vllm-dlc-model-adaptation.md"
                prompt.write_text(mutate(prompt.read_text()))
                result = self.run_cli("knowledge-package", manifest, root)
                self.assertEqual(result.returncode, 20, result.stdout)
                self.assertEqual(json.loads(result.stdout)["checks"][0]["code"], code)

    def test_prompt_body_cannot_claim_acceptance_or_finalization(self):
        additions = [
            "Real DLC Hardware evidence is passed.",
            "Real weights passed.",
            "Acceptance is verified.",
            "The workflow was finalized.",
            "Mandatory hardware acceptance passed successfully.",
            "Main-to-Main finalization is complete.",
            "acceptance_eligible: true",
            "finalize_eligible: true",
        ]
        for addition in additions:
            with self.subTest(addition=addition):
                root, manifest = self.copied_package()
                prompt = root / "prompt-examples/vllm-dlc-main-to-main-upgrade.md"
                prompt.write_text(prompt.read_text() + "\n" + addition + "\n")
                result = self.run_cli("knowledge-package", manifest, root)
                self.assertEqual(result.returncode, 20, result.stdout)
                check = json.loads(result.stdout)["checks"][0]
                self.assertEqual(check["code"], "prompt.invalid")
                self.assertEqual(check["role"], "main_to_main_prompt")

    def test_missing_manifest_schema_is_distinct_from_unsupported_schema(self):
        document = json.loads((FIXTURES / "knowledge-package.json").read_text())
        document.pop("schema_version")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as fixture:
            json.dump(document, fixture)
            fixture.flush()
            result = self.run_cli("knowledge-package", Path(fixture.name))
        self.assertEqual(result.returncode, 20, result.stdout)
        self.assertEqual(
            json.loads(result.stdout)["checks"][0]["code"],
            "documentation.missing_required_field",
        )

    def test_dry_run_fixture_is_closed_world(self):
        mutations = [
            lambda value: value.update(extra=True),
            lambda value: value["cases"][0].update(prompt_role="invented"),
            lambda value: value["cases"][0]["provided_inputs"].update(undeclared=True),
            lambda value: value["cases"].append(dict(value["cases"][0])),
            lambda value: value.update(schema_version="unsupported"),
        ]
        for mutate in mutations:
            with self.subTest(mutation=repr(mutate)):
                document = json.loads((FIXTURES / "prompt-dry-run.json").read_text())
                mutate(document)
                with tempfile.NamedTemporaryFile(mode="w", suffix=".json", dir=FIXTURES) as fixture:
                    json.dump(document, fixture)
                    fixture.flush()
                    result = self.run_cli("prompt-dry-run", Path(fixture.name))
                self.assertEqual(result.returncode, 20, result.stdout)
                self.assertIn(json.loads(result.stdout)["checks"][0]["code"], {"prompt.invalid", "documentation.unsupported_schema_version"})

    def test_dry_run_rejects_present_but_invalid_inputs(self):
        mutations = [
            lambda case: case["provided_inputs"].update(model_id=""),
            lambda case: case["provided_inputs"].update(model_id=None),
            lambda case: case["provided_inputs"].update(
                target_vllm_full_sha="not-a-full-sha"
            ),
            lambda case: case["provided_inputs"].update(available_device_count=-1),
        ]
        for mutate in mutations:
            with self.subTest(mutation=repr(mutate)):
                document = json.loads((FIXTURES / "prompt-dry-run.json").read_text())
                mutate(document["cases"][0])
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".json", dir=FIXTURES
                ) as fixture:
                    json.dump(document, fixture)
                    fixture.flush()
                    result = self.run_cli("prompt-dry-run", Path(fixture.name))
                self.assertEqual(result.returncode, 20, result.stdout)
                self.assertEqual(
                    json.loads(result.stdout)["checks"][0]["code"], "prompt.invalid"
                )

    def test_prompt_frontmatter_rejects_non_string_required_input(self):
        root, manifest = self.copied_package()
        prompt = root / "prompt-examples/vllm-dlc-model-adaptation.md"
        prompt.write_text(
            prompt.read_text().replace("  - model_id", "  - {model_id: invalid}")
        )
        result = self.run_cli("knowledge-package", manifest, root)
        self.assertEqual(result.returncode, 20, result.stdout)
        self.assertEqual(json.loads(result.stdout)["checks"][0]["code"], "prompt.invalid")


if __name__ == "__main__":
    unittest.main()
