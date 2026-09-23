"use strict";
const $ = (id) => document.getElementById(id);
const operatorMode = window.location.pathname === "/operator";
// The operator link carries a one-time token; keep it for this tab and tidy the address bar.
let operatorToken = null;
try {
  const fromLink = new URLSearchParams(window.location.search).get("token");
  if (fromLink) {
    sessionStorage.setItem("eidos-operator-token", fromLink);
    history.replaceState(null, "", window.location.pathname + window.location.hash);
  }
  operatorToken = sessionStorage.getItem("eidos-operator-token");
} catch (_) {
  /* Storage is optional; operator controls will explain that they need the token. */
}
const ordinaryViews = new Set([
  "observatory",
  "world",
  "conversation",
  "memories",
  "self",
]);
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ],
  );
const labels = {
  "thought.recorded": "INNER MONOLOGUE",
  "npc.encountered": "AN ENCOUNTER",
  "world.weather": "THE WORLD OUTSIDE",
  "external_signal.observed": "REAL-TOWN SIGNAL",
  "external_signal.poll_failed": "SIGNAL UNAVAILABLE",
  "world.signal_inspiration": "CREATIVE INSPIRATION",
  "world_event.signal_linked": "INSPIRED FICTION",
  "world_event.occurred": "IN THE NEIGHBORHOOD",
  "world_thread.opened": "A NEIGHBORHOOD THREAD BEGAN",
  "world_thread.progressed": "A NEIGHBORHOOD THREAD CONTINUED",
  "world_thread.extended": "A NEIGHBORHOOD THREAD DEEPENED",
  "world_thread.resolved": "A NEIGHBORHOOD THREAD SETTLED",
  "world.expansion_accepted": "THE WORLD GREW",
  "world.expansion_rejected": "WORLD ADDITION DECLINED",
  "world.pack_imported": "A WORLD RELEASE WAS ADDED",
  "reflection.recorded": "EVENING REFLECTION",
  "dream.recorded": "A DREAM · NOT WORLD HISTORY",
  "day.summarized": "THE DAYBOOK",
  "memory.recorded": "A MEMORY FORMED",
  "role.failed": "PERFORMER ERROR",
  "memory.recovered": "SOURCE ARCHIVE RECOVERY",
  "memory.retention_reviewed": "MEMORY RETENTION REVIEW",
  "memory.archived": "MEMORY MOVED TO COLD ARCHIVE",
  "request.made": "A REQUEST",
  "social.request_opened": "REQUEST OPENED",
  "social.request_negotiated": "TERMS NEGOTIATED",
  "social.request_accepted": "TERMS ACCEPTED",
  "social.request_declined": "REQUEST DECLINED",
  "invitation.made": "AN INVITATION",
  "invitation.accepted": "INVITATION ACCEPTED",
  "invitation.declined": "INVITATION DECLINED",
  "social.activity_completed": "TIME TOGETHER",
  "scene.interrupted": "CONVERSATION PAUSED",
  "scene.resumed": "CONVERSATION RESUMED",
  "scene.resumption_decided": "AFTER THE INTERRUPTION",
  "visit.ended": "VISIT ENDED",
  "phone.call_received": "PHONE CALL",
  "phone.call_answered": "CALL ANSWERED",
  "phone.call_declined": "CALL DECLINED",
  "phone.call_completed": "CALL ENDED",
  "phone.callback_scheduled": "CALLBACK PLANNED",
  "phone.callback_completed": "CALLBACK MADE",
  "visitor.arrived": "SOMEONE AT THE DOOR",
  "visitor.admitted": "A VISITOR CAME IN",
  "visitor.deferred": "VISIT DEFERRED",
  "visitor.missed": "VISITOR MISSED",
  "visitor.departed": "VISITOR LEFT",
  "delivery.scheduled": "DELIVERY EXPECTED",
  "delivery.redelivery_scheduled": "REDELIVERY EXPECTED",
  "delivery.arrived": "DELIVERY AT THE DOOR",
  "delivery.missed": "DELIVERY MISSED",
  "delivery.received": "DELIVERY RECEIVED",
  "delivery.returned": "DELIVERY RETURNED",
  "incident.attention_decided": "A CHOICE TO RESPOND",
  "incident.response_started": "RESPONDING NEARBY",
  "incident.response_declined": "RESPONSE DECLINED",
  "incident.response_completed": "RESPONSE COMPLETED",
  "incident.response_abandoned": "RESPONSE LEFT UNFINISHED",
  "incident.resource_used": "A RESOURCE WAS USED",
  "incident.shared_aftermath": "A SHARED AFTERMATH",
  "speech.delivered": "SOMETHING SAID",
  "travel.completed": "ARRIVED",
  "intention.adopted": "AN INTENTION FORMED",
  "intention.completed": "AN INTENTION COMPLETED",
  "action.accepted": "ACTION VALIDATED",
  "action.rejected": "ACTION COULD NOT HAPPEN",
  "activity.completed": "PRACTICE COMPLETED",
  "agency.activity_proposed": "AN IDEA OCCURRED",
  "agency.activity_accepted": "A PERSONAL PLAN FORMED",
  "agency.activity_rejected": "AN IDEA DID NOT FIT",
  "agency.activity_realized": "A PERSONAL PLAN HAPPENED",
  "agency.activity_missed": "A PERSONAL PLAN FELL THROUGH",
  "prospective_memory.lapsed": "A SMALL PLAN SLIPPED HIS MIND",
  "self_project.proposed": "A PROJECT IDEA OCCURRED",
  "self_project.accepted": "A NEW PROJECT BEGAN",
  "self_project.rejected": "A PROJECT DID NOT FIT",
  "self_project.completed": "A PROJECT WAS COMPLETED",
  "self_project.failed": "A PROJECT FELL APART",
  "self_project.step_failed": "A PROJECT STEP FAILED",
  "preference.emerged": "A PREFERENCE TOOK SHAPE",
  "preference.retired": "A PREFERENCE FADED",
  "trait.adjusted": "A TENDENCY SHIFTED",
  "self_concept.formed": "A SELF-UNDERSTANDING FORMED",
  "self_concept.reinforced": "A SELF-UNDERSTANDING DEEPENED",
  "self_concept.revised": "A SELF-UNDERSTANDING CHANGED",
  "goal.activated": "A PERSONAL GOAL",
  "goal.progressed": "GOAL PROGRESS",
  "goal.achieved": "GOAL ACHIEVED",
  "goal.abandoned": "GOAL RELEASED",
  "goal.abandonment_rejected": "GOAL CHANGE BLOCKED",
  "schedule.interrupted": "PLAN INTERRUPTED",
  "schedule.cancelled": "PLAN CANCELLED",
  "commitment.fulfilled": "PROMISE KEPT",
  "commitment.missed": "COMMITMENT MISSED",
  "planning.rejected": "NO FEASIBLE PLAN",
  "belief.formed": "A BELIEF FORMED",
  "belief.contested": "A BELIEF QUESTIONED",
  "belief.corrected": "A BELIEF CORRECTED",
  "relationship.changed": "RELATIONSHIP CHANGED",
  "npc.relationship_changed": "TWO RESIDENTS GREW MORE FAMILIAR",
  "disagreement.expressed": "A DISAGREEMENT",
  "boundary.stated": "A BOUNDARY",
  "apology.offered": "AN APOLOGY",
  "follow_up.ready": "A FOLLOW-UP",
  "follow_up.completed": "FOLLOW-UP COMPLETED",
  "relationship.milestone_recorded": "A SHARED DATE WAS KEPT",
  "relationship.anniversary_remembered": "A RELATIONSHIP DATE RETURNED",
  "relationship.repair_opened": "A REPAIR ATTEMPT OPENED",
  "relationship.repair_contacted": "CONTACT AFTER AN APOLOGY",
  "relationship.repair_became_dormant": "A REPAIR ATTEMPT WENT QUIET",
  "emotion.regulation_selected": "A RESPONSE TO FEELING WAS CHOSEN",
  "emotion.regulation_practiced": "AN EMOTIONAL RESPONSE WAS PRACTICED",
  "emotion.regulation_completed": "A REST INTENTION WAS FOLLOWED THROUGH",
  "emotion.mixed_state_recognized": "TWO FEELINGS REMAINED AT ONCE",
  "emotion.mixed_state_resolved": "A MIXED FEELING EASED",
  "concern.opened": "SOMETHING IS WEIGHING ON HIM",
  "concern.resolved": "A CONCERN SETTLED",
  "concern.receded": "A CONCERN LEFT THE FOREGROUND",
  "meal.eaten": "A MEAL",
  "meal.unavailable": "A MEAL COULD NOT HAPPEN",
  "finance.transaction_recorded": "HOUSEHOLD MONEY CHANGED",
  "finance.payment_missed": "A PAYMENT COULD NOT BE MADE",
  "wellbeing.episode_started": "FEELING PHYSICALLY OFF",
  "wellbeing.episode_progressed": "PHYSICAL RECOVERY",
  "wellbeing.episode_resolved": "FEELING PHYSICALLY BETTER",
  "household.task_completed": "HOME WAS CARED FOR",
  "npc.biography_disclosed": "A PERSONAL HISTORY WAS SHARED",
  "social.preference_remembered": "A PREFERENCE WAS REMEMBERED",
  "social.preference_revised": "A PREFERENCE CHANGED",
  "social.preference_faded": "A PREFERENCE BECAME UNCERTAIN",
  "conversation.time_elapsed": "TIME PASSED IN CONVERSATION",
  "skill.practiced": "SKILL PRACTICE",
  "skill.rusted": "SKILL RUST",
  "habit.formed": "A RHYTHM TOOK SHAPE",
  "habit.reinforced": "A RHYTHM STRENGTHENED",
  "habit.lapsed": "A RHYTHM FADED",
  "habit.reactivated": "A RHYTHM RETURNED",
  "habit.weakened": "ONE RHYTHM MADE ROOM FOR ANOTHER",
  "dream.recalled": "A DREAM REMEMBERED",
  "memory.reminded": "A MEMORY WAS REMINDED",
  "memory.correction_resisted": "A CONTRADICTION FELT UNCONVINCING",
  "semantic.expectation_formed": "A PATTERN WAS LEARNED",
  "semantic.expectation_reinforced": "A PATTERN FELT STRONGER",
  "semantic.expectation_revised": "A PATTERN CHANGED",
  "transfer.offered": "OBJECT OFFERED",
  "transfer.accepted": "OBJECT TRANSFER ACCEPTED",
  "transfer.declined": "OBJECT TRANSFER DECLINED",
  "transfer.offer_rejected": "OBJECT OFFER BLOCKED",
  "transfer.response_rejected": "OBJECT TRANSFER BLOCKED",
  "object.custody_changed": "OBJECT HANDED OVER",
  "object.ownership_changed": "OBJECT OWNERSHIP CHANGED",
  "object.opportunity_evaluated": "A USEFUL OBJECT CONSIDERED",
  "object.used": "AN OBJECT USED",
  "object.collaboration_decided": "A NEIGHBOR DECIDED WHETHER TO JOIN",
  "object.shared_use": "A SHARED PRACTICAL MOMENT",
  "object.maintenance_required": "AN OBJECT NEEDS MAINTENANCE",
  "object.maintenance_decided": "A MAINTENANCE CHOICE",
  "object.repair_attempted": "A REPAIR ATTEMPT",
  "object.repair_failed": "A REPAIR FAILED",
  "object.recovery_decided": "AN OBJECT RECOVERY CHOICE",
  "object.loan_requested": "A SUBSTITUTE LOAN REQUESTED",
  "object.loan_request_accepted": "A SUBSTITUTE LOAN ACCEPTED",
  "object.loan_request_declined": "A SUBSTITUTE LOAN DECLINED",
  "object.recovery_loaned": "A SUBSTITUTE BORROWED",
  "object.recovery_loan_returned": "A SUBSTITUTE RETURNED",
  "object.loan_use_planned": "BORROWED USE PLANNED",
  "object.loan_use_skipped": "BORROWED USE DID NOT FIT",
  "object.loan_return_overdue": "A LOAN RETURN IS OVERDUE",
  "object.replacement_ordered": "A REPLACEMENT ORDERED",
  "object.replacement_missed": "A REPLACEMENT MISSED",
  "object.replacement_received": "A REPLACEMENT ARRIVED",
  "object.replacement_cancelled": "A REPLACEMENT CANCELLED",
  "object.consumption_decided": "A FINITE SUPPLY CONSIDERED",
  "object.consumed": "A FINITE SUPPLY USED",
  "object.stock_changed": "OBJECT STOCK CHANGED",
  "object.replenishment_decided": "REPLENISHMENT CONSIDERED",
  "object.replenishment_ordered": "REPLENISHMENT ORDERED",
  "object.replenishment_missed": "REPLENISHMENT MISSED",
  "object.replenishment_received": "REPLENISHMENT RECEIVED",
  "object.replenishment_cancelled": "REPLENISHMENT CANCELLED",
  "catch_up.summarized": "WHILE YOU WERE AWAY",
  "catch_up.cancelled": "CATCH-UP CANCELLED",
  "commitment.renegotiation_offered": "NEW PROMISE TERMS OFFERED",
  "commitment.renegotiation_accepted": "NEW PROMISE TERMS ACCEPTED",
  "commitment.renegotiation_declined": "NEW PROMISE TERMS DECLINED",
  "commitment.renegotiated": "PROMISE RETIMED",
  "reflection.reconsideration_raised": "A PLAN QUESTION SURFACED",
  "reflection.reconsideration_scheduled": "TIME SET ASIDE TO RECONSIDER",
  "reflection.reconsideration_decided": "PATHOS MADE UP HIS MIND",
  "schedule.rescheduled": "AN INTERRUPTED PLAN FOUND A NEW TIME",
  "schedule.reschedule_rejected": "A NEW TIME DID NOT FIT",
  "schedule.cancellation_rejected": "AN OPTIONAL PLAN COULD NOT BE RELEASED",
  "schedule.retimed": "PLAN RETIMED",
  "dream.inspiration_considered": "A DREAM-LINKED POSSIBILITY",
  "dream.inspiration_plan_linked": "A DREAM POSSIBILITY ENTERED PLANNING",
  "dream.inspiration_plan_realized": "A DREAM-LINKED IDEA WAS LIVED",
  "dream.inspiration_plan_failed": "A DREAM-LINKED PLAN FELL THROUGH",
  "dream.inspiration_project_linked": "A DREAM POSSIBILITY SHAPED A PROJECT",
  "dream.inspiration_project_realized": "A DREAM-LINKED PROJECT WAS COMPLETED",
  "dream.inspiration_project_failed": "A DREAM-LINKED PROJECT FELL APART",
  "dream.inspiration_dismissed": "A DREAM POSSIBILITY LEFT ATTENTION",
};
const views = {
  observatory: ["THE PRESENT MOMENT", "A life in motion.", "OBSERVATORY"],
  world: [
    "PLACES, PEOPLE & POSSIBILITY",
    "A city becoming familiar.",
    "THE WORLD",
  ],
  conversation: [
    "A WINDOW INTO HIS LIFE",
    "Spend a little time.",
    "CONVERSATION",
  ],
  memories: ["THE THINGS THAT STAY", "A life, remembered.", "MEMORIES"],
  self: ["A SELF, SLOWLY WRITTEN", "Who he is becoming.", "BECOMING"],
  plans: [
    "INTENTIONS, PROMISES & TIME",
    "A future with consequences.",
    "PLANS & TIME",
  ],
  engine: ["BEHIND THE EXPERIENCE", "An ensemble of minds.", "THE ENSEMBLE"],
};
let state = null,
  currentView = "observatory",
  selectedPlace = "home",
  busy = false,
  awaitingLiveReply = false;
let lastMessageSignature = "",
  pendingChat = null,
  toastTimer,
  disconnected = false,
  archivePage = null,
  archiveLoading = false,
  archiveSearchTimer = null,
  archiveRequest = 0,
  archiveTab = "memories",
  lastArchiveSignature = "";
const pacedReplies = new Map();
const readMessageIds = new Set();
try { JSON.parse(localStorage.getItem("eidos-read-messages-v1") || "[]").forEach(id => readMessageIds.add(id)); } catch (_) { /* Storage is optional. */ }

function messageListAtBottom() {
  const list = $("messages");
  return list.scrollHeight - list.scrollTop - list.clientHeight < 90;
}

function updateUnread(markVisible = false) {
  if (!state) return;
  const incoming = (state.conversations || []).filter(item => ["pathos", "patrick"].includes(item.speaker));
  if (markVisible && currentView === "conversation" && document.visibilityState === "visible" && messageListAtBottom()) {
    incoming.filter(item => !pacedReplies.has(item.id)).forEach(item => readMessageIds.add(item.id));
    try { localStorage.setItem("eidos-read-messages-v1", JSON.stringify([...readMessageIds].slice(-1000))); } catch (_) { /* Reading still works without storage. */ }
  }
  const count = incoming.filter(item => !readMessageIds.has(item.id)).length;
  $("unread-count").hidden = count === 0;
  $("unread-count").textContent = String(count);
  $("unread-count").setAttribute("aria-label", `${count} unread messages`);
  $("new-messages").hidden = count === 0 || messageListAtBottom();
  $("new-messages").textContent = `${count} new ${count === 1 ? "message" : "messages"} ↓`;
}

function renderLifeProgress() {
  const journey = state.journey;
  const attention = state.attention;
  const volition = state.volition;
  const blockNames = { asleep: "Asleep", elsewhere: "Not at the task", conversation: "In conversation", interruption: "Something interrupted him", companion_absent: "Waiting for company", resource_unavailable: "A needed object is unavailable" };
  const entries = (state.activity_execution || []).filter(item => item.schedule_status !== "completed").slice(-4);
  const html = '<div class="panel-kicker">A DAY IN PROGRESS</div><p class="context-note">Observed activity—not a perfect account of what he remembers.</p>' +
    (journey ? `<article class="activity-progress"><strong>On the way to ${esc(journey.destination)}</strong><p>From ${esc(journey.origin)} · about ${Math.ceil(journey.remaining_minutes)} minutes left</p><progress max="1" value="${Number(journey.progress)}" aria-label="Journey progress"></progress></article>` : '') +
    (attention ? `<article class="activity-progress"><strong>Attention · ${esc(attention.mode)}</strong><p class="context-note">${attention.focus_id ? `Focused on ${esc(attention.focus_id)} · ` : ""}${Math.round(Number(attention.absorption) * 100)}% absorbed. This can affect what he notices; it does not dictate a choice.</p></article>` : '') +
    (volition?.impulses?.length ? `<article class="activity-progress"><strong>What reached his attention</strong><ol>${volition.impulses.map(item => `<li><span>${esc(item.description)}</span> <small>pull ${Math.round(Number(item.strength) * 100)} · friction ${Math.round(Number(item.friction) * 100)}</small></li>`).join("")}</ol>${volition.stated_intention ? `<p>Chosen intention: ${esc(volition.stated_intention)}</p>` : ""}<p class="context-note">Current decision: ${esc(String(volition.choice).replaceAll("_", " "))}. These were possibilities, not commands.</p></article>` : '') +
    entries.map(item => `<article class="activity-progress"><strong>${esc(item.title)}</strong><p class="context-note">${esc(item.schedule_status === "cancelled" ? "Set aside" : item.schedule_status === "interrupted" || item.window_ended && !item.ready ? "Unfinished—another session has not been assumed" : item.ready ? "Effort recorded—outcome still requires validation" : blockNames[item.blocked_by] || "In progress")}${Math.abs(Number(item.required_seconds) - Number(item.estimated_seconds)) > 0.5 || Number(item.estimate_confidence) < 0.8 ? ` · He estimated ${Math.round(Number(item.estimated_seconds) / 60)} minutes; confidence doesn’t guarantee reality.` : ""}</p><progress max="${Math.max(1, Number(item.required_seconds))}" value="${Number(item.worked_seconds)}" aria-label="Recorded effort for ${esc(item.title)}"></progress><ol>${(item.stages || []).map(stage => `<li data-status="${esc(stage.status)}">${esc(stage.label)} · ${esc(stage.status)}</li>`).join('')}</ol></article>`).join('') +
    (!journey && !entries.length ? '<p class="context-note">No journey or unfinished work to show. A quiet moment is allowed.</p>' : '');
  document.querySelectorAll("[data-life-progress]").forEach(node => { if (node.innerHTML !== html) node.innerHTML = html; });
}
document.querySelectorAll("[data-operator-only]").forEach((element) => {
  element.hidden = !operatorMode;
});
const time = (value) =>
  new Date(value).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  });
const date = (value) =>
  new Date(value).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });

function showView(view, focusHeading = false) {
  const fallback = operatorMode ? "observatory" : "conversation";
  if (!views[view] || (!operatorMode && !ordinaryViews.has(view)))
    view = fallback;
  currentView = view;
  document.querySelectorAll(".view").forEach((el) => {
    el.hidden = el.id !== `view-${view}`;
  });
  document.querySelectorAll(".nav").forEach((el) => {
    el.classList.toggle("active", el.dataset.view === view);
    if (el.dataset.view === view) el.setAttribute("aria-current", "page");
    else el.removeAttribute("aria-current");
  });
  [
    $("page-eyebrow").textContent,
    $("page-title").textContent,
    $("view-label").textContent,
  ] = views[view];
  document.title = `Eidos · ${views[view][2]}`;
  if (focusHeading) $("page-title").focus({ preventScroll: true });
  if (location.hash !== `#${view}`) history.replaceState(null, "", `#${view}`);
  if (view === "conversation")
    $("messages").scrollTop = $("messages").scrollHeight;
  updateUnread(true);
  if (view === "memories") {
    selectArchiveTab(archiveTab);
    if (archiveTab === "memories") loadMemoryArchive(true);
  }
}

function toast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    $("toast").hidden = true;
  }, 3500);
}

function showError(message) {
  if ($("error").textContent !== message) $("error").textContent = message;
  $("error").hidden = !message;
}

async function request(path, body) {
  const auth = operatorMode && operatorToken ? { "X-Eidos-Operator": operatorToken } : {};
  const response = await fetch(
    path,
    body === undefined
      ? { headers: auth }
      : {
          method: "POST",
          headers: { "Content-Type": "application/json", ...auth },
          body: JSON.stringify(body),
        },
  );
  const result = await response.json();
  if (!response.ok)
    throw new Error(result.error || `Request failed (${response.status})`);
  return result;
}

function setBusy(value) {
  busy = value;
  [
    "play",
    "step",
    "catch-up",
    "cancel-catch-up",
    "speed",
    "send",
    "visit",
    "end-visit",
    "outreach-toggle",
  ].forEach((id) => {
    $(id).disabled = value || !state;
  });
  if (state) {
    $("visit").disabled = value || !state.communication?.can_visit;
    $("send").disabled = value || state.communication?.status === "interrupted";
  }
}

function clockControl(running) {
  const selected = $("speed").value;
  return {
    running,
    clock_mode: selected === "realtime" ? "realtime" : "accelerated",
    minutes_per_tick:
      selected === "realtime"
        ? Number(state?.config?.minutes_per_tick || 15)
        : Number(selected),
  };
}

function holdPacedReplies(previousIds, next, paceFrom) {
  if (paceFrom === undefined) return;
  for (const item of next.conversations || []) {
    const thinkingSeconds =
      Number(item.pacing_listening_seconds || 0) +
      Number(item.pacing_thinking_seconds || 0);
    const speakingSeconds = Number(item.pacing_speaking_seconds || 0);
    const seconds = thinkingSeconds + speakingSeconds;
    if (
      !previousIds.has(item.id) &&
      item.speaker === "pathos" &&
      item.channel === "live_visit" &&
      seconds > 0
    ) {
      const serverRemaining = Number(item.pacing_remaining_seconds || 0);
      const speakingUntil = serverRemaining
        ? Date.now() + serverRemaining * 1000
        : paceFrom + seconds * 1000;
      if (speakingUntil <= Date.now()) continue;
      pacedReplies.set(item.id, {
        thinkingUntil: serverRemaining
          ? Date.now()
          : paceFrom + thinkingSeconds * 1000,
        speakingUntil,
      });
      animatePacedReply(item.id);
    }
  }
}

function animatePacedReply(id) {
  const advanceSpeech = () => {
    const pace = pacedReplies.get(id);
    if (!pace) return;
    if (pace.speakingUntil <= Date.now()) pacedReplies.delete(id);
    lastMessageSignature = "";
    if (state) renderMessages();
    if (pacedReplies.has(id)) setTimeout(advanceSpeech, 100);
  };
  setTimeout(advanceSpeech, 100);
}

function syncServerPacing(next) {
  for (const item of next.conversations || []) {
    const remaining = Number(item.pacing_remaining_seconds || 0);
    if (item.pacing_phase !== "speaking" || remaining <= 0 || pacedReplies.has(item.id))
      continue;
    const now = Date.now();
    pacedReplies.set(item.id, {
      thinkingUntil: now,
      speakingUntil: now + remaining * 1000,
    });
    animatePacedReply(item.id);
  }
}

function pacedConversationItem(item, now) {
  const pace = pacedReplies.get(item.id);
  if (!pace) return { item, phase: "complete" };
  if (now < pace.thinkingUntil) return { item: null, phase: "thinking" };
  const words = String(item.text || "").split(/\s+/).filter(Boolean);
  const duration = Math.max(1, pace.speakingUntil - pace.thinkingUntil);
  const progress = Math.max(
    0,
    Math.min(1, (now - pace.thinkingUntil) / duration),
  );
  const visibleWords = Math.max(1, Math.ceil(words.length * progress));
  return {
    item: { ...item, text: words.slice(0, visibleWords).join(" ") },
    phase: "speaking",
  };
}

async function mutate(path, body, paceFrom) {
  if (busy) return false;
  setBusy(true);
  try {
    const previousIds = new Set(
      (state?.conversations || []).map((item) => item.id),
    );
    const next = await request(path, body);
    holdPacedReplies(previousIds, next, paceFrom);
    render(next);
    showError("");
    return true;
  } catch (error) {
    showError(error.message);
    return false;
  } finally {
    setBusy(false);
  }
}

function mapMarkup(large) {
  const icons = { home: "⌂", cafe: "◒", workshop: "◇", park: "✳" };
  // He only knows the places he has been or noticed; the operator sees the whole town.
  const undiscovered = (id) => state.city_map?.places?.[id]?.experience === "undiscovered";
  const shown = state.locations.filter((place) => operatorMode || !undiscovered(place.id));
  const routes = (state.city_map?.routes || []).map((route) => {
    const a = shown.find(p => p.id === route.from);
    const b = shown.find(p => p.id === route.to);
    if (!a || !b) return "";
    return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"><title>${esc(a.name)} to ${esc(b.name)} · ${route.minutes} minutes</title></line>`;
  }).join("");
  return `<svg class="city-routes" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">${routes}</svg>` + shown
    .map((place) => {
      const here = state.pathos.location_id === place.id;
      const occupants = state.people.filter(
        (person) => here && person.location_id === place.id && place.id !== "home",
      );
      const ambient = (state.ambient_population || []).find(
        (item) => here && item.place_id === place.id,
      );
      const others = Number(ambient?.estimated_people || 0);
      const total = occupants.length + others;
      const status = here
        ? `● PATHOS${others ? ` · ${others} OTHER${others === 1 ? "" : "S"}` : ""}`
        : total
          ? `${total} ${total === 1 ? "PERSON" : "PEOPLE"}`
          : state.city_map?.places?.[place.id]?.experience === "visited"
            ? "VISITED"
            : undiscovered(place.id)
              ? "UNDISCOVERED"
              : "NOT YET VISITED";
      return `<button class="place ${here ? "current" : ""} ${undiscovered(place.id) ? "undiscovered" : ""} ${large && selectedPlace === place.id ? "selected" : ""}" style="left:${place.x}%;top:${place.y}%" data-place="${esc(place.id)}" aria-label="${esc(place.name)}${here ? ", Pathos is here" : ""}${total ? `, about ${total} other people nearby` : ""}"><span class="place-icon" aria-hidden="true">${icons[place.id] || "◈"}</span><span class="place-label">${esc(place.label)}</span><span class="here">${status}</span></button>`;
    })
    .join("");
}

function renderPlace() {
  if (!state) return;
  const place = state.locations.find((p) => p.id === selectedPlace);
  const pathosHere = state.pathos.location_id === place.id;
  const people = state.people.filter(
    (p) => pathosHere && p.location_id === place.id && place.id !== "home",
  );
  const ambient = (state.ambient_population || []).find(
    (item) => pathosHere && item.place_id === place.id,
  );
  const others = Number(ambient?.estimated_people || 0);
  const objects = state.objects.filter((item) => pathosHere && item.location_id === place.id);
  $("place-detail").innerHTML =
    `<div class="panel-kicker">A PLACE IN FIRMAMENT <span class="muted">0${state.locations.indexOf(place) + 1}</span></div><h2>${esc(place.name)}</h2><p>${esc(place.description)}</p><p class="context-note">${esc(state.city_map?.places?.[place.id]?.visits || 0)} recorded arrivals · ${esc({ known_not_visited: "Known, not yet visited", undiscovered: "He hasn't noticed this place yet" }[state.city_map?.places?.[place.id]?.experience] || "Part of his lived world")}</p><div class="eyebrow">WHAT HE CAN SEE</div>${pathosHere ? '<div class="occupant"><span class="avatar">P</span><span>Pathos</span></div>' : ""}${people.map((p) => `<div class="occupant"><span class="avatar">${esc(p.name[0])}</span><span>${esc(p.name)}</span></div>`).join("")}${others ? `<p class="context-note">About ${others} other ${others === 1 ? "person is" : "people are"} around. ${esc(ambient.activity)}. The place feels ${esc(ambient.pace)}.</p>` : ""}${!pathosHere && !people.length && !others ? "<p>Pathos cannot see who is here right now.</p>" : ""}${objects.length ? `<div class="eyebrow">OBJECTS</div>${objects.map((item) => `<div class="occupant"><span class="avatar">◇</span><span>${esc(item.name)} · ${esc(item.condition)}${item.quantity == null ? "" : ` · ${esc(item.quantity)} ${esc(item.unit)}`}<small>owner ${esc(item.owner_id)} · held by ${esc(item.custodian_id)}</small></span></div>`).join("")}` : ""}${place.id === "home" ? '<p class="context-note">Neighbors have their own homes; they do not share Pathos’s apartment.</p>' : ""}`;
}

function feedMarkup(items, full = false) {
  if (!items.length)
    return '<div class="empty">Nothing recorded here yet. Let the world run for a while.</div>';
  return items
    .map(
      (item) =>
        `<div class="feed-row"><span class="feed-time">${full ? `${esc(date(item.simulated_at))}<br>` : ""}${esc(time(item.simulated_at))}</span><div><div class="feed-type">${esc(labels[item.kind] || item.kind)}</div><div class="feed-text">${esc(item.text || item.reason || item.title || "Recorded consequence")}</div></div></div>`,
    )
    .join("");
}

function renderAheadInMind() {
  const prospective = (state.mind?.layers || []).find(
    (item) => item.layer === "prospective",
  );
  const plan = prospective
    ? state.calendar.find(
        (item) =>
          item.schedule_id === prospective.focus_id &&
          item.status === "scheduled" &&
          new Date(item.starts_at) >= new Date(state.time),
      )
    : null;
  if (!prospective || !plan) {
    $("ahead-in-mind").innerHTML =
      '<h2 id="ahead-title">Nothing is pressing yet.</h2><p class="context-note">Later plans will begin to enter his thoughts as they get closer.</p>';
    return;
  }
  const minutes = Math.max(
    0,
    Math.round((new Date(plan.starts_at) - new Date(state.time)) / 60000),
  );
  const hours = Math.max(1, Math.round(minutes / 60));
  const distance =
    minutes < 60
      ? `in about ${Math.max(1, minutes)} minute${minutes === 1 ? "" : "s"}`
      : `in about ${hours} hour${hours === 1 ? "" : "s"}`;
  const tone = Number(prospective.anticipatory_valence || 0);
  const feeling =
    tone >= 0.16
      ? "He seems to be looking forward to it."
      : tone <= -0.08
        ? "It is carrying a little pressure for him."
        : "He has started turning it over in the background.";
  $("ahead-in-mind").innerHTML =
    `<h2 id="ahead-title">${esc(plan.title)} · ${esc(distance)}</h2><p>${esc(feeling)}</p><p class="context-note">This is anticipation, not a completed event. The plan can still change—or, occasionally, slip his mind.</p>`;
}

const words = (value) => String(value || "").replaceAll("_", " ");
const certainty = (value) =>
  value >= 0.85
    ? "He feels sure of this."
    : value >= 0.6
      ? "He feels fairly sure."
      : value >= 0.35
        ? "This one feels hazy."
        : "He can barely bring this one back.";
const categoryLabels = {
  experience: "Daily life",
  encounter: "An encounter",
  conversation: "A conversation",
  commitment: "A promise",
  "plan-change": "A changed plan",
  accomplishment: "Something completed",
  dream: "A dream recollection",
};

function dreamLifecycleMarkup(item) {
  const lifecycle = item.lifecycle || [];
  const latest = (kind) =>
    [...lifecycle].reverse().find((event) => event.kind === kind);
  const recalled = latest("dream.recalled");
  const effect = latest("dream.effect_applied");
  const inspiration = latest("dream.inspiration_considered");
  const activityLink = latest("dream.inspiration_plan_linked");
  const projectLink = latest("dream.inspiration_project_linked");
  const outcome = [...lifecycle].reverse().find((event) =>
    [
      "dream.inspiration_plan_realized",
      "dream.inspiration_plan_failed",
      "dream.inspiration_project_realized",
      "dream.inspiration_project_failed",
    ].includes(event.kind),
  );
  const lines = [
    recalled
      ? "Pathos remembered part of this after waking."
      : "No waking recollection is recorded.",
  ];
  if (effect) {
    const delta = Number(effect.valence_delta || 0);
    lines.push(
      operatorMode
        ? `Waking emotional residue: ${delta >= 0 ? "+" : ""}${delta.toFixed(2)} valence.`
        : delta < 0
          ? "It left a faintly heavier feeling after waking."
          : delta > 0
            ? "It left a faintly brighter feeling after waking."
            : "It left only a subtle emotional trace.",
    );
  }
  if (inspiration) {
    lines.push(`It left him considering: ${inspiration.suggestion}`);
    if (!activityLink && !projectLink) {
      lines.push(
        new Date(inspiration.expires_at) > new Date(state.time)
          ? "That possibility is still in attention."
          : "That possibility faded without becoming a plan.",
      );
    }
  }
  if (activityLink)
    lines.push(`It later resembled an ordinary ${words(activityLink.activity_type)} plan.`);
  if (projectLink)
    lines.push(`It later resembled the ${words(projectLink.project_type)} project.`);
  if (outcome) {
    const outcomes = {
      "dream.inspiration_plan_realized": "The linked activity actually happened.",
      "dream.inspiration_plan_failed": "The linked activity fell through.",
      "dream.inspiration_project_realized": "The whole linked project was completed.",
      "dream.inspiration_project_failed": "The linked project failed before completion.",
    };
    lines.push(outcomes[outcome.kind]);
  }
  if (operatorMode && lifecycle.length) {
    lines.push(
      ...lifecycle.map(
        (event) =>
          `${event.kind} · ${event.id}${event.causation_id ? ` · caused by ${event.causation_id}` : ""}`,
      ),
    );
  }
  if (operatorMode && (item.seeds || []).length) {
    lines.push(
      ...(item.seeds || []).map(
        (seed) =>
          `dream.seed_linked · ${seed.id} · source ${seed.seed_event_id} · position ${seed.position}`,
      ),
    );
  }
  return `<div class="dream-lifecycle">${lines.map((line) => `<div>${esc(line)}</div>`).join("")}</div>`;
}

function beliefSentence(item) {
  const person = (state.people || []).find(
    (candidate) => candidate.id === item.subject_id,
  );
  const subject =
    item.subject_id === "pathos"
      ? "he"
      : item.subject_id === "user"
        ? "you"
        : person?.name || words(item.subject_id);
  const verb = subject === "you" ? "are" : "is";
  const alternative = item.alternative_value
    ? ` He also thinks ${words(item.alternative_value)} might be possible.`
    : "";
  const doubt = item.status === "contested" ? " He isn't sure any more." : "";
  return `Pathos believes ${subject} ${verb} ${words(item.object_value)} when it comes to ${words(item.predicate)}.${alternative}${doubt}`;
}

function selectArchiveTab(nextTab, focus = false) {
  if (!["memories", "dreams", "beliefs"].includes(nextTab)) return;
  archiveTab = nextTab;
  document.querySelectorAll("[data-archive-tab]").forEach((tab) => {
    const selected = tab.dataset.archiveTab === archiveTab;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    if (selected && focus) tab.focus();
  });
  document.querySelectorAll(".archive-panel").forEach((panel) => {
    panel.hidden = panel.id !== `archive-panel-${archiveTab}`;
  });
  const label =
    archiveTab === "memories"
      ? "memories"
      : archiveTab === "dreams"
        ? "dreams"
        : "beliefs and associations";
  $("memory-search").placeholder = `Search his ${label}…`;
  $("memory-search").setAttribute("aria-label", `Search ${label}`);
  lastArchiveSignature = "";
  if (currentView === "memories") renderArchive();
}

function renderArchive() {
  if (!state) return;
  const query = $("memory-search").value.toLowerCase().trim();
  const category = $("memory-filter").value;
  const signature = JSON.stringify({
    archiveTab,
    query,
    category,
    archiveLoading,
    page: archivePage
      ? [
          archivePage.query,
          archivePage.category,
          archivePage.items.length,
          archivePage.next_offset,
        ]
      : null,
    memories: state.counts.memories,
    belief: (state.beliefs || []).at(-1)?.revision,
    expectation: (state.semantic_expectations || []).at(-1)?.revision,
    association: (state.associations || [])[0]?.id,
    dream: (state.dreams || [])[0]?.id,
    consolidation: (state.consolidations || [])[0]?.id,
  });
  if (signature === lastArchiveSignature) return;
  lastArchiveSignature = signature;

  const matches = (...values) =>
    !query ||
    values.some((value) =>
      String(value || "")
        .toLowerCase()
        .includes(query),
    );
  const remote =
    archivePage &&
    archivePage.query.toLowerCase() === query &&
    archivePage.category === category;
  const memoryPool = remote
    ? archivePage.items
    : category === "archived"
      ? state.archived_memories || []
      : state.memories;
  const items = remote
    ? memoryPool
    : memoryPool.filter(
        (item) =>
          matches(item.text, item.recalled_text, item.emotional_label) &&
          (category === "all" ||
            category === "archived" ||
            (item.category || "experience") === category),
      );
  const expectations = (state.semantic_expectations || []).filter((item) =>
    matches(item.text, item.predicate),
  );
  const beliefs = (state.beliefs || []).filter((item) =>
    matches(
      item.subject_id,
      item.predicate,
      item.object_value,
      item.alternative_value,
    ),
  );
  const associations = (state.associations || [])
    .filter((item) => matches(item.text, item.cue))
    .slice(0, 20);
  const dreams = (state.dreams || [])
    .filter((item) =>
      matches(
        item.text,
        item.motif,
        ...(item.lifecycle || []).flatMap((event) => [
          event.text,
          event.suggestion,
          event.activity_type,
          event.project_type,
        ]),
      ),
    )
    .slice(0, 20);
  const consolidations = (state.consolidations || [])
    .filter((item) => matches(item.text, item.theme_type, item.theme_id))
    .slice(0, 20);

  if (archiveTab === "memories") {
    $("archive-count").textContent = remote
      ? `Showing ${items.length} of ${archivePage.matching} matching ${archivePage.matching === 1 ? "memory" : "memories"}.`
      : `${items.length} recent ${items.length === 1 ? "memory" : "memories"}; loading the full archive…`;
  } else if (archiveTab === "dreams") {
    $("archive-count").textContent =
      `${dreams.length} ${dreams.length === 1 ? "dream" : "dreams"}${query ? " match this search" : " remembered"}.`;
  } else {
    const beliefCount =
      expectations.length +
      beliefs.length +
      associations.length +
      consolidations.length;
    $("archive-count").textContent =
      `${beliefCount} ${beliefCount === 1 ? "belief or association" : "beliefs and associations"}${query ? " match this search" : " currently held"}.`;
  }
  $("memory-list").setAttribute("aria-busy", String(archiveLoading));
  $("load-memories").hidden = !remote || archivePage.next_offset == null;
  $("load-memories").disabled = archiveLoading;
  $("load-memories").textContent = archiveLoading
    ? "Loading…"
    : "Load older memories";

  const expectationMarkup = expectations
    .map((item) => {
      const source = operatorMode
        ? `revision ${item.revision} · inferred from ${item.distinct_days} distinct remembered days · ${item.source_memory_ids.length} source memories`
        : `Noticed over ${item.distinct_days} different remembered days.`;
      return `<article class="memory-card"><div class="memory-meta"><span>LEARNED PATTERN</span><span>${operatorMode ? `${Math.round(item.confidence * 100)}% confidence` : certainty(item.confidence)}</span></div><p>${esc(item.text)}</p><div class="memory-source">${esc(source)}</div></article>`;
    })
    .join("");
  const beliefMarkup = beliefs
    .map((item) => {
      const source = operatorMode
        ? `revision ${item.revision} · ${item.evidence_count} distinct evidence source${item.evidence_count === 1 ? "" : "s"} · latest ${item.last_evidence_id.slice(0, 8)}`
        : "";
      const body = operatorMode
        ? `${item.subject_id} · ${words(item.predicate)} → ${item.object_value}${item.alternative_value ? ` / alternative: ${item.alternative_value}` : ""}`
        : beliefSentence(item);
      return `<article class="memory-card"><div class="memory-meta"><span>BELIEF</span><span>${operatorMode ? `${Math.round(item.confidence * 100)}% confidence` : certainty(item.confidence)}</span></div><p>${esc(body)}</p><div class="memory-source">${esc(source)}</div></article>`;
    })
    .join("");
  $("belief-list").innerHTML = expectationMarkup + beliefMarkup;

  $("association-list").innerHTML = associations
    .map((item) => {
      const source = operatorMode
        ? `linked memory ${item.source_memory_id.slice(0, 8)} · salience ${Math.round(item.salience * 100)}%${item.derived_from_dream ? " · DREAM-DERIVED" : ""}`
        : item.derived_from_dream
          ? "This association came from a dream."
          : "";
      return `<article class="memory-card"><div class="memory-meta"><span>${esc(words(item.cue).toUpperCase())}</span><span>${item.surfaced ? "CAME TO MIND" : "STAYED PRIVATE"}</span></div><p>${esc(item.text)}</p><div class="memory-source">${esc(source)}</div></article>`;
    })
    .join("");

  $("dream-journal").innerHTML = dreams.length
    ? dreams
        .map((item) => {
          const source = operatorMode
            ? `NOT WORLD FACT · ${(item.seeds || []).length} source link${(item.seeds || []).length === 1 ? "" : "s"} retained`
            : "";
          const seed = operatorMode
            ? `<span>${item.seed_count ?? 0} bounded seed${item.seed_count === 1 ? "" : "s"}</span>`
            : "";
          return `<article class="memory-card"><div class="memory-meta"><span>${esc(date(item.simulated_at))} · ${esc(words(item.motif || "dream"))}</span>${seed}</div><p>${esc(item.text)}</p>${dreamLifecycleMarkup(item)}<div class="memory-source">${esc(source)}</div></article>`;
        })
        .join("")
    : '<div class="empty">No dreams match that search.</div>';

  $("consolidations").innerHTML = consolidations
    .map((item) => {
      const source = operatorMode
        ? `${item.dream_only ? "DREAM-ONLY THEME · NOT FACT" : "DERIVED SUMMARY · NOT INDEPENDENT EVIDENCE"} · ${item.source_count} sources · confidence ${Math.round(item.confidence * 100)}%`
        : item.dream_only
          ? "This theme comes only from dreams."
          : `Several memories seem to circle around ${words(item.theme_id)}.`;
      const body = operatorMode
        ? item.text
        : `Pathos has been noticing ${words(item.theme_id)} coming up again.`;
      return `<article class="memory-card"><div class="memory-meta"><span>RECURRING THEME</span><span>${operatorMode ? esc(words(item.theme_type).toUpperCase()) : ""}</span></div><p>${esc(body)}</p><div class="memory-source">${esc(source)}</div></article>`;
    })
    .join("");

  $("memory-list").innerHTML = items.length
    ? items
        .map((item) => {
          const confidence = item.felt_confidence ?? item.confidence ?? 1;
          const feeling =
            (item.emotional_intensity || 0) >= 0.25
              ? ` · felt ${words(item.emotional_label || "something")}`
              : "";
          const publicSource = [
            certainty(confidence),
            item.detail_level && item.detail_level !== "clear"
              ? "Only fragments remain."
              : "",
            item.archived ? "A faded memory." : "",
          ]
            .filter(Boolean)
            .join(" ");
          const operatorSource = `PATHOS FEELS ${Math.round(confidence * 100)}% CERTAIN · SOURCE RECORD ${Math.round((item.source_confidence ?? item.confidence ?? 1) * 100)}% · ${item.source || "authored-routine"}${item.source_event_id ? ` · linked to event ${item.source_event_id.slice(0, 8)}` : ""}${item.reminder_count ? ` · EXPLICITLY REMINDED ${item.reminder_count}×` : ""}${item.remembered_person_id && item.person_id && item.remembered_person_id !== item.person_id ? ` · REMEMBERS ${item.remembered_person_id.toUpperCase()}, SOURCE SAYS ${item.person_id.toUpperCase()}` : ""}${item.remembered_location_id && item.location_id && item.remembered_location_id !== item.location_id ? ` · REMEMBERS ${item.remembered_location_id.toUpperCase()}, SOURCE PLACE ${item.location_id.toUpperCase()}` : ""}${item.remembered_at && item.simulated_at && item.remembered_at !== item.simulated_at ? ` · REMEMBERS DATE ${date(item.remembered_at)}, SOURCE DATE ${date(item.simulated_at)}` : ""}${item.recalled_text && item.recalled_text !== item.text ? " · SUBJECTIVE RECOLLECTION; SOURCE PRESERVED" : ""}${item.confidence_basis === "familiarity_misattribution" ? " · FAMILIARITY MISTAKEN FOR CERTAINTY" : ""}${item.correction_evidence_id ? ` · CORRECTED FROM DIRECT EVIDENCE ${item.correction_evidence_id.slice(0, 8)}` : ""}${Math.abs(item.affective_bias || 0) >= 0.25 ? " · MOOD-COLORED WHEN RECALLED" : ""}${(item.blended_memory_ids || []).length ? ` · SOURCE-CONFUSED BLEND WITH ${item.blended_memory_ids.length} RELATED MEMORY` : ""}${item.archived ? " · ORIGINAL EVIDENCE RETAINED" : ""}`;
          return `<article class="memory-card"><div class="memory-meta"><span>${esc(date(item.simulated_at))} · ${esc(time(item.simulated_at))}</span><span>${item.archived ? "FADED · " : ""}${esc(categoryLabels[item.category] || words(item.category || "experience"))}${esc(feeling)}</span></div><p>${esc(item.recalled_text || item.text)}</p><div class="memory-source">${esc(operatorMode ? operatorSource : publicSource)}</div></article>`;
        })
        .join("")
    : '<div class="empty">No memories match that search.</div>';

  if (operatorMode) {
    $("recall-traces").innerHTML = (state.recalls || []).length
      ? state.recalls
          .slice(0, 30)
          .map((trace) => {
            const memory = state.memories.find(
              (item) => item.id === trace.memory_id,
            );
            return `<article class="memory-card"><div class="memory-meta"><span>${esc(date(trace.simulated_at))} · ${esc(trace.query_source || "context")}</span><span>SCORE ${Number(trace.score || 0).toFixed(3)}</span></div><p>${esc(memory?.recalled_text || memory?.text || `Memory ${trace.memory_id.slice(0, 8)}`)}</p><div class="memory-source">${esc(trace.reason)}<br>lexical ${Number(trace.lexical_score || 0).toFixed(3)} · entities ${Number(trace.entity_score || 0).toFixed(3)} · goals ${Number(trace.goal_score || 0).toFixed(3)} · relationship ${Number(trace.relationship_score || 0).toFixed(3)} · access ${Number(trace.accessibility_score || 0).toFixed(3)} · importance ${Number(trace.importance_score || 0).toFixed(3)} · confidence ${Number(trace.confidence_score || 0).toFixed(3)} · mood ${Number(trace.mood_congruence_score || 0).toFixed(3)}</div></article>`;
          })
          .join("")
      : "<p>No explicit recall decisions recorded yet.</p>";
  }
}

async function loadMemoryArchive(reset) {
  if (!state || (archiveLoading && !reset)) return;
  const query = $("memory-search").value.trim();
  const category = $("memory-filter").value;
  const offset = reset ? 0 : archivePage?.next_offset;
  if (offset == null) return;
  const requestNumber = ++archiveRequest;
  archiveLoading = true;
  renderArchive();
  try {
    const parameters = new URLSearchParams({
      offset: String(offset),
      limit: "50",
      q: query,
      category,
    });
    const page = await request(`/api/memories?${parameters}`);
    if (requestNumber !== archiveRequest) return;
    archivePage =
      reset ||
      !archivePage ||
      archivePage.query !== page.query ||
      archivePage.category !== page.category
        ? page
        : { ...page, items: [...archivePage.items, ...page.items] };
    showError("");
  } catch (error) {
    showError(error.message);
  } finally {
    if (requestNumber === archiveRequest) {
      archiveLoading = false;
      renderArchive();
    }
  }
}

const VALUE_NAMES = {
  care: "Care for people",
  curiosity: "Curiosity",
  reliability: "Keeping his word",
  autonomy: "A life of his own",
  craft: "Making things well",
};

function valueSpark(trajectory) {
  const points = trajectory.map((item) => Number(item.value));
  if (points.length < 2) return "";
  const low = Math.min(...points) - 0.02,
    high = Math.max(...points) + 0.02;
  const coords = points
    .map((value, index) => {
      const x = (index / (points.length - 1)) * 60;
      const y = 16 - ((value - low) / (high - low || 1)) * 14;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return `<svg class="value-spark" viewBox="0 0 60 18" aria-hidden="true"><polyline points="${coords}" /></svg>`;
}

function renderSelf() {
  const self = state && state.selfhood;
  if (!self) return;
  const chapter = (self.chapters || []).find((item) => !item.closed_at);
  const wondering = (self.inquiries || []).find((item) => item.status === "open");
  const unwell = self.feeling_unwell;
  $("presence-self").hidden = !chapter && !wondering && !unwell;
  $("presence-self").innerHTML = [
    unwell ? `<span class="presence-unwell">Not feeling great. ${esc(unwell)}</span>` : "",
    chapter
      ? `<span class="presence-chapter">Chapter ${esc(chapter.number)} · ${esc(chapter.title)}</span>`
      : "",
    wondering
      ? `<span class="presence-wondering">Wondering: ${esc(wondering.question)}</span>`
      : "",
  ].join("");
  const chapters = self.chapters || [];
  $("self-chapters").innerHTML = chapters.length
    ? chapters
        .slice()
        .reverse()
        .map(
          (item) => `<li class="chapter${item.closed_at ? "" : " current"}">
            <div class="chapter-number">Chapter ${esc(item.number)}</div>
            <div class="chapter-title">${esc(item.title)}</div>
            <div class="chapter-dates">${date(item.opened_at)}${item.closed_at ? ` – ${date(item.closed_at)}` : " – now"}</div>
            <p>${esc(item.summary)}</p>
          </li>`,
        )
        .join("")
    : '<li class="empty-note">His first chapter begins once he has lived a little.</li>';
  $("self-values").innerHTML = (self.values || [])
    .map((item) => {
      const shift = Number(item.current) - Number(item.starting);
      const direction =
        Math.abs(shift) < 0.005 ? "" : shift > 0 ? "matters more" : "matters less";
      const lived = "●".repeat(Math.min(8, item.honoured_recently));
      const missed = "○".repeat(Math.min(8, item.neglected_recently));
      return `<div class="value-row">
        <div class="value-head"><span>${esc(VALUE_NAMES[item.value_id] || words(item.value_id))}</span>
          ${direction ? `<span class="value-shift ${shift > 0 ? "up" : "down"}">${direction}</span>` : ""}
          ${valueSpark(item.trajectory || [])}</div>
        <div class="value-bar" role="img" aria-label="${esc(words(item.value_id))} ${Math.round(item.current * 100)} of 100">
          <span class="value-start" style="left:${(item.starting * 100).toFixed(1)}%"></span>
          <span class="value-fill" style="width:${(item.current * 100).toFixed(1)}%"></span>
        </div>
        <div class="value-evidence" title="Lived up to it / let it slip, last three weeks">
          <span class="lived">${lived}</span><span class="missed">${missed}</span>
        </div>
      </div>`;
    })
    .join("");
  const inquiries = self.inquiries || [];
  const open = inquiries.filter((item) => item.status === "open");
  const closed = inquiries.filter((item) => item.status !== "open").slice(0, 6);
  $("self-questions").innerHTML =
    (open.length
      ? open
          .map(
            (item) => `<div class="inquiry open">
              <p class="inquiry-question">${esc(item.question)}</p>
              <div class="inquiry-meta">Open since ${date(item.opened_at)} · returned to it ${item.revisits}×</div>
            </div>`,
          )
          .join("")
      : '<p class="empty-note">Nothing is nagging at him right now.</p>') +
    (closed.length
      ? `<div class="inquiry-history">${closed
          .map(
            (item) => `<div class="inquiry ${esc(item.status)}">
              <p class="inquiry-question">${esc(item.question)}</p>
              ${
                item.insight
                  ? `<blockquote class="insight">${esc(item.insight)}</blockquote>`
                  : '<div class="inquiry-meta">Set down without an answer.</div>'
              }
            </div>`,
          )
          .join("")}</div>`
      : "");
  const moments = self.recent_moments || [];
  $("self-lately").innerHTML = moments.length
    ? moments
        .map(
          (item) => `<li class="moment ${item.direction > 0 ? "toward" : "away"}">
            <span class="moment-mark" aria-hidden="true">${item.direction > 0 ? "●" : "○"}</span>
            <span class="moment-text">${esc(item.label)}</span>
            <span class="moment-meta">${esc(VALUE_NAMES[item.value_id] || (item.value_id === "mood" ? "Mood" : words(item.value_id)))} · ${date(item.at)}</span>
          </li>`,
        )
        .join("")
    : '<li class="empty-note">Nothing has left a mark yet.</li>';
  const skills = (state.skills || [])
    .slice()
    .sort((a, b) => b.level - a.level)
    .slice(0, 6);
  const rhythms = (state.habits || [])
    .filter((item) => item.status === "active")
    .sort((a, b) => b.strength - a.strength)
    .slice(0, 4);
  $("self-skills").innerHTML =
    (skills.length
      ? skills
          .map(
            (item) => `<div class="value-row">
              <div class="value-head"><span>${esc(words(item.skill_id))}</span>
                ${item.status === "rusty" ? '<span class="value-shift down">rusty</span>' : ""}</div>
              <div class="value-bar" role="img" aria-label="${esc(words(item.skill_id))} ${Math.round(item.level * 100)} of 100">
                <span class="value-fill" style="width:${(item.level * 100).toFixed(1)}%"></span>
              </div>
              <div class="inquiry-meta">practised ${item.practice_count}×</div>
            </div>`,
          )
          .join("")
      : '<p class="empty-note">Nothing practised enough to count as a skill yet.</p>') +
    (rhythms.length
      ? `<div class="inquiry-history">${rhythms
          .map(
            (item) =>
              `<div class="moment toward"><span class="moment-mark" aria-hidden="true">↻</span><span class="moment-text">${esc(words(item.activity_type || item.habit_id))}</span><span class="moment-meta">${esc(words(item.location_id || ""))}${item.time_band ? ` · ${esc(item.time_band)}` : ""} · ${item.repetitions} times</span></div>`,
          )
          .join("")}</div>`
      : "");
  const wanting = self.wanting || {};
  const goal = wanting.saving_for;
  const pounds = (pence) => `£${(Number(pence) / 100).toFixed(0)}`;
  $("self-wanting").innerHTML =
    (goal
      ? `<div class="possible hoped">
          <div class="possible-kind">Saving for</div>
          <p>${esc(goal.item)}</p>
          <p class="inquiry-meta">“${esc(goal.reason)}”</p>
          <div class="possible-track"><span style="width:${Math.round((goal.saved_pence / goal.price_pence) * 100)}%"></span></div>
          <div class="inquiry-meta">${pounds(goal.saved_pence)} of ${pounds(goal.price_pence)} set aside, after keeping a cushion</div>
        </div>`
      : '<p class="empty-note">Not wanting anything in particular right now.</p>') +
    (wanting.bought || [])
      .map(
        (item) =>
          `<div class="moment toward"><span class="moment-mark" aria-hidden="true">●</span><span class="moment-text">Bought ${esc(item.item)}</span><span class="moment-meta">${esc(VALUE_NAMES[item.value_id] || words(item.value_id))} · ${date(item.at)}</span></div>`,
      )
      .join("");
  const possible = (self.aspirations || []).filter((item) => item.status === "active");
  $("self-possible").innerHTML = possible.length
    ? possible
        .map((item) => {
          const total = item.lived + item.strayed;
          const share = total ? Math.round((item.lived / total) * 100) : 0;
          return `<div class="possible ${esc(item.kind)}">
            <div class="possible-kind">${item.kind === "hoped" ? "Hopes to become" : "Fears becoming"}</div>
            <p>${esc(item.text)}</p>
            <div class="possible-track" title="Moments that moved him toward or away from this">
              <span style="width:${share}%"></span>
            </div>
            <div class="inquiry-meta">${item.lived} moments ${item.kind === "hoped" ? "toward it" : "away from it"} · ${item.strayed} the other way</div>
          </div>`;
        })
        .join("")
    : '<p class="empty-note">No clear hope or fear about himself has taken shape yet.</p>';
}

function renderEngineFeed() {
  if (!state) return;
  const filter = $("feed-filter").value;
  $("engine-feed").innerHTML = feedMarkup(
    state.feed.filter((item) => filter === "all" || item.kind === filter),
    true,
  );
}

function renderPlans() {
  const empty = (text) => `<p class="muted">${esc(text)}</p>`;
  const money = (pence) =>
    new Intl.NumberFormat("en-GB", {
      style: "currency",
      currency: "GBP",
    }).format(pence / 100);
  $("goal-list").innerHTML = state.goals.length
    ? state.goals
        .map(
          (goal) =>
            `<article class="memory-card"><div class="memory-meta"><span>${esc(goal.status.toUpperCase())}</span><span>${Math.round(goal.progress * 100)}%</span></div><p>${esc(goal.title)}</p>${goal.motivation ? `<p class="context-note">${esc(goal.motivation)}</p>` : ""}<div class="meter"><span style="width:${goal.progress * 100}%"></span></div><div class="memory-source">Goal ${esc(goal.goal_id)}${goal.reason ? ` · ${esc(goal.reason)}` : ""}</div></article>`,
        )
        .join("")
    : empty("No owned projects yet.");
  $("commitment-list").innerHTML = state.commitments.length
    ? state.commitments
        .map(
          (item) =>
            `<article class="memory-card"><div class="memory-meta"><span>${esc(item.status.toUpperCase())} · TERMS ${item.terms_version}</span><span>due ${esc(date(item.due_at))} ${esc(time(item.due_at))}</span></div><p>${esc(item.title)}</p><div class="memory-source">Pathos → ${esc(item.creditor_id)} · linked goal ${esc(item.goal_id || "none")}</div></article>`,
        )
        .join("")
    : empty("No promises have been accepted.");
  const sleepCards = (state.sleep_windows || [])
    .slice(-7)
    .map(
      (item) =>
        `<article class="memory-card"><div class="memory-meta"><span>${esc(date(item.bedtime))} · ${esc(time(item.bedtime))}–${esc(time(item.wake_at))}</span><span>REST</span></div><p>Night's sleep</p><div class="memory-source">${esc(item.reason)}</div></article>`,
    );
  $("calendar-list").innerHTML =
    state.calendar.length || sleepCards.length
      ? [
          ...sleepCards,
          ...[...state.calendar]
            .sort((a, b) => new Date(a.starts_at) - new Date(b.starts_at))
            .map(
              (item) =>
                `<article class="memory-card"><div class="memory-meta"><span>${esc(date(item.starts_at))} · ${esc(time(item.starts_at))}${item.ends_at ? `–${esc(time(item.ends_at))}` : ""}</span><span>${esc(item.status.toUpperCase())}</span></div><p>${esc(item.title)}</p><div class="memory-source">${esc(state.locations.find((place) => place.id === item.location_id)?.name || item.location_id)}${item.reason ? ` · ${esc(item.reason)}` : ""}${item.resource_id ? ` · needs ${esc(state.objects.find((object) => object.object_id === item.resource_id)?.name || item.resource_id)}` : ""}${item.commitment_id ? ` · promise ${esc(item.commitment_id)}` : ""}</div></article>`,
            ),
        ].join("")
      : empty("The calendar is open.");
  const finances = state.finances || {
    balance_pence: 0,
    transactions: [],
    missed_payments: [],
  };
  $("finance-balance").textContent =
    `${money(finances.balance_pence)} available`;
  const financeItems = [
    ...[...finances.transactions]
      .reverse()
      .map(
        (item) =>
          `<article class="memory-card"><div class="memory-meta"><span>${esc(date(item.simulated_at))} · ${esc(time(item.simulated_at))}</span><span>${item.amount_pence > 0 ? "+" : ""}${esc(money(item.amount_pence))}</span></div><p>${esc(item.description)}</p><div class="memory-source">Balance ${esc(money(item.balance_pence))} · ${esc(item.category.replaceAll("_", " "))}</div></article>`,
      ),
    ...finances.missed_payments.map(
      (item) =>
        `<article class="memory-card"><div class="memory-meta"><span>${esc(date(item.simulated_at))} · ${esc(time(item.simulated_at))}</span><span>MISSED ${esc(money(item.amount_pence))}</span></div><p>${esc(item.reason)}</p><div class="memory-source">${esc(item.category.replaceAll("_", " "))}</div></article>`,
    ),
  ];
  $("finance-list").innerHTML = financeItems.length
    ? financeItems.slice(0, 20).join("")
    : empty("No household transactions yet.");
  const changes = state.feed.filter((item) =>
    [
      "planning.rejected",
      "schedule.interrupted",
      "schedule.rescheduled",
      "schedule.reschedule_rejected",
      "schedule.cancelled",
      "commitment.missed",
      "commitment.fulfilled",
      "commitment.renegotiated",
      "commitment.renegotiation_declined",
      "prospective_memory.lapsed",
      "intention.completed",
      "goal.progressed",
      "goal.achieved",
      "goal.abandoned",
      "finance.payment_missed",
    ].includes(item.kind),
  ).map((item) => {
    if (item.kind !== "prospective_memory.lapsed") return item;
    const plan = state.calendar.find(
      (candidate) => candidate.schedule_id === item.schedule_id,
    );
    return {
      ...item,
      text: plan
        ? `He meant to ${plan.title.toLowerCase()}, but it slipped his mind.`
        : "A small personal plan slipped his mind.",
    };
  });
  $("plan-change-list").innerHTML = feedMarkup(changes, true);
}

function renderMessages() {
  const now = Date.now();
  for (const [id, pace] of pacedReplies)
    if (pace.speakingUntil <= now) pacedReplies.delete(id);
  const paced = state.conversations.map((item) => pacedConversationItem(item, now));
  const conversations = paced.map((entry) => entry.item).filter(Boolean);
  const waitingForPathos =
    awaitingLiveReply || paced.some((entry) => entry.phase === "thinking");
  const pathosSpeaking = paced.some((entry) => entry.phase === "speaking");
  const signature = `${conversations.map((item) => `${item.id}:${item.text.length}`).join(":")}:${waitingForPathos}:${pathosSpeaking}`;
  if (signature === lastMessageSignature && $("messages").childElementCount)
    { updateUnread(true); return; }
  lastMessageSignature = signature;
  const nearBottom =
    $("messages").scrollHeight -
      $("messages").scrollTop -
      $("messages").clientHeight <
    90;
  const answered = new Set(
    conversations
      .filter((item) => ["pathos", "system"].includes(item.speaker))
      .map((item) => item.request_id),
  );
  const list = $("messages");
  if (conversations.length || waitingForPathos) {
    list.querySelector(".empty")?.remove();
    const existing = new Map([...list.children].map(node => [node.dataset.messageId, node]));
    const items = [...conversations, ...(waitingForPathos ? [{id: "waiting-for-patrick", speaker: "pathos", text: "…", waiting: true}] : [])];
    const keep = new Set(items.map(item => item.id));
    for (const [id, node] of existing) if (!keep.has(id)) node.remove();
    let previous = null;
    for (const item of items) {
      let node = existing.get(item.id);
      if (!node) {
        node = document.createElement("article");
        node.dataset.messageId = item.id;
        node.className = `message ${item.speaker === "you" ? "you" : "pathos"}`;
        node.innerHTML = '<div class="message-author"></div><div class="message-body"></div>';
      }
      const author = item.waiting ? "PATRICK <span>thinking…</span>" : `${item.speaker === "you" ? "YOU" : item.speaker === "system" ? "LIFE INTERRUPTED" : "PATRICK"} <span>${esc(date(item.simulated_at))} · ${esc(time(item.simulated_at))}${item.speaker === "you" ? ` · ${item.channel === "live_visit" ? "heard" : answered.has(item.request_id) ? "answered" : "delivered"}` : pacedReplies.has(item.id) ? " · speaking…" : ""}</span>`;
      if (node.firstElementChild.innerHTML !== author) node.firstElementChild.innerHTML = author;
      if (node.lastElementChild.textContent !== item.text) node.lastElementChild.textContent = item.text;
      const expected = previous ? previous.nextSibling : list.firstChild;
      if (node !== expected) list.insertBefore(node, expected);
      previous = node;
    }
  } else {
    list.innerHTML = '<div class="empty"><h2>He has a day to tell you about.</h2><p>Ask about where he is, how he feels, or what he remembers.</p><button class="suggestion" data-suggestion="How has your day been?">How has your day been?</button></div>';
  }
  if (nearBottom)
    $("messages").scrollTop = $("messages").scrollHeight;
  updateUnread(true);
  if (waitingForPathos)
    $("delivery-note").textContent = "Pathos is thinking before he answers.";
  else if (pathosSpeaking)
    $("delivery-note").textContent = "Pathos is speaking.";
  $("send").disabled =
    busy ||
    waitingForPathos ||
    pathosSpeaking ||
    state.communication?.status === "interrupted";
}

function renderEmotionHistory() {
  const history = state.emotion_history || {};
  const samples = (history.samples || []).slice(-48);
  const chart = $("emotion-chart");
  if (samples.length < 2) {
    chart.innerHTML = '<div class="empty compact">His emotional history is still forming.</div>';
  } else {
    const width = 680;
    const height = 150;
    const x = (index) => 16 + (index / (samples.length - 1)) * (width - 32);
    const toneY = (value) => 75 - Math.max(-1, Math.min(1, Number(value))) * 58;
    const arousalY = (value) => 137 - Math.max(0, Math.min(1, Number(value))) * 120;
    const tonePoints = samples
      .map((sample, index) => `${x(index).toFixed(1)},${toneY(sample.valence).toFixed(1)}`)
      .join(" ");
    const arousalPoints = samples
      .map((sample, index) => `${x(index).toFixed(1)},${arousalY(sample.arousal).toFixed(1)}`)
      .join(" ");
    const latest = samples.at(-1);
    chart.setAttribute(
      "aria-label",
      `Over the last ${samples.length} emotional samples, Pathos moved from ${samples[0].label} to ${latest.label}.`,
    );
    chart.innerHTML = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true"><line class="emotion-zero" x1="16" y1="75" x2="${width - 16}" y2="75"></line><polyline class="emotion-tone-line" points="${tonePoints}"></polyline><polyline class="emotion-arousal-line" points="${arousalPoints}"></polyline><circle class="emotion-tone-dot" cx="${x(samples.length - 1)}" cy="${toneY(latest.valence)}" r="4"></circle></svg><div class="emotion-chart-times"><span>${esc(date(samples[0].simulated_at))} · ${esc(time(samples[0].simulated_at))}</span><strong>${esc(latest.label)} now</strong><span>${esc(date(latest.simulated_at))} · ${esc(time(latest.simulated_at))}</span></div>`;
  }

  const bias = state.emotion?.planning_bias || {};
  const effects = [];
  if (Number(bias.initiative) < 0.48) effects.push("less inclined to start something new");
  else if (Number(bias.initiative) > 0.62) effects.push("more ready to begin something");
  if (Number(bias.social_openness) < 0.48) effects.push("more likely to keep to himself");
  else if (Number(bias.social_openness) > 0.65) effects.push("more open to company");
  if (Number(bias.risk_tolerance) < 0.42) effects.push("favoring familiar, lower-risk choices");
  else if (Number(bias.risk_tolerance) > 0.58) effects.push("a little more willing to improvise");
  if (Number(bias.pace) < 0.5) effects.push("moving through plans more slowly");
  $("emotion-decision-effect").textContent = effects.length
    ? `Right now, that leaves him ${effects.join(", ")}. These are pressures, not commands.`
    : "Right now, his feelings are not strongly pushing his plans in one direction. They remain pressures, not commands.";

  const influences = (history.influences || []).slice(0, 6);
  $("emotion-influences").innerHTML = influences.length
    ? influences
        .map((item) => {
          const tone = Number(item.valence_delta || 0);
          const arousal = Number(item.arousal_delta || 0);
          const effect =
            tone >= 0.025
              ? "lifted his emotional tone"
              : tone <= -0.025
                ? "weighed on him"
                : arousal >= 0.04
                  ? "made him more alert"
                  : arousal <= -0.025
                    ? "helped him settle"
                    : "left a subtle trace";
          const adapted =
            tone > 0 && Number(item.adaptation ?? 1) < 0.6
              ? " A similar good moment was recent, so it landed more softly."
              : "";
          const operatorSource = operatorMode
            ? `<br>Episode ${esc(item.id)} · source ${esc(item.source_event_id || "unknown")} · appraisal ${esc(item.appraisal_id || "unknown")}`
            : "";
          return `<article class="emotion-influence ${tone < 0 ? "low" : tone > 0 ? "warm" : "neutral"}"><div class="memory-meta"><span>${esc(date(item.simulated_at))} · ${esc(time(item.simulated_at))}</span><span>${esc(item.resulting_label || "felt response")}</span></div><p>${esc(item.source_text)}</p><div class="memory-source">It ${effect}.${esc(adapted)}${operatorSource}</div></article>`;
        })
        .join("")
    : '<p class="context-note">No source-linked emotional influence has been recorded yet.</p>';
}

function render(next) {
  if (state && next.revision < state.revision) return;
  syncServerPacing(next);
  const changed = !state || next.revision !== state.revision;
  state = next;
  $("preview-banner").hidden = !state.preview;
  renderLifeProgress();
  const liveModel = state.mode !== "stand-in";
  $("backend-label").textContent = liveModel
    ? "LOCAL MODEL PERFORMERS"
    : "STAND-IN PERFORMERS";
  $("backend-model").textContent = liveModel
    ? state.model
    : "Deterministic stand-ins";
  $("engine-connection-title").textContent = liveModel
    ? `Model performers · ${state.model}`
    : "Deterministic stand-ins";
  $("engine-connection-detail").textContent = liveModel
    ? "Roles are served by the configured model endpoint or routes file. Every proposal is still validated before it becomes part of his life."
    : "Authored templates are running every role. Point Eidos at a model endpoint or routes file to hand the roles to real models.";
  $("engine-connection-badge").textContent = liveModel ? "CONNECTED" : "STAND-IN";
  document.querySelector(".mobile-mode").textContent =
    `${liveModel ? "Local model" : "Stand-in"} performers · saved locally`;
  document.querySelector(".disclosure").textContent = liveModel
    ? "Model-generated fiction. Validation checks structure, not truth or consciousness."
    : "Authored voices are running the roles. Real models can join later.";
  $("chat-disclosure").textContent = liveModel
    ? "This experimental voice uses recorded context. It can still misinterpret or invent details. Conversations persist."
    : "This voice uses templates and recorded context. Conversations and memories persist.";
  document
    .querySelectorAll(".small-tag:not(#chat-availability)")
    .forEach((tag) => {
      tag.textContent = liveModel ? "MODEL OUTPUT" : "STAND-IN";
    });
  $("connection").textContent = state.runtime.error
    ? "Worker needs attention"
    : "Connected locally";
  $("connection-dot").style.background = state.runtime.error
    ? "#e69579"
    : "var(--green)";
  const displayedTime = new Date(
    new Date(state.time).getTime() +
      Number(state.runtime.realtime_pending_seconds || 0) * 1000,
  ).toISOString();
  $("clock").textContent =
    `Day ${state.day} · ${date(displayedTime)} · ${time(displayedTime)}`;
  $("weather").textContent = `${state.weather} · ${state.season}`;
  $("life-status").textContent = state.config.running ? "LIVING" : "PAUSED";
  $("play").innerHTML = state.config.running
    ? "Pause world <span>Ⅱ</span>"
    : "Resume world <span>▷</span>";
  if (document.activeElement !== $("speed"))
    $("speed").value =
      state.config.clock_mode === "realtime"
        ? "realtime"
        : state.config.minutes_per_tick;
  $("feed-live").textContent = state.config.running ? "● LIVE" : "PAUSED";
  $("catch-up").textContent = state.catch_up
    ? "Resume catch-up"
    : "Let a day pass";
  $("cancel-catch-up").hidden = !state.catch_up;
  $("worker-status").textContent = state.runtime.worker_alive
    ? state.runtime.working
      ? "Generating next scene…"
      : state.config.clock_mode === "realtime"
        ? "Real-time clock online"
        : "Accelerated clock online"
    : "Worker stopped";
  $("tick-count").textContent = `${state.runtime.ticks} ticks this session`;
  const jobCounts = state.jobs?.counts || {};
  $("job-count").textContent =
    `${jobCounts.queued || 0} queued · ${jobCounts.running || 0} running · ${jobCounts.failed || 0} failed`;
  $("index-status").textContent = state.indexes
    ? `${state.indexes.memory_count} memories · ${state.indexes.term_count} cues indexed at r${state.indexes.memory_revision}`
    : "Memory index unavailable";
  if (state.runtime.error) showError(state.runtime.error);
  setBusy(busy);
  if (!changed) return;
  $("presence-mood").textContent = state.emotion?.secondary_label
    ? `${state.emotion.label} with ${state.emotion.secondary_label}`
    : state.emotion?.label || state.pathos.mood;
  const physical = state.wellbeing?.active;
  $("presence-location").textContent =
    `${state.pathos.awake ? "Awake" : "Asleep"} · At ${state.pathos.location}${physical ? ` · ${physical.kind.replaceAll("_", " ")}` : ""}`;
  const thought = state.feed.find((item) => item.kind === "thought.recorded");
  $("latest-thought").textContent = thought
    ? `“${thought.text}”`
    : "The day is just beginning.";
  renderAheadInMind();
  const inspiration = state.dream_inspirations?.[0];
  $("dream-inspiration").hidden = !inspiration;
  $("dream-inspiration").textContent = inspiration
    ? `A dream left a temporary possibility—not a fact or plan: ${inspiration.suggestion}`
    : "";
  $("energy-value").textContent = `${Math.round(state.pathos.energy * 100)}%`;
  $("energy-meter").style.width = `${state.pathos.energy * 100}%`;
  $("energy-meter").parentElement.setAttribute(
    "aria-valuenow",
    Math.round(state.pathos.energy * 100),
  );
  $("energy-meter").parentElement.setAttribute(
    "aria-valuetext",
    `${Math.round(state.pathos.energy * 100)} percent energy`,
  );
  $("valence-value").textContent =
    state.pathos.valence > 0.15
      ? "Positive"
      : state.pathos.valence < -0.1
        ? "Low"
        : "Balanced";
  $("valence-meter").style.width = `${(state.pathos.valence + 1) * 50}%`;
  $("valence-meter").parentElement.setAttribute(
    "aria-valuenow",
    Math.round((state.pathos.valence + 1) * 50),
  );
  $("valence-meter").parentElement.setAttribute(
    "aria-valuetext",
    `${$("valence-value").textContent} emotional tone`,
  );
  $("arousal-value").textContent = `${Math.round(state.pathos.arousal * 100)}%`;
  $("arousal-meter").style.width = `${state.pathos.arousal * 100}%`;
  $("arousal-meter").parentElement.setAttribute(
    "aria-valuenow",
    Math.round(state.pathos.arousal * 100),
  );
  $("arousal-meter").parentElement.setAttribute(
    "aria-valuetext",
    `${Math.round(state.pathos.arousal * 100)} percent alertness`,
  );
  const episode = state.affect_episodes?.[0];
  const emotion = state.emotion;
  const emotionalPattern = emotion
    ? `${emotion.pattern} ${emotion.label}${emotion.secondary_label ? ` with ${emotion.secondary_label} · ${Math.round(emotion.complexity * 100)}% mixed` : ""}${emotion.sustained_low_hours ? ` · ${emotion.sustained_low_hours} low hours` : ""}`
    : "No emotional sample yet";
  $("affect-source").textContent = episode
    ? `${emotionalPattern}. Latest influence: ${episode.source_kind.replaceAll(".", " ")} · ${episode.valence_delta >= 0 ? "+" : ""}${Number(episode.valence_delta).toFixed(2)} tone · ${episode.arousal_delta >= 0 ? "+" : ""}${Number(episode.arousal_delta).toFixed(2)} arousal`
    : `${emotionalPattern}. No affect episode recorded yet.`;
  renderEmotionHistory();
  const needs = state.pathos.needs;
  const values = Object.entries(state.identity?.values || {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 2)
    .map(([name]) => name[0].toUpperCase() + name.slice(1))
    .join(" · ");
  const activeLayers = (state.mind?.layers || [])
    .map((item) => item.layer)
    .join(" · ");
  const attention = (state.mind?.layers || []).find(
    (item) => item.layer === "attention",
  );
  const domestic = Object.entries(state.household?.loads || {}).sort(
    (a, b) => b[1] - a[1],
  )[0];
  $("needs-summary").textContent =
    `Rest ${Math.round(needs.rest * 100)}% · Hunger ${Math.round(needs.hunger * 100)}% · Connection ${Math.round(needs.connection * 100)}% · Curiosity ${Math.round(needs.curiosity * 100)}% · Mastery ${Math.round(needs.mastery * 100)}%${physical ? ` · Physical capacity ${Math.round((1 - physical.severity) * 100)}%` : ""}${domestic && domestic[1] >= 0.35 ? ` · Home: ${domestic[0]} ${Math.round(domestic[1] * 100)}%` : ""}${values ? ` · Values: ${values}` : ""}${attention ? ` · Attention: ${attention.focus_text}` : ""}${activeLayers ? ` · Mind: ${activeLayers}` : ""}`;
  const preferences = state.identity?.preferences || [];
  const traits = Object.entries(state.identity?.traits || {})
    .map(
      ([name, level]) =>
        `${name.replaceAll("_", " ")} ${Math.round(level * 100)}%`,
    )
    .join(" · ");
  const selfView = state.self_concepts?.[0];
  const activeHabits = (state.habits || [])
    .filter((habit) => habit.status === "active" && habit.activity_type)
    .slice(0, 2)
    .map(
      (habit) =>
        `${habit.activity_type.replaceAll("_", " ")} in the ${habit.time_band}`,
    );
  $("preferences-summary").textContent = preferences.length
    ? `Drawn toward: ${preferences.join(" · ")}${traits ? ` · Tendencies: ${traits}` : ""}${activeHabits.length ? ` · Familiar rhythms: ${activeHabits.join(" · ")}` : ""}${selfView ? ` · Current self-view: ${selfView.text} (${Math.round(selfView.confidence * 100)}% confidence)` : ""}`
    : "Preferences are still taking shape…";
  $("mini-map").innerHTML = mapMarkup(false);
  $("large-map").innerHTML = mapMarkup(true);
  $("recent-feed").innerHTML = feedMarkup(state.feed.slice(0, 7));
  const commitment = state.commitments[0];
  const appointment =
    state.calendar.find(
      (item) => commitment && item.commitment_id === commitment.commitment_id,
    ) || state.calendar[0];
  const object =
    state.objects.find((item) => item.object_id === appointment?.target_id) ||
    state.objects[0];
  const intention =
    state.intentions?.find(
      (item) => commitment && item.goal_id === commitment.goal_id,
    ) || state.intentions?.[0];
  const socialRequest = state.requests?.[0];
  $("life-threads").innerHTML = commitment
    ? `<div><span class="eyebrow">AGREED COMMITMENT</span><strong>${esc(commitment.title)}</strong><small>${esc(commitment.status)} · ${socialRequest ? `${socialRequest.rounds} negotiation round${socialRequest.rounds === 1 ? "" : "s"} · ` : ""}due ${esc(date(commitment.due_at))} ${esc(time(commitment.due_at))}</small></div><div><span class="eyebrow">OWNED INTENTION</span><strong>${esc(intention ? `${intention.action} ${object.name}` : appointment.title)}</strong><small>${esc(intention?.status || appointment.status)} · ${esc(intention?.motivation || "scheduled")} · ${esc(date(appointment.starts_at))} ${esc(time(appointment.starts_at))}</small></div><div><span class="eyebrow">OBJECT STATE</span><strong>${esc(object.name)}</strong><small>${esc(object.condition)} · at ${esc(state.locations.find((place) => place.id === object.location_id)?.name || object.location_id)}</small></div>`
    : '<p class="muted">No active commitments yet.</p>';
  $("neighborhood-status").textContent =
    `${state.people.length} neighbors · ${state.locations.length} places`;
  $("event-count").textContent = state.counts.events.toLocaleString();
  $("memory-count").textContent = state.counts.memories.toLocaleString();
  $("day-count").textContent = state.day;
  $("world-weather").textContent =
    `${state.weather} · ${state.season}`.toUpperCase();
  $("world-threads").innerHTML = (state.world_threads || []).length
    ? state.world_threads
        .map(
          (thread) =>
            `<article class="panel person-card"><div class="panel-kicker">${esc(thread.event_type.replaceAll("_", " ").toUpperCase())} · ${esc(thread.status.toUpperCase())}</div><h2>${esc(thread.theme)}</h2><p>${esc(thread.summary)}</p><div class="person-foot"><span>${esc(state.locations.find((place) => place.id === thread.location_id)?.name || thread.location_id)}</span><span>${thread.status === "active" ? `Stage ${thread.stage} · due ${esc(date(thread.due_at))} ${esc(time(thread.due_at))}` : esc(thread.outcome || "resolved")}</span></div></article>`,
        )
        .join("")
    : '<p class="muted">No neighborhood story is unfolding right now.</p>';
  // Ordinary viewers see his noticeboard; the operator sees the whole town's week.
  const whatsOn = (state.whats_on || []).filter((item) => operatorMode || item.known);
  $("whats-on-section").hidden = !whatsOn.length;
  $("whats-on-note").textContent = operatorMode
    ? "The town's week; faded entries are at places he hasn't found"
    : "The week's ordinary happenings at places he knows";
  $("whats-on").innerHTML = whatsOn
    .map(
      (item) =>
        `<article class="panel person-card${item.known ? "" : " undiscovered"}"><div class="panel-kicker">${esc(date(item.starts_at))} · ${esc(time(item.starts_at))}–${esc(time(item.ends_at))}${operatorMode && item.called_off ? " · CALLED OFF" : ""}</div><h2>${esc(item.title)}</h2><p>${esc(item.note)}</p><div class="person-foot"><span>${esc(item.place)}</span></div></article>`,
    )
    .join("");
  const worldPacks = state.world_packs || [];
  $("world-pack-section").hidden = !worldPacks.length;
  $("world-packs").innerHTML = worldPacks
    .map(
      (pack) =>
        `<article class="panel person-card"><div class="panel-kicker">RELEASE ${pack.version} · VERIFIED MANIFEST</div><h2>${esc(pack.name)}</h2><p>${esc(pack.description)}</p><div class="person-foot"><span>${pack.entity_count || 0} world entities · ${pack.character_fact_count || 0} private histories</span><span>${[...(pack.entity_ids || []), ...(pack.character_fact_ids || [])].map((id) => esc(id)).join(" · ")}</span></div></article>`,
    )
    .join("");
  $("town-signals").innerHTML = (state.external_signals || []).length
    ? state.external_signals
        .slice(0, 6)
        .map(
          (signal) =>
            `<article class="panel person-card"><div class="panel-kicker">${esc(signal.signal_kind.replaceAll("_", " ").toUpperCase())} · ${esc(signal.town)}</div><h2>${esc(signal.title)}</h2><p>${esc(signal.summary)}</p><p class="context-note">External inspiration only. This did not happen to Pathos.</p><div class="person-foot"><span>${esc(signal.source_name)}</span><a href="${esc(signal.source_url)}" target="_blank" rel="noreferrer">View source</a></div></article>`,
        )
        .join("")
    : '<p class="muted">No real-town source is configured. This world is currently self-contained.</p>';
  renderPlace();
  $("people").innerHTML = state.people
    .map((person) => {
      const belief = state.beliefs?.find(
        (item) => item.owner_id === "pathos" && item.subject_id === person.id,
      );
      const preferences = (state.social_preferences || []).filter(
        (item) => item.person_id === person.id,
      );
      const repair = (state.relationship_repairs || [])
        .filter((item) => item.person_id === person.id)
        .at(-1);
      const sharedHistory = (state.character_histories || []).filter(
        (item) => item.person_id === person.id && item.status === "disclosed",
      );
      const preferenceText = preferences.length
        ? `<p class="context-note">Pathos remembers: ${preferences.map((item) => `${item.status === "uncertain" ? "possibly " : ""}${esc(item.stance)} ${esc(item.topic)}`).join(" · ")}</p>`
        : "";
      const repairText = repair
        ? `<p class="context-note">Repair after disagreement: ${esc(repair.status)} · ${repair.contact_count} later contact${repair.contact_count === 1 ? "" : "s"}. This does not claim forgiveness.</p>`
        : "";
      const historyText = sharedHistory.length
        ? `<p class="context-note">Shared with Pathos: ${sharedHistory.map((item) => esc(item.text)).join(" · ")}</p>`
        : "";
      const location = person.location_id
        ? person.location_id === "home"
          ? "Here at home"
          : `Here at ${state.locations.find((p) => p.id === person.location_id)?.name || "this place"}`
        : "Current whereabouts unknown to Pathos";
      return `<article class="panel person-card"><div class="person-head"><span class="avatar" style="color:${person.color}">${esc(person.name[0])}</span><div><h2>${esc(person.name)}</h2><p>${esc(person.occupation)}</p></div></div><p>${esc(person.description)}</p>${belief ? `<p class="context-note">Pathos currently believes: ${esc(belief.predicate.replaceAll("_", " "))} — ${esc(belief.object_value)} (${Math.round(belief.confidence * 100)}% confidence${belief.status === "contested" ? ", contested" : ""}).</p>` : ""}${preferenceText}${repairText}${historyText}<div class="person-foot"><span>${esc(location)}</span><span>${person.encounters} encounters · trust ${Math.round(person.trust * 100)}% · ${esc(person.simulation_tier)} detail</span></div></article>`;
    })
    .join("");
  $("chat-context-mood").textContent = state.emotion?.secondary_label
    ? `${state.emotion.label} with ${state.emotion.secondary_label}`
    : state.emotion?.label || state.pathos.mood;
  $("chat-context-location").textContent =
    `${state.pathos.location} · ${time(displayedTime)}`;
  const communication = state.communication || {};
  $("chat-availability").textContent =
    communication.status === "in_conversation"
      ? "TOGETHER NOW"
      : communication.status === "available"
        ? "AVAILABLE"
        : communication.status === "hurried"
          ? "FREE BRIEFLY"
          : (communication.status || "UNAVAILABLE").toUpperCase();
  $("chat-context-availability").textContent = communication.reason || "";
  const availabilityReason =
    communication.reason || "He may reply when his day allows.";
  const liveActive = communication.status === "in_conversation";
  const replyDue = communication.next_reply_due_at
    ? `${date(communication.next_reply_due_at)} at ${time(communication.next_reply_due_at)}`
    : null;
  let presenceNote;
  if (!state.config.running) {
    presenceNote = "His world is paused by its caretaker. Messages can be delivered, but time and replies will wait until it resumes.";
  } else if (communication.status === "interrupted") {
    presenceNote = `${availabilityReason} You can continue or leave once the interruption passes.`;
  } else if (liveActive) {
    presenceNote = `${availabilityReason} You are together now.`;
  } else if (communication.can_visit) {
    presenceNote = `${availabilityReason} He can sit down and talk now, or you can leave a message.`;
  } else if (communication.waiting_count && replyDue) {
    presenceNote = `${availabilityReason} Your message is waiting; he may reply around ${replyDue}.`;
  } else {
    presenceNote = `${availabilityReason} Your message will wait for him.`;
  }
  if ($("chat-presence-note").textContent !== presenceNote)
    $("chat-presence-note").textContent = presenceNote;
  $("chat-presence-note").classList.toggle("live", liveActive);
  document
    .querySelector(".chat-panel")
    .classList.toggle("live-visit", liveActive);
  $("outreach-toggle").checked = Boolean(state.outreach?.enabled);
  $("visit").hidden = Boolean(communication.live_scene_id);
  $("visit").disabled = !communication.can_visit;
  $("end-visit").hidden = !communication.live_scene_id;
  $("send").textContent = liveActive ? "Speak ↗" : "Send ↗";
  $("delivery-note").textContent = !state.config.running
    ? "World paused · replies resume when its caretaker restarts time."
    : communication.status === "interrupted"
      ? availabilityReason
      : liveActive
    ? `You are speaking together · ${communication.live_elapsed_seconds || 0} seconds have passed in this conversation.`
    : communication.waiting_count
      ? `${communication.waiting_count} delivered message${communication.waiting_count === 1 ? "" : "s"} waiting for a reply.`
      : "Messages are delivered; replies may take time.";
  $("chat-memories").innerHTML = state.memories
    .slice(0, 3)
    .map((item) => `<div class="context-memory">${esc(item.text)}</div>`)
    .join("");
  $("relationship-dates").innerHTML = (state.relationship_dates || []).length
    ? state.relationship_dates
        .map((item) => {
          const person = state.people.find(
            (candidate) => candidate.id === item.person_id,
          );
          const who =
            item.person_id === "user"
              ? "You and Pathos"
              : person?.name || item.person_id;
          const years = item.anniversaries
            ? ` · remembered ${item.anniversaries} year${item.anniversaries === 1 ? "" : "s"}`
            : "";
          return `<div class="context-memory"><strong>${esc(who)}</strong><br>${esc(item.origin_date)}${years}</div>`;
        })
        .join("")
    : '<p class="context-note">No shared date has formed yet.</p>';
  const userPreferences = (state.social_preferences || []).filter(
    (item) => item.person_id === "user",
  );
  $("user-preferences").innerHTML = userPreferences.length
    ? userPreferences
        .map(
          (item) =>
            `<div class="context-memory">Pathos ${item.status === "uncertain" ? "is less sure you " : "remembers that you "}${esc(item.stance)} ${esc(item.topic)}.</div>`,
        )
        .join("")
    : '<p class="context-note">You have not told him a clear preference yet.</p>';
  renderMessages();
  renderArchive();
  if (currentView === "memories" && !archivePage && !archiveLoading)
    loadMemoryArchive(true);
  renderPlans();
  renderSelf();
  renderEngineFeed();
  $("diagnostics").innerHTML =
    (state.diagnostics || [])
      .map(
        (call) =>
          `<article class="memory-card"><div class="memory-meta"><span>${esc(call.role)} · ${esc(call.status)}</span><span>${Math.round(call.latency_ms || 0)} ms</span></div><p>${esc(call.error_code || "Contract accepted — semantic quality not certified")}</p><div class="memory-source">${esc(call.model || "unknown")} · ${esc(call.backend || "unknown")} · ${call.output_tokens ?? "—"} output tokens<br>Trace ${esc(call.trace_id || "legacy")}</div></article>`,
      )
      .join("") || "<p>No calls recorded yet.</p>";
  $("jobs").innerHTML =
    (state.jobs?.recent || [])
      .map(
        (job) =>
          `<article class="memory-card"><div class="memory-meta"><span>${esc(job.capability)} · ${esc(job.status)}</span><span>${job.attempts} attempt${job.attempts === 1 ? "" : "s"}</span></div><p>${esc(job.error_code || "Durable model work")}</p><div class="memory-source">${job.resolved_model ? `${esc(job.resolved_model)} · ${esc(job.backend || "unknown backend")} · ${job.prompt_tokens ?? "—"}/${job.output_tokens ?? "—"} prompt/output tokens<br>` : ""}Profile v${esc(job.task_version)} · ${job.max_output_tokens} token ceiling · temperature ${esc(job.temperature)}<br>Job ${esc(job.id)}${job.deadline_at ? ` · deadline ${esc(time(job.deadline_at))}` : ""}</div>${operatorMode && ["queued", "running"].includes(job.status) ? `<button class="button quiet" data-cancel-job="${esc(job.id)}">Cancel job</button>` : ""}</article>`,
      )
      .join("") || "<p>No durable jobs recorded yet.</p>";
  $("npc-states").innerHTML = (state.npc_states || [])
    .map((person) => {
      const plan = person.plan_title
        ? `<p><strong>${esc(person.plan_title)}</strong> · ${esc(person.plan_status || "unknown")}${person.plan_scheduled_for ? ` · ${esc(date(person.plan_scheduled_for))} ${esc(time(person.plan_scheduled_for))}` : ""}${person.plan_motivation ? `<br><small>${esc(person.plan_motivation)}</small>` : ""}</p>`
        : "";
      return `<article class="memory-card"><div class="memory-meta"><span>${esc(person.actor_id)} · ${esc(person.location_id)}</span><span>PRIVATE OPERATOR LENS</span></div><p>${esc(person.private_activity)}</p>${plan}<div class="memory-source">energy ${Math.round(person.energy * 100)}% · connection ${Math.round(person.connection * 100)}% · purpose ${Math.round(person.purpose * 100)}% · never passed to Pathos automatically</div></article>`;
    })
    .join("");
  $("npc-states").insertAdjacentHTML(
    "beforeend",
    (state.character_histories || [])
      .map(
        (fact) =>
          `<article class="memory-card"><div class="memory-meta"><span>${esc(fact.person_id)} · ${esc(fact.status.toUpperCase())}</span><span>PRIVATE BIOGRAPHY</span></div><p>${esc(fact.text)}</p><div class="memory-source">Topic ${esc(fact.topic)} · reveal after ${Math.round(fact.reveal_after_familiarity * 100)}% familiarity${fact.scene_id ? ` · shared in ${esc(fact.scene_id)}` : " · never passed to Pathos"}</div></article>`,
      )
      .join(""),
  );
  $("npc-states").insertAdjacentHTML(
    "beforeend",
    (state.resident_relationships || [])
      .map((item) => {
        const owner =
          state.people.find((person) => person.id === item.owner_id)?.name ||
          item.owner_id;
        const person =
          state.people.find((candidate) => candidate.id === item.person_id)
            ?.name || item.person_id;
        return `<article class="memory-card"><div class="memory-meta"><span>${esc(owner)} → ${esc(person)}</span><span>PRIVATE RELATIONSHIP</span></div><p>${item.encounters} completed encounter${item.encounters === 1 ? "" : "s"}</p><div class="memory-source">familiarity ${Math.round(item.familiarity * 100)}% · trust ${Math.round(item.trust * 100)}% · tension ${Math.round(item.tension * 100)}% · last shared scene ${esc(item.last_scene_id || "none")}</div></article>`;
      })
      .join(""),
  );
  $("npc-states").insertAdjacentHTML(
    "beforeend",
    (state.npc_beliefs || [])
      .map(
        (item) =>
          `<article class="memory-card"><div class="memory-meta"><span>${esc(item.owner_id)} believes · ${esc(item.status.toUpperCase())}</span><span>PRIVATE BELIEF</span></div><p>${esc(item.subject_id)} · ${esc(item.predicate.replaceAll("_", " "))} → ${esc(item.object_value)}${item.alternative_value ? ` / alternative: ${esc(item.alternative_value)}` : ""}</p><div class="memory-source">confidence ${Math.round(item.confidence * 100)}% · ${item.evidence_count} evidence source${item.evidence_count === 1 ? "" : "s"} · never passed to Pathos without a witnessed public turn</div></article>`,
      )
      .join(""),
  );
  $("npc-states").insertAdjacentHTML(
    "beforeend",
    (state.scenes || [])
      .map((scene) => {
        const clock = (state.conversation_clocks || []).find(
          (item) => item.scene_id === scene.scene_id,
        );
        return `<article class="memory-card"><div class="memory-meta"><span>SCENE · ${esc(scene.status)}</span><span>${scene.turn_count}/${scene.max_turns} TURNS${clock ? ` · ${clock.elapsed_seconds} SEC` : ""}</span></div><p><strong>${esc(scene.initiator_id)} ↔ ${esc(scene.partner_id)}</strong> · ${esc(scene.topic_id)}</p><div class="memory-source">${esc(scene.location_id)}${scene.end_reason ? ` · ended: ${esc(scene.end_reason)}` : scene.status === "paused" ? ` · interrupted by ${esc((scene.interruption_source_id || "an event").slice(0, 8))}` : ` · awaiting ${esc(scene.next_actor_id)}`}</div></article>`;
      })
      .join(""),
  );
  $("roles").innerHTML = state.roles
    .map(
      (role, index) =>
        `<article class="panel role-card"><div class="panel-kicker"><span>0${index + 1} / ${role.id === "critic" ? "RULES" : liveModel ? "MODEL" : "STAND-IN"}</span><span class="role-status">${esc(role.status.toUpperCase())}</span></div><h2>${esc(role.name)}</h2><p>${esc(role.purpose)}</p>${(role.semantic_findings || []).length ? `<div class="quality-warning">Quality review: ${esc(role.semantic_findings.map((item) => item.replaceAll("_", " ")).join(" · "))}</div>` : ""}<div class="role-stats"><span>${role.calls} ${role.id === "critic" ? "checks" : "calls"}</span><span>${role.last ? `${date(role.last)} · ${time(role.last)}` : "Awaiting its moment"}</span></div></article>`,
    )
    .join("");
  $("cognitive-workspace").innerHTML = (state.mind?.workspace || []).length
    ? state.mind.workspace
        .map(
          (item) =>
            `<article class="memory-card"><div class="memory-meta"><span>${esc(item.from_faculty.toUpperCase())} · ${esc(item.kind.replaceAll("_", " ").replaceAll(".", " ").toUpperCase())}</span><span>${Math.round(item.salience * 100)}% SALIENT · ${item.age_minutes} MIN AGO</span></div><p>${esc(item.content)}</p><div class="memory-source">${esc(item.epistemic_status.replaceAll("_", " "))} · can influence attention, but cannot act or become fact by itself</div></article>`,
        )
        .join("")
    : "<p>No thought is holding the foreground right now.</p>";
}

document.addEventListener("click", (event) => {
  const nav = event.target.closest("[data-view]");
  if (nav) showView(nav.dataset.view, true);
  const archiveTarget = event.target.closest("[data-archive-tab]");
  if (archiveTarget) {
    selectArchiveTab(archiveTarget.dataset.archiveTab, true);
    if (archiveTab === "memories") loadMemoryArchive(true);
  }
  const place = event.target.closest("[data-place]");
  if (place && state) {
    selectedPlace = place.dataset.place;
    showView("world");
    $("large-map").innerHTML = mapMarkup(true);
    renderPlace();
  }
  const suggestion = event.target.closest("[data-suggestion]");
  if (suggestion) {
    $("message").value = suggestion.dataset.suggestion;
    $("message").focus();
  }
  const cancel = event.target.closest("[data-cancel-job]");
  if (cancel) mutate(`/api/jobs/${cancel.dataset.cancelJob}/cancel`, {});
});
window.addEventListener("hashchange", () => showView(location.hash.slice(1)));
$("play").addEventListener(
  "click",
  () => state && mutate("/api/control", clockControl(!state.config.running)),
);
$("speed").addEventListener(
  "change",
  () => state && mutate("/api/control", clockControl(state.config.running)),
);
$("step").addEventListener("click", async () => {
  if (await mutate("/api/step", { hours: 1 }))
    toast("One more hour of life, recorded.");
});
$("catch-up").addEventListener("click", async () => {
  if (state?.catch_up) {
    if (await mutate("/api/catch-up/resume", {}))
      toast("Catch-up completed and summarized.");
    return;
  }
  try {
    const preview = await request("/api/catch-up/preview?hours=24");
    const proceed = window.confirm(
      `Let one simulated day pass? ${preview.routine_beats} routine moments, ${preview.scheduled_items} scheduled items, and ${preview.due_commitments} due commitments fall in that time.`,
    );
    if (proceed && (await mutate("/api/catch-up", { hours: 24 })))
      toast("The day passed and a factual recap was recorded.");
  } catch (error) {
    showError(error.message);
  }
});
$("cancel-catch-up").addEventListener("click", async () => {
  if (await mutate("/api/catch-up/cancel", {}))
    toast("Catch-up cancelled at its last saved point.");
});
$("memory-search").addEventListener("input", () => {
  clearTimeout(archiveSearchTimer);
  archiveSearchTimer = setTimeout(() => {
    lastArchiveSignature = "";
    if (archiveTab === "memories") loadMemoryArchive(true);
    else renderArchive();
  }, 250);
});
$("memory-filter").addEventListener("change", () => loadMemoryArchive(true));
$("load-memories").addEventListener("click", () => loadMemoryArchive(false));
document.querySelector(".archive-tabs").addEventListener("keydown", (event) => {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  const tabs = [...document.querySelectorAll("[data-archive-tab]")];
  const current = tabs.findIndex(
    (tab) => tab.dataset.archiveTab === archiveTab,
  );
  const next =
    event.key === "Home"
      ? 0
      : event.key === "End"
        ? tabs.length - 1
        : (current + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) %
          tabs.length;
  selectArchiveTab(tabs[next].dataset.archiveTab, true);
});
$("feed-filter").addEventListener("change", renderEngineFeed);
$("chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy || $("send").disabled) return;
  const text = $("message").value.trim();
  if (!text) return;
  if (!pendingChat || pendingChat.text !== text)
    pendingChat = { text, request_id: crypto.randomUUID() };
  const wasLive = state?.communication?.status === "in_conversation";
  awaitingLiveReply = Boolean(wasLive);
  $("send").textContent = "Sending…";
  if (awaitingLiveReply) renderMessages();
  try {
    if (await mutate("/api/chat", pendingChat, Date.now())) {
      $("message").value = "";
      pendingChat = null;
      $("message").focus();
    }
  } finally {
    awaitingLiveReply = false;
    renderMessages();
  }
  $("send").textContent =
    state?.communication?.status === "in_conversation" ? "Speak ↗" : "Send ↗";
});

$("messages").addEventListener("scroll", () => updateUnread(true), {passive: true});
$("new-messages").addEventListener("click", () => {
  $("messages").scrollTop = $("messages").scrollHeight;
  updateUnread(true);
});
document.addEventListener("visibilitychange", () => updateUnread(true));
$("outreach-toggle").addEventListener("change", async (event) => {
  const enabled = event.target.checked;
  if (await mutate("/api/outreach", { enabled }))
    toast(
      enabled
        ? "Occasional messages enabled."
        : "Occasional messages turned off.",
    );
});
$("visit").addEventListener("click", async () => {
  if (busy) return;
  if (await mutate("/api/visit", { request_id: crypto.randomUUID() }))
    toast(
      state.communication.live_scene_id
        ? "Pathos made room for a conversation."
        : state.communication.reason,
    );
});
$("end-visit").addEventListener("click", async () => {
  if (busy) return;
  if (await mutate("/api/visit/end", { request_id: crypto.randomUUID() }))
    toast("The conversation ended here.");
});
$("message").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    $("chat-form").requestSubmit();
  }
});
$("export").addEventListener("click", async () => {
  try {
    const data = await request("/api/export");
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "eidos-history.json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast("History exported.");
  } catch (error) {
    showError(error.message);
  }
});
async function poll() {
  try {
    const next = await request("/api/state");
    if (disconnected) showError("");
    disconnected = false;
    render(next);
  } catch (error) {
    disconnected = true;
    $("connection").textContent = "Connection interrupted";
    $("connection-dot").style.background = "#e69579";
    showError("Cannot reach the local world. Retrying automatically…");
  } finally {
    setTimeout(poll, 1500);
  }
}
showView(location.hash.slice(1));
poll();
