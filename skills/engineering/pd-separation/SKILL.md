---
name: pd-separation
description: Deploy or diagnose vLLM-DLC Prefill/Decode separation with MooncakeDLCConnector; use for single-node TCP or lyp_full, cross-machine TCP, Prefill/Decode/Proxy startup, KV-transfer lifecycle, routing, and PD-specific health or transfer failures.
---

# Prefill/Decode Separation

Establish a request-correlated Prefill/Decode (PD) deployment. Service readiness is only a startup signal; completion requires evidence that the intended Prefill Worker produced KV Cache and the intended Decode Worker consumed it.

## Inputs

- Exact vLLM, vllm-dlc, mooncake-dlc, PyTorch DLC Backend, and model identities.
- Topology: `single_node_tcp`, `single_node_lyp_full`, or `cross_machine_tcp`.
- Prefill, Decode, and Proxy hosts, routable addresses, device sets, TP, and ports.
- Model, tokenizer, dtype, quantization, KV layout/cache dtype, block size, context, and role-specific vLLM arguments.
- Artifact directory and authorization for network, install/build, device execution, privileged Host integration, and Host maintenance as separate actions.

Missing topology, model/cache compatibility, routable endpoint, required hardware, or authorization is a blocker. Device execution never authorizes process eviction, `--privileged`, Host PID namespace, Host system mounts, driver reload, firmware/Chip ID/HBM operations, PCIe reconfiguration, or reboot.

## Workflow

1. Freeze the deployment contract before launching. Record full source/package identities, model asset identity, both role profiles, connector/module identity, transport, endpoint and port matrix, request parameters, expected evidence, cleanup baseline, and explicit exceptions to role symmetry. Read installed `pd_launcher`, proxy, and vLLM `--help`; source examples never override the checked-out implementation. **Complete when:** every identity and endpoint is fixed, or a structured blocker names the exact missing input.
2. Establish a monolithic serving baseline for the same model and equivalent deterministic request. Delegate environment repair to `dlc-env-setup`; delegate model-specific Attention, MLA, MoE, quantization, MTP, KV-layout, TP, or DCP compatibility to `model-adaptation`. **Complete when:** the baseline passes with raw evidence, or its failure is isolated outside PD orchestration.
3. Qualify the declared devices and links without changing Host state. Confirm no task-owned stale process remains, device sets are disjoint when co-located, TP matches each visible set, required API/side-channel/store/RPC ports are free to bind, and the peer network path/firewall permits the planned connections. Test the exact service endpoints from the peer after launch. **Complete when:** both roles have a clean observed baseline, every planned port is free, and network-policy or temporary-probe evidence has a pass/fail result.
4. Select one supported transport branch from [DLC adaptation](references/dlc-adaptation.md). Default to `tcp`; use `lyp_full` only for an explicitly qualified same-host DLC P2P topology. Treat legacy `lyp` as diagnostic-only and `rdma_direct` as unavailable unless the exact implementation and driver capability independently prove support. **Complete when:** both roles use one compatible protocol and its memory, store, synchronization, and port requirements are closed.
5. Launch Prefill, then Decode, then Proxy according to [Deployment and troubleshooting](references/deployment-and-troubleshooting.md). Set device visibility, protocol, and side-channel variables before importing vLLM or spawning workers. Use `kv_producer` for Prefill and `kv_consumer` for Decode. **Complete when:** separate server epochs and logs show the intended launcher environment, connector role, transport initialization, and all three health endpoints are ready.
6. Run one deterministic request through Proxy before concurrency or benchmark work. Correlate client, Proxy, Prefill, and Decode request identities; retain Prefill block ownership/registration, Decode KV pull, transfer completion, successful receive, response, health-after, and device/process observations. **Complete when:** request-correlated evidence proves routing and KV transfer, output meets the declared functional assertion, and both role epochs remain healthy.
7. Expand one variable at a time through lifecycle, concurrency, long-context, and performance checks. Measure TTFT, TPOT, ITL, throughput, queueing, and KV-transfer cost separately; compare against the declared monolithic workload without claiming causality from a single sample. **Complete when:** each requested workload has raw results, role logs, health-after, and an explicit `pass`, `failed`, or `not_verified` state.
8. Diagnose failures by phase: identity/config, startup, connector/control plane, metadata/request correlation, KV layout/block mapping, transport, Decode cache availability, functional divergence, performance, or cleanup. Change one variable per failure epoch and never replace real transfer evidence with readiness or HTTP success. **Complete when:** the earliest failing phase is bounded and the next probe or blocker is reproducible.
9. Stop Proxy, Decode, then Prefill and clean only task-owned resources. Compare processes, ports, and device memory with the sealed baseline; escalate Host maintenance separately when cleanup cannot be achieved safely. **Complete when:** task resources return to baseline or `blocked_cleanup_incomplete` records the residual owner, impact, and authorized resume action.

## Public States

```text
pd_validated
failed_validation
not_verified
blocked_missing_contract
blocked_missing_hardware
blocked_missing_authorization
blocked_network_unreachable
blocked_model_or_cache_incompatible
blocked_cleanup_incomplete
```

Report independent statuses for static configuration, service readiness, request routing, KV transfer, functional equivalence, lifecycle/cleanup, performance workload, and stability baseline.

Aggregate deterministically:

1. `blocked_cleanup_incomplete` wins when task resources do not return to baseline.
2. Otherwise report every active blocker and use the earliest workflow blocker as primary.
3. Otherwise `failed_validation` wins when an executed mandatory gate fails.
4. Otherwise `not_verified` applies when any mandatory core gate was not executed.
5. Otherwise `pd_validated` requires static configuration, service readiness, request routing, KV transfer, functional equivalence, and lifecycle/cleanup to pass. Performance workload and stability baseline remain independently `pass`, `failed`, `not_requested`, or `not_verified` and do not downgrade core PD validation unless the deployment contract made them mandatory.

## Claim Boundary

- Static configuration, connector handshake, `/health`, HTTP 200, non-empty output, or benchmark completion alone does not prove PD separation or KV transfer.
- A Decode response does not prove which Prefill Worker supplied KV without request-correlated role logs.
- Cross-machine deployment defaults to TCP. `lyp_full` is not cross-machine-qualified by the source guidance.
- TCP CPU staging adds device-to-host and host-to-device copies plus pinned-memory pressure; quantify it for the declared workload rather than repeating an unscoped performance claim.
- Connector names, CLI flags, layouts, ports, and defaults are version-sensitive. Verify actual source and `--help` before execution.
- `--trust-remote-code` is permitted only for an approved, revision-pinned model source.
- PD evidence does not establish Verified vLLM Alignment or general Real DLC Hardware acceptance.

conditional_reference: [MooncakeDLCConnector architecture and transport contracts](references/dlc-adaptation.md)
conditional_reference: [Deployment branches, evidence, and troubleshooting](references/deployment-and-troubleshooting.md)
