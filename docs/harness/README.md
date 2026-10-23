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

## What it measures

- **Turned away**, with a 95% range (Wilson), so a narrow win on 20 moments isn't
  over-trusted.
- **Held out:** the moments are split in two, and `adopt` needs the change to be no worse
  on either half, so it isn't tuned to a few moments.
- **Quality,** beyond not being turned away: how varied the openings and phrasing are,
  how long and how spread out the lengths are, and how much each line is about the moment
  (shares a word with what it was given). A change that makes him much more alike
  (openings under 60% as varied) is not adopted, and its trade-offs are listed.
- **Roles judged:** firmament (encounters and conversations), pathos_text (his texts:
  emoji, signing off), murmur (his thoughts: the third person, his nickname), and for
  every role a name brought in from nowhere, a leaked record id, an AI slip, running long.

## Modes

| Mode | What it does | Models? |
| --- | --- | --- |
| `harness-probe --role R` | Measures the current way and shows what's turned away | yes |
| `--variant file.json` | The current way against your change, on the same moments | yes |
| `--propose N` | An editor model (the 35B, role `harness_editor`) reads the failures, what each check means and `LESSONS.md`, and suggests N changes; each is probed | yes |
| `--models a,b,c` | The same moments through each configured model | yes |
| `--audit` | Today's checks on answers already given: what they'd catch or wrongly block | no |

The first editor proposals read "someone claimed his project" as "the project is made up"
and suggested banning his sound atlas. The probe rejected all three. Since then the editor
is told what each check means and the gist of each failed moment.

## Each night

While he sleeps (between 1 and 5 in the morning, on the Dell's clock), the live server
measures encounters, his texts and his thoughts on the day's moments, audits the answers
already given, and for the worst role over 20% asks the editor for three changes and
probes them. Results go beside the database in `harness/` (`night-*.json`,
`history.jsonl`, `LESSONS.md`); the Models page shows each role's rate, its range, a
fortnight's trend and any suggestion. A winner on the night's moments is tried again on
as many older moments it wasn't tuned on; if it wins there too (the same `adopt` bar) it is
**adopted**: kept in `harness/adopted.json`, applied to his life's calls at once and on
every restart, and noted in `LESSONS.md` and the trend. A trial prompt applies only to the
probe's own calls (a context variable), never to the calls his life makes meanwhile, and a
later trial stacks on what's adopted. To undo one, remove it from `adopted.json` and
restart.

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
[LESSONS.md](LESSONS.md). A change adopted by the night lives in `harness/adopted.json`;
one worth keeping for good goes into `adapters/http_gateway.py` by hand, with a comment
pointing at its lesson, and comes out of `adopted.json`.
