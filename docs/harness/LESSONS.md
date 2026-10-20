# Harness lessons

Changes tried on how the model roles are asked, measured on real recorded moments with `eidos harness-probe`, newest last.

## 2026-10-20: firmament, narrate-and-ground

- **Why:** On 20 live moments 55% of lines were turned away: encounters written as a bare line of dialogue without the person in them, and people asking after 'that project Ellis mentioned', which doesn't exist.
- **Samples:** 20
- **Turned away:** 0.575 now, 0.2 with the change
- **Problems now:** {'missing_actor': 11, 'invented_thing': 8, 'claims_his_project': 3, 'repeat': 2}
- **Problems with it:** {'repeat': 3, 'claims_his_project': 3, 'missing_actor': 2, 'too_long': 1}
- **Verdict:** adopt

## 2026-10-20: firmament, proposed-forbid-atlas-invention

- **Why:** Explicitly bans inventing the non-existent 'atlas of neighbourhood sounds' project that caused repeated rejections.
- **Samples:** 14
- **Turned away:** 0.143 now, 0.286 with the change
- **Problems now:** {'claims_his_project': 2, 'repeat': 1}
- **Problems with it:** {'invented_thing': 2, 'repeat': 1, 'claims_his_project': 1}
- **Verdict:** keep current: worse

## 2026-10-20: firmament, proposed-ground-in-shared-topic

- **Why:** Ensures the dialogue stays strictly within the provided scene_topic rather than drifting into unverified personal projects.
- **Samples:** 14
- **Turned away:** 0.143 now, 0.357 with the change
- **Problems now:** {'claims_his_project': 2, 'repeat': 1}
- **Problems with it:** {'repeat': 2, 'claims_his_project': 2, 'invented_thing': 2}
- **Verdict:** keep current: worse

## 2026-10-20: firmament, proposed-no-unsourced-details

- **Why:** Prevents adding invented details to Patrick's life or relationships that contradict the provided context.
- **Samples:** 14
- **Turned away:** 0.143 now, 0.214 with the change
- **Problems now:** {'claims_his_project': 2, 'repeat': 1}
- **Problems with it:** {'gives_away_his_project': 2, 'claims_his_project': 1, 'repeat': 1}
- **Verdict:** keep current: worse

## 2026-10-20: firmament, proposed-forbid-atlas-invention

- **Why:** Explicitly bans any speaker other than Patrick from claiming or discussing his specific 'atlas of neighbourhood sounds' project, preventing the model from assigning it to others.
- **Samples:** 14
- **Turned away:** 0.214 now, 0.214 with the change
- **Problems now:** {'claims_his_project': 2, 'repeat': 1, 'missing_actor': 1}
- **Problems with it:** {'gives_away_his_project': 1, 'claims_his_project': 1, 'repeat': 1, 'invented_thing': 1}
- **Verdict:** keep current: no clear difference

## 2026-10-20: firmament, proposed-ground-in-shared-topic

- **Why:** Ensures dialogue stays strictly within the provided scene_topic to prevent drifting into unverified details or repeating previous turns.
- **Samples:** 14
- **Turned away:** 0.214 now, 0.214 with the change
- **Problems now:** {'claims_his_project': 2, 'repeat': 1, 'missing_actor': 1}
- **Problems with it:** {'repeat': 1, 'invented_thing': 1, 'claims_his_project': 1}
- **Verdict:** keep current: no clear difference

## 2026-10-20: firmament, proposed-require-actor-in-narration

- **Why:** Prevents narration from omitting the person's name by mandating that every third-person summary explicitly names the individual involved.
- **Samples:** 14
- **Turned away:** 0.214 now, 0.214 with the change
- **Problems now:** {'claims_his_project': 2, 'repeat': 1, 'missing_actor': 1}
- **Problems with it:** {'repeat': 2, 'claims_his_project': 1}
- **Verdict:** keep current: no clear difference

