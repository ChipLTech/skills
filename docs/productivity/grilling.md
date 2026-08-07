Quickstart:

```bash
npx skills add mattpocock/skills --skill=grilling
```

```bash
npx skills update grilling
```

[Source](https://github.com/mattpocock/skills/tree/main/skills/productivity/grilling)

## What it does

`grilling` is the interview primitive itself — the shared engine underneath [grill-me](https://aihero.dev/skills-grill-me), [grill-with-docs](https://aihero.dev/skills-grill-with-docs), [triage](https://aihero.dev/skills-triage), [wayfinder](https://aihero.dev/skills-wayfinder), and [improve-codebase-architecture](https://aihero.dev/skills-improve-codebase-architecture).

It maps the plan as a **design tree** and works it in **rounds**: the **frontier** is every decision whose prerequisites are already settled — the questions you can ask *now* without guessing at answers you haven't heard yet. It asks the whole frontier in one round, numbering each question and giving a recommended answer, then waits. Each round's answers reshape the tree, pushing the frontier outward.

Finding *facts* is the agent's job, never the user's: when a frontier question needs a fact from the environment, it dispatches a sub-agent to find it rather than asking you. The *decisions* are yours — each is put to you, and the session ends only when the frontier is empty and you confirm the shared understanding.

## When to reach for it

Reach for it directly only when you want the interview with no wrapper around it. Named in the format — a question title, body, and a recommended answer — each question carries a recommendation, so a round both extracts and proposes.

## It's working if

- Questions arrive in rounds across the whole currently-unblocked frontier, not one at a time.
- Each question has a numbered title, a body, and a recommended answer.
- Facts are looked up, not asked for; only decisions go to the user.
- The session stops only when the frontier is empty and the user confirms the shared understanding.

## Where it fits

`grilling` is the interview mechanism beneath every skill that needs to stress-test a plan. The two named ways in are [grill-me](https://aihero.dev/skills-grill-me) (stateless, no working directory) and [grill-with-docs](https://aihero.dev/skills-grill-with-docs) (stateful, in a repo). When you're unsure which skill or flow fits, [ask-matt](https://aihero.dev/skills-ask-matt) routes you.
