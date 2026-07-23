# MooncakeDLCConnector Adaptation

Use this reference when selecting a transport, checking KV Cache compatibility, reading connector code, or interpreting PD lifecycle logs. These observations were derived from internal guidance for `mooncake-dlc` main and are version-sensitive; confirm them against the exact checkout.

## Connector Contract

The documented DLC connector is `MooncakeDLCConnector` in `mooncake.mooncake_connector_dlc_v1`. Prefill declares `kv_role=kv_producer`; Decode declares `kv_role=kv_consumer`. The vLLM KV Connector V1 split remains:

- Scheduler: matched-token accounting, allocation-state updates, connector metadata, and request-finished lifecycle.
- Worker: KV Cache registration, send/receive, and transport initialization.
- `remote_request_id`: maps Decode-local request identity to the Prefill-side request identity.

Treat class names, module paths, callback names, and metadata fields as checked-source facts, not durable API.

## Import-Before-Spawn Rule

`pd_launcher` must set the following before importing vLLM and before worker spawn:

| Launcher input | Documented environment |
|---|---|
| `--visible-devices` | `DLC_VISIBLE_DEVICES`, mirrored to `CHIPLTECH_VISIBLE_DEVICES` |
| `--mooncake-protocol` | `VLLM_MOONCAKE_PROTOCOL` |
| `--lyp-store-host` | `MOONCAKE_LYP_STORE_HOST` |
| `--lyp-store-port` | `MOONCAKE_LYP_STORE_PORT` |
| `--lyp-debug` | `MOONCAKE_LYP_DEBUG` |
| `--p2p-full-debug` | `MOONCAKE_LYP_FULL_DEBUG` |
| `--side-channel-port` | `VLLM_MOONCAKE_SIDE_CHANNEL_PORT` |
| `--device-offset` | `VLLM_DLC_DEVICE_OFFSET` |
| `--env-KEY VALUE` | task-declared `KEY=VALUE` |

The launcher uses `--` to separate its arguments from vLLM server arguments. Read its actual parser before constructing commands.

## Transport Decision

| Protocol | Data path | Recommended scope | Constraints |
|---|---|---|---|
| `tcp` | DLC KV Cache -> pinned CPU staging -> TransferEngine TCP -> pinned CPU staging -> DLC KV Cache | Default; same-host or cross-machine | Extra copies, pinned-memory capacity, routable advertised host, TransferEngine RPC/handshake connectivity, no unintended RDMA dependency |
| `lyp_full` | DLCCommunicator/DLCCL over LYP, gathered full layer/component tensor | Explicitly qualified same-host P2P | Prefill-first startup, matching TP/store/tag behavior, store port per rank, device-memory peak, DLCCL stability |
| `dlccl_direct` | Package-local native DLCCL send/receive over registered DLC KV descriptors | Exact checkout with native extension; qualified same-host LYP group | Not on every branch; extension/library ABI identity, local device index, communicator init, request serialization, payload-content gate |
| `lyp` | ProcessGroupDLCCL chunked send/recv | Legacy diagnostics only | Deprecated in source guidance; strict rank, store, order, and tag matching |
| `rdma_direct` | Direct device-memory registration | Unsupported by documented environment | Requires independently proven driver/GDR-equivalent capability |

The documented default is `tcp`; `lyp_full` and `dlccl_direct` are optional capability-derived paths, not additional defaults. An optional protocol exists only when the exact checkout parser and connector implement it.

## Transport Qualification Gate

Before loading two model replicas, run the smallest transport-only test available for the selected branch. Preserve exact source/native-library identities, physical visible devices, process-local device indexes, payload size, endpoint/port, timeout, send/receive completion, and content validation.

The gate passes only when:

- Both endpoints initialize concurrently in separate process contexts matching deployment visibility.
- A non-empty payload traverses the intended data path.
- Both send and receive complete within the declared timeout.
- The receiver validates payload content, not only byte count or process exit.
- Processes, ports, and device memory return to the pre-gate baseline.

For a process with `DLC_VISIBLE_DEVICES=<physical-id>`, the only visible device is normally process-local `dlc:0`. Native benchmark `--device` arguments must use the local index unless the exact runtime documents otherwise. Record both physical and local identities.

### TCP Auto-Discovery Guard

Some TransferEngine builds accept protocol `tcp` but still auto-discover HCAs and install RDMA. Treat log markers such as `Auto-discovering topology`, `installTransport, type=rdma`, completion-queue allocation failure, or `No available RNIC` as a TCP implementation/capability failure, not a model failure. A Python import or one successful engine object does not prove two role processes can initialize concurrently.

Do not silently relabel this path as TCP success. Either use an exact build that disables RDMA discovery and installs TCP explicitly, or select another independently qualified protocol.

## TCP CPU-Staging Lifecycle

For each cache tensor, the documented implementation allocates a same-shape, same-dtype pinned CPU buffer, records its address, and registers the CPU memory with TransferEngine. Decode publishes staging addresses and requested block IDs in metadata. Prefill copies selected blocks from DLC KV Cache to its staging buffer, writes corresponding ranges to Decode staging, and signals `TRANS_DONE`. Decode then copies those blocks into its DLC KV Cache and synchronizes through `torch.dlc`.

Review these invariants in code:

- Address and length belong to a live pinned allocation for the entire transfer.
- Block offsets derive from the actual layout and `num_blocks`.
- `index_select`/`index_copy_` or equivalent writes back to the intended tensor rather than a temporary advanced-index tensor.
- Completion means the final DLC-side synchronization has occurred, not only the remote CPU write.
- Pinned-memory capacity and process memlock are sufficient for all cache tensors.

Optional fingerprints may include checksum, absolute maximum, mean, first values, and NaN/Inf counts. They are diagnostics, not proof of full tensor equality.

## KV Cache Layout Contract

The source guidance lists these layouts:

| Layout | Documented shape | Block dimension |
|---|---|---|
| TorchAttention merged | `(num_blocks, num_kv_heads, block_size, head_size * 2)` | `0` |
| TorchAttention non-merged | `(2, num_blocks, num_kv_heads, block_size, head_size)` | `1` |
| SparseMLA | `(num_blocks, block_size, head_size)` | `0` |

For a 5D tensor with `shape[0] == 2`, the documented logic takes `num_blocks=shape[1]`; otherwise it takes `shape[0]`. It derives block size from `shape[-2]` and byte length per block from total bytes divided by block count.

The source simultaneously describes the current cache as 5D non-merged and most operation as merged/unified with `split_k_and_v=False`. Resolve this ambiguity from the exact DLC Attention Backend tensor, connector branch, and vLLM version. Shape coincidence is insufficient: record semantic K/V/component ownership, dtype, stride, and block dimension on both roles.

## LYP Full Lifecycle

The documented `LYPFullTransportManager` gathers selected blocks and sends one flattened contiguous tensor per layer/component. Tags derive from a base plus transfer index. Qualify:

- Matching model layers, components, shapes, dtype, TP rank count, and transfer ordering.
- Unique and concurrency-safe tag assignment.
- Prefill-first TCPStore startup and reachability of `store_base + tp_rank`.
- Correct `torch.dlc` device selection and synchronization.
- Peak memory for gathered layer/component tensors.

`LYPFullTransportManager.initialize()` may block in `TCPStore` before the API server becomes ready. The safe rendezvous sequence is Prefill process start -> observe the declared store listener -> start Decode -> wait for both role readiness. Waiting for Prefill HTTP readiness before starting Decode can consume the store timeout and create a false alternating timeout.

If request IDs, block counts, tensor metadata, tag/order, and both role health states align but `ProcessGroupDLCCL.send(...).wait()` / `recv(...).wait()` never complete, return to the transport-only gate and LYP group state. Do not keep changing request correlation or cache semantics without contradictory evidence.

## Native Direct DLCCL Lifecycle

When the exact branch implements `dlccl_direct`, the documented pattern is:

1. Snapshot ordered KV tensor descriptors: pointer, shape, stride, item size, block dimension, and process-local device index.
2. Decode creates a DLCCL unique ID and sends an init-only control request to Prefill.
3. Prefill starts rank 0 initialization; Decode starts rank 1 after acknowledgement.
4. Prefill sends selected local block IDs through native DLCCL; Decode receives into its declared local block IDs.
5. A per-communicator lock serializes requests unless the exact implementation proves concurrency support.

Require the extension module identity, linked `libdlccl` identity, and branch SHA. A manually built extension is a local qualification artifact, not a published package. Do not claim `dlccl_direct` support for main or another wheel unless that exact source/package contains it.

## Request Lifecycle Evidence

Useful documented markers include:

- Prefill `request_finished` retaining/registering blocks for remote Decode.
- Decode `group_kv_pull` with local and remote request IDs, peer endpoint, and local blocks.
- `receive_kv` with request IDs and selected path.
- Transport-specific send/receive and successful KV receipt.
- Decode `remote_request_id` joining its local request to Prefill, local/remote block counts, and external-cache use when observable.

Preserve enough fields to join client request -> Proxy routing -> Prefill request -> Decode request -> block IDs -> transfer completion. Log strings can change; instrument equivalent state when absent.

## Known Boundaries

- The DLC path uses `torch.dlc`, not upstream `torch.cuda` semantics.
- Cross-machine `get_ip()` may advertise loopback or a container-private address; explicit peer reachability is mandatory.
- TransferEngine RPC/handshake ports are required but were not enumerated by the source; discover them from the actual implementation/configuration.
- Full-layer LYP can increase device-memory peak and expose DLCCL operation stability issues under large caches or concurrency.
- LYP qualification is device-group scoped. A passing back-four group does not establish the front-four group or every pair.
- CPU staging has an architectural copy cost. Any claim that the impact is small needs workload-specific evidence.
