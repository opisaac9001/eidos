"use strict";
const $ = (id) => document.getElementById(id);
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
  "reflection.recorded": "EVENING REFLECTION",
  "dream.recorded": "A DREAM · NOT WORLD HISTORY",
  "day.summarized": "THE DAYBOOK",
  "memory.recorded": "A MEMORY FORMED",
  "role.failed": "PERFORMER ERROR",
  "memory.recovered": "SOURCE ARCHIVE RECOVERY",
  "request.made": "A REQUEST",
  "social.request_opened": "REQUEST OPENED",
  "social.request_negotiated": "TERMS NEGOTIATED",
  "social.request_accepted": "TERMS ACCEPTED",
  "social.request_declined": "REQUEST DECLINED",
  "intention.adopted": "AN INTENTION FORMED",
  "intention.completed": "AN INTENTION COMPLETED",
  "action.accepted": "ACTION VALIDATED",
  "action.rejected": "ACTION COULD NOT HAPPEN",
  "schedule.interrupted": "PLAN INTERRUPTED",
  "commitment.fulfilled": "PROMISE KEPT",
  "commitment.missed": "COMMITMENT MISSED",
  "planning.rejected": "NO FEASIBLE PLAN",
  "relationship.changed": "RELATIONSHIP CHANGED",
  "dream.recalled": "A DREAM REMEMBERED",
};
const views = {
  observatory: ["THE PRESENT MOMENT", "A life in motion.", "OBSERVATORY"],
  world: [
    "PLACES, PEOPLE & POSSIBILITY",
    "His corner of the world.",
    "THE WORLD",
  ],
  conversation: [
    "A WINDOW INTO HIS LIFE",
    "Spend a little time.",
    "CONVERSATION",
  ],
  memories: ["THE THINGS THAT STAY", "A life, remembered.", "MEMORY ARCHIVE"],
  engine: ["BEHIND THE EXPERIENCE", "An ensemble of minds.", "THE ENSEMBLE"],
};
let state = null,
  currentView = "observatory",
  selectedPlace = "home",
  busy = false;
let lastMessageSignature = "",
  pendingChat = null,
  toastTimer,
  disconnected = false;
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

function showView(view) {
  if (!views[view]) view = "observatory";
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
  if (location.hash !== `#${view}`) history.replaceState(null, "", `#${view}`);
  if (view === "conversation")
    $("messages").scrollTop = $("messages").scrollHeight;
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
  $("error").textContent = message;
  $("error").hidden = !message;
}

async function request(path, body) {
  const response = await fetch(
    path,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
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
  ["play", "step", "speed", "send"].forEach((id) => {
    $(id).disabled = value || !state;
  });
}

async function mutate(path, body) {
  if (busy) return false;
  setBusy(true);
  try {
    render(await request(path, body));
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
  return state.locations
    .map((place) => {
      const here = state.pathos.location_id === place.id;
      const occupants = state.people.filter(
        (person) => person.location_id === place.id && place.id !== "home",
      );
      return `<button class="place ${here ? "current" : ""} ${large && selectedPlace === place.id ? "selected" : ""}" style="left:${place.x}%;top:${place.y}%" data-place="${esc(place.id)}" aria-label="${esc(place.name)}${here ? ", Pathos is here" : ""}"><span class="place-icon" aria-hidden="true">${icons[place.id]}</span><span class="place-label">${esc(place.label)}</span><span class="here">${here ? "● PATHOS" : occupants.length ? `${occupants.length} NEIGHBOR${occupants.length > 1 ? "S" : ""}` : " "}</span></button>`;
    })
    .join("");
}

function renderPlace() {
  if (!state) return;
  const place = state.locations.find((p) => p.id === selectedPlace);
  const pathosHere = state.pathos.location_id === place.id;
  const people = state.people.filter(
    (p) => p.location_id === place.id && place.id !== "home",
  );
  $("place-detail").innerHTML =
    `<div class="panel-kicker">A PLACE IN FIRMAMENT <span class="muted">0${state.locations.indexOf(place) + 1}</span></div><h2>${esc(place.name)}</h2><p>${esc(place.description)}</p><div class="eyebrow">HERE RIGHT NOW</div>${pathosHere ? '<div class="occupant"><span class="avatar">P</span><span>Pathos</span></div>' : ""}${people.map((p) => `<div class="occupant"><span class="avatar">${esc(p.name[0])}</span><span>${esc(p.name)}</span></div>`).join("")}${!pathosHere && !people.length ? "<p>No one is here at the moment.</p>" : ""}${place.id === "home" ? '<p class="context-note">Neighbors have their own homes; they do not share Pathos’s apartment.</p>' : ""}`;
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

function renderArchive() {
  if (!state) return;
  const query = $("memory-search").value.toLowerCase().trim();
  const category = $("memory-filter").value;
  const items = state.memories.filter(
    (item) =>
      (!query || item.text.toLowerCase().includes(query)) &&
      (category === "all" || (item.category || "experience") === category),
  );
  $("archive-count").textContent =
    `${items.length} matching memories · ${state.counts.memories} recorded in total${state.counts.memories > 300 ? " · browsing the latest 300" : ""}`;
  $("memory-list").innerHTML = items.length
    ? items
        .map(
          (item) =>
            `<article class="memory-card"><div class="memory-meta"><span>${esc(date(item.simulated_at))} · ${esc(time(item.simulated_at))}</span><span>${esc((item.category || "experience").toUpperCase())} · ${Math.round((item.accessibility ?? 1) * 100)}% ACCESSIBLE</span></div><p>${esc(item.text)}</p><div class="memory-source">${esc(item.source || "authored-routine")}${item.source_event_id ? ` · linked to event ${esc(item.source_event_id.slice(0, 8))}` : ""}</div></article>`,
        )
        .join("")
    : '<div class="empty">No memories match that search.</div>';
  $("recall-traces").innerHTML = (state.recalls || []).length
    ? state.recalls
        .slice(0, 30)
        .map((trace) => {
          const memory = state.memories.find(
            (item) => item.id === trace.memory_id,
          );
          return `<article class="memory-card"><div class="memory-meta"><span>${esc(date(trace.simulated_at))} · ${esc(trace.query_source || "context")}</span><span>SCORE ${Number(trace.score || 0).toFixed(3)}</span></div><p>${esc(memory?.text || `Memory ${trace.memory_id.slice(0, 8)}`)}</p><div class="memory-source">${esc(trace.reason)}<br>lexical ${Number(trace.lexical_score || 0).toFixed(3)} · entities ${Number(trace.entity_score || 0).toFixed(3)} · goals ${Number(trace.goal_score || 0).toFixed(3)} · access ${Number(trace.accessibility_score || 0).toFixed(3)} · importance ${Number(trace.importance_score || 0).toFixed(3)} · confidence ${Number(trace.confidence_score || 0).toFixed(3)}</div></article>`;
        })
        .join("")
    : "<p>No explicit recall decisions recorded yet.</p>";
}

function renderEngineFeed() {
  if (!state) return;
  const filter = $("feed-filter").value;
  $("engine-feed").innerHTML = feedMarkup(
    state.feed.filter((item) => filter === "all" || item.kind === filter),
    true,
  );
}

function renderMessages() {
  const signature = state.conversations.map((item) => item.id).join(":");
  if (signature === lastMessageSignature && $("messages").childElementCount)
    return;
  lastMessageSignature = signature;
  const nearBottom =
    $("messages").scrollHeight -
      $("messages").scrollTop -
      $("messages").clientHeight <
    90;
  $("messages").innerHTML = state.conversations.length
    ? state.conversations
        .map(
          (item) =>
            `<article class="message ${item.speaker === "you" ? "you" : "pathos"}"><div class="message-author">${item.speaker === "you" ? "YOU" : item.speaker === "system" ? "SYSTEM" : "PATHOS"} <span>${esc(date(item.simulated_at))} · ${esc(time(item.simulated_at))}</span></div><div class="message-body">${esc(item.text)}</div></article>`,
        )
        .join("")
    : '<div class="empty"><div class="identity-disc" style="margin:15px auto 30px">P</div><h2>He has a day to tell you about.</h2><p>Ask about where he is, how he feels, or what he remembers.</p><button class="suggestion" data-suggestion="How has your day been?">How has your day been?</button><button class="suggestion" data-suggestion="What are you doing?">What are you doing?</button></div>';
  if (nearBottom || currentView === "conversation")
    $("messages").scrollTop = $("messages").scrollHeight;
}

function render(next) {
  if (state && next.revision < state.revision) return;
  const changed = !state || next.revision !== state.revision;
  state = next;
  const liveModel = state.mode !== "stand-in";
  $("backend-label").textContent = liveModel
    ? "LOCAL MODEL PERFORMERS"
    : "STAND-IN PERFORMERS";
  $("backend-model").textContent = liveModel
    ? state.model
    : "Deterministic stand-ins";
  document.querySelector(".mobile-mode").textContent =
    `${liveModel ? "Local model" : "Stand-in"} performers · saved locally`;
  document.querySelector(".disclosure").textContent = liveModel
    ? "Model-generated fiction. Validation checks structure, not truth or consciousness."
    : "Authored voices are running the roles. Real models can join later.";
  document.querySelector(".context-note").textContent = liveModel
    ? "This experimental voice uses recorded context. It can still misinterpret or invent details. Conversations persist."
    : "This voice uses templates and recorded context. Conversations and memories persist.";
  document.querySelectorAll(".small-tag").forEach((tag) => {
    tag.textContent = liveModel ? "MODEL OUTPUT" : "STAND-IN";
  });
  $("connection").textContent = state.runtime.error
    ? "Worker needs attention"
    : "Connected locally";
  $("connection-dot").style.background = state.runtime.error
    ? "#e69579"
    : "var(--green)";
  $("clock").textContent =
    `Day ${state.day} · ${date(state.time)} · ${time(state.time)}`;
  $("weather").textContent = state.weather;
  $("life-status").textContent = state.config.running ? "LIVING" : "PAUSED";
  $("play").innerHTML = state.config.running
    ? "Pause world <span>Ⅱ</span>"
    : "Resume world <span>▷</span>";
  if (document.activeElement !== $("speed"))
    $("speed").value = state.config.minutes_per_tick;
  $("feed-live").textContent = state.config.running ? "● LIVE" : "PAUSED";
  $("worker-status").textContent = state.runtime.worker_alive
    ? state.runtime.working
      ? "Generating next scene…"
      : "Chronos worker online"
    : "Worker stopped";
  $("tick-count").textContent = `${state.runtime.ticks} ticks this session`;
  const jobCounts = state.jobs?.counts || {};
  $("job-count").textContent =
    `${jobCounts.queued || 0} queued · ${jobCounts.running || 0} running · ${jobCounts.failed || 0} failed`;
  if (state.runtime.error) showError(state.runtime.error);
  setBusy(busy);
  if (!changed) return;
  $("presence-mood").textContent = state.pathos.mood;
  $("presence-location").textContent = `At ${state.pathos.location}`;
  const thought = state.feed.find((item) => item.kind === "thought.recorded");
  $("latest-thought").textContent = thought
    ? `“${thought.text}”`
    : "The day is just beginning.";
  $("energy-value").textContent = `${Math.round(state.pathos.energy * 100)}%`;
  $("energy-meter").style.width = `${state.pathos.energy * 100}%`;
  $("valence-value").textContent =
    state.pathos.valence > 0.15
      ? "Positive"
      : state.pathos.valence < -0.1
        ? "Low"
        : "Balanced";
  $("valence-meter").style.width = `${(state.pathos.valence + 1) * 50}%`;
  $("mini-map").innerHTML = mapMarkup(false);
  $("large-map").innerHTML = mapMarkup(true);
  $("recent-feed").innerHTML = feedMarkup(state.feed.slice(0, 7));
  const commitment = state.commitments[0];
  const appointment = state.calendar[0];
  const object = state.objects[0];
  const intention = state.intentions?.[0];
  const socialRequest = state.requests?.[0];
  $("life-threads").innerHTML = commitment
    ? `<div><span class="eyebrow">AGREED COMMITMENT</span><strong>${esc(commitment.title)}</strong><small>${esc(commitment.status)} · ${socialRequest ? `${socialRequest.rounds} negotiation round${socialRequest.rounds === 1 ? "" : "s"} · ` : ""}due ${esc(date(commitment.due_at))} ${esc(time(commitment.due_at))}</small></div><div><span class="eyebrow">OWNED INTENTION</span><strong>${esc(intention ? `${intention.action} ${object.name}` : appointment.title)}</strong><small>${esc(intention?.status || appointment.status)} · ${esc(intention?.motivation || "scheduled")} · ${esc(date(appointment.starts_at))} ${esc(time(appointment.starts_at))}</small></div><div><span class="eyebrow">OBJECT STATE</span><strong>${esc(object.name)}</strong><small>${esc(object.condition)} · at ${esc(state.locations.find((place) => place.id === object.location_id)?.name || object.location_id)}</small></div>`
    : '<p class="muted">No active commitments yet.</p>';
  $("neighborhood-status").textContent =
    `${state.people.length} neighbors · ${state.locations.length} places`;
  $("event-count").textContent = state.counts.events.toLocaleString();
  $("memory-count").textContent = state.counts.memories.toLocaleString();
  $("day-count").textContent = state.day;
  $("world-weather").textContent = state.weather.toUpperCase();
  renderPlace();
  $("people").innerHTML = state.people
    .map(
      (person) =>
        `<article class="panel person-card"><div class="person-head"><span class="avatar" style="color:${person.color}">${esc(person.name[0])}</span><div><h2>${esc(person.name)}</h2><p>${esc(person.occupation)}</p></div></div><p>${esc(person.description)}</p><div class="person-foot"><span>${person.location_id === "home" ? "At their own home" : esc(state.locations.find((p) => p.id === person.location_id).name)}</span><span>${person.encounters} encounters · trust ${Math.round(person.trust * 100)}%</span></div></article>`,
    )
    .join("");
  $("chat-context-mood").textContent = state.pathos.mood;
  $("chat-context-location").textContent =
    `${state.pathos.location} · ${time(state.time)}`;
  $("chat-memories").innerHTML = state.memories
    .slice(0, 3)
    .map((item) => `<div class="context-memory">${esc(item.text)}</div>`)
    .join("");
  renderMessages();
  renderArchive();
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
          `<article class="memory-card"><div class="memory-meta"><span>${esc(job.capability)} · ${esc(job.status)}</span><span>${job.attempts} attempt${job.attempts === 1 ? "" : "s"}</span></div><p>${esc(job.error_code || "Durable model work")}</p><div class="memory-source">Job ${esc(job.id)}</div>${["queued", "running"].includes(job.status) ? `<button class="button quiet" data-cancel-job="${esc(job.id)}">Cancel job</button>` : ""}</article>`,
      )
      .join("") || "<p>No durable jobs recorded yet.</p>";
  $("roles").innerHTML = state.roles
    .map(
      (role, index) =>
        `<article class="panel role-card"><div class="panel-kicker"><span>0${index + 1} / ${role.id === "critic" ? "RULES" : liveModel ? "MODEL" : "STAND-IN"}</span><span class="role-status">${esc(role.status.toUpperCase())}</span></div><h2>${esc(role.name)}</h2><p>${esc(role.purpose)}</p><div class="role-stats"><span>${role.calls} ${role.id === "critic" ? "checks" : "calls"}</span><span>${role.last ? `${date(role.last)} · ${time(role.last)}` : "Awaiting its moment"}</span></div></article>`,
    )
    .join("");
}

document.addEventListener("click", (event) => {
  const nav = event.target.closest("[data-view]");
  if (nav) showView(nav.dataset.view);
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
  () =>
    state &&
    mutate("/api/control", {
      running: !state.config.running,
      minutes_per_tick: Number($("speed").value),
    }),
);
$("speed").addEventListener(
  "change",
  () =>
    state &&
    mutate("/api/control", {
      running: state.config.running,
      minutes_per_tick: Number($("speed").value),
    }),
);
$("step").addEventListener("click", async () => {
  if (await mutate("/api/step", { hours: 1 }))
    toast("One more hour of life, recorded.");
});
$("memory-search").addEventListener("input", renderArchive);
$("memory-filter").addEventListener("change", renderArchive);
$("feed-filter").addEventListener("change", renderEngineFeed);
$("chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy) return;
  const text = $("message").value.trim();
  if (!text) return;
  if (!pendingChat || pendingChat.text !== text)
    pendingChat = { text, request_id: crypto.randomUUID() };
  $("send").textContent = "Thinking…";
  if (await mutate("/api/chat", pendingChat)) {
    $("message").value = "";
    pendingChat = null;
    $("message").focus();
  }
  $("send").textContent = "Send ↗";
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
