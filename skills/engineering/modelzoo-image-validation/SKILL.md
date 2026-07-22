---
name: modelzoo-image-validation
description: Qualify a local model from an ordinary daily base, use ModelZoo as optional read-only reference, then build independent DLC Chip and TYD Chip deliverables only after functional and benchmark gates pass. Use for ModelZoo-to-image workflows, local-model runtime qualification, or DLC/TYD image export.
---

# ModelZoo Image Validation

This skill orchestrates a **runtime-first** model delivery. The local model is authoritative for execution; ModelZoo is optional reference evidence. Build a formal model image only after C1a, C1b, real-weight functional assertions, and the declared benchmark workload pass.

## Inputs

- Model name and absolute local model directory.
- Mode: `qualification_only` or `qualification_and_image_delivery`.
- Optional framework selector and ModelZoo root.
- Requested targets: DLC, TYD, or both.
- Authorization for each requested pull, network/install, build, device, export, Host-maintenance, and push action.

## Workflow

1. Qualify local assets before ModelZoo. Require `config.json`, non-empty weights, and applicable tokenizer/processor; record architecture, dtype, quantization, shard inventory, size, and digests without serializing model contents. **Complete when:** the selected asset identity is closed, or `blocked_missing_asset` names the exact resume input.
2. Resolve ModelZoo through `scripts/resolve-modelzoo.py` when available. Treat `modelzoo_reference_unavailable`, `modelzoo_reference_incomplete`, `modelzoo_reference_ambiguous`, and `modelzoo_reference_malformed` as reference states, not local functional blockers. **Complete when:** a deterministic reference record is retained without ModelZoo mutation.
3. Write a stable resolved-model manifest and a separate runtime qualification contract. Keep `modelzoo_claims`, `local_observations`, `inferences`, `execution_evidence`, and `unverified_scope` separate. **Complete when:** stable resolution excludes PID, port, HBM, occupancy, and timestamps, while the runtime contract binds all run-local inputs and assertions.
4. Qualify an immutable ordinary daily base and create a task-owned persistent validation environment. Before any model load, close the driver API, device mapping, C1b-compatible container profile, clean source/submodule worktrees, binary overlay provenance, and the CMake toolchain used by actual build subprocesses. Model-specialized, golden, candidate, or unexplained images are ineligible. Follow [Runtime Qualification](references/runtime-qualification.md). **Complete when:** base/container/source/package/device identities and the cleanup baseline are closed.
5. Delegate package/import and layered device checks to `dlc-env-setup`; delegate capability analysis, TP derivation, and model-specific compatibility to `model-adaptation`. Do not duplicate their probes. Recreate only the task container for a known driver-profile mismatch; use partial clone plus fixed-object verification for interrupted large repositories; restore only the same fixed commit for an incomplete task-owned submodule. **Complete when:** C1a and every required C1b/device/collective result have terminal states.
6. Execute real-weight functional assertions, then the declared benchmark. Read the installed server `--help`, use an explicit absolute model path, and set offline Hub guards before starting a server. Functional failure blocks benchmark and delivery. Distinguish `benchmark_workload_pass` from `benchmark_stability_baseline_pass`; a declared single-run workload may qualify delivery without becoming a stable baseline. **Complete when:** raw requests/results, health, server epochs, profile diff, warm-up/formal attempts, and cleanup evidence are retained.
7. For image delivery, seal runtime evidence before building. Build DLC as a fixed-tag, weight-free image and record exact-image validation separately from pre-build runtime qualification. **Complete when:** image/base/source/build identities, exact-image C1a, tar path/size/SHA-256, attestation, validation level, and target cleanup are closed.
8. Derive TYD from the delivered DLC Image ID through [DLC And TYD Delivery](references/tyd-delivery.md). Driver API changes and any rebuilt native dependency require downstream rebuild through PyTorch, vLLM-DLC, and vLLM; never infer a rebuild from an existing base library. **Complete when:** TYD has its own fixed tag, Image ID, tar/hash, provenance, static/exact-image result, prohibited device scope, and final target status.
9. Emit independent DLC/TYD final states and clean only task-owned resources. **Complete when:** task processes/ports/HBM delta return to the sealed baseline or tolerance; retained deliverables and failed epochs are explicit; no unrelated resource was modified.

## Public States

Reference states:

```text
modelzoo_reference_resolved
modelzoo_reference_unavailable
modelzoo_reference_incomplete
modelzoo_reference_ambiguous
modelzoo_reference_malformed
```

Workflow blockers:

```text
blocked_missing_asset
blocked_unqualified_daily_base
blocked_unresolved_runtime_contract
blocked_unsupported_framework
blocked_missing_hardware
blocked_missing_authorization
blocked_missing_qualified_dlc_base
blocked_cleanup_incomplete
```

Delivery states:

```text
delivered_runtime_qualified
delivered_runtime_qualified_by_equivalent_environment
delivered_static_package_only
prequalification_only
failed_validation
```

## Claim Boundary

- C1a is package/import evidence, not device execution.
- C1b is bounded DLC Runtime execution, not model correctness.
- HTTP success, weight load, health, or non-empty output do not replace semantic assertions.
- A benchmark workload pass is not a stable performance baseline unless repeated attempts were declared and completed.
- Pre-build runtime evidence is not exact-image runtime evidence; bind equivalence and report exact-image validation level.
- Static/package/hash/label checks do not prove TYD functionality.
- On DLC Gen1, TYD device operation, C1b, DLCCL, model load, serving, and benchmark are `intentionally_not_executed_on_dlc_gen1`.
- A native component is rebuilt only when task build output, terminal build/install logs, installed-target hash, and applicable linker/symbol/fresh-import evidence all agree.
- A source archive SHA never proves a compiled extension identity; record both source and binary hashes.

## Resolver Exit Contract

- Exit `0`: deterministic `modelzoo-reference-record/v1`, including unavailable/incomplete/ambiguous/malformed reference states.
- Exit `2`: caller error such as invalid CLI arguments.
- Exit `70`: internal failure to perform safe read-only resolution.

The resolver never validates local assets, qualifies hardware, authorizes actions, builds images, or emits runtime PASS.

conditional_reference: [Runtime qualification from an ordinary daily base](references/runtime-qualification.md)
conditional_reference: [Independent DLC and TYD delivery](references/tyd-delivery.md)
