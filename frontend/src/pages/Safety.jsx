import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { safetyApi } from "../safetyApi.js";

// ════════════════════════════════════════════════════════════════════════════
//  THE GUARDIAN — a GUIDED, INTERACTIVE walkthrough of defence-in-depth safety.
//  ---------------------------------------------------------------------------
//  One subject (Ramesh, 78, home alone) and three layers, each introduced in
//  turn — and each DRIVEN BY REAL CHOICES, not a hardcoded script:
//
//    ① Wellbeing — his real learned routine is shown; tap the one he MISSED →
//       the Guardian gently CHECKS IN (a reassuring reply clears the flag).
//    ② Hazards   — pick a hazard (gas / water / door / window). It corroborates
//       the open wellbeing concern → two layers agree → the tone HEIGHTENS to an
//       escalation.
//    ③ Vital signs — a wearable SOS → the most urgent response, instant alarm.
//
//  Every scene calls the SAME real backend (guardianAssess / checkin); the
//  narrator LLM phrases each one, so the tone escalates on its own — gentle for
//  a missed routine, serious for a hazard, gravest for an SOS.
// ════════════════════════════════════════════════════════════════════════════

const HID = "E001";
const DEFAULT_CLOCK = "11:00";

// The cast you can place as "home alone". Vulnerability drives the escalation
// factor the engine multiplies every concern by. Ramesh/Saroja are the two
// residents whose daily routine + medicine the home has actually learned; the
// others demonstrate how the SAME event escalates differently by who's home.
const ROSTER = [
  { id: "grandpa", name: "Ramesh", age: 78, emoji: "👴", vuln: "elderly", factor: "×2.0", medicine: "grandpa_medicine" },
  { id: "grandma", name: "Saroja", age: 75, emoji: "👵", vuln: "elderly", factor: "×2.0", medicine: "grandma_medicine" },
  { id: "meera", name: "Meera", age: 29, emoji: "🤰", vuln: "pregnant", factor: "×1.8", medicine: null },
  { id: "ravi", name: "Ravi", age: 34, emoji: "🤒", vuln: "unwell", factor: "×1.8", medicine: null },
  { id: "aarav", name: "Aarav", age: 9, emoji: "🧒", vuln: "child", factor: "×1.7", medicine: null },
  { id: "arjun", name: "Arjun", age: 41, emoji: "🧑", vuln: "normal", factor: "×1.0", medicine: null },
];
const ROSTER_BY_ID = Object.fromEntries(ROSTER.map((p) => [p.id, p]));
const VULN_LABEL = { elderly: "Elderly", pregnant: "Expecting", unwell: "Recovering", child: "Child", normal: "Capable adult" };

// Activity sensors kept "alive" so the clock never manufactures phantom
// inactivity — a missed routine must be a deliberate choice.
const LIVENESS = ["grandpa_activity", "grandma_activity", "kitchen_activity", "living_activity"];

// The home's learned morning routine (matches E001's 30-day seeded history). The
// `miss` entries can be skipped to produce a real MISSED_ROUTINE / INACTIVITY.
// The medicine step is person-specific and added at runtime (only Ramesh/Saroja
// have a learned medicine routine).
const ROUTINE = [
  { icon: "🌅", label: "Wakes up", time: "06:30" },
  { icon: "🚶", label: "Morning walk", time: "07:00" },
  { icon: "🪔", label: "Morning pooja", time: "07:30", miss: "pooja_lamp" },
  { icon: "🍳", label: "Breakfast", time: "08:00", miss: "kitchen_activity" },
];

// Home hazards the user can introduce. Gas/water overrun (duration); door/window
// left open far too long (safety-net) AND flagged as a security emergency when
// it's night. Each corroborates the wellbeing concern.
const HAZARDS = {
  gas: { icon: "🔥", label: "Gas stove", note: "left on for an hour", device: "kitchen_gas_stove", onMin: -70, night: false },
  water: { icon: "🚰", label: "Water motor", note: "overflowing the tank", device: "water_motor", onMin: -40, night: false },
  door: { icon: "🚪", label: "Front door", note: "open — worse at night", device: "main_door", onMin: -800, night: true },
  window: { icon: "🪟", label: "Bedroom window", note: "open — worse at night", device: "bedroom_window", onMin: -800, night: true },
};

const LAYERS = [
  {
    id: 1, key: "wellbeing", icon: "🚶", name: "Wellbeing", tagline: "A gentle nudge",
    watches: "Is he up and following his routine?",
    demonstrates:
      "Layer 1 never alarms the family first. A missed routine could be nothing — so the Guardian gently checks in. A reassuring reply clears the flag; silence or distress escalates.",
    accent: "sky",
  },
  {
    id: 2, key: "hazard", icon: "🔥", name: "Home Hazards", tagline: "Raises the stakes",
    watches: "Is the home itself safe right now?",
    demonstrates:
      "Layer 2 watches the home. A hazard next to an open wellbeing concern means two independent layers agree — so the gentle check-in becomes an urgent escalation. The narrator's tone hardens on its own.",
    accent: "amber",
  },
  {
    id: 3, key: "vitals", icon: "❤️", name: "Vital Signs", tagline: "The ground truth",
    watches: "Is he physically okay?",
    demonstrates:
      "Layer 3 is certain. When a vital signal or SOS fires there is no check-in and no waiting — the family is alerted instantly. It's the high-confidence backstop, but layers 1 and 2 need no wearable at all.",
    accent: "rose",
  },
];

const ACCENT = {
  sky: { ring: "border-sky-500/60", bg: "bg-sky-500/10", text: "text-sky-300", solid: "bg-sky-500" },
  amber: { ring: "border-amber-500/60", bg: "bg-amber-500/10", text: "text-amber-300", solid: "bg-amber-500" },
  rose: { ring: "border-rose-500/60", bg: "bg-rose-500/10", text: "text-rose-300", solid: "bg-rose-500" },
};
const SEV_FILL = { clear: "text-emerald-300", low: "text-sky-300", medium: "text-amber-300", high: "text-orange-300", critical: "text-red-300" };

function isoAtClock(clock, offsetMin = 0) {
  const [h, m] = clock.split(":").map(Number);
  const d = new Date();
  d.setUTCHours(h, m + offsetMin, 0, 0);
  return d.toISOString();
}

function blobToBase64(blob) {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onloadend = () => res(String(r.result).split(",")[1]);
    r.onerror = rej;
    r.readAsDataURL(blob);
  });
}

// Build the exact board state for a step from the live CHOICES — who is home
// (vulnerability), the demo clock, which routine was missed, which hazard — then
// let the REAL Guardian decide.
function buildRequest(step, { missed, hazard, person, clock }) {
  const p = ROSTER_BY_ID[person] || ROSTER_BY_ID.grandpa;
  const skipDev = missed || "pooja_lamp";
  const wearable = `${p.id}_wearable`;
  const req = {
    current_time: clock,
    active_devices: [],
    device_on_since: {},
    people_home: { [p.id]: true },
    profiles: [{
      person_id: p.id, display_name: `${p.name} (${VULN_LABEL[p.vuln]})`, vulnerability: p.vuln,
      wearable_id: wearable, relation: null, emergency_contacts: ["son_bangalore", "daughter_pune"],
    }],
    signals: LIVENESS.filter((id) => id !== skipDev).map((id) => ({
      device_id: id, device_type: "activity", room: "home", action: "ACTIVE", triggered_by: "system", minutes_ago: 5,
    })),
    // Own today's picture entirely: drop the stored event tail, then rebuild it
    // from synthetic completions (skip = the missed routine) + the liveness
    // pings above. This makes a missed routine deterministic, independent of when
    // the demo home was seeded.
    ignore_stored_events: true,
    healthy_baseline: true,
    skip_completions: [],
  };
  if (step >= 1) req.skip_completions.push(skipDev);
  if (step >= 2) {
    const h = HAZARDS[hazard || "gas"];
    req.active_devices.push(h.device);
    req.device_on_since[h.device] = isoAtClock(clock, h.onMin);
  }
  if (step >= 3) {
    req.signals.push({ device_id: wearable, device_type: "wearable", room: "living_room", action: "SOS", triggered_by: p.id, minutes_ago: 1 });
  }
  return req;
}

function speak(text) {
  try {
    if (!text || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
  } catch { /* best-effort */ }
}

export default function Safety() {
  const [theme, setTheme] = useState(() => localStorage.getItem("pp-theme") || "dark");
  const [step, setStep] = useState(0);            // 0 intro · 1-3 layers · 4 complete
  const [person, setPerson] = useState("grandpa"); // who is home alone
  const [clock, setClock] = useState(DEFAULT_CLOCK); // simulated time of day
  const [missed, setMissed] = useState(null);     // routine device chosen in Layer 1
  const [hazard, setHazard] = useState(null);     // hazard key chosen in Layer 2
  const [triggered, setTriggered] = useState(false);
  const [decision, setDecision] = useState(null);
  const [verdict, setVerdict] = useState(null);
  const [busy, setBusy] = useState(false);
  const [checkBusy, setCheckBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [connected, setConnected] = useState(true);
  const mrRef = useRef(null);

  useEffect(() => { localStorage.setItem("pp-theme", theme); }, [theme]);

  useEffect(() => {
    (async () => {
      try {
        const s = await safetyApi.getSafety(HID);
        if (!s?.patterns_count) await safetyApi.seed(HID, "normal");
        setConnected(true);
      } catch { setConnected(false); }
    })();
  }, []);

  const subject = ROSTER_BY_ID[person] || ROSTER_BY_ID.grandpa;
  const layer = step >= 1 && step <= 3 ? LAYERS[step - 1] : null;

  const runAssess = useCallback(async (s, choices) => {
    setBusy(true);
    setVerdict(null);
    try {
      const d = await safetyApi.guardianAssess(HID, buildRequest(s, { person, clock, ...choices }));
      setDecision(d);
      setTriggered(true);
      setConnected(true);
      speak(d?.spoken);
    } catch { setConnected(false); } finally { setBusy(false); }
  }, [person, clock]);

  // Layer 1 — miss a routine.
  const missRoutine = useCallback((device) => {
    setMissed(device);
    runAssess(1, { missed: device, hazard });
  }, [hazard, runAssess]);

  // Layer 2 — pick a hazard.
  const pickHazard = useCallback((key) => {
    setHazard(key);
    runAssess(2, { missed, hazard: key });
  }, [missed, runAssess]);

  // Layer 3 — fire the SOS.
  const fireSos = useCallback(() => {
    runAssess(3, { missed, hazard });
  }, [missed, hazard, runAssess]);

  // Re-run the current step's assessment when the time of day changes (so the
  // same board flags differently — e.g. an open window becomes unsafe at night).
  useEffect(() => {
    if (!triggered || !layer) return;
    runAssess(layer.id, { missed, hazard });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clock]);

  const respond = useCallback(async ({ text, audioBase64 } = {}) => {
    if (!decision) return;
    setCheckBusy(true);
    try {
      const v = await safetyApi.guardianCheckin(HID, {
        text: text ?? null, audio_base64: audioBase64 || null, audio_format: "webm",
        person: decision.person, concern_detail: decision.flagged?.detail || "",
      });
      setVerdict(v);
      speak(v?.spoken);
    } catch { /* ignore */ } finally { setCheckBusy(false); }
  }, [decision]);

  const toggleRecord = useCallback(async () => {
    if (recording) { try { mrRef.current?.stop(); } catch { /* noop */ } return; }
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); } catch { return; }
    const mr = new MediaRecorder(stream);
    mrRef.current = mr;
    const chunks = [];
    mr.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    mr.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      setRecording(false);
      respond({ audioBase64: await blobToBase64(new Blob(chunks, { type: mr.mimeType || "audio/webm" })) });
    };
    mr.start();
    setRecording(true);
    setTimeout(() => { try { mr.state !== "inactive" && mr.stop(); } catch { /* noop */ } }, 6000);
  }, [recording, respond]);

  const goTo = useCallback((s) => {
    setStep(s);
    setTriggered(false);
    setDecision(null);
    setVerdict(null);
    if (s === 0) { setMissed(null); setHazard(null); }
  }, []);

  const layerState = useMemo(() => {
    const m = {};
    (decision?.layers?.layers || []).forEach((l) => { m[l.key] = l; });
    return m;
  }, [decision]);

  return (
    <div className="pp-app min-h-full" data-ptheme={theme}>
      <div className="mx-auto flex min-h-full max-w-4xl flex-col gap-5 p-4 sm:p-6">
        {/* Header */}
        <header className="flex items-center gap-3">
          <span className="grid h-11 w-11 place-items-center rounded-2xl bg-gradient-to-br from-rose-500 to-red-600 text-2xl shadow-lg">🛡️</span>
          <div className="leading-tight">
            <h1 className="text-lg font-bold text-slate-100">The Guardian</h1>
            <p className="text-sm text-slate-400">
              Watching over {subject.emoji} {subject.name} · {VULN_LABEL[subject.vuln]} {subject.factor} · home alone
            </p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <span className={["hidden items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium sm:flex", connected ? "bg-emerald-500/15 text-emerald-300" : "bg-red-500/15 text-red-300"].join(" ")}>
              <span className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-400" : "bg-red-400"}`} />
              {connected ? "live" : "offline"}
            </span>
            <button
              onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
              title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
              className="grid h-9 w-9 place-items-center rounded-lg border border-slate-700 bg-slate-800 text-base text-slate-300 transition hover:border-slate-500"
            >
              {theme === "dark" ? "☀️" : "🌙"}
            </button>
          </div>
        </header>

        {/* Time-of-day control — routines and hazards depend on it (an open
            window is fine at noon but unsafe at night). Always adjustable. */}
        {step >= 1 && <ClockBar clock={clock} onClock={setClock} subject={subject} />}

        {/* Stepper — the three layers, always visible */}
        <div className="flex items-stretch gap-2">
          {LAYERS.map((l, i) => {
            const ls = layerState[l.key];
            const isCurrent = step === l.id;
            const engaged = ls?.active;
            const a = ACCENT[l.accent];
            return (
              <div key={l.key} className="flex flex-1 items-center gap-2">
                <div className={["flex-1 rounded-xl border px-3 py-2.5 transition-all", isCurrent ? `${a.ring} ${a.bg}` : engaged ? "border-slate-600 bg-slate-800/40" : "border-slate-700/60 bg-slate-900/40"].join(" ")}>
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{l.icon}</span>
                    <div className="min-w-0">
                      <p className="text-xs font-bold text-slate-100">{l.name}</p>
                      <p className="truncate text-[10px] text-slate-500">
                        {engaged ? <span className={SEV_FILL[ls.severity] || "text-slate-400"}>● active</span>
                          : isCurrent ? <span className={a.text}>▶ now</span> : "watching"}
                      </p>
                    </div>
                    <span className="ml-auto text-[10px] font-bold text-slate-600">{l.id}</span>
                  </div>
                </div>
                {i < LAYERS.length - 1 && <span className="text-slate-600">›</span>}
              </div>
            );
          })}
        </div>

        {/* Stage — the single focus */}
        <main className="rounded-3xl border border-slate-700/60 bg-slate-900/50 p-6 sm:p-8">
          {step === 0 && <Intro person={person} onPerson={setPerson} onBegin={() => goTo(1)} />}

          {layer && (
            <div className="flex flex-col gap-5">
              {/* Scene header */}
              <div className="flex items-start gap-4">
                <span className={["grid h-14 w-14 shrink-0 place-items-center rounded-2xl text-3xl", ACCENT[layer.accent].bg].join(" ")}>{layer.icon}</span>
                <div>
                  <p className={["text-xs font-bold uppercase tracking-wider", ACCENT[layer.accent].text].join(" ")}>
                    Layer {layer.id} · {layer.name} — {layer.tagline}
                  </p>
                  <p className="mt-1 text-lg font-semibold leading-snug text-slate-100">
                    {step === 1 && <>Here's {subject.name}'s usual morning. Tap the routine they <span className="text-sky-300">missed</span> today.</>}
                    {step === 2 && <>A hazard raises the stakes. Introduce something <span className="text-amber-300">unsafe</span> in the home.</>}
                    {step === 3 && <>The last line of defence — a direct <span className="text-rose-300">distress signal</span>.</>}
                  </p>
                </div>
              </div>

              {/* Interactive control per layer */}
              {step === 1 && <RoutinePicker subject={subject} missed={missed} onMiss={missRoutine} busy={busy} />}
              {step === 2 && <HazardPicker hazard={hazard} clock={clock} onPick={pickHazard} busy={busy} />}
              {step === 3 && <SosButton subject={subject} onFire={fireSos} busy={busy} fired={triggered} />}

              {/* The Guardian's response */}
              {triggered && (
                <GuardianResponse
                  decision={decision} verdict={verdict} checkBusy={checkBusy}
                  recording={recording} onRespond={respond} onRecord={toggleRecord}
                />
              )}

              {/* Explainer for the audience */}
              <div className="rounded-xl border border-slate-700/50 bg-slate-950/30 px-4 py-3">
                <p className="text-xs font-bold uppercase tracking-wider text-slate-500">What this layer shows</p>
                <p className="mt-1 text-sm leading-relaxed text-slate-300">{layer.demonstrates}</p>
              </div>
            </div>
          )}

          {step === 4 && <Complete onReplay={() => goTo(1)} />}
        </main>

        {/* Guided navigation */}
        {step >= 1 && (
          <nav className="flex items-center gap-3">
            <button onClick={() => goTo(0)} className="pp-btn rounded-lg px-3 py-2 text-sm font-semibold">↺ Restart</button>
            {step >= 1 && step <= 3 && (
              <button
                onClick={() => goTo(step + 1)}
                disabled={!triggered}
                className="ml-auto rounded-lg bg-[var(--pp-accent)] px-5 py-2 text-sm font-bold text-[#131a22] shadow transition hover:brightness-105 disabled:opacity-40"
              >
                {step < 3 ? `Next — Layer ${step + 1} ›` : "Finish ›"}
              </button>
            )}
          </nav>
        )}
      </div>
    </div>
  );
}

/* ───────────────────────────────────────────────────── Interactive controls */

function RoutinePicker({ subject, missed, onMiss, busy }) {
  // Only Ramesh/Saroja have a learned medicine routine; add it for them.
  const items = subject.medicine
    ? [...ROUTINE, { icon: "💊", label: `${subject.name}'s medicine`, time: "09:00", miss: subject.medicine }]
    : ROUTINE;
  return (
    <div className="flex flex-col gap-1.5">
      {items.map((r) => {
        const isMissed = r.miss && missed === r.miss;
        const clickable = !!r.miss;
        return (
          <button
            key={r.label}
            onClick={() => clickable && onMiss(r.miss)}
            disabled={busy || !clickable}
            className={[
              "flex items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition",
              isMissed
                ? "border-amber-500/60 bg-amber-500/10"
                : clickable
                  ? "border-slate-700/60 bg-slate-800/40 hover:border-sky-500/50 hover:bg-slate-800/70"
                  : "border-slate-800 bg-slate-900/30 opacity-70",
            ].join(" ")}
          >
            <span className="w-12 shrink-0 font-mono text-xs text-slate-500">{r.time}</span>
            <span className="text-lg">{r.icon}</span>
            <span className={["flex-1 text-sm font-medium", isMissed ? "text-amber-200 line-through" : "text-slate-200"].join(" ")}>
              {r.label}
            </span>
            {isMissed ? (
              <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold uppercase text-amber-200">missed</span>
            ) : clickable ? (
              <span className="text-[10px] text-slate-500">tap to skip →</span>
            ) : (
              <span className="text-[10px] text-emerald-400">✓ done</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

function HazardPicker({ hazard, clock, onPick, busy }) {
  const hour = Number((clock || "11:00").split(":")[0]);
  const isNight = hour >= 22 || hour < 6;
  return (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {Object.entries(HAZARDS).map(([key, h]) => {
          const on = hazard === key;
          return (
            <button
              key={key}
              onClick={() => onPick(key)}
              disabled={busy}
              className={[
                "relative flex flex-col items-center gap-1 rounded-xl border px-3 py-4 text-center transition",
                on ? "border-amber-500/70 bg-amber-500/15" : "border-slate-700/60 bg-slate-800/40 hover:border-amber-500/50 hover:bg-slate-800/70",
              ].join(" ")}
            >
              {h.night && (
                <span className={["absolute right-1.5 top-1.5 text-xs", isNight ? "" : "opacity-40"].join(" ")} title="More dangerous at night">🌙</span>
              )}
              <span className="text-3xl">{h.icon}</span>
              <span className={["text-sm font-semibold", on ? "text-amber-200" : "text-slate-200"].join(" ")}>{h.label}</span>
              <span className="text-[10px] text-slate-500">{h.note}</span>
            </button>
          );
        })}
      </div>
      <p className="text-xs text-slate-500">
        🌙 An open door or window is a <span className="text-amber-300">security emergency at night</span> —
        set the clock above to night and watch the response harden.
      </p>
    </div>
  );
}

function SosButton({ subject, onFire, busy, fired }) {
  return (
    <div className="flex flex-col items-center gap-2 py-2">
      <button
        onClick={onFire}
        disabled={busy}
        className={[
          "grid h-28 w-28 place-items-center rounded-full border-4 text-center font-black uppercase tracking-wide text-white shadow-xl transition disabled:opacity-60",
          fired ? "border-red-300 bg-red-600 animate-pulse" : "border-red-400/70 bg-red-500 hover:bg-red-600 hover:scale-105",
        ].join(" ")}
      >
        <span className="text-lg leading-tight">🆘<br />SOS</span>
      </button>
      <p className="text-xs text-slate-500">{fired ? "Signal fired from the wearable" : `${subject.name}'s wearable detects a fall — tap to fire`}</p>
    </div>
  );
}

// Time-of-day slider — the clock drives which routines/hazards flag.
function ClockBar({ clock, onClock, subject }) {
  const mins = (() => { const [h, m] = clock.split(":").map(Number); return h * 60 + m; })();
  const hour = Number(clock.split(":")[0]);
  const isNight = hour >= 22 || hour < 6;
  const setMins = (v) => onClock(`${String(Math.floor(v / 60)).padStart(2, "0")}:${String(v % 60).padStart(2, "0")}`);
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-700/60 bg-slate-900/40 px-4 py-2.5">
      <span className="flex items-center gap-1.5 text-sm font-semibold text-slate-300">
        {isNight ? "🌙" : "☀️"} <span className="font-mono">{clock}</span>
        <span className="text-xs font-normal text-slate-500">{isNight ? "night" : "day"}</span>
      </span>
      <input
        type="range" min="0" max="1439" step="15" value={mins}
        onChange={(e) => setMins(Number(e.target.value))}
        className="h-1.5 flex-1 cursor-pointer appearance-none rounded-full bg-slate-700 accent-rose-500"
        title="Drag to change the time of day"
      />
      <span className="ml-auto flex items-center gap-1.5 text-xs text-slate-500">
        <span>{subject.emoji}</span> {subject.name} home alone
      </span>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────── Intro / Complete */

function Intro({ person, onPerson, onBegin }) {
  const subject = ROSTER_BY_ID[person] || ROSTER_BY_ID.grandpa;
  return (
    <div className="flex flex-col items-center gap-5 py-4 text-center">
      <span className="text-6xl">{subject.emoji}</span>
      <div>
        <h2 className="text-2xl font-bold text-slate-100">Who is home alone?</h2>
        <p className="mx-auto mt-2 max-w-xl text-sm leading-relaxed text-slate-400">
          Pick the person the home is watching over. How vulnerable they are decides how hard the Guardian
          reacts — the <span className="font-semibold text-slate-200">same event</span> escalates differently for each.
        </p>
      </div>

      {/* Who's-home picker */}
      <div className="grid w-full max-w-2xl grid-cols-2 gap-2 sm:grid-cols-3">
        {ROSTER.map((p) => {
          const on = p.id === person;
          return (
            <button
              key={p.id}
              onClick={() => onPerson(p.id)}
              className={[
                "flex items-center gap-2 rounded-xl border px-3 py-2.5 text-left transition",
                on ? "border-rose-500/70 bg-rose-500/10" : "border-slate-700/60 bg-slate-800/40 hover:border-slate-500",
              ].join(" ")}
            >
              <span className="text-2xl">{p.emoji}</span>
              <div className="min-w-0 leading-tight">
                <p className="text-sm font-bold text-slate-100">{p.name}</p>
                <p className="text-[11px] text-slate-500">{VULN_LABEL[p.vuln]} · {p.factor}</p>
              </div>
            </button>
          );
        })}
      </div>

      <p className="text-xs text-slate-500">
        {subject.vuln === "normal"
          ? "A capable adult — the Guardian keeps a light watch."
          : `${subject.name} is vulnerable and alone — every concern is escalated ${subject.factor}.`}
      </p>

      <button onClick={onBegin} className="rounded-xl bg-[var(--pp-accent)] px-6 py-3 text-sm font-bold text-[#131a22] shadow-lg transition hover:brightness-105">
        ▶ Begin — Layer 1
      </button>
    </div>
  );
}

function Complete({ onReplay }) {
  return (
    <div className="flex flex-col items-center gap-4 py-8 text-center">
      <span className="text-5xl">🛡️</span>
      <h2 className="text-2xl font-bold text-slate-100">Three layers, one guardian.</h2>
      <p className="mx-auto max-w-xl text-base leading-relaxed text-slate-400">
        A gentle nudge for a missed routine, a sharper response when a hazard corroborates it, and an instant alarm
        when a vital signal fires. Independent layers that cross-check each other — so a single false signal never
        cries wolf, and a real emergency is never missed.
      </p>
      <button onClick={onReplay} className="pp-btn rounded-lg px-5 py-2 text-sm font-semibold">↺ Play again</button>
    </div>
  );
}

// The genuine "why I think this" LLM reasoning, shown the same way the pattern
// engine surfaces its narration explanation. Visible by default for the demo.
function WhyBlock({ text, tone = "slate" }) {
  const [open, setOpen] = useState(true);
  if (!text) return null;
  const accent = tone === "alert" ? "text-red-300" : tone === "warn" ? "text-amber-300" : "text-sky-300";
  return (
    <div className="mt-2">
      <button onClick={() => setOpen((v) => !v)} className={["inline-flex items-center gap-1 text-xs font-semibold transition", accent].join(" ")}>
        🧠 Why I think this <span className={open ? "rotate-180 transition-transform" : "transition-transform"}>▾</span>
      </button>
      {open && (
        <div className="mt-1.5 rounded-lg border border-slate-700/60 bg-slate-950/50 p-3">
          <p className="text-sm leading-relaxed text-slate-300">{text}</p>
        </div>
      )}
    </div>
  );
}

// Shows whether the spoken line was phrased by the Groq LLM narrator or the
// deterministic fallback (so it's clear the responses are LLM-generated).
function LlmBadge({ on }) {
  return on ? (
    <span className="rounded-full bg-fuchsia-500/15 px-2 py-0.5 text-xs font-semibold text-fuchsia-300" title="Phrased live by the Groq LLM narrator">
      🧠 spoken by Alexa
    </span>
  ) : (
    <span className="rounded-full bg-slate-700/50 px-2 py-0.5 text-xs font-medium text-slate-400" title="LLM unavailable — deterministic fallback. Set GROQ_API_KEY on the safety service.">
      template
    </span>
  );
}

/* ─────────────────────────────────────────────────────── Guardian response card */

function GuardianResponse({ decision, verdict, checkBusy, recording, onRespond, onRecord }) {
  if (!decision) return null;
  const fl = decision.flagged;

  if (decision.mode === "auto_alarm") {
    return (
      <div className="rounded-2xl border border-red-500/60 bg-red-500/10 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-md bg-red-500/25 px-2 py-0.5 text-xs font-black uppercase tracking-wide text-red-200 animate-pulse">🚨 Alarm raised</span>
          {decision.layers?.corroborated_emergency && (
            <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-xs font-semibold text-amber-200">⚡ layers agree</span>
          )}
          <LlmBadge on={decision.llm_powered} />
        </div>
        {fl && <p className="mt-2 text-base font-semibold text-slate-100">{fl.detail}</p>}
        <p className="mt-2 rounded-lg bg-slate-950/40 px-3 py-2 text-base text-red-100">🔊 {decision.spoken}</p>
        <WhyBlock text={decision.explanation} tone="alert" />
        {decision.family_message && (
          <div className="mt-2 rounded-lg border border-red-500/30 bg-slate-950/40 px-3 py-2">
            <p className="text-xs font-bold uppercase tracking-wide text-red-300">👪 Family notified — now</p>
            <p className="text-sm text-slate-200">{decision.family_message}</p>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-amber-500/50 bg-amber-500/10 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-md bg-amber-500/20 px-2 py-0.5 text-xs font-bold uppercase text-amber-200">❔ Checking in first</span>
        <LlmBadge on={decision.llm_powered} />
      </div>
      <p className="mt-2 rounded-lg bg-slate-950/40 px-3 py-2 text-base text-amber-100">🔊 {decision.checkin_prompt || decision.spoken}</p>
      <WhyBlock text={decision.explanation} tone="warn" />

      {!verdict ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-sm text-slate-400">{decision.person} replies:</span>
          <button onClick={() => onRespond({ text: "I'm fine, just resting" })} disabled={checkBusy}
            className="rounded-lg border border-emerald-500/50 bg-emerald-500/10 px-3 py-2 text-sm font-semibold text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-50">
            🟢 I'm fine
          </button>
          <button onClick={() => onRespond({ text: "Help, I've fallen and I can't get up" })} disabled={checkBusy}
            className="rounded-lg border border-red-500/50 bg-red-500/10 px-3 py-2 text-sm font-semibold text-red-200 hover:bg-red-500/20 disabled:opacity-50">
            🔴 I need help
          </button>
          <button onClick={onRecord} disabled={checkBusy}
            className={["rounded-lg border px-3 py-2 text-sm font-semibold transition disabled:opacity-50",
              recording ? "border-red-400/70 bg-red-500/20 text-red-200 animate-pulse" : "border-slate-600/60 bg-slate-800/60 text-slate-300 hover:bg-slate-700"].join(" ")}>
            {recording ? "■ listening" : "🎙️ speak"}
          </button>
          <button onClick={() => onRespond({ text: "" })} disabled={checkBusy}
            className="rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-400 hover:text-slate-200 disabled:opacity-50">
            ⏱ no response
          </button>
          {checkBusy && <span className="text-sm text-slate-500">…</span>}
        </div>
      ) : (
        <div className={["mt-3 rounded-xl border px-4 py-3", verdict.verdict === "stand_down" ? "border-emerald-500/40 bg-emerald-500/5" : "border-red-500/50 bg-red-500/10"].join(" ")}>
          <p className={["text-xs font-bold uppercase tracking-wide", verdict.verdict === "stand_down" ? "text-emerald-300" : "text-red-300"].join(" ")}>
            {verdict.verdict === "stand_down" ? "✓ Flag cleared — stood down" : "🚨 Escalated to family"}
          </p>
          {verdict.transcript && <p className="mt-0.5 text-xs italic text-slate-500">heard: “{verdict.transcript}”</p>}
          <p className="mt-1 text-base text-slate-100">🔊 {verdict.spoken}</p>
          <WhyBlock text={verdict.explanation} tone={verdict.verdict === "stand_down" ? "slate" : "alert"} />
          {verdict.notify_family && verdict.family_message && (
            <p className="mt-1 text-sm text-red-200">👪 {verdict.family_message}</p>
          )}
        </div>
      )}
    </div>
  );
}
