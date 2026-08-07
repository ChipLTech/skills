Quickstart:

```bash
npx skills add mattpocock/skills --skill=to-questionnaire
```

```bash
npx skills update to-questionnaire
```

[Source](https://github.com/mattpocock/skills/tree/main/skills/productivity/to-questionnaire)

## What it does

`to-questionnaire` turns a decision you can't fully answer into a **questionnaire** — a Markdown document you hand to one person to fill in async, or fill out together over a meeting. The recipient holds knowledge you lack; the questionnaire pulls it out of them.

**Grill the send, not the subject.** It interviews you only about the *send*, which you can always answer: who it goes to, and what you need back. The questions in the document then target the **gap** between what the recipient knows and what you need.

## When to reach for it

You invoke this by typing `/to-questionnaire` — the agent won't reach for it on its own.

Reach for it when the thing blocking you isn't in your head or the codebase but in **someone else's** — a missing product decision, an undocumented process, domain knowledge held by a colleague. It's the inverse of [grill-me](https://aihero.dev/skills-grill-me): instead of interviewing you about the subject, it interviews you about the send. What comes back is material for [grill-with-docs](https://aihero.dev/skills-grill-with-docs) or [to-spec](https://aihero.dev/skills-to-spec).

## It's working if

- The send is settled first — recipient's role, expertise, relationship — in one exchange.
- The questions target the gap between what the recipient knows and what you need, not generic interview questions.
- The document carries the context the recipient needs, calibrated to who they are.
- It is user-invoked: the agent recommends it but never fires it on its own.

## Where it fits

`to-questionnaire` is a reach-for-it-anytime standalone. When you're unsure which skill or flow fits, [ask-matt](https://aihero.dev/skills-ask-matt) routes you.
