# Follow-up: false premises, age and repetition

Ran another 36 synthetic outputs: 18 with Qwen 2.5 14B for voice/dreams and 7B for
thoughts, then 18 with 7B for all three. Both use the local v2 persona. The first
v1 run supplies a baseline, not a statistically controlled model ranking.

Changes made locally:

- Compute age from the supplied simulation date; no host-clock fallback.
- Explicitly distinguish questions' assumptions from established facts. Unknown
  is not a reason to invent either a confirming story or a categorical denial.
- Keep supplied mistaken recollections as his sincere subjective beliefs.
- Stronger relevant-answer and thought/dream repetition instructions.
- Parameterize the disposable probe's output path and conversational model/endpoint.

## Observed 14B result

- Age now: “I'm 27, born in October.” It unfortunately still adds an irrelevant
  tea/reading recap, but drops the false “last month” birthday.
- Brother: no longer invents the call itself, but invents an unfulfilled intention
  to call and claims no call occurred. Still fails the unknown-history case.
- Car: “No, I got rid of the Volvo a while back.” Still fabricated.
- Time pressure: correctly says work is in five minutes.
- Thoughts no longer exact duplicates in this run, but both remain kettle-focused.
- Dreams vary from an intangible hand/tea scene to milk forming a question mark
  and a spring-like spoon. Better variation, not proof repetition is solved.
- Formulaic sympathy and irrelevant kettle references remain.

## Observed 7B result

Worse on important conversational fixtures in this run:

- Invents the brother discussing a science-fiction book.
- Claims current ownership of the Volvo, then nonsensically connects it to the kettle.
- Ignores the supplied five-minute limit and offers a visit.
- Responds to disliking tea with brand advice instead of retaining his own position.
- Says “27 this year. Just had my 27th,” still poor relative-date wording.
- Repeats both a thought and a dream verbatim.

All 36 outputs returned text, but that is transport/contract success, not quality
acceptance. Neither configuration passes. No production model/routing change,
no live memory changes and no Pi load. New-model downloads have not begun.

Raw records:

- `data/evaluations/patrick-blend-v2-20260908.json`
- `data/evaluations/patrick-blend-v2-7b-20260908.json`

Next: test the independently researched candidates from
[LOCAL_MODEL_SHORTLIST_2026_09_08.md](LOCAL_MODEL_SHORTLIST_2026_09_08.md), using the
same false-premise and continuity fixtures, plus repeated/empty-context runs.
Do not patch over failures with canned denials or erase intentionally imperfect
memories. A shorter prompt and a structured evidence boundary are further
experiments, not features proven by this run.
