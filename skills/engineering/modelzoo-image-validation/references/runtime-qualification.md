# Runtime Qualification

Load this reference before creating a validation container or executing C1a/C1b/model/benchmark gates.

## Ordinary Daily Base

Require immutable Image ID, repo digest when available, non-model-specialized provenance, clean task container identity, original package inventory, and pre-launch process/port/device/HBM baseline. A tag is provenance, not immutable identity.

Task-owned offline dependency bundles, clean source archives, and built extensions are permitted when their source/hash and later build-context equivalence are recorded. Existing model-specific aliases, plugins, caches, servers, or acceptance claims are not inherited.

## C1a And C1b

Use `dlc-env-setup` for C1a package/import origins and fresh-process C1b allocation, H2D, nontrivial operation, synchronize, D2H, and correctness. Invoke C1b separately for each requested logical device, then run simultaneous/collective probes required by the deployment profile.

## Functional Gate

Bind exact model assets, profile, alias, and server epoch. Preserve health-before, model list, at least two orthogonal deterministic assertions, raw requests/responses, HTTP/completion/non-empty/semantic results, finish reason/token count when observable, corruption/repetition checks, health-after, and process identity.

Any assertion failure blocks benchmark and delivery. CPU Reference is diagnostic only.

## Benchmark Gate

Declare dataset/corpus digest, endpoint, model alias, functional/benchmark profile diff, token policy, request count/rate/concurrency, seed, sampling, timeout, warm-up, and formal attempts. Preserve CLI help, raw logs, structured results, actual token distributions, request success, throughput/latency metrics, Peak concurrent requests, and health-after.

`benchmark_workload_pass` requires the declared workload to complete. `benchmark_stability_baseline_pass` additionally requires declared repeated attempts and a dispersion summary.

## Failure And Cleanup

Each retry is a new append-only epoch with one changed variable. Stop only task-owned processes after rechecking identity. Completion is task process/port/handle/HBM delta returning to the sealed baseline or tolerance; a shared Host need not return to global zero.
