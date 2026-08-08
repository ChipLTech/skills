import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "validate-restricted-reference-governance.py"
CONFIG = ROOT / "config" / "restricted-reference-governance.json"
FIXTURE = Path(__file__).parent / "fixtures" / "negative" / "restricted-execution-asset.txt"

SPEC = importlib.util.spec_from_file_location("restricted_reference_governance", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class RestrictedReferenceGovernanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.governance = MODULE.validate_governance(json.loads(CONFIG.read_text(encoding="utf-8")))
        cls.manifest = MODULE.build_manifest(ROOT)

    def test_live_manifest_is_deterministic_and_has_unique_destinations(self):
        first = MODULE.canonical_bytes(self.manifest)
        second = MODULE.canonical_bytes(MODULE.build_manifest(ROOT))
        self.assertEqual(first, second)
        identities = [(item["channel"], item["destination_path"]) for item in self.manifest]
        self.assertEqual(len(identities), len(set(identities)))
        self.assertTrue(all(item["sha256"].startswith("sha256:") for item in self.manifest))

    def test_kilo_default_matches_actual_bucket_selection_and_generated_roles(self):
        expected = {
            path.parent.name
            for bucket in ("engineering", "productivity", "misc")
            for path in (ROOT / "skills" / bucket).glob("*/SKILL.md")
        }
        for channel in ("kilo_global_default", "kilo_project_default"):
            actual = {item["package"] for item in self.manifest if item["channel"] == channel}
            self.assertEqual(actual, expected)
        project_entries = [item for item in self.manifest if item["channel"] == "kilo_project_default"]
        wrappers = [item for item in project_entries if item["destination_path"].startswith("command/")]
        metadata = [item for item in project_entries if item["destination_path"].endswith("/.kilo-link-source")]
        self.assertEqual({item["package"] for item in wrappers}, expected)
        self.assertEqual({item["package"] for item in metadata}, expected)
        self.assertTrue(all(item["role"] == "template" for item in wrappers))
        self.assertTrue(all(item["role"] == "installation_metadata" for item in metadata))

    def test_claude_agent_linker_is_all_non_deprecated_skills(self):
        expected = {
            skill.parent.name
            for bucket in ROOT.joinpath("skills").iterdir()
            if bucket.is_dir() and bucket.name != "deprecated"
            for skill in bucket.glob("*/SKILL.md")
        }
        actual = {
            item["package"]
            for item in self.manifest
            if item["channel"] == "claude_agent_linker"
        }
        self.assertEqual(actual, expected)
        self.assertIn("obsidian-vault", actual)
        self.assertIn("writing-beats", actual)

    def test_plugin_inventory_has_exact_declared_packages(self):
        plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        expected = {Path(value).name for value in plugin["skills"]}
        actual = {item["package"] for item in self.manifest if item["channel"] == "plugin"}
        self.assertEqual(actual, expected)

    def test_skillhub_inventory_expands_only_declared_members(self):
        rows = MODULE.parse_skillhub(ROOT / "SKILLHUB.yaml")
        expected_packages = {row["name"] for row in rows}
        actual_entries = [item for item in self.manifest if item["channel"] == "skillhub"]
        self.assertEqual({item["package"] for item in actual_entries}, expected_packages)
        for row in rows:
            declared = tuple(member.rstrip("/") for member in row["files"])
            members = [
                PurePosixPath(item["destination_path"]).relative_to("skills", row["name"]).as_posix()
                for item in actual_entries
                if item["package"] == row["name"]
            ]
            self.assertTrue(
                all(any(member == value or member.startswith(value + "/") for value in declared) for member in members),
                row["name"],
            )

    def test_live_distribution_has_no_synthetic_prohibited_import(self):
        result = MODULE.validate(ROOT, CONFIG)
        prohibited = [item for item in result["findings"] if item["kind"] == "prohibited_import"]
        self.assertEqual(prohibited, [])
        self.assertEqual(result["status"], "blocked_legal_boundary")
        self.assertEqual(
            result["legal_blockers"],
            [{"kind": "source", "id": "cannbot-local-static-snapshot-20260808"}],
        )

    def test_synthetic_source_digest_matches_negative_fixture(self):
        source = next(
            row for row in self.governance["source_register"]
            if row["id"] == "synthetic-restricted-test-source"
        )
        self.assertEqual(source["source_revision_or_sha256"], MODULE.sha256_bytes(FIXTURE.read_bytes()))

    def test_review_terms_are_review_only(self):
        for term in MODULE.REVIEW_TERMS:
            with self.subTest(term=term):
                item = self.synthetic_entry("package/reference.txt", "bundled_reference")
                findings = MODULE.scan_entries([item], self.governance, {item["source_path"]: term.encode()})
                self.assertEqual([finding["kind"] for finding in findings], ["review_required"])

    def test_governance_investigation_and_negative_fixture_are_not_execution_assets(self):
        content = FIXTURE.read_bytes()
        for role in ("governance_record", "investigation_record", "negative_fixture"):
            with self.subTest(role=role):
                item = self.synthetic_entry(f"records/{role}.txt", role)
                self.assertEqual(MODULE.scan_entries([item], self.governance, {item["source_path"]: content}), [])

    def test_negative_fixture_fails_if_packaged_as_execution_asset(self):
        item = self.synthetic_entry("skills/example/scripts/fixture.txt", "executable_script")
        findings = MODULE.scan_entries(
            [item], self.governance, {item["source_path"]: FIXTURE.read_bytes()}
        )
        self.assertEqual(
            {finding["kind"] for finding in findings},
            {"prohibited_import", "review_required"},
        )
        prohibited_matches = {
            finding["match"] for finding in findings if finding["kind"] == "prohibited_import"
        }
        self.assertEqual(
            prohibited_matches,
            {
                "SYNTHETIC_RESTRICTED_IMPORT_R0_A",
                self.governance["source_register"][0]["source_revision_or_sha256"],
            },
        )

    def test_general_similarity_is_not_a_legal_conclusion(self):
        item = self.synthetic_entry("skills/example/reference.txt", "bundled_reference")
        content = b"profile schema performance workflow skill template engineering"
        self.assertEqual(MODULE.scan_entries([item], self.governance, {item["source_path"]: content}), [])

    def test_unresolved_source_is_blocked_legal_boundary(self):
        governance = copy.deepcopy(self.governance)
        for source in governance["source_register"]:
            source["disposition"] = "prohibited"
        governance["source_register"][0]["disposition"] = "blocked_legal_boundary"
        self.assertEqual(MODULE.legal_blockers(governance), [{"kind": "source", "id": "synthetic-restricted-test-source"}])

    def test_allowlist_requires_exact_closed_fields_and_non_glob_path(self):
        valid = {
            "path": "skills/example/reference.txt",
            "match": "torch_npu",
            "reason": "Reviewed synthetic occurrence.",
            "owner": "Governance reviewer",
            "review_date": "2026-08-08",
        }
        governance = copy.deepcopy(self.governance)
        governance["review_allowlist"] = [valid]
        MODULE.validate_governance(governance)
        for key in valid:
            with self.subTest(missing=key):
                invalid = copy.deepcopy(governance)
                del invalid["review_allowlist"][0][key]
                with self.assertRaises(MODULE.GovernanceError):
                    MODULE.validate_governance(invalid)
        invalid = copy.deepcopy(governance)
        invalid["review_allowlist"][0]["path"] = "skills/**/reference.txt"
        with self.assertRaises(MODULE.GovernanceError):
            MODULE.validate_governance(invalid)

    def test_allowlist_suppresses_only_exact_path_and_match(self):
        governance = copy.deepcopy(self.governance)
        governance["review_allowlist"] = [
            {
                "path": "skills/example/reference.txt",
                "match": "torch_npu",
                "reason": "Reviewed synthetic occurrence.",
                "owner": "Governance reviewer",
                "review_date": "2026-08-08",
            }
        ]
        item = self.synthetic_entry("skills/example/reference.txt", "bundled_reference")
        other = self.synthetic_entry("skills/other/reference.txt", "bundled_reference")
        contents = {
            item["source_path"]: b"torch_npu",
            other["source_path"]: b"torch_npu",
        }
        findings = MODULE.scan_entries([item, other], governance, contents)
        self.assertEqual([finding["path"] for finding in findings], ["skills/other/reference.txt"])

    def test_cli_output_is_byte_deterministic(self):
        command = [sys.executable, str(SCRIPT), "--skills-root", str(ROOT)]
        first = subprocess.run(command, capture_output=True, check=False)
        second = subprocess.run(command, capture_output=True, check=False)
        self.assertEqual(first.returncode, second.returncode)
        self.assertEqual(first.stdout, second.stdout)
        result = json.loads(first.stdout)
        self.assertEqual(result["status"], "blocked_legal_boundary")

    @staticmethod
    def synthetic_entry(path: str, role: str) -> dict:
        return {
            "channel": "fixture",
            "package": "example",
            "source_path": path,
            "destination_path": path,
            "role": role,
            "sha256": "sha256:" + "0" * 64,
        }


if __name__ == "__main__":
    unittest.main()
