# Kernel CSV Export

Use this branch after a DLCSynapse profile run has already produced a `.log` or
`.ansi` launch log. It is log post-processing, not profile acquisition.

Run:

```bash
python3 <SKILL_ROOT>/scripts/export-dlc-kernel-csv.py \
  <ARTIFACT_DIR>/syn_<PID>.ansi \
  --tool /home/xuansun/llama2-fine-tune/tool.py \
  --output-dir <ARTIFACT_DIR>/kernel-summary
```

The exporter loads the supplied `tool.py` parser and writes only `operators.csv`
from its launch metrics. It deliberately produces no text summary, image, or
manifest file. Both total and average time use the `tool.py` frequency, fixed at 1400
MHz; a tool with another `F` value is rejected. Do not use `table.py`'s 1500 MHz
`Total Time` conversion for this workflow.

The CSV is sorted by total cycles and contains kernel name, calls, total cycles,
cycle percentage, total/average time, ops, average/max GFLOPS, bytes,
average/max bandwidth, crt cycles, average crt time, and `clock_mhz`. Preserve
The command result binds the source log, tool, and CSV by SHA-256 and records
launch/kernel counts and the 1400 MHz basis; retain that stdout beside the task's
existing evidence record when those identities are needed.

Before comparing two CSV files, bind both logs to the same workload, source,
package, image, rank/device mapping, profile configuration, warm-up, and
diagnostic epoch. A kernel aggregate has no request, layer, rank, device, shape,
or causal attribution unless separate evidence supplies it. Empty parse results
fail closed instead of emitting an empty CSV.

Claim Boundary: `operators.csv` is a diagnostic DLCSynapse launch-log summary.
It can rank parsed kernel cost within one captured log;
they do not prove formal benchmark performance, production latency, root cause,
or model correctness.
