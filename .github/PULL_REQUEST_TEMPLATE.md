## What and why

<!-- One concern per pull request. For a change to his life, what did a simulated day look like before and after? -->

## How it was tested

- [ ] `python -m pytest -q`
- [ ] `mypy src`, `ruff check src tests` and `ruff format --check src tests`
- [ ] New or changed behaviour has a test (always, for events, replay and model wiring)
- [ ] For a change to his life: a few simulated days run and read

## Invariants (see CONTRIBUTING.md)

- [ ] Validation for existing event kinds isn't tightened; old histories replay
- [ ] Models propose, rules decide; he only knows what he's learned
- [ ] New context keys are in the role's `ROLE_FIELDS`
- [ ] No keys, tokens, databases or anything from a real life in the diff
