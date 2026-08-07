Quickstart:

```bash
npx skills add mattpocock/skills --skill=domain-modeling
```

```bash
npx skills update domain-modeling
```

[Source](https://github.com/mattpocock/skills/tree/main/skills/engineering/domain-modeling)

## What it does

`domain-modeling` is the *active* discipline of building and sharpening a project's domain model — challenging fuzzy terms, resolving overloaded words, stress-testing domain relationships with concrete scenarios, and writing the glossary and decisions down the moment they crystallise. Resolved terms land in the active project's `CONTEXT.md`; decisions that are hard to reverse, surprising without context, and the result of a real trade-off land as ADRs under `docs/adr/`. Both files are created lazily.

It operates on the **active business workspace's project context**. A separately configured Chipltech knowledge-base `CONTEXT.md` is external, read-only authority selected through `/chipltech-context`, not an implicit project file.

## When to reach for it

The agent reaches for it automatically when another skill needs the domain model maintained — `/grill-with-docs` drives it, and `/improve-codebase-architecture` uses it to keep the model current while decisions crystallise. Reach for it directly when the *words* are the problem: you need to pin down domain terminology, resolve an overloaded term, or record an architectural decision.

## It's working if

- A term that conflicts with the existing glossary is called out immediately, not silently absorbed.
- Resolved terms are written to `CONTEXT.md` inline, the moment they resolve — not batched at the end.
- `CONTEXT.md` stays a glossary and nothing else: no implementation details, no spec, no scratch notes.
- ADRs are offered only when all three gates pass — hard to reverse, surprising without context, a real trade-off.
- It never edits the Chipltech knowledge root without explicit knowledge-maintenance authorization.

## Where it fits

`domain-modeling` is a **reach-for-it-anytime standalone** and the vocabulary layer beneath the engineering skills, sitting beside [codebase-design](https://aihero.dev/skills-codebase-design) — one owns the domain's words, the other owns the module's shape. When you're unsure which skill or flow fits, [ask-matt](https://aihero.dev/skills-ask-matt) routes you.
