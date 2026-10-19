# Contributing to Eidos

Thanks for helping. Eidos simulates one person's life as faithfully as it can, so the bar is simple: **he must only ever do, know and remember what his life has actually given him, and his history must always replay.**

## Setup

Requires Python 3.12 or newer. There are no runtime dependencies.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q                # about 1,400 tests, a couple of minutes
.venv/bin/python -m mypy src                 # strict
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
PYTHONPATH=src .venv/bin/eidos serve         # the Observatory at http://127.0.0.1:8765
```

Tests use the deterministic stand-in gateway, so they never call a model or the network. To see a change in a life, run a few simulated days:

```bash
PYTHONPATH=src .venv/bin/eidos --database /tmp/try.sqlite3 advance --hours 24
PYTHONPATH=src .venv/bin/eidos --database /tmp/try.sqlite3 believability
```

## Layout

- `src/eidos/domain`: events, folds and validation. The rules for what can be true.
- `src/eidos/application`: his life, one module per system (habits, work, money, friends, memory, the inner stream...). `life.py` runs the phases of each tick.
- `src/eidos/adapters`: SQLite, the model gateways and their prompts, the stand-ins, feeds, and the web server and UI.
- `src/eidos/ports`: interfaces to models, storage and the outside world.
- `world_packs`: additive world releases. `infra`: running him on a home server.

Before designing a change, read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/SYSTEM_INTERACTIONS.md](docs/SYSTEM_INTERACTIONS.md), and [docs/PATRICK_SHAW.md](docs/PATRICK_SHAW.md) if it touches who he is.

## Invariants

These keep his life coherent and his history safe. A pull request that breaks one won't be merged.

- **The replay contract.** Never tighten validation for an existing event kind; old histories must always replay. New optional payload fields are fine. Note rollback limits in [docs/UPGRADE_EVOLVE_TRUE_SELF.md](docs/UPGRADE_EVOLVE_TRUE_SELF.md).
- **Models propose, rules decide.** A model's output is a proposal until a rule accepts it. Nothing becomes true because a model said it.
- **He knows only what he's learned.** Perceived, told, read or remembered. Never someone's whereabouts or feelings he couldn't know.
- **Payloads are scalars.** Event payload values are immutable scalars, never lists (use `step_1..step_n` fields).
- **Every booking has a cause.** A `schedule.created` follows an agreement or a decision event.
- **New context keys must reach real models.** A key in a role's context is silently dropped unless it's in that role's `ROLE_FIELDS` in `adapters/http_gateway.py`. The stand-in sees everything, so add a test that checks the field list.
- **New model roles are wired everywhere.** `STRUCTURED_CAPABILITIES`, the routed gateway's `CAPABILITIES` and `FALLBACKS`, provider `ROLE_GROUPS`, persona `PERSONAL_ROLES`, the HTTP `ROLE_PROMPTS` and `ROLE_FIELDS`, and a stand-in branch.
- **No secrets in the repository.** Model keys and tokens live outside it (`~/.config/eidos/models.json`, environment variables). Never commit a `.sqlite3` file or anything from a real life.

## Code style

- Plain, typed Python that passes `mypy --strict` and `ruff`.
- Comments explain *why*, usually with the moment in his life that showed the problem.
- Prefer a rule in code to an instruction in a prompt: small models ignore instructions, and rules can be tested.
- Tests describe behaviour in plain words (`test_he_puts_the_kettle_down_when_you_come_round`) and use stand-ins and in-memory or temporary databases.

## Pull requests

- Tests, mypy and ruff pass. CI runs them on every push.
- New behaviour has a test. Anything touching events, replay or model wiring needs one.
- One concern per pull request.
- For changes to his life, say what a simulated day looked like before and after.

## Reporting bugs and ideas

Use the issue templates. For security problems, see [SECURITY.md](SECURITY.md) and don't open a public issue.

## License

Contributions are licensed under [AGPL-3.0-only](LICENSE.md), like the rest of the project.
