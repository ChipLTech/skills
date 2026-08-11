---
name: pytorch-dlc-plugin-migration
description: Migrate an existing production PyTorch DLC Backend component into a standard PrivateUse1 loadable plugin while preserving operator semantics and DLC kernel ABIs; use for component migration, phase audits, compile/link/wheel closure, and deferred-test accounting, not for inventing new DLC Custom Kernel semantics.
---

# PyTorch DLC Plugin Migration

Migrate existing production behavior from a built-in PyTorch DLC Backend into a loadable PrivateUse1 plugin. The production backend owns DLC behavior, standard PyTorch owns extension contracts, and any architecture reference supplies structure only.

## Inputs

- Exact roots, full SHAs, dirty states, and build identities for the production PyTorch DLC Backend, standard PyTorch host, and target plugin.
- Migration slice, writable paths, protected paths, expected artifacts, and deferred-test ledger.
- Separate authorization for workspace mutation, build, install, device execution, artifact writing, commit, and push.
- Production evidence for the public operator semantics, kernel selection, KernelDesc Descriptor ABI, DLC Custom Kernel Entry ABI, dtype/layout/rank/error boundaries, and unsupported behavior.

Ambiguous roots, missing production semantics, overlapping uncommitted changes, or missing authorization stop before mutation.

## Workflow

1. Discover and freeze the three authoritative roots. Record repository root, full SHA, branch, dirty state, package/import origin, compiler/build profile, and relevant binary identities. Read the knowledge-base `CONTEXT.md`, `README.md`, and `prompt-examples/pytorch-dlc-plugin-migration-prompts.md`. **Complete when:** each source has one unambiguous identity and every pre-existing modification has an owner or exclusion.
2. Map the vertical slice across production implementation and registration, standard PyTorch PrivateUse1 extension points, and target-plugin source/build/package entrypoints. Architecture references may inform layering but never operator or hardware semantics. **Complete when:** every source, registration, generated file, target, and artifact in the slice has an owner and expected destination.
3. Classify each capability as direct source migration, built-in integration requiring PrivateUse1 adaptation, standard extension interface requiring registration, or absent production behavior. Preserve absent behavior as a deterministic unsupported path; do not invent a DLC Custom Kernel or CPU computation fallback. **Complete when:** every requested capability has exactly one class and evidence source.
4. Freeze the semantic contract before editing. Preserve Public Operator Schema behavior, kernel name and selection, KernelDesc argument order, DLC Custom Kernel Entry ABI, dtype/layout/contiguity/rank boundaries, error propagation, and async completion semantics. Replace built-in registration mechanics with standard PrivateUse1 plugin registration; registration mechanism changes are expected, semantic dispatch drift is not. **Complete when:** a reviewer can compare each preserved contract field against production evidence.
5. Implement only the migration adapters required by the slice: PrivateUse1 dispatch, device guard, allocator, stream/event, StorageImpl, KernelDesc adapter, codegen/YAML, include/namespace/visibility, source lists, and packaging as applicable. Keep shared-file writes serialized across agents; subagents do not commit. **Complete when:** the target plugin owns the slice through its normal build and registration paths without unrelated changes.
6. Close gates in increasing cost: generator/static boundary checks and affected-target compile are always mandatory for an implemented slice; link is mandatory when linked code changes; full-core, wheel, and isolated standard-host import are mandatory when the default or release artifact changes. Device behavior may be deferred only when the contract does not require runtime acceptance or authorization/hardware is unavailable; record owner, reason, and exact unverified behavior. A compile, registration count, import, or one smoke proves only its own gate. **Complete when:** every applicable mandatory build/package gate has raw output and every permitted behavior deferral is explicit.
7. Audit completion against exact evidence. Bind every claim to repository identity, build command/configuration, timestamp, artifact path/hash, package/import origin, and applicable device/environment identity. Classify each result as `direct_repository_evidence`, `runtime_observation`, `inference`, or `missing_evidence`. **Complete when:** no completion claim depends on stale or unbound output.
8. Review the final diff and artifacts, excluding caches, personal paths, temporary worktrees, and unrelated changes. Restore or explicitly retain every generated file, build output, installed package, temporary worktree, import environment, and device allocation against the sealed baseline. Commit or push only under their separate authorization. **Complete when:** cleanup is closed and the requested slice and deferred-test ledger are reproducible from the recorded identities.

## Public States

```text
plugin_slice_validated
implementation_complete_tests_deferred
unsupported_by_production_backend
failed_validation
not_verified
blocked_ambiguous_source
blocked_missing_production_semantics
blocked_overlapping_changes
blocked_missing_authorization
blocked_cleanup_incomplete
```

Report source mapping, semantic contract, migration adapters, gate results, deferred tests, evidence classes, artifact identities, and remaining risks independently.

Aggregate deterministically:

1. `blocked_cleanup_incomplete` wins when workspace, package, build, import, or device state does not return to the sealed baseline or an explicitly retained deliverable state.
2. Otherwise report every active blocker and use the earliest workflow blocker as primary.
3. Otherwise `failed_validation` wins when any executed mandatory gate fails.
4. Otherwise `unsupported_by_production_backend` applies only when production evidence proves the requested behavior absent and no implementation was invented.
5. Otherwise `implementation_complete_tests_deferred` requires all applicable build/package gates to pass and only explicitly permitted device behavior to remain unverified.
6. Otherwise `not_verified` applies when a mandatory gate was not executed without a permitted deferral.
7. Otherwise `plugin_slice_validated` requires every contract-mandatory build, package, import, and device behavior gate to pass.

## Claim Boundary

- Architecture similarity does not transfer another backend's device semantics to DLC Platform.
- PrivateUse1 registration or isolated import does not prove operator behavior or Real DLC Hardware execution.
- Build output is valid only for its bound source, configuration, toolchain, and artifact identity.
- CPU may supply constants or serve as an H2D/D2H endpoint; CPU computation fallback is not migrated production behavior unless production evidence explicitly says otherwise.
- This Skill migrates existing behavior. New operator semantics or DLC Custom Kernel work requires a separate owner and contract.
