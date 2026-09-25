# A life, not a routine

These are the systems that give Patrick an ordinary, specific life beyond his week: the
people in it, what he's into, the year turning, the ways he falls short, and where things
are going. Each one follows the project's rule: **models propose, rules decide**. Events
are recorded only when something actually happens, everything replays exactly, and the
models voice what the rules establish rather than inventing it.

Everything here applies to natural lives. Authored fixture worlds are unchanged.

## The real world's news (`application/world_news.py`, `adapters/news_feeds.py`)

Opt in with `EIDOS_NEWS=on` (the BBC's feeds) or `EIDOS_NEWS_FEEDS`.

**Hearing it.** At 07:00 and 18:00 he reads what's new (`news.heard`; real reports, with
source and link). The `pathos_news_take` role (routed like `reflection` unless given its
own route) picks up to three stories he'd take in. For each it gives his take in his own
voice, a feeling, how much it matters to him, and whether it touches his life (`news.take`).

**Rules that keep it honest.** A take must be about a story he was shown. He can't claim
to have been involved, and feelings are bounded.

**What it changes.**
- **Mood:** stories that matter move it a little, and important ones become memories.
- **Spending:** a price rise he took to heart makes his weekly bits cost 10% more for a
  month.
- **What's on his mind:** stories that touch his life appear there (`news_on_his_mind`).
- **Conversation:** the context carries `in_the_news` (headline, what was reported, his
  take). He can discuss real events, knows only what was reported, and says so if you
  mention something he hasn't seen.
- **Weather:** with the town signal configured, the real weather over the town becomes his
  weather.

**When.** A live world (the web server) gets today's news and weather whatever its
calendar says. A fast simulation only gets them if its date is within a few days of today.

## His family (`application/family.py`)

Mum (Helen), Dad (Richard) and his older brother Tom, with Jess and Isla, live in Kent and
London. They are authored background in persona `patrick-blend-v3`.

- **Mum** rings most Sunday evenings; Dad sometimes comes on the line.
- **Tom** keeps the family chat going (photos of Isla, memes, articles from Dad) and rings
  every few weeks.
- **Patrick** rings home when he's missing them, more often when he's lonely.

He can miss a call and owe one back. He usually rings back within a day or two; if not,
"it's been days" is felt as care slipping. Birthdays, Mothering Sunday, Father's Day and the
anniversary can be remembered, or forgotten and apologised for the next day. On his own
birthday, they always ring.

Their lives go on in short storylines he hears about one step at a time, at least two weeks
apart: Dad's knee operation, Tom's move to Kent, Mum's exhibition. There are also the
things that come round every year, like Mum's seed trays and Dad changing forty clocks.

**Christmas at home.** In early December Mum asks, and he books the train home. That is a
recorded agreement, which registers his parents' house in Wye as a place a train ride away.
It is hidden from the town map and from what he knows of Alderwick. He travels after his
last shift and stays from the 23rd to the 27th. He eats at the family table (no cost, no
stock), with Christmas Eve, Christmas Day and a Boxing Day walk or clock restoration, and
sometimes Dad's questions about his plans. Sleeping there counts as being there. Mum rings
to check he got home.

## Going home (`application/family_visits.py`)

- **Easter:** agreed on Mothering Sunday, Good Friday to Easter Monday.
- **The August bank holiday weekend:** booked about three weeks ahead.

Both fall on days the workshop is shut, so no shifts are missed. If money is too tight
for the train, he says so. Mum offers to pay; he says no, and wishes he hadn't.

**Dad's heart scare.** Once, somewhere between 14 and 19 months in, Mum rings late:

- Dad's in hospital with chest pains. They think he's all right.
- Patrick rings Ellis, who tells him to go; the shifts while he's away are cancelled.
- He takes the first train and stays three nights: the ward, then Dad home, then late
  nights in the kitchen with Mum.
- A fortnight later Dad is on the mend and complaining about porridge.

It's the first time he has thought about his parents getting old, and he starts ringing
more.

## What he knows about you (`application/user_notes.py`)

On each evening after you talked, he may note up to four things about your life in his own
words (for example, "You start the new job on Monday").

- **Grounded:** each note must quote something you actually said, or it is rejected.
- **Fallible:** work, family, pets, home and interests stay with him; other details fade
  after two months.
- **Follow-ups:** a follow-up comes due when the thing happens, and he may ask how it went.
  If you're a friend and outreach is on, he may send a short "Been meaning to ask…" message
  a day or more after it's due.

Capability: `pathos_user_notes`, which falls back to the `reflection` route.

## Asking what you think (`application/advice.py`)

When something in his life needs deciding, he wants your view if you're a friend (or you've
talked on three or more days). The questions are:

- whether to take on the workshop;
- whether to move flat;
- whether to message a friend he's fallen out with;
- whether to say something to someone he likes.

He brings it up next time you talk (`wants_your_view_on`, not repeated for three days after
he's asked). If outreach is on and you haven't talked for a day, he messages to ask.

Each evening the `pathos_advice_heard` role reads what you've said since he asked. It records
whether you leaned for, against or were unsure, quoting your words (`advice.heard`). This
role is routed like `reflection` unless given its own route.

Your view then weighs in when he decides: it shifts the workshop decision, makes him more or
less likely to reach out or ask someone out, and can talk him out of moving. It's one voice
among his own values. He can still go the other way, and his memory of deciding says whether
he took your advice.

## Running jokes (`application/in_jokes.py`)

- **With friends:** after an evening talking with a friend (level 3+), there's sometimes a new
  running joke: the otter question at the quiz, the kettle nobody's allowed to descale.
  There's at most one new joke a week, and at most three per friend.
- **Callbacks:** now and then (not the same joke within two months) a joke comes back when they're together ("Rowan brought up the
  goose standoff again"). Both the joke and the callback count as small shared moments.
- **With you:** the evening notes role may spot a moment in your conversation that made you
  both laugh, give it a label and quote it (`running_joke`). The conversation context
  carries `running_jokes_with_you`, so he can call back to them.

## Memories that come back (`application/surfacing.py`)

He remembers when something sets it off, not only when asked. There are three triggers:

- **A place:** a place where something that mattered happened (importance 0.6+, over a month
  ago) can bring it back while he's there.
- **An anniversary:** a year (or two, or three) to the day since something important, he
  remembers it in the evening.
- **Missing someone:** now and then he misses a close friend who has moved away.
- **An evening with someone:** after time with a friend, something the two of them share
  can come back.

Only moments from his own story come back (family, friends, love, work, home; not routine or
passing faces): at most one a day and two a week, and the same one not again for a
year, preferring ones that haven't come back before. The self-context shows what's come
back to him in the last few days (`came_back_to_him_lately`).

## "Fine, yeah" (`application/masking.py`)

When you ask how he is and something's weighing on him, he doesn't always say. That could
be Dad in hospital, a falling-out, a break-up, a friend just gone, a friend's worry, or
just a low patch he can't explain.

How likely he is to be honest depends on your bond:

| Your bond | Chance he's honest |
|---|---|
| Closest | 95% |
| Close | 70% |
| Friend | 40% |
| Not yet a friend | about 1 in 8 |

If he brushed it off and you're a friend, then the next time you talk on a later day, he
owns up. Telling you, either time, deepens the friendship. The conversation context carries
`how_he_really_is` or `owes_honesty`, and a real model is told to follow it.

## Books, series, music (`application/media.py`)

He is usually partway through a book (a chapter before bed), a series (an episode on a free
evening) and an album (on repeat for a week or two). These are real works that fit his
interests; only titles and creators are used.

- **Where books come from:** new books come off his shelf, then from the library and
  second-hand shops once he knows them.
- **What he thinks of them:** a stable temperament for each work plus how it fits him
  decides his opinion. He may give up a third of the way in ("life's too short").
- **Tastes:** loving two works of the same kind becomes a taste.

## The turning year (`application/seasons.py`)

- **Light:** dark winter evenings pull his mood a little low and tire him slightly faster;
  long summer evenings lift him.
- **The clocks:** they go forward in March (an hour's sleep lost) and back in October.
- **Holidays:** England and Wales bank holidays, with substitute days, close the workshop,
  as do Christmas Eve to New Year.
- **Moments of the year:** the shortest and longest days, the first light evening, the
  first frost and the first warm day are each noticed once a year.
- **His own anniversaries:** a year in Alderwick, at the workshop, and since someone became
  a friend.

## Falling short (`application/imperfection.py`)

- **Putting things off:** on a tired or low day, with lower follow-through, he puts off a
  plan he made for himself.
- **Late nights:** on a restless or lonely evening he's on his phone till gone one, at most
  twice a week, and is more tired the next day.
- **Being short with people:** exhausted, he can snap at someone over nothing. If he cares
  enough, he apologises the next day, which counts as a small repair.

Each lapse is lived evidence, so questions about himself can grow out of them. Patterns seen
twice in a month appear in his self-context as things he'd like to change.

## Where work goes (`application/work_arc.py`)

The job's terms live in its agreement history, and each shift carries the wage it was booked
at.

- **After three months and forty good shifts,** Ellis gives him a raise.
- **Later, Ellis offers a fifth day.** He takes it or keeps his Wednesdays, depending on how
  much craft, money and free time matter to who he has become.
- **After a year, if Ellis is a close friend,** Ellis asks whether he'd ever think about
  taking the workshop on.
- **A month later he answers**, depending on how much craft and independence matter to
  him, how close he is to Ellis, and whether money is too tight to risk it.
  - **Yes:** Ellis writes a plan on the back of an invoice. Four months later Patrick is
    running things day to day: five days a week at £13.50 an hour. About ten months
    after that he gets the keys (£15 an hour). Ellis still pops in.
  - **No:** Ellis takes on an apprentice, and Patrick is the one teaching him.

## Everyday money (`application/spending.py`)

Rent and food were always paid for; now the rest of an ordinary week is too.

- **Where he goes costs something:** most visits to a café, pub, shop, cinema or venue
  come with a small spend, at most once a day per place, and no coffee on top of a café
  meal.
- **Every Saturday:** £16–36 of bits and bobs; every seventh week a haircut.
- **On the 3rd of each month:** the phone bill, which is owed even when money is tight.
- **Family:** a card and present for each occasion he marks, even late; at Christmas the
  train fare once it's agreed and presents bought in town beforehand.
- **Thrift:** he skips extras unless next week's rent and £30 would be left. With less
  than two weeks' rent put by, the weekly bits shrink to the basics and the haircut
  waits.

## His friends' lives (`application/friends_lives.py`)

His friends' lives go on without him, and change his weeks.

- **What happens:** new jobs, someone new, a baby (after a partner of nine months or
  more, for friends who want children), a parent unwell, a half-marathon or a new dog.
  Sometimes a friend moves to another city.
- **How often:** about one turn every eight months per friend he's reasonably close to,
  and never more than one piece of news a week. Nothing happens to people he barely
  knows.
- **What it changes:**
  - A friend with a newborn (four months) or a family worry isn't free for invitations
    or visits.
  - He messages to ask how things are when a friend is worried; that deepens a
    friendship.
  - He buys a present for a new baby and a leaving card.
- **Moving away:** announced about three weeks ahead. The leaving do is a Friday or
  Saturday night at the Crown, where the friend joins him. The next day they are gone:
  off the map for good, with no more invitations, visits or bumping into them. Phone
  calls still happen, and a close friend stays close (friendship from level 6 never
  fades).
- **Facts:** whether a friend wants children is fixed per person; whether they'd move is
  rolled per year, so any friend might eventually go.
- **Where it shows:** `whats_going_on_with_his_friends` in his self-context, and his
  answer when you ask about his friends.

## The year with friends (`application/social_calendar.py`)

- **Friends' birthdays:** once someone is a real friend (level 4 and up) he knows their
  birthday, a fixed fact about them. On the day he messages; for a close friend there's a
  card and a pint. Sometimes it slips his mind and two days later he sends something
  sheepish.
- **His birthday (27 October):** with two or more friends free, a week before, they decide
  it's drinks at the Crown on the night, and messages come in all day.
- **Bonfire night:** fireworks on the rec on the Saturday nearest the fifth, with a friend
  if one's free, sometimes alone.
- **New Year's Eve:** the Crown with friends, or a quiet night in.

Each plan (`calendar.plan`) causes its booking, and he remembers the evening if he was there.

## Friends far away (`application/far_friends.py`)

- **Calls:** friends who've moved away ring or get rung on Sunday evenings
  (`friend.kept_in_touch`). With a close friend that's every few weeks. With a newer one it
  gets rarer as the months pass. Each call is a small shared moment, so close friendships
  hold at a distance.
- **A visit:** two to nine months after a close friend moves, if he can afford the train,
  he goes to stay for a weekend in their new city (`visiting_a_friend`). He remembers
  Saturday night and the hungover breakfast.

## A friend's wedding (`application/friends_lives.py`)

- **Engagement:** a friend with a partner of eighteen months or more may get engaged.
- **Invitation:** about ten months later the invitation comes. If they're close (level 4
  and up) he's invited: a Saturday booked at the community hall and a £40 present.
- **The day:** he remembers the wedding if he was there, or the photos if he wasn't.

## Lying awake (`application/sleep_trouble.py`)

At two in the morning, if he's asleep:
- **Worry:** if something's weighing on him (the same things he'd hide behind "fine"), he may
  wake and not get back off. Money keeps him up now and then when he's down to less than a
  week's rent.
- **Excitement:** the night before something big (a wedding, moving day, a trip, a date),
  he may lie awake for better reasons.
- **Effect:** it costs rest the next day, happens at most twice a week, and his self-context
  counts `restless_nights_this_week`.

## Falling out (`application/falling_out.py`)

- **How it starts:** rarely, it goes wrong with a friend he has known at least three
  months. It's about once in several years, a little likelier just after he lets them
  down, and never twice within six months. The bond shows as strained.
- **Making up:** over the next weeks he may reach out. How soon depends on how much care
  and reliability matter to him.
  - A close friend (level 6 and up) always comes back round.
  - With a newer friend the first try works more often than not.
  - If they don't reply, he leaves it three weeks before trying again.
  - Making up counts as a deepening moment.
- **When it doesn't mend:** after three months they "don't really speak now". That
  friend stops inviting him or coming round, and the friendship fades with absence like
  any unkept one.

## A week away (`application/holiday.py`)

Ellis shuts the workshop Monday to Friday of the first full week of August, so there are no
shifts that week.

On the second Sunday in May, Patrick books a week away for the shutdown if he can afford it
and still keep £400 behind him:
- **Who with:** whoever he's properly together with; otherwise, more often than not, his
  closest friend; otherwise on his own.
- **Where:** a cottage near Coniston, a caravan in Pembrokeshire, a B&B in
  Wells-next-the-Sea, or a flat in Lisbon.
- **Cost:** about £520 alone, or £340 when shared.
- **The week:** a stay away (`on_holiday`) with three moments he remembers.

If money's tight he stays home and notices he didn't go.

When there's money put by (sixteen weeks' rent or more), he's a little less careful. The
weekly bits and bobs cost a quarter more, and once a month there's a treat: boots, a
record, a takeaway and a film.

## Moving flat (`application/home_move.py`)

- **When:** after 400 days or more, with about £900 put by, he starts looking (some
  Sunday evening). His flat is fine, but the damp in the bathroom is winning.
- **Finding one:** three weeks or more later he finds a place (£140 a week) and pays a
  four-week deposit once he can do it without going short.
- **Moving day:** a Saturday two weeks on, with his closest available friend helping.
  From then on the new rent is what's charged each week.
- **With a partner:** if he has been properly together with someone for nine months or
  more, it's moving in together instead: somewhere bigger, and his half is £95.
- **Not again** for at least three years.

## An evening class (`application/evening_course.py`)

- **When:** on the first Sunday of September, some years, he signs up for a community-hall
  class. Never in his first eight months, at most every other year, and only if the £120
  fee won't leave him short.
- **Which class:** chosen with a lean from who he is:
  - craft: furniture restoration;
  - curiosity: Alderwick's history;
  - if he has come to love drawing: life drawing.
- **The term:** ten Tuesday evenings. On a day he's worn out or low he may skip one.
- **How it ends:** seven or more classes and he finishes, proud of what he made. Fewer, and
  it's one more thing he started and didn't finish, which he notices.

## His body over time (`application/body.py`)

- **Knocks at the bench:** now and then during a shift he cuts his thumb on a chisel,
  burns his fingers on the soldering iron, traps a finger in the vice or pulls his back
  lifting a radiogram. That's about one or two a year, a little likelier when he's short of
  sleep, and never two within six weeks. It stays sore for four to seven days
  (`sore_at_the_moment`), dents his mood, and costs a few pounds in plasters or ibuprofen.
- **Hangovers:** the morning after three hours or more at the Crown, being out at the pub,
  music room or community hall past eleven, or a friend's leaving do, he may wake
  hungover. The chance is about a third, or 60% after a leaving do. It costs some rest and
  he remembers it ruefully.
- **Fitness:** each week (`body.week`) his hours at the park, riverside, hill path, nature
  path, dog walk and allotments, plus time walking between places, move a slow fitness
  level toward that week's. About six hours a week keeps him fit. Crossing into fit is a
  memory ("Walked up Westfield Hill without stopping for the first time"), and so is
  falling out of shape ("Out of breath on the stairs").
- **The dentist:** about nine months after he arrives (and after each check-up) he
  remembers he should go, and "putting off booking the dentist" joins the patterns he'd
  like to change. Weeks later (within about three months) he rings and books, which is his
  decision and causes the booking. He goes on a weekday he isn't working. It's usually fine
  (£27.40), sometimes a filling (£75.30). If he misses it he books again.
- **Colds** are the existing wellbeing episodes. From November to February a spell is more
  often "under the weather".

## Views on the town (`application/town_issues.py`)

Ordinary local rows that he has a view on.

- **The issues:** five authored ones: flats in the old mill, cutting the 12 bus, a coffee
  chain on Market Row, a 20mph zone through the old town, and cutting the library's hours.
  Each has a case for and against, and each side speaks to some of his values.
- **When:** the first comes up after about three to five months in town, then roughly one
  every four to six months, never two at once. He hears about it from the post office
  noticeboard, the Advertiser or someone at the café (`town.issue`, stage `raised`).
- **His view:** a lean worked out from his current values, plus a little replay-stable
  noise. It is for, against or torn, and held with some strength (`opinion.formed`).
- **The public meeting:** a Wednesday evening at the council rooms three to five weeks
  later. If he cares enough and is curious enough, he decides to go
  (`town.meeting_planned`, which the booking cites). If he goes and the room leans the
  other way, he may come out less sure, or on the other side (`opinion.changed`).
- **Ellis:** has a fixed view on each issue and is usually against things. Over a lunch
  at the workshop they may talk it over (`opinion.discussed`). Ellis can wear him down.
- **The outcome:** six to twelve weeks after the meeting the council decides
  (`town.issue`, stage `decided`). He is pleased or disappointed, as much as he cared
  (`opinion.outcome`, which moves his mood). If he was torn, he is unbothered.
- **Where it shows:** `views_on_the_town` in his self-context lists the live issue and
  those decided in the last six months, with his view in his own words. The stand-in
  answers questions about the town, the council or a named issue from it.

## Small touches of home and habit (`application/small_touches.py`)

- **A cat (`pet.event`):**
  - **When:** two weeks after he moves flat, or after 18 months settled if he never
    moves (not while a move is under way). On a Sunday he may go to the rescue "just to
    look".
  - **How likely:** likelier the lonelier he is and the more care matters to him. He
    needs the £85 fee plus two weeks' rent in the bank. Only ever one cat.
  - **The cat:** its name, looks, temperament and he/she are replay-stable facts, rolled
    from its id.
  - **Cat moments:** on an evening at home, about one every couple of weeks (a 5am
    wake-up, sitting on his book, a leaf by his pillow). Each lifts connection a little.
  - **Costs:** food and litter every Saturday (£8.50), and a vet's bill about twice a year.
    Both are everyday spending.
  - **Trips to Wye:** a friend (or the neighbour downstairs) feeds the cat, and he mentions
    it once.
- **Houseplants (`plant.event`):**
  - **Buying:** a plant now and then, and very likely in the first weeks after a move.
  - **Dying:** each week he's worn out or has been away, it's likelier to die ("Another
    one. I'm a menace."). After a death he waits two months before buying another.
  - **Thriving:** a plant that lasts ten weeks thrives and stays, a small point of pride.
  - **How often:** about two to four plant events a year.
- **The usual (`habit.regular`):**
  - **Being known:** a visit is a day he arrives at Juniper Café. After ten visits Mara
    says "The usual?" once. From then on his order (a fixed drink and a fixed
    scone-or-cake) is in his self-context.
  - **After months away:** if he stays away 100 days or more, on his return Mara either
    asks where he's been or has forgotten. If she has forgotten, he earns the usual again
    over ten more visits.
- **Where it shows:** `at_home` (cat and plants) and `his_usual` in his self-context. The
  stand-in answers questions about pets, plants, his flat and his usual from them.

## Romance (`application/romance.py`)

Rare, slow and uncertain.

- **Who:** he may be drawn to someone he has got to know. It is never the person talking
  with him in the app, never his boss, and never family.
- **Most crushes fade unspoken.** With enough nerve (sociability, mood) he asks: yes or a
  kind no.
- **Dates** are agreed Friday or Saturday evenings out at places he knows, which he travels
  to and remembers after. After six, it becomes "properly together" or quietly ends.
- **Where people meet:** a friend he has got to know, or a regular he has chatted with a
  few times. And now and then, on a quiet Sunday, a close friend offers to set him up with
  someone they know. He may say no. A set-up is one evening out, which becomes a second
  date or doesn't.
- **Not everything lasts:** about 40% of relationships that become "together" end three to
  nine months in (`broke_up`). That hits hard, and he doesn't look for anyone for six
  months.
- **Hidden facts:** whether someone sparks, whether it's mutual and whether it lasts are
  replay-stable facts about each pair.
- **Why this was reworked:** the spark was a fixed fact per person, and none of the authored
  cast had it, so in the standard world romance could never happen.
- **Orientation:** his is not specified in his authored background, so it is left open.
  People he is set up with have names that could belong to anyone, and are "they".

## People, tastes and the town

These systems are described in their own documents:

- friendship depth and bonds: [SELFHOOD.md](SELFHOOD.md) §9;
- tastes: [SELFHOOD.md](SELFHOOD.md) §8;
- the latent town of 8,500 met one at a time: [ALDERWICK.md](ALDERWICK.md).

## Where it shows

- **Self-context** (voice, reflection, dreams, planning): `family`, `people_he_says_hello_to`,
  `reading_watching_listening`, `time_of_year`, `patterns_he_would_like_to_change`, `work`, `money`,
  `love_life`, `body`, `views_on_the_town`, `home`, `evening_class`,
  `whats_going_on_with_his_friends`, `fallings_out`, `running_jokes`,
  `came_back_to_him_lately`. The conversation context also gets `what_he_knows_about_you`,
  `things_to_ask_you_about`, `wants_your_view_on`, `what_you_advised_lately`,
  `running_jokes_with_you`, and `how_he_really_is` or `owes_honesty` when they apply.
  Home life shows as `at_home` (cat, plants) and `his_usual` (his café order).
- **The Becoming view:** panels for his people, his family, what he knows about you,
  reading, watching and listening, and work, love and what he'd change.
