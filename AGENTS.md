# Eidos Agent Guide

Instructions for coding agents (Codex, Claude Code and others) working in this repository.

## Before changing code

From the repository root, confirm the checkout and preserve any existing work:

```sh
pwd
git remote get-url origin
git branch --show-current
git status --short
```

Then read [CONTRIBUTING.md](CONTRIBUTING.md) for the invariants, [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how a tick runs, and [docs/PATRICK_SHAW.md](docs/PATRICK_SHAW.md) before touching who he is.

## What the project is for

Eidos simulates one person, Patrick "Pathos" Shaw, as close to how a real person lives and thinks as it can. Judge every change by one question: **would a real person do, think or know this?**

- Rules decide what happens. Models only word it, or propose ideas the rules check.
- He knows only what he has perceived, been told, read or remembers.
- His life is lived, not scheduled: times to the minute, choices from his body, mood, habits and what's on his mind.
- Keep his identity and the people in his life as they are unless the change is deliberately about them.

## Rules that are easy to break

- **Replay contract.** Never tighten validation for an existing event kind. Old histories must replay.
- **Scalar payloads.** Event payload values are scalars, never lists.
- **Bookings need a cause.** Every `schedule.created` follows an agreement or a decision event.
- **Context keys reach real models only if listed** in that role's `ROLE_FIELDS` in `src/eidos/adapters/http_gateway.py`. The stand-in sees everything, so tests pass either way: add a field-membership test.
- **A new model role** needs `STRUCTURED_CAPABILITIES`, the routed gateway's `CAPABILITIES` and `FALLBACKS`, provider `ROLE_GROUPS`, persona `PERSONAL_ROLES`, `ROLE_PROMPTS` and `ROLE_FIELDS`, and a stand-in branch.
- **Small models ignore instructions.** Prefer a check in code (turn the output away, ask once more) to another line in a prompt.
- **Measure a prompt change before shipping it.** `eidos harness-probe` replays real recorded moments the current way and your way and says which would be turned away less (see [docs/harness](docs/harness/README.md)). Record the outcome in `docs/harness/LESSONS.md`.
- **Everyday doings** (`doing-` calendar entries from `application/everyday.py`) are exempt from forgetting, "samey" judgements, visit blocking and agency causes. Keep them that way.
- **No secrets.** Model keys and operator tokens never go in the repository, the event log or the UI.

## Verifying a change

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m mypy src
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
```

For a change to his life, also run a few simulated days with the stand-in and read what happened, or run `eidos believability` on the result. Tests that check a whole life use the stand-in gateway and temporary databases.

## Commits and publishing

Do not commit, push, merge, rewrite history or change branches unless the user asks. Commit messages describe the change in his life in plain words ("Ellis lets him off the rest of his notice: he's a writer now") and carry no AI attribution or co-author lines. The repository is public: check a diff for keys, tokens and private addresses before pushing.
