---
name: main-to-main-upgrade
description: Upgrade vllm-dlc main toward an exact upstream vLLM full SHA, recover an unknown Verified vLLM Alignment candidate, or perform complete compatibility-impact analysis; do not use for standalone model adaptation, environment rebuild, single-operator diagnosis, independent compile work, release branch management, or smoke-only requests.
---

# Main-to-Main Upgrade

shared_contract: vllm-dlc-contract/v1

Use this stable read-only, no-finalize workflow to plan one upstream alignment change. A tag is lineage metadata only; the target identity is a full SHA. Model Adaptation is the only model-specific child feedback seam.

1. Validate target, branch, shared contract, history, approved assets, hardware allocation, observability, and the read-only repository boundary. Complete when: each identity is unique or one stable preflight blocker records an exact resume point without modifying vllm-dlc.
2. Recover the baseline in evidence-confidence order from historical mandatory evidence, an explicit pin requiring revalidation, then a correlated candidate requiring revalidation. Complete when: exactly one Verified vLLM Alignment has complete mandatory evidence, or the baseline remains unknown with `blocked_missing_verified_alignment`.
3. Classify the complete old-to-target upstream delta as affected dependency, new dependency candidate, or confirmed irrelevant. In each v1 delta row's existing evidence, record the source owner, consumers, change kind, cross-repository pairing, and validation owner. Exact-HEAD static absence can establish a source gap; whether it is necessary for a target workload remains a validation assignment until exact-artifact runtime evidence returns. Code present with mismatched schema, descriptor, DLC Custom Kernel binary, toolchain, or native stack is pairing impact, not source absence. Complete when: history is complete, every changed surface has exactly one v1 classification, evidence names its owner and validation assignment, and unknown impact count is zero.
4. Produce the Patch Import Manifest impact report without applying it. Use only the v1 `future_add`, `future_update`, `future_remove`, or `no_change` action vocabulary; distinguish source change, schema/descriptor adapter, artifact pairing only, or no change in the existing reason. Complete when: every affected dependency and new candidate has one valid future action, applied changes are empty, and manifest state is reported unchanged.
5. Build unique mandatory DeepSeek real-weight TP=2 and Llama real-weight TP=1 assignments; keep DeepSeek TP=1 diagnostic-only. Map each Step 3 runtime validation assignment to the existing v1 `expected_dependency_ids`; if no mandatory child can own it, preserve it as not verified. Complete when: parent, child run, target, candidate, model, deployment, and expected dependency identities are unique and closed, and every validation assignment is mapped or explicitly not verified.
6. Delegate model-specific incompatibility one-way to Model Adaptation and consume only its sealed v1 handoff chain. Complete when: run spec, result, gate, parent, child, target, candidate, model, deployment, result digest, expected dependency IDs, and returned changed dependency identities agree exactly; v1 identity closure alone does not establish runtime necessity.
7. Aggregate mandatory child evidence conservatively. A source gap becomes a demonstrated necessary fix only when the mapped child returns eligible sealed evidence for that dependency and a bounded diagnosis reaches the assigned failure boundary; because v1 has no separate necessity-verdict field, any ambiguous or absent verdict remains not verified. Complete when: each validation assignment and mandatory child has a terminal state, and any failed, blocked, not verified, Dummy, fake-server, DLCsim, static, ambiguous, or otherwise acceptance-ineligible evidence stops the parent.
8. Report freeze and finalize eligibility without changing metadata. Complete when: tested revision uniqueness, evidence freshness, and commit authorization are explicit while alignment remains unchanged, manifest remains report-only, and finalize action remains none.

conditional_reference: [Main-to-Main stable decisions](knowledge.md)

## Stop Semantics

- Missing target, contract, approved asset, hardware, or observability stops with the corresponding stable `blocked_*` reason.
- A branch mismatch stops as `blocked_branch_mismatch`; this candidate never creates release, RC, or per-commit branches.
- Missing verified baseline stops as `blocked_missing_verified_alignment`; checkout, installation metadata, README, and time correlation are clues only.
- Incomplete Git history stops as `blocked_incomplete_upstream_history`; unknown impact stops as `blocked_unresolved_compatibility_impact`.
- A changed surface with unknown owner, pairing, or validation impact remains `blocked_unresolved_compatibility_impact`; an old patch missing verbatim from main is not evidence that the target workload needs it.
- Child identity or digest mismatch is rejected as an invalid contract; a child blocker is propagated without weakening it.
- Any requested source, manifest, alignment, test, generated metadata, or repository write stops as `blocked_read_only_boundary`.
- A non-unique tested revision, stale evidence, or absent commit authorization stops before finalize. This candidate never commits or finalizes.

Real weights, Real DLC Hardware, Chunked Prefill runtime, and DLC Runtime dispatch remain `not_verified` unless eligible sealed evidence exists. Publication only makes this workflow discoverable; it does not broaden Ticket 06 operational evidence.
