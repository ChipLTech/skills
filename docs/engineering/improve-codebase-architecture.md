Quickstart:

```bash
npx skills add mattpocock/skills --skill=improve-codebase-architecture
```

```bash
npx skills update improve-codebase-architecture
```

[Source](https://github.com/mattpocock/skills/tree/main/skills/engineering/improve-codebase-architecture)

## What it does

`improve-codebase-architecture` surfaces architectural friction and proposes **deepening opportunities** — refactors that turn shallow modules into deep ones, for testability and AI-navigability.

It is *informed* by the project's domain model and built on a shared design vocabulary: [codebase-design](https://aihero.dev/skills-codebase-design) supplies the architecture terms (module, interface, depth, seam, adapter, leverage, locality), and `CONTEXT.md` plus `docs/adr/` supply the domain language and settled decisions.

**Scope before you scan — YAGNI.** It decides *where* to look before it looks: if you named a direction, it takes it; otherwise it walks the commit history for hot spots and lets recently changing code pull its attention first. Then it spawns a sub-agent to walk the codebase organically, noting friction — shallow modules, pure functions extracted for testability while the real bugs hide in how they're called, tightly-coupled modules leaking across seams.

Candidates are presented as a self-contained HTML report in the OS temp directory, then **grilled**: once you pick a candidate, it runs the [grilling](https://aihero.dev/skills-grilling) interview over the decision tree, and [domain-modeling](https://aihero.dev/skills-domain-modeling) keeps the domain model current as decisions crystallise.

## When to reach for it

You invoke this by typing `/improve-codebase-architecture` — the agent won't reach for it on its own.

Run it whenever you have a spare moment to keep the codebase good for agents to operate in. Picking one deepening opportunity *generates an idea* you can take into the main flow at [grill-with-docs](https://aihero.dev/skills-grill-with-docs).

## It's working if

- The scan is scoped — named direction or hot spots from history — rather than a whole-repository sweep.
- Every suggestion is written in the `codebase-design` vocabulary, with the deletion test applied to anything suspected shallow.
- The HTML report lands outside the repo, with a recommendation strength and a top recommendation.
- The follow-up is a grilling loop, not a silent refactor.

## Where it fits

`improve-codebase-architecture` is the codebase-health lane — not feature work, upkeep. Its post-mortem is where [diagnosing-bugs](https://aihero.dev/skills-diagnosing-bugs) hands off when the real finding is that there's no good seam to lock a bug down. When you're unsure which skill or flow fits, [ask-matt](https://aihero.dev/skills-ask-matt) routes you.
