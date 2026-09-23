# Voluntary in-app contact

Outreach is enabled for the current deployment. There is no fixed cooldown or
one-message-per-day limit. Legacy configuration events containing a 72-hour
interval replay with the retired interval normalized to zero.

A fresh thought linked to a user-conversation memory becomes a candidate.
Pathos receives that subjective thought and the last twelve conversation
messages, and chooses between writing an actual message and `[KEEP_PRIVATE]`.
The latter is recorded as `outreach.kept_private` and never delivered as text.
Invitations remain conversational proposals, not automatically booked activities
or accepted visits. A thought is considered only once, including failed or
rejected attempts. Quiet hours, awake status, pending user replies, and live
visit checks still apply. Model guidance discourages repeated invitations and
chasing unanswered messages; this is not a hard guarantee against repetition.

Tests cover legacy replay, multiple distinct same-day thoughts, private choices,
deduplication, quiet hours, stale thoughts, and pressure rejection. Naturalness
and action selection still need longer live observation. The model does not
yet identify every possible association with the user: eligibility currently
requires a thought's source-memory link to a user conversation.
