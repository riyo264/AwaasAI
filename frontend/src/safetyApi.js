// Thin API client for the Adaptive Safety Intelligence backend — an INDEPENDENT
// twin of the patterns engine running on its own port (:8006). It never touches
// the patterns service, so the two features are fully isolated.
import { getLang } from "./lib/lang.js";

const BASE =
  import.meta.env.VITE_SAFETY_API_BASE || "http://localhost:8006";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText} — ${text}`);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : null;
}

export const safetyApi = {
  health: () => request("/health"),

  // The full Adaptive Safety Dashboard payload (context + safety + profiles +
  // state + timeline + patterns). `at` is an optional "HH:MM" demo clock.
  getSafety: (householdId, at) =>
    request(
      `/safety/${householdId}${at ? `?at=${encodeURIComponent(at)}` : ""}`,
    ),

  // Seed the elderly home with a specific "today" safety scenario:
  // normal | inactivity | gas | window_night | health | sos
  seed: (householdId, scenario = "normal") =>
    request(
      `/admin/seed/${householdId}?scenario=${encodeURIComponent(scenario)}`,
      { method: "POST" },
    ),

  // Swap WHO is home (and how vulnerable) without re-seeding events:
  // elderly | child_alone | pregnant_alone | unwell_alone | mixed_support
  setHousehold: (householdId, preset = "elderly") =>
    request(
      `/admin/profiles/${householdId}?preset=${encodeURIComponent(preset)}`,
      { method: "POST" },
    ),

  // The live "dollhouse" evaluation: send the exact current board (which
  // devices are ON, who is placed in the home + how vulnerable, the demo clock,
  // and any momentary signals) and get back a fully vulnerability-aware
  // ContextObject. Nothing is persisted — every call is ephemeral, so the demo
  // data is never mutated no matter how much the user pokes at the home.
  //
  // body = {
  //   current_time?: "HH:MM",
  //   active_devices: string[],
  //   device_on_since?: { [deviceId]: ISOString },
  //   people_home?: { [personId]: boolean },
  //   profiles?: PersonProfile[],          // the placed cast
  //   signals?: EvaluateSignal[],          // SOS / health / last-seen pings
  //   ignore_stored_events?: boolean,      // clean "quiet house" inactivity
  // }
  evaluate: (householdId, body) =>
    request(`/context/${householdId}/evaluate`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  scenarios: () => request("/admin/scenarios"),

  // ── Guardian: elderly-alone triage + check-in-before-alarm ────────────────
  // Send the same dollhouse board; the Guardian runs the deterministic safety
  // evaluation, then triages the raised concerns to the single most dangerous +
  // relevant one and decides: raise the alarm now (extreme) or check in with the
  // person first (less serious). Returns a GuardianDecision.
  guardianAssess: (householdId, body) =>
    request(`/guardian/${householdId}/assess`, {
      method: "POST",
      body: JSON.stringify({ language: getLang(), ...body }),
    }),
  // Interpret the person's reply to a check-in → stand down or escalate.
  guardianCheckin: (householdId, body) =>
    request(`/guardian/${householdId}/checkin/respond`, {
      method: "POST",
      body: JSON.stringify({ language: getLang(), ...body }),
    }),

  // Narrate each detected concern as its own spoken Alexa line (most-severe
  // first), so the dashboard can stack + read them one-by-one.
  narrateEach: (context) =>
    request(`/context/narrate/each?language=${getLang()}`, {
      method: "POST",
      body: JSON.stringify(context),
    }),
};

export { BASE as SAFETY_API_BASE };
