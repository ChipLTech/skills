# 04 — Productize the Main-to-Main Upgrade skill

**What to build:** Publish an independent model-invoked Main-to-Main Upgrade skill in the skills repository. It must read baseline, Git history, alignment, and manifest information without changing vllm-dlc; classify every upstream change; delegate model-specific work one-way to Model Adaptation; define mandatory DeepSeek TP=2 and Llama TP=1 assignments; and stop without claiming metadata finalization whenever evidence is incomplete.

**Blocked by:** 01 — Build the static workflow contract tool; 02 — Build the fake-server Smoke Runner seam; 03 — Productize the Model Adaptation skill.

**Status:** ready-for-agent

## Inputs

- Target upstream vLLM full SHA and optional lineage tag.
- Read-only vLLM and vllm-dlc Git history, current branch, revisions, and worktree state.
- Read-only current alignment and compatibility manifest.
- Historical alignment candidates and their evidence references.
- Regression profiles for DeepSeek TP=2, Llama TP=1, and any other mandatory model.
- Ticket 01 contracts, Ticket 02 runner seam, and Ticket 03 parent-child handoff.
- Approved model assets, hardware allocation, and artifact destination when runtime validation is requested.

## Public Test Seam

- Ticket 01 validates the skill package and all baseline, delta, manifest, assignment, child-handoff, aggregate, and no-finalize fixtures.
- Ticket 02's runner is the only API/lifecycle evidence seam.
- Ticket 03's sealed handoff is the only model-specific child feedback contract.
- Dry runs use read-only repositories and structured fixtures; they never edit alignment or manifest.

## Acceptance Criteria

- [ ] The trigger is specific to upstream target alignment, baseline recovery, or compatibility-impact analysis and does not absorb standalone model adaptation.
- [ ] Target identity is always a full upstream SHA; stable, RC, and nearest ancestor tags are lineage only.
- [ ] Preflight stops on branch mismatch, missing target, incomplete history, missing contracts, missing assets, missing devices, or missing observability.
- [ ] Baseline recovery follows the approved evidence-confidence order and never treats checkout, installation metadata, or README text as Verified vLLM Alignment.
- [ ] Every changed upstream surface is classified as an affected dependency, new dependency candidate, or confirmed irrelevant; the workflow cannot proceed with an unknown impact count above zero.
- [ ] Manifest impact analysis remains read-only in this productization scope and reports required future changes without editing vllm-dlc metadata.
- [ ] Delegation is one-way to Model Adaptation and validates parent run, target SHA, candidate identity, model identity, and evidence digest on return.
- [ ] DeepSeek real-weight TP=2 and Llama real-weight TP=1 are mandatory assignments; TP=1 DeepSeek remains diagnostic-only.
- [ ] Any mandatory child `failed`, `blocked`, or `not_verified` prevents completion and any claim that alignment was finalized.
- [ ] The skill describes finalize eligibility and stop semantics but never edits alignment, manifest, or other vllm-dlc files.
- [ ] A non-unique tested revision or missing commit authorization stops before any finalization claim.
- [ ] Every ordered step has an exhaustive completion criterion and stable resume point.
- [ ] Ticket 01 and all dry-run fixtures pass without changing vllm-dlc.

## Stop Conditions

- Target or baseline identity cannot be established from complete read-only history.
- Any changed upstream surface remains unresolved.
- Child handoff identity or digest does not match the parent assignment.
- A mandatory model result is failed, blocked, not verified, Dummy-only, or fake-server-only.
- Continuing requires modifying alignment, manifest, source, tests, or generated metadata in vllm-dlc.
- Existing user changes cannot be preserved safely.

## Evidence Requirements

- Ticket 01 static validation report.
- Trigger and anti-trigger matrix.
- Unknown-baseline fixture ending in `blocked_missing_verified_alignment`.
- Incomplete-history or unresolved-impact fixture ending before adaptation claims.
- Child identity-mismatch fixture proving evidence rejection.
- Mandatory child `not_verified` fixture proving no finalization claim.
- Read-only report showing which vllm-dlc changes a future implementation would require, clearly separated from changes made in this ticket.
- Before/after vllm-dlc revision and status showing zero ticket-created changes.
