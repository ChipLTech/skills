# 07 — Publish the skills to Kilo

**What to build:** Publish the two Real DLC Hardware-validated skills through every supported skills and Kilo discovery surface. A clean Kilo configuration must expose both model-invoked skills and their slash-command wrappers, route natural-language triggers correctly, preserve anti-trigger boundaries, and avoid overwriting user configuration. Publication metadata must describe capability and trigger boundaries, not duplicate hardware evidence or runner rules.

**Blocked by:** 01 — Build the static workflow contract tool; 03 — Productize the Model Adaptation skill; 04 — Productize the Main-to-Main Upgrade skill; 05 — Migrate stable knowledge and reusable prompts; 06 — Run Real DLC Hardware regression.

**Status:** completed

## Completion Record (2026-07-18)

Ticket 07 stable Kilo publication is complete. Evidence root:

`/tmp/kilo/vllm-dlc-ticket07-recovery-20260718T122139Z/evidence`

Summary:

- `model-adaptation` and `main-to-main-upgrade` exist only as stable packages under
  `/work/skills/skills/engineering/`; no duplicate in-progress identity remains.
- Both skills are model-invoked and slash-command reachable through generated
  frontmatter-derived Kilo wrappers.
- The six publication surfaces agree structurally: `/work/skills/README.md`,
  `/work/skills/skills/engineering/README.md`, `.claude-plugin/plugin.json`,
  `SKILLHUB.yaml`, `scripts/link-kilo-skills.sh`, and `kilo-code-installation-and-validation.md`.
- The default Kilo linker installs both skills and command wrappers without
  `--all`; isolated reruns are idempotent and preserve user-owned directories,
  files, symlinks, commands, and unrelated config.
- Isolated Kilo discovery proved both stable skills and the neighboring
  `dlc-env-setup` and `diagnosing-bugs` skills are each discoverable exactly once
  from the project installation seam. The negative control with
  `KILO_DISABLE_PROJECT_CONFIG=1` removed project-installed skills and commands.
- Fresh Kilo provider preflight passed with `openai/gpt-5.6-terra` against the
  user-provided OpenAI-compatible endpoint. Credential values were not written to
  evidence.
- Fresh Kilo JSON event-stream routing passed for the required natural-language,
  slash-command, neighboring anti-trigger, independent compile, and
  release/smoke-only cases. Expected skill tool events, argument forwarding, and
  absence of mutation/execution tools are recorded under `routing/`.
- The final deterministic suite, `py_compile`, scoped structured parsing,
  `git diff --check`, two sealed live-package reports, two structural publication
  reports, and publication surface inventory passed.
- The Ticket 06 canonical six-check chain still passes under the unchanged sealed
  validator digest
  `sha256:704a9260ac5e21bbe2b9895338addff87c3de951ea55893d08e01fc5a6631c24`.
- `/work/vllm` and `/work/vllm-dlc` before/after closed inventories are equal.
- Standards and Spec review have no unresolved Critical or High findings.

Claim boundary:

- Ticket 06 evidence remains operational-only for the exact v12 profiles:
  `authoritativeness: operational_only`, `acceptance_eligible: false`, alignment
  unchanged, manifest report-only, and finalization `none`.
- This publication does not claim Real DLC Hardware acceptance, authoritative
  attestation, Verified vLLM Alignment, device health/provenance/stable hardware
  identity, request-correlated Chunked Prefill, DLC Runtime dispatch, DLCCL/LYP
  execution, a specific Attention implementation, Triton non-execution,
  compile/Dynamo non-execution, or rank-to-device allocation.
- Ticket 07 validation did not start model-serving workloads, compile workloads,
  Real DLC Hardware workloads, commits, pushes, or runtime repository
  modifications.

## Inputs

- Final Model Adaptation and Main-to-Main Upgrade skill packages.
- Final knowledge-base entry points and prompt references.
- Ticket 06 Real DLC Hardware evidence showing all mandatory gates passed.
- Ticket 01 publication checker.
- Skills catalogs, plugin manifest, SkillHub manifest, Kilo linker, command-wrapper generator, and installation documentation.
- Isolated temporary Kilo configuration root and fresh-session validation mechanism.

## Public Test Seam

- Ticket 01's publication CLI verifies package and catalog consistency.
- The normal Kilo linker installs into an isolated temporary configuration root.
- Fresh Kilo sessions or equivalent independently loaded contexts exercise natural-language and slash-command invocation.
- Tests inspect public symlink, command, catalog, and invocation behavior rather than linker internals.

## Acceptance Criteria

- [ ] Both skills appear consistently in the top-level catalog, engineering catalog, SkillHub manifest, plugin manifest, Kilo stable linking set, and installation documentation.
- [ ] Package names, paths, descriptions, and agent quick prompts agree across every publication surface.
- [ ] Both skills are installed by the default stable linker path without requiring an all-skills override.
- [ ] Slash-command wrappers are generated from canonical frontmatter or otherwise proven not to maintain duplicate descriptions.
- [ ] A fresh session routes a specific model adaptation request to Model Adaptation.
- [ ] A fresh session routes an upstream alignment request to Main-to-Main Upgrade.
- [ ] Anti-trigger cases do not confuse either skill with DLC environment setup, single-operator debugging, or independent compile work.
- [ ] Temporary installation preserves existing real directories, custom commands, and unrelated user configuration.
- [ ] Publication does not embed or claim more hardware coverage than Ticket 06 proves.
- [ ] Ticket 01's final publication report is fully passing.
- [ ] No vllm-dlc file, metadata, branch, or worktree state is changed.

## Stop Conditions

- Ticket 06 is failed, blocked, not verified, or lacks sealed evidence for any mandatory model.
- Any publication surface is missing, stale, or disagrees with canonical skill frontmatter.
- Installation can only be tested by overwriting a user's real Kilo configuration or directory.
- A fresh-session load cannot be obtained and the active session may be using cached skill metadata.
- Correct publication would require editing vllm-dlc.
- Existing unrelated changes in the skills or knowledge-base repositories cannot be preserved safely.

## Evidence Requirements

- Fully passing Ticket 01 publication JSON.
- Catalog and manifest inventory showing both skills on every required surface.
- Isolated Kilo installation inventory with symlink and wrapper targets.
- Frontmatter-to-wrapper description comparison.
- Fresh-session transcript for both natural-language triggers.
- Fresh-session transcript for both slash-command invocations.
- Anti-trigger routing transcript.
- Preservation proof for existing Kilo directories and custom commands.
- Before/after vllm-dlc revision and status showing zero ticket-created changes.
