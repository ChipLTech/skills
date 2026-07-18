---
name: main-to-main-upgrade
description: Upgrade vllm-dlc main toward an exact upstream vLLM full SHA, recover an unknown Verified vLLM Alignment candidate, or perform complete compatibility-impact analysis; do not use for standalone model adaptation, environment rebuild, single-operator diagnosis, independent compile work, release branch management, or smoke-only requests.
---

# Main-to-Main Upgrade

shared_contract: vllm-dlc-contract/v1

Use this stable read-only, no-finalize workflow to plan one upstream alignment change. A tag is lineage metadata only; the target identity is a full SHA. Model Adaptation is the only model-specific child feedback seam.

1. Validate target, branch, shared contract, history, approved assets, hardware allocation, observability, and the read-only repository boundary. Complete when: each identity is unique or one stable preflight blocker records an exact resume point without modifying vllm-dlc.
2. Recover the baseline in evidence-confidence order from historical mandatory evidence, an explicit pin requiring revalidation, then a correlated candidate requiring revalidation. Complete when: exactly one Verified vLLM Alignment has complete mandatory evidence, or the baseline remains unknown with `blocked_missing_verified_alignment`.
3. Classify the complete old-to-target upstream delta as affected dependency, new dependency candidate, or confirmed irrelevant. Complete when: history is complete, every changed surface has exactly one classification, and unknown impact count is zero.
4. Produce the Patch Import Manifest impact report without applying it. Complete when: every affected dependency and new candidate has a future action, applied changes are empty, and manifest state is reported unchanged.
5. Build unique mandatory DeepSeek real-weight TP=2 and Llama real-weight TP=1 assignments; keep DeepSeek TP=1 diagnostic-only. Complete when: parent, child run, target, candidate, model, deployment, and expected dependency identities are unique and closed.
6. Delegate model-specific incompatibility one-way to Model Adaptation and consume only its sealed v1 handoff chain. Complete when: run spec, result, gate, parent, child, target, candidate, model, deployment, result digest, and changed dependency identities agree exactly.
7. Aggregate mandatory child evidence conservatively. Complete when: each mandatory child has a terminal state and any failed, blocked, not verified, Dummy, fake-server, DLCsim, static, or otherwise acceptance-ineligible evidence stops the parent.
8. Report freeze and finalize eligibility without changing metadata. Complete when: tested revision uniqueness, evidence freshness, and commit authorization are explicit while alignment remains unchanged, manifest remains report-only, and finalize action remains none.

conditional_reference: [Main-to-Main stable decisions](knowledge.md)

## Stop Semantics

- Missing target, contract, approved asset, hardware, or observability stops with the corresponding stable `blocked_*` reason.
- A branch mismatch stops as `blocked_branch_mismatch`; this candidate never creates release, RC, or per-commit branches.
- Missing verified baseline stops as `blocked_missing_verified_alignment`; checkout, installation metadata, README, and time correlation are clues only.
- Incomplete Git history stops as `blocked_incomplete_upstream_history`; unknown impact stops as `blocked_unresolved_compatibility_impact`.
- Child identity or digest mismatch is rejected as an invalid contract; a child blocker is propagated without weakening it.
- Any requested source, manifest, alignment, test, generated metadata, or repository write stops as `blocked_read_only_boundary`.
- A non-unique tested revision, stale evidence, or absent commit authorization stops before finalize. This candidate never commits or finalizes.

Real weights, Real DLC Hardware, Chunked Prefill runtime, and DLC Runtime dispatch remain `not_verified` unless eligible sealed evidence exists. Publication only makes this workflow discoverable; it does not broaden Ticket 06 operational evidence.
