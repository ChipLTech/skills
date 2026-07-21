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

- **[prototype](./prototype/SKILL.md)** — Build a throwaway prototype to flesh out a design — either a runnable terminal app for state/business-logic questions, or several radically different UI variations toggleable from one route.
- **[diagnosing-bugs](./diagnosing-bugs/SKILL.md)** — Disciplined diagnosis loop for hard bugs and performance regressions: reproduce → minimise → hypothesise → instrument → fix → regression-test.
- **[research](./research/SKILL.md)** — Investigate a question against high-trust primary sources and capture the findings as a cited Markdown file in the repo, run as a background agent.
- **[tdd](./tdd/SKILL.md)** — Test-driven development with a red-green-refactor loop. Builds features or fixes bugs one vertical slice at a time.
- **[code-review](./code-review/SKILL.md)** — Review a diff since a fixed point along Standards and Spec axes in parallel sub-agents.
- **[resolving-merge-conflicts](./resolving-merge-conflicts/SKILL.md)** — Resolve an in-progress merge or rebase hunk by hunk from each side's intent, then finish the operation.
- **[dlc-env-setup](./dlc-env-setup/SKILL.md)** — Rebuild and verify a workstation DLC toolchain, PyTorch 2.5.0 wheel, and optional local vLLM runtime.
- **[model-adaptation](./model-adaptation/SKILL.md)** — Adapt a specific new or incompatible model for loading or serving on the DLC Platform; use for model-level Attention, MLA, MoE, quantization, multimodal, MTP, or distributed compatibility, not upstream alignment, environment rebuilds, single-operator debugging, independent compile work, or running an existing smoke alone.
- **[modelzoo-image-validation](./modelzoo-image-validation/SKILL.md)** — Resolve a named ModelZoo entry into an auditable read-only manifest and drive guarded DLC Chip and TYD Chip image workflows. Use when a model name must select ModelZoo evidence, detect framework ambiguity, or prepare generation-correct image build and validation contracts without guessing assets, refs, hardware, or authorization.
- **[main-to-main-upgrade](./main-to-main-upgrade/SKILL.md)** — Upgrade vllm-dlc main toward an exact upstream vLLM full SHA, recover an unknown Verified vLLM Alignment candidate, or perform complete compatibility-impact analysis; do not use for standalone model adaptation, environment rebuild, single-operator diagnosis, independent compile work, release branch management, or smoke-only requests.
