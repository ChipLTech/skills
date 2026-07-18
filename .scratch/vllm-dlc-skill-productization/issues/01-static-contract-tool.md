# 01 — Build the static workflow contract tool

**What to build:** Provide a deterministic, read-only CLI in the skills repository that validates the shared vLLM-DLC skill contracts before any skill text, fake-server scenario, hardware run, or publication can be accepted. The tool must validate versioned run-spec, result/evidence, and parent-child handoff fixtures; inspect skill packaging and knowledge pointers; detect duplicated quality gates; and prove that the vllm-dlc repository was not modified. It must not implement model serving, compatibility analysis, or vllm-dlc business behavior.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

## Inputs

- The approved vLLM-DLC skill productization spec and decision record.
- Skills repository root.
- Chipltech knowledge-base repository root.
- Read-only vllm-dlc repository root.
- Versioned positive and negative contract fixtures.
- Expected skill identities and required publication surfaces.

## Public Test Seam

- A single CLI accepts repository roots and a fixture or live-package validation target.
- The CLI emits stable machine-readable JSON on stdout and diagnostics on stderr.
- Exit code `0` means every requested check passed; non-zero codes distinguish invalid input, contract failure, publication inconsistency, duplicated quality gates, and read-only boundary violation.
- Tests invoke only this CLI and assert its exit code and JSON output, not internal helper calls.

## Acceptance Criteria

- [ ] Valid run-spec, result/evidence, and handoff fixtures pass under an explicitly versioned contract.
- [ ] Unknown required fields, unsupported schema versions, invalid statuses, missing full identities, and inconsistent digests fail deterministically.
- [ ] The report uses stable ordering and produces equivalent JSON for repeated identical input.
- [ ] Skill validation checks frontmatter identity, model-invoked configuration, ordered steps, checkable completion criteria, stop semantics, conditional knowledge pointers, and required agent resources.
- [ ] Publication validation checks every catalog and Kilo exposure surface without publishing anything.
- [ ] Knowledge validation detects copied runner commands, duplicated HTTP assertions, or a second quality gate where the skill should point to the shared contract.
- [ ] Repository guards snapshot the read-only vllm-dlc revision and worktree state before and after validation and fail if this ticket caused any change.
- [ ] Positive fixtures and a minimal negative fixture for every stable failure category are included.
- [ ] The tool and tests modify only the skills or knowledge-base repositories.

## Stop Conditions

- The contract cannot be defined from the approved spec without a new product decision.
- Implementing a check would require editing or generating files in the vllm-dlc repository.
- The tool starts reproducing model loading, HTTP serving, Chunked Prefill, Triton/compile dispatch, alignment finalization, or other vllm-dlc business logic.
- Existing user changes in either writable repository cannot be preserved safely.
- A read-only vllm-dlc snapshot cannot be obtained; report the exact blocker instead of weakening the guard.

## Evidence Requirements

- CLI test summary and exact test invocation.
- One passing JSON report.
- One representative contract failure report.
- One representative publication inconsistency report.
- One representative read-only boundary failure fixture.
- Before/after vllm-dlc revision and worktree-state evidence showing no ticket-created change.
- Final list of files changed in the skills and knowledge-base repositories only.
