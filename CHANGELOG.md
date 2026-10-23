# Changelog

## Unreleased

### His life
- **He forgets like a person.** Memories fade along a curve set by how much they mattered (days for trivia, years for what counted), slowed by going back to them; details go before the gist, and what mattered keeps its gist for good. Hazy memories carry hazy times, and a hazy memory he uses can drift (details lost, two moments blended, the wrong person stuck). Nightly, what has faded is archived and a fortnight of the same thing becomes one memory. Residents remember him the same way: clearly for days, as gist for weeks, and sometimes not at all; a friend may tell him news again, having forgotten they did. Plans come back to mind naturally or by a reminder in his phone; without either, a plan with someone can slip his mind, rarely, with everything that follows. What he keeps is weighed nightly by how the moment felt and how unusual it was, not by which system wrote it down. When nothing comes back about what you ask, he says so. A memory with a friend is something to bring up with them, once; where he is and who's with him can bring a memory into his thoughts. Recall works by meaning as well as by words on a small local embedding model, and what comes up primes the memories near it.
- **He makes his own plans.** When he's been on his own a few days or a friend is on his mind, he texts someone ("Pint tonight? The Listening Room, half seven?"). They answer from their own day: working, tired, busy, "Thursday instead?", or yes. A yes books it. This replaces follow-ups that booked "Spend time with X" at one the next afternoon. Friends text him too, at lunch or after work, for evenings and weekends, and he answers from his own week.
- **Weeks have a rhythm.** Deadline weeks run into the evenings and a Saturday morning with no weeknight plans; slack weeks start late, finish at five and are when he pitches. He looks at the week on Monday morning.

### Running it
- **`eidos harness-probe`** tries a change to how a model role is asked on real recorded moments, the current way and the new way on the same models, judged by the checks his life already uses, and keeps the lesson (after Harness²). Its first run cut encounter and conversation lines turned away from 57% to 20%. It judges his texts and thoughts too, gives margins of error and quality measures, confirms on held-out moments, compares models (all three local ones scored alike, so routing stayed), audits answers already given with no model calls, and has an editor model propose changes. Each night while he sleeps it measures his roles and suggests (never adopts) a change; the Models page shows how they're doing. Its first nightly suggestion, confirmed on 30 more moments, took encounters turned away from 30% to 20%.

### His world
- **The town has a story.** A storyteller paces it: quiet weeks, then something that matters. A burst main shuts the café (Mara's at home), the river floods the path, the power goes, the chip shop burns, Dennis from the hardware shop dies. Residents hear and talk about it; he hears it by being there, on the town's Facebook group, in a queue, over the fence or from a friend, or not at all. News leads somewhere: the record shop opens and he can go, he decides about Dennis's funeral, and puts a fiver in the jar for the family from the chip shop.
- **His local.** The Crown & Anchor is on the Market Place, three minutes from Juniper: drinks, birthdays, leaving dos and New Year go there, and so do residents of an evening.
- Chance meetings with anyone who has a surname (Stuart, Beth, Hannah) were thrown away for not using their full name, and retried every quarter-hour; now a first name will do.
- His thoughts: less wandering (it ran at 0.64 against about half for people), a little more looking ahead, and old record ids reach the models as names.
- He forgot 28% of what he meant to do; the nightly chance of something slipping is lower, so it's nearer one in eight.
- The model is asked for improvised town moments now and then (at most every six hours, none for two days after a story), not every hour.
- What has stayed with him is a moment he went back to on different days (a Tuesday's summary his stream cued seventeen times one evening hasn't), weighed by how it felt; texts, summaries and lines people said don't qualify.
- His stream is no longer shown its own rut: thoughts carrying a worn-out word ("Rowan's sketchbook", eleven thoughts one evening) are kept from the model, a word and its compounds count as one rut, and an opening leaned on over days ("Should I...", 54 times in three days) is worn even when never three in a dozen. The murmur prompt line last night's probe found better (42% to 25% turned away) is in.
- **He feels more.** An outing that was more than its name, one that fell flat, a friend calling round or ringing, a friend's rough week in the group chat, a day with nobody in it, putting something off: each is now a feeling about something, and a strong one names his mood over mild contentment (two labels had covered 97% of three days).
- **Calls have words.** A call he answers has their opening, his reply and their sign-off; a call he makes goes on past their first answer. Each line is checked like a text and remembered.
- **The night's summary is held to the day.** The day as it happened (where he went, whom he talked with and where, who called round, whom he rang) goes to the chronicler with the memories; a summary that names someone who wasn't in the day, or says someone visited when they met elsewhere, is asked for again, then replaced by the outline's own sentences.
- Something he only just put on the calendar isn't "put off" in the same hour.
- **The nightly probe adopts.** A winning change is confirmed on older moments it wasn't tuned on; if it wins there too it applies to his life's calls at once and across restarts (`harness/adopted.json`).
- In the group chat nobody thanks someone who hasn't posted ("Thanks, Nina", answering Ellis), a resident doesn't address a line to themself ("Hannah, I remember you mentioned...", as Hannah's words; the probe counts it as `talks_to_self`), residents don't chat mid-journey, and a visitor at the door is Hannah Fenwick, not "Townsfolk 1855".

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
