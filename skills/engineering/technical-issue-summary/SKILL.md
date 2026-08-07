---
name: technical-issue-summary
description: Compress a closed technical diagnosis into a one- or two-sentence Sprint update, Issue title or summary, owner note, or evidence-linked handoff conclusion. Use when the user asks to summarize, briefly introduce, or explain a diagnosed technical issue across teams.
---

# Technical Issue Summary

Turn closed diagnostic evidence into a short, accurate explanation. This skill compresses evidence; it does not diagnose the failure or promote an inference into a root cause.

## Inputs

- The diagnostic report, Issue, logs, handoff, conversation, or artifact paths to summarize.
- The target format: Sprint update, Issue title, Issue summary, owner note, or handoff conclusion. Infer it from the request when clear; otherwise default to a one-sentence cross-team summary.
- The target audience and any length limit stated by the user.

## Workflow

### 1. Bind the evidence

Extract these five slots without filling gaps from plausibility:

| Slot | Required meaning |
|---|---|
| Object | Workload, model, service, operator, or user path affected |
| Scenario | Operation and conditions under which it fails |
| Mechanism | Component, first abnormal boundary, and abnormal action or state |
| Quantification | Reproducible size, count, latency, memory, error rate, or other measured change |
| Impact | User-visible OOM, crash, hang, wrong output, or slowdown |

For each slot, classify the source as `established`, `current boundary`, or `unknown`. Preserve exact source, package, image, binary, workload, and device identities in the supporting detail when they affect the claim, even if they do not fit in the final sentence.

If the material does not establish the user's actual symptom or a current boundary, state that limitation and summarize only the observation. Route unresolved diagnosis to `diagnosing-bugs`; do not manufacture a complete sentence by guessing.

### 2. Separate cause from context

Classify the evidence before writing:

- **Direct cause**: the first mechanism that creates the wrong scale, value, contract, or state.
- **Contributing factor**: the ABI, layout, architecture, or design constraint that makes the mechanism possible.
- **Trigger**: the model, input, shape, threshold, concurrency, or environment condition that exposes it.
- **Propagation**: the later layer that reports or surfaces the failure.

Name the direct cause only when established. A trigger is the affected object, not automatically the owner; a propagation layer is the symptom boundary, not automatically the cause.

### 3. Close every number

Use a number only when it can be recomputed from bound evidence or reproduced by the cited measurement. For tensor memory, verify shape product, dtype bytes, physical layout, alignment, and amplification. For performance, use the original workload after diagnostic instrumentation is removed.

If the number does not close, omit it or label it as an observation with its uncertainty. Never reverse-engineer a unique cause from an OOM size or latency sample alone.

### 4. Select the output form

**Cross-team or Sprint summary**

> `<object>` 在执行 `<scenario>` 时，`<component>` 在 `<boundary>` 发生 `<mechanism>`，导致 `<quantified change>`，最终触发 `<user-visible impact>`。

Use one sentence, or two when a verified workaround or next owner is useful. Remove source symbols, full call stacks, hashes, and experiment history from the sentence; keep an evidence link or path alongside it.

**Issue title**

```text
[component/object] <operation> at <boundary> causes <abnormal cost/state> and <impact>
```

**Issue summary**

> `<workload>` reliably triggers `<symptom>` under `<operation and conditions>`. Evidence establishes that `<mechanism>` first occurs in `<component/boundary>`, producing `<quantified change>`; `<control>` excludes `<competing layer>`, so `<owner/action>` should evaluate `<direction>`.

**Owner note**

> Evidence shows `<logical state/amount>` becomes `<physical state/amount>` during `<adaptation step>` and fails `<before launch/during execution/at synchronization>`. Please confirm whether this contract is required or whether `<candidate direction>` is valid.

Phrase unconfirmed ownership or repair directions as confirmation requests, not conclusions.

**Handoff conclusion**

Lead with the short conclusion, then preserve the red command, identities, minimal repro, controls, falsified hypotheses, first abnormal boundary, quantitative calculation, fix or workaround validation, artifact paths, next owner, and Claim Boundary. A handoff is not constrained to one sentence.

### 5. Translate and audit

Replace internal helper names and incidental stack detail with the component, phase, action, and consequence they prove. Keep a symbol or source location only when the target is an engineering owner who needs it.

Before returning, verify:

- A reader outside the investigation can understand the first sentence.
- All five slots are present, or missing slots are explicitly bounded.
- The trigger is not mislabeled as the owner.
- The propagation layer is not mislabeled as the direct cause.
- Every number closes against evidence.
- No unverified assertion is phrased as fact.
- Detailed evidence remains traceable through a path, Issue, or artifact reference.

## Chipltech Branch

For a Chipltech-Family Accelerator, DLC Platform, DLC Ecosystem, PyTorch DLC Backend, DLC Runtime, or Real DLC Hardware issue, load `chipltech-context` and use the knowledge-base topic `debugging-workflows/technical-issue-summary.md`. Its terminology, component-owner table, evidence boundaries, and Claim Boundary are authoritative for this branch.

Use `dlc-hardware-observability` when device, HBM, process, link, or cleanup claims require query-only evidence. Do not use a model name, DLC Runtime allocation error, kernel driver OOM, or a DLC Custom Kernel name in a stack as sufficient owner evidence by itself.

## Completion Criterion

The run is complete when the requested output form is concise enough for its audience, every factual clause maps to bound evidence, uncertainty is visible, and the supporting evidence remains independently traceable.

## Claim Boundary

This skill establishes the wording of a technical summary, not the truth of unverified diagnostic claims. It cannot replace reproduction, identity binding, source inspection, runtime or hardware observation, semantic correctness checks, performance validation, or owner confirmation.
