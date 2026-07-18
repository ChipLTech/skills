# 03 — Productize the Model Adaptation skill

**What to build:** Publish an independent model-invoked Model Adaptation skill in the skills repository. It must analyze a model and its configuration through read-only inputs, build an exhaustive capability matrix, identify the smallest compatibility action, orchestrate the shared runner, keep Dummy diagnostics separate from real-weight acceptance, and produce a sealed handoff without claiming or updating global alignment.

**Blocked by:** 01 — Build the static workflow contract tool; 02 — Build the fake-server Smoke Runner seam.

**Status:** ready-for-agent

## Inputs

- Approved model identity, revision, weights, tokenizer, and processor when applicable.
- Model configuration, weight index, and architecture metadata.
- Deployment profile including TP, dtype, quantization, capacity, Chunked Prefill, and served model identity.
- Read-only vLLM and vllm-dlc repository identities and worktree states.
- Ticket 01's contracts and Ticket 02's public runner seam.
- Real DLC Hardware requirements and artifact destination.
- Optional parent handoff identity from Main-to-Main Upgrade.

## Public Test Seam

- Ticket 01 validates the skill package, trigger description, ordered steps, completion criteria, stop semantics, context pointers, and handoff fixtures.
- Ticket 02's runner is the only behavior seam for API and lifecycle evidence.
- Read-only dry runs exercise the skill through user-style prompts and inspect its structured final status; they do not execute model code or edit vllm-dlc.

## Acceptance Criteria

- [ ] The model-facing description triggers for a specific new or incompatible model and does not trigger for global upstream alignment work.
- [ ] Preflight requires one unambiguous model identity, deployment profile, repository identity, contract version, hardware requirement, and artifact identity.
- [ ] The capability matrix covers text generation, Attention, MLA, MoE, quantization, multimodal, distributed, MTP, tokenizer, processor, and model-specific paths as required, conditional, or evidence-backed not applicable.
- [ ] Every ordered step ends in a checkable, exhaustive completion criterion.
- [ ] Stable stop states distinguish missing asset, missing hardware, branch mismatch, missing contract, missing observability, unsupported path, failed assertion, and read-only boundary violation.
- [ ] TP for non-fixed models is derived from weights, model configuration, dtype, quantization, capacity, and target deployment profile rather than copied from DeepSeek or Llama defaults.
- [ ] The skill points to shared contracts and knowledge references instead of copying runner commands or maintaining HTTP assertions.
- [ ] Dummy is available only as an explicit diagnostic branch after a real-weight failure; its outcome is `diagnostic_only` and cannot satisfy real-weight or hardware acceptance.
- [ ] The real-weight handoff requires explicit `passed`, `failed`, `blocked`, `not_applicable`, or `not_verified` gate states and sealed evidence references.
- [ ] The skill explicitly does not own Verified vLLM Alignment recovery or update.
- [ ] An agent quick prompt and trigger/anti-trigger examples agree with the skill frontmatter.
- [ ] Ticket 01 and all dry-run fixtures pass without modifying vllm-dlc.

## Stop Conditions

- Required model identity, configuration, tokenizer, processor, deployment profile, or contract is missing or ambiguous.
- The skill would need to edit vllm-dlc to complete this ticket.
- The workflow starts merging with Main-to-Main Upgrade into one oversized skill.
- Dummy, fake-server, DLCsim, or static evidence is about to be presented as real-weight or Real DLC Hardware acceptance.
- Existing user changes in the skills or knowledge-base repository conflict with the intended package.

## Evidence Requirements

- Ticket 01 static validation report.
- Trigger and anti-trigger matrix.
- Missing-asset dry-run transcript ending in `blocked_missing_asset` before runner invocation.
- Dummy diagnostic dry-run transcript explicitly remaining acceptance-ineligible.
- Contract-available dry run showing ordered steps and sealed handoff shape without claiming real-weight success.
- Audit showing no runner command or duplicate quality gate in the skill text.
- Before/after vllm-dlc revision and status showing zero ticket-created changes.
