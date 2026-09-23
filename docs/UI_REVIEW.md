# Hearth-inspired UI pass

Follow-up: [Lived-day integration](LIVED_DAY_2026_09_08.md) now supplies unread
indicators, stable message-node updates, small-screen day context, activity stages
and journey inspection. Desktop/mobile browser checks and a disposable preview
accompany that pass; the original review below is retained as history.

Reference: Enve Book Player's `docs/ui/DESIGN.md` and `Hearth.swift`, not its
legacy ThemeManager. Eidos adopts the Ink palette (#0C0A09, #191512,
#F0E9DC, #A99F92), ember #F5921A, serif display type, flat warm surfaces,
and rounded cards. This pass is dark-only; no claim of full Paper/System
theme parity. Enve source was not modified.

Claude CLI completed a read-only review of Eidos's three web files. It did
not run the browser. Findings: missing unread/proactive-message indicators,
forced scrolling, contradictory paused/live text, interrupted-send feedback,
and whole-log rebuilding during paced replies. It also noted the lack of a
mobile alternative for the hidden observer sidebar and incomplete CSS tokens.

Addressed in this pass: removed unconditional scroll-to-bottom while reading
the conversation, prioritized paused state over live presence, clarified the
paused/interrupted compose footer, used a non-loading disabled cursor, and
updated outreach wording. No artificial sample messages were inserted.

Verification: 14 web tests passed and JavaScript syntax checked. Codex inspected
the deployed conversation visually and expanded its real message settings;
the enabled outreach control and paused footer matched runtime state. Broader
responsive, unread-state, and live-message accessibility work remains.
