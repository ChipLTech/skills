---
name: model-adaptation
description: Adapt a specific new or incompatible model for loading or serving on the DLC Platform; use for model-level Attention, MLA, MoE, quantization, multimodal, MTP, or distributed compatibility, not upstream alignment, environment rebuilds, single-operator debugging, independent compile work, or running an existing smoke alone.
---

# Model Adaptation

shared_contract: vllm-dlc-contract/v1

Use this stable workflow for one approved model and deployment profile. It may consume a one-way Main-to-Main parent assignment, but it does not recover, update, finalize, or claim Verified vLLM Alignment.

1. Run preflight over approved model weights, revisions, tokenizer and applicable processor, deployment, repository, contract, hardware requirement, and external artifact identities. Complete when: every required identity is unique and available, or one stable blocker and resume point has been emitted before execution.
2. Build the closed-world capability matrix for text generation, Attention, MLA, MoE, quantization, multimodal, distributed, MTP, tokenizer, processor, and model-specific paths. Complete when: every capability is required, resolved conditional, or evidence-backed not applicable, with no unknown or unresolved path.
3. Inventory compatibility dependencies reachable by the target model. Complete when: every required or active conditional capability maps to a traceable upstream, vllm-dlc, or DLC Runtime compatibility dependency and no unrelated work is included.
4. Select the smallest compatibility action and derive TP from the approved weights, model configuration, dtype, quantization, device capacity, and deployment profile. Complete when: the action is traceable to the inventory and the TP decision contains all six evidence classes without inheriting a fixed regression profile.
5. Prepare the real-weight branch and delegate API and lifecycle behavior exclusively to the shared runner contract. When Real DLC Hardware executes, require the runner to delegate the SMI Observation Envelope to `dlc-hardware-observability` without treating it as model acceptance. Complete when: the sealed run spec and result identities agree, every runner-owned gate and observation point has a terminal state, and unexecuted Real DLC Hardware, Chunked Prefill, or DLC Runtime evidence remains not verified.
6. Enter the optional Dummy branch only after a sealed real-weight failure and explicit user approval. Complete when: any Dummy result is diagnostic only, acceptance-ineligible, and cannot produce a passed real-weight or Real DLC Hardware handoff.
7. Seal the result and optional parent-child handoff without changing global alignment. Complete when: run, target, candidate, model, deployment, result, parent, and changed-dependency identities close exactly, child status is propagated, and no Verified vLLM Alignment claim is made.

conditional_reference: [Model Adaptation stable decisions](knowledge.md)

## Stop Semantics

- Missing or ambiguous approved assets stop as `blocked_missing_asset` and resume from model assets.
- Insufficient deployment devices stop as `blocked_missing_hardware` and resume from hardware allocation.
- Repository branch mismatch stops as `blocked_branch_mismatch` before modification.
- Missing or unsupported shared contracts stop as `blocked_missing_contract`.
- Missing request-level or DLC Runtime observations stop as `blocked_missing_observability`.
- A required capability limited to a forbidden execution path stops as `blocked_unsupported_execution_path`.
- A sealed runner assertion failure stops as `failed_assertion`; it is never rewritten as a preflight blocker or downgraded through Dummy.
- Any destination or action that would modify the ticket's read-only vllm-dlc repository stops as `blocked_read_only_boundary`.

Fake-server, Dummy, DLCsim, and static evidence are never real-weight or Real DLC Hardware acceptance. Publication only makes this workflow discoverable; it does not broaden Ticket 06 operational evidence.
