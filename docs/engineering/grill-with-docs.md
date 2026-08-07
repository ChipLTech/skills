Quickstart:

```bash
npx skills add mattpocock/skills --skill=grill-with-docs
```

```bash
npx skills update grill-with-docs
```

[Source](https://github.com/mattpocock/skills/tree/main/skills/engineering/grill-with-docs)

## What it does

`grill-with-docs` interviews you about a plan or design until you and the agent share one understanding of it, and writes the vocabulary and the hard decisions into your repo while it does. It is the same round-based interview [grill-me](https://aihero.dev/skills-grill-me) runs, pointed at a codebase — which makes it **stateful**: a term gets resolved and lands in `CONTEXT.md` the moment it resolves, and a decision that passes three gates (hard to reverse, surprising without context, a real trade-off) lands as an ADR under `docs/adr/`.

Its own `SKILL.md` is a thin wrapper that delegates: [grilling](https://aihero.dev/skills-grilling) supplies the interview, [domain-modeling](https://aihero.dev/skills-domain-modeling) supplies the writing. Installing `grill-with-docs` alone gets you a skill that does not work — both dependencies must be present.

It operates on the **active business workspace's project context**. A separately configured Chipltech knowledge-base `CONTEXT.md` is external read-only authority, not an implicit write target.

## When to reach for it

You invoke this by typing `/grill-with-docs` — the agent won't reach for it on its own.

Reach for it at the start of a change, in a repo, when the plan is still fuzzy and the words for the thing are not settled. If you're not working in a working directory, use [grill-me](https://aihero.dev/skills-grill-me) — it runs the same interview statelessly. If the effort is too big to hold in one session, use [wayfinder](https://aihero.dev/skills-wayfinder). If a decision is blocked on knowledge in someone else's head, use [to-questionnaire](https://aihero.dev/skills-to-questionnaire).

## It's working if

- Questions come in rounds across the currently unblocked decision frontier — not one at a time, and never asking you for facts the agent could look up itself.
- Resolved terms land in `CONTEXT.md` inline, and qualifying decisions land as ADRs — both created lazily, with nothing scaffolded up front.
- `CONTEXT.md` stays a glossary and nothing else.

## Where it fits

`grill-with-docs` is the head of the main **idea → ship** flow — the single-session planning step that sharpens an idea before it becomes a [spec](https://aihero.dev/skills-to-spec) and [tickets](https://aihero.dev/skills-to-tickets). When you're unsure which skill or flow fits, [ask-matt](https://aihero.dev/skills-ask-matt) routes you.
