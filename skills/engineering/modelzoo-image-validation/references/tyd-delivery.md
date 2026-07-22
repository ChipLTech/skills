# DLC And TYD Delivery

Load this reference only after runtime qualification passes and image delivery is requested.

## DLC

Build from the qualified ordinary daily base and sealed runtime inputs. Model weights remain external. Record fixed tag, Image ID, base/source/model identities, dependency/extension hashes, build context, build log, exact-image C1a, exact-image C1b/function/benchmark states, tar path/size/SHA-256, attestation, and cleanup.

If exact-image runtime gates are not repeated, use `delivered_runtime_qualified_by_equivalent_environment` only when the equivalence record binds all inputs and differences.

## TYD

Prefer an immutable, inspectable full-stack TYD base with upstream attestation. Inherited packaging records `provenance_mode: inherited_full_stack_tyd_base` and does not recreate upstream compile evidence.

Without an eligible base, return `blocked_missing_qualified_tyd_base`. A new full-stack build is a separately authorized `create_tyd_full_stack_base` workflow covering dlc-thunk, LLVM, DLCsim, DLCSynapse, DLC_CL, DLC_Custom_Kernel Repository, PyTorch DLC Backend, vLLM, and applicable vLLM-DLC extension under `DLC_TPU_VERSION=2`. Image `ENV` alone is not a rebuild.

On DLC Gen1, run static/package/import/hash/label/attestation only. Report all TYD device scopes as `intentionally_not_executed_on_dlc_gen1`.
