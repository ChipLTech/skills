Quickstart:

```bash
npx skills add mattpocock/skills --skill=codebase-design
```

```bash
npx skills update codebase-design
```

[Source](https://github.com/mattpocock/skills/tree/main/skills/engineering/codebase-design)

## What it does

`codebase-design` fixes the words you use to design a module: **module**, **interface**, **depth**, **seam**, **adapter**, **leverage**, and **locality**. It defines each term precisely, bans the loose substitutes ("component", "service", "API", "boundary"), and states the handful of principles that follow — the deletion test, "the interface is the test surface", and "one adapter means a hypothetical seam; two means a real one".

It is a **reference, not a process**. There is no loop to run and no artifact it produces; it gives you the language and stops. `/tdd` and `/improve-codebase-architecture` both speak it, and `DESIGN-IT-TWICE.md` in the package runs parallel sub-agents to compare radically different interfaces for the same module.

## When to reach for it

Type `/codebase-design`, or the agent reaches for it automatically when a design task fits.

Reach for it when you already know which code you're redesigning and need to think about its shape — where the seam goes, how small the interface can get, whether an extraction is earning its keep. If the problem is the *words of the domain* ("account" means three things), use [domain-modeling](https://aihero.dev/skills-domain-modeling) instead. If you don't yet know *which* module to redesign, use [improve-codebase-architecture](https://aihero.dev/skills-improve-codebase-architecture) — the survey that finds candidates.

## It's working if

- Design conversations stop producing "component", "service", and "boundary", and start producing "module", "interface", and "seam".
- Someone can point at a proposed extraction and say whether it passes the deletion test, without hedging.
- A proposed seam comes with a second adapter named, not just the first one.
- Invoking it does not start a session. If the agent begins reading files and proposing refactors off the back of `/codebase-design` alone, it has mistaken the reference for a driver.

## Where it fits

`codebase-design` is a **reach-for-it-anytime standalone**, the vocabulary layer underneath the engineering skills rather than a step in any chain. Its closest neighbour is [domain-modeling](https://aihero.dev/skills-domain-modeling), the parallel reference for the problem domain's words rather than the module's shape. When you're unsure which skill or flow fits, [ask-matt](https://aihero.dev/skills-ask-matt) routes you.
