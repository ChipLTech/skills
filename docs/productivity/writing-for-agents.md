Quickstart:

```bash
npx skills add mattpocock/skills --skill=writing-for-agents
```

```bash
npx skills update writing-for-agents
```

[Source](https://github.com/mattpocock/skills/tree/main/skills/productivity/writing-for-agents)

## What it does

`writing-for-agents` is the reference for writing any document an agent consumes — a skill, an `AGENTS.md` / `CLAUDE.md`, a doc reached by a pointer. The packaging differs; the writing does not: the same levers make each one predictable — the agent taking the same *process* every run, not producing the same output.

Its core ideas:

- **Context pointers** — a reference held in the agent's context that names out-of-context material and encodes the condition for reaching it. The pointer's *wording*, not its target, decides when the agent reaches the material.
- **The two loads** — every document spends **context load** (always-loaded material in the window) or **cognitive load** (the human remembering it exists).
- **Information hierarchy** — steps versus reference, and progressive disclosure down the ladder so the top stays legible.
- **Leading words** — a compact pretrained concept (_tight_, _red_, _tracer bullet_) that anchors a whole region of behaviour in the fewest tokens.
- **Pruning** — single source of truth, relevance, the environment as a lookup, and the no-op test applied sentence by sentence, against sediment and sprawl.

When the document you're writing is a skill, read `SKILL-MECHANICS.md` in the package for frontmatter, invocation choice, and router skills.

## When to reach for it

The agent reaches for it automatically when a task fits — creating or editing skills, modifying `AGENTS.md` or `CLAUDE.md`, or writing a doc an agent will consume. In the Chipltech context, it can improve agent-facing document quality but cannot rewrite approved Prompt, Contract, or Runbook content without separate authorization.

## It's working if

- Every pointer front-loads its leading word, lists one trigger per genuinely distinct branch, and cut identity the body already carries.
- Splitting a document happens only when the cut earns it — by sequence or by invocation.
- Duplication, restatements, and no-ops are hunted sentence by sentence and removed.
- `writing-for-agents` supersedes the retired `writing-great-skills`; the old name no longer appears in the promoted set.

## Where it fits

`writing-for-agents` is a reach-for-it-anytime standalone — the meta-reference you consult while building the rest of the set. It replaced the retired `writing-great-skills` in v1.2. When you're unsure which skill or flow fits, [ask-matt](https://aihero.dev/skills-ask-matt) routes you.
