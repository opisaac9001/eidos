# Upgrading a live world to `evolve/true-self`

This branch changes how Patrick lives and who he becomes. It is **additive to history**:
no recorded event is rewritten, and every existing world replays. On the first ticks
after the upgrade, new systems start mid-life.

## Verified before release (September 23, 2026)

Copies of the local `observatory`, `server-migration-20260907` (the Dell lineage, 4,056
events), `development` and `lab` databases were each:

1. loaded and projected into a full UI snapshot;
2. advanced 24 simulated hours with stand-in performers;
3. reopened in a fresh process and fully replayed.

All four succeeded. The live Dell world (4,108 events at `natural20260908a`) shares the
server-migration lineage, but it has not been tested directly. **Repeat the replay check
on a verified backup of the Dell database before installing**:

```bash
PYTHONPATH=src .venv/bin/python -m eidos backup --database /var/lib/eidos/observatory.sqlite3 --output /srv/eidos-data/eidos/backups/pre-true-self.sqlite3
PYTHONPATH=src .venv/bin/python -m eidos verify-backup --input /srv/eidos-data/eidos/backups/pre-true-self.sqlite3
cp /srv/eidos-data/eidos/backups/pre-true-self.sqlite3 /tmp/replay-check.sqlite3
PYTHONPATH=src .venv/bin/python -m eidos --database /tmp/replay-check.sqlite3 advance --hours 24
PYTHONPATH=src .venv/bin/python -m eidos --database /tmp/replay-check.sqlite3 self
```

Only ever advance the **copy**.

## What will change for Patrick after the upgrade

| System | What appears on the first ticks |
|---|---|
| Job | `work.agreement_accepted`: a part-time arrangement with Ellis (Mon, Tue, Thu, Fri, 10:00–16:00). The next week's shifts are published, each citing the agreement. Ellis keeps those hours at the workshop. |
| Going home | If Patrick is away from home, he walks home before his chosen bedtime, when a place closes, or after three idle hours. Worlds where he had been sleeping in the park stop doing so. |
| Food | His next grocery order is a weekly shop (21 portions, £42). A "go without" choice now holds for the day. Couriers wait up to three hours. |
| Sleep | Rest recovers 0.065 an hour asleep instead of 0.04, so chronic exhaustion eases over a few nights. He wakes at the hour he chose. |
| Self | At 20:00 on the first evening, chapter 1 ("Finding my feet") opens. Questions about himself need three weeks of lived evidence, so expect the first one after a few weeks, not immediately. |
| Wages | Shifts pay £11 an hour for hours actually worked. The old routine-memory wage stops in worlds with a rota. |
| Rent | Weekly housing rises from £85 to £125 (rent and bills). The existing balance is kept; the new £400 opening cushion applies only to brand-new worlds. If the live balance is low, the first week or two could miss a rent payment before shift wages build up. |
| Energy | Sleep now restores energy and waking hours spend it. Expect higher morning energy and more initiative than the live world has shown. |
| Company | An hour spent among people he knows (or talking with you) tops up connection instead of draining it. His long-running loneliness in the live world should lift over a few days of ordinary life. |
| Wants | After two settled weeks, a Saturday may bring one thing he wants that fits who he is. He saves for it with a £200 cushion and buys it on a free day out. |
| Calls and visits | Neighbours reach out far less often: each person at most every three days, one unprompted contact a day. |
| Finishing things | Work that is at least 80% done when its time runs out is finished off if he is still there and free, so shifts with a lunch hour count as complete. |
| Ordinary friction | Rarely, something breaks and costs money, Ellis cancels a shift in a quiet week, a rushed or cut-short shift leaves Ellis short with him (which he may clear over a later lunch), or he notices a friend he hasn't seen in weeks. Repeated clashes with Ellis can become a question he asks himself. |
| Sick days | The existing wellbeing episodes (headaches, aches, feeling under the weather) now reach work: on a morning bad enough that he couldn't work through it, he rings Ellis in sick and that shift is cancelled (unpaid). Milder spells he works through. If you ask how he is while unwell, he says so. |
| Places he knows | He starts knowing home, the café, the workshop and the park. Other places become known when he goes there, notices one next to where he is, or is invited there. His own plans and projects only use places he knows, so a world with the city-life pack will see him choose fewer outings to far places until he has found them. The ordinary map shows only known places. |
| Meetings | Anyone who has agreed a time with him now sets off to be there and stays until it ends. Before, meetings only worked when the other person happened to be nearby, and he was blamed for the missed commitment when they weren't. |
| Shifts | Talking with Ellis during a shift no longer pauses the work, and a chat in the last hour of a long stint no longer leaves it unfinished. Expect far fewer "left the bench half-done" clashes. |

None of this touches past messages, memories or relationships.

## Operator token

The operator controls (clock, step, catch-up, event history, export, job cancellation)
now require a token. `serve` prints an `/operator?token=…` link to the journal at startup.
To keep one stable across restarts, create `/etc/eidos/operator.env` with
`EIDOS_OPERATOR_TOKEN=<something long and random>` (mode 600). The updated
`eidos.service` loads it if present. Update any bookmarks that go through the SSH tunnel.

## New model capability: `pathos_selfhood`

The routes file must either have a `default` route or list `pathos_selfhood`
explicitly. `infra/dell-t630/model-routes.json` has a default (the world P40), which is
a reasonable home: the role runs at most once per evening, plus once on some Sundays.

Two structured schemas go through it (insight and chapter). As with the other structured
roles, invalid output is recorded as a failed trace and Patrick simply keeps wondering.
Nothing is invented on failure.

The reflection prompt now receives `self_inquiry` when a question is open. Watch the first
real-model reflections for quoting the question verbatim or answering too neatly.

## Performance

A tick now costs a small fraction of what it did. A 75-day stand-in life replays and
advances without the growth that previously made day 60 take about 45 seconds. The full
test suite takes about 90 seconds, down from about 10 minutes. The first tick after a
cold start replays the log once, then the incremental projections take over.

## Rollback

Code rollback follows the September 8 procedure. Verified: the pre-upgrade code (`c895b4a`) loads, advances and replays a world that already contains new `self.*` and `work.*` events. The new event kinds (`self.*`,
`work.*`) are ignored by older code's projections because they match no handler, so a
rollback after some new events exist still replays. Patrick would stop going home and
working until the upgrade returns.
