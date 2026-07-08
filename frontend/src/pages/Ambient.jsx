import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../patternsApi.js";
import AlexaNotification from "../components/patterns/AlexaNotification.jsx";

// ════════════════════════════════════════════════════════════════════════════
//  AMBIENT CONTEXT — "The Household Ear"
//  ---------------------------------------------------------------------------
//  Press LISTEN → the browser records a ~4s mic clip → it's sent to Google
//  Gemini (an AUDIO-NATIVE LLM) which identifies ANY household sound in open
//  vocabulary (pressure-cooker whistle, mixer-grinder, temple bell, baby crying)
//  and reasons an action. When the sound matches a known routine, the backend
//  overlays the DETERMINISTIC verified action + expected/unusual timing.
//  Simulate buttons drive the same deterministic pipeline as a stage fallback.
//
//  Privacy: only a short clip is analysed for its SOUND, in the family's own
//  Google project; nothing is stored and no speech transcript is kept.
// ════════════════════════════════════════════════════════════════════════════

const HID = "AMB1";
const ROSTER = ["father", "mother", "grandma", "baby"];
const TARGET_SR = 16000;

const SEV = {
  info: { ring: "border-sky-500/40", text: "text-sky-300", dot: "bg-sky-400", badge: "bg-sky-500/15 text-sky-300" },
  suggest: { ring: "border-fuchsia-500/40", text: "text-fuchsia-300", dot: "bg-fuchsia-400", badge: "bg-fuchsia-500/15 text-fuchsia-300" },
  warn: { ring: "border-amber-500/50", text: "text-amber-300", dot: "bg-amber-400", badge: "bg-amber-500/15 text-amber-300" },
  alert: { ring: "border-red-500/60", text: "text-red-300", dot: "bg-red-500", badge: "bg-red-500/20 text-red-300" },
};
const TIMING = {
  expected: { label: "on schedule", cls: "bg-emerald-500/15 text-emerald-300" },
  unusual: { label: "unusual timing", cls: "bg-amber-500/20 text-amber-200" },
  new: { label: "new", cls: "bg-slate-700/50 text-slate-300" },
};

function nowHHMM() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

// ── Audio helpers: record → 16k mono WAV → base64 (Gemini-friendly) ──────────
function downsample(buf, from, to) {
  if (to >= from) return buf;
  const ratio = from / to;
  const len = Math.round(buf.length / ratio);
  const out = new Float32Array(len);
  let oi = 0, bi = 0;
  while (oi < len) {
    const next = Math.round((oi + 1) * ratio);
    let sum = 0, c = 0;
    for (let i = bi; i < next && i < buf.length; i++) { sum += buf[i]; c++; }
    out[oi++] = sum / (c || 1);
    bi = next;
  }
  return out;
}

function encodeWav(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const w = (o, s) => { for (let i = 0; i < s.length; i++) view.setUint8(o + i, s.charCodeAt(i)); };
  w(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true); w(8, "WAVE");
  w(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  w(36, "data"); view.setUint32(40, samples.length * 2, true);
  let o = 44;
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    o += 2;
  }
  return new Blob([view], { type: "audio/wav" });
}

function blobToBase64(blob) {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onloadend = () => res(String(r.result).split(",")[1]);
    r.onerror = rej;
    r.readAsDataURL(blob);
  });
}

export default function Ambient() {
  const [sounds, setSounds] = useState([]);
  const [routines, setRoutines] = useState([]);
  const [clock, setClock] = useState(nowHHMM());
  const [people, setPeople] = useState(() => new Set(["mother", "baby"]));
  const [gasOn, setGasOn] = useState(true);
  const [feed, setFeed] = useState([]);
  const [listening, setListening] = useState(false);
  const [micStatus, setMicStatus] = useState("idle"); // idle | loading | listening | error
  const [analyzing, setAnalyzing] = useState(false);
  const [level, setLevel] = useState(0);               // 0..1 VU meter
  const [toast, setToast] = useState(null);
  const [alexaQueue, setAlexaQueue] = useState([]);   // spoken Alexa narrations
  // Light / dark theme (Amazon palette), shared key with the Patterns page.
  const [theme, setTheme] = useState(
    () => localStorage.getItem("pp-theme") || "dark",
  );
  // Which "Explore" section is expanded (accordion; null = all collapsed).
  const [openSection, setOpenSection] = useState(null);
  // The "Trigger a sound" simulate palette — collapsed until clicked.
  const [simOpen, setSimOpen] = useState(false);
  // Continuous-listening audio plumbing (refs so the audio callback sees them).
  const audioCtxRef = useRef(null);
  const streamRef = useRef(null);
  const nodeRef = useRef(null);
  const ringRef = useRef(null);        // rolling PCM buffer
  const ringWriteRef = useRef(0);
  const lastSendRef = useRef(0);       // cooldown clock (rate-limit safe)
  const sendingRef = useRef(false);
  const levelRef = useRef(0);
  const levelTimerRef = useRef(null);
  const ctxDataRef = useRef({});       // latest house context for the callback
  const analyzeRef = useRef(async () => {});

  useEffect(() => {
    localStorage.setItem("pp-theme", theme);
  }, [theme]);

  const flash = useCallback((msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3200);
  }, []);

  const loadRoutines = useCallback(async () => {
    try { setRoutines(await api.ambientRoutines(HID)); } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    (async () => {
      try { setSounds((await api.ambientSounds()).sounds); } catch { /* ignore */ }
      loadRoutines();
    })();
  }, [loadRoutines]);

  const buildContext = useCallback(
    () => ({
      current_time: clock || undefined,
      people_home: [...people],
      active_devices: gasOn ? ["kitchen_gas_stove"] : [],
      ingest: true,
    }),
    [clock, people, gasOn],
  );

  const pushResult = useCallback((r) => {
    if (!r) return;
    r._id = `${Date.now()}-${r.sound}`;
    setFeed((f) => [r, ...f].slice(0, 30));
    if (r.recognised) loadRoutines();
    // Speak it aloud through the Alexa narrator (flags AND informational sounds).
    if (r.recognised !== false) {
      const text = r.narration || r.prompt;
      if (text) {
        const alert = r.flagged || ["warn", "high", "critical", "alert"].includes(r.severity);
        setAlexaQueue((q) => [
          {
            id: r._id,
            text,
            explanation: r.explanation || r.sense_reason || r.likely_activity || r.meaning || "",
            llmPowered: !!(r.narration_llm || r.llm_powered),
            tone: alert ? "alert" : "calm",
          },
          ...q,
        ].slice(0, 6));
      }
    }
  }, [loadRoutines]);

  // ── Simulate path (deterministic /observe) ───────────────────────────────
  const simulate = useCallback(
    async (key) => {
      try {
        pushResult(await api.ambientObserve(HID, { ...buildContext(), sound: key, confidence: 0.95 }));
      } catch (e) { flash(`Interpret failed: ${e.message}`); }
    },
    [buildContext, pushResult, flash],
  );

  // Keep the latest house context available to the (long-lived) audio callback.
  useEffect(() => { ctxDataRef.current = buildContext(); }, [buildContext]);

  // Analyse one captured clip with Gemini and surface the result.
  const analyzeClip = useCallback(async (float32, sr) => {
    setAnalyzing(true);
    try {
      const mono = sr === TARGET_SR ? float32 : downsample(float32, sr, TARGET_SR);
      const audio_base64 = await blobToBase64(encodeWav(mono, TARGET_SR));
      const r = await api.ambientListen(HID, {
        ...ctxDataRef.current, audio_base64, mime_type: "audio/wav",
      });
      if (r && r.recognised !== false) pushResult(r);
    } catch {
      /* transient — keep listening */
    } finally {
      setAnalyzing(false);
      sendingRef.current = false;
    }
  }, [pushResult]);
  useEffect(() => { analyzeRef.current = analyzeClip; }, [analyzeClip]);

  // ── Continuous listening: hear a real sound → capture → Gemini ────────────
  // Energy-gated with a cooldown so silence costs nothing and we never exceed
  // Gemini's free-tier rate limit. Just play/make a sound — no clicking.
  const startListening = useCallback(async () => {
    setMicStatus("loading");
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      setMicStatus("error");
      flash(`Mic unavailable: ${e.message}. Use the simulate buttons.`);
      return;
    }
    streamRef.current = stream;
    let ctx;
    try { ctx = new AudioContext({ sampleRate: TARGET_SR }); } catch { ctx = new AudioContext(); }
    audioCtxRef.current = ctx;
    const sr = ctx.sampleRate;
    ringRef.current = new Float32Array(sr * 4); // rolling 4s
    ringWriteRef.current = 0;

    const source = ctx.createMediaStreamSource(stream);
    const node = ctx.createScriptProcessor(4096, 1, 1);
    nodeRef.current = node;

    const ENERGY = 0.03;      // RMS gate — meaningful sound, not room hiss
    const COOLDOWN = 6000;    // ms between sends (≤10/min → within free tier)
    const CLIP_SECONDS = 3;

    node.onaudioprocess = (e) => {
      const input = e.inputBuffer.getChannelData(0);
      const ring = ringRef.current;
      const N = ring.length;
      let w = ringWriteRef.current;
      let sumSq = 0;
      for (let i = 0; i < input.length; i++) {
        const s = input[i];
        ring[w] = s;
        w = (w + 1) % N;
        sumSq += s * s;
      }
      ringWriteRef.current = w;
      const rms = Math.sqrt(sumSq / input.length);
      levelRef.current = Math.max(rms, levelRef.current * 0.85);

      const now = Date.now();
      if (rms > ENERGY && !sendingRef.current && now - lastSendRef.current > COOLDOWN) {
        sendingRef.current = true;
        lastSendRef.current = now;
        const clipLen = Math.min(N, sr * CLIP_SECONDS);
        const clip = new Float32Array(clipLen);
        const start = (w - clipLen + N) % N;
        for (let i = 0; i < clipLen; i++) clip[i] = ring[(start + i) % N];
        analyzeRef.current(clip, sr);
      }
    };
    source.connect(node);
    node.connect(ctx.destination); // output left silent → no mic echo

    levelTimerRef.current = setInterval(() => {
      setLevel(Math.min(1, levelRef.current * 6));
      levelRef.current *= 0.8;
    }, 150);

    setMicStatus("listening");
    setListening(true);
    flash("Listening — play or make a household sound");
  }, [flash]);

  const stopListening = useCallback(() => {
    try {
      if (levelTimerRef.current) clearInterval(levelTimerRef.current);
      nodeRef.current?.disconnect();
      audioCtxRef.current?.close();
      streamRef.current?.getTracks().forEach((t) => t.stop());
    } catch {
      /* ignore */
    }
    levelTimerRef.current = null;
    nodeRef.current = null;
    audioCtxRef.current = null;
    streamRef.current = null;
    sendingRef.current = false;
    setLevel(0);
    setListening(false);
    setMicStatus("idle");
  }, []);

  useEffect(() => () => stopListening(), [stopListening]);

  const confirmAction = useCallback(
    (item) => {
      const a = item.suggested_action;
      if (a?.device === "kitchen_gas_stove" && a.action === "OFF") setGasOn(false);
      flash(`✓ ${a.action} ${a.device.replace(/_/g, " ")}`);
      setFeed((f) => f.map((x) => (x._id === item._id ? { ...x, _done: true } : x)));
    },
    [flash],
  );

  const seedDemo = useCallback(async () => {
    try {
      const r = await api.ambientSeed(HID);
      flash(`Learned ${r.sound_routines_learned} sound routines from ${r.events_stored} events`);
      loadRoutines();
    } catch (e) { flash(`Seed failed: ${e.message}`); }
  }, [flash, loadRoutines]);

  const togglePerson = (p) =>
    setPeople((prev) => { const n = new Set(prev); n.has(p) ? n.delete(p) : n.add(p); return n; });

  const current = feed[0];
  const byCategory = useMemo(() => {
    const g = {};
    sounds.forEach((s) => (g[s.category] ||= []).push(s));
    return g;
  }, [sounds]);

  const listenLabel = micStatus === "loading" ? "… starting"
    : listening ? (analyzing ? "● hearing…" : "● Listening") : "🎙️ Listen";

  return (
    <div className="pp-app min-h-full" data-ptheme={theme}>
      <div className="mx-auto flex min-h-full max-w-[1400px] flex-col gap-4 p-4">
        {/* Header — brand + demo/theme controls (Listen moved to centre stage) */}
        <header className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-700/70 bg-slate-900/70 px-4 py-3 backdrop-blur">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-teal-500 to-cyan-600 text-xl shadow-lg">👂</span>
          <div className="leading-tight">
            <h1 className="text-base font-bold text-slate-100">Ambient Context · The Household Ear</h1>
            <p className="text-xs text-slate-400">
              Hears a real sound → Gemini identifies it → context-aware action
            </p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
              title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
              className="grid h-9 w-9 place-items-center rounded-lg border border-slate-700 bg-slate-800 text-base text-slate-300 transition hover:border-slate-500"
            >
              {theme === "dark" ? "☀️" : "🌙"}
            </button>
            <button onClick={seedDemo}
              className="pp-btn rounded-lg px-3 py-2 text-sm font-semibold transition"
              title="Learn 30 days of sound routines so 'expected vs unusual' works">
              ⤵ Learn routines
            </button>
          </div>
        </header>

        {/* Live-context bar — slim controls that shape interpretation */}
        <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-700/60 bg-slate-900/40 px-4 py-2.5">
          <span className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-slate-500">
            <span className="grid h-6 w-6 place-items-center rounded-lg bg-[var(--pp-blue-weak)] text-sm">🧭</span>
            Context
          </span>
          <input type="time" value={clock} onChange={(e) => setClock(e.target.value || nowHHMM())}
            className="rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-sm text-slate-100 outline-none focus:border-[var(--pp-accent)]" />
          <button onClick={() => setGasOn((g) => !g)}
            className={["rounded-lg border px-3 py-1.5 text-sm font-semibold transition",
              gasOn ? "border-orange-400/60 bg-orange-500/20 text-orange-200" : "border-slate-700 bg-slate-800/60 text-slate-400"].join(" ")}>
            🔥 Gas {gasOn ? "ON" : "off"}
          </button>
          <span className="ml-1 text-xs text-slate-500">Home:</span>
          {ROSTER.map((p) => {
            const on = people.has(p);
            return (
              <button key={p} onClick={() => togglePerson(p)}
                className={["rounded-full px-2.5 py-1 text-xs font-medium capitalize",
                  on ? "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/40" : "bg-slate-700/40 text-slate-500"].join(" ")}>
                {on ? "🟢" : "⚪"} {p}
              </button>
            );
          })}
          <span className="ml-auto hidden items-center gap-1.5 text-xs text-slate-500 sm:flex" title="Nothing is recorded or stored; no speech is transcribed.">
            🔒 sound only · nothing stored
          </span>
        </div>

        {/* ── Centre stage: the big Listen orb, like a voice-assistant simulator ── */}
        <section className="rounded-2xl border border-slate-700/60 bg-slate-900/50 px-4 py-10">
          <div className="flex flex-col items-center gap-5">
            <div className="relative grid place-items-center">
              {/* Reactive halo — grows with the live mic level while listening */}
              {listening && (
                <span
                  className="pointer-events-none absolute h-48 w-48 rounded-full bg-teal-400/20"
                  style={{
                    transform: `scale(${1 + level * 0.7})`,
                    opacity: 0.35 + level * 0.5,
                    transition: "transform 120ms ease-out, opacity 120ms ease-out",
                  }}
                />
              )}
              {listening && (
                <span className="pointer-events-none absolute h-44 w-44 animate-ping rounded-full bg-red-400/10" />
              )}
              <button
                onClick={listening ? stopListening : startListening}
                disabled={micStatus === "loading"}
                title={listening ? "Tap to stop listening" : "Tap to start listening"}
                className={[
                  "relative grid h-40 w-40 place-items-center rounded-full border-2 shadow-xl transition disabled:cursor-not-allowed disabled:opacity-60",
                  listening
                    ? "border-red-400/70 bg-red-500/15 text-red-200"
                    : "border-teal-400/60 bg-teal-500/10 text-teal-200 hover:bg-teal-500/20",
                ].join(" ")}
              >
                <span className="text-6xl leading-none">{listening ? "🔴" : "🎙️"}</span>
              </button>
            </div>

            <div className="text-center">
              <p className="text-xl font-bold text-slate-100">
                {micStatus === "loading"
                  ? "Starting mic…"
                  : listening
                    ? analyzing
                      ? "Hearing a sound…"
                      : "Listening…"
                    : "Tap to Listen"}
              </p>
              <p className="mt-1 text-sm text-slate-400">
                {listening
                  ? "Play or make a household sound · tap the orb to stop"
                  : "Play a real sound — or open ‘Trigger a sound’ below to simulate"}
              </p>
            </div>
          </div>

          {/* The interpretation appears here as a message, right under the orb */}
          {current && (
            <div className={["mx-auto mt-8 w-full max-w-3xl rounded-2xl border bg-slate-950/30 p-5", SEV[current.severity]?.ring || "border-slate-700/60"].join(" ")}>
              <div className="flex items-start gap-4">
                <span className="text-5xl leading-none">{current.emoji}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-xl font-bold text-slate-100">{current.detected_raw || current.label}</h2>
                    {current.flagged && <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-bold uppercase text-amber-200">⚠ flagged</span>}
                    <span className={["rounded px-1.5 py-0.5 text-[10px] font-bold uppercase", SEV[current.severity]?.badge].join(" ")}>{current.severity}</span>
                    {current.timing !== "new" && <span className={["rounded px-1.5 py-0.5 text-[10px] font-semibold", TIMING[current.timing]?.cls].join(" ")}>{TIMING[current.timing]?.label}</span>}
                    {current.llm_powered && <span className="rounded bg-cyan-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-cyan-300">🎧 heard by Gemini</span>}
                  </div>
                  {/* The spoken "Alexa" line — narration when the engine flagged it, else the base prompt. */}
                  <p className="mt-2 text-base leading-relaxed text-slate-100">🔊 {current.narration || current.prompt}</p>
                  {current.sense_reason && (
                    <p className="mt-2 rounded-md bg-amber-500/10 px-2.5 py-1.5 text-sm text-amber-200/90">
                      🧠 Why flagged: {current.sense_reason}
                      {current.narration_llm && <span className="ml-1 text-slate-500">· phrased by LLM</span>}
                    </p>
                  )}
                  {current.likely_activity && <p className="mt-1 text-sm text-slate-400">🏠 {current.likely_activity}</p>}
                  {current.routine_note && <p className="mt-1 text-sm text-slate-400">🕒 {current.routine_note}</p>}
                  {current.suggested_action && !current._done && (
                    <div className="mt-3 flex items-center gap-2">
                      <button onClick={() => confirmAction(current)}
                        className="rounded-lg border border-emerald-400/60 bg-emerald-500/15 px-4 py-2 text-sm font-bold text-emerald-200 hover:bg-emerald-500/25">
                        {current.suggested_action.requires_confirmation ? "✓ Confirm" : "▶"} {current.suggested_action.action} {current.suggested_action.device.replace(/_/g, " ")}
                      </button>
                      <span className="text-xs text-slate-500">{current.suggested_action.requires_confirmation ? "asks before acting" : "auto-action"}</span>
                    </div>
                  )}
                  {current._done && <p className="mt-2 text-sm text-emerald-300">✓ done</p>}
                </div>
              </div>
            </div>
          )}
        </section>

        {/* Trigger a sound — the simulate palette, collapsed until clicked */}
        <section className="overflow-hidden rounded-2xl border border-slate-700/60 bg-slate-900/40">
          <button
            onClick={() => setSimOpen((o) => !o)}
            className="flex w-full items-center gap-2 px-4 py-3 text-left transition hover:bg-slate-800/40"
          >
            <span className="text-base">🎛️</span>
            <span className="text-sm font-bold uppercase tracking-wide text-slate-300">
              Trigger a sound
            </span>
            <span className="text-sm font-normal normal-case text-slate-500">· tap to simulate</span>
            {sounds.length > 0 && (
              <span className="rounded-full bg-slate-700/70 px-1.5 text-xs font-bold text-slate-300">
                {sounds.length}
              </span>
            )}
            <span className="ml-auto text-slate-500">{simOpen ? "▾" : "▸"}</span>
          </button>
          {simOpen && (
            <div className="flex flex-col gap-3 border-t border-slate-700/60 p-4">
              {Object.entries(byCategory).map(([cat, items]) => (
                <div key={cat}>
                  <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">{cat}</p>
                  <div className="flex flex-wrap gap-1.5">
                    {items.map((s) => (
                      <button key={s.key} onClick={() => simulate(s.key)} title={s.meaning}
                        className="rounded-lg border border-slate-700 bg-slate-800/60 px-2.5 py-1.5 text-sm text-slate-300 transition hover:border-teal-500/50 hover:bg-slate-700/60">
                        {s.emoji} {s.label}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Explore drawer — recent sounds + learned routines, collapsed by default */}
        <ExploreDrawer
          openKey={openSection}
          onToggle={(k) => setOpenSection((cur) => (cur === k ? null : k))}
          sections={[
            {
              key: "feed",
              label: "Recent Sounds",
              icon: "📜",
              count: Math.max(0, feed.length - 1),
              render: () =>
                feed.length <= 1 ? (
                  <p className="text-sm text-slate-500">Nothing yet — trigger a sound above.</p>
                ) : (
                  <ul className="flex flex-col gap-1.5">
                    {feed.slice(1).map((it) => (
                      <li key={it._id} className={["flex items-center gap-2 rounded-lg px-3 py-2", it.flagged ? "bg-amber-500/10 ring-1 ring-amber-500/30" : "bg-slate-950/40"].join(" ")}>
                        <span className={["h-2 w-2 shrink-0 rounded-full", SEV[it.severity]?.dot].join(" ")} />
                        <span className="text-base">{it.emoji}</span>
                        <span className="text-sm text-slate-200">{it.detected_raw || it.label}</span>
                        {it.flagged && <span className="text-xs text-amber-300">⚠</span>}
                        <span className="ml-auto truncate text-xs text-slate-500">{it.narration || it.prompt}</span>
                      </li>
                    ))}
                  </ul>
                ),
            },
            {
              key: "routines",
              label: "Learned Routines",
              icon: "🕒",
              count: routines.length,
              render: () =>
                routines.length === 0 ? (
                  <p className="text-sm text-slate-500">None yet — hit <span className="text-slate-300">Learn routines</span> in the header.</p>
                ) : (
                  <ul className="grid gap-1.5 sm:grid-cols-2">
                    {routines.map((r) => (
                      <li key={r.sound} className="flex items-center gap-2 rounded-lg bg-slate-950/40 px-3 py-2 text-sm text-slate-300">
                        <span className="text-base">{r.emoji}</span>
                        <span className="flex-1 truncate">{r.label}</span>
                        <span className="font-mono text-slate-400">~{r.usual_time}</span>
                        <span className="text-xs text-slate-500">{Math.round(r.confidence * 100)}%</span>
                      </li>
                    ))}
                  </ul>
                ),
            },
          ]}
        />

        {toast && (
          <div className="fixed bottom-5 left-1/2 -translate-x-1/2 rounded-xl bg-slate-800/95 px-4 py-2 text-sm font-medium text-white shadow-xl ring-1 ring-slate-600">
            {toast}
          </div>
        )}

        {/* Alexa speaks every recognised sound aloud (narrator LLM) */}
        <AlexaNotification
          notifications={alexaQueue}
          onDismiss={(id) => setAlexaQueue((q) => q.filter((n) => n.id !== id))}
          onDismissAll={() => setAlexaQueue([])}
          maxVisible={3}
          autoExpandDetails
        />
      </div>
    </div>
  );
}

// Row of heading buttons that reveal one panel at a time below them —
// mirrors the Patterns page so the two views feel like one product.
function ExploreDrawer({ sections, openKey, onToggle }) {
  const active = sections.find((s) => s.key === openKey);
  return (
    <section className="rounded-2xl border border-slate-700/60 bg-slate-900/50 p-3">
      <div className="mb-1 flex items-center gap-2 px-1">
        <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Explore</span>
        <span className="text-xs text-slate-500">— details are tucked away; open what you need</span>
      </div>
      <div className="flex flex-wrap gap-2 p-1">
        {sections.map((s) => {
          const open = openKey === s.key;
          return (
            <button
              key={s.key}
              data-open={open}
              onClick={() => onToggle(s.key)}
              className="pp-tab flex items-center gap-2 rounded-xl px-3.5 py-2 text-sm font-semibold transition"
            >
              <span className="text-base">{s.icon}</span>
              {s.label}
              {s.count > 0 && (
                <span className="rounded-full bg-slate-700/70 px-1.5 text-xs font-bold text-slate-300">
                  {s.count}
                </span>
              )}
              <span className="text-slate-500">{open ? "▾" : "▸"}</span>
            </button>
          );
        })}
      </div>
      {active && (
        <div className="mt-2 rounded-xl border border-slate-700/60 bg-slate-950/30 p-3">
          {active.render()}
        </div>
      )}
    </section>
  );
}
