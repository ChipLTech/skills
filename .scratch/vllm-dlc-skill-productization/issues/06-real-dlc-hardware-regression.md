# 06 — Run Real DLC Hardware regression

## Approved Operational Amendment (2026-07-17)

This amendment supersedes conflicting acceptance and stop criteria below.
Ticket 06 now produces **Real DLC Hardware operational regression evidence**.
It does not produce authoritative runtime or hardware attestation and does not
establish Verified vLLM Alignment.

- Exactly three independent real-weight runs remain required: one approved
  Model Adaptation profile, DeepSeek-V2-Lite-Chat TP=2, and dense Llama TP=1.
- The one public Smoke Runner remains the sole behavior seam.
- Every run must pass Service Ready, models, completions, chat, non-empty
  generated-field assertions, immediate liveness checks, tokenizer-derived
  long-prefix execution, runner-owned lifecycle cleanup, artifact byte closure,
  and guarded repository preservation.
- Query-only `chipltech_smi_lib` observations may establish sufficient queryable,
  non-excluded physical device count and runner-owned process occupancy for the
  operational hardware gate.
- Normalized device identities must be unique and qualified inventory must contain
  at least the declared required device count. Across all during-request rows, the
  runner PID union must contain at least TP distinct PIDs; occupied row count has
  no minimum. Each row's runner PID list must be a subset of that row's observed
  PID list, while the adapter guarantees process-group and vendor-process match.
  Operational launches require exactly `DLC_VISIBLE_DEVICES` and
  `DLC_SYN_COPY_ASYNC=O2`. The visible-device selector is a canonical unique
  nonnegative ordinal list whose count equals TP; approved profiles constrain TP,
  not physical ordinal identities.
- Production observation uses the official default-version `cltech_smi` behind
  the skills-owned normalization adapter. The adapter must not reimplement the
  vendor tool from raw sysfs values or copy vendor executables into the skills
  repository.
- Qualification requires indexed finite positive HBM capacity, fail-closed
  process/device inspection, run-local device references, an empty original
  runner process group, and no device PID beyond the sealed pre-launch baseline
  after cleanup. Shared-host baseline occupancy cannot contribute to run gates.
- The execution container must be privileged, use the host PID namespace, and
  mount host `pci.ids`, `/dev`, `/sys`, `/run`, `/lib/modules`, and `/var/log`.
  If the DLC base image or host payload does not provide `cltech_smi`, environment
  preparation may clone `git@github.com:ChipLTech/chipltech_smi_lib.git` and
  build/install the default version before freezing its source and executable
  identities.
- Operational evidence does not prove request-correlated Chunked Prefill, DLC
  Runtime dispatch, DLCCL/LYP execution, dense Attention implementation, Triton
  non-execution, or compile/Dynamo non-execution.
- Lease, signature, trusted-time, revocation, runtime-stream binding, atomic
  allocation, and changes to non-skills runtime repositories are not required.
- Fixture, fake-server, Dummy, DLCsim, static, unknown-provider, or manually
  assembled evidence remains completion-ineligible.
- V2 operational results always have `acceptance_eligible: false`; they may have
  `completion_eligible: true` only when every mandatory operational gate passes.
- Alignment remains unchanged, manifest remains report-only, finalization is
  `none`, and Ticket 07 publication remains out of scope.
- Approved models may be internally modified assets with no upstream Git or
  Hugging Face revision. Operational v2 profiles close model, tokenizer, and
  optional processor identity through exact approved local paths and recursive
  byte digests; their revision fields may be null and must not be guessed.

The revised mandatory operational gates replace the former authoritative gates
with `long_prefix_threshold_exercised`, `eager_dlc_configuration_observed`,
`real_dlc_hardware_operational`, and exactly one of
`model_adaptation_profile_operational`, `deepseek_tp2_operational`, or
`llama_tp1_dense_operational`.

**What to build:** Validate the candidate skills against real model weights and Real DLC Hardware using the exact public Smoke Runner seam proven by fake-server tests. Run one approved Model Adaptation deployment profile plus the mandatory DeepSeek TP=2 and Llama TP=1 Main-to-Main regression assignments. This ticket executes and records evidence only; it does not adapt source code, update metadata, or modify vllm-dlc.

**Blocked by:** 02 — Build the fake-server Smoke Runner seam; 03 — Productize the Model Adaptation skill; 04 — Productize the Main-to-Main Upgrade skill; 05 — Migrate stable knowledge and reusable prompts. External blockers: approved real-model assets, sufficient Real DLC Hardware, and required runtime observability must be available.

**Status:** completed-operational-regression

## Operational Completion Record (2026-07-18)

Ticket 06 is complete under the Approved Operational Amendment only. The
selected exactly-three evidence is bound to execution campaign
`sha256:b43a09b83cd7c804a579b2d6a652da7bf871778794a8ea2c106fec0c595502d1`:

- Model Adaptation: `ticket06-qwen-attempt12-20260718`, TP=1.
- Dense Llama: `ticket06-llama-attempt12-20260718`, TP=1.
- DeepSeek-V2-Lite-Chat: `ticket06-deepseek-attempt12-20260718`, TP=2.

All mandatory operational gates passed independently for all three runs. Each
sealed result has `completion_eligible: true`, `acceptance_eligible: false`,
`authoritativeness: operational_only`, and no diagnostics. The public
operational-result, exactly-three Ticket 06, Model Adaptation consumer, and
policy-closed Main-to-Main consumer validators all passed.

Selected evidence:

- Campaign: `/tmp/kilo/vllm-dlc-ticket06-campaign-v12-20260718/campaign.json`.
- Aggregate: `/tmp/kilo/vllm-dlc-ticket06-runs-v12-20260718/ticket06-operational-index.json`.
- Model Adaptation consumer: `/tmp/kilo/vllm-dlc-ticket06-runs-v12-20260718/model-adaptation-operational.json`.
- Main-to-Main consumer: `/tmp/kilo/vllm-dlc-ticket06-runs-v12-20260718/main-to-main-operational.json`.

Alignment remains unchanged, the manifest remains report-only, finalization is
`none`, and Ticket 07 remains not published. This completion does not establish
any of the excluded authoritative conclusions listed in the amendment.

## Inputs

- Approved model IDs, exact local paths, recursive asset digests, and optional independently known model/tokenizer/processor revisions.
- One Model Adaptation deployment profile with TP derived from model weights, configuration, dtype, quantization, capacity, and target deployment.
- DeepSeek-V2-Lite-Chat deployment profile with TP=2.
- Llama dense-model deployment profile with TP=1.
- At least two available Real DLC Hardware devices for the DeepSeek run.
- A fully mounted production container and an official default-version
  `cltech_smi` whose source full SHA and executable digest are recorded.
- Read-only vLLM and vllm-dlc full revisions and worktree-state snapshots.
- Ticket 02's versioned runner, timeout policy, runtime event contract, and artifact destination outside vllm-dlc.

## Public Test Seam

- The sole highest behavior seam is the same versioned run-spec to sealed result/evidence JSON runner used in Ticket 02.
- Skill transcripts prove orchestration only; runner results prove API, lifecycle, Chunked Prefill, runtime path, and hardware behavior.
- No handwritten command sequence or manually interpreted log may replace a required runner gate.

## Acceptance Criteria

The checklist below is retained as historical ticket text. Conflicting items are
superseded by the Approved Operational Amendment and are not completion claims.

- [ ] The Model Adaptation run uses approved real weights and the declared target deployment profile on Real DLC Hardware.
- [ ] DeepSeek uses approved real weights and TP=2, with evidence for the intended DLCCL/LYP distributed path.
- [ ] Llama uses approved real weights and TP=1, covering the standard dense Attention and generation path.
- [ ] Every model independently passes Service Ready, models, completions, chat completions, non-empty target generation fields, and post-request server liveness.
- [ ] Every required Chunked Prefill run has tokenizer/threshold proof and request-correlated runtime evidence of at least two chunks.
- [ ] Runtime dispatch evidence proves eager/DLC execution and no actual Triton JIT/kernel or `torch.compile`/Dynamo execution for required requests.
- [ ] Real DLC Hardware attestation identifies hardware class, device count, runtime identity, and a stable privacy-safe device reference.
- [ ] Each model has a unique run identity and sealed run-spec, result, evidence, and artifact digests.
- [ ] All mandatory gates are `passed`; no required gate is `failed`, `blocked`, or `not_verified`.
- [ ] Dummy, fake-server, DLCsim, or static evidence contributes nothing to this ticket's completion status.
- [ ] All artifacts are written outside vllm-dlc and vllm-dlc remains unchanged.
- [ ] No alignment or manifest finalization is performed or claimed.

## Stop Conditions

- Any required approved model/tokenizer/processor path, recursive digest, or deployment profile is missing or ambiguous.
- Fewer than two Real DLC Hardware devices are available for DeepSeek TP=2.
- Request-level chunk observation or backend/dispatch observation is unavailable.
- The public runner cannot express or evaluate a mandatory gate.
- Any mandatory gate returns failed, blocked, or not verified.
- Continuing would require downloading an unapproved substitute or modifying vllm-dlc.
- The tested source revision cannot be uniquely identified.
- Artifact isolation outside vllm-dlc cannot be guaranteed.

## Evidence Requirements

- Independent run spec, result, evidence, and artifact digest for the Model Adaptation profile, DeepSeek TP=2, and Llama TP=1.
- Model, tokenizer, processor applicability, exact paths, recursive digests, optional known revisions, dtype, quantization, TP, context, and capacity identity for every run.
- Real DLC Hardware attestation for every required run.
- API status, JSON assertion, generated-field, and liveness summaries.
- Request-correlated Chunked Prefill and runtime dispatch event summaries.
- Server logs and timeout/process-state artifacts where applicable.
- Explicit overall status with no Dummy or fake evidence counted.
- Before/after vllm-dlc full revision and worktree-state comparison showing zero ticket-created changes.
