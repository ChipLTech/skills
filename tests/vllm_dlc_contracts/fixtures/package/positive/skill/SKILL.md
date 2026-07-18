---
name: fixture-model-adaptation
description: Adapt a specified model for the DLC Platform when model compatibility work is required.
---

shared_contract: vllm-dlc-contract/v1

1. Read the shared contract when its branch is reached. Complete when: the identity is resolved.

conditional_reference: [knowledge pointer](../knowledge.md)
2. Validate evidence. Complete when: every mandatory gate has a terminal state.

## Stop Semantics

Stop with `blocked_missing_asset` when approved assets are unavailable.
