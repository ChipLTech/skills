# Distributed Collective Qualification

`vllm-dlc-distributed-collective-qualification/v1` is the closed-world Stage A safety baseline for distributed model routes. It is a launch gate, not a parallel-performance profile. Validate artifacts with `scripts/validate-vllm-dlc-qualification.py`; execute an approved bounded harness with `scripts/run-dlccl-qualification.py`.

## Route Inventory

Inventory every reachable primitive and keep these route classes separate:

Use `scripts/inventory-vllm-dlc-collectives.py --vllm-root <root>` to seal the
source-level communicator and MoE caller snapshot. This inventory is generated
from the injected checkout rather than copied from a model fixture, and remains
`static_snapshot` evidence only.

| Route class | Required identity | It does not prove |
|---|---|---|
| `native_dlc_cl` | source SHA, native binary SHA-256, symbol, applicable ABI digest | PyTorch registration or completion |
| `pytorch_process_group` | exact ProcessGroup source route and backend | native symbol content correctness |
| `vllm_communicator` | exact vLLM communicator method and fallback state | model reachability |
| `model_route` | exact active model site and ownership predicate | communicator implementation |
| `moe_dispatch` | active dispatch route, dtype/count/rank order/completion | combine behavior |
| `moe_combine` | active combine route, dtype/count/rank order/completion | dispatch behavior |
| `custom_kernel` | public route, ordered descriptor ABI digest, entry symbol, binary SHA-256 | caller or collective routing |

For AllReduce, AllGather/AllGatherIntoTensor, Gather, ReduceScatter, ReduceScatterV, AllGatherV, AllToAll, Send/Recv, and active MoE dispatch/combine, record backend, dtype, shape/count, rank/world size, rank order, stream, async/completion boundary, fallback, and qualification state. An inactive anti-route remains in the inventory with `active: false` and must not appear in `required_route_ids`. Required route IDs equal the active route set exactly.

## Topology/Payload-Aware Selection

For a route with multiple topology-specific implementations, inventory the initialized communicator as the owner of actual LYP topology, formal algorithm lookup, root metadata, and rank order. Record every selector input, including payload bytes and applicable dtype/layout constraints; world size identifies participant count only. The framework adapter must cache by every decision input and pass a stable strategy plus explicit rank-domain metadata to the DLC Custom Kernel. The kernel dispatches the strategy and may reject illegal strategy or strategy/rank descriptor contradictions, while payload capacity, alignment, root availability, and preferred-implementation support remain pre-launch selection conditions.

Fallback is a state transition, not an enum substitution. Begin from Unknown, validate the candidate's graph, channel, complete rank order, rank range, uniqueness, root metadata, payload, and alignment prerequisites, then commit the candidate only after all applicable checks pass. A formal selector may downgrade a multi-root implementation to a verified single-root implementation when that transition is explicitly defined; otherwise it must validate the generic fallback or remain Unknown and fail closed.

Qualification fixtures cover each formal threshold boundary, aligned and unaligned payloads, missing/out-of-range/duplicate roots, unknown mapping, incomplete or duplicate rank order, fallback validation failure, and changed payload on one communicator. Static/source checks establish selection structure only. Real qualification binds exact selector source, loaded native and kernel binaries, actual LYP topology, payload, all-rank content correctness, and task-owned cleanup evidence.

## Preflight And Stops

Preflight runs before any harness launch. The artifact is a Qualification Artifact Envelope v1 extension and must pass the generated `validate_envelope(document, ("qualification",))` validator. Envelope blockers use only canonical `status`, `code`, and `path` fields; distributed phase, message, and resume detail remains under `qualification.blocker_details`. Status aggregation is always `failed` before `blocked` before `not_verified`.

Collect live identity first with
`scripts/collect-vllm-dlc-live-identity.py <spec> <output>`. The collector is
read-only, validates a closed-world spec, hashes path type/content and symlink
target, requires a clean authoritative Git root for source observation, and
emits all thirteen Qualification Artifact Envelope identity classes as
non-authoritative `operational_only` evidence with terminal state
`not_verified` / `blocked_non_atomic_identity_snapshot`. Sequential read-only
collection cannot prove that thirteen mutable paths formed one atomic snapshot;
only an authoritative atomic identity provider can remove this blocker.
Caller-selected metadata sidecars
are byte-bound but do not replace authoritative package DB, image engine,
runtime/driver, model registry, policy authority, or official hardware
producers. The
attester re-runs the same collector spec immediately before issuance and rejects
any digest drift as `blocked_stale_live_identity`. A static source snapshot is
always non-authoritative `static_snapshot` evidence and cannot be attested.

Provider observations use the closed-world
`references/identity-provider-seal-v1.schema.json` contract and canonical
`scripts/identity_provider_seal.py` validator. An authoritative seal requires a
provider identity trusted outside the seal, an immutable generation or
transaction ID with `atomic: true`, an observation and expiry time, a raw
evidence digest, an exact subject class, and `passed` status. Self-declared
provider identity, wrong-class seals, expired seals, unknown fields, digest
drift, and stale generations fail closed. A package provider cannot satisfy an
image, runtime, model, policy, or hardware identity.

Provider code identity is not seal authentication. This v1 contract has no
approved detached-signature or equivalent provider-controlled authentication
mechanism, so every otherwise `authoritative` seal remains blocked as
`blocked_missing_authenticated_provider_seal`. Authoritative verification also
requires the exact externally trusted provider ID/version/code identity, the
provider's current generation, and `observed_at <= now < expires_at`. Do not use
the public code digest or canonical document SHA-256 as a credential.

`scripts/observe-python-package-identity.py` is the first provider adapter. It
derives package name, version, installed path, recorded files, and native binary
digests from Python distribution `METADATA` and `RECORD`, not a caller metadata
sidecar. The actual package tree must pair exactly with the package files in
`RECORD`; unrecorded Python or native files fail as
`blocked_package_binary_pairing_unresolved`. It re-observes the distribution to
detect a mutation window. Standard
Python installation metadata exposes no atomic package database generation, so
this adapter intentionally emits `operational` / `not_verified` with
`blocked_missing_atomic_package_generation`; drift emits
`blocked_unstable_package_identity`, and an absent or unpairable record emits
`blocked_package_binary_pairing_unresolved`.

The live collector may consume this package seal only with the package name and
search roots needed to re-run the adapter. It compares the complete seal digest
and includes that digest in `input_artifact_digests`. Consumption replaces the
caller-selected package sidecar but does not upgrade the collector above
`non_authoritative` or remove `blocked_non_atomic_identity_snapshot`.

`scripts/attest-vllm-dlc-qualification.py` invokes the canonical distributed
validator and immediately re-runs the live collector. It does not issue a
signature in this version: production issuance remains
`blocked_missing_authoritative_identity_producers` or
`blocked_missing_trusted_qualification_inputs` until authoritative identity
producers, trusted authorization, official hardware observation, pinned harness
identity, and independent oracle provenance are supplied. Missing inputs stop as
`blocked_missing_trusted_qualification_inputs`; invalid or stale bindings stop
as `blocked_collective_not_qualified`. Single-rank construction does not require
distributed evidence.

An active unsupported route stops as `blocked_collective_unimplemented`; an active implemented but unqualified route stops as `blocked_collective_not_qualified`. Missing native/custom ABI or binary identity stops as `blocked_missing_identity`. Missing authorization stops as `blocked_missing_authorization`. Missing Real DLC Hardware stops as `blocked_missing_hardware`, resumes at `real_dlc_hardware_allocation`, and remains `not_verified` for a controlled fixture.

Requests for `formal_acceptance` or shared-device modification are dangerous operations outside this runner's authority and stop as `blocked_dangerous_operation`. Resume by supplying an authorized bounded `qualify` request; do not weaken the route or producer policy.

## Bounded Runner

The runner accepts an argv vector, starts a new process session, applies an external timeout to each attempt, and aggregates every rank exit. On timeout it terminates the whole task-owned process group, escalates to SIGKILL when needed, reaps it, checks residual process-group members, and records a post-failure health snapshot. A collective's internal timeout never replaces this watchdog.

Controlled fixtures exercise watchdog, parent exit, rank aggregation, and process-group cleanup semantics without hardware. They emit `fixture` evidence only and are not collective evidence. A nonzero harness parent is failure even if its stdout claims passing ranks. Cleanup targets the task-owned process group even when the parent exits before a child.

Real qualification fails closed before launch unless trusted external authorization, the official `dlc-hardware-observability` envelope, a pinned harness identity, and a correctness-result schema are supplied and validated. Stage A does not yet consume those trusted inputs, so it emits `blocked_missing_trusted_qualification_inputs` and resumes at `trusted_qualification_inputs` rather than launching. SMI observations alone do not establish collective correctness.

The runner producer is fixed as `model-adaptation/dlccl-qualification-runner` version `1.0.0`. Controlled execution emits only non-authoritative `fixture` evidence. A future trusted real path may emit bounded `qualification` evidence with operational authority. The runner never emits `formal_acceptance`, never sets `acceptance_eligible` true, and never accepts a model, benchmark, or image. `modelzoo-image-validation` must independently rerun any formal gate it owns.

Every artifact claim must begin with the literal label:

`Claim Boundary:`

The boundary states what the exact run established and explicitly retains Real DLC Hardware, model, benchmark, image, and global alignment scope as unverified when they were not independently executed.
