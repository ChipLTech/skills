# 06P1 - Future authoritative runtime observability and trusted attestation

**What to build:** In future work, add repository-owned, production-authenticated instrumentation and services that can emit complete, request-correlated Real DLC Hardware acceptance evidence without relying on logs, static inference, or producer self-claims.

**Blocked by:** Repository ownership outside the current skills-only boundary and a future decision to pursue the stronger Real DLC Hardware acceptance class.

**Status:** future-out-of-scope

This issue is not a blocker for the revised Ticket 06 Real DLC Hardware
operational regression. Operational evidence must not claim that this future
work has been completed.

## Required producer capabilities

- Bind a runner-originated random request nonce to the vLLM external and scheduler request identities before execution.
- Emit request-level prefill chunk start/completion events, chunk indices, and token counts that close against the sealed tokenizer proof.
- Emit authenticated generation start/end and contiguous sequence evidence for every expected TP/PP rank and worker generation.
- Emit explicit dropped-event, overflow, incomplete-record, and stream-end counters; acceptance requires zero loss and no sequence gap.
- Bind DLC Platform, PyTorch DLC Backend, and DLC Runtime dispatch events to the same request, process, rank, stream, and execution campaign.
- Bind DeepSeek operations to matching DLCCL collective identities and LYP transport completion across all required ranks.
- Bind dense Llama Attention and generation operations to the same request identity.
- Emit authoritative Triton JIT/kernel invocation and execution counters, including authenticated zero observations over a complete observation interval.
- Emit authoritative `torch.compile` and Dynamo invocation, capture, compile, and compiled-execution counters, including authenticated zero observations over a complete observation interval.
- Provide a trusted Real DLC Hardware attestor that binds hardware, runtime, process incarnation, rank, stream, atomic device allocation, and privacy-safe device references.
- Provide atomic endpoint and device lease acquire, renew, verify, fence, and release operations.

## Current feasibility evidence

- vLLM propagates scheduler request IDs and per-request scheduled token counts, but no runner nonce mapping producer exists.
- Existing vLLM-DLC profiler scopes are aggregate and do not provide request-correlated rank generation closure.
- DLCSynapse has internal event identities, but standard exports omit required sequence/completeness fields and can omit incomplete records without a sealed loss count.
- DLCCL exposes rank and collective sequence information, but no existing producer joins it to a DeepSeek request and LYP operation.
- Existing dense Attention and generation call chains do not emit request-correlated role evidence.
- DLC Platform replaces `torch.compile` with an identity path; no authoritative complete Triton or Dynamo non-execution producer was found.
- `chipltech_smi_lib` can query diagnostic hardware state, memory, firmware, process occupancy, and selected link information, but it has no lease authority, signed producer identity, trusted time, revocation, runtime-stream binding, privacy-safe stable identity, atomic snapshot, or closed-world attestation output.

## Repository boundary

Instrumentation changes must be owned and approved in the repository that owns each signal. Ticket 06 and skills-owned 06P must not patch vLLM, vllm-dlc, PyTorch DLC Backend, DLCSynapse, DLC Runtime, DLC Custom Kernel, DLCCL, or `chipltech_smi_lib` to bypass this prerequisite.

## Acceptance criteria

- [ ] Every required signal has a versioned producer interface and bounded no-model or minimal probe.
- [ ] Every producer has a distinct authorized production role credential and a separate fixture trust root.
- [ ] Request, process, rank, stream, challenge, nonce, lease, policy, profile, subject, and campaign identities close cryptographically.
- [ ] Complete observation has explicit start/end, expected participants, contiguous sequence, and zero-drop/overflow proof.
- [ ] Production signing capability is unavailable to repository fixtures and test processes.
- [ ] Hardware and endpoint allocation are atomic, fenced, renewable, and verifiably released.
- [ ] Raw host, device, process, and network identifiers are excluded from persisted evidence by an approved allowlist policy.
- [ ] Independent security and operational reviews have no unresolved finding.

## Stop semantics

- Static source paths, package presence, HTTP success, TP configuration, full tensor dumps, free-form logs, and missing log strings do not satisfy this prerequisite.
- A query-only SMI tool without authenticated allocation and runtime binding remains qualification-only.
- If any producer can only self-report trust or completeness in JSON, production acceptance remains blocked.
