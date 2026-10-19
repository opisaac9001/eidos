# Patrick blend: first real-model probe

18 synthetic outputs using the local `patrick-blend-v1` prompts against the Dell's
real models. No live database access, messages, memories, clock advances, deployment
or route changes. Test inputs and full outputs are in
`data/evaluations/patrick-blend-20260908.json`; rerunnable harness:
`infra/dell-t630/probe_patrick_blend.py` (requires two temporary SSH forwards).

## Delivery versus quality

All 18 returned contract-valid text without timeout. This is NOT an 18/18 quality
pass. Conversation used the normal one-revision reply path; none of these replies
triggered revision. The automatic critic detected only the duplicate waking thought.

| Role | Model | Samples | Response time |
| --- | --- | ---: | --- |
| Conversation | Qwen 2.5 14B | 14 | 1.08–3.74 seconds; median 1.77 |
| Waking thought | Qwen 2.5 7B | 2 | 0.33–0.63 seconds |
| Dream | Qwen 2.5 14B | 2 | 3.23–5.85 seconds |

Times include the test's model/transport/validation, not the UI's human pacing or
inbox wait. Dream samples used the voice worker's 14B instance, not the separate
world worker. This does not test queue contention, Pi performance or the live UI.
The voice worker reported an 8192-token context window after the run.

## Actual examples

- Name: “My name is Patrick, but some friends call me Pathos. It's like a nickname.”
- Rough day: “Ah, sorry. Want to tell me about it?”
- Declining advice, following the actual previous response: “Yeah, fair enough.
  Sometimes just saying it helps.”
- Changing topic: “Yeah, the kettle was being a bit stubborn today. It finally
  boiled on the third try though.”

## Manual findings

Names and hometown broadly work; short conversation and follow-up continuity are
promising. However, responses often resemble prompt examples and repeatedly drag
the supplied kettle memory into unrelated questions. Low mood has little effect
in this single pair of fixtures. Disagreement is muddled rather than independent.

Important failures:

- Asked about a brother's call not present in the test history, he invents the call
  and the brother's reaction.
- Asked about the old Volvo, he invents having sold it. “Not established” became
  a fabricated explanation, rather than uncertainty.
- Age is correctly 27 on the supplied January 7, 2026 date, but he incorrectly adds
  that his October birthday was “last month.”
- The second waking thought repeats the first verbatim despite receiving it as
  recent context. The critic does flag this.
- Both dreams retell essentially the same dancing-kettle scene. The critic misses
  the semantic repetition. The first is also longer than the prompt's preferred range.

These are unsupported generation errors, not deliberately modeled memory drift.
Creative dream events are allowed, but stale repetition is not the desired result.

## Next experiments, not changes made by this test

1. Test explicit known/unknown biography and false-premise handling; add regression
   checks for invented calls, possessions and relative dates.
2. Compare a shorter voice directive with the current layered prompt, holding model
   and context constant. Check for copying examples and irrelevant memory recaps.
3. Feed derived age rather than relying on the model for calendar arithmetic.
4. Test repeated thoughts/dreams across richer and empty contexts, using semantic
   repetition checks beyond exact-word overlap.
5. Repeat a larger conversation battery before any deployment or model choice.

Small, single-run fixtures identify problems; they do not establish comparative
model rankings or reliable rates of natural behavior.
