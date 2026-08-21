---
name: chipltech-context
description: Route Chipltech tasks with cited engineering knowledge.
metadata:
  hermes:
    category: engineering
    tags: [chipltech, knowledge, routing, evidence]
    requires_toolsets: [file, skills]
    config:
      - key: chipltech_kb.path
        description: Absolute path to the Chipltech engineering knowledge base.
        prompt: Chipltech knowledge-base path
      - key: chipltech_skills.path
        description: Absolute path to the Chipltech skills repository.
        prompt: Chipltech skills repository path
---

# Chipltech Context

Establish the Chipltech-Family Accelerator domain context, retrieve authoritative repository evidence, and route the request to an approved business contract and execution Skill. This is a read-only retrieval and routing workflow; it does not replace the owning execution Skill or turn repository text into runtime Evidence.

## When To Use

- A task concerns the Chipltech-Family Accelerator, DLC Platform, DLC Ecosystem, PyTorch DLC Backend, DLC Runtime, vLLM-CL, model qualification, or related engineering work.
- The answer must use the team's formal terminology or cite the engineering knowledge base.
- The correct business prompt or execution Skill is not yet known.

## Inputs

- The user's task or question.
- `chipltech_kb.path` and `chipltech_skills.path` from Skill config.
- The actual code or runtime workspace, which remains separate from the knowledge-base root.
- The execution locus for each supplied path or command: Host or exact Docker container, plus any Host-to-container mount mapping.

## Workflow

1. Establish the execution locus before resolving a path. Treat a path identity as `locus + absolute path`; `/work/...` paths in DLC business contracts are Docker container coordinates unless the contract explicitly declares a Host locus. Use the query-only `scripts/execution_locus.py` classifier when a path's namespace or container availability could be confused. Record the exact container identity and Host-to-container mount mapping when crossing namespaces. Host absence of a container-only path is `blocked_missing_container_contract`, not repository or model absence, and a lookalike Host path is not a substitute.
2. Resolve both configured roots within their declared locus to readable absolute paths. Confirm the knowledge root contains `CONTEXT.md` and `README.md`, and the skills root contains `skills/`. If no configured path is usable, perform query-only discovery in the same locus. Multiple plausible roots without a unique authority stop as `blocked_ambiguous_knowledge_root` or `blocked_ambiguous_skills_root`.
   Repository-aware qualification uses the injectable `scripts/repository_guard.py` and requires the supplied path to equal the Git top-level root. Artifact-only validators do not invoke this guard and do not assume `/work/vllm-cl` or any other fixed checkout path. A validator whose fixture paths target a Docker container must run in that container or report/skip the missing container precondition; it must not classify Host lookup failure as a product validation failure.
3. Read `<KNOWLEDGE_BASE_ROOT>/CONTEXT.md` and `<KNOWLEDGE_BASE_ROOT>/README.md`. Adopt their formal terminology, component boundaries, source-of-truth policy, and maintenance rules before interpreting the task.
   Treat `vllm-cl` as the current repository and Distribution and `vllm_cl` as its Python package. Old `vllm-dlc` or `vllm_dlc` tokens are historical aliases only when an original pre-rename artifact explicitly contains them; never generate them for a current checkout, command, URL, identity field, or import.
4. For capability discovery, task routing, or an unclear owner, read `<KNOWLEDGE_BASE_ROOT>/prompt-examples/all-supported-capabilities-quickstart.md` as the canonical catalog of supported task entrypoints. Select its linked detailed Prompt, Contract, or Runbook; never execute from the catalog alone or treat catalog coverage as execution Evidence.
5. Classify the request by problem domain. Search repository-relative filenames, headings, and content before reading broadly. Prefer the relevant topic document, then the nearest applicable case study, then the selected approved contract under `prompt-examples/`.
6. For every substantive domain claim, cite a repository-relative path plus heading or line range. Label the basis as one of: `direct repository evidence`, `runtime observation`, `inference`, or `missing evidence`. Never upgrade one class into another.
7. Check whether candidate sources conflict, are explicitly historical, or make different claims for different versions. If authority cannot be resolved from repository rules and current identities, stop as `blocked_conflicting_authority` and name the conflicting sources.
8. Route execution to the narrowest approved Skill. Before naming its blocker or Claim Boundary, actually load it through the active Harness and read its scope, negative scope, Inputs, completion criteria, Stop Semantics, and Claim Boundary. Never infer an owner Skill's current contract from this routing table alone or copy its instructions into the answer.
9. Keep the execution workspace unchanged. The knowledge base supplies rationale and contracts; the current business/code repository and task-owned artifact directory supply execution and Evidence.
10. Return the selected knowledge paths, business contract, execution Skill, first executable action, execution locus and mount assumptions, authorization needs, expected terminal states, and Evidence boundary. When routing to an execution Skill or reporting a terminal blocker, include a literal `Claim Boundary:` label followed by what is and is not established. For knowledge-only questions, return the cited answer without invoking an execution Skill.

### Generic Skill Boundary

- `domain-modeling`, `grill-with-docs`, and `wait-what` use the active business workspace's project context. `<KNOWLEDGE_BASE_ROOT>/CONTEXT.md` remains Chipltech knowledge context and is not an implicit write target.
- `codebase-design` supplies generic module and interface vocabulary; `grilling` supplies interview mechanics; `to-questionnaire` collects human-held decisions; `wizard` packages authorized human-only procedures; `writing-for-agents` improves agent-facing documents. None replaces an owning DLC Skill or relaxes its Evidence, authorization, Stop Semantics, or Claim Boundary.
- If the active project context and configured knowledge context resolve to the same path, report that fact and remain read-only unless the user explicitly authorizes a knowledge-base contribution workflow.
- Skill discovery in Claude, Kilo, Codex, or Hermes proves availability only. It is not business execution or runtime Evidence.

## Routing Guide

| Request | Knowledge entry | Execution Skill |
| --- | --- | --- |
| Workstation rebuild or package/runtime repair | `runtime-debugging/`, `debugging-workflows/` | `dlc-env-setup` |
| Built-in PyTorch DLC Backend to PrivateUse1 plugin migration | `prompt-examples/pytorch-dlc-plugin-migration-prompts.md` | `pytorch-dlc-plugin-migration` |
| Query-only device, HBM, process, link, or cleanup evidence | `runtime-debugging/chipltech-smi-observability.md` | `dlc-hardware-observability` |
| One model's loading or serving compatibility | `vllm-cl/model-adaptation-and-main-to-main-decisions.md` | `model-adaptation` |
| Local-model qualification or DLC/TYD image delivery | `vllm-cl/modelzoo-driven-dlc-tyd-image-contract.md` | `modelzoo-image-validation` |
| Prefill/Decode separation | `vllm-cl/prefill-decode-separation.md` | `pd-separation` |
| Exact upstream vLLM SHA alignment | `vllm-cl/model-adaptation-and-main-to-main-decisions.md` | `main-to-main-upgrade` |
| Hard bug | Relevant topic and nearest case study | `diagnosing-bugs` |
| Model-serving performance regression | `runtime-debugging/performance-profiling.md` and nearest performance case study | `diagnosing-bugs` |
| Profile artifact completeness or trace-track breakdown | `runtime-debugging/performance-profiling.md` | `diagnosing-bugs` |
| Model distributed/MoE collective compatibility | `vllm-cl/distributed-collective-qualification.md` | `model-adaptation` |
| Completed technical delivery needing a one-sentence cross-team summary | `foundation/technical-delivery-summary.md` | `technical-delivery-summary` |
| Closed diagnosis needing a short cross-team explanation | `debugging-workflows/technical-issue-summary.md` | `technical-issue-summary` |

The table is a starting map, not a substitute for reading the current repository and Skill scopes.

If performance diagnosis demonstrates a model/backend compatibility defect, route the smallest compatibility action to `model-adaptation`; diagnosis remains owned by `diagnosing-bugs`. Qualification or image-delivery benchmarks remain owned by `modelzoo-image-validation`.

## Stop Semantics

- `blocked_ambiguous_knowledge_root`: more than one plausible knowledge root exists and authority is not unique.
- `blocked_ambiguous_skills_root`: more than one plausible skills root exists and authority is not unique.
- `blocked_missing_container_contract`: a required Docker container, container identity, or mount mapping is unavailable; no claim is made about the corresponding Host or business asset.
- `blocked_missing_knowledge`: required authoritative material is absent or unreadable.
- `blocked_conflicting_authority`: applicable sources conflict and repository rules or current identities do not resolve them.
- `blocked_missing_skill`: the required execution Skill cannot be uniquely discovered and loaded.
- `blocked_missing_repository`: a required source repository cannot be uniquely discovered for `dlc-env-setup`.
- `not_supported_by_repository_evidence`: the knowledge base does not support the requested claim.

## Claim Boundary

- Repository text can support domain definitions, documented procedures, and historical case evidence; it cannot prove the current Host, package, model, DLC Runtime, transport, or Real DLC Hardware state.
- Package/import evidence, C1b, query-only SMI observation, model correctness, request-correlated KV transfer, and performance evidence remain distinct.
- A business prompt is a task contract, not proof that its steps ran.
- Session history and memory are navigation aids, not acceptance records.
- Do not write back to the knowledge or skills repositories under this read-only workflow. Use a separately authorized contribution workflow after Evidence and claim boundaries are closed.
