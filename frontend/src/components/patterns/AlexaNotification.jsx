import { useEffect, useRef, useState } from "react";

// Pick a pleasant English voice for the "Alexa" persona, preferring a female
// voice when one is available. Voices load asynchronously in some browsers.
function pickVoice() {
  const voices = window.speechSynthesis?.getVoices?.() || [];
  if (!voices.length) return null;
  const en = voices.filter((v) => /^en(-|_|$)/i.test(v.lang));
  const pool = en.length ? en : voices;
  const preferred = pool.find((v) =>
    /samantha|female|zira|google us english|aria|jenny|alexa/i.test(v.name),
  );
  return preferred || pool[0];
}

// ───────────────────────────────────────────────────────────────────────────
// A single Alexa notification card (presentational). All the voice / TTS
// orchestration lives in the parent stack — this card only reflects whether it
// is the one currently being spoken (`isSpeaking`) and renders the controls.
// ───────────────────────────────────────────────────────────────────────────
function NotificationCard({
  notification,
  isSpeaking,
  muted,
  ttsSupported,
  onToggleMute,
  onReplay,
  onDismiss,
}) {
  const [shown, setShown] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [expanded, setExpanded] = useState(false);

  // Slide in on mount.
  useEffect(() => {
    const t = setTimeout(() => setShown(true), 20);
    return () => clearTimeout(t);
  }, []);

  const dismiss = () => {
    setLeaving(true);
    setTimeout(() => onDismiss?.(notification.id), 280);
  };

  const alert = notification.tone === "alert";

  return (
    <div
      className={[
        "w-[360px] max-w-[calc(100vw-2.5rem)] transition-all duration-300 ease-out",
        shown && !leaving
          ? "translate-x-0 opacity-100"
          : "translate-x-6 opacity-0",
      ].join(" ")}
      role="status"
      aria-live="polite"
    >
      <div
        className={[
          "relative overflow-hidden rounded-2xl border bg-slate-900/95 p-4 shadow-2xl backdrop-blur",
          isSpeaking
            ? "ring-2 ring-offset-1 ring-offset-slate-950 " +
              (alert
                ? "border-red-400/70 ring-red-400/70"
                : "border-sky-400/70 ring-sky-400/70")
            : alert
              ? "border-red-500/50"
              : "border-sky-500/40",
        ].join(" ")}
      >
        {/* Glow accent bar */}
        <span
          className={[
            "absolute inset-x-0 top-0 h-0.5",
            alert
              ? "bg-gradient-to-r from-red-500 via-orange-400 to-red-500"
              : "bg-gradient-to-r from-sky-400 via-cyan-300 to-indigo-400",
          ].join(" ")}
        />

        <div className="flex items-start gap-3">
          {/* Alexa ring / speaking pulse */}
          <div className="relative mt-0.5 shrink-0">
            <span
              className={[
                "block h-10 w-10 rounded-full ring-2",
                alert ? "ring-red-400/70" : "ring-sky-400/70",
              ].join(" ")}
              style={{
                background: alert
                  ? "radial-gradient(circle at 50% 50%, #fca5a5 0%, #0ea5e9 0%, #0f172a 70%)"
                  : "radial-gradient(circle at 50% 50%, #67e8f9 0%, #0ea5e9 45%, #0f172a 75%)",
              }}
            />
            {/* speaking pulse — only on the card being read aloud */}
            {isSpeaking && (
              <span className="alexa-ping absolute inset-0 rounded-full" />
            )}
          </div>

          <div className="min-w-0 flex-1">
            <div className="mb-0.5 flex items-center gap-2">
              <span className="text-xs font-bold tracking-wide text-slate-200">
                Alexa
              </span>
              <span
                className={[
                  "rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide ring-1",
                  notification.llmPowered
                    ? "bg-emerald-500/15 text-emerald-300 ring-emerald-500/40"
                    : "bg-slate-700/50 text-slate-400 ring-slate-600/50",
                ].join(" ")}
                title={
                  notification.llmPowered
                    ? "Phrased live by the Groq LLM"
                    : "Deterministic fallback (set GROQ_API_KEY for LLM phrasing)"
                }
              >
                {notification.llmPowered ? "✦ LLM" : "fallback"}
              </span>

              {isSpeaking && !muted && (
                <span className="flex items-center gap-0.5" title="Speaking…">
                  <span className="tts-bar h-2 w-0.5 rounded bg-sky-400" />
                  <span className="tts-bar tts-bar-2 h-3 w-0.5 rounded bg-sky-400" />
                  <span className="tts-bar tts-bar-3 h-2 w-0.5 rounded bg-sky-400" />
                </span>
              )}

              {ttsSupported && (
                <div className="ml-auto flex items-center gap-1">
                  {!muted && (
                    <button
                      onClick={() => onReplay?.(notification)}
                      title="Replay voice"
                      className="rounded p-0.5 text-slate-500 transition hover:bg-slate-800 hover:text-sky-300"
                      aria-label="Replay voice"
                    >
                      ⟲
                    </button>
                  )}
                  <button
                    onClick={onToggleMute}
                    title={muted ? "Unmute voice" : "Mute voice"}
                    className={[
                      "rounded p-0.5 transition hover:bg-slate-800",
                      muted
                        ? "text-slate-500 hover:text-slate-300"
                        : "text-sky-300",
                    ].join(" ")}
                    aria-label={muted ? "Unmute voice" : "Mute voice"}
                  >
                    {muted ? "🔇" : "🔊"}
                  </button>
                </div>
              )}
            </div>
            <p className="text-sm leading-relaxed text-slate-100">
              {notification.text}
            </p>

            {/* See more — expandable reasoning from the LLM */}
            {notification.explanation && (
              <>
                <button
                  onClick={() => setExpanded((v) => !v)}
                  className={[
                    "mt-2 inline-flex items-center gap-1 text-[11px] font-semibold transition",
                    alert
                      ? "text-red-300 hover:text-red-200"
                      : "text-sky-300 hover:text-sky-200",
                  ].join(" ")}
                  aria-expanded={expanded}
                >
                  {expanded ? "Hide details" : "See more"}
                  <span
                    className={[
                      "transition-transform",
                      expanded ? "rotate-180" : "",
                    ].join(" ")}
                  >
                    ▾
                  </span>
                </button>

                <div
                  className={[
                    "grid transition-all duration-300 ease-out",
                    expanded
                      ? "mt-2 grid-rows-[1fr] opacity-100"
                      : "grid-rows-[0fr] opacity-0",
                  ].join(" ")}
                >
                  <div className="overflow-hidden">
                    <div className="rounded-lg border border-slate-700/60 bg-slate-950/60 p-2.5">
                      <p className="mb-1 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                        <span>🧠</span> Why I think this
                      </p>
                      <p className="text-[12px] leading-relaxed text-slate-300">
                        {notification.explanation}
                      </p>
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>

          <button
            onClick={dismiss}
            className="shrink-0 rounded-md p-1 text-slate-500 transition hover:bg-slate-800 hover:text-slate-200"
            aria-label="Dismiss"
          >
            ✕
          </button>
        </div>
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────────────
// Stack of Alexa notifications — like a phone's notification tray. All issues
// appear at once, stacked vertically (most-severe at the top), and a single
// narrator reads them out ONE BY ONE in order, highlighting the card it is
// currently speaking. At most `maxVisible` cards are shown; any overflow is
// summarised with a "+N more" chip.
//
// Props:
//   notifications: [{ id, text, explanation, llmPowered, tone }] — ordered
//   onDismiss: (id) => void  — remove a single notification
//   onDismissAll: () => void — clear the whole stack
//   maxVisible: number (default 4)
// ───────────────────────────────────────────────────────────────────────────
export default function AlexaNotification({
  notifications = [],
  onDismiss,
  onDismissAll,
  maxVisible = 4,
}) {
  const ttsSupported =
    typeof window !== "undefined" && "speechSynthesis" in window;

  const [muted, setMuted] = useState(() => {
    try {
      return localStorage.getItem("alexa_tts_muted") === "1";
    } catch {
      return false;
    }
  });
  const [speakingId, setSpeakingId] = useState(null);
  // Ids already read aloud (so the sequence never repeats a line) + a tick to
  // re-trigger the narrator after each utterance finishes.
  const spokenIds = useRef(new Set());
  const knownIds = useRef(new Set());
  const [tick, setTick] = useState(0);

  // Persist mute preference.
  useEffect(() => {
    try {
      localStorage.setItem("alexa_tts_muted", muted ? "1" : "0");
    } catch {
      /* ignore storage failures */
    }
  }, [muted]);

  const idsKey = notifications.map((n) => n.id).join("|");

  // When a genuinely NEW batch arrives (new ids appear — e.g. a fresh "Go"),
  // cancel any in-progress speech so the new stack starts narrating from the
  // top. Removing a single card does NOT reset the sequence.
  useEffect(() => {
    const hasNew = notifications.some((n) => !knownIds.current.has(n.id));
    notifications.forEach((n) => knownIds.current.add(n.id));
    if (hasNew && ttsSupported) {
      window.speechSynthesis.cancel();
      setSpeakingId(null);
      setTick((t) => t + 1);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idsKey]);

  // Sequential narrator: speak the first not-yet-spoken notification, then on
  // completion advance to the next. Honours mute and stops cleanly.
  useEffect(() => {
    if (!ttsSupported) return;
    if (muted) {
      window.speechSynthesis.cancel();
      setSpeakingId(null);
      return;
    }
    if (window.speechSynthesis.speaking) return;
    const next = notifications.find((n) => !spokenIds.current.has(n.id));
    if (!next) return;

    const synth = window.speechSynthesis;
    const utter = new SpeechSynthesisUtterance(next.text);
    utter.rate = 1.02;
    utter.pitch = 1.0;
    const voice = pickVoice();
    if (voice) utter.voice = voice;
    utter.onstart = () => setSpeakingId(next.id);
    const finish = () => {
      spokenIds.current.add(next.id);
      setSpeakingId(null);
      setTick((t) => t + 1); // re-arm for the next line
    };
    utter.onend = finish;
    utter.onerror = finish;
    // Some browsers need a tick after cancel() before speak() takes effect.
    const t = setTimeout(() => synth.speak(utter), 80);
    return () => clearTimeout(t);
  }, [notifications, muted, ttsSupported, tick]);

  // Stop speech if the stack empties or unmounts. Also reset both id-trackers so
  // re-appearing concerns (e.g. SOS toggled off then on again) are treated as
  // new and get spoken aloud rather than silently skipped.
  useEffect(() => {
    if (!ttsSupported) return;
    if (notifications.length === 0) {
      window.speechSynthesis.cancel();
      spokenIds.current.clear();
      knownIds.current.clear();
    }
    return () => window.speechSynthesis.cancel();
  }, [notifications.length, ttsSupported]);

  const toggleMute = () =>
    setMuted((m) => {
      const next = !m;
      if (next && ttsSupported) window.speechSynthesis.cancel();
      return next;
    });

  // Replay a single line on demand (interrupts the sequence, then resumes).
  const replay = (n) => {
    if (!ttsSupported || muted) return;
    const synth = window.speechSynthesis;
    synth.cancel();
    const utter = new SpeechSynthesisUtterance(n.text);
    utter.rate = 1.02;
    const voice = pickVoice();
    if (voice) utter.voice = voice;
    utter.onstart = () => setSpeakingId(n.id);
    const done = () => {
      setSpeakingId(null);
      setTick((t) => t + 1);
    };
    utter.onend = done;
    utter.onerror = done;
    setTimeout(() => synth.speak(utter), 80);
  };

  if (!notifications.length) return null;

  const visible = notifications.slice(0, maxVisible);
  const overflow = notifications.length - visible.length;

  return (
    <div className="fixed bottom-5 right-5 z-50 flex max-h-[calc(100vh-2.5rem)] flex-col items-end gap-2 overflow-visible">
      {/* Stack header — count + clear all */}
      {notifications.length > 1 && (
        <div className="flex items-center gap-2 rounded-full border border-slate-700/60 bg-slate-900/90 px-3 py-1 shadow-lg backdrop-blur">
          <span className="text-[11px] font-semibold text-slate-300">
            🔔 {notifications.length} notifications
          </span>
          <button
            onClick={onDismissAll}
            className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 transition hover:text-slate-200"
          >
            Clear all
          </button>
        </div>
      )}

      {visible.map((n) => (
        <NotificationCard
          key={n.id}
          notification={n}
          isSpeaking={speakingId === n.id}
          muted={muted}
          ttsSupported={ttsSupported}
          onToggleMute={toggleMute}
          onReplay={replay}
          onDismiss={onDismiss}
        />
      ))}

      {overflow > 0 && (
        <div className="rounded-full border border-slate-700/60 bg-slate-900/80 px-3 py-1 text-[10px] font-semibold text-slate-400 shadow">
          +{overflow} more notification{overflow > 1 ? "s" : ""}
        </div>
      )}
    </div>
  );
}
