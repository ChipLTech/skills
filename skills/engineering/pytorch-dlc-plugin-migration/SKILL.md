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
- For every external architecture reference: source locator, revision or SHA-256, license metadata, intended use, reviewer roles, and source-register disposition.

Ambiguous roots, missing production semantics, overlapping uncommitted changes, or missing authorization stop before mutation.

## Workflow

1. Discover and freeze the three authoritative roots. Record repository root, full SHA, branch, dirty state, package/import origin, compiler/build profile, and relevant binary identities. Read the knowledge-base `CONTEXT.md`, `README.md`, and `prompt-examples/pytorch-dlc-plugin-migration-prompts.md`. **Complete when:** each source has one unambiguous identity and every pre-existing modification has an owner or exclusion.
2. Run the source classification gate before viewing or using any external architecture reference. Check its source locator, revision or SHA-256, license metadata, intended use, reviewer-role separation, and disposition against `restricted-reference-governance.json`. Missing, unregistered, unreviewed, or unresolved input returns `blocked_legal_boundary`. Keywords such as `torch_npu` only trigger review and are not legal conclusions; 关键词只触发 review。A permitted reviewer may produce an independent DLC-native specification; the implementation author must not receive or directly migrate from restricted source. 不得复制、翻译或机械改写 reference code、tests、templates、Skill prose、schema 或 eval. **Complete when:** no reference is used without a resolved disposition and ADR 0005 role separation.
3. Map the vertical slice across production implementation and registration, standard PyTorch PrivateUse1 extension points, and target-plugin source/build/package entrypoints. Architecture references may inform licensed structure questions but never operator or hardware semantics; the production PyTorch DLC Backend remains the DLC semantics authority. **Complete when:** every source, registration, generated file, target, and artifact in the slice has an owner and expected destination.
4. Classify each capability as direct source migration, built-in integration requiring PrivateUse1 adaptation, standard extension interface requiring registration, or absent production behavior. Preserve absent behavior as a deterministic unsupported path; do not invent a DLC Custom Kernel or CPU computation fallback. **Complete when:** every requested capability has exactly one class and evidence source.
5. Freeze the semantic contract before editing. Preserve Public Operator Schema behavior, kernel name and selection, KernelDesc argument order, DLC Custom Kernel Entry ABI, dtype/layout/contiguity/rank boundaries, error propagation, and async completion semantics. Replace built-in registration mechanics with standard PrivateUse1 plugin registration; registration mechanism changes are expected, semantic dispatch drift is not. **Complete when:** a reviewer can compare each preserved contract field against production evidence.
6. Implement only the migration adapters required by the slice: PrivateUse1 dispatch, device guard, allocator, stream/event, StorageImpl, KernelDesc adapter, codegen/YAML, include/namespace/visibility, source lists, and packaging as applicable. Keep shared-file writes serialized across agents; subagents do not commit. **Complete when:** the target plugin owns the slice through its normal build and registration paths without unrelated changes.
7. Delegate environment/package/Stack Preflight and C1a/C1b evidence to `dlc-env-setup`; consume a fresh Package Provider seal within its operational ceiling. Delegate query-only device/process/HBM/cleanup observation to `dlc-hardware-observability`, while the migration owner retains responsibility for exact plugin behavior assertions on Real DLC Hardware; SMI observation cannot substitute for behavior. Consume a route qualification artifact for an applicable distributed slice. The migration owner also retains source mapping, PrivateUse1 adaptation, migration diff, compile/link, and wheel/import evidence. **Complete when:** every evidence dimension names its owner and exact artifact, or remains an explicit blocker/not-verified state.
8. Close gates in increasing cost: generator/static boundary checks and affected-target compile are always mandatory for an implemented slice; link is mandatory when linked code changes; full-core, wheel, and isolated standard-host import are mandatory when the default or release artifact changes. Device behavior may be deferred only when the contract does not require runtime acceptance or authorization/hardware is unavailable; record owner, reason, and exact unverified behavior. A compile, registration count, import, or one smoke proves only its own gate. **Complete when:** every applicable mandatory build/package gate has raw output and every permitted behavior deferral is explicit.
9. Audit completion against exact evidence. Bind every claim to repository identity, build command/configuration, timestamp, artifact path/hash, package/import origin, and applicable device/environment identity. Classify each result as `direct_repository_evidence`, `runtime_observation`, `inference`, or `missing_evidence`. **Complete when:** no completion claim depends on stale or unbound output.
10. Review the final diff and artifacts, excluding caches, personal paths, temporary worktrees, and unrelated changes. Restore or explicitly retain every generated file, build output, installed package, temporary worktree, import environment, and device allocation against the sealed baseline. Commit or push only under their separate authorization. **Complete when:** cleanup is closed and the requested slice and deferred-test ledger are reproducible from the recorded identities.

## Public States

```text
all_declared_dimensions_passed
implementation_complete_tests_deferred
unsupported_by_production_backend
failed_validation
not_verified
blocked_ambiguous_source
blocked_missing_production_semantics
blocked_overlapping_changes
blocked_missing_authorization
blocked_legal_boundary
blocked_missing_preflight
blocked_stale_package_seal
blocked_stale_owner_evidence
blocked_missing_observability
blocked_distributed_route_unqualified
blocked_cleanup_incomplete
```

Report source migration, compile/link, wheel/import, DLC Runtime execution, Real DLC Hardware behavior, distributed behavior, and cleanup independently using `references/plugin-migration-result-v1.schema.json` and `scripts/evaluate-plugin-migration.py`. Results remain non-authoritative and not acceptance eligible until authoritative providers are closed.

Aggregate deterministically:

1. `blocked_cleanup_incomplete` wins when workspace, package, build, import, or device state does not return to the sealed baseline or an explicitly retained deliverable state.
2. Otherwise report every active blocker and use the earliest workflow blocker as primary.
3. Otherwise `failed_validation` wins when any executed mandatory gate fails.
4. Otherwise `unsupported_by_production_backend` applies only when production evidence proves the requested behavior absent and no implementation was invented.
5. Otherwise `implementation_complete_tests_deferred` requires all applicable build/package gates to pass and only explicitly permitted device behavior to remain unverified.
6. Otherwise `not_verified` applies when a mandatory gate was not executed without a permitted deferral.
7. Otherwise `all_declared_dimensions_passed` means every applicable dimension has owner-bound supplied evidence marked pass; because authoritative providers remain incomplete, it is neither authoritative nor acceptance eligible.

## Claim Boundary

- Architecture similarity does not transfer another backend's device semantics to DLC Platform.
- PrivateUse1 registration or isolated import does not prove operator behavior or Real DLC Hardware execution.
- Build output is valid only for its bound source, configuration, toolchain, and artifact identity.
- CPU may supply constants or serve as an H2D/D2H endpoint; CPU computation fallback is not migrated production behavior unless production evidence explicitly says otherwise.
- This Skill migrates existing behavior. New operator semantics or DLC Custom Kernel work requires a separate owner and contract.
