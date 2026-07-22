# PD Deployment And Troubleshooting

Use this reference after the deployment contract is fixed. Replace every placeholder with recorded values; do not inherit source-document paths, IPs, model names, TP counts, or ports as universal defaults.

## Authorization Boundary

Read-only health checks may observe device state, link state, process ownership, ports, firmware status, and logs. The following are separate Host-maintenance actions and require explicit authorization, a maintenance window, affected-owner checks, rollback, and vendor-approved instructions:

- Writing Chip ID, loading or unloading the kernel module, HBM repair, Bluejay/firmware initialization, LYP initialization that changes state, or PCIe generation reconfiguration.
- Killing processes not proven task-owned, reclaiming another workload's device memory, rebooting, or starting privileged containers with Host PID/network/system mounts.

Do not reproduce a broad process-name kill on a shared Host. Identify task process group, owner, container, command, and device allocation first. If abnormal exit leaves memory allocated, stop at `blocked_cleanup_incomplete` unless Host maintenance is explicitly authorized.

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
| Model/cache profile | required | compatible | request alias |
| Connector role | `kv_producer` | `kv_consumer` | route target |

Role profiles normally share model weights/tokenizer, dtype, quantization, block size, cache dtype/layout, context semantics, and connector implementation. Document and validate every exception. TP comes from the approved model/deployment profile, not an example.

## Read-Only Preflight

1. Observe device health, existing allocations, task-owned processes, and available memory.
2. Run the approved LYP/RDMA/link test and operator smoke for each declared device set; retain output and pass criteria.
3. Confirm `DLC_VISIBLE_DEVICES` and `CHIPLTECH_VISIBLE_DEVICES` mapping and ensure co-located Prefill/Decode sets do not overlap.
4. Verify TP and all distributed dimensions against visible devices and the model profile.
5. Verify model/tokenizer paths, filesystem visibility, package imports, source identities, and server/launcher `--help`.
6. Confirm API ports, every `side_channel_base + tp_rank`, every applicable `store_base + tp_rank`, and discovered TransferEngine ports are free to bind.
7. Validate routes and firewall policy with an approved temporary probe when available. Test the exact advertised service endpoints from each peer namespace after launch. Loopback is valid only when both endpoints intentionally share that namespace.

Proceed only when every required check has an explicit result.

## Launch Skeleton

Construct commands from actual `--help`. The documented shape is:

```bash
python3 -m mooncake.pd_launcher \
  --visible-devices <ROLE_DEVICE_LIST> \
  --mooncake-protocol <tcp|lyp_full> \
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
2. Decode after Prefill's required control plane is ready.
3. Proxy after both role health endpoints are ready.
4. Deterministic client request through Proxy.

For `lyp_full`, both roles use the same store host/base and Prefill starts first. For cross-machine deployment, use TCP unless a separate qualification explicitly establishes another path.

## Evidence Ladder

1. Launcher logs show intended device visibility, protocol, side-channel, and forwarded vLLM arguments.
2. Prefill and Decode show correct connector roles and transport initialization.
3. All health endpoints respond in the same recorded server epochs.
4. Proxy routes one deterministic request to the intended roles.
5. Prefill retains/registers the request's blocks.
6. Decode requests matching remote request and block identities.
7. Transport completion and DLC-side KV receipt/synchronization are recorded.
8. Response satisfies the deterministic assertion and health remains good.
9. Stop/cleanup returns task processes, ports, and device memory to baseline.

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
- Do not switch to direct device-memory RDMA as an unqualified workaround.

### `lyp_full` blocks

- Confirm Prefill started first and owns the intended store master.
- Confirm equal TP, matching store host/base, every rank-derived store port, protocol, transfer order, shapes, and tags.
- Check DLCCL/LYP health, device selection, synchronization, and peak gathered-buffer memory.

### Output diverges

- Re-run the equivalent monolithic deterministic request.
- Compare tokenizer/model identities, prompt tokens, decoding parameters, cache layout/dtype/block mapping, and first divergent token/logits.
- Delegate model-specific Attention/MLA/MoE/MTP/quantization behavior to `model-adaptation` after PD routing and transfer are proven.

### Performance regresses

- Separate queueing, Prefill compute, KV copy/transfer, Decode compute, and client overhead.
- Compare identical warm-up and formal workloads, concurrency, context/output lengths, and server epochs.
- For TCP, include both DLC-to-CPU and CPU-to-DLC copies; for `lyp_full`, include gather/scatter and DLCCL synchronization.

## Cleanup

Stop Proxy, Decode, then Prefill using task-owned process identities. Allow graceful termination before a task-scoped forced kill. Recheck ports, process groups, and device memory against baseline. Driver reload, Chip ID write, HBM/firmware/LYP state changes, PCIe downgrade, and reboot are Host-maintenance escalation, never automatic cleanup.
