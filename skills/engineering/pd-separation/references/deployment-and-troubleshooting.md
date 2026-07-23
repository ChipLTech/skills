# PD Deployment And Troubleshooting

Use this reference after the deployment contract is fixed. Replace every placeholder with recorded values; do not inherit source-document paths, IPs, model names, TP counts, or ports as universal defaults.

## Authorization Boundary

Read-only health checks may observe device state, link state, process ownership, ports, firmware status, and logs. The following are separate Host-maintenance actions and require explicit authorization, a maintenance window, affected-owner checks, rollback, and vendor-approved instructions:

- Writing Chip ID, loading or unloading the kernel module, HBM repair, Bluejay/firmware initialization, LYP initialization that changes state, or PCIe generation reconfiguration.
- Killing processes not proven task-owned, reclaiming another workload's device memory, rebooting, or starting privileged containers with Host PID/network/system mounts.

Do not reproduce a broad process-name kill on a shared Host. Identify task process group, owner, container, command, and device allocation first. If abnormal exit leaves memory allocated, stop at `blocked_cleanup_incomplete` unless Host maintenance is explicitly authorized.

Before authorized Host maintenance, seal every pre-existing workload's PID/PGID, container, device, HBM/frequency, port, model identity, full launch command, health probe, and minimal functional request. Also seal installed package identities, source checkouts, temporary worktrees, native extensions, and runtime overlays introduced by install/build authorization. Device-limited maintenance flags may still trigger global process cleanup, driver work, or container recreation; tool naming is not an impact guarantee.

## Deployment Contract

Record this matrix before launch:

| Item | Prefill | Decode | Proxy |
|---|---|---|---|
| Host/container epoch | required | required | required |
| Routable address | required | required | client-facing |
| Visible devices | required | required | none |
| TP/PP/EP/DCP | required | required | none |
| API port | required | required | required |
| Side-channel base/range | required | required | none |
| Store base/range | for qualified LYP | for qualified LYP | none |
| TransferEngine ports | for TCP | for TCP | none |
| Transport-only gate | endpoint A + physical/local device | endpoint B + physical/local device | none |
| Model/cache profile | required | compatible | request alias |
| Connector role | `kv_producer` | `kv_consumer` | route target |
| Readiness capability | actual role route/probe | actual role route/probe | actual route, listener, or real request |
| Recovery target | pre-existing workloads and Host state | pre-existing workloads and Host state | client-facing route |

Role profiles normally share model weights/tokenizer, dtype, quantization, block size, cache dtype/layout, context semantics, and connector implementation. Document and validate every exception. TP comes from the approved model/deployment profile, not an example.

## Read-Only Preflight

1. Qualify and capture the official `cltech_smi` through `docs/chipltech-smi-observation-contract.md`; preserve raw output and normalized `before_launch` evidence for device health, allocations, holders, and capacity.
2. Run the approved LYP/RDMA/link test and operator smoke for each declared device group; retain output and pass criteria without generalizing one group to another.
3. Confirm `DLC_VISIBLE_DEVICES` and `CHIPLTECH_VISIBLE_DEVICES` mapping and ensure co-located Prefill/Decode sets do not overlap.
4. Verify TP and all distributed dimensions against visible devices and the model profile.
5. Verify model/tokenizer paths, filesystem visibility, package imports, source identities, and server/launcher `--help`.
6. Confirm API ports, every `side_channel_base + tp_rank`, every applicable `store_base + tp_rank`, and discovered TransferEngine ports are free to bind.
7. Validate routes and firewall policy with an approved temporary probe when available. Test the exact advertised service endpoints from each peer namespace after launch. Loopback is valid only when both endpoints intentionally share that namespace.
8. Inspect every readiness route from actual source or route listing. A Proxy may omit `/health`; declare listener plus a real routed request as its probe rather than inventing a route.

Proceed only when every required check has an explicit result.

## Launch Skeleton

Construct commands from actual `--help`. The documented shape is:

```bash
python3 -m mooncake.pd_launcher \
  --visible-devices <ROLE_DEVICE_LIST> \
  --mooncake-protocol <tcp|lyp_full|dlccl_direct-if-supported> \
  --lyp-store-host <DECLARED_STORE_HOST> \
  --lyp-store-port <DECLARED_STORE_BASE> \
  --side-channel-port <ROLE_SIDE_CHANNEL_BASE> \
  -- \
  --host <ROLE_BIND_ADDRESS> \
  --model <ABSOLUTE_MODEL_PATH> \
  --tensor-parallel-size <ROLE_TP> \
  --port <ROLE_API_PORT> \
  --kv-transfer-config '<CHECKED_CONNECTOR_JSON>' \
  <DECLARED_COMMON_AND_ROLE_ARGUMENTS>
```

Use producer JSON on Prefill and consumer JSON on Decode. Quote JSON as one shell argument. Bind addresses and advertised addresses are different concerns: `0.0.0.0` may bind a service but is not a peer destination. Exposing unauthenticated APIs on `0.0.0.0` requires a trusted network or source-restricted firewall.

Launch order:

1. Prefill and its transport/store master.
2. Decode after the protocol-specific prerequisite is ready.
3. Proxy after both role probes are ready.
4. Deterministic client request through Proxy.

For protocol-specific launch prerequisites and lazy initialization evidence, follow [DLC adaptation](dlc-adaptation.md). For cross-machine deployment, use TCP unless a separate qualification explicitly establishes another path.

## Evidence Ladder

1. Launcher logs show intended device visibility, protocol, side-channel, and forwarded vLLM arguments.
2. Prefill and Decode show correct connector roles; eager transports also show initialization, while lazy initialization is declared deferred.
3. All declared capability-derived readiness probes pass in the same recorded server epochs.
4. Proxy routes one deterministic request to the intended roles.
5. Prefill retains/registers the request's blocks.
6. Decode requests matching remote request and block identities.
7. Any deferred transport initialization, transport completion, and DLC-side KV receipt/synchronization are recorded; Decode's local request joins the Prefill request through `remote_request_id` or an equivalent exact identity.
8. Response satisfies the deterministic assertion and health remains good.
9. Stop/cleanup returns task processes, ports, and device memory to baseline, and normalized `after_cleanup` closes against `before_launch`.

Only step 7 closes KV transfer. Health and HTTP response remain separate evidence.

## Troubleshooting By Earliest Failure

### Role does not start

- Compare launcher environment with the contract.
- Check visible-device mapping, TP, model path, package/source identity, device/link/operator preflight, and all rank-derived ports.
- Distinguish server import failure, engine initialization, model load, distributed initialization, and connector initialization.

### Decode does not receive KV

- Verify Proxy targets and server epochs.
- Join local and remote request IDs across both roles.
- Check Prefill block retention/registration and Decode block IDs.
- Validate advertised host from the Decode namespace; reject loopback/container-private addresses across machines.
- Confirm both sides use the same connector generation and compatible cache contract.

### TCP transfer fails

- Confirm both roles selected `tcp` and initialized CPU staging.
- Check pinned allocation/memlock, registration lengths, TransferEngine RPC/handshake reachability, firewall, and container network.
- Verify offset calculations against actual block dimensions and tensor lengths.
- Inspect logs for unintended RDMA topology discovery/transport installation. CQ allocation or RNIC failure under protocol `tcp` means the exact TransferEngine build did not provide a TCP-only path.
- Do not switch to direct device-memory RDMA as an unqualified workaround.

### `lyp_full` blocks

- Confirm Prefill started first and owns the intended store master; start Decode after the store listener appears, not after Prefill HTTP readiness.
- Confirm equal TP, matching store host/base, every rank-derived store port, protocol, transfer order, shapes, and tags.
- Check DLCCL/LYP health, device selection, synchronization, and peak gathered-buffer memory.
- If both sides reach matching `send().wait()` / `recv().wait()` and hang, run the same device pair through a content-validating transport-only gate before changing connector metadata.

### `dlccl_direct` fails

- Confirm the exact connector parser implements `dlccl_direct`; do not combine a main connector with an extension from another branch without a reviewed compatibility contract.
- Record extension SHA/build command, Python ABI, linked `libdlccl`, physical visible devices, and process-local `device=0` mapping.
- Run the native benchmark in separate producer/consumer processes and require content validation.
- Distinguish communicator init failure from send/receive completion failure and request-layer metadata failure.

### LYP initialization or repair fails

- Read the timestamped LYP log, not only the wrapper summary. Check whether reset scripts actually executed; a script inside a recreated image/container may remain non-executable despite a Host-side `chmod`.
- Treat extracted indexes as tool-scope indexes until mapped to physical devices. A back-group local index is not automatically the same physical device number.
- Re-run read-only group status after initialization or repair. Record front/back or exact pair scope; never promote one passing group to whole-Host health.
- Power cycle, Bluejay/HBM work, driver reload, and reboot require Host-maintenance authorization and trigger the full recovery contract.

### Output diverges

- Re-run the equivalent monolithic deterministic request.
- Compare tokenizer/model identities, prompt tokens, decoding parameters, cache layout/dtype/block mapping, and first divergent token/logits.
- Delegate model-specific Attention/MLA/MoE/MTP/quantization behavior to `model-adaptation` after PD routing and transfer are proven.

### Performance regresses

- Separate queueing, Prefill compute, KV copy/transfer, Decode compute, and client overhead.
- Compare identical warm-up and formal workloads, concurrency, context/output lengths, and server epochs.
- For TCP, include both DLC-to-CPU and CPU-to-DLC copies; for `lyp_full`, include gather/scatter and DLCCL synchronization.

## Cleanup

Stop Proxy, Decode, then Prefill using task-owned process identities. Allow graceful termination before a task-scoped forced kill. A stopped `docker exec` client does not prove the process in a Host-PID container exited; inspect PID/PGID, listener, and device ownership directly. Recheck ports, process groups, HBM allocation, frequency/link state, package/source/build state, and pre-existing workloads against baseline. Remove temporary wheels, extensions, worktrees, and overlays unless the contract declares them retained deliverables. Restore disrupted services from the sealed launch contract and validate model identity plus a real request. Driver reload, Chip ID write, HBM/firmware/LYP state changes, PCIe downgrade, and reboot are Host-maintenance escalation, never automatic cleanup.
