import { useState, useEffect, useMemo, useRef, useCallback } from "react";
import { deviceApi } from "../deviceApi.js";
import {
  HOUSEHOLDS,
  roomsForHousehold,
  DEVICE_KIND,
} from "../config/houseLayout.js";
import DeviceTile from "../components/patterns/DeviceTile.jsx";
import AlexaNotification from "../components/patterns/AlexaNotification.jsx";

// The Devices section is the ACTUATOR layer over the fixed H003 care home.
// Mood, Patterns and Safety all only *observe*; here their conclusions are
// resolved — per room — into a single coherent set of device commands by a
// deterministic priority ladder (Manual > Safety > Mood > Pattern > Default).
// You can also grab manual control of any device; the AI hands it back once the
// override timer expires. Everything is ephemeral — nothing is persisted.

const HID = "H003";

function minsToHHMM(m) {
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return `${String(h).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}
function hhmmToMins(s) {
  const [h, m] = s.split(":").map(Number);
  return h * 60 + m;
}

export default function DeviceControl() {
  const rooms = useMemo(() => roomsForHousehold(HID), []);
  const devices = HOUSEHOLDS[HID].devices;
  const devicesByRoom = useCallback(
    (roomKey) => devices.filter((d) => d.room === roomKey),
    [devices],
  );

  const [scenario, setScenario] = useState(null);
  const [clock, setClock] = useState("18:45");
  const [mood, setMood] = useState(null);
  const [safety, setSafety] = useState(null);
  // Manual overrides: { [deviceId]: { on: bool, expires: epochMs } }
  const [manual, setManual] = useState({});
  const [result, setResult] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const [beatIndex, setBeatIndex] = useState(0);
  const [autoPlay, setAutoPlay] = useState(false);
  const [err, setErr] = useState(null);
  const [now, setNow] = useState(Date.now()); // ticks for countdowns

  const overrideSecs = scenario?.manual_override_seconds ?? 20;

  // Load the fixed H003 scenario once.
  useEffect(() => {
    deviceApi
      .scenario()
      .then(setScenario)
      .catch((e) => setErr(String(e)));
  }, []);

  // 1-second heartbeat: drives override countdowns and expiry.
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  // Drop expired manual overrides → control returns to the AI automatically.
  useEffect(() => {
    setManual((prev) => {
      const live = Object.fromEntries(
        Object.entries(prev).filter(([, v]) => v.expires > now),
      );
      return Object.keys(live).length === Object.keys(prev).length
        ? prev
        : live;
    });
  }, [now]);

  // Serialize only the bits that affect arbitration (live, non-expired manual).
  const manualPayload = useMemo(() => {
    const out = {};
    for (const [dev, v] of Object.entries(manual)) {
      if (v.expires > now) out[dev] = v.on;
    }
    return out;
  }, [manual, now]);

  const arbKey = useMemo(
    () => JSON.stringify({ clock, mood, safety, manualPayload }),
    [clock, mood, safety, manualPayload],
  );

  // Debounced ephemeral arbitration whenever the board changes.
  const lastNotif = useRef("");
  useEffect(() => {
    const t = setTimeout(async () => {
      try {
        const r = await deviceApi.arbitrate({
          time: clock,
          mood,
          safety,
          manual: manualPayload,
        });
        setResult(r);
        setErr(null);
        // Feed spoken lines to the Alexa stack, de-duped by fingerprint.
        const fp = (r.notifications || []).map((n) => n.id).join("|");
        if (fp !== lastNotif.current) {
          lastNotif.current = fp;
          setNotifications(
            (r.notifications || []).map((n) => ({
              id: n.id,
              text: n.text,
              tone: n.tone,
              llmPowered: false,
            })),
          );
        }
      } catch (e) {
        setErr(String(e));
      }
    }, 160);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [arbKey]);

  // Guided auto-play: step through the beats hands-free.
  useEffect(() => {
    if (!autoPlay || !scenario) return;
    const beats = scenario.beats || [];
    const t = setTimeout(() => {
      const next = beatIndex + 1;
      if (next >= beats.length) {
        setAutoPlay(false);
        return;
      }
      applyBeat(next);
    }, 7000);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoPlay, beatIndex, scenario]);

  function applyBeat(i) {
    const beat = scenario.beats[i];
    if (!beat) return;
    setBeatIndex(i);
    setClock(beat.time);
    setMood(beat.mood ?? null);
    setSafety(beat.safety ?? null);
    if (!beat.hint_manual) setManual({});
  }

  // Manual override: tap a device → take control of its room for overrideSecs.
  function toggleDevice(device, isOn) {
    setManual((prev) => ({
      ...prev,
      [device.id]: { on: !isOn, expires: Date.now() + overrideSecs * 1000 },
    }));
  }

  function resetBoard() {
    setMood(null);
    setSafety(null);
    setManual({});
    setAutoPlay(false);
    setBeatIndex(0);
  }

  const activeSet = useMemo(
    () => new Set(result?.active_devices || []),
    [result],
  );
  const anomalyMap = useMemo(
    () => new Map(Object.entries(result?.anomalies || {})),
    [result],
  );

  // Per-room remaining override seconds (max across its manual devices).
  const roomOverrideLeft = useCallback(
    (roomKey) => {
      let left = 0;
      for (const d of devicesByRoom(roomKey)) {
        const v = manual[d.id];
        if (v && v.expires > now)
          left = Math.max(left, Math.ceil((v.expires - now) / 1000));
      }
      return left;
    },
    [devicesByRoom, manual, now],
  );

  const beat = scenario?.beats?.[beatIndex];
  const mode = result?.mode_meta;

  return (
    <div className="space-y-5">
      {/* Header + mode banner */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-white">Ambient Intelligence</h2>
          <p className="text-sm text-slate-400">
            H003 · Indian-Context Care Home — Mood, Patterns & Safety resolved
            into one decision per room
          </p>
        </div>
        {mode && (
          <div
            className="flex items-center gap-2 rounded-full border px-4 py-1.5 text-sm font-semibold shadow"
            style={{
              borderColor: `${mode.color}80`,
              background: `${mode.color}1a`,
              color: mode.color,
            }}
          >
            <span>{mode.icon}</span>
            <span>House mode: {mode.label}</span>
          </div>
        )}
      </div>

      {err && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {err} — is the devices service running on :8004?
        </div>
      )}

      {/* Guided demo strip */}
      {scenario && beat && (
        <div className="rounded-2xl border border-indigo-500/30 bg-indigo-950/30 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-indigo-300">
              <span>🎬 Guided demo</span>
              <span className="text-slate-500">
                Step {beatIndex + 1} / {scenario.beats.length}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => applyBeat(Math.max(0, beatIndex - 1))}
                disabled={beatIndex === 0}
                className="rounded-lg border border-slate-700 px-3 py-1 text-xs font-semibold text-slate-300 transition hover:border-slate-500 disabled:opacity-40"
              >
                ‹ Prev
              </button>
              <button
                onClick={() => setAutoPlay((v) => !v)}
                className="rounded-lg border border-indigo-500/50 bg-indigo-500/15 px-3 py-1 text-xs font-semibold text-indigo-200 transition hover:bg-indigo-500/25"
              >
                {autoPlay ? "⏸ Pause" : "▶ Play"}
              </button>
              <button
                onClick={() =>
                  applyBeat(
                    Math.min(scenario.beats.length - 1, beatIndex + 1),
                  )
                }
                disabled={beatIndex === scenario.beats.length - 1}
                className="rounded-lg border border-slate-700 px-3 py-1 text-xs font-semibold text-slate-300 transition hover:border-slate-500 disabled:opacity-40"
              >
                Next ›
              </button>
            </div>
          </div>
          <p className="mt-2 text-sm font-semibold text-white">{beat.title}</p>
          <p className="mt-1 text-sm leading-relaxed text-slate-300">
            {beat.caption}
          </p>
        </div>
      )}

      {/* Controls: clock + signals */}
      <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr_1fr]">
        {/* Clock scrubber */}
        <div className="rounded-2xl border border-slate-700/60 bg-slate-900/50 p-4">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
              🕐 Demo clock
            </span>
            <span className="font-mono text-lg font-bold text-sky-300">
              {clock}
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={1439}
            step={5}
            value={hhmmToMins(clock)}
            onChange={(e) => {
              setAutoPlay(false);
              setClock(minsToHHMM(Number(e.target.value)));
            }}
            className="w-full accent-sky-500"
          />
          <div className="mt-1 flex justify-between text-[10px] text-slate-500">
            <span>00:00</span>
            <span>drives the learned PATTERN routines</span>
            <span>23:59</span>
          </div>
        </div>

        {/* Mood signal */}
        <SignalGroup
          title="🧠 Mood signal"
          accent="#a855f7"
          options={scenario?.mood_signals}
          value={mood}
          onChange={(v) => {
            setAutoPlay(false);
            setMood(v);
          }}
        />

        {/* Safety signal */}
        <SignalGroup
          title="🛡️ Safety signal"
          accent="#ef4444"
          options={scenario?.safety_signals}
          value={safety}
          onChange={(v) => {
            setAutoPlay(false);
            setSafety(v);
          }}
        />
      </div>

      {/* Floor plan + side rail */}
      <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
        {/* The H003 floor plan, tinted per winning source */}
        <div className="relative rounded-3xl border border-slate-700/50 bg-slate-950/40 p-4 shadow-2xl">
          <div className="pointer-events-none absolute right-5 top-4 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-600">
            H003 · Live · tap a device to override
          </div>
          <div
            className="grid gap-3"
            style={{
              gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
              gridTemplateRows: "repeat(4, minmax(140px, 1fr))",
            }}
          >
            {rooms.map((room) => {
              const rr = result?.rooms?.[room.key];
              const isControlled = rr && rr.source !== "default";
              const left = roomOverrideLeft(room.key);
              return (
                <div
                  key={room.key}
                  className="relative flex flex-col rounded-2xl border bg-slate-900/40 p-3 shadow-lg transition-colors"
                  style={{
                    gridColumn: room.col,
                    gridRow: room.row,
                    borderColor: isControlled
                      ? `${rr.source_color}80`
                      : "rgba(51,65,85,0.6)",
                    boxShadow: isControlled
                      ? `0 0 22px -6px ${rr.source_color}80`
                      : undefined,
                  }}
                >
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span
                        className="h-2.5 w-2.5 rounded-full"
                        style={{
                          background: room.accent,
                          boxShadow: `0 0 8px ${room.accent}`,
                        }}
                      />
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                        {room.name}
                      </h3>
                    </div>
                    {isControlled && (
                      <span
                        className="rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide"
                        style={{
                          background: `${rr.source_color}22`,
                          color: rr.source_color,
                        }}
                        title={rr.reason}
                      >
                        {rr.source_icon} {rr.source_label}
                        {left > 0 ? ` ${left}s` : ""}
                      </span>
                    )}
                  </div>

                  <div className="grid flex-1 content-start gap-2">
                    {devicesByRoom(room.key).map((d) => (
                      <DeviceTile
                        key={d.id}
                        device={d}
                        isOn={activeSet.has(d.id)}
                        anomaly={anomalyMap.get(d.id)}
                        onToggle={toggleDevice}
                        busy={false}
                      />
                    ))}
                    {devicesByRoom(room.key).length === 0 && (
                      <p className="text-[11px] italic text-slate-600">
                        no devices
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Side rail: arbitration breakdown + action log */}
        <div className="space-y-4">
          <ArbitrationPanel result={result} />
          <ActionLog result={result} />
          <button
            onClick={resetBoard}
            className="w-full rounded-xl border border-slate-700 bg-slate-900/50 px-3 py-2 text-xs font-semibold text-slate-300 transition hover:border-slate-500"
          >
            ↺ Reset board
          </button>
        </div>
      </div>

      <AlexaNotification
        notifications={notifications}
        onDismiss={(id) =>
          setNotifications((ns) => ns.filter((n) => n.id !== id))
        }
        onDismissAll={() => setNotifications([])}
      />
    </div>
  );
}

// ─── Signal toggle group (mood / safety) ─────────────────────────────────────
function SignalGroup({ title, accent, options, value, onChange }) {
  const entries = Object.entries(options || {});
  return (
    <div className="rounded-2xl border border-slate-700/60 bg-slate-900/50 p-4">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
        {title}
      </div>
      <div className="flex flex-col gap-1.5">
        {entries.length === 0 && (
          <p className="text-[11px] italic text-slate-600">loading…</p>
        )}
        {entries.map(([id, sig]) => {
          const on = value === id;
          return (
            <button
              key={id}
              onClick={() => onChange(on ? null : id)}
              className="flex items-center justify-between rounded-lg border px-2.5 py-1.5 text-left text-xs font-medium transition"
              style={{
                borderColor: on ? `${accent}99` : "rgba(51,65,85,0.6)",
                background: on ? `${accent}1a` : "transparent",
                color: on ? accent : "#cbd5e1",
              }}
            >
              <span className="truncate">{sig.label}</span>
              <span className="ml-2 text-[10px] opacity-70">
                {on ? "● on" : "○"}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ─── Per-room "who decided what" breakdown ───────────────────────────────────
function ArbitrationPanel({ result }) {
  const rooms = result?.rooms || {};
  const active = Object.entries(rooms).filter(
    ([, r]) => r.source !== "default",
  );
  return (
    <div className="rounded-2xl border border-slate-700/60 bg-slate-900/50 p-4">
      <h3 className="mb-3 text-sm font-bold text-white">Who's in control</h3>
      {active.length === 0 && (
        <p className="text-xs italic text-slate-500">
          Every room idle — no routine, mood, or alert active.
        </p>
      )}
      <div className="space-y-2">
        {active.map(([key, r]) => (
          <div
            key={key}
            className="rounded-lg border bg-slate-950/40 p-2.5"
            style={{ borderColor: `${r.source_color}40` }}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold capitalize text-slate-200">
                {key.replace(/_/g, " ")}
              </span>
              <span
                className="rounded px-1.5 py-0.5 text-[9px] font-bold uppercase"
                style={{
                  background: `${r.source_color}22`,
                  color: r.source_color,
                }}
              >
                {r.source_icon} {r.source_label}
              </span>
            </div>
            <p className="mt-1 text-[11px] leading-snug text-slate-400">
              {r.reason}
            </p>
            {r.overridden?.length > 0 && (
              <p className="mt-1 text-[10px] italic text-slate-600">
                outranked: {r.overridden.join(", ")}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Live action log ─────────────────────────────────────────────────────────
function ActionLog({ result }) {
  const log = result?.log || [];
  return (
    <div className="rounded-2xl border border-slate-700/60 bg-slate-900/50 p-4">
      <h3 className="mb-3 text-sm font-bold text-white">Action log</h3>
      {log.length === 0 && (
        <p className="text-xs italic text-slate-500">Nothing happening yet.</p>
      )}
      <div className="space-y-1.5">
        {log.map((e, i) => (
          <div key={i} className="flex items-start gap-2 text-[11px]">
            <span className="mt-0.5 font-mono text-slate-500">{e.time}</span>
            <span
              className="rounded px-1 py-0.5 text-[9px] font-bold uppercase"
              style={{
                background: "rgba(148,163,184,0.12)",
                color: "#cbd5e1",
              }}
            >
              {e.source_label}
            </span>
            <span className="flex-1 leading-snug text-slate-400">{e.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
