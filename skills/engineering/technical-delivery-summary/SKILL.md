---
name: technical-delivery-summary
description: Distill completed technical work into an audience-ready one-sentence delivery summary. Use for cross-team updates, review updates, daily reports, release summaries, or multi-repository implementations when the reader needs the delivered capability rather than implementation detail.
---

# Technical Delivery Summary

Turn implementation and validation evidence into one sentence about the capability delivered. This skill summarizes successful technical work; use `diagnosing-bugs` for unresolved failures and `technical-issue-summary` for closed diagnoses.

## Inputs

- The implementation report, diff, commits, tests, review notes, conversation, or artifact paths to summarize.
- The audience and intended channel, when stated.
- Any required length, terminology, or scope constraint.

Infer missing presentation preferences from the request. Do not infer missing delivery evidence.

## Workflow

### 1. Bind the delivery state

Classify each claimed state before drafting:

| State | Minimum evidence |
|---|---|
| Implemented | The capability exists in identified source changes or artifacts |
| Integrated | Required component boundaries are connected in identified source changes |
| Validated | The stated checks passed against the identified implementation or artifact |
| Merged | The identified change was accepted into its target branch |
| Released | The identified change was published, deployed, or otherwise made available to its intended consumers |

These states are independent evidence dimensions, not a maturity ladder. Record every state material to the requested claim, then choose a verb that names only the dimension being summarized. Build success does not establish runtime validation; historical validation does not transfer to a changed artifact; merge does not establish release; release does not establish validation.

### 2. Extract the capability spine

Reduce the material to these slots:

| Slot | Required meaning |
|---|---|
| Object | The operator, service, workflow, user path, or system that gained the capability |
| Behavior | What it can now do |
| Basis or condition | The runtime input, environment, policy, or scenario governing the behavior, when material |
| Outcome | The user-, operator-, or system-visible result |
| Delivery state | The independently established implementation, integration, validation, merge, or release state relevant to this sentence |

The **capability spine** is `delivery state + object + behavior + material basis/condition + outcome`. It describes the delivered behavior across component boundaries without narrating those boundaries.

### 3. Choose the reader's abstraction level

Translate repository and symbol detail into domain behavior:

- Replace API names, integer strategies, helper names, descriptor fields, and call sequences with the behavior they jointly enable.
- Name a technical term when the audience needs it to identify the capability; add a short functional gloss when the term is ambiguous outside its owning team.
- Keep a decision basis such as topology, payload, policy, or workload only when it explains what makes the capability distinctive.
- Keep safety or fallback behavior only when it is part of the externally important guarantee.
- Move repository scope, implementation ownership, test matrices, and evidence paths to an optional supporting sentence or note.

### 4. Draft one sentence

Default form:

> `<delivery-state verb>` `<object>` to `<behavior>` based on `<material basis/condition>`, resulting in `<outcome>`.

Natural-language order may change. Prefer one finite main claim and roughly 15-35 words when the user gives no limit. Do not force an empty slot into the sentence.

Useful variants:

**Capability-first**

> Implemented `<object>` support for `<behavior>` based on `<basis>`, enabling `<outcome>`.

**Validation-first**

> Validated that `<object>` `<behavior>` under `<conditions>`, with `<result>`.

**Release-first**

> Released `<capability>` for `<object>`, enabling `<audience>` to `<outcome>`.

If repository scope matters, append one separate sentence:

> The integration spans `<components or repositories>`.

### 5. Run the subtraction test

Remove each clause in turn:

- If removing it changes what was delivered, why it matters, or the established delivery state, keep it.
- If removing it only hides how the implementation works, move it to supporting detail.
- If a reader could mistake the object for a model, algorithm, repository, or component, clarify its domain role.
- If a term is opaque to the target audience, replace it with its function or pair it with a short gloss.

Then audit the final claim:

- Every factual clause maps to identified evidence.
- The delivery verb matches the evidence dimension being claimed and does not hide another material state.
- The sentence describes one capability, not a chronological work log.
- Cross-repository plumbing is compressed into end-to-end behavior.
- No internal identifier is carrying meaning that a domain term should carry.
- Limitations material to the reader remain visible in a short qualifier or supporting note.

## Output

Return:

1. The one-sentence summary.
2. An optional scope or evidence note only when needed to prevent overclaiming or satisfy the request.

Do not return the extraction worksheet or multiple alternatives unless the user asks for the derivation or variants.

## Chipltech Branch

For Chipltech-Family Accelerator, DLC Platform, DLC Ecosystem, PyTorch DLC Backend, DLCCL, or Real DLC Hardware work, load `chipltech-context` and use the knowledge-base topic `foundation/technical-delivery-summary.md`. The configured knowledge base's terminology and Claim Boundary are authoritative for this branch.

Preserve distinctions among source implementation, build evidence, DLC Runtime execution, Real DLC Hardware validation, model acceptance, performance evidence, and release. A cross-repository implementation may be summarized as one end-to-end capability, but its evidence does not become stronger through compression.

Unlike the generic output, every Chipltech result has exactly two required parts:

1. One summary sentence.
2. One literal `Claim Boundary:` line naming every material unproved dimension.

Prefer “source 中已实现” over bare “支持” when evidence is source-only. `scripts/format-delivery-summary.py` provides the deterministic delivery-verb seam. This wording workflow does not create a Qualification Artifact.

## Completion Criterion

The run is complete when a reader outside the implementation can state what capability changed and why it matters after reading one sentence, every clause is evidence-bound, and removing any remaining implementation detail would change the claim rather than merely shorten it.

## Claim Boundary

This skill establishes wording, not delivery truth. It cannot replace source inspection, build or test execution, exact artifact identity, runtime or hardware validation, semantic correctness checks, performance measurement, review, merge, deployment, or release evidence.
