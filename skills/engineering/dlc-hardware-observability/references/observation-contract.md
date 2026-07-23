# SMI Observation And Diagnostic Escalation

## Four Sample Points

| Point | Required identity | Purpose |
|---|---|---|
| `before_launch` | run, devices, baseline holders | Seal inventory, exclusions, capacity, occupancy, HBM, and cleanup baseline |
| `after_ready` | server PID/PGID and epoch | Prove the declared workload owns the observed devices after readiness |
| `during_request` | same PID/PGID and active request/attempt | Correlate active work with device ownership and HBM state |
| `after_cleanup` | run and sealed baseline | Close task-owned process/handle/HBM delta without requiring global zero |

Preserve raw `cltech_smi` output beside normalized `vllm-dlc-smi-observation/v1` JSON. The skills-owned adapter queries device inventory, exclusions, total HBM, and the vendor process table, then cross-checks two Host handle samples and process-group membership. Adapter exit failure is `blocked_missing_observability`, not evidence that a device failed.

## Installation Modes

- Installed skill: use `<SKILL_ROOT>/scripts/qualify-vllm-dlc-smi-environment.py` and `<SKILL_ROOT>/scripts/observe-cltech-smi.py`.
- Full skills checkout: repo-level compatibility entrypoints remain available under `<SKILLS_ROOT>/scripts/` for existing contracts.
- Missing official tool: discover approved installed locations. Clone/build/install only with network/build/install authorization, then seal source SHA and executable digest before use. Do not recreate the normalized schema manually.

## Escalation Matrix

| Observation | Next owner/probe |
|---|---|
| Missing/excluded device or unexpected holder | Caller preflight; stop before model load |
| HBM delta or static server PID after timeout | Process/port/runtime logs plus fresh C1b as applicable |
| Allocation/H2D/op/sync/D2H failure | `dlc-env-setup` layered C1b |
| Multi-device or communication failure | Group-scoped LYP/DLCCL check plus content-validating collective/transport gate |
| Model output failure with healthy observation | `model-adaptation`; SMI does not establish model cause |
| Cleanup mismatch | Owning workflow returns `blocked_cleanup_incomplete` |

`cltech_device_info` head/tail progress may help localize a hang but does not prove root cause. `cltech_smi --debug` performs external upload and requires explicit content/external-communication authorization.
