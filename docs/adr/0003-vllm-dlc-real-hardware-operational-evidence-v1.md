# vLLM-DLC Real Hardware Operational Evidence

## Status

Approved for Ticket 06 operational regression on 2026-07-17.

## Context

The existing v1 runner cannot evaluate authoritative runtime and hardware gates.
The available runtime repositories do not expose all request-correlated,
rank-complete events required by the original Ticket 06 plan, and those
repositories are read-only for this work. The approved product boundary permits
implementation only in the skills repository and stable decision wording in the
knowledge base.

## Decision

Ticket 06 produces operational evidence, not Real DLC Hardware acceptance.
`vllm-dlc-run-spec/v1` remains unchanged. Closed-world
`vllm-dlc-run-spec/v2` and `vllm-dlc-result-evidence/v2` are introduced for the
operational workflow.

V2 results have `authoritativeness: operational_only` and always set
`acceptance_eligible: false`. `completion_eligible` is derived by the public
runner and may be true only when the run uses real weights and local-process
providers, every mandatory operational gate passes, artifacts close, cleanup
passes, and guarded repositories are unchanged.

SHA-256 digests establish deterministic byte identity and graph consistency.
They are not signatures and do not establish provenance, trusted freshness, or
security against a malicious same-user process.

Approved model assets may be internally modified and need not correspond to an
upstream Git or Hugging Face commit. In run-spec v2, model, tokenizer, and
processor revision fields are nullable. Exact approved local paths and recursive
streaming asset digests are mandatory and define the execution asset identity.
An independently known revision may be retained, but no revision is inferred
from names, timestamps, documentation, or content digests. Guarded source
repository identities remain full Git SHAs.

## Operational gates

The shared mandatory gates are `service_ready`, `models_api`,
`completions_api`, `chat_api`, `long_prefix_api`, `server_liveness`,
`long_prefix_threshold_exercised`, `eager_dlc_configuration_observed`,
`real_dlc_hardware_operational`, `lifecycle_cleanup`, `repository_state`, and `artifact_closure`.
Exactly one role gate is mandatory:
`model_adaptation_profile_operational`, `deepseek_tp2_operational`, or
`llama_tp1_dense_operational`.

`long_prefix_threshold_exercised` proves only that an approved tokenizer-derived
prompt exceeded the batching threshold, fit within context, and completed.
`eager_dlc_configuration_observed` proves only sealed launch configuration.
Hardware and role gates require unique normalized device identities, at least the
declared required count of allowlisted SMI queryable/not-excluded devices, and a
nonempty union of runner-owned PIDs across all device rows containing at least TP
distinct PIDs. They do not require the number of occupied device rows to equal or
exceed the required device count. Each row's runner-owned PID list must be a
subset of that row's observed PID list; the adapter guarantees process-group and
vendor-process matching. Operational launch environments contain exactly
`DLC_VISIBLE_DEVICES` and `DLC_SYN_COPY_ASYNC=O2`. The visible-device selector is
a canonical unique nonnegative ordinal list whose count equals TP; approved
profiles constrain TP, not physical ordinal identities. Device-node PID sets may overlap because stable
control-node handles are global; they do not prove rank-to-device mapping or
device allocation. None proves internal runtime dispatch.

## Provider boundary

Fixture providers use `diagnostic_only` mode and are always completion-ineligible.
Operational completion permits only allowlisted local-process launcher and SMI
adapter provider classes. This is an accidental-promotion boundary, not
cryptographic authentication.

The SMI adapter persists only allowlisted normalized fields. Raw serials, PCI
addresses, hostnames, IP addresses, unrestricted command lines, environment
dumps, and secrets are rejected. Device references are run-local digests and are
not stable hardware identities.
Each row contains a run-local device digest, queryable/not-excluded state,
indexed finite positive HBM capacity, and runner-process-group PIDs observed on
the corresponding device node. Device/process inspection failures fail closed.
Cleanup additionally requires the complete original runner process group to be
empty, post-cleanup SMI observations to contain no runner-process-group PID, and
no observed PID beyond the sealed pre-launch baseline.
Shared-host occupancy is retained for diagnostics but cannot contribute to or
fail runner-owned occupancy gates because unrelated host churn is not lifecycle
evidence for this run.

For production, the adapter invokes the official default-version `cltech_smi`;
it does not reproduce the vendor implementation by interpreting raw sysfs values.
The production container is privileged, uses the host PID namespace, and mounts
host `pci.ids`, `/dev`, `/sys`, `/run`, `/lib/modules`, and `/var/log`, matching
the vendor README and internal server setup. The current development container
may lack some mounts and therefore cannot qualify the full provider surface.

The DLC base image or host payload may supply the tool. If it does not,
environment setup may clone `git@github.com:ChipLTech/chipltech_smi_lib.git` and
build/install the default version. The frozen campaign records the vendor source
full SHA and executable digest, verifies the official Git origin and clean source
checkout, and binds executable bytes to the checkout's default build artifact.
It neither vendors the executable into
`/work/skills` nor modifies the vendor repository. Ticket 06 invokes only
allowlisted query operations; reset, installation, debug upload, LYP, loopcheck,
DLCCL checks, and other maintenance actions remain outside the regression runner.

## Compatibility and consumers

V1 behavior and structural validation remain unchanged. Ticket 03 and Ticket 04
may consume a byte-closed v2 result only as operational regression evidence.
They remain report-only/no-finalize and cannot promote v2 evidence to v1
acceptance.

Alignment remains unchanged, the Patch Import Manifest remains report-only, and
finalization is `none`.

The Main-to-Main operational consumer requires a byte-sealed
`vllm-dlc-main-to-main-operational-policy/v1` document. This closed-world policy
is approved only for `operational_only` claims and binds the exact vLLM SHA,
vllm-dlc SHA, Patch Import Manifest byte digest, DeepSeek operational role at
TP=2, and dense Llama operational role at TP=1. It fixes alignment to
`unchanged`, manifest handling to `report_only`, and finalization to `none`.

The consumer re-reads `policy_path`, checks the SHA-256 digest over the exact
bytes, validates the closed-world policy, and compares the policy target, role,
and TP to each sealed child run spec. Both children must also have distinct run
identities and the same target and execution campaign digest. The policy file is
a mandatory `main_to_main_operational_policy` entry in every operational
execution campaign. Online runner and offline evidence validation require the
exact skills-owned config path, close its byte digest through the campaign, and
require its target to equal the run-spec target. This approval does not raise
authoritativeness or acceptance eligibility.

## Exit precedence

V2 primary exit precedence is `50`, `41`, `42`, `40`, `10`, `23`, `24`, `22`,
`21`, `30`, `31`, `32`, `34`, `27`, `25`, `26`, `20`, `29`, then `0`.
Secondary diagnostics remain in the result.

## Consequences

Revised Ticket 06 can validate practical real-model operation without changing
runtime repositories. It cannot establish authoritative runtime behavior or
Verified vLLM Alignment. Those stronger conclusions require future
repository-owned instrumentation and trust work tracked separately.
