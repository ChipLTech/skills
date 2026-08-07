Quickstart:

```bash
npx skills add mattpocock/skills --skill=wizard
```

```bash
npx skills update wizard
```

[Source](https://github.com/mattpocock/skills/tree/main/skills/engineering/wizard)

## What it does

`wizard` generates an interactive bash script that walks a human, step by step, through a manual procedure only a human can perform — provisioning infrastructure, setting up credentials or CI secrets, walking an unfamiliar third-party dashboard, running a one-off migration or cutover. It opens each URL, says what to click and copy, captures the values, and writes them where they belong (`.env`, GitHub secrets), with confirmation gates before irreversible steps.

The agent writes the script; it never runs it — you do, on your own machine. So a wizard is not a list of instructions to follow; it is a program that drives the procedure and holds the state. `template.sh` in the package already solves the UX (stage-by-stage progress, hidden secret entry, idempotent `.env` upserts, cross-platform URL opening); your job is only to scope the procedure and author its stages.

## When to reach for it

Type `/wizard`, and the agent can also reach for it on its own. When the agent hits a step only you can take — a key it can't mint, a dashboard it can't click — it builds a wizard instead of dumping numbered steps into the chat.

Don't reach for it to *decide* what to build; for that, [grill-with-docs](https://aihero.dev/skills-grill-with-docs) and [to-spec](https://aihero.dev/skills-to-spec) are the tools. In the Chipltech context, a wizard packages already-authorized human-only steps; it does not grant credentials, Host-modification, or production-cutover permission, and it cannot prove the steps ran.

## It's working if

- You're shown an ordered list of stages and the values each one produces, and asked to confirm — before any script exists.
- Every URL is opened before the value from that page is asked for.
- Secrets are typed blind; nothing sensitive echoes into scrollback.
- Each stage fits one screen; nothing you still need has scrolled away.
- Ctrl-C and re-run picks up where you left off, offering already-saved values as defaults.
- The final screen lists what it wrote and, separately, what you must finish by hand.

## Where it fits

`wizard` is a reach-for-it-anytime standalone at the line where automation stops and a human has to click. It pairs with [implement](https://aihero.dev/skills-implement) when a build lands a feature that needs credentials or a manual cutover. When you're unsure which skill fits, [ask-matt](https://aihero.dev/skills-ask-matt) routes you.
