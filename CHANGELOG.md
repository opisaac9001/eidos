# Changelog

## 0.1.0 (2026-10-19)

The first release of the rebuilt Eidos: a persistent simulated person, Patrick "Pathos" Shaw, living minute by minute in a small English market town, with his whole life kept as a replayable event history.

### His mind
- **Two speeds of choosing.** Free time is chosen by rules, the way people mostly choose: from what he could do where he is, weighed by need, energy, mood, learned habits, tastes, boredom, the weather and whatever was on his mind. Real decisions and new ideas go to a model, and the rules check them. New things he tries and enjoys can become habits.
- **A continuous inner stream** of passing thoughts on a small local model (a 4B model on a Raspberry Pi), shaped after Descriptive Experience Sampling. Ruts, worn openings, invented people, invented touch and made-up events are turned away rather than kept.
- Thoughts lead to doing: a pull his thoughts keep returning to (fresh air, the kettle, a friend he's worried about) is acted on, put off or let go.
- Intentions that form, come back to mind and sometimes slip, at about the rate people's do.
- Moods named from feelings with causes, memories with fallible recall, dreams from the day he lived, a nightly sense of his life lately, and chapters of his life.
- Measured against how people actually live: `eidos believability` checks mind-wandering, thinking ahead, slipped intentions, sameness of days, sleep and company.

### His life
- **Work.** Eight months at Ellis's repair workshop, then freelance writing on technology and ordinary life: an offer from his old team, telling Ellis, pitches, commissions, writing sessions he books himself, edits, publication, invoices, chasing late payers and a column offer.
- **Money.** A ledger for everyday spending, plus savings, a tax pot, an ISA, a general investment account and self-assessment in January, after his old company's share options paid out.
- **Body.** A two-process sleep model with waking his own way, hunger and meals that fit the day, tiredness, colds, hangovers and small injuries.
- **People.** Friendships that deepen and fade, friends with lives of their own, a family who ring on Sundays and visits home to Wye, a friends' group chat whose plans become real meet-ups, slow and uncertain romance, and pronouns of each person's own.
- **Conversation.** Talking points chosen by rules from what two people actually know, a setting for why they're both there, and Patrick speaking from how his life really stands.
- An evening class, records, books and series he gets through, a film camera, and the block plane he's still learning to tune.

### His world
- **Alderwick on real streets:** laid out on OpenStreetMap data of Frome, Somerset, with walking times from real distances, and about 8,500 latent townspeople met one at a time.
- **Residents with days of their own:** work, lunch out, walks after work, weekends and evenings out, within opening hours, keeping the plans they make with him.
- News that travels round town and changes in the retelling, opinions people form of each other with reasons, town issues, happenings, seasons and the real weather and headlines when connected.
- **Human knowledge.** He only knows what he has perceived, been told, read or remembers, never anyone's whereabouts or feelings he couldn't know.

### Running it
- Event-sourced on SQLite: every change is an event, and state is a replayable fold. A replay contract keeps old histories valid across releases.
- Model-agnostic: local servers or hosted APIs per role, with backups, a daily budget, and visible skips when nothing can answer.
- Runs in real time on a home server, with a Raspberry Pi for his inner voice and a hosted fallback; deploys run checks first and catch his clock up.
- The Observatory web interface (no build step, no external assets) and an operator view for plans, the engine and models.
- About 1,400 tests, strict mypy and ruff in CI.

## Earlier

The original 2025 implementation is preserved on the `legacy-2025` branch and tag.
