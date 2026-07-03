// Thin API client for the Pattern Recognition backend (the standalone
// patterns service). Local dev talks to it directly on :8003. In production
// (ECS + ALB) set VITE_PATTERNS_API_BASE to the gateway/ALB path, e.g.
// "https://<alb-host>/patterns".
import { getLang } from "./lib/lang.js";

const BASE = import.meta.env.VITE_PATTERNS_API_BASE || "http://localhost:8003";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText} — ${text}`);
  }
  // 204 / empty bodies
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : null;
}

export const api = {
  health: () => request("/health"),

  getState: (householdId) => request(`/state/${householdId}`),

  getPatterns: (householdId) => request(`/patterns/${householdId}`),

  // `at` is an optional "HH:MM" simulated clock value.
  getContext: (householdId, at) =>
    request(
      `/context/${householdId}${at ? `?at=${encodeURIComponent(at)}` : ""}`,
    ),

  // Evaluate a user-supplied what-if state against the learned patterns.
  // This powers the "set the state + clock, then hit Go" flow: the supplied
  // device states are compared to the patterns in-memory only (nothing is
  // persisted, so repeated evaluations never pollute the demo data).
  evaluate: (
    householdId,
    { at, activeDevices, peopleHome, deviceOnSince } = {},
  ) =>
    request(`/context/${householdId}/evaluate`, {
      method: "POST",
      body: JSON.stringify({
        current_time: at || null,
        active_devices: activeDevices || [],
        people_home: peopleHome || {},
        device_on_since: deviceOnSince || {},
      }),
    }),

  // Turn a context object into a natural, spoken-style "Alexa says…" line.
  // The backend uses Groq when GROQ_API_KEY is set, else a deterministic
  // fallback sentence. Returns { alexa_response, llm_powered, reasoning }.
  narrate: (context) =>
    request(`/context/narrate`, {
      method: "POST",
      body: JSON.stringify(context),
    }),

  // Narrate EACH detected issue separately so no detail is lost to compression.
  // Returns { narrations: [{ alexa_response, explanation, llm_powered,
  // device, anomaly_type, severity }, ...] } ordered most-severe-first, ready
  // to be shown/spoken one-by-one as a sequence of floating notifications.
  narrateEach: (context) =>
    request(`/context/narrate/each?language=${getLang()}`, {
      method: "POST",
      body: JSON.stringify(context),
    }),

  // LLM-generated, deterministically-verified CONTEXT-CONDITIONAL patterns.
  // The LLM proposes rules ("AC only on hot days"); the backend re-measures each
  // against real history and returns only the ones the data supports. `ctx` is
  // the live house context (temperature, weekend, who's home) used to flag which
  // conditional patterns apply right now. Returns a ContextualResponse.
  contextual: (householdId, ctx = {}) =>
    request(`/patterns/${householdId}/contextual`, {
      method: "POST",
      body: JSON.stringify({
        temperature_c: ctx.temperatureC ?? null,
        is_weekend: ctx.isWeekend ?? null,
        occupants: ctx.occupants || [],
        at: ctx.at || null,
      }),
    }),


  // Fetch events for a household. With no options it returns the full
  // chronological history (the backend paginates); pass { since, limit } to
  // constrain the window or grab only the latest N.
  getEvents: (householdId, { since, limit } = {}) => {
    const params = new URLSearchParams({ household_id: householdId });
    if (since) params.set("since", since);
    if (limit) params.set("limit", String(limit));
    return request(`/events?${params.toString()}`);
  },

  postEvent: (event) =>
    request("/events", { method: "POST", body: JSON.stringify(event) }),

  seed: (householdId) =>
    request(`/admin/seed/${householdId}`, { method: "POST" }),

  // ── Ambient sound understanding (the household "ear") ──────────────────────
  // The browser classifies mic audio locally (MediaPipe YAMNet); these endpoints
  // interpret a detected sound, learn sound-routines, and expose the taxonomy.
  ambientSounds: () => request(`/ambient/sounds`),
  ambientObserve: (householdId, body) =>
    request(`/ambient/${householdId}/observe`, {
      method: "POST",
      body: JSON.stringify({ language: getLang(), ...body }),
    }),
  ambientRoutines: (householdId) => request(`/ambient/${householdId}/routines`),

  // ── User context notes → temporary pattern adjustments (guests / festivals) ─
  // Speak/type an occasion; the LLM previews adjustments; apply persists them as
  // a reversible overlay on the learned patterns.
  contextNote: (householdId, { text, audioBase64, audioFormat } = {}) =>
    request(`/context/${householdId}/note`, {
      method: "POST",
      body: JSON.stringify({
        text: text || null,
        audio_base64: audioBase64 || null,
        audio_format: audioFormat || "webm",
      }),
    }),
  applyContextPlan: (householdId, plan) =>
    request(`/context/${householdId}/note/apply`, {
      method: "POST",
      body: JSON.stringify({
        occasion: plan.occasion || "",
        occasion_date: plan.occasion_date || "",
        summary: plan.summary || "",
        adjustments: plan.adjustments || [],
      }),
    }),
  getAdjustments: (householdId) => request(`/context/${householdId}/adjustments`),
  deleteAdjustment: (householdId, id) =>
    request(`/context/${householdId}/adjustments/${id}`, { method: "DELETE" }),
  clearAdjustments: (householdId) =>
    request(`/context/${householdId}/adjustments`, { method: "DELETE" }),
  // The learned daily routine with the active occasion overlay applied.
  effectiveSchedule: (householdId) =>
    request(`/context/${householdId}/effective-schedule`),
  // Send a recorded mic clip to the audio LLM (Gemini) for open-vocab detection.
  ambientListen: (householdId, body) =>
    request(`/ambient/${householdId}/listen`, {
      method: "POST",
      body: JSON.stringify({ language: getLang(), ...body }),
    }),
  ambientSeed: (householdId) =>
    request(`/ambient/${householdId}/seed`, { method: "POST" }),
};

export { BASE as API_BASE };
