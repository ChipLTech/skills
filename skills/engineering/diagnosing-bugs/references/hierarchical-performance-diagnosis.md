# Hierarchical Performance Diagnosis

Load this reference for performance regressions that cross nested application, framework, runtime, communication, or device-execution boundaries.

## 1. Seal The Workload

Record code/package/runtime/model identities, hardware/topology, deployment profile, input/output policy, batch, concurrency, request rate/count, sampling, warm-up, attempts, metrics, and the regression threshold. Establish correctness and liveness assertions alongside performance. Complete when the exact workload can be repeated without relying on an informal command history.

## 2. Separate Measurement Profiles

Maintain two append-only profiles:

- **Uninstrumented profile**: the baseline and final performance authority.
- **Diagnostic profile**: profiler, events, synchronization, blocking, debug logs, or temporary wrappers used to close timing boundaries.

Record the exact profile diff. Diagnostic measurements can rank and localize boundaries; they cannot establish the uninstrumented result. Complete when every number names its profile and no diagnostic-only number is presented as production performance.

## 3. Localize Top-Down

Start at end-to-end latency or throughput, then deepen only the slowest confirmed boundary:

```text
request / scheduler
-> model or application forward
-> block / layer
-> stage
-> framework wrapper / unified operation / backend
-> runtime, copy, queue, synchronization, or collective
-> device operation / kernel
```

Not every path reaches a kernel; host scheduling, materialization, conversion, and waiting are valid terminal hotspots. Complete when the slowest boundary is the smallest one supported by current evidence, not merely the lowest-level event visible in a profiler.

## 4. Reconcile Adjacent Boundaries

For each parent and child interval, record inclusive/exclusive semantics and synchronization placement. Compare the parent total with covered non-overlapping child intervals. A stable residual means the work sets or wait attribution differ; test duplicate execution, preprocessing/postprocessing, materialization, layout conversion, asynchronous completion, queueing, collectives, and timer-definition errors as separate hypotheses.

A residual that resembles one child cost is a clue, not proof of duplication. Complete when every material discrepancy is explained by evidence or retained as unresolved.

## 5. Bind Hotspots To Execution Identity

For each suspected operation retain parent call, invocation count, cumulative/mean/distribution timing, input/output shape, dtype, stride/layout, rank/device, and execution phase such as prefill/decode. For layout, view, alias, or materialization candidates, also retain source/destination contiguity, storage identity, storage offset, and logical view relationship when observable; a shared storage identity does not establish identical logical Tensor semantics. Operation or kernel names alone are insufficient because the same implementation may serve multiple paths and shapes. Complete when the candidate cost is attributable to one declared workload path.

## 6. Audit Work Ownership

Check that adjacent layers assign one owner to cache/state updates, allocation/materialization, layout conversion, quantization/dequantization, collectives, and fused work. Declared capability or ownership must match actual invocation behavior. A model/backend-specific flag is evidence for that exact identity, not a universal setting.

## 7. Verify One-Variable Causality

Change one variable and verify three axes:

1. Correctness and state/cache semantics.
2. Invocation count and parent/child ownership contract.
3. Target-stage and end-to-end performance.

Remove temporary synchronization, logging, blocking, and wrappers, then rerun the sealed uninstrumented workload. Stability or regression claims require the declared repeated attempts and dispersion summary. Complete when the causal claim is bounded to executed evidence and instrumentation is absent from the final run.
