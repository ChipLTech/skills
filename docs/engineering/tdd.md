Quickstart:

```bash
npx skills add mattpocock/skills --skill=tdd
```

```bash
npx skills update tdd
```

[Source](https://github.com/mattpocock/skills/tree/main/skills/engineering/tdd)

## What it does

`tdd` builds a feature or fixes a bug test-first: one failing test, then just enough code to pass it, then the next behaviour. It carries the standards that make that loop produce tests worth keeping — what a good test is, where tests go, what mocks are for, and the anti-patterns that quietly ruin a suite.

Three words carry the skill:

- **Red-green.** Write the failing test, then only enough code to pass it. There is no refactor phase — refactoring belongs to [code-review](https://aihero.dev/skills-code-review), not the red → green loop.
- **Vertical slice.** One seam, one test, one minimal implementation, then repeat — the first cycle a tracer bullet that proves a single path end to end. The opposite, horizontal slicing (all tests first), verifies *imagined* behaviour.
- **Pre-agreed seam.** No test is written at an unconfirmed seam. Invoked on its own, the skill asks you to name the public boundaries it intends to test at and confirm them first.

When the shape of the interface itself is the open question — how deep the module is, where the seam belongs — it defers to the [codebase-design](https://aihero.dev/skills-codebase-design) vocabulary rather than inventing its own.

## When to reach for it

Type `/tdd`, or the agent reaches for it automatically when a task fits — building a feature or fixing a bug test-first, or when you say "red-green-refactor".

Reach for it when there is a concrete behaviour to build with an input and an observable output, and you want tests that survive a refactor. If the behaviour isn't pinned down yet, use [to-spec](https://aihero.dev/skills-to-spec) first, which also agrees the test seams. If the question is really the shape of the interface, use [codebase-design](https://aihero.dev/skills-codebase-design). If you have a spec or tickets and want the whole build run, use [implement](https://aihero.dev/skills-implement), which drives `/tdd` per ticket.

## It's working if

- The failing test is written first and watched fail for the right reason.
- Tests assert through public interfaces, with expected values from an independent source of truth — never recomputed the way the code does (the tautological anti-pattern).
- Mocks appear only at system boundaries — external APIs, time, randomness, filesystem — never against your own modules.
- One cycle is one seam, one test, one minimal implementation.

## Where it fits

`tdd` is a **reference** the implementation chain runs: [implement](https://aihero.dev/skills-implement) drives it per ticket and [code-review](https://aihero.dev/skills-code-review) closes it out, checking that only agreed seams were used. It speaks the [codebase-design](https://aihero.dev/skills-codebase-design) vocabulary for module shape. When you're unsure which skill or flow fits, [ask-matt](https://aihero.dev/skills-ask-matt) routes you.
