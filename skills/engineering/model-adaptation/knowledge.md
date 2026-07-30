# Model Adaptation Stable Decisions

shared_contract: vllm-dlc-contract/v1

Model Adaptation owns capability analysis and the smallest traceable compatibility decision for one explicit model. Main-to-Main owns upstream alignment, baseline recovery, global impact analysis, and finalization. Delegation flows from Main-to-Main to Model Adaptation and sealed evidence flows back; the child never invokes or assumes parent ownership.

TP is a model-specific deployment decision derived from approved weights, model configuration, dtype, quantization, capacity, and the target profile. Fixed regression TP values are not defaults for arbitrary models.

The shared contract owns API, lifecycle, Chunked Prefill, and DLC Runtime behavior evidence. This package names their evidence states but does not reproduce their executable assertions. Dummy is available only after sealed real-weight failure and explicit approval, remains diagnostic-only, and cannot contribute to acceptance.

Exact Ticket 06 v12 Model Adaptation completed operational regression with `authoritativeness: operational_only`, `acceptance_eligible: false`, alignment unchanged, and finalization `none`. That evidence does not establish Real DLC Hardware acceptance, Verified vLLM Alignment, request-correlated Chunked Prefill, DLC Runtime dispatch, DLCCL/LYP execution, a specific Attention implementation, Triton non-execution, compile/Dynamo non-execution, or rank-to-device allocation. New targets require their own sealed evidence. Model Adaptation does not recover, update, finalize, or claim Verified vLLM Alignment.

For serving runtime failures, the target boundary is the sealed lifecycle stage and exact symptom, not merely process failure. HTTP 500, worker cancellation, Engine death, and cleanup warnings may be consequences of an earlier asynchronous DLC Custom Kernel failure. Graph/speculative/MTP diagnosis must preserve scheduler state, actual Graph dispatch size, final worker environment, and one-variable deltas. Blocking or debug configuration that creates an initialization or weight-load stall has not reproduced a decode failure and cannot identify its cause. Resolve the detailed procedure through `chipltech-context` at `runtime-debugging/runtime-troubleshooting.md`; this skill owns only the gate.

Performance diagnosis is owned by `diagnosing-bugs`. Model Adaptation may consume a bounded diagnosis only after it demonstrates a model/backend compatibility mismatch for an exact workload and preserves correctness, execution ownership, and uninstrumented scope. Instrumented timing improvement is not a stable performance baseline, Real DLC Hardware acceptance, or Verified vLLM Alignment; a backend flag observed in one source identity is not a universal capability rule.

## Campaign-Derived Diagnostic Gates

For a stable wrong-output symptom, use an ordered seam diagnosis: loaded-weight integrity, deterministic synthetic fused-op checks, rank-local operations, TP collectives one at a time, one-variable diagnostic probes, real-model Model-Site Dump comparison, then a same-family cross-model comparison. Seal the workload and change one variable per epoch. The first material divergence identifies a boundary to minimize; it does not establish that boundary as the sole cause.

Synthetic input can falsify a catastrophic single-op hypothesis but cannot replace real-model intermediates. A smaller same-family model passing in the same environment can falsify a platform-global failure hypothesis, but it supplies only supporting evidence for a model-depth or scale hypothesis. Model Adaptation must preserve that distinction between confirmed issue, falsified hypothesis, and unverified cause.

The Qwen3-32B Block-256 campaign confirmed a reproducible BF16 DLCCL `o_proj` all-reduce divergence while a CPU collective probe failed to repair the end symptom. Treat collective source identity, dtype, shape, rank order, and replay equivalence as required evidence; do not generalize one source identity into a universal DLCCL rule. Resolve the authoritative case study through `chipltech-context` at `case-studies/qwen3-32b-dlc-block256-diagnosis.md` instead of duplicating its environment-specific commands here.

## Hermes Execution Boundary

In the recorded campaign profile, five Hermes oneshot invocations completed without executing required tools. This is operational evidence for that profile, not a universal Hermes capability claim. Execution-mandatory Real DLC Hardware work must use a tool path that produces observable operations and retained evidence. Run each model in an independent tracked process, preserve logs and results under the task artifact root, and keep Hermes oneshot limited to read-only analysis when tool execution cannot be demonstrated.
