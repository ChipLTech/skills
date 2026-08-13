# Engineering

Skills I use daily for code work.

## User-invoked

Reachable only when you type them (`disable-model-invocation: true`).

- **[ask-matt](./ask-matt/SKILL.md)** — Ask which skill or flow fits your situation. A router over the user-invoked skills in this repo.
- **[grill-with-docs](./grill-with-docs/SKILL.md)** — Grilling session that challenges your plan against the existing domain model, sharpens terminology, and updates `CONTEXT.md` and ADRs inline.
- **[triage](./triage/SKILL.md)** — Triage issues through a state machine of triage roles.
- **[improve-codebase-architecture](./improve-codebase-architecture/SKILL.md)** — Find deepening opportunities in a codebase, informed by the domain language in `CONTEXT.md` and the decisions in `docs/adr/`.
- **[setup-matt-pocock-skills](./setup-matt-pocock-skills/SKILL.md)** — Scaffold the per-repo config (issue tracker, triage label vocabulary, domain doc layout) that the other engineering skills consume.
- **[to-spec](./to-spec/SKILL.md)** — Turn the current conversation into a spec and publish it to the issue tracker.
- **[to-tickets](./to-tickets/SKILL.md)** — Break any plan, spec, or conversation into tracer-bullet tickets, each declaring its blocking edges.
- **[implement](./implement/SKILL.md)** — Build the work described by a spec or set of tickets, driving `/tdd` at pre-agreed seams and closing out with `/code-review` before committing.
- **[wayfinder](./wayfinder/SKILL.md)** — Plan work too large for one agent session as a shared map of decision tickets on the issue tracker.
- **[zoom-out](./zoom-out/SKILL.md)** — Tell the agent to zoom out and give broader context or a higher-level perspective on an unfamiliar section of code.

## Model-invoked

Model- or user-reachable (rich trigger phrasing so the model can reach for them).

- **[chipltech-context](./chipltech-context/SKILL.md)** — Route Chipltech tasks with cited engineering knowledge.
- **[codebase-design](./codebase-design/SKILL.md)** — Shared vocabulary for deep modules, interfaces, seams, leverage, locality, and testability.
- **[domain-modeling](./domain-modeling/SKILL.md)** — Build and sharpen the active project's domain language, `CONTEXT.md`, and ADRs.
- **[prototype](./prototype/SKILL.md)** — Build a shareable single-file logic demo or several radically different UI variations to answer one design question.
- **[diagnosing-bugs](./diagnosing-bugs/SKILL.md)** — Disciplined diagnosis loop for hard bugs and performance regressions: reproduce → minimise → hypothesise → instrument → fix → regression-test.
- **[technical-delivery-summary](./technical-delivery-summary/SKILL.md)** — Distill completed technical work into an audience-ready one-sentence delivery summary. Use for cross-team updates, review updates, daily reports, release summaries, or multi-repository implementations when the reader needs the delivered capability rather than implementation detail.
- **[technical-issue-summary](./technical-issue-summary/SKILL.md)** — Compress a closed technical diagnosis into a one- or two-sentence Sprint update, Issue title or summary, owner note, or evidence-linked handoff conclusion. Use when the user asks to summarize, briefly introduce, or explain a diagnosed technical issue across teams.
- **[research](./research/SKILL.md)** — Investigate a question against high-trust primary sources and capture the findings as a cited Markdown file in the repo, run as a background agent.
- **[tdd](./tdd/SKILL.md)** — Test-driven development through pre-agreed public seams, one red-green vertical slice at a time.
- **[code-review](./code-review/SKILL.md)** — Review a diff since a fixed point along Standards and Spec axes in parallel sub-agents.
- **[resolving-merge-conflicts](./resolving-merge-conflicts/SKILL.md)** — Resolve an in-progress merge or rebase hunk by hunk from each side's intent, then finish the operation.
- **[wizard](./wizard/SKILL.md)** — Generate an interactive bash wizard for setup, credentials, dashboards, migrations, and cutovers only a human can perform.
- **[dlc-env-setup](./dlc-env-setup/SKILL.md)** — Rebuild and verify a workstation DLC toolchain, PyTorch 2.5.0 wheel, and optional local vLLM runtime.
- **[dlc-hardware-observability](./dlc-hardware-observability/SKILL.md)** — Observe Real DLC Hardware with the official cltech_smi and normalized query-only evidence; use when model serving, image qualification, PD, environment repair, or debugging needs device, HBM, process, link, or cleanup snapshots without performing maintenance.
- **[model-adaptation](./model-adaptation/SKILL.md)** — Adapt a specific new or incompatible model for loading or serving on the DLC Platform; use for model-level Attention, MLA, MoE, quantization, multimodal, MTP, or distributed compatibility, not upstream alignment, environment rebuilds, single-operator debugging, independent compile work, or running an existing smoke alone.
- **[modelzoo-image-validation](./modelzoo-image-validation/SKILL.md)** — Qualify a local model from an ordinary daily base, use ModelZoo as optional read-only reference, then build independent DLC Chip and TYD Chip deliverables only after functional and benchmark gates pass. Use for ModelZoo-to-image workflows, local-model runtime qualification, or DLC/TYD image export.
- **[pd-separation](./pd-separation/SKILL.md)** — Deploy or diagnose vLLM-DLC Prefill/Decode separation with MooncakeDLCConnector; use for single-node TCP, qualified lyp_full or dlccl_direct, cross-machine TCP, transport qualification, KV-transfer lifecycle, routing, and recovery.
- **[pytorch-dlc-plugin-migration](./pytorch-dlc-plugin-migration/SKILL.md)** — Migrate an existing production PyTorch DLC Backend component into a standard PrivateUse1 loadable plugin while preserving operator semantics and DLC kernel ABIs; use for component migration, phase audits, compile/link/wheel closure, and deferred-test accounting, not for inventing new DLC Custom Kernel semantics.
- **[main-to-main-upgrade](./main-to-main-upgrade/SKILL.md)** — Upgrade vllm-dlc main toward an exact upstream vLLM full SHA, recover an unknown Verified vLLM Alignment candidate, or perform complete compatibility-impact analysis; do not use for standalone model adaptation, environment rebuild, single-operator diagnosis, independent compile work, release branch management, or smoke-only requests.
