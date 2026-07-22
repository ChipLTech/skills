---
name: dlc-env-setup
description: Rebuild and verify a workstation DLC toolchain, PyTorch 2.5.0 wheel, and optional local vLLM runtime after rediscovering repo locations and checking git safety. Use when the user needs to bootstrap or repair a local DLC development environment, switch rebuild branches safely, or rerun PyTorch or vLLM install validation.
---

# DLC Env Setup

Use this skill to turn a machine with unknown repo layout into a validated DLC development workstation. Keep the execution flow here, and use the related knowledge-base docs for the reusable background rules.

## Use This Skill When

- The user wants a full DLC workstation rebuild.
- The user wants to switch one or more rebuild repos to target branches before rebuilding.
- The user wants a partial rebuild from LLVM, `DLC_Custom_Kernel`, PyTorch wheel build, or wheel reinstall.
- The user wants to repair local `vllm` or `vllm-dlc` editable installs on top of a working PyTorch DLC stack.

## Inputs To Collect Up Front

- Which stage to start from: full rebuild, LLVM, `DLC_Custom_Kernel`, PyTorch, wheel reinstall only, or optional `vllm` repair.
- Any requested repo-to-branch mapping before rebuild.
- Any user-provided workspace roots that should be searched before broad filesystem discovery.

## Automatic Workflow

1. Rediscover repo locations instead of assuming `/home/workspace`.
2. Build and echo a repo map for a usable CMake installation or source tree, `dlc-thunk`, `DLCsim`, `DLCSynapse`, `DLC_CL`, `LLVM`, `DLC_Custom_Kernel`, and `pytorch`.
3. Before mutation, validate every requested ref object, recursive submodule worktree, and expected build entrypoint. A submodule SHA alone is insufficient: the required `CMakeLists.txt`, Makefile, `setup.py`, or build script must exist in the worktree. When the builder UID differs from a task-owned source owner, validate canonical paths and write only the task root and build-time submodules to a task-local `GIT_CONFIG_GLOBAL` `safe.directory` file; remove that file during task cleanup.
4. If branch switching was requested, inspect `git status --short`, current branch, and branch availability before any checkout.
5. Before the first long build, read the Host driver API from its authority surface and choose a DLCSynapse ref explicitly compatible with it. Confirm Host driver version, source header, installed library, and fresh import agree; tags and existing images are provenance only. A fresh userspace import does not replace target-hardware runtime validation.
6. Run the rebuild in dependency order. A driver API or native dependency change invalidates every downstream consumer and requires rebuild through PyTorch, optional `vllm-dlc`, and optional `vllm`.
7. Run `scripts/pytorch-preflight.sh` before the PyTorch 2.5.0 wheel build. Set the approved PyTorch build version before the first configure; wheel metadata and `torch.__version__` must agree.
8. Force-reinstall the fresh wheel and verify runtime behavior from outside the source tree.
9. If the user asked for local `vllm` or `vllm-dlc` repair, run `scripts/vllm-preflight.sh` and then perform the editable installs.
10. Finish package validation with `scripts/runtime-smoke.sh` plus the final install checks listed below. Before Real DLC Hardware model serving, additionally run it with `--require-device-execution` in a fresh process.

## Rebuild Order

1. CMake check or install from the local source tree when the installed version is not strictly greater than `3.27.0`.
2. `dlc-thunk`
3. `DLCsim`
4. `DLCSynapse`
5. `DLC_CL`
6. `LLVM`
7. `DLC_Custom_Kernel`
8. PyTorch 2.5.0 wheel build and reinstall.
9. Optional `vllm` and `vllm-dlc` editable install repair.

## Partial Rebuild Rules

- From LLVM: rebuild LLVM, `DLC_Custom_Kernel`, PyTorch, reinstall the wheel, then rerun smoke.
- From `DLC_Custom_Kernel`: rebuild `DLC_Custom_Kernel`, PyTorch, reinstall the wheel, then rerun smoke.
- From PyTorch: confirm the native dependency installs still exist before building the wheel.
- Wheel reinstall only: use only when a fresh wheel already exists in `dist/`.
- If dependency health is unclear, fall back to the earlier stage instead of skipping ahead.

## Stop Immediately When

- Any required repo cannot be found.
- A discovered repo is missing its expected build entrypoint.
- Requested branch switching finds uncommitted changes.
- The requested branch does not exist locally or on the tracked remote.
- A build step fails and the failure is not resolved by the documented clean rebuild path.
- Package smoke fails after reinstall, especially if `torch.tensor(...).numpy()` or `import torch` outside the repo is broken.
- A requested Real DLC Hardware execution smoke fails or times out at device enumeration, allocation, H2D, device operation, synchronize, D2H, or correctness.
- Multiple candidate repos share the same name and the authoritative root is ambiguous.

## Verification Standard

- `/usr/local/bin/cmake --version` or the default `cmake --version` reports a version strictly greater than `3.27.0`.
- The default `cmake`, `ctest`, and `cpack` on `PATH` are available from the intended installation.
- `torch.__version__` reports `2.5.0` outside the PyTorch source tree.
- `torch.tensor([0.1], dtype=torch.float32).numpy()` succeeds outside the source tree.
- `/usr/local/chipltech/synapse/bin` contains the installed custom-kernel test tools.
- If optional `vllm` work was requested, inspect the fixed source packaging mode before setting a device target. A core `empty` platform plus independent `vllm-dlc` plugin is valid when the source implements that mode; do not force an unsupported core device target. `import vllm` and its `pip show` metadata checks succeed. `import vllm_dlc` and its metadata are additionally required only when the deployment contract uses the plugin.
- Before Real DLC Hardware model serving, `scripts/runtime-smoke.sh /tmp --require-device-execution` passes in a fresh process on every requested logical device. Use `--require-vllm` when vLLM is part of the contract. Plugin deployments add `--require-vllm-dlc`; a built-in DLC Platform deployment uses `--skip-vllm-dlc` after verifying its platform and entry-point identity.
- A native component is complete only when task build output exists, the build and install logs have terminal success, the installed target timestamp/hash matches the task output, and applicable `ldd`, `nm`, or fresh import validation succeeds. Finding a same-named base-image library is not evidence of the current rebuild.

## Script Assets

- `scripts/pytorch-preflight.sh`: Python packaging and NumPy preflight before building the wheel.
- `scripts/vllm-preflight.sh`: editable-install preflight for local `vllm` and `vllm-dlc` work.
- `scripts/runtime-smoke.sh`: package checks outside source trees, with optional required vLLM imports and an opt-in layered Real DLC Hardware execution gate.
- `agents/openai.yaml`: preserved agent entrypoint for environments that surface skill-specific quick prompts.

## Related Knowledge-Base Docs

- `/work/chipltech-knowledge-base/runtime-debugging/dlc-workstation-env-rebuild.md`
- `/work/chipltech-knowledge-base/debugging-workflows/python-build-preflight-for-pytorch-and-vllm.md`
- `/work/chipltech-knowledge-base/debugging-workflows/post-install-runtime-smoke.md`
- `/work/chipltech-knowledge-base/runtime-debugging/environment-setup-and-update.md`

## Operating Rules

- Echo the discovered repo map before long rebuild steps.
- Do not use destructive git commands unless the user explicitly asks.
- Keep platform-specific wrappers in this skill, not in the knowledge base.
- Treat the knowledge base as the source of reusable rationale, and this skill as the source of execution order.
- Do not infer device execution health from package imports, backend availability, allocation, or H2D alone. A recovery or device-state change requires a fresh-process layered execution smoke before model loading resumes.
