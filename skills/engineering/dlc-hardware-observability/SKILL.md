---
name: dlc-hardware-observability
description: Observe Real DLC Hardware with the official cltech_smi and normalized query-only evidence; use when model serving, image qualification, PD, environment repair, or debugging needs device, HBM, process, link, or cleanup snapshots without performing maintenance.
---

# DLC Hardware Observability

Establish a fail-closed SMI Observation Envelope. This skill owns query-only device observation; the caller owns model, runtime, transport, image, and recovery decisions.

## Inputs

- Run ID, artifact directory, Host/container namespaces, physical/logical device mapping, requested device count, workload PID/PGID when started, and four sample points.
- Official default-version `cltech_smi` executable; `chipltech_smi_lib` source root/full SHA and executable digest when available.
- Read access to device handles and Host process identity. Privileged Host integration, external debug upload, and Host maintenance remain separate authorizations.

## Workflow

1. Qualify the observation surface before model execution. Read current `cltech_smi -h`; record executable path/digest, source SHA when available, namespaces, device nodes/mapping, and artifact destination. Use `scripts/qualify-vllm-dlc-smi-environment.py`; do not clone/build/install `chipltech_smi_lib` without separate authorization. **Complete when:** the official query surface is uniquely identified, or `blocked_missing_observability` records the exact missing tool/mount/identity.
2. Capture raw and normalized query-only evidence at `before_launch`, `after_ready`, `during_request`, and `after_cleanup` with `scripts/observe-cltech-smi.py`. Bind active samples to the exact server PID/PGID. **Complete when:** every applicable sample point has raw output and a normalized terminal state.
3. Cross-check device enumeration/exclusion, finite positive HBM capacity, two-sample stable handle ownership, vendor process table, Host process group, and declared physical/logical mapping. Treat disagreement as an observability failure, not a hardware verdict. **Complete when:** every declared device and task process has one consistent mapping, or the earliest mismatch is preserved.
4. Localize failures without changing Host state. Device/holder/HBM anomalies stop before workload mutation; DLC Runtime failures route to fresh-process C1b; multi-device failures add group-scoped LYP/DLCCL plus content-validating communication probes; serving hangs correlate SMI, process/port, runtime logs, and optional `cltech_device_info` progress. **Complete when:** the next owning workflow and minimal probe are explicit.
5. Close cleanup against `before_launch`. Shared Hosts need not reach global zero; task-owned processes, handles, ports, and HBM delta must return to the sealed baseline/tolerance. **Complete when:** cleanup closes or the caller receives `blocked_cleanup_incomplete` with residual owner and impact.

## Public States

```text
observation_pass
blocked_missing_observability
observation_identity_mismatch
observation_process_mismatch
observation_cleanup_mismatch
```

## Claim Boundary

- Query-only SMI evidence can establish inventory, bounded HBM capacity, observed ownership, and run-local device reference.
- It does not independently prove C1b, Real DLC Hardware acceptance, DLC Runtime dispatch, model correctness, request-correlated KV transfer, communication correctness, or performance stability.
- Reset, LYP repair, driver/HBM/firmware work, power cycle, debug upload, and reboot are not observation. Route them through explicit authorization and a recovery contract, then rerun C1b and the owning workload.

conditional_reference: [SMI observation and diagnostic escalation](references/observation-contract.md)
