import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "skills" / "engineering" / "modelzoo-image-validation" / "scripts" / "resolve-modelzoo.py"
FIXTURES = Path(__file__).with_name("fixtures")


class ModelZooResolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(dir="/tmp/kilo")
        cls.workspace = Path(cls.temporary.name)
        cls.fixture_roots = {}
        for source in sorted(path for path in FIXTURES.iterdir() if path.is_dir()):
            target = cls.workspace / source.name
            shutil.copytree(source, target)
            cls.fixture_roots[source.name] = target

        cls.component_repo = cls.workspace / "approved-component"
        cls.component_repo.mkdir()
        (cls.component_repo / "artifact.txt").write_text("approved component\n", encoding="utf-8")
        cls.git(cls.component_repo, "init", "--quiet")
        cls.git(cls.component_repo, "remote", "add", "origin", f"file://{cls.component_repo}")
        cls.git(cls.component_repo, "add", "artifact.txt")
        cls.git(cls.component_repo, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "fixture")
        cls.component_ref = cls.git(cls.component_repo, "rev-parse", "HEAD").stdout.strip()

        cls.fixture_private_key = cls.workspace / "fixture-observation-private.pem"
        cls.fixture_public_key = cls.workspace / "fixture-observation-public.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "Ed25519", "-out", str(cls.fixture_private_key)],
            capture_output=True,
            text=True,
            check=True,
        )
        subprocess.run(
            ["openssl", "pkey", "-in", str(cls.fixture_private_key), "-pubout", "-out", str(cls.fixture_public_key)],
            capture_output=True,
            text=True,
            check=True,
        )

        complete_readme = cls.fixture_roots["complete zoo"] / "vllm" / "models" / "Complete-7B" / "README.md"
        complete_readme.write_text(re.sub(r"\b[0-9a-f]{40}\b", cls.component_ref, complete_readme.read_text(encoding="utf-8")), encoding="utf-8")
        cls.model_asset = cls.workspace / "approved-model"
        cls.model_asset.mkdir()
        (cls.model_asset / "config.json").write_text('{"model_type":"fixture"}\n', encoding="utf-8")

        cls.evidence = {}
        for name, claims in {
            "base-image": {"identity": "sha256:" + "a" * 64},
            "framework-package": {"identity": "vllm-fixture"},
            "hardware": {"available": True, "generation": "dlc_gen1", "resource_occupied": False},
            "authorization": {"authorized": True, "intent": "prepare_both"},
        }.items():
            path = cls.workspace / f"{name}.txt"
            path.write_text(json.dumps(claims, sort_keys=True), encoding="utf-8")
            signature = path.with_suffix(".sig")
            subprocess.run(
                ["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(cls.fixture_private_key), "-in", str(path), "-out", str(signature)],
                capture_output=True,
                text=True,
                check=True,
            )
            cls.evidence[name] = {
                "path": str(path),
                "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
                "signature_path": str(signature),
                "signature_sha256": "sha256:" + hashlib.sha256(signature.read_bytes()).hexdigest(),
            }

        components = ("dlc-thunk", "llvm", "dlcsim", "dlcsynapse", "dlc-cl", "dlc-custom-kernel", "pytorch", "vllm")
        cls.preflight_path = cls.workspace / "preflight.json"
        cls.preflight_path.write_text(json.dumps({
            "intent": "prepare_both",
            "weight_path": str(cls.model_asset),
            "component_sources": {component: {"repository_root": str(cls.component_repo), "ref": cls.component_ref} for component in components},
            "base_image": {"identity": "sha256:" + "a" * 64, "evidence": cls.evidence["base-image"]},
            "framework_package": {"identity": "vllm-fixture", "evidence": cls.evidence["framework-package"]},
            "hardware": {"generation": "dlc_gen1", "available": True, "resource_occupied": False, "evidence": cls.evidence["hardware"]},
            "authorization": {"authorized": True, "evidence": cls.evidence["authorization"]},
        }, sort_keys=True), encoding="utf-8")

        for root in cls.fixture_roots.values():
            cls.git(root, "init", "--quiet")
            cls.git(root, "remote", "add", "origin", f"file://{root}")
            cls.git(root, "add", ".")
            cls.git(root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "fixture")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @staticmethod
    def git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", "-C", str(root), *arguments], capture_output=True, text=True, check=True)

    @staticmethod
    def reseal_preflight(document: dict, directory: Path) -> None:
        claims = {
            "base_image": {"identity": document["base_image"]["identity"]},
            "framework_package": {"identity": document["framework_package"]["identity"]},
            "hardware": {key: document["hardware"][key] for key in ("available", "generation", "resource_occupied")},
            "authorization": {"authorized": document["authorization"]["authorized"], "intent": document["intent"]},
        }
        for field, payload in claims.items():
            path = directory / f"{field}.json"
            path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
            signature = path.with_suffix(".sig")
            subprocess.run(
                ["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(ModelZooResolverTests.fixture_private_key), "-in", str(path), "-out", str(signature)],
                capture_output=True,
                text=True,
                check=True,
            )
            document[field]["evidence"] = {
                "path": str(path),
                "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
                "signature_path": str(signature),
                "signature_sha256": "sha256:" + hashlib.sha256(signature.read_bytes()).hexdigest(),
            }

    def run_cli(self, fixture: str, model: str, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), "--modelzoo-root", str(self.fixture_roots[fixture]), "--model", model, *extra],
            capture_output=True,
            text=True,
            check=False,
        )

    def report(self, fixture: str, model: str, *extra: str) -> dict:
        result = self.run_cli(fixture, model, *extra)
        self.assertIn(result.returncode, (0, 20), result.stderr + result.stdout)
        return json.loads(result.stdout)

    def complete_arguments(self) -> tuple[str, ...]:
        return (
            "--framework", "vllm", "--preflight", str(self.preflight_path),
            "--test-observation-public-key", str(self.fixture_public_key),
        )

    def test_complete_vllm_resolves_deterministically(self):
        first = self.run_cli("complete zoo", "Complete-7B", *self.complete_arguments())
        second = self.run_cli("complete zoo", "Complete-7B", *self.complete_arguments())
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        report = json.loads(first.stdout)
        self.assertEqual(report["schema"], "modelzoo-dlc-tyd-resolved-manifest/v1")
        self.assertEqual(report["resolution_status"], "resolved")
        self.assertEqual(report["selection"]["framework"], "vllm")
        self.assertEqual(report["source_claims"]["weight_paths"][0]["classification"], "modelzoo_declared")
        self.assertEqual(report["resolved"]["framework_adapter"], "vllm/v1")
        self.assertTrue(report["current_observations"]["model_asset"]["exists"])
        self.assertIn("model_functional", report["claim_boundary"]["unverified_scope"])
        self.assertEqual(report["workflow_contract"]["tyd"]["dlc_gen1_execution_status"], "intentionally_not_executed_on_dlc_gen1")
        self.assertEqual(report["resolution_id"], self.digest(report))
        self.assertEqual(report["current_observations"]["trust_class"], "fixture_diagnostic")
        self.assertFalse(report["current_observations"]["action_eligible"])

    def test_ambiguous_name_blocks_without_guessing(self):
        report = self.report("ambiguous", "Duplicate")
        self.assertEqual(report["blocked"]["code"], "blocked_ambiguous_model")
        self.assertEqual([row["framework"] for row in report["selection"]["candidates"]], ["nemo", "vllm"])

    def test_framework_selector_still_requires_current_host_preflight(self):
        report = self.report("ambiguous", "Duplicate", "--framework", "vllm")
        self.assertEqual(report["blocked"]["code"], "blocked_missing_required_field")

    def test_missing_model_and_selector_miss_are_public_states(self):
        missing = self.report("complete zoo", "Absent")
        selector_miss = self.report("ambiguous", "Duplicate", "--framework", "pytorch")
        self.assertEqual(missing["blocked"]["code"], "blocked_model_not_found")
        self.assertEqual(selector_miss["blocked"]["code"], "blocked_ambiguous_model")

    def test_non_authoritative_modelzoo_root_blocks(self):
        result = subprocess.run(
            [sys.executable, str(CLI), "--modelzoo-root", str(FIXTURES / "complete zoo"), "--model", "Complete-7B", "--framework", "vllm"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 20, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["blocked"]["code"], "blocked_malformed_metadata")
        self.assertIn("modelzoo.git_identity", report["blocked"]["missing_or_conflicting_fields"])

    def test_malformed_metadata_retains_diagnostic_detail(self):
        malformed = self.report("malformed", "Broken", "--framework", "vllm")
        wrong_type = self.report("wrong-type", "Wrong-Type", "--framework", "vllm")
        noncanonical_bool = self.report("noncanonical-bool", "Noncanonical", "--framework", "vllm")
        self.assertEqual(malformed["blocked"]["code"], "blocked_malformed_metadata")
        self.assertEqual(malformed["blocked"]["details"][0]["detail"], "yaml_parse_error")
        self.assertIsNotNone(malformed["sources"]["metafile"]["sha256"])
        self.assertEqual(wrong_type["blocked"]["code"], "blocked_malformed_metadata")
        self.assertIsNotNone(wrong_type["sources"]["metafile"]["sha256"])
        self.assertEqual(noncanonical_bool["blocked"]["code"], "blocked_malformed_metadata")

    def test_yaml_alias_is_rejected_without_construction(self):
        report = self.report("unsafe-yaml", "Unsafe", "--framework", "vllm")
        self.assertEqual(report["blocked"]["code"], "blocked_malformed_metadata")

    def test_unsupported_framework_is_parsed_then_blocked(self):
        report = self.report("unsupported", "Nemo-Model", "--framework", "nemo")
        self.assertEqual(report["blocked"]["code"], "blocked_unsupported_framework")
        self.assertEqual(report["selection"]["framework"], "nemo")
        self.assertIsNotNone(report["sources"]["metafile"]["sha256"])

    def test_missing_readme_fields_and_infer_false_block(self):
        missing = self.report("missing-readme-fields", "Sparse", "--framework", "vllm")
        absent = self.report("readme-absent", "No-Readme", "--framework", "vllm")
        infer_false = self.report("infer-false", "No-Infer", "--framework", "vllm")
        self.assertEqual(missing["blocked"]["code"], "blocked_missing_required_field")
        self.assertEqual(absent["blocked"]["code"], "blocked_missing_required_field")
        self.assertIsNone(absent["sources"]["readme"]["path"])
        self.assertEqual(infer_false["blocked"]["code"], "blocked_missing_required_field")
        self.assertIn("component_refs.vllm", absent["blocked"]["missing_or_conflicting_fields"])
        self.assertTrue(absent["blocked"]["evidence"])
        self.assertIn("provide_missing_required_evidence", missing["blocked"]["recovery_inputs"])

    def test_extra_metadata_and_numeric_parameters_are_preserved(self):
        report = self.report("extra-metadata", "Extended", "--framework", "nemo")
        self.assertEqual(report["blocked"]["code"], "blocked_unsupported_framework")
        fields = report["sources"]["metafile"]["fields"]
        self.assertEqual(fields["Parameters"], 7)
        self.assertEqual(fields["ExtraField"], {"source": "fixture"})

    def test_conflicting_deployment_commands_block(self):
        report = self.report("conflicting-readme", "Conflict", *self.complete_arguments())
        self.assertEqual(report["blocked"]["code"], "blocked_conflicting_source_claims")
        self.assertIn("serve_contract", report["conflicts"])

    def test_critical_source_conflict_is_not_masked_by_missing_preflight(self):
        report = self.report("conflicting-readme", "Conflict", "--framework", "vllm")
        self.assertEqual(report["blocked"]["code"], "blocked_conflicting_source_claims")

    def test_preflight_requires_a_trusted_signature(self):
        report = self.report("complete zoo", "Complete-7B", "--framework", "vllm", "--preflight", str(self.preflight_path))
        self.assertEqual(report["blocked"]["code"], "blocked_missing_required_field")
        self.assertIn("trusted_observation_key_missing", str(report["blocked"]["details"]))

    def test_digest_mismatch_in_sealed_evidence_blocks(self):
        document = json.loads(self.preflight_path.read_text(encoding="utf-8"))
        document["base_image"]["evidence"]["sha256"] = "sha256:" + "0" * 64
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            preflight = Path(directory) / "preflight.json"
            preflight.write_text(json.dumps(document), encoding="utf-8")
            report = self.report("complete zoo", "Complete-7B", "--framework", "vllm", "--preflight", str(preflight), "--test-observation-public-key", str(self.fixture_public_key))
        self.assertEqual(report["blocked"]["code"], "blocked_missing_required_field")
        self.assertIn("evidence_digest_mismatch:base_image", str(report["blocked"]["details"]))

    def test_readme_secret_and_remote_credentials_are_not_serialized(self):
        sensitive_readme = self.fixture_roots["sensitive"] / "vllm" / "models" / "Sensitive" / "README.md"
        sensitive_readme.write_text(
            sensitive_readme.read_text(encoding="utf-8")
            + "\n## Start Service\n```bash\nvllm serve --model /models/Sensitive --api-key super-secret\n```\n",
            encoding="utf-8",
        )
        self.git(self.fixture_roots["sensitive"], "add", ".")
        self.git(self.fixture_roots["sensitive"], "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "credential fixture")
        self.git(self.fixture_roots["sensitive"], "remote", "set-url", "origin", "https://user:super-secret@example.invalid/ModelZoo.git")
        report = self.report("sensitive", "Sensitive", "--framework", "vllm")
        serialized = json.dumps(report)
        self.assertNotIn("super-secret", serialized)
        self.assertNotIn("user:", serialized)

    def test_environment_values_and_remote_query_credentials_are_redacted(self):
        readme = self.fixture_roots["sensitive"] / "vllm" / "models" / "Sensitive" / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8") + "\n## Environment Variables\n```bash\nexport VLLM_EXTRA=super-secret\n```\n",
            encoding="utf-8",
        )
        self.git(self.fixture_roots["sensitive"], "add", ".")
        self.git(self.fixture_roots["sensitive"], "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "environment fixture")
        self.git(self.fixture_roots["sensitive"], "remote", "set-url", "origin", "https://example.invalid/ModelZoo.git?access_token=super-secret")
        report = self.report("sensitive", "Sensitive", "--framework", "vllm")
        serialized = json.dumps(report)
        self.assertNotIn("super-secret", serialized)
        self.assertIsNone(report["modelzoo"]["remote"])

    def test_model_path_override_retains_the_readme_claim_and_decision(self):
        report = self.report("complete zoo", "Complete-7B", *self.complete_arguments())
        model_path = report["resolved"]["model_path"]
        self.assertNotEqual(model_path, report["source_claims"]["weight_paths"][0]["value"])
        self.assertEqual(report["resolved"]["model_path_resolution_reason"], "user_override")
        self.assertIn("model_path", report["conflicts"])

    def test_preflight_covers_ref_hardware_and_authorization_blocks(self):
        cases = [
            (lambda doc: doc.update(weight_path="/missing"), "blocked_missing_asset"),
            (lambda doc: doc["component_sources"]["vllm"].update(ref="0" * 40), "blocked_unresolved_component_ref"),
            (lambda doc: (doc.update(intent="validate_dlc"), doc["hardware"].update(available=False)), "blocked_missing_hardware"),
            (lambda doc: doc["authorization"].update(authorized=False), "blocked_missing_authorization"),
            (lambda doc: doc.update(intent="validate_tyd"), "blocked_missing_hardware"),
            (lambda doc: doc["base_image"].update(identity=None), "blocked_missing_required_field"),
            (lambda doc: doc["framework_package"].update(identity=""), "blocked_missing_required_field"),
            (lambda doc: doc["hardware"].update(generation="unknown"), "blocked_missing_required_field"),
        ]
        base = json.loads(self.preflight_path.read_text(encoding="utf-8"))
        for mutation, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
                document = json.loads(json.dumps(base))
                mutation(document)
                root = Path(directory)
                self.reseal_preflight(document, root)
                preflight = root / "preflight.json"
                preflight.write_text(json.dumps(document), encoding="utf-8")
                report = self.report(
                    "complete zoo", "Complete-7B", "--framework", "vllm", "--preflight", str(preflight),
                    "--test-observation-public-key", str(self.fixture_public_key),
                )
                self.assertEqual(report["blocked"]["code"], expected)

    def test_nested_declared_name_and_sensitive_readme_are_safe(self):
        nested = self.report("nested", "Wan2.1", "--framework", "pytorch")
        sensitive = self.report("sensitive", "Sensitive", "--framework", "vllm")
        self.assertEqual(nested["blocked"]["code"], "blocked_unsupported_framework")
        serialized = json.dumps(sensitive)
        self.assertNotIn("super-secret", serialized)
        self.assertNotIn("192.168.1.20", serialized)

    def test_source_tree_remains_byte_identical(self):
        before = self.tree_digest(self.fixture_roots["complete zoo"])
        self.run_cli("complete zoo", "Complete-7B", *self.complete_arguments())
        self.assertEqual(before, self.tree_digest(self.fixture_roots["complete zoo"]))

    def test_tyd_and_final_report_contract_match_knowledge_public_contract(self):
        report = self.report("complete zoo", "Complete-7B", *self.complete_arguments())
        workflow = report["workflow_contract"]
        tyd = workflow["tyd"]
        self.assertFalse(tyd["image_env_alone_sufficient"])
        self.assertTrue(tyd["process_environment_evidence_required"])
        self.assertEqual(set(tyd["build_components"]), set(tyd["compile_process_environment"]))
        for component in tyd["build_components"]:
            self.assertEqual(tyd["compile_process_environment"][component]["DLC_TPU_VERSION"], "2")
        self.assertIn("PyTorch DLC Backend", tyd["build_components"])
        self.assertIn("DLC_Custom_Kernel Repository", tyd["build_components"])
        self.assertIn("vLLM", tyd["build_components"])
        self.assertIn("validation_report", workflow["dlc"]["artifact_identity"])
        self.assertIn("validation_report", workflow["tyd"]["artifact_identity"])
        self.assertIn("model_functional_pass", workflow["tyd"]["validation_states"])
        provenance = workflow["tyd"]["component_provenance_record"]
        self.assertEqual(provenance["missing_record_status"], "blocked_missing_required_field")
        self.assertFalse(provenance["formal_tag_and_full_stack_pass_allowed_when_incomplete"])
        self.assertIn("artifact_sha256", provenance["required_fields"])
        self.assertIn("compile_process_environment_evidence", provenance["required_fields"])
        lifecycle = provenance["epoch_lifecycle"]
        self.assertEqual(lifecycle["mode"], "append_only")
        self.assertTrue(lifecycle["failed_epoch_evidence_retained"])
        self.assertTrue(lifecycle["completed_component_provenance_retained"])
        self.assertTrue(lifecycle["retry_requires_new_epoch"])
        self.assertIn("failed", lifecycle["states"])
        self.assertIn("superseded", lifecycle["states"])
        self.assertIn("blocked_*", workflow["tyd"]["validation_states"])
        self.assertEqual(workflow["validation_report_schema"], "modelzoo-dlc-tyd-validation-report/v1")
        self.assertIn("blocked_cleanup_incomplete", workflow["terminal_blockers"])
        self.assertEqual(workflow["final_report_sections"], ["modelzoo_claims", "current_observations", "inferences", "execution_evidence", "unverified_scope"])

    @staticmethod
    def digest(document: dict) -> str:
        payload = {key: document[key] for key in ("inputs", "modelzoo", "selection", "sources", "source_claims", "current_observations", "resolved", "missing_fields", "conflicts", "blocked")}
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def tree_digest(root: Path) -> str:
        digest = hashlib.sha256()
        for path in sorted(path for path in root.rglob("*") if path.is_file()):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()


if __name__ == "__main__":
    unittest.main()
