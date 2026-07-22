# DLC And TYD Delivery

Load this reference only after runtime qualification passes and image delivery is requested.

## DLC

Build from the qualified ordinary daily base and sealed runtime inputs. Model weights remain external. Record fixed tag, Image ID, base/source/model identities, dependency/extension hashes, build context, build log, exact-image C1a, exact-image C1b/function/benchmark states, tar path/size/SHA-256, attestation, and cleanup.

If exact-image runtime gates are not repeated, use `delivered_runtime_qualified_by_equivalent_environment` only when the equivalence record binds all inputs and differences.

## TYD

Derive TYD from the same model's qualified DLC Image ID. Other models' TYD images may provide offline recipes, source/binary overlays, or attestation schema, but cannot substitute for the current model's DLC baseline or delivery identity.

If a qualified DLC immutable Image ID is unavailable, return `blocked_missing_qualified_dlc_base`. A new full-stack build is a separately authorized `create_tyd_full_stack_rebuild` workflow covering dlc-thunk, LLVM, DLCsim, DLCSynapse, DLC_CL, DLC_Custom_Kernel Repository, PyTorch DLC Backend, vLLM, and applicable vLLM-DLC extension under `DLC_TPU_VERSION=2`. Image `ENV` alone is not a rebuild.

Before the first long build, close the Host driver API to a minimum compatible DLCSynapse ref, all source/submodule refs, task-builder Git ownership, CMake/ctest/cpack subprocess provenance, PyTorch build version, and the fixed vLLM packaging mode. A release tag does not prove driver API compatibility; validate the source header, installed library, and fresh import.

Build in dependency order. A driver API or native dependency change invalidates every downstream layer: rebuild the changed component, then its consumers through PyTorch, vLLM-DLC, and vLLM. A component is complete only with task build output, terminal build/install log, installed target timestamp/hash, and applicable `ldd`, `nm`, or fresh import evidence. Existing base-image libraries do not prove the current build ran.

For a PyTorch wheel, set the approved build version before the first configure. If generated `torch/version.py`, wheel metadata, and fresh import disagree, remove only task build/dist/generated-version outputs and rebuild from a clean task tree. For archive-based vLLM source, use its documented version override mechanism; probe whether core vLLM uses an `empty` platform plus vLLM-DLC plugin before passing a device target.

On DLC Gen1, run static/package/import/hash/label/attestation only. Report all TYD device scopes as `intentionally_not_executed_on_dlc_gen1`.
