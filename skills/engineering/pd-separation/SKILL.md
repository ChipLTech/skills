---
name: pd-separation
description: Deploy or diagnose vLLM-DLC Prefill/Decode separation with MooncakeDLCConnector; use for single-node TCP, qualified lyp_full or dlccl_direct, cross-machine TCP, transport qualification, KV-transfer lifecycle, routing, and recovery.
---

# Prefill/Decode Separation

Establish a request-correlated Prefill/Decode (PD) deployment. Service readiness is only a startup signal; completion requires evidence that the intended Prefill Worker produced KV Cache and the intended Decode Worker consumed it.

## Inputs

- Exact vLLM, vllm-dlc, mooncake-dlc, PyTorch DLC Backend, and model identities.
- Topology: `single_node_tcp`, `single_node_lyp_full`, qualified `single_node_dlccl_direct`, or `cross_machine_tcp`.
- Prefill, Decode, and Proxy hosts, routable addresses, device sets, TP, and ports.
- Model, tokenizer, dtype, quantization, KV layout/cache dtype, block size, context, and role-specific vLLM arguments.
- Artifact directory and authorization for network, install/build, device execution, privileged Host integration, and Host maintenance as separate actions.
- Sealed process/device/port/HBM/link/package/source/build-artifact baseline plus a recovery contract for every pre-existing workload that Host maintenance could disrupt.

Missing topology, model/cache compatibility, routable endpoint, required hardware, or authorization is a blocker. Device execution never authorizes process eviction, `--privileged`, Host PID namespace, Host system mounts, driver reload, firmware/Chip ID/HBM operations, PCIe reconfiguration, or reboot.

## Workflow

1. Freeze the deployment contract before launching. Record full source/package identities, model asset identity, both role profiles, connector/module identity, transport, endpoint and port matrix, request parameters, expected evidence, cleanup baseline, pre-existing workload recovery commands, and the SMI Observation Envelope owned by `dlc-hardware-observability`. Read installed `pd_launcher`, proxy, and vLLM `--help`; inspect actual routes instead of assuming `/health`; source examples never override the checked-out implementation. **Complete when:** every identity, endpoint, capability-derived readiness probe, observer, and recovery target is fixed, or a structured blocker names the exact missing input.
2. Establish a monolithic serving baseline for the same model and equivalent deterministic request. Delegate environment repair to `dlc-env-setup`; delegate model-specific Attention, MLA, MoE, quantization, MTP, KV-layout, TP, or DCP compatibility to `model-adaptation`. **Complete when:** the baseline passes with raw evidence, or its failure is isolated outside PD orchestration.
3. Qualify the declared devices and links without changing Host state. Confirm no task-owned stale process remains, device sets are disjoint when co-located, TP matches each visible set, required API/side-channel/store/RPC ports are free, and peer paths are reachable. Treat single-device tensor allocation and PCIe health as weaker than the exact LYP/DLCCL data path. **Complete when:** both roles have a clean observed baseline and every device-group, port, and peer-path check has raw pass/fail evidence.
4. Select one supported transport branch from [DLC adaptation](references/dlc-adaptation.md), then run its smallest available transport-only gate before loading two models. Default to `tcp`; use `lyp_full` only on a qualified same-host LYP group; use `dlccl_direct` only when the exact checkout contains that protocol and its native extension; keep legacy `lyp` diagnostic-only. The gate must prove both endpoints can initialize concurrently, transfer a non-empty payload, complete send/receive, and validate received content; a process exit or latency sample alone is insufficient. **Complete when:** the selected branch passes the exact data-path gate, or the run stops with `blocked_transport_unqualified` and preserves the earliest failure.
5. Launch roles according to [Deployment and troubleshooting](references/deployment-and-troubleshooting.md). Set device visibility, protocol, and side-channel variables before importing vLLM or spawning workers. For ordinary TCP, launch Prefill then Decode; for `lyp_full`, launch Decode as soon as Prefill's store listener exists rather than waiting for Prefill HTTP readiness; then launch Proxy after both role probes pass. Use `kv_producer` and `kv_consumer`. **Complete when:** separate server epochs show the intended environment and connector roles, every declared readiness probe passes, and eager transports initialize; lazy `dlccl_direct` communicator evidence is explicitly deferred to step 6.
6. Run one deterministic request through Proxy before concurrency work. Correlate client, Proxy, Prefill, and Decode identities; retain lazy transport initialization when applicable, Prefill block ownership/registration, Decode `remote_request_id`, local/remote block mapping, transport completion, successful device-side receive, response, role health-after, and raw/normalized SMI observations across both role process groups. **Complete when:** request-correlated evidence proves routing and KV consumption, every deferred transport initialization completes, output meets the comparison contract, both role epochs remain healthy, and `during_request` binds the intended processes to the declared devices.
7. Expand one variable at a time through lifecycle, concurrency, long-context, and performance checks. Measure TTFT, TPOT, ITL, throughput, queueing, and KV-transfer cost separately; compare against the declared monolithic workload without claiming causality from a single sample. **Complete when:** each requested workload has raw results, role logs, health-after, and an explicit `pass`, `failed`, or `not_verified` state.
8. Diagnose failures by earliest phase: identity/config, device-group qualification, transport-only gate, startup, connector/control plane, metadata/request correlation, KV layout/block mapping, Decode cache availability, functional divergence, performance, or cleanup. Change one variable per failure epoch. If request identities and blocks align but native completion hangs, return to the transport-only gate and Host LYP state before modifying connector semantics. **Complete when:** the earliest failing phase is bounded and the next probe or blocker is reproducible.
9. Escalate state-changing LYP initialization, power cycle, Bluejay/HBM work, driver reload, or reboot only through the Host-maintenance contract. Re-seal device numbering, link/HBM state, containers, ports, and pre-existing workloads after every such action; map tool-local failure indexes to physical devices before repair. **Complete when:** maintenance has an authorized target and recovery evidence, or execution stops before the state change.
10. Stop Proxy, Decode, then Prefill and clean only task-owned process groups. Stopping a `docker exec` client is not proof that its container process exited. Compare process groups, ports, HBM, frequency/link state, packages, source/build artifacts, and every pre-existing workload with the sealed baseline; remove temporary wheels/extensions/worktrees/overlays or explicitly retain them as declared deliverables. Validate restored services with an actual request, not health alone. **Complete when:** the full site baseline is restored or `blocked_cleanup_incomplete` records the residual owner, impact, and authorized resume action.

## Public States

```text
pd_validated
failed_validation
not_verified
blocked_missing_contract
blocked_missing_hardware
blocked_missing_observability
blocked_missing_authorization
blocked_network_unreachable
blocked_model_or_cache_incompatible
blocked_transport_unqualified
blocked_cleanup_incomplete
```

Report independent statuses for static configuration, transport qualification, service readiness, request routing, KV transfer, functional equivalence, lifecycle/cleanup, site recovery, performance workload, and stability baseline.

Aggregate deterministically:

1. `blocked_cleanup_incomplete` wins when any sealed site-baseline item, including pre-existing workloads or package/build state, does not return to baseline.
2. Otherwise report every active blocker and use the earliest workflow blocker as primary.
3. Otherwise `failed_validation` wins when an executed mandatory gate fails.
4. Otherwise `not_verified` applies when any mandatory core gate was not executed.
5. Otherwise `pd_validated` requires static configuration, transport qualification, service readiness, request routing, KV transfer, functional equivalence, lifecycle/cleanup, and applicable site recovery to pass. Performance workload and stability baseline remain independently `pass`, `failed`, `not_requested`, or `not_verified` and do not downgrade core PD validation unless the deployment contract made them mandatory.

## Claim Boundary

- Static configuration, connector handshake, `/health`, HTTP 200, non-empty output, or benchmark completion alone does not prove PD separation or KV transfer.
- A Decode response does not prove which Prefill Worker supplied KV without request-correlated role logs.
- Cross-machine deployment defaults to TCP. `lyp_full` is not cross-machine-qualified by the source guidance.
- `dlccl_direct` is a version-sensitive optional protocol, not a replacement default; require exact-source support, native-extension identity, LYP qualification, and payload-content evidence.
- TCP CPU staging adds device-to-host and host-to-device copies plus pinned-memory pressure; quantify it for the declared workload rather than repeating an unscoped performance claim.
- A proxy without a `/health` route may use listener plus real request evidence; never invent a route or weaken Prefill/Decode health-after requirements.
- Connector names, CLI flags, layouts, ports, and defaults are version-sensitive. Verify actual source and `--help` before execution.
- `--trust-remote-code` is permitted only for an approved, revision-pinned model source.
- PD evidence does not establish Verified vLLM Alignment or general Real DLC Hardware acceptance.

conditional_reference: [MooncakeDLCConnector architecture and transport contracts](references/dlc-adaptation.md)
conditional_reference: [Deployment branches, evidence, and troubleshooting](references/deployment-and-troubleshooting.md)
