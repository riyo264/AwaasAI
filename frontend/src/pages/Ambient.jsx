import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../patternsApi.js";
import AlexaNotification from "../components/patterns/AlexaNotification.jsx";

// ════════════════════════════════════════════════════════════════════════════
//  AMBIENT CONTEXT — "The Household Ear"
//  ---------------------------------------------------------------------------
//  Press LISTEN → the browser records a ~4s mic clip → it's sent to an
//  AUDIO-NATIVE LLM which identifies ANY household sound in open
//  vocabulary (pressure-cooker whistle, mixer-grinder, temple bell, baby crying)
//  and reasons an action. When the sound matches a known routine, the backend
//  overlays the DETERMINISTIC verified action + expected/unusual timing.
//  Simulate buttons drive the same deterministic pipeline as a stage fallback.
//
//  Privacy: only a short clip is analysed for its SOUND, in the family's own
//  Google project; nothing is stored and no speech transcript is kept.
// ════════════════════════════════════════════════════════════════════════════

const HID = "AMB1";
// Who's home is fed to the interpreter as context (shapes e.g. an empty-house
// glass-break vs. a daytime one) but is no longer a user-facing control.
const PEOPLE_HOME = ["mother", "baby"];
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

function timeAgo(ts) {
  const s = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  return `${Math.round(m / 60)}h ago`;
}

// ── Audio helpers: record → 16k mono WAV → base64 (LLM-friendly) ─────────────
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
  const [gasOn, setGasOn] = useState(true);
  const [feed, setFeed] = useState([]);
  const [listening, setListening] = useState(false);
  const [micStatus, setMicStatus] = useState("idle"); // idle | loading | listening | error
  const [analyzing, setAnalyzing] = useState(false);
  const [heard, setHeard] = useState(false);           // gate tripped, capturing the sound's body
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
  const analyserRef = useRef(null);    // feeds the live spectrum ring
  const ringRef = useRef(null);        // rolling PCM buffer
  const ringWriteRef = useRef(0);
  const lastSendRef = useRef(0);       // cooldown clock (rate-limit safe)
  const sendingRef = useRef(false);
  const heardTimerRef = useRef(null);  // pending body-capture timer
  const noiseFloorRef = useRef(0.008); // adaptive room-noise estimate
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
      people_home: [...PEOPLE_HOME],
      active_devices: gasOn ? ["kitchen_gas_stove"] : [],
      ingest: true,
    }),
    [clock, gasOn],
  );

  const pushResult = useCallback((r) => {
    if (!r) return;
    r._id = `${Date.now()}-${r.sound}`;
    r._at = Date.now();
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

  // Analyse one captured clip with the audio LLM and surface the result.
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

  // ── Continuous listening: hear a real sound → capture → audio LLM ─────────
  // Energy-gated with a cooldown so silence costs nothing and we never exceed
  // the audio LLM's rate limit. Just play/make a sound — no clicking.
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
    // Analyser drives the live spectrum ring around the orb (60fps, no state).
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = 0.72;
    source.connect(analyser);
    analyserRef.current = analyser;

    const node = ctx.createScriptProcessor(4096, 1, 1);
    nodeRef.current = node;

    const COOLDOWN = 6000;     // ms between sends (≤10/min → within free tier)
    const CLIP_SECONDS = 3;
    const BODY_DELAY = 1100;   // ms after the gate trips before capturing, so the
                               // clip holds the sound's BODY, not just its onset —
                               // markedly better identification.
    noiseFloorRef.current = 0.008;

    node.onaudioprocess = (e) => {
      const input = e.inputBuffer.getChannelData(0);
      const ring = ringRef.current;
      if (!ring) return;
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

      // Adaptive gate: slow-follow the room's noise floor so a humming fan
      // doesn't trigger constantly, while a quiet room stays sensitive.
      const floor = noiseFloorRef.current;
      if (rms < floor * 3) noiseFloorRef.current = floor * 0.98 + rms * 0.02;
      const gate = Math.max(0.022, noiseFloorRef.current * 3.5);

      const now = Date.now();
      if (rms > gate && !sendingRef.current && now - lastSendRef.current > COOLDOWN) {
        sendingRef.current = true;
        lastSendRef.current = now;
        setHeard(true);
        // Let the sound develop, THEN slice the last CLIP_SECONDS from the ring
        // (≈1.9s before the trigger + 1.1s after — onset AND body).
        heardTimerRef.current = setTimeout(() => {
          heardTimerRef.current = null;
          setHeard(false);
          const liveRing = ringRef.current;
          if (!liveRing || !nodeRef.current) { sendingRef.current = false; return; }
          const clipLen = Math.min(N, sr * CLIP_SECONDS);
          const clip = new Float32Array(clipLen);
          const start = (ringWriteRef.current - clipLen + N) % N;
          for (let i = 0; i < clipLen; i++) clip[i] = liveRing[(start + i) % N];
          analyzeRef.current(clip, sr);
        }, BODY_DELAY);
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
      if (heardTimerRef.current) clearTimeout(heardTimerRef.current);
      nodeRef.current?.disconnect();
      audioCtxRef.current?.close();
      streamRef.current?.getTracks().forEach((t) => t.stop());
    } catch {
      /* ignore */
    }
    levelTimerRef.current = null;
    heardTimerRef.current = null;
    nodeRef.current = null;
    analyserRef.current = null;
    audioCtxRef.current = null;
    streamRef.current = null;
    sendingRef.current = false;
    setLevel(0);
    setHeard(false);
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

  const current = feed[0];
  const byCategory = useMemo(() => {
    const g = {};
    sounds.forEach((s) => (g[s.category] ||= []).push(s));
    return g;
  }, [sounds]);

  return (
    <div className="pp-app min-h-full" data-ptheme={theme}>
      <div className="mx-auto flex min-h-full max-w-[1400px] flex-col gap-4 p-4">
        {/* Header — brand + demo/theme controls (Listen moved to centre stage) */}
        <header className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-700/70 bg-slate-900/70 px-4 py-3 backdrop-blur">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-teal-500 to-cyan-600 text-xl shadow-lg">👂</span>
          <div className="leading-tight">
            <h1 className="text-base font-bold text-slate-100">Ambient Context · The Household Ear</h1>
            <p className="text-xs text-slate-400">
              Hears a real sound → Alexa identifies it → context-aware action
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
          <span className="ml-auto hidden items-center gap-1.5 text-xs text-slate-500 sm:flex" title="Nothing is recorded or stored; no speech is transcribed.">
            🔒 sound only · nothing stored
          </span>
        </div>

        {/* ── Centre stage: the big Listen orb, like a voice-assistant simulator ── */}
        <section className="rounded-2xl border border-slate-700/60 bg-slate-900/50 px-4 py-10">
          <div className="flex flex-col items-center gap-5">
            <div className="relative grid h-56 w-56 place-items-center">
              {/* Soft ripples while quietly listening (paused during analysis) */}
              {listening && !analyzing && (
                <>
                  <span className="mic-ripple pointer-events-none absolute h-40 w-40 rounded-full border border-teal-400/35" />
                  <span
                    className="mic-ripple pointer-events-none absolute h-40 w-40 rounded-full border border-teal-400/20"
                    style={{ animationDelay: "1.2s" }}
                  />
                </>
              )}
              {/* Live-level glow — a soft, level-reactive halo hugging the orb. */}
              {listening && (
                <span
                  className="pointer-events-none absolute h-40 w-40 rounded-full bg-teal-400/25 blur-xl"
                  style={{
                    transform: `scale(${1 + level * 0.45})`,
                    opacity: 0.2 + level * 0.55,
                    transition: "transform 140ms ease-out, opacity 140ms ease-out",
                  }}
                />
              )}
              {/* Real-time spectrum ring — radial bars dancing to the live audio */}
              {listening && <OrbVisualizer analyserRef={analyserRef} active={listening} />}
              {/* "thinking" ring — a conic sweep orbiting the mic */}
              {analyzing && (
                <span className="mic-analyzing-ring pointer-events-none absolute h-44 w-44 rounded-full" />
              )}
              <button
                onClick={listening ? stopListening : startListening}
                disabled={micStatus === "loading"}
                title={listening ? "Tap to stop listening" : "Tap to start listening"}
                className={[
                  "mic-orb relative grid h-36 w-36 place-items-center rounded-full border-2 shadow-xl transition-all duration-500 disabled:cursor-not-allowed disabled:opacity-60",
                  // `mic-breathe` animates transform, so it must yield to the
                  // "heard" scale pop — they can't be applied together.
                  heard ? "scale-110" : listening ? "mic-breathe" : "mic-idle-float",
                  listening
                    ? "mic-orb-listening border-teal-300/70 text-teal-100"
                    : "border-teal-400/50 text-teal-200 hover:border-teal-300/80",
                ].join(" ")}
              >
                <span className="text-6xl leading-none transition-transform duration-300">
                  {analyzing ? "🧠" : listening ? "👂" : "🎙️"}
                </span>
              </button>
            </div>

            <div className="text-center">
              <p className="text-xl font-bold text-slate-100">
                {micStatus === "loading"
                  ? "Starting mic…"
                  : analyzing
                    ? "Identifying the sound…"
                    : heard
                      ? "Heard something…"
                      : listening
                        ? "Listening…"
                        : "Tap to Listen"}
              </p>
              <p className="mt-1 text-sm text-slate-400">
                {micStatus === "loading"
                  ? "allow microphone access"
                  : analyzing
                    ? "Alexa is reasoning about what it heard"
                    : heard
                      ? "capturing the sound…"
                      : listening
                        ? "Play or make a household sound · tap the orb to stop"
                        : "Play a real sound — or simulate one from the palette at the bottom"}
              </p>
            </div>
          </div>

          {/* The interpretation appears here as a message, right under the orb.
              Keyed on the result id so a fresh sound re-plays the reveal. */}
          {current && (
            <div
              key={current._id}
              className={["pp-rise mx-auto mt-8 w-full max-w-3xl rounded-2xl border bg-slate-950/40 p-5 shadow-lg", SEV[current.severity]?.ring || "border-slate-700/60"].join(" ")}
            >
              <div className="flex items-start gap-4">
                <span className="grid h-14 w-14 shrink-0 place-items-center rounded-2xl bg-slate-900/60 text-4xl leading-none">{current.emoji}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-xl font-bold text-slate-100">{current.detected_raw || current.label}</h2>
                    {current.flagged && <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-bold uppercase text-amber-200">⚠ flagged</span>}
                    <span className={["rounded px-1.5 py-0.5 text-[10px] font-bold uppercase", SEV[current.severity]?.badge].join(" ")}>{current.severity}</span>
                    {current.timing !== "new" && <span className={["rounded px-1.5 py-0.5 text-[10px] font-semibold", TIMING[current.timing]?.cls].join(" ")}>{TIMING[current.timing]?.label}</span>}
                    {current.llm_powered && <span className="rounded bg-cyan-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-cyan-300">🎧 heard by Alexa</span>}
                    {current.narration_llm && !current.llm_powered && <span className="rounded bg-violet-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-violet-300">✨ phrased by LLM</span>}
                  </div>
                  {/* The spoken line — the home's voice. Given a quote treatment so
                      it reads as the primary, "Alexa is speaking" response. */}
                  <div className="mt-2.5 flex items-start gap-2 rounded-xl border border-slate-700/50 bg-slate-900/50 px-3.5 py-2.5">
                    <span className="mt-0.5 text-base">🔊</span>
                    <p className="flex-1 text-base font-medium leading-relaxed text-slate-100">
                      {current.narration || current.prompt}
                    </p>
                  </div>
                  {current.sense_reason && (
                    <p className="mt-2 rounded-md bg-amber-500/10 px-2.5 py-1.5 text-sm text-amber-200/90">
                      🧠 Why flagged: {current.sense_reason}
                    </p>
                  )}
                  {(current.likely_activity || current.routine_note) && (
                    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-slate-400">
                      {current.likely_activity && <span>🏠 {current.likely_activity}</span>}
                      {current.routine_note && <span>🕒 {current.routine_note}</span>}
                    </div>
                  )}
                  {typeof current.confidence === "number" && current.confidence > 0 && (
                    <div className="mt-2.5 flex items-center gap-2 text-xs text-slate-500">
                      <span className="uppercase tracking-wide">confidence</span>
                      <div className="h-1.5 w-28 overflow-hidden rounded-full bg-slate-800">
                        <div
                          className="pp-grow-bar h-full rounded-full bg-gradient-to-r from-teal-500 to-cyan-400"
                          style={{ width: `${Math.round(current.confidence * 100)}%` }}
                        />
                      </div>
                      <span className="font-semibold text-teal-300">{Math.round(current.confidence * 100)}%</span>
                    </div>
                  )}
                  {current.suggested_action && !current._done && (
                    <div className="mt-3 flex items-center gap-2">
                      <button onClick={() => confirmAction(current)}
                        className="rounded-lg border border-emerald-400/60 bg-emerald-500/15 px-4 py-2 text-sm font-bold text-emerald-200 transition hover:bg-emerald-500/25">
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
                  <p className="text-sm text-slate-500">Nothing yet — listen for a real sound, or trigger one from the palette at the bottom of the page.</p>
                ) : (
                  <ul className="flex flex-col gap-1.5">
                    {feed.slice(1).map((it) => (
                      <li key={it._id} className={["pp-slide-in flex items-center gap-2 rounded-lg px-3 py-2", it.flagged ? "bg-amber-500/10 ring-1 ring-amber-500/30" : "bg-slate-950/40"].join(" ")}>
                        <span className={["h-2 w-2 shrink-0 rounded-full", SEV[it.severity]?.dot].join(" ")} />
                        <span className="text-base">{it.emoji}</span>
                        <span className="shrink-0 text-sm text-slate-200">{it.detected_raw || it.label}</span>
                        {it.flagged && <span className="text-xs text-amber-300">⚠</span>}
                        <span className="ml-auto min-w-0 truncate text-xs text-slate-500">{it.narration || it.prompt}</span>
                        {it._at && (
                          <span className="shrink-0 text-[10px] font-medium tabular-nums text-slate-600">
                            {timeAgo(it._at)}
                          </span>
                        )}
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
                  <>
                    <p className="mb-2 text-xs text-slate-500">
                      Learned from ~30 days of listening. These let the home tell an
                      <span className="text-emerald-300"> expected</span> sound from an
                      <span className="text-amber-300"> unusual</span> one.
                    </p>
                    <RoutineTimeline routines={routines} />
                    <ul className="grid gap-1.5 sm:grid-cols-2">
                      {routines.map((r) => (
                        <li key={r.sound} className="flex items-center gap-2.5 rounded-lg bg-slate-950/40 px-3 py-2 text-sm text-slate-300">
                          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-slate-900/60 text-base">{r.emoji}</span>
                          <div className="min-w-0 flex-1 leading-tight">
                            <p className="truncate font-medium text-slate-200">{r.label}</p>
                            <p className="text-xs text-slate-500">
                              ~{r.usual_time} · ±{r.window_minutes}m
                              {r.occurrences ? ` · seen ${r.occurrences}×` : ""}
                            </p>
                          </div>
                          <span
                            className="shrink-0 rounded-full bg-teal-500/15 px-2 py-0.5 text-xs font-semibold text-teal-300"
                            title="How consistent this routine's timing is"
                          >
                            {Math.round(r.confidence * 100)}%
                          </span>
                        </li>
                      ))}
                    </ul>
                  </>
                ),
            },
          ]}
        />

        {/* Trigger a sound — the simulate palette, parked at the very bottom as a
            developer/demo fallback. Collapsed until clicked. */}
        <section className="overflow-hidden rounded-2xl border border-slate-700/60 bg-slate-900/40">
          <button
            onClick={() => setSimOpen((o) => !o)}
            className="flex w-full items-center gap-2 px-4 py-3 text-left transition hover:bg-slate-800/40"
          >
            <span className="text-base">🎛️</span>
            <span className="text-sm font-bold uppercase tracking-wide text-slate-300">
              Trigger a sound
            </span>
            <span className="text-sm font-normal normal-case text-slate-500">· simulate without the mic</span>
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

// ── Live spectrum ring ───────────────────────────────────────────────────────
// A canvas ring of radial frequency bars around the orb, driven straight from
// the WebAudio AnalyserNode at 60fps — no React state per frame, so it stays
// perfectly smooth. Bars ease toward the live spectrum for a liquid feel.
function OrbVisualizer({ analyserRef, active }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const SIZE = 224;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = SIZE * dpr;
    canvas.height = SIZE * dpr;
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);

    const BARS = 56;
    const smoothed = new Float32Array(BARS);
    let data = null;
    let raf;

    const draw = () => {
      ctx.clearRect(0, 0, SIZE, SIZE);
      const analyser = analyserRef.current;
      if (active && analyser) {
        if (!data || data.length !== analyser.frequencyBinCount) {
          data = new Uint8Array(analyser.frequencyBinCount);
        }
        analyser.getByteFrequencyData(data);
      }
      const cx = SIZE / 2;
      const cy = SIZE / 2;
      const r0 = 80;
      let any = false;
      for (let i = 0; i < BARS; i++) {
        // Sample the lower ~70% of bins — where household sounds live.
        let v = 0;
        if (active && data) {
          const idx = Math.floor((i / BARS) * data.length * 0.7);
          v = data[idx] / 255;
        }
        smoothed[i] += (v - smoothed[i]) * 0.25; // ease toward live value
        if (smoothed[i] > 0.004) any = true;
        const len = 2 + smoothed[i] * 26;
        const ang = (i / BARS) * Math.PI * 2 - Math.PI / 2;
        ctx.strokeStyle = `rgba(45, 212, 191, ${0.22 + smoothed[i] * 0.78})`;
        ctx.lineWidth = 2.5;
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.moveTo(cx + Math.cos(ang) * r0, cy + Math.sin(ang) * r0);
        ctx.lineTo(cx + Math.cos(ang) * (r0 + len), cy + Math.sin(ang) * (r0 + len));
        ctx.stroke();
      }
      // Keep animating while active, or while bars are still decaying to rest.
      if (active || any) raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [active, analyserRef]);

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none absolute inset-0 h-full w-full"
      style={{ width: 224, height: 224 }}
      aria-hidden
    />
  );
}

// ── 24-hour routine timeline ────────────────────────────────────────────────
// The learned sound routines laid out on a day strip — at a glance you can see
// the home's acoustic rhythm and where "now" sits inside it. Markers alternate
// above/below the baseline so close routines don't collide.
function RoutineTimeline({ routines }) {
  const toMin = (hhmm) => {
    const [h, m] = String(hhmm).split(":").map(Number);
    return (h || 0) * 60 + (m || 0);
  };
  const now = new Date();
  const nowPct = ((now.getHours() * 60 + now.getMinutes()) / 1440) * 100;
  const sorted = [...routines].sort((a, b) => toMin(a.usual_time) - toMin(b.usual_time));

  return (
    <div className="mb-3 rounded-xl border border-slate-700/50 bg-slate-950/40 px-3 pb-1.5 pt-3">
      <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">
        The home's daily sound rhythm
      </p>
      <div className="relative mx-2 h-[72px]">
        {/* baseline + hour ticks */}
        <div className="absolute inset-x-0 top-1/2 h-px bg-slate-700/70" />
        {[0, 3, 6, 9, 12, 15, 18, 21, 24].map((h) => (
          <div
            key={h}
            className="absolute top-1/2 h-2 w-px -translate-y-1/2 bg-slate-600/80"
            style={{ left: `${(h / 24) * 100}%` }}
          />
        ))}
        {/* "now" marker */}
        <div
          className="tl-now absolute inset-y-0 w-0.5 rounded bg-[var(--pp-accent)]"
          style={{ left: `${nowPct}%` }}
          title={`Now · ${nowHHMM()}`}
        />
        {/* routine markers, alternating above/below the line */}
        {sorted.map((r, i) => (
          <span
            key={r.sound}
            title={`${r.label} · usually ~${r.usual_time} (±${r.window_minutes}m)`}
            className="absolute grid h-8 w-8 -translate-x-1/2 cursor-default place-items-center rounded-full border border-teal-500/40 bg-slate-900 text-base shadow-md transition-transform hover:z-10 hover:scale-125"
            style={{
              left: `${(toMin(r.usual_time) / 1440) * 100}%`,
              ...(i % 2 === 0 ? { top: 0 } : { bottom: 0 }),
            }}
          >
            {r.emoji}
          </span>
        ))}
      </div>
      <div className="mx-2 flex justify-between text-[10px] text-slate-500">
        <span>12 AM</span><span>6 AM</span><span>12 PM</span><span>6 PM</span><span>12 AM</span>
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
