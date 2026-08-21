import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts" / "validate-chipltech-organization.py"
KNOWLEDGE_ROOT = ROOT.parent / "chipltech-knowledge-base"


def load_validator():
    spec = importlib.util.spec_from_file_location("organization_validator", VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ChipltechOrganizationDiscoveryTests(unittest.TestCase):
    def test_default_discovery_and_repository_closure(self):
        result = subprocess.run(
            [str(VALIDATOR), "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertTrue(report["passed"])
        self.assertEqual(Path(report["skills_root"]), ROOT)
        self.assertEqual(Path(report["knowledge_root"]), KNOWLEDGE_ROOT)
        self.assertGreaterEqual(report["capability_count"], 1)
        self.assertEqual(report["validated_lesson_count"], 4)
        quality = report["quality_view"]["levels"]
        self.assertEqual(quality["L1"]["status"], "passed")
        self.assertEqual(quality["L2"]["status"], "not_reported")
        self.assertEqual(quality["L3"]["status"], "not_reported")
        self.assertEqual(quality["ST"]["status"], "not_reported")
        self.assertEqual(quality["Hardware"]["status"], "not_reported")
        self.assertEqual(report["quality_view"]["runtime_quality"], "not_reported")

    def test_behavior_quality_consumes_completed_run_artifact(self):
        manifest = json.loads(
            (ROOT / "tests/workflow_behavior/fixtures/representative-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        manifest_path = ROOT / "tests/workflow_behavior/fixtures/representative-manifest.json"
        manifest_digest = "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        source_digest = load_validator()._source_tree_digest(ROOT)
        run = {
            "schema": "workflow-behavior-run-result/v1",
            "run_binding": {
                "manifest_digest": manifest_digest,
                "case_ids": [case["id"] for case in manifest["cases"]],
                "repository_head": "0" * 40,
                "repository_status_digest": "0" * 64,
                "repository_snapshot_digest": "sha256:" + "0" * 64,
                "repository_source_digest": source_digest,
            },
            "terminal_state": "suite_passed",
            "problems": [],
            "authoritative": False,
            "runtime_acceptance": False,
            "claim_boundary": "Behavior fixtures verify software contracts only.",
            "cases": [
                {
                    "id": case["id"],
                    "workflow": case["workflow"],
                    "quality_kind": case["quality_kind"],
                    "terminal_state": "passed",
                    "authoritative": False,
                    "runtime_acceptance": False,
                    "claim_boundary_preserved": True,
                    "forbidden_actions": case["forbidden_actions"],
                    "workspace_mutation_observed": False,
                }
                for case in manifest["cases"]
            ],
        }
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            artifact = Path(directory) / "behavior-run.json"
            artifact.write_text(json.dumps(run), encoding="utf-8")
            result = subprocess.run(
                [str(VALIDATOR), "--json", "--behavior-run", str(artifact)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        level = json.loads(result.stdout)["quality_view"]["levels"]["L2"]
        self.assertEqual(level["status"], "passed")
        self.assertEqual(level["executed_workflows"], sorted(
            case["workflow"] for case in manifest["cases"]
            if case["quality_kind"] == "behavior"
        ))

    def test_invalid_behavior_run_and_manifest_types_fail_without_traceback(self):
        validator = load_validator()
        errors = []
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            path = Path(directory) / "run.json"
            path.write_text("[]", encoding="utf-8")
            status, workflows = validator._load_behavior_run(path, errors)
        self.assertEqual(status, "failed")
        self.assertEqual(workflows, [])
        self.assertTrue(errors)

    def test_validator_does_not_execute_skills_root_commands(self):
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertNotIn("import subprocess", source)
        self.assertNotIn("subprocess.", source)

    def test_failed_behavior_run_fails_validation_instead_of_reporting_presence(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            artifact = Path(directory) / "behavior-run.json"
            artifact.write_text(
                json.dumps(
                    {
                        "schema": "workflow-behavior-run-result/v1",
                        "run_binding": {
                            "manifest_digest": "sha256:" + "0" * 64,
                            "case_ids": ["failed-case"],
                            "repository_head": "0" * 40,
                            "repository_status_digest": "0" * 64,
                            "repository_snapshot_digest": "sha256:" + "0" * 64,
                        },
                        "terminal_state": "suite_failed",
                        "problems": [],
                        "authoritative": False,
                        "runtime_acceptance": False,
                        "claim_boundary": "Behavior fixtures verify software contracts only.",
                        "cases": [
                            {
                                "id": "failed-case",
                                "workflow": "pd-separation",
                                "quality_kind": "behavior",
                                "terminal_state": "assertion_failed",
                                "authoritative": False,
                                "runtime_acceptance": False,
                                "claim_boundary_preserved": True,
                                "forbidden_actions": ["runtime_acceptance"],
                                "workspace_mutation_observed": False,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            report = validator.validate_organization(ROOT, KNOWLEDGE_ROOT, artifact)
        self.assertFalse(report["passed"])
        self.assertEqual(report["quality_view"]["levels"]["L2"]["status"], "failed")

    def test_behavior_run_must_match_manifest_and_report_no_mutation(self):
        validator = load_validator()
        manifest_path = ROOT / "tests/workflow_behavior/fixtures/representative-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        digest = "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        cases = [
            {
                "id": case["id"],
                "workflow": case["workflow"],
                "quality_kind": case["quality_kind"],
                "terminal_state": "passed",
                "authoritative": False,
                "runtime_acceptance": False,
                "claim_boundary_preserved": True,
                "forbidden_actions": case["forbidden_actions"],
                "workspace_mutation_observed": False,
            }
            for case in manifest["cases"]
        ]
        base = {
            "schema": "workflow-behavior-run-result/v1",
            "run_binding": {
                "manifest_digest": digest,
                "case_ids": [case["id"] for case in manifest["cases"]],
                "repository_head": "0" * 40,
                "repository_status_digest": "0" * 64,
                "repository_snapshot_digest": "sha256:" + "0" * 64,
            },
            "terminal_state": "suite_passed",
            "problems": [],
            "authoritative": False,
            "runtime_acceptance": False,
            "claim_boundary": "Behavior fixtures verify software contracts only.",
            "cases": cases,
        }
        variants = []
        wrong_digest = json.loads(json.dumps(base))
        wrong_digest["run_binding"]["manifest_digest"] = "sha256:" + "0" * 64
        variants.append(wrong_digest)
        missing_case = json.loads(json.dumps(base))
        missing_case["cases"].pop()
        variants.append(missing_case)
        wrong_case_ids = json.loads(json.dumps(base))
        wrong_case_ids["run_binding"]["case_ids"] = list(reversed(
            wrong_case_ids["run_binding"]["case_ids"]
        ))
        variants.append(wrong_case_ids)
        wrong_workflow = json.loads(json.dumps(base))
        wrong_workflow["cases"][0]["workflow"] = "other"
        variants.append(wrong_workflow)
        mutated = json.loads(json.dumps(base))
        mutated["cases"][0]["workspace_mutation_observed"] = True
        variants.append(mutated)
        for run in variants:
            with self.subTest(run=run):
                with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
                    artifact = Path(directory) / "behavior-run.json"
                    artifact.write_text(json.dumps(run), encoding="utf-8")
                    report = validator.validate_organization(ROOT, KNOWLEDGE_ROOT, artifact)
                self.assertFalse(report["passed"])
                self.assertEqual(report["quality_view"]["levels"]["L2"]["status"], "failed")

    def test_reference_paths_reject_absolute_parent_and_symlink_escape(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            root = Path(directory)
            skills = root / "skills"
            knowledge = root / "knowledge"
            skills.mkdir()
            knowledge.mkdir()
            outside = root / "outside.md"
            outside.write_text("# Outside\n", encoding="utf-8")
            (knowledge / "link.md").symlink_to(outside)
            for ref in ("/etc/passwd", "../outside.md", "link.md"):
                errors = []
                validator._check_ref(ref, "test", skills, knowledge, errors)
                self.assertEqual(len(errors), 1)
                self.assertIn("escapes its root", errors[0])

    def test_capability_manifest_closes_quickstart_owner_and_publication(self):
        manifest = yaml.safe_load(
            (KNOWLEDGE_ROOT / "agent-context" / "capability-manifest.yaml").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["schema"], "chipltech-capability-catalog/v1")
        ids = [row["capability_id"] for row in manifest["capabilities"]]
        self.assertEqual(len(ids), len(set(ids)))
        for row in manifest["capabilities"]:
            with self.subTest(capability_id=row["capability_id"]):
                self.assertRegex(row["capability_id"], r"^cap\.[a-z0-9.-]+$")
                self.assertIn("#", row["quickstart_ref"])
                self.assertTrue(row["owner_skill"])
                self.assertEqual(row["publication_ref"], "SKILLHUB.yaml")
                self.assertTrue(row["claim_boundary_ref"])

    def test_ask_contract_is_published_at_human_entrypoints(self):
        required = (
            "Selected capability:",
            "Selection basis:",
            "Minimum missing inputs:",
            "First safe action:",
            "Expected terminal states:",
            "Evidence boundary:",
        )
        for path in (
            KNOWLEDGE_ROOT / "README.md",
            KNOWLEDGE_ROOT / "agent-context" / "new-session-context.md",
        ):
            text = path.read_text(encoding="utf-8")
            for field in required:
                self.assertIn(field, text, f"{field} missing from {path}")

    def test_lesson_index_has_four_reviewed_cases_and_historical_default(self):
        index = yaml.safe_load(
            (KNOWLEDGE_ROOT / "validated-lessons" / "index.yaml").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(index["schema"], "chipltech-validated-lesson-index/v1")
        self.assertEqual(index["unlisted_case_default"], "historical_unreviewed")
        self.assertEqual(len(index["lessons"]), 4)
        for lesson in index["lessons"]:
            with self.subTest(lesson_id=lesson["lesson_id"]):
                self.assertEqual(lesson["status"], "validated")
                self.assertTrue(lesson["source_cases"])
                self.assertTrue(lesson["rule_refs"])
                self.assertTrue(lesson["test_refs"])
                self.assertIn("does not", lesson["claim_boundary"].lower())
                self.assertNotEqual(lesson["evidence_class"], "runtime_observation")

    def test_broken_capability_owner_fails_closed(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            root = Path(directory)
            knowledge = root / "knowledge"
            skills = root / "skills"
            (knowledge / "agent-context").mkdir(parents=True)
            (knowledge / "validated-lessons").mkdir()
            (knowledge / "prompt-examples").mkdir()
            (skills / "skills" / "engineering").mkdir(parents=True)
            (knowledge / "CONTEXT.md").write_text("# Context\n", encoding="utf-8")
            (knowledge / "README.md").write_text("# Knowledge\n", encoding="utf-8")
            (knowledge / "prompt-examples" / "all-supported-capabilities-quickstart.md").write_text(
                "# Catalog\n\n## Example\n\nCapability ID: `cap.example`\n",
                encoding="utf-8",
            )
            (knowledge / "agent-context" / "capability-manifest.yaml").write_text(
                """schema: chipltech-capability-catalog/v1
capabilities:
  - capability_id: cap.example
    human_entry: Example
    quickstart_ref: prompt-examples/all-supported-capabilities-quickstart.md#example
    owner_skill: missing-owner
    publication_ref: SKILLHUB.yaml
    claim_boundary_ref: prompt-examples/all-supported-capabilities-quickstart.md#example
""",
                encoding="utf-8",
            )
            (knowledge / "validated-lessons" / "index.yaml").write_text(
                "schema: chipltech-validated-lesson-index/v1\nunlisted_case_default: historical_unreviewed\nlessons: []\n",
                encoding="utf-8",
            )
            (skills / "SKILLHUB.yaml").write_text("skills: []\n", encoding="utf-8")

            report = validator.validate_organization(skills, knowledge)

        self.assertFalse(report["passed"])
        self.assertTrue(
            any("missing-owner" in error and "owner" in error for error in report["errors"])
        )

    def test_validator_rejects_broken_lesson_ref_and_claim_boundary(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            root = Path(directory)
            knowledge = root / "knowledge"
            skills = root / "skills"
            (knowledge / "agent-context").mkdir(parents=True)
            (knowledge / "validated-lessons").mkdir()
            (knowledge / "prompt-examples").mkdir()
            owner = skills / "skills" / "engineering" / "example-owner"
            owner.mkdir(parents=True)
            (owner / "SKILL.md").write_text("# Owner\n", encoding="utf-8")
            (knowledge / "CONTEXT.md").write_text("# Context\n", encoding="utf-8")
            (knowledge / "README.md").write_text("# Knowledge\n", encoding="utf-8")
            (knowledge / "prompt-examples" / "all-supported-capabilities-quickstart.md").write_text(
                "# Catalog\n\n## Example\n\nCapability ID: `cap.example`\n",
                encoding="utf-8",
            )
            (knowledge / "agent-context" / "capability-manifest.yaml").write_text(
                """schema: chipltech-capability-catalog/v1
capabilities:
  - capability_id: cap.example
    human_entry: Example
    quickstart_ref: prompt-examples/all-supported-capabilities-quickstart.md#example
    owner_skill: example-owner
    owner_contract_ref: skills/engineering/example-owner/SKILL.md
    minimum_inputs_ref: prompt-examples/all-supported-capabilities-quickstart.md#example
    negative_scope_ref: skills/engineering/example-owner/SKILL.md
    hardware_authorization_ref: skills/engineering/example-owner/SKILL.md
    terminal_states_ref: skills/engineering/example-owner/SKILL.md
    claim_boundary_ref: prompt-examples/all-supported-capabilities-quickstart.md#example
    publication_ref: SKILLHUB.yaml
""",
                encoding="utf-8",
            )
            (knowledge / "validated-lessons" / "index.yaml").write_text(
                """schema: chipltech-validated-lesson-index/v1
unlisted_case_default: historical_unreviewed
lessons:
  - lesson_id: lesson.example
    status: validated
    statement: Example
    source_cases: [case-studies/missing.md]
    identity_scope: Historical fixture
    applies_to: Example
    does_not_apply_to: Other examples
    evidence_class: historical_case
    evidence_refs: [case-studies/missing.md]
    validation_method: Review
    counterexample: Counterexample
    owner_skill: example-owner
    rule_refs: [skills/engineering/example-owner/SKILL.md]
    test_refs: [tests/chipltech_context/test_organization_discovery.py]
    review_date: 2026-08-21
    claim_boundary: Establishes everything.
""",
                encoding="utf-8",
            )
            (skills / "SKILLHUB.yaml").write_text(
                """skills:
  - name: example-owner
    path: skills/engineering/example-owner
""",
                encoding="utf-8",
            )
            report = validator.validate_organization(skills, knowledge)

        self.assertFalse(report["passed"])
        self.assertTrue(any("missing file" in error for error in report["errors"]))
        self.assertTrue(any("claim boundary" in error for error in report["errors"]))


class ChipltechOrganizationLessonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = yaml.safe_load(
            (KNOWLEDGE_ROOT / "validated-lessons" / "index.yaml").read_text(
                encoding="utf-8"
            )
        )
        cls.lessons = {
            lesson["lesson_id"]: lesson for lesson in cls.index["lessons"]
        }

    def assert_lesson_contract(self, lesson_id, statement, required_rule_terms):
        lesson = self.lessons[lesson_id]
        self.assertEqual(lesson["status"], "validated")
        self.assertEqual(lesson["statement"], statement)
        rule_text = "\n".join(
            load_validator()
            ._resolve_ref(ref, ROOT, KNOWLEDGE_ROOT)[0]
            .read_text(encoding="utf-8")
            .lower()
            for ref in lesson["rule_refs"]
        )
        for term in required_rule_terms:
            self.assertIn(term.lower(), rule_text)

    def test_collective_validate_then_commit_lesson_contract(self):
        self.assert_lesson_contract(
            "lesson.collective.validate-then-commit",
            "A collective fallback is a newly qualified candidate and must remain unknown until graph, channel, rank order, rank domain, uniqueness, and metadata checks all pass.",
            ("validate-then-commit", "graph", "channel", "rank order", "metadata"),
        )

    def test_optional_schema_descriptor_lesson_contract(self):
        self.assert_lesson_contract(
            "lesson.abi.optional-schema-is-not-optional-descriptor",
            "An optional public operator argument set to None does not prove that its KernelDesc descriptor slot is absent or compatible with a frozen DLC Custom Kernel Entry ABI.",
            ("Public Operator Schema", "KernelDesc argument order", "DLC Custom Kernel Entry ABI"),
        )

    def test_quantization_refinement_lesson_contract(self):
        self.assert_lesson_contract(
            "lesson.quantization.refine-before-partition",
            "Lossless quantization group refinement must close metadata and permutation ownership before Tensor Parallel slicing, while physical padding remains a separate zero-contribution kernel representation concern.",
            ("refined quantization group", "permutation", "logical shard", "zero-contribution padding"),
        )

    def test_evidence_ledger_summary_lesson_contract(self):
        self.assert_lesson_contract(
            "lesson.reporting.evidence-ledger-before-summary",
            "A decision summary must bind each claim to an Evidence Ledger class and identity before compression, preserving separate feasibility, adaptation-completion, and stable-delivery states.",
            ("Evidence Ledger", "路线可行", "当前完成到哪一阶段", "稳定交付"),
        )


class ChipltechCapabilityCatalogClosureTests(unittest.TestCase):
    def test_quickstart_capability_ids_equal_manifest_ids(self):
        validator = load_validator()
        manifest = yaml.safe_load(
            (KNOWLEDGE_ROOT / "agent-context" / "capability-manifest.yaml").read_text(
                encoding="utf-8"
            )
        )
        quickstart = (
            KNOWLEDGE_ROOT
            / "prompt-examples"
            / "all-supported-capabilities-quickstart.md"
        ).read_text(encoding="utf-8")
        quickstart_ids = set(
            validator.re.findall(
                r"^Capability ID:\s*`(cap\.[a-z0-9.-]+)`\s*$",
                quickstart,
                flags=validator.re.MULTILINE,
            )
        )
        manifest_ids = {
            capability["capability_id"] for capability in manifest["capabilities"]
        }
        self.assertEqual(quickstart_ids, manifest_ids)

    def test_validator_rejects_quickstart_capability_missing_from_manifest(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            knowledge = Path(directory) / "knowledge"
            source = KNOWLEDGE_ROOT
            (knowledge / "agent-context").mkdir(parents=True)
            (knowledge / "validated-lessons").mkdir()
            (knowledge / "prompt-examples").mkdir()
            for relative in ("CONTEXT.md", "README.md"):
                (knowledge / relative).write_text(
                    (source / relative).read_text(encoding="utf-8"), encoding="utf-8"
                )
            (knowledge / "agent-context" / "capability-manifest.yaml").write_text(
                "schema: chipltech-capability-catalog/v1\n"
                "catalog_ref: prompt-examples/all-supported-capabilities-quickstart.md\n"
                "capabilities: []\n",
                encoding="utf-8",
            )
            (knowledge / "validated-lessons" / "index.yaml").write_text(
                "schema: chipltech-validated-lesson-index/v1\n"
                "unlisted_case_default: historical_unreviewed\n"
                "lessons: []\n",
                encoding="utf-8",
            )
            (knowledge / "prompt-examples" / "all-supported-capabilities-quickstart.md").write_text(
                "# Catalog\n\n## Unmanifested\n\nCapability ID: `cap.unmanifested`\n",
                encoding="utf-8",
            )

            report = validator.validate_organization(ROOT, knowledge)

        self.assertFalse(report["passed"])
        self.assertTrue(
            any(
                "missing from manifest=['cap.unmanifested']" in error
                for error in report["errors"]
            )
        )


if __name__ == "__main__":
    unittest.main()
