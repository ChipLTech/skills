# Matt Pocock Skills

A collection of agent skills (slash commands and behaviors) loaded by Claude Code. Skills are organized into buckets and consumed by per-repo configuration emitted by `/setup-matt-pocock-skills`.

## Language

**Issue tracker**:
The tool that hosts a repo's issues — GitHub Issues, Linear, a local `.scratch/` markdown convention, or similar. Skills like `to-tickets`, `to-spec`, and `triage` read from and write to it.
_Avoid_: backlog manager, backlog backend, issue host

**Issue**:
A single tracked unit of work inside an **Issue tracker** — a bug, task, spec, implementation ticket, or decision ticket.

**Implementation ticket**:
A tracer-bullet slice produced by `to-tickets`, declaring the work it delivers and its blocking edges. Once introduced in a workflow, "ticket" may be used as shorthand when it cannot be confused with a **Decision ticket**.

**Decision ticket**:
A `wayfinder` unit — a child **Issue** of a `wayfinder:map` holding a *question* whose resolution is a decision, not an **Implementation ticket** to execute. The **decision** qualifier distinguishes the two ticket types.

**Triage role**:
A canonical state-machine label applied to an **Issue** during triage (e.g. `needs-triage`, `ready-for-afk`). Each role maps to a real label string in the **Issue tracker** via `docs/agents/triage-labels.md`.

## Relationships

- An **Issue tracker** holds many **Issues**
- An **Issue** carries one **Triage role** at a time
- An **Implementation ticket** is an **Issue** produced by `to-tickets`
- A **Decision ticket** is an **Issue** (a child of a `wayfinder:map`)

## Context Boundaries

**Project context** is the `CONTEXT.md` belonging to the active business or code workspace. Generic skills may read it and, when their contract permits, update it.

**Chipltech knowledge context** is the configured knowledge base's `CONTEXT.md`. It is selected through `chipltech-context`, remains read-only unless a contribution workflow is explicitly authorized, and does not become runtime Evidence.

The two contexts must not be conflated based on filename alone. `domain-modeling`, `grill-with-docs`, and `wait-what` operate on project context; Chipltech execution and Evidence boundaries remain owned by the narrow DLC skills.

## Execution Locus Boundaries

**Execution locus** identifies the namespace in which a command, absolute path, process, or artifact exists. Chipltech model execution and runtime-dependent tests normally use a declared Docker container locus; the Host normally orchestrates containers and stores mounted sources/artifacts.

A path identity is `execution locus + absolute path`, not the path string alone. `/work/vllm`, `/work/vllm-cl`, `/work/chipltech-knowledge-base`, and `/work/skills` are container coordinates unless the active contract explicitly declares a Host locus. Host absence of a container coordinate is an unmet test harness/container precondition, not evidence that the business repository or asset is missing.

Relate Host and container paths only through an explicit mount mapping that records container identity, source, destination, mode, and relevant content identity. Before running a path-bound validator, establish its execution locus. If its required container contract is unavailable, skip or return a precise container-precondition blocker; do not run it against lookalike Host paths or report a product failure.

## Flagged ambiguities

- "backlog" was previously used to mean both the *tool* hosting issues and the *body of work* inside it — resolved: the tool is the **Issue tracker**; "backlog" is no longer used as a domain term.
- "backlog backend" / "backlog manager" — resolved: collapsed into **Issue tracker**.
