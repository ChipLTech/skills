Quickstart:

```bash
npx skills add mattpocock/skills --skill=ask-matt
```

```bash
npx skills update ask-matt
```

[Source](https://github.com/mattpocock/skills/tree/main/skills/engineering/ask-matt)

## What it does

`ask-matt` is the router over the skills in this repo. You describe the situation you're in; it tells you which skill or flow fits and in what order to run them.

It **does no work itself**. It doesn't grill, write a spec, or fix anything — it only orients. It exists for the **user-invoked** skills above all: nothing fires those for you, so *you* have to remember they exist, and `ask-matt` is the memory you offload that to. It also points at the model-invoked skills you'd reach for by name — `/tdd`, `/diagnosing-bugs`, `/prototype`, `/code-review`, and the vocabulary layer underneath. It answers "which one, and when", then hands you off to the skill that actually does the job.

## When to reach for it

You invoke this by typing `/ask-matt` — the agent won't reach for it on its own.

Reach for it whenever you're unsure which skill or flow a situation calls for: you have an idea and don't know where to start, a pile of bug reports and don't know if they're for `/triage`, or two skills that look interchangeable and you can't tell them apart. If you already know the skill you want, skip the router and invoke it directly.

## Flows, not just skills

The idea `ask-matt` gives you to think with is the **flow** — a path *through* the skills rather than a single one. Most work runs along one **main flow** (idea → ship: grill → spec → tickets → implement → review), with two **on-ramps** merging onto it (a triage lane for incoming bugs and requests; a codebase-health lane that generates ideas), a **vocabulary layer** running underneath (`/domain-modeling` for the domain's words, `/codebase-design` for the module's shape), and **standalones** you reach for on their own (`/grilling`, `/prototype`, `/research`, `/to-questionnaire`, `/wizard`, `/wait-what`, `/writing-for-agents`, `/handoff`, `/compact`). Chipltech accelerator, DLC, and vLLM-DLC work routes through `/chipltech-context` first, which retrieves cited read-only knowledge and loads the narrow owning execution skill.

**Phase boundaries** — between chunks of work inside a session, the router offers five options in order: Continue, `/clear`, `/handoff`, subagent, `/compact`. `PHASE-BOUNDARIES.md` in the package holds the ordered decision tree; the primary-source cost makes Continue the one to rule out first.

## Where it fits

`ask-matt` is the **router** — the standalone map that sits over the whole set. It is the node every other docs page links back to, so it never sits *in* a chain; it points *into* every chain. From here you'll most often land on [grill-with-docs](https://aihero.dev/skills-grill-with-docs), the head of the main flow, or [triage](https://aihero.dev/skills-triage), the on-ramp for work you didn't create. When even the router's own picture is stale, its [Source](https://github.com/mattpocock/skills/tree/main/skills/engineering/ask-matt) is the map of record.
