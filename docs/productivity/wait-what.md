Quickstart:

```bash
npx skills add mattpocock/skills --skill=wait-what
```

```bash
npx skills update wait-what
```

[Source](https://github.com/mattpocock/skills/tree/main/skills/productivity/wait-what)

## What it does

`wait-what` is the corrective for a message that didn't land. Used mid-conversation, inside any other skill, it makes the agent re-pitch what it just said with the context you were missing, in plain English, using the `CONTEXT.md` vocabulary.

It works **after the fact**; [grill-with-docs](https://aihero.dev/skills-grill-with-docs) is the upfront cure, because a shared language agreed early is what stops the jargon arriving at all.

## When to reach for it

You invoke this by typing `/wait-what` — the agent won't reach for it on its own.

Reach for it the moment a message leaves you confused: too much jargon, missing context, a leap you can't follow. In the Chipltech context, re-pitching must preserve formal DLC terminology and the Claim Boundary — simplification is about the explanation, not the evidence.

## It's working if

- The re-pitch is plain English with the missing context supplied, using project vocabulary.
- Formal domain terms and evidence boundaries survive the simplification.

## Where it fits

`wait-what` is a reach-for-it-anytime standalone, usable inside any other skill. When you're unsure which skill or flow fits, [ask-matt](https://aihero.dev/skills-ask-matt) routes you.
