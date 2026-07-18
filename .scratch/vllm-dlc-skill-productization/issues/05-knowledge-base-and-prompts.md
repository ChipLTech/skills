# 05 — Migrate stable knowledge and reusable prompts

**What to build:** Complete the knowledge-base side of vLLM-DLC skill productization. Reconcile the decision record with the approved two-repository modification scope, document stable terminology and evidence levels, add one reusable prompt for each skill, and expose the material from the knowledge-base entry points. The knowledge base must explain why and when; it must not copy runner commands or become a second execution contract.

**Blocked by:** 02 — Build the fake-server Smoke Runner seam; 03 — Productize the Model Adaptation skill; 04 — Productize the Main-to-Main Upgrade skill.

**Status:** ready-for-agent

## Inputs

- Final trigger, input, status, stop-state, and handoff vocabulary from Tickets 03 and 04.
- Shared runner and fake-server evidence boundary from Ticket 02.
- Existing DLC Ecosystem glossary, vLLM-DLC decision record, README, and prompt examples.
- Existing user modifications in the knowledge-base worktree.
- The approved rule that this ticket may modify only the skills and knowledge-base repositories.

## Public Test Seam

- Ticket 01's documentation and duplicate-quality-gate checks.
- Link validation from knowledge-base entry points to the decision record and both prompt examples.
- Two read-only prompt dry runs: each prompt must select the intended skill, identify missing inputs, use canonical status vocabulary, and point to the shared seam without inventing commands.

## Acceptance Criteria

- [ ] The knowledge base states that current productization implementation lives only in the skills and knowledge-base repositories and treats vllm-dlc as read-only.
- [ ] The formal DLC terminology remains centralized in the glossary; implementation steps and mutable interface details are not added to the glossary.
- [ ] Stable rules distinguish static validation, fake-server validation, Dummy diagnostics, DLCsim evidence, real-weight evidence, and Real DLC Hardware acceptance.
- [ ] Hardware-dependent work that did not run on Real DLC Hardware is always reported as “未验证” or `not_verified`.
- [ ] The Model Adaptation prompt declares model identity, deployment profile, required inputs, stop conditions, and evidence expectations without copying runner commands.
- [ ] The Main-to-Main Upgrade prompt declares target identity, read-only baseline/impact analysis, child handoff, mandatory regressions, and no-finalize conditions without copying commands.
- [ ] Both prompts preserve the separation between Dummy diagnostics and real-weight acceptance.
- [ ] Facts, experience, recommendations, and unverified assumptions are explicitly distinguishable.
- [ ] README or equivalent knowledge entry points make the decision record and both prompts discoverable.
- [ ] Ticket 01 reports no duplicated quality gate and all links resolve.
- [ ] Existing user content and unrelated untracked documents are preserved.

## Stop Conditions

- Tickets 03 or 04 still use unstable trigger, status, or handoff vocabulary.
- A prompt would need to copy a mutable runner command to be usable.
- Current knowledge-base changes conflict directly and cannot be merged without overwriting user work.
- The document is about to state that Real DLC Hardware, real weights, Chunked Prefill, Triton absence, or compile absence passed without corresponding evidence.
- Completing the ticket would require a vllm-dlc edit.

## Evidence Requirements

- Ticket 01 documentation validation report.
- Link-check report.
- Model Adaptation prompt dry-run transcript.
- Main-to-Main Upgrade prompt dry-run transcript.
- Terminology and evidence-level audit summary.
- Duplicate-quality-gate audit showing prompts and docs do not reproduce the runner contract.
- Before/after knowledge-base status demonstrating preservation of pre-existing user changes.
- Before/after vllm-dlc revision and status showing zero ticket-created changes.
