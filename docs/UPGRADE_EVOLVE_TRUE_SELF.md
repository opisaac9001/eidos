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
| What's on | With the city-life or Alderwick places installed, venues have a weekly rhythm (quiz, repair café, music, film, market). Once he knows a venue, its next happening can reach his choices, and he may go. The World view lists the week's happenings at places he knows. |
| Tastes | Each thing he chooses to do is now felt (`experience.felt`), and places and activities become things he loves or that aren't for him (`taste.formed`), sometimes changing his mind later. Expect him to return to places he loves and drop activities he has gone off. The first tastes typically appear within a week or two. |
| His people | Each friendship now has a depth from 1 to 12 (after "12 Levels of Friendship"), built from shared moments and time. Only friendships below level 6 fade with absence; close friends stay close however long it's been. He's warmly reminded of a close friend he hasn't seen in weeks, and picks up where they left off when they meet again. Strain is a passing state. Existing relationships are assessed from their whole history on the first evening. |
| News | If outreach is enabled and you're a friend (or have talked on three or more days), he may message you about something that just happened: a new love, a great evening, a purchase he saved for. It happens at most every three days, and never while one of his own messages is unanswered. |
| Townsfolk | When he is out, he now sometimes notices one of the town's regulars (`townsfolk.noticed`), sees them again, and after a few sightings may get talking (`townsfolk.introduced`). Firmament describes and names them through the new `firmament_townsfolk` capability. If you route capabilities per model, it uses your `firmament` route (or the default) unless you give it its own. After a handful of chats with someone he clicks with, they swap numbers (`townsfolk.numbers_swapped`) and the townsperson is registered as a full resident who can invite him out. Expect one or two townsfolk moments on days out. |
| Family | His family (Mum, Dad, Tom, Jess, Isla) is now part of his life: Sunday calls, Tom's family chat, news, birthdays that can be forgotten, and Christmas at home in Wye (a train ride away, from 23 to 27 December). The persona is now `patrick-blend-v3`. **Rollback note:** meals at his parents' are recorded with `provision_source: family_table`, which code older than this release rejects; roll back only to a copy made before a Christmas visit. |
| What he knows about you | Each evening you talked, he may note things about your life, quoting your own words (`pathos_user_notes`, routed like `reflection` unless given its own route), and asks how they went. |
| "Fine, yeah" | Asked how he is while something's weighing on him, he may brush it off (`feeling.masked`), more often the less close you are, and own up next time (`feeling.admitted`). **Real models:** the conversation context now carries `wants_your_view_on`, `what_you_advised_lately`, `running_jokes_with_you`, `how_he_really_is` and `owes_honesty`, and the reply prompt explains them; these fields were added to the HTTP gateway's allowed list. |
| Memories that come back | A place, an anniversary or a friend who has moved away can bring a memory back unprompted (`memory.surfaced`), at most once a day. |
| Running jokes | Time with friends can turn into running jokes that come back weeks later (`joke.shared`, `joke.recalled`). The evening notes role now also sees the whole day's exchange (`todays_exchange`) and may return an optional `running_joke` with you. Older models that ignore it are fine. |
| Asking your advice | When something in his life needs deciding (the workshop, moving flat, a falling-out, someone he likes) and you're a friend, he asks what you think, in conversation or by message. The new `pathos_advice_heard` role (routed like `reflection` unless named) reads your answer each evening; your view then weighs in on what he decides. |
| Books, series, music | He is usually partway through a book, a series and an album, with opinions when he finishes (or gives up). |
| Seasons | Winter darkness weighs a little, summer evenings lift. Bank holidays and Christmas close the workshop. The clocks change. Moments of the year and anniversaries of his own life are remembered. |
| Falling short | He sometimes puts off his own plans on flat days, has late nights on his phone, and can snap at someone when exhausted (and apologise). |
| Work | Shifts now record their wage. A raise after three months, a fifth-day offer later (taken or not), and after a year a question about the workshop's future. A month later he answers: yes leads to him running the workshop over the next year and a half (five days, then the keys); no leads to Ellis taking on an apprentice he teaches. |
| Friends' lives | His friends now have their own turns (`friend.life_event`): new jobs, partners, babies, family worries, small achievements, and sometimes a move to another city after a leaving do. A friend who has moved away is no longer met, invited or visited in person, but can still call. Expect a few pieces of friends' news a year. |
| Going home | He now goes home to Wye for Easter and the August bank holiday weekend when he can afford the train, and once in his second year rushes home for three nights after Dad's heart scare (his shifts that week are cancelled with Ellis's blessing). New activity type `visiting_home`. |
| Evening class | Some Septembers he signs up for a ten-week Tuesday evening class at the community hall (`course.stage`), may skip the odd week when worn out, and either finishes it or admits he stopped going. |
| Friends' birthdays, bonfire night, New Year | His friends' birthdays (`friend.birthday`), his own birthday drinks, bonfire night and New Year's Eve are now plans (`calendar.plan`) that cause bookings. |
| Friends far away | Friends who've moved away are called every few weeks (`friend.kept_in_touch`), and a close one may be visited for a weekend (`friend.visit_planned`, activity `visiting_a_friend`). |
| Weddings | Friends can get engaged and married (`friend.life_event` kinds `engaged`, `wedding_invited`, `wedding_announced`, `married`). He goes if he's invited. |
| Lying awake | Worry, money or excitement can keep him up at night (`sleep.restless`), costing some rest. |
| Real news | Opt-in (`EIDOS_NEWS=on` or `EIDOS_NEWS_FEEDS`). He reads real headlines morning and evening (`news.heard`), forms his take through the new `pathos_news_take` role (routed like `reflection` unless named), and can discuss them. They also move his mood, can nudge his spending, and are on his mind. With the town signal on, the real weather becomes his weather in a live world. The HTTP gateway passes `in_the_news`, `headlines_he_has_seen` and `news_instruction` to his replies. |
| Falling out | Rarely, and more likely after he lets someone down, he falls out with a friend (`friend.falling_out`, plus a tension change that marks the bond strained). Close friends always make up; newer ones sometimes don't, and stop inviting him or calling round. |
| His body | New `body.event` and `body.week` kinds. Now and then a small knock at the bench stays sore for a few days (about one or two a year). A big night out can mean a hangover and a tired morning. A weekly fitness level follows how much he walks and gets outdoors, with a memory when he's noticeably fitter or out of shape. In a world more than nine months old, the first evening brings a nag about the dentist; within about three months he books it (a new "Castle Street Dental" place is registered), goes, and pays for a check-up or a filling. In winter a wellbeing spell is more often a cold. |
| Views on the town | After a few months in town, and then every four to six months, a local issue comes up (`town.issue`): the old mill, the 12 bus, a coffee chain, a 20mph zone, the library. He takes a view from his values (`opinion.formed`), may book the public meeting at the council rooms (`town.meeting_planned`), may change his mind there or after talking to Ellis (`opinion.changed`, `opinion.discussed`), and is pleased or disappointed by the council's decision (`opinion.outcome`). Worlds without the Alderwick pack have the issues but no meeting booking. |
| Home and habit | Small touches (`pet.event`, `plant.event`, `habit.regular`). After a move, or after 18 months settled, he may adopt a rescue cat. It has its own name and temperament, occasional moments at home, weekly food and the odd vet's bill (everyday spending). A friend feeds it when he's in Wye. He buys houseplants now and then: most die when he's worn out or away, and a few thrive. After ten visits to Juniper Café, Mara knows his usual. In a live world that has already been going for 18 months, a cat is possible from the first Sunday after the upgrade, and a café regular's "The usual?" can come on the next visit, since past arrivals count. |
| A week away | The workshop now shuts for the first full week of August (no shifts, unpaid). In May he books a holiday for that week if he can afford it (`holiday.stage`, activity `on_holiday`), alone, with his partner or with his closest friend. Once savings are comfortable, his everyday spending grows a little and includes a monthly treat. |
| Moving flat | In his second year, with money put by, he may look for a better flat, pay a deposit and move with a friend's help (`home.move`), or move in with a partner. Rent is now read from his latest move, so the weekly housing charge changes after one. |
| Romance | Rare and slow; never involving you, his boss or family. He can be drawn to regulars as well as friends, close friends sometimes set him up, and some relationships end after a few months. Expect something (a crush, a set-up or a few dates) in a typical year or two. New stages: `set_up`, `passed_on`, `no_spark`, `broke_up`. See `docs/LIFE.md`. |
| Memories | An hour that simply continues a planned activity is now remembered with low importance, so recall surfaces moments that stood out. |
| Everyday spending | Money now leaks out the way it does in a real week: a coffee at the café, drinks at the Crown, a cinema ticket, sandpaper at the hardware shop, weekly bits and bobs, a haircut every few weeks, a monthly phone bill, cards and presents for family occasions, and the train and presents at Christmas (`spending.made`). In a simulated year he now finishes about £900 up on part-time wages, not £5,000, and never misses rent. He only buys extras if next week's rent and £30 would still be left, keeps to the basics when savings are under two weeks' rent, and the phone bill is always owed. **Rollback note:** the ledger's new categories (`everyday`, `bills`, `going_out`, `gifts`, `travel`) are rejected by older code; roll back only to a copy made before the upgrade ran. |
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
