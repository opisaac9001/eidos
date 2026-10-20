# Tuning how the model roles are asked

Each model role (firmament for encounters and conversations, murmur for his passing
thoughts, his texts, his deliberation) is asked through a *harness*: its prompt
(`ROLE_PROMPTS`), the context it may see (`ROLE_FIELDS`) and the checks on what it says.
`eidos harness-probe` tries a change to a harness on real recorded moments before his life
gets it, after [Harness²](https://github.com/google-research/harness2) (Xu et al., 2026):
propose a change, probe it on the same tasks as the current harness, keep it only if it
behaves better, and write down what was learned.

## How it works

- **The moments are real.** Every model call his life makes is kept with its full context
  in the `cognition_jobs` table. The probe takes the most recent distinct ones for the
  role (or those mentioning `--grep`).
- **Both ways, the same models.** It asks each moment the current way and the proposed
  way, through the same configured models (`--repeats` asks each more than once, since
  answers vary).
- **Judged by the checks his life uses** (`application/harness_probe.judge`): an invalid
  or unfinished answer, an encounter without the person in it, an invented shared thing
  ("that project Ellis mentioned"), someone else claiming his project, Patrick giving his
  project away, a shared past from before he came, saying the same thing again, a leaked
  record id or the simulation's name, running long.
- **A clear win only.** `adopt` needs a fifth fewer lines turned away and at least five
  points, with no kind of problem noticeably worse.

## Running it

On the Dell, on a copy of the live database, at low priority (it uses the same models his
life does; keep runs small):

```sh
cp /var/lib/eidos/observatory.sqlite3 /tmp/obs_copy.sqlite3
cd /srv/eidos
EIDOS_MODELS_FILE=/var/lib/eidos/models.json nice -n 10 .venv/bin/python -m eidos \
  --database /tmp/obs_copy.sqlite3 harness-probe --role firmament --samples 20 --repeats 2 \
  --variant /tmp/my-change.json --record /tmp/LESSONS.md --out /tmp/harness-out
```

Without `--variant` it measures the current harness and shows what would be turned away.

## A variant

```json
{
  "role": "firmament",
  "name": "narrate-and-ground",
  "why": "What went wrong, in the live life",
  "prompt_append": "Text added to the end of the role's prompt.",
  "prompt_replace": ["old wording", "new wording"],
  "fields_add": ["a context key the role should see"],
  "fields_drop": ["one it shouldn't"],
  "context": {"key": "a value added to every moment"}
}
```

Kept variants are in [variants/](variants); what was tried and how it went is in
[LESSONS.md](LESSONS.md). An adopted change goes into `adapters/http_gateway.py` by hand,
with a comment pointing at its lesson.
