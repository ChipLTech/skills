import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "skills/engineering/main-to-main-upgrade/scripts/assess-publication-candidate.py"
FIXTURES = Path(__file__).with_name("fixtures") / "publication-candidate"
ASSESSMENT_SCHEMA = ROOT / "skills/engineering/main-to-main-upgrade/references/publication-candidate-assessment-v1.schema.json"


def run_git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def seal(document: dict) -> str:
    payload = {key: value for key, value in document.items() if key != "digest"}
    return digest_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


class PublicationCandidateAssessorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir="/tmp/kilo")
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.remote, self.tested, self.candidate = root / "remote", root / "tested", root / "candidate"
        self._create_repository(self.remote)
        run_git(self.remote, "branch", "-M", "main")
        subprocess.run(["git", "clone", "--quiet", str(self.remote), str(self.tested)], check=True)
        subprocess.run(["git", "clone", "--quiet", str(self.remote), str(self.candidate)], check=True)
        self.base_sha = run_git(self.remote, "rev-parse", "HEAD")
        self._commit(self.tested, "approved.txt", "tested change\n", "tested")
        self._commit(self.candidate, "approved.txt", "tested change\n", "candidate")
        self.tested_sha, self.candidate_sha = run_git(self.tested, "rev-parse", "HEAD"), run_git(self.candidate, "rev-parse", "HEAD")
        run_git(self.remote, "update-ref", "refs/heads/publication", self.base_sha)
        self.handoff, self.artifacts = self._handoff()

    @staticmethod
    def _create_repository(root: Path):
        root.mkdir(); run_git(root, "init", "--quiet"); run_git(root, "config", "user.email", "tests@example.com"); run_git(root, "config", "user.name", "Tests")
        (root / "approved.txt").write_text("base\n"); (root / "excluded.txt").write_text("excluded\n")
        run_git(root, "add", "approved.txt", "excluded.txt"); run_git(root, "commit", "--quiet", "-m", "base")

    @staticmethod
    def _commit(root: Path, relative: str, content: str, message: str):
        run_git(root, "config", "user.email", "tests@example.com"); run_git(root, "config", "user.name", "Tests")
        (root / relative).write_text(content); run_git(root, "add", relative); run_git(root, "commit", "--quiet", "-m", message)

    @staticmethod
    def _git_digest(root: Path, *args: str) -> str:
        return digest_bytes(subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True).stdout)

    def _artifact(self, artifact_id: str, **fields) -> dict:
        artifact = {"artifact_id": artifact_id, **fields}; artifact["digest"] = seal(artifact); return artifact

    def _handoff(self):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        stamp = lambda delta=0: (now + timedelta(minutes=delta)).strftime("%Y-%m-%dT%H:%M:%SZ")
        document = json.loads((FIXTURES / "eligible.json").read_text())
        tested_diff = self._git_digest(self.tested, "diff", "--binary", self.base_sha, self.tested_sha, "--", "approved.txt")
        candidate_diff = self._git_digest(self.candidate, "diff", "--binary", self.base_sha, self.candidate_sha, "--", "approved.txt")
        candidate_tree = self._git_digest(self.candidate, "ls-tree", "-r", self.candidate_sha, "--", "approved.txt")
        document.update(generated_at=stamp(-1), expires_at=stamp(60))
        document["tested_revision"].update(base_sha=self.base_sha, commit_sha=self.tested_sha, tree_sha=run_git(self.tested, "rev-parse", "HEAD^{tree}"))
        candidate = document["publication_candidate"]
        candidate.update(base_sha=self.base_sha, commit_sha=self.candidate_sha, tree_sha=run_git(self.candidate, "rev-parse", "HEAD^{tree}"), created_at=stamp(-5), scoped_diff_digest=candidate_diff, scoped_tree_digest=candidate_tree)
        candidate["patch_equivalence"].update(tested_scoped_diff_digest=tested_diff, candidate_scoped_diff_digest=candidate_diff)
        candidate["remote_observation"].update(target_base_sha=self.base_sha, pr_tip_sha=self.base_sha, observed_at=stamp())
        candidate["lease"].update(target_base_expected_old_sha=self.base_sha, pr_tip_expected_old_sha=self.base_sha)
        scope = digest_bytes(json.dumps({"included_paths": ["approved.txt"], "excluded_paths": ["excluded.txt"], "scoped_diff_digest": candidate_diff, "scoped_tree_digest": candidate_tree}, sort_keys=True, separators=(",", ":")).encode())
        artifacts = {}
        artifacts["wheel"] = self._artifact("wheel", schema_version="vllm-cl-rebuilt-artifact/v1", authority_id="independent-builder", candidate_base_sha=self.base_sha, candidate_commit_sha=self.candidate_sha, artifact_graph_digest=candidate["artifact_graph_digest"], scope_digest=scope, built_at=stamp(-4), expires_at=stamp(30))
        for artifact_id, kind, minute in (("source", "source", -3), ("build", "build", -3), ("runtime", "runtime", -2)):
            artifacts[artifact_id] = self._artifact(artifact_id, schema_version="vllm-cl-publication-gate-evidence/v1", authority_id="independent-ci", kind=kind, status="passed", acceptance_eligible=True, candidate_base_sha=self.base_sha, candidate_commit_sha=self.candidate_sha, artifact_graph_digest=candidate["artifact_graph_digest"], scope_digest=scope, completed_at=stamp(minute), expires_at=stamp(30))
        for action in ("commit", "publication"):
            artifact_id = f"auth-{action}"
            artifacts[artifact_id] = self._artifact(artifact_id, schema_version="vllm-cl-publication-authorization/v1", authority_id="release-owner", producer_authority_id="producer-team", action=action, authorized=True, candidate_base_sha=self.base_sha, candidate_commit_sha=self.candidate_sha, scope_digest=scope, authorized_at=stamp(-1), expires_at=stamp(30))
        candidate["affected_gate_refs"] = [{"artifact_id": key, "digest": value["digest"]} for key, value in artifacts.items() if key in {"source", "build", "runtime"}]
        candidate["rebuilt_artifact_refs"] = [{"artifact_id": "wheel", "digest": artifacts["wheel"]["digest"]}]
        candidate["authorization_refs"] = [{"artifact_id": key, "digest": value["digest"]} for key, value in artifacts.items() if key.startswith("auth-")]
        document["digest"] = seal(document)
        return document, artifacts

    def assess(self, mutate=None, artifact_mutate=None, candidate_root=True, reseal=True, use_dir=False, artifact_map_mutate=None, reseal_artifact_map=True):
        document, artifacts = copy.deepcopy(self.handoff), copy.deepcopy(self.artifacts)
        if mutate: mutate(document)
        if artifact_mutate: artifact_mutate(artifacts)
        if document.get("publication_candidate"):
            for field in ("affected_gate_refs", "rebuilt_artifact_refs", "authorization_refs"):
                for ref in document["publication_candidate"][field]:
                    if ref["artifact_id"] in artifacts:
                        ref["digest"] = artifacts[ref["artifact_id"]]["digest"]
        if reseal: document["digest"] = seal(document)
        root = Path(self.temporary.name); handoff = root / "handoff.json"
        handoff.write_text(json.dumps(document))
        command = [sys.executable, str(CLI), "--handoff", str(handoff), "--tested-root", str(self.tested), "--remote-root", str(self.remote)]
        artifact_dir = root / ("artifact-dir" if use_dir else "artifact-map-files"); artifact_dir.mkdir(exist_ok=True)
        entries = []
        referenced = set()
        if document.get("publication_candidate"):
            for field in ("affected_gate_refs", "rebuilt_artifact_refs", "authorization_refs"):
                referenced.update(ref["artifact_id"] for ref in document["publication_candidate"][field])
        for key, artifact in artifacts.items():
            if key not in referenced: continue
            path = f"{key}.json"; (artifact_dir / path).write_text(json.dumps(artifact))
            entries.append({"artifact_id": key, "schema_version": artifact["schema_version"], "digest": artifact["digest"], "path": path})
        manifest = {"schema_version": "vllm-cl-publication-artifact-map/v1", "artifact_map_id": "test-map", "candidate_base_sha": document.get("publication_candidate", {}).get("base_sha", self.base_sha) if document.get("publication_candidate") else self.base_sha, "candidate_commit_sha": document.get("publication_candidate", {}).get("commit_sha", self.tested_sha) if document.get("publication_candidate") else self.tested_sha, "entries": entries}
        if artifact_map_mutate: artifact_map_mutate(manifest)
        if reseal_artifact_map: manifest["digest"] = seal(manifest)
        artifact_map = artifact_dir / "artifact-map.json"; artifact_map.write_text(json.dumps(manifest))
        command.extend(("--artifact-dir", str(artifact_dir)) if use_dir else ("--artifact-map", str(artifact_map)))
        if candidate_root: command.extend(("--candidate-root", str(self.candidate)))
        return subprocess.run(command, capture_output=True, text=True, check=False)

    def assert_blocked(self, code, mutate=None, artifact_mutate=None, returncode=20):
        result = self.assess(mutate, artifact_mutate)
        self.assertEqual(result.returncode, returncode, result.stderr + result.stdout)
        report = json.loads(result.stdout); self.assertEqual(report["primary_blocker"]["code"], code)
        self.assertEqual(report["finalize_action"], "none")
        if "repository_before" in report: self.assertEqual(report["repository_before"], report["repository_after"])

    def test_assessment_complete_never_claims_publication_eligibility(self):
        for use_dir in (False, True):
            result = self.assess(use_dir=use_dir); self.assertEqual(result.returncode, 0, result.stdout)
            report = json.loads(result.stdout)
            self.assertEqual(report["status"], "assessment_complete")
            self.assertEqual(report["publication_verification"], "not_verified_for_publication")
            self.assertFalse(report["publication_eligible"])
            self.assertEqual(report["authorization_status"], "human_authorization_required")
            self.assertEqual(report["repository_before"], report["repository_after"])
            self.assertEqual(list(Draft202012Validator(json.loads(ASSESSMENT_SCHEMA.read_text())).iter_errors(report)), [])

    def test_schema_failure_is_fail_fast_before_git_or_artifacts(self):
        result = self.assess(lambda doc: doc.update(surprise=True), candidate_root=False)
        report = json.loads(result.stdout); self.assertEqual(result.returncode, 20); self.assertEqual(report["primary_blocker"]["code"], "handoff.schema_invalid")
        self.assertNotIn("repository_before", report)

        result = self.assess(
            lambda doc: doc["tested_revision"].update(commit_sha="f" * 40),
            candidate_root=False,
            reseal=False,
        )
        report = json.loads(result.stdout)
        self.assertEqual(report["primary_blocker"]["code"], "handoff.digest")
        self.assertNotIn("repository_before", report)

    def test_assessment_schema_is_closed_world(self):
        schema = json.loads(ASSESSMENT_SCHEMA.read_text())
        result = self.assess()
        report = json.loads(result.stdout)
        report["unexpected"] = True
        errors = list(Draft202012Validator(schema).iter_errors(report))
        self.assertTrue(errors)

    def test_artifact_map_digest_schema_identity_and_reference_set_are_closed(self):
        result = self.assess(artifact_map_mutate=lambda doc: doc.update(digest="sha256:" + "0" * 64), reseal_artifact_map=False)
        report = json.loads(result.stdout); self.assertEqual(result.returncode, 30); self.assertIn("artifact map schema or digest is invalid", report["error"])
        result = self.assess(artifact_map_mutate=lambda doc: doc.update(candidate_commit_sha="f" * 40))
        report = json.loads(result.stdout); self.assertEqual(result.returncode, 20); self.assertEqual(report["primary_blocker"]["code"], "artifact_map.identity_mismatch"); self.assertNotIn("repository_before", report)
        result = self.assess(artifact_map_mutate=lambda doc: doc["entries"].pop())
        report = json.loads(result.stdout); self.assertEqual(result.returncode, 20); self.assertEqual(report["primary_blocker"]["code"], "artifact_map.reference_set_mismatch"); self.assertNotIn("repository_before", report)

    def test_dash_path_and_ref_are_schema_rejected_fail_fast(self):
        for mutate in (lambda doc: doc["publication_candidate"].update(included_paths=["-unsafe"]), lambda doc: doc["publication_candidate"]["remote_observation"].update(target_base_ref="-refs/heads/main")):
            result = self.assess(mutate, candidate_root=False); self.assertEqual(json.loads(result.stdout)["primary_blocker"]["code"], "handoff.schema_invalid")
        result = self.assess(lambda doc: doc["publication_candidate"]["remote_observation"].update(target_base_ref="refs/heads/main@{1}"), candidate_root=False)
        report = json.loads(result.stdout); self.assertEqual(report["primary_blocker"]["code"], "handoff.schema_invalid"); self.assertNotIn("repository_before", report)

    def test_tested_dirty_is_recorded_but_candidate_dirty_blocks(self):
        (self.tested / "dirty.txt").write_text("dirty\n")
        result = self.assess(lambda doc: doc["tested_revision"].update(worktree_clean=False)); self.assertEqual(result.returncode, 0, result.stdout)
        (self.candidate / "dirty.txt").write_text("dirty\n"); self.assert_blocked("candidate.dirty", lambda doc: doc["tested_revision"].update(worktree_clean=False))

    def test_artifact_digest_identity_authority_acceptance_and_binding(self):
        cases = (
            ("gate.identity_mismatch", lambda rows: self._reseal(rows, "runtime", candidate_commit_sha="f" * 40)),
            ("gate.authority_missing", lambda rows: self._reseal(rows, "runtime", authority_id="producer-team")),
            ("gate.acceptance_ineligible", lambda rows: self._reseal(rows, "runtime", acceptance_eligible=False)),
            ("gate.artifact_schema", lambda rows: self._reseal(rows, "runtime", surprise=True)),
        )
        for code, mutate in cases:
            with self.subTest(code=code): self.assert_blocked(code, artifact_mutate=mutate)

        result = self.assess(artifact_mutate=lambda rows: rows["runtime"].update(status="failed"))
        report = json.loads(result.stdout)
        self.assertEqual(result.returncode, 30)
        self.assertEqual(report["primary_blocker"]["code"], "assessment.invalid_input")
        self.assertIn("artifact map entry identity, schema, or digest mismatch", report["error"])

    def _reseal(self, rows, key, **updates):
        rows[key].update(updates); rows[key]["digest"] = seal(rows[key])

    def test_candidate_always_requires_rebuilt_artifact_and_fresh_source_build_runtime(self):
        self.assert_blocked("gate.missing_build_rerun", artifact_mutate=lambda rows: self._reseal(rows, "build", kind="contract"))
        self.assert_blocked("gate.missing_source_rerun", artifact_mutate=lambda rows: self._reseal(rows, "source", kind="contract"))
        self.assert_blocked("artifact_map.reference_set_mismatch", lambda doc: doc["publication_candidate"]["rebuilt_artifact_refs"][0].update(artifact_id="missing"))
        result = self.assess(lambda doc: (doc["publication_candidate"].update(artifact_graph_digest=doc["tested_revision"]["artifact_graph_digest"]), doc["publication_candidate"]["affected_gate_refs"].__setitem__(slice(None), [r for r in doc["publication_candidate"]["affected_gate_refs"] if r["artifact_id"] == "source"])))
        self.assertEqual(result.returncode, 20); self.assertEqual(json.loads(result.stdout)["primary_blocker"]["code"], "handoff.schema_invalid")

    def test_future_gate_and_stale_or_future_remote_observation_block(self):
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.assert_blocked("gate.future_completed", artifact_mutate=lambda rows: self._reseal(rows, "runtime", completed_at=future))
        self.assert_blocked("remote.observation_stale", lambda doc: doc["publication_candidate"]["remote_observation"].update(observed_at="2020-01-01T00:00:00Z"))
        self.assert_blocked("remote.future_observation", lambda doc: doc["publication_candidate"]["remote_observation"].update(observed_at=future))

    def test_authorizations_are_structural_observations_only(self):
        result = self.assess(lambda doc: doc["publication_candidate"].update(authorization_refs=[]))
        report = json.loads(result.stdout); self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(report["authorization_status"], "human_authorization_required"); self.assertFalse(report["publication_eligible"])
        result = self.assess(artifact_mutate=lambda rows: self._reseal(rows, "auth-publication", authority_id="producer-team"))
        report = json.loads(result.stdout); self.assertEqual(result.returncode, 0, result.stdout); self.assertEqual(report["authorization_status"], "human_authorization_required")
        self.assert_blocked("authorization.binding_mismatch", artifact_mutate=lambda rows: self._reseal(rows, "auth-publication", candidate_commit_sha="f" * 40))

    def test_stable_patch_id_only_removed_from_schema(self):
        result = self.assess(lambda doc: doc["publication_candidate"]["patch_equivalence"].update(method="stable-patch-id-only"), candidate_root=False)
        self.assertEqual(json.loads(result.stdout)["primary_blocker"]["code"], "handoff.schema_invalid")

    def test_no_proposal_accepts_recorded_dirty_tested_revision(self):
        (self.tested / "dirty.txt").write_text("dirty\n")
        document = json.loads((FIXTURES / "not-proposed.json").read_text()); now = datetime.now(timezone.utc).replace(microsecond=0)
        document.update(generated_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"), expires_at=(now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        document["tested_revision"].update(base_sha=self.base_sha, commit_sha=self.tested_sha, tree_sha=run_git(self.tested, "rev-parse", "HEAD^{tree}")); document["digest"] = seal(document)
        self.handoff, self.artifacts = document, {}
        result = self.assess(candidate_root=False); self.assertEqual(result.returncode, 0, result.stdout); self.assertEqual(json.loads(result.stdout)["status"], "not_proposed")


if __name__ == "__main__": unittest.main()
