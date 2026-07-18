# vLLM-DLC workflow contract v1

Ticket 01 needs a deterministic contract in the skills repository while `/work/vllm-dlc` remains read-only. This ADR fixes the implementation-level decisions left open by the product spec.

## Contract documents

The three document kinds are `run_spec`, `result_evidence`, and `parent_child_handoff`. Their schema versions are respectively `vllm-dlc-run-spec/v1`, `vllm-dlc-result-evidence/v1`, and `vllm-dlc-parent-child-handoff/v1`.

Every object is closed-world: unknown fields fail. Every listed field is required unless its value is explicitly nullable. Identifiers are non-empty strings; source revisions are lowercase 40-character Git SHAs; digests are `sha256:` followed by 64 lowercase hexadecimal characters.

`run_spec` contains:

- `run_id`, `workflow` (`model_adaptation` or `main_to_main`), `mode` (`acceptance` or `diagnostic_only`), and `finalization_intent` (`none` or `eligible_only`).
- `target`: `vllm_sha`, `vllm_dlc_sha`, and `manifest_digest`.
- `deployment_profile`: model, model revision, tokenizer revision, nullable processor revision, TP, PP, dtype, quantization, context limit, batching threshold, Chunked Prefill selection, served model name, and real-weight requirement.
- `hardware`: class (`real_dlc_hardware`, `fake_server`, `dlcsim`, or `none`), positive device count when hardware is required, and required flag.
- Positive startup, request, and long-prefix timeouts.
- `runtime_policy`: eager execution with Triton and compile execution forbidden.
- A non-empty, duplicate-free list of gate identities and an absolute artifact destination outside the read-only vllm-dlc root.

`result_evidence` contains run identity, run-spec digest, execution environment, acceptance eligibility, aggregate status, exit code, gates, artifacts, diagnostics, and its digest. Gate rows contain exactly `id`, `mandatory`, `status`, and `evidence_digest`. Artifact rows contain exactly `id`, `kind`, `uri`, and `digest`. Diagnostic rows contain exactly `code`, `message`, and nullable `artifact_digest`. Simulated, Dummy, DLCsim, and static environments are acceptance-ineligible. Mandatory aggregation is `failed`, then `blocked`, then `not_verified`, then `passed`; `not_applicable` does not participate.

`parent_child_handoff` contains parent and child run identities, target vLLM and candidate vllm-dlc full SHAs, result/evidence digest, a duplicate-free list of changed dependency identities, status, and its digest. Status uses the gate status vocabulary except `not_applicable`; a passed handoff requires at least one changed dependency identity only when compatibility changed, so an empty list is valid.

## Canonicalization

Contract digests use UTF-8 JSON with object keys sorted lexicographically, no insignificant whitespace, JSON booleans/null, and Unicode emitted directly. The top-level `digest` member is omitted before SHA-256. Floating-point values are not admitted by v1 schemas, avoiding number-normalization ambiguity.

## Package and publication contract

A package target declares exactly these roles: `skill`, `agent`, `knowledge`, `top_level_catalog`, `engineering_catalog`, `plugin_manifest`, `skillhub_manifest`, `kilo_linker`, and `installation_documentation`. Roles cannot be renamed or omitted. Live validation maps those roles to repository-fixed paths.

A model-invoked skill has frontmatter with an exact `name` and non-empty `description`, and no true `disable-model-invocation`. It has consecutively numbered ordered steps, each with a `Complete when:` criterion, a `Stop Semantics` section, at least one `conditional_reference: [name](path.md)` marker, and an agent resource with the `interface` mapping and its three required fields: `display_name`, `short_description`, and `default_prompt`.

Ticket 03 adds a candidate-package target for packages under `skills/in-progress/`. A candidate declares exactly `skill`, `agent`, and `knowledge` roles and is validated for package content and shared quality-gate ownership, but is deliberately absent from stable catalogs, plugin manifests, SkillHub, the default Kilo linker, and installation documentation. Moving it to `skills/engineering/` and validating the nine-role publication package remains a separate publication decision.

## Model Adaptation bundle

`vllm-dlc-model-adaptation-bundle/v1` is a closed-world orchestration input to the Ticket 01 CLI, not a fourth sealed evidence document. It binds preflight facts, the exhaustive capability matrix, TP decision evidence, compatibility state, and optional existing `run_spec`, `result_evidence`, and `parent_child_handoff` documents. The three embedded documents retain their existing schemas and canonical digests.

The validator derives a stable dry-run outcome with workflow, phase, status, reason code, runner invocation, acceptance eligibility, handoff emission, resume point, and guarded repository snapshots. Prerequisite blockers stop before runner invocation. `failed_assertion` is different: it consumes a sealed failed Ticket 02 result and therefore reports `runner_invoked: true`. Real DLC Hardware, request-level Chunked Prefill, and DLC Runtime dispatch remain `not_verified` when corresponding sealed evidence was not executed; fake-server, Dummy, DLCsim, and static evidence cannot promote those states.

## Shared quality-gate ownership

Skill and knowledge documents must contain the marker `shared_contract: vllm-dlc-contract/v1`. They may name gate identities, evidence levels, and reasons. They must not contain:

- Shell fenced blocks, or command lines that invoke a runner or HTTP client directly or through an environment/package wrapper.
- Literal OpenAI-compatible endpoint paths.
- Executable HTTP status/JSON/generated-field assertions.
- Numeric Chunked Prefill chunk assertions.
- Executable Triton or compile acceptance assertions.

These structural rules intentionally avoid guessing whether unrestricted prose is semantically equivalent to a quality gate. The shared-contract marker is the positive ownership assertion; prohibited executable structures are the deterministic duplicate detector.

## Repository guard and invalid input

The CLI bootstraps `--vllm-dlc-root` before full argument parsing. If that root resolves to a readable Git worktree, every target, including malformed fixtures and later argument failures, reports before and after snapshots. If the root is absent, malformed, or not a readable Git worktree, exit `10` reports `repository_state: not_verified`; it never claims preservation. Snapshot comparison includes HEAD, branch, porcelain status, staged and unstaged binary diff digests, and untracked-content digest.

The CLI never mutates the guarded repository. A synthetic expected-snapshot mismatch is the negative boundary fixture because deliberately mutating `/work/vllm-dlc` would violate the product boundary.
