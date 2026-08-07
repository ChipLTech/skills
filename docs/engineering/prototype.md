Quickstart:

```bash
npx skills add mattpocock/skills --skill=prototype
```

```bash
npx skills update prototype
```

[Source](https://github.com/mattpocock/skills/tree/main/skills/engineering/prototype)

## What it does

`prototype` is **throwaway code that answers one design question** — and the question decides the shape:

- **"Does this logic / state model feel right?"** → a single shareable HTML file — free-play buttons plus tabbed guided walkthroughs — that pushes the state machine through cases hard to reason about on paper, and that a non-developer can drive.
- **"What should this look like?"** → several radically different UI variations on a single route, switchable via a URL search param and a floating bottom bar.

Rules that apply to both branches: throwaway from day one and clearly marked; trivial to run; no persistence by default; skip the polish; surface the full state after every action. **Capture it when done** — fold any validated decision into the real code, then keep the prototype itself as a **primary source** on a `prototype/<name>` branch out of main, pointed at from the implementation issue. "Throwaway" is a constraint on how the code is written, not a promise to destroy it.

## When to reach for it

Type `/prototype`, or the agent reaches for it automatically when a design question needs a runnable answer — state, business logic, a UI you have to see.

Reach for it any time a design question is hard to settle on paper. It's the detour in step 2 of the main flow, bridged by [handoff](https://aihero.dev/skills-handoff) in both directions. Note the Chipltech evidence boundary: a generic prototype is design evidence — it is not Real DLC Hardware, model-correctness, DLC Runtime, or performance acceptance evidence.

## It's working if

- The branch chosen matches the question — logic → shareable HTML, UI → multiple variations — and the assumption is stated when the question was ambiguous.
- A non-developer can run it without thinking, and see the state change on every action.
- The validated decision is in the real code and the prototype is committed to a throwaway branch as a primary source.
- The main branch keeps only the validated decision.

## Where it fits

`prototype` is a reach-for-it-anytime standalone and the detour in the main flow when a question needs a runnable answer. When you're unsure which skill or flow fits, [ask-matt](https://aihero.dev/skills-ask-matt) routes you.
