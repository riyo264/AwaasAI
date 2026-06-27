import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { safetyApi } from "../safetyApi.js";
import AlexaNotification from "../components/patterns/AlexaNotification.jsx";

// ════════════════════════════════════════════════════════════════════════════
//  ADAPTIVE SAFETY — "Living Dollhouse"
//  ---------------------------------------------------------------------------
//  A top-view home you operate directly:
//    • Place PEOPLE into the home (each carries a vulnerability ×factor).
//    • Click DEVICES / windows / doors to turn them on/open.
//    • Drag the CLOCK forward to let a running device overrun, or reach night.
//    • Fire momentary SIGNALS (SOS / health / quiet house).
//  Every change is sent to /context/E001/evaluate — a fully EPHEMERAL call:
//  nothing is persisted, so you can poke the home endlessly without ever
//  corrupting the seeded history. The engine returns a vulnerability-aware
//  assessment; the SAME concern changes severity purely by who is in the room.
// ════════════════════════════════════════════════════════════════════════════

const HID = "E001";

// ── Floor plan: rooms on a 3×3 grid. ───────────────────────────────────────
const ROOMS = {
  bedroom: { name: "Bedroom", col: "1 / 2", row: "1 / 2" },
  pooja_room: { name: "Pooja Room", col: "2 / 3", row: "1 / 2" },
  balcony: { name: "Balcony", col: "3 / 4", row: "1 / 2" },
  living_room: { name: "Living Room", col: "1 / 3", row: "2 / 3" },
  kitchen: { name: "Kitchen", col: "3 / 4", row: "2 / 3" },
  entrance: { name: "Entrance", col: "1 / 2", row: "3 / 4" },
  utility: { name: "Utility", col: "2 / 4", row: "3 / 4" },
};

// Devices that map to E001's seeded history. `interactive` devices can be
// toggled on/open from the map (they paint the live `active_devices` set);
// the rest are read-only context chips. Doors/windows (id suffix `_door` /
// `_window`) drive the night-safety check; gas/motor/lamp drive duration.
const DEVICE_META = {
  // Interactive (clickable) — these produce concerns when on/open.
  bedroom_window: { room: "bedroom", icon: "🪟", label: "Bedroom window", interactive: true, verb: "Open" },
  main_door: { room: "entrance", icon: "🚪", label: "Main door", interactive: true, verb: "Open" },
  kitchen_gas_stove: { room: "kitchen", icon: "🔥", label: "Gas stove", interactive: true, verb: "Turn on" },
  water_motor: { room: "utility", icon: "🛢️", label: "Water motor", interactive: true, verb: "Turn on" },
  living_room_light: { room: "living_room", icon: "💡", label: "Living light", interactive: true, verb: "Turn on" },
  pooja_lamp: { room: "pooja_room", icon: "🪔", label: "Pooja lamp", interactive: true, verb: "Turn on" },
  temple_bell: { room: "pooja_room", icon: "🔔", label: "Temple bell", interactive: true, verb: "Turn on" },
  bhajan_speaker: { room: "pooja_room", icon: "🔊", label: "Bhajan", interactive: true, verb: "Turn on" },
  // Read-only context (sensors / care pings).
  grandpa_activity: { room: "bedroom", icon: "🚶", label: "Grandpa activity" },
  grandma_activity: { room: "bedroom", icon: "🚶", label: "Grandma activity" },
  grandpa_medicine: { room: "bedroom", icon: "💊", label: "Grandpa medicine" },
  grandma_medicine: { room: "bedroom", icon: "💊", label: "Grandma medicine" },
  grandpa_wearable: { room: "living_room", icon: "⌚", label: "Wearable" },
  kitchen_activity: { room: "kitchen", icon: "🍳", label: "Kitchen activity" },
  living_activity: { room: "living_room", icon: "🛋️", label: "Living activity" },
};

// The cast you can place in the home. Vulnerability drives the ×factor the
// engine multiplies every concern by. An ADULT (normal) present mitigates risk.
const ROSTER = [
  { person_id: "grandpa", display_name: "Ramesh", role: "Grandpa", vulnerability: "elderly", emoji: "👴", wearable_id: "grandpa_wearable", relation: "father", emergency_contacts: ["son_bangalore", "daughter_pune"] },
  { person_id: "grandma", display_name: "Saroja", role: "Grandma", vulnerability: "elderly", emoji: "👵", relation: "mother", emergency_contacts: ["son_bangalore", "daughter_pune"] },
  { person_id: "arjun", display_name: "Arjun", role: "Adult son", vulnerability: "normal", emoji: "🧑", relation: "son", emergency_contacts: ["daughter_pune"] },
  { person_id: "aarav", display_name: "Aarav", role: "Child", vulnerability: "child", emoji: "🧒", relation: "grandchild", emergency_contacts: ["son_bangalore"] },
  { person_id: "meera", display_name: "Meera", role: "Expecting", vulnerability: "pregnant", emoji: "🤰", relation: "daughter-in-law", emergency_contacts: ["son_bangalore"] },
  { person_id: "ravi", display_name: "Ravi", role: "Recovering", vulnerability: "unwell", emoji: "🤒", relation: "son", emergency_contacts: ["daughter_pune"] },
];
const ROSTER_BY_ID = Object.fromEntries(ROSTER.map((p) => [p.person_id, p]));

const STATUS_META = {
  safe: { label: "Safe", color: "#22c55e", bg: "bg-emerald-500/15", ring: "ring-emerald-500/50", text: "text-emerald-300", emoji: "🟢" },
  inactive: { label: "Inactive", color: "#eab308", bg: "bg-yellow-500/15", ring: "ring-yellow-500/50", text: "text-yellow-300", emoji: "🟡" },
  needs_attention: { label: "Needs Attention", color: "#f97316", bg: "bg-orange-500/15", ring: "ring-orange-500/50", text: "text-orange-300", emoji: "🟠" },
  emergency: { label: "Emergency", color: "#ef4444", bg: "bg-red-500/15", ring: "ring-red-500/60", text: "text-red-300", emoji: "🔴" },
};

const SEVERITY_COLOR = {
  low: { dot: "bg-emerald-400", text: "text-emerald-300", ring: "border-emerald-500/40" },
  medium: { dot: "bg-yellow-400", text: "text-yellow-300", ring: "border-yellow-500/40" },
  high: { dot: "bg-orange-400", text: "text-orange-300", ring: "border-orange-500/40" },
  critical: { dot: "bg-red-500", text: "text-red-300", ring: "border-red-500/50" },
};
const SEV_RANK = { critical: 0, high: 1, medium: 2, low: 3 };

const VULN_META = {
  elderly: { label: "Elderly", emoji: "👴", cls: "bg-rose-500/15 text-rose-300 ring-rose-500/40", factor: "×2.0" },
  child: { label: "Child", emoji: "🧒", cls: "bg-amber-500/15 text-amber-300 ring-amber-500/40", factor: "×1.7" },
  pregnant: { label: "Expecting", emoji: "🤰", cls: "bg-pink-500/15 text-pink-300 ring-pink-500/40", factor: "×1.8" },
  unwell: { label: "Unwell", emoji: "🤒", cls: "bg-orange-500/15 text-orange-300 ring-orange-500/40", factor: "×1.8" },
  normal: { label: "Adult", emoji: "🧑", cls: "bg-slate-600/30 text-slate-300 ring-slate-500/40", factor: "×1.0" },
};

// One-click situations that POPULATE the live board (everything stays editable
// afterwards — add/remove people, move the clock, toggle more devices).
const QUICK = [
  { key: "window_night", label: "Window open · night", emoji: "🌙" },
  { key: "gas_left_on", label: "Gas left on", emoji: "🔥" },
  { key: "sos", label: "SOS pressed", emoji: "🆘" },
  { key: "quiet", label: "No movement (5h)", emoji: "🟡" },
];

function nowHHMM() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

// Build an ISO timestamp on today's UTC date at the given HH:MM (+offset min),
// matching the backend's demo-clock resolution so durations line up exactly.
function isoAtClock(hhmm, offsetMin = 0) {
  const [h, m] = (hhmm || nowHHMM()).split(":").map(Number);
  const d = new Date();
  d.setUTCHours(h, m + offsetMin, 0, 0);
  return d.toISOString();
}

export default function Safety() {
  const [clock, setClock] = useState(nowHHMM());
  const [activeDevices, setActiveDevices] = useState(() => new Set());
  const [deviceOnSince, setDeviceOnSince] = useState({}); // id -> ISO
  const [placed, setPlaced] = useState(() => new Set(["grandpa", "grandma"]));
  const [signals, setSignals] = useState(() => new Set()); // sos | health | quiet

  const [data, setData] = useState(null); // last evaluate ContextObject
  const [patternsCount, setPatternsCount] = useState(0);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [connected, setConnected] = useState(true);
  const [alexaQueue, setAlexaQueue] = useState([]);
  const [toast, setToast] = useState(null);
  const lastNarr = useRef("");

  const flash = useCallback((msg, ok = true) => {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 2600);
  }, []);

  // ── Device painting ────────────────────────────────────────────────────
  const turnDeviceOn = useCallback((id, onSinceIso) => {
    setActiveDevices((prev) => new Set(prev).add(id));
    setDeviceOnSince((prev) => ({ ...prev, [id]: onSinceIso }));
  }, []);
  const turnDeviceOff = useCallback((id) => {
    setActiveDevices((prev) => {
      const n = new Set(prev);
      n.delete(id);
      return n;
    });
    setDeviceOnSince((prev) => {
      const n = { ...prev };
      delete n[id];
      return n;
    });
  }, []);
  const toggleDevice = useCallback(
    (id) => {
      if (!DEVICE_META[id]?.interactive) return;
      if (activeDevices.has(id)) turnDeviceOff(id);
      else turnDeviceOn(id, isoAtClock(clock));
    },
    [activeDevices, clock, turnDeviceOn, turnDeviceOff],
  );

  // ── People placement ─────────────────────────────────────────────────────
  const togglePerson = useCallback((id) => {
    setPlaced((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }, []);

  const toggleSignal = useCallback((key) => {
    setSignals((prev) => {
      const n = new Set(prev);
      if (n.has(key)) n.delete(key);
      else n.add(key);
      return n;
    });
  }, []);

  // ── Quick situations (populate the live board) ───────────────────────────
  const runQuick = useCallback(
    (key) => {
      if (key === "window_night") {
        setClock("23:00");
        turnDeviceOn("bedroom_window", isoAtClock("23:00"));
      } else if (key === "gas_left_on") {
        // Already overrunning: turned on ~60 min before the current clock.
        turnDeviceOn("kitchen_gas_stove", isoAtClock(clock, -60));
      } else if (key === "sos") {
        toggleSignal("sos");
      } else if (key === "quiet") {
        toggleSignal("quiet");
      }
    },
    [clock, turnDeviceOn, toggleSignal],
  );

  const resetBoard = useCallback(() => {
    setActiveDevices(new Set());
    setDeviceOnSince({});
    setSignals(new Set());
    setClock(nowHHMM());
    setPlaced(new Set(["grandpa", "grandma"]));
    flash("Board reset to a calm home");
  }, [flash]);

  // ── Build the ephemeral evaluate request from the live board ─────────────
  const buildRequest = useCallback(() => {
    const profiles = [...placed].map((id) => {
      const p = ROSTER_BY_ID[id];
      return {
        person_id: p.person_id,
        display_name: `${p.display_name} (${p.role})`,
        vulnerability: p.vulnerability,
        emergency_contacts: p.emergency_contacts || [],
        wearable_id: p.wearable_id || null,
        relation: p.relation || null,
      };
    });
    const people_home = {};
    placed.forEach((id) => {
      people_home[id] = true;
    });

    const sigArr = [];
    let ignore = false;
    if (signals.has("sos")) {
      sigArr.push({ device_id: "grandpa_wearable", device_type: "wearable", room: "living_room", action: "SOS", triggered_by: "grandpa", minutes_ago: 2 });
    }
    if (signals.has("health")) {
      sigArr.push({ device_id: "grandpa_wearable", device_type: "wearable", room: "bedroom", action: "ALERT", triggered_by: "grandpa", minutes_ago: 6, metadata: { signal: "heart_rate", value: 44, threshold: "<50 bpm" } });
    }
    if (signals.has("quiet")) {
      // Ignore stored events so seeded routine pings don't count as life; the
      // only sign of life is a single "last seen" ping 5h ago → high inactivity.
      ignore = true;
      sigArr.push({ device_id: "grandpa_activity", device_type: "activity", room: "bedroom", action: "ACTIVE", triggered_by: "grandpa", minutes_ago: 300 });
    } else {
      // Keep the home "alive": a fresh activity ping ~5 min before the demo
      // clock. Without this, scrubbing the clock forward (e.g. to 23:00 for the
      // window-at-night demo) would make the seeded last-activity look hours old
      // and trigger a phantom global-inactivity emergency. Inactivity should be
      // a deliberate scenario (the "No movement" toggle), never a clock artifact.
      sigArr.push({ device_id: "grandpa_activity", device_type: "activity", room: "bedroom", action: "ACTIVE", triggered_by: "grandpa", minutes_ago: 5 });
    }

    return {
      current_time: clock || undefined,
      active_devices: [...activeDevices],
      device_on_since: deviceOnSince,
      people_home,
      profiles,
      signals: sigArr,
      ignore_stored_events: ignore,
    };
  }, [placed, signals, clock, activeDevices, deviceOnSince]);

  const speak = useCallback(async (ctx) => {
    if (!ctx) return;
    try {
      const { narrations } = await safetyApi.narrateEach(ctx);
      const items = (narrations || [])
        .filter((n) => n && n.alexa_response)
        .map((n, i) => ({
          id: `${i}-${n.device || "all"}-${n.anomaly_type || ""}`,
          text: n.alexa_response,
          explanation: n.explanation,
          llmPowered: n.llm_powered,
          tone:
            n.severity === "high" || n.severity === "critical" || n.severity === "medium"
              ? "alert"
              : "calm",
        }));
      setAlexaQueue(items);
    } catch {
      /* narration is optional */
    }
  }, []);

  // ── The live evaluation: runs (debounced) on every board change ──────────
  const boardKey = useMemo(
    () =>
      JSON.stringify({
        c: clock,
        a: [...activeDevices].sort(),
        o: deviceOnSince,
        p: [...placed].sort(),
        s: [...signals].sort(),
      }),
    [clock, activeDevices, deviceOnSince, placed, signals],
  );

  const evaluate = useCallback(async () => {
    setBusy(true);
    try {
      const ctx = await safetyApi.evaluate(HID, buildRequest());
      setData(ctx);
      setConnected(true);
    } catch (e) {
      setConnected(false);
      flash(`Cannot reach Safety API on :8006 — is it running? (${e.message})`, false);
    } finally {
      setBusy(false);
    }
  }, [buildRequest, flash]);

  // First load: make sure the home has learned its routines (seed once if not),
  // then enable the live loop.
  useEffect(() => {
    (async () => {
      try {
        const s = await safetyApi.getSafety(HID);
        let count = s?.patterns_count ?? 0;
        if (!count) {
          const r = await safetyApi.seed(HID, "normal");
          count = r?.patterns_extracted ?? 0;
        }
        setPatternsCount(count);
        setConnected(true);
      } catch (e) {
        setConnected(false);
        flash(`Cannot reach Safety API on :8006 — is it running? (${e.message})`, false);
      } finally {
        setReady(true);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Re-evaluate whenever the board changes (debounced so rapid clicks coalesce).
  useEffect(() => {
    if (!ready) return undefined;
    const t = setTimeout(() => evaluate(), 180);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boardKey, ready]);

  // Narrate only when the set of concerns actually changes (no LLM spam).
  useEffect(() => {
    const anoms = data?.anomalies || [];
    if (!anoms.length) {
      setAlexaQueue([]);
      lastNarr.current = "";
      return;
    }
    const sig = anoms
      .map((a) => `${a.type}:${a.device}:${a.severity}`)
      .sort()
      .join("|");
    if (sig === lastNarr.current) return;
    lastNarr.current = sig;
    speak(data);
  }, [data, speak]);

  // ── Derived view data ────────────────────────────────────────────────────
  const safety = data?.safety;
  const anomalies = useMemo(() => data?.anomalies || [], [data]);
  const status = STATUS_META[safety?.status] || STATUS_META.safe;

  const roomRisk = useMemo(() => {
    const m = {};
    anomalies.forEach((a) => {
      const room = DEVICE_META[a.device]?.room;
      if (!room) return;
      if (!m[room] || SEV_RANK[a.severity] < SEV_RANK[m[room]]) m[room] = a.severity;
    });
    return m;
  }, [anomalies]);

  const sortedAnoms = useMemo(
    () => [...anomalies].sort((a, b) => SEV_RANK[a.severity] - SEV_RANK[b.severity]),
    [anomalies],
  );
  const escalatedCount = useMemo(
    () => anomalies.filter((a) => a.base_severity && a.base_severity !== a.severity).length,
    [anomalies],
  );

  return (
    <div className="mx-auto flex min-h-full max-w-[1400px] flex-col gap-4">
      {/* Header */}
      <header className="flex flex-col gap-3 rounded-2xl border border-slate-700/60 bg-slate-900/60 px-4 py-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-rose-500 to-red-600 text-lg shadow-lg">
              🛡️
            </span>
            <div className="leading-tight">
              <h1 className="text-sm font-bold text-slate-100">Adaptive Safety · Living Home</h1>
              <p className="text-[10px] text-slate-400">
                Operate the home directly — the same concern changes severity by who's inside
              </p>
            </div>
          </div>

          <div className="ml-auto flex items-center gap-2">
            <span className="hidden items-center gap-1.5 text-[11px] text-slate-400 sm:flex">
              {busy ? "⏳ evaluating…" : "live"}
            </span>
            <button
              onClick={resetBoard}
              className="rounded-lg border border-emerald-600/50 bg-emerald-500/10 px-2.5 py-1.5 text-[11px] font-semibold text-emerald-300 transition hover:bg-emerald-500/20"
              title="Clear devices + signals, calm home"
            >
              🟢 Reset
            </button>
            <span
              className={[
                "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-medium",
                connected ? "bg-emerald-500/15 text-emerald-300" : "bg-red-500/15 text-red-300",
              ].join(" ")}
            >
              <span className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-400" : "bg-red-400"}`} />
              {connected ? "Safety API :8006" : "API offline"}
            </span>
          </div>
        </div>

        {/* Clock scrubber + quick situations */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Clock</span>
            <input
              type="range"
              min="0"
              max="1439"
              step="5"
              value={(() => {
                const [h, m] = clock.split(":").map(Number);
                return h * 60 + m;
              })()}
              onChange={(e) => {
                const v = Number(e.target.value);
                setClock(`${String(Math.floor(v / 60)).padStart(2, "0")}:${String(v % 60).padStart(2, "0")}`);
              }}
              className="h-1.5 w-44 cursor-pointer appearance-none rounded-full bg-slate-700 accent-rose-500"
              title="Drag to move the demo clock"
            />
            <input
              type="time"
              value={clock}
              onChange={(e) => setClock(e.target.value || nowHHMM())}
              className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-100 outline-none focus:border-rose-500"
            />
            <button
              onClick={() => setClock(nowHHMM())}
              className="rounded-lg border border-slate-700 px-2 py-1.5 text-[10px] text-slate-400 hover:text-slate-200"
            >
              now
            </button>
            <button
              onClick={() => {
                const [h, m] = clock.split(":").map(Number);
                const v = (h * 60 + m + 60) % 1440;
                setClock(`${String(Math.floor(v / 60)).padStart(2, "0")}:${String(v % 60).padStart(2, "0")}`);
              }}
              className="rounded-lg border border-slate-700 px-2 py-1.5 text-[10px] text-slate-400 hover:text-slate-200"
              title="Jump one hour ahead"
            >
              +1h
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Quick</span>
            {QUICK.map((q) => {
              const on =
                (q.key === "sos" && signals.has("sos")) ||
                (q.key === "quiet" && signals.has("quiet")) ||
                (q.key === "window_night" && activeDevices.has("bedroom_window")) ||
                (q.key === "gas_left_on" && activeDevices.has("kitchen_gas_stove"));
              return (
                <button
                  key={q.key}
                  onClick={() => runQuick(q.key)}
                  className={[
                    "rounded-lg border px-2.5 py-1.5 text-[11px] font-semibold transition",
                    on
                      ? "border-rose-400/70 bg-rose-500/20 text-rose-100"
                      : "border-slate-700 bg-slate-800/60 text-slate-300 hover:border-slate-500",
                  ].join(" ")}
                  title={`Set up: ${q.label}`}
                >
                  {q.emoji} {q.label}
                </button>
              );
            })}
          </div>
        </div>
        <p className="text-[10px] text-slate-500">
          💡 Turn a device on, then drag the clock forward to watch it overrun · open a window and reach night ·
          remove the adult to see concerns escalate.
        </p>
      </header>

      {/* Status banner */}
      <section className={["flex flex-wrap items-center gap-4 rounded-2xl border bg-slate-900/60 p-4 ring-1", status.ring].join(" ")}>
        <div className={["grid h-16 w-16 place-items-center rounded-2xl text-3xl", status.bg].join(" ")}>
          {status.emoji}
        </div>
        <div className="min-w-0">
          <p className="text-[11px] uppercase tracking-wide text-slate-400">Home status · {clock}</p>
          <p className={["text-2xl font-extrabold", status.text].join(" ")}>{status.label}</p>
          <p className="mt-0.5 max-w-2xl text-xs text-slate-400">{safety?.rationale || "All quiet."}</p>
        </div>

        <div className="ml-auto flex items-center gap-4">
          {safety?.vulnerable_alone && (
            <span className="rounded-full bg-rose-500/15 px-3 py-1.5 text-[11px] font-semibold text-rose-300 ring-1 ring-rose-500/40">
              ⚠ Vulnerable person home alone ×{safety?.vulnerability_factor}
            </span>
          )}
          <div className="text-center">
            <div
              className="grid h-20 w-20 place-items-center rounded-full"
              style={{ background: `conic-gradient(${status.color} ${(safety?.safety_score ?? 100) * 3.6}deg, #1e293b 0deg)` }}
            >
              <div className="grid h-16 w-16 place-items-center rounded-full bg-slate-950">
                <span className="text-xl font-bold text-slate-100">{Math.round(safety?.safety_score ?? 100)}</span>
              </div>
            </div>
            <p className="mt-1 text-[10px] uppercase tracking-wide text-slate-500">Safety score</p>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_380px]">
        {/* Left: floor plan */}
        <main className="flex flex-col gap-4">
          <div className="rounded-3xl border border-slate-700/50 bg-slate-950/40 p-4">
            <div className="mb-3 flex items-center justify-between">
              <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">Home Layout · click to operate</p>
              <p className="text-[10px] text-slate-500">🟦 on/open · 🟥 concern</p>
            </div>
            <div
              className="grid gap-3"
              style={{ gridTemplateColumns: "repeat(3, 1fr)", gridTemplateRows: "repeat(3, minmax(140px,1fr))" }}
            >
              {Object.entries(ROOMS).map(([key, room]) => {
                const risk = roomRisk[key];
                const sev = risk ? SEVERITY_COLOR[risk] : null;
                const devices = Object.entries(DEVICE_META).filter(([, m]) => m.room === key);
                return (
                  <div
                    key={key}
                    style={{ gridColumn: room.col, gridRow: room.row }}
                    className={[
                      "rounded-2xl border p-3 transition-all",
                      sev
                        ? `${sev.ring} bg-slate-900/80 ${risk === "critical" ? "anomaly-pulse" : ""}`
                        : "border-slate-700/60 bg-slate-900/40",
                    ].join(" ")}
                  >
                    <div className="mb-2 flex items-center justify-between">
                      <span className="text-xs font-semibold text-slate-200">{room.name}</span>
                      {risk && <span className={["text-[9px] font-bold uppercase", sev.text].join(" ")}>⚠ {risk}</span>}
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {devices.map(([id, m]) => {
                        const on = activeDevices.has(id);
                        const flagged = anomalies.some((a) => a.device === id);
                        const clickable = !!m.interactive;
                        return (
                          <button
                            key={id}
                            onClick={() => toggleDevice(id)}
                            disabled={!clickable}
                            title={
                              clickable
                                ? `${m.verb || "Toggle"} ${m.label}${on ? " (on)" : ""}`
                                : `${m.label} · sensor`
                            }
                            className={[
                              "flex items-center gap-1 rounded-lg px-1.5 py-1 text-sm transition",
                              clickable ? "cursor-pointer hover:scale-105" : "cursor-default opacity-70",
                              flagged
                                ? "bg-red-500/20 ring-1 ring-red-500/50"
                                : on
                                  ? "bg-sky-500/20 ring-1 ring-sky-400/50"
                                  : "bg-slate-800/60",
                            ].join(" ")}
                          >
                            <span>{m.icon}</span>
                            <span className="text-[9px] text-slate-300">{m.label.split(" ").slice(-1)[0]}</span>
                          </button>
                        );
                      })}
                      {devices.length === 0 && (
                        <span className="text-[10px] text-slate-600">—</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Signals strip */}
          <div className="rounded-2xl border border-slate-700/60 bg-slate-900/40 p-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Momentary Signals</p>
            <div className="flex flex-wrap gap-2">
              {[
                { key: "sos", emoji: "🆘", label: "SOS pressed" },
                { key: "health", emoji: "❤️", label: "Abnormal heart rate" },
                { key: "quiet", emoji: "🟡", label: "No movement (5h)" },
              ].map((s) => {
                const on = signals.has(s.key);
                return (
                  <button
                    key={s.key}
                    onClick={() => toggleSignal(s.key)}
                    className={[
                      "rounded-lg border px-2.5 py-1.5 text-[11px] font-semibold transition",
                      on
                        ? "border-rose-400/70 bg-rose-500/25 text-rose-100 ring-1 ring-rose-500/40"
                        : "border-slate-700 bg-slate-800/60 text-slate-300 hover:border-slate-500",
                    ].join(" ")}
                  >
                    {on ? "✓ " : ""}
                    {s.emoji} {s.label}
                  </button>
                );
              })}
            </div>
            <p className="mt-2 text-[10px] text-slate-500">
              SOS &amp; health are instant emergencies. "No movement" fires the elderly-alone safety net.
            </p>
          </div>
        </main>

        {/* Right column */}
        <aside className="flex flex-col gap-4">
          {/* Who's home — the vulnerability lens */}
          <div className="rounded-2xl border border-slate-700/60 bg-slate-900/40 p-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Who's Home · tap to place</p>
            <div className="flex flex-wrap gap-2">
              {ROSTER.map((p) => {
                const on = placed.has(p.person_id);
                const vm = VULN_META[p.vulnerability] || VULN_META.normal;
                return (
                  <button
                    key={p.person_id}
                    onClick={() => togglePerson(p.person_id)}
                    className={[
                      "flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] font-semibold transition",
                      on
                        ? "border-sky-400/60 bg-sky-500/20 text-sky-100"
                        : "border-slate-700 bg-slate-800/40 text-slate-400 hover:border-slate-500",
                    ].join(" ")}
                    title={`${p.display_name} · ${vm.label} ${vm.factor}`}
                  >
                    <span>{p.emoji}</span>
                    <span>{p.display_name}</span>
                    <span className="text-[9px] opacity-70">{vm.factor}</span>
                  </button>
                );
              })}
            </div>
            {placed.size === 0 ? (
              <p className="mt-2 rounded-lg bg-slate-800/60 px-2.5 py-1.5 text-[11px] text-slate-400">
                Nobody is home — place someone to begin.
              </p>
            ) : safety?.vulnerable_alone ? (
              <p className="mt-2 rounded-lg bg-rose-500/10 px-2.5 py-1.5 text-[11px] text-rose-300">
                ⚠ {safety?.occupant_labels?.[safety?.most_vulnerable] || "A vulnerable person"} is home alone — every
                concern is escalated ×{safety?.vulnerability_factor}.
              </p>
            ) : (
              <p className="mt-2 rounded-lg bg-emerald-500/10 px-2.5 py-1.5 text-[11px] text-emerald-300">
                ✓ A capable adult is present — risk is mitigated (×{safety?.vulnerability_factor}).
              </p>
            )}
          </div>

          {/* Concerns rail — the COMPLETE deterministic list */}
          <div className="rounded-2xl border border-slate-700/60 bg-slate-900/40 p-4">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                Concerns Detected ({anomalies.length})
              </p>
              {escalatedCount > 0 && (
                <span className="rounded bg-rose-500/15 px-1.5 py-0.5 text-[9px] font-bold uppercase text-rose-300">
                  {escalatedCount} escalated
                </span>
              )}
            </div>
            {anomalies.length === 0 ? (
              <p className="rounded-lg bg-emerald-500/10 px-3 py-2 text-sm text-emerald-300">
                ✓ No safety concerns — routines, home-safety and health all look normal.
              </p>
            ) : (
              <ul className="flex flex-col gap-1.5">
                {sortedAnoms.map((a, i) => {
                  const sev = SEVERITY_COLOR[a.severity] || SEVERITY_COLOR.medium;
                  return (
                    <li key={i} className={["flex items-start gap-2 rounded-lg border bg-slate-950/40 px-3 py-2", sev.ring].join(" ")}>
                      <span className={["mt-1.5 h-2 w-2 shrink-0 rounded-full", sev.dot].join(" ")} />
                      <div className="min-w-0">
                        <p className="text-sm text-slate-100">{a.detail}</p>
                        <p className="text-[10px] uppercase tracking-wide text-slate-500">
                          <span className={sev.text}>{a.severity}</span>
                          {a.base_severity && a.base_severity !== a.severity && (
                            <span className="text-slate-600">
                              {" "}
                              · escalated from {a.base_severity} (×{a.vulnerability_factor})
                            </span>
                          )}
                          {" · "}
                          {a.type}
                        </p>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
            <p className="mt-2 text-[10px] text-slate-500">
              🔊 Alexa speaks the most urgent of these aloud; the full list above is always shown.
            </p>
          </div>

          {/* How it decides */}
          <div className="rounded-2xl border border-slate-700/60 bg-slate-900/40 p-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">How Alexa Decides</p>
            <ol className="flex flex-col gap-1.5 text-[11px] text-slate-400">
              <li><span className="text-slate-200">1. Learns</span> the daily routine ({patternsCount} patterns) from the same engine as Pattern Recognition.</li>
              <li><span className="text-slate-200">2. Detects</span> safety, health &amp; security concerns from the live home.</li>
              <li><span className="text-slate-200">3. Escalates</span> each concern by who's home (elderly ×2, expecting ×1.8, child ×1.7).</li>
              <li><span className="text-slate-200">4. Acts</span> — secures the home and alerts family on its own.</li>
            </ol>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {Object.entries(STATUS_META).map(([k, v]) => (
                <span key={k} className={["rounded px-1.5 py-0.5 text-[9px] font-semibold", v.bg, v.text].join(" ")}>
                  {v.emoji} {v.label}
                </span>
              ))}
            </div>
          </div>
        </aside>
      </div>

      {/* Alexa's spoken response — the "voice" (a prioritized subset) */}
      <AlexaNotification
        notifications={alexaQueue}
        onDismiss={(id) => setAlexaQueue((q) => q.filter((n) => n.id !== id))}
        onDismissAll={() => setAlexaQueue([])}
        maxVisible={4}
      />

      {toast && (
        <div
          className={[
            "fixed bottom-5 left-1/2 -translate-x-1/2 rounded-xl px-4 py-2 text-sm font-medium shadow-xl",
            toast.ok ? "bg-emerald-500/90 text-white" : "bg-red-500/90 text-white",
          ].join(" ")}
        >
          {toast.msg}
        </div>
      )}
    </div>
  );
}
