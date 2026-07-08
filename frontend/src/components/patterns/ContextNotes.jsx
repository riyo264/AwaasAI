import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../patternsApi.js";
import { deviceIcon } from "./AdjustedRoutine.jsx";

// ════════════════════════════════════════════════════════════════════════════
//  OCCASION OVERLAY — tell the home about an occasion (voice or text), the LLM
//  re-plans the learned routines for that day.
//  ---------------------------------------------------------------------------
//  Groq Whisper transcribes; an LLM (which knows the Indian festival calendar +
//  the home's learned patterns) proposes a set of TEMPORARY, dated adjustments
//  that OVERLAY the routines without changing them. Preview → curate → apply.
//  Fully reversible; the base patterns are never touched.
// ════════════════════════════════════════════════════════════════════════════

const TYPE_META = {
  add: { icon: "➕", label: "add", cls: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30" },
  shift: { icon: "⏱", label: "shift", cls: "bg-sky-500/15 text-sky-300 ring-sky-500/30" },
  suppress: { icon: "⛔", label: "skip", cls: "bg-rose-500/15 text-rose-300 ring-rose-500/30" },
  adjust: { icon: "✨", label: "tweak", cls: "bg-violet-500/15 text-violet-300 ring-violet-500/30" },
};

const EXAMPLES = [
  { icon: "🪔", text: "Tomorrow is Diwali." },
  { icon: "🎉", text: "We have guests coming over tomorrow evening." },
  { icon: "✈️", text: "We're travelling for the next two days." },
  { icon: "🤒", text: "My mother is unwell today." },
];

// Staged "the AI is working" messages, cycled while the plan is being drafted.
const THINKING_STAGES = [
  "Reading your note…",
  "Scanning 30 days of learned routines…",
  "Consulting the festival calendar…",
  "Drafting temporary adjustments…",
  "Double-checking every change against real patterns…",
];

function occasionEmoji(occ = "") {
  const o = occ.toLowerCase();
  if (/diwali|deepav/.test(o)) return "🪔";
  if (/holi/.test(o)) return "🎨";
  if (/navratri|durga|dussehra|dasara/.test(o)) return "🔱";
  if (/eid/.test(o)) return "🌙";
  if (/christmas|xmas/.test(o)) return "🎄";
  if (/pongal|sankranti|makar|lohri/.test(o)) return "🌾";
  if (/raksha|rakhi/.test(o)) return "🧵";
  if (/guest|visit|party|dinner/.test(o)) return "🎉";
  if (/travel|trip|away|vacation/.test(o)) return "✈️";
  if (/unwell|sick|ill|fever/.test(o)) return "🤒";
  return "📌";
}

function blobToBase64(blob) {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onloadend = () => res(String(r.result).split(",")[1]);
    r.onerror = rej;
    r.readAsDataURL(blob);
  });
}

// The animated "AI is thinking" card shown while the LLM drafts the plan.
function ThinkingCard() {
  const [stage, setStage] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setStage((s) => (s + 1) % THINKING_STAGES.length), 1400);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="pp-rise mt-4 overflow-hidden rounded-2xl border border-indigo-500/40 bg-indigo-500/[0.06]">
      <div className="flex items-center gap-3 px-4 py-3">
        {/* spinning halo */}
        <span className="relative grid h-10 w-10 shrink-0 place-items-center">
          <span
            className="pp-thinking-halo absolute inset-0 rounded-full"
            style={{
              background:
                "conic-gradient(from 0deg, transparent 0 300deg, #818cf8 330deg, transparent 360deg)",
              mask: "radial-gradient(farthest-side, transparent calc(100% - 3px), #000 0)",
              WebkitMask: "radial-gradient(farthest-side, transparent calc(100% - 3px), #000 0)",
            }}
          />
          <span className="text-lg">🧠</span>
        </span>
        <div className="min-w-0 leading-tight">
          <p className="text-sm font-bold text-indigo-100">Re-planning the day…</p>
          <p key={stage} className="pp-rise text-xs text-slate-400">{THINKING_STAGES[stage]}</p>
        </div>
      </div>
      {/* skeleton adjustment rows */}
      <div className="flex flex-col gap-2 px-4 pb-4">
        {[72, 88, 60].map((w, i) => (
          <div key={i} className="flex items-center gap-3">
            <span className="pp-skeleton h-8 w-8 shrink-0 rounded-lg" />
            <div className="flex-1">
              <span className="pp-skeleton block h-3 rounded" style={{ width: `${w}%` }} />
              <span className="pp-skeleton mt-1.5 block h-2.5 rounded" style={{ width: `${w - 25}%` }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ContextNotes({ householdId, onOverlayChange, refreshKey }) {
  const [text, setText] = useState("");
  const [plan, setPlan] = useState(null);
  const [include, setInclude] = useState({});
  const [active, setActive] = useState([]);
  const [busy, setBusy] = useState(false);
  const [applying, setApplying] = useState(false);
  const [recording, setRecording] = useState(false);
  const [note, setNote] = useState(null);
  const mrRef = useRef(null);

  const loadActive = useCallback(async () => {
    try { setActive(await api.getAdjustments(householdId)); } catch { /* ignore */ }
  }, [householdId]);

  useEffect(() => { setPlan(null); setText(""); loadActive(); }, [householdId, loadActive, refreshKey]);

  const makePlan = useCallback(
    async ({ textArg, audioBase64 } = {}) => {
      setBusy(true);
      setNote(null);
      setPlan(null);
      try {
        const p = await api.contextNote(householdId, {
          text: textArg ?? text, audioBase64, audioFormat: "webm",
        });
        setPlan(p);
        setInclude(Object.fromEntries((p.adjustments || []).map((_, i) => [i, true])));
        if (p.transcript && !textArg) setText(p.transcript);
        if (!p.adjustments?.length) setNote(p.summary || "No adjustments proposed.");
      } catch (e) {
        setNote(`Couldn't plan: ${e.message}`);
      } finally {
        setBusy(false);
      }
    },
    [householdId, text],
  );

  const toggleRecord = useCallback(async () => {
    if (recording) { try { mrRef.current?.stop(); } catch { /* noop */ } return; }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      setNote(`Mic unavailable: ${e.message} — type instead.`);
      return;
    }
    const mr = new MediaRecorder(stream);
    mrRef.current = mr;
    const chunks = [];
    mr.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    mr.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      setRecording(false);
      const b64 = await blobToBase64(new Blob(chunks, { type: mr.mimeType || "audio/webm" }));
      makePlan({ audioBase64: b64 });
    };
    mr.start();
    setRecording(true);
    setNote("Listening… tap the mic again to stop.");
    setTimeout(() => { try { mr.state !== "inactive" && mr.stop(); } catch { /* noop */ } }, 8000);
  }, [recording, makePlan]);

  const apply = useCallback(async () => {
    if (!plan) return;
    const chosen = (plan.adjustments || []).filter((_, i) => include[i]);
    if (!chosen.length) { setNote("Select at least one adjustment."); return; }
    setApplying(true);
    try {
      await api.applyContextPlan(householdId, { ...plan, adjustments: chosen });
      setPlan(null);
      setText("");
      setNote("Applied — watch the routine re-arrange on the right.");
      loadActive();
      onOverlayChange?.();
    } catch (e) {
      setNote(`Apply failed: ${e.message}`);
    } finally {
      setApplying(false);
    }
  }, [plan, include, householdId, loadActive, onOverlayChange]);

  const removeAdj = useCallback(
    async (id) => {
      try { await api.deleteAdjustment(householdId, id); loadActive(); onOverlayChange?.(); } catch { /* ignore */ }
    },
    [householdId, loadActive, onOverlayChange],
  );

  const grouped = useMemo(() => {
    const g = {};
    active.forEach((a) => (g[`${a.occasion || "note"}||${a.occasion_date || ""}`] ||= []).push(a));
    return g;
  }, [active]);

  const chosenCount = useMemo(
    () => (plan?.adjustments || []).filter((_, i) => include[i]).length,
    [plan, include],
  );

  return (
    <section className="flex h-full flex-col overflow-hidden rounded-2xl border border-indigo-500/40 bg-slate-900/50 shadow-lg shadow-indigo-900/10">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3 bg-gradient-to-r from-indigo-600/25 to-violet-600/10 px-4 py-3.5">
        <span className="grid h-11 w-11 place-items-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-xl shadow">🗣️</span>
        <div className="leading-tight">
          <h2 className="text-base font-bold text-slate-100">Occasion Overlay</h2>
          <p className="text-xs text-slate-400">
            Tell the home about a festival, guests, travel… the AI re-plans the day —{" "}
            <span className="text-indigo-300">reversible</span>, never overwrites
          </p>
        </div>
        <span className="ml-auto rounded-full border border-indigo-400/40 bg-indigo-500/15 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-indigo-300">
          ✦ LLM-planned
        </span>
      </div>

      <div className="flex flex-1 flex-col p-4">
        {/* Input row — mic-forward */}
        <div className="flex items-stretch gap-2">
          <div className="flex flex-1 items-center gap-2 rounded-xl border border-slate-700 bg-slate-800/70 px-3 focus-within:border-indigo-500">
            <span className="text-slate-500">💬</span>
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && text.trim() && !busy && makePlan()}
              placeholder="e.g. Tomorrow is Diwali"
              className="w-full bg-transparent py-3 text-sm text-slate-100 outline-none placeholder:text-slate-500"
            />
          </div>
          <button onClick={toggleRecord} title={recording ? "Stop" : "Speak"}
            className={["grid h-12 w-12 shrink-0 place-items-center rounded-xl text-lg transition",
              recording ? "bg-red-500/25 text-red-200 ring-2 ring-red-500/60 animate-pulse"
                : "bg-slate-800/70 text-slate-300 ring-1 ring-slate-700 hover:bg-slate-700"].join(" ")}>
            {recording ? "■" : "🎙️"}
          </button>
          <button onClick={() => makePlan()} disabled={busy || !text.trim()}
            className="rounded-xl bg-indigo-500/90 px-5 text-sm font-bold text-white transition hover:bg-indigo-500 disabled:opacity-40">
            {busy ? "…" : "✦ Plan"}
          </button>
        </div>

        {/* Example chips */}
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          <span className="self-center text-[10px] text-slate-600">Try:</span>
          {EXAMPLES.map((ex) => (
            <button key={ex.text} onClick={() => { setText(ex.text); makePlan({ textArg: ex.text }); }}
              disabled={busy}
              className="rounded-full border border-slate-700 bg-slate-800/50 px-2.5 py-1 text-[11px] text-slate-300 transition hover:border-indigo-500/50 hover:text-white disabled:opacity-40">
              {ex.icon} {ex.text.replace(/\.$/, "")}
            </button>
          ))}
        </div>
        {note && <p className="pp-rise mt-2 text-xs text-slate-400">{note}</p>}

        {/* AI thinking state */}
        {busy && <ThinkingCard />}

        {/* Proposed plan — preview + curate */}
        {!busy && plan && plan.adjustments?.length > 0 && (
          <div className="pp-rise mt-4 rounded-2xl border border-indigo-500/40 bg-indigo-500/[0.06] p-3.5">
            <div className="mb-2.5 flex flex-wrap items-center gap-2.5">
              <span className="grid h-9 w-9 place-items-center rounded-xl bg-indigo-500/20 text-lg">{occasionEmoji(plan.occasion)}</span>
              <div className="min-w-0 flex-1 leading-tight">
                <p className="text-sm font-bold text-indigo-100">
                  {plan.occasion || "Occasion"}{" "}
                  <span className="font-mono text-[10px] font-normal text-slate-400">· {plan.occasion_date}</span>
                </p>
                <p className="text-xs text-slate-400">{plan.summary}</p>
              </div>
              <span className="rounded-full bg-slate-800 px-2.5 py-1 text-[10px] font-semibold text-slate-300">
                {plan.adjustments.length} proposed · tap to keep/drop
              </span>
            </div>
            <ul className="flex flex-col gap-2">
              {plan.adjustments.map((a, i) => {
                const tm = TYPE_META[a.type] || TYPE_META.adjust;
                const on = !!include[i];
                return (
                  <li key={i}
                    onClick={() => setInclude((p) => ({ ...p, [i]: !p[i] }))}
                    style={{ animationDelay: `${i * 60}ms` }}
                    className={["pp-rise flex cursor-pointer items-start gap-2.5 rounded-xl border px-3 py-2 transition",
                      on ? "border-slate-700 bg-slate-950/40 hover:border-indigo-500/40" : "border-transparent bg-slate-950/20 opacity-40"].join(" ")}>
                    <span className={["mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-md text-[11px] transition", on ? "bg-indigo-500 text-white" : "bg-slate-700 text-transparent"].join(" ")}>✓</span>
                    <span className="mt-0.5 text-base">{deviceIcon(a.device, a.description)}</span>
                    <div className="min-w-0 flex-1">
                      <p className="text-[13px] leading-snug text-slate-100">
                        <span className={["mr-1.5 rounded px-1.5 py-0.5 text-[9px] font-bold uppercase ring-1", tm.cls].join(" ")}>{tm.icon} {tm.label}</span>
                        {a.description}
                        {a.new_time && <span className="ml-1.5 rounded bg-sky-500/15 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-sky-300">@{a.new_time}</span>}
                      </p>
                      {a.reason && <p className="mt-0.5 text-[11px] italic leading-snug text-slate-500">↳ {a.reason}</p>}
                    </div>
                  </li>
                );
              })}
            </ul>
            <div className="mt-3 flex items-center gap-2">
              <button onClick={apply} disabled={applying || !chosenCount}
                className="rounded-lg bg-emerald-500/90 px-4 py-2 text-sm font-bold text-white transition hover:bg-emerald-500 disabled:opacity-40">
                {applying ? "Applying…" : `✓ Apply ${chosenCount} to the home`}
              </button>
              <button onClick={() => setPlan(null)}
                className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-400 hover:text-slate-200">Dismiss</button>
              {plan.llm_powered === false && <span className="text-[10px] text-amber-400">planner offline — try again</span>}
            </div>
          </div>
        )}

        {/* Active overlay */}
        {active.length > 0 && (
          <div className="mt-4">
            <p className="mb-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-500">Active occasion overlay</p>
            <div className="flex flex-col gap-2">
              {Object.entries(grouped).map(([head, items]) => {
                const [occ, date] = head.split("||");
                return (
                  <div key={head} className="rounded-xl border border-slate-800 bg-slate-950/40 p-2.5">
                    <p className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-indigo-300">
                      <span>{occasionEmoji(occ)}</span> {occ}{" "}
                      <span className="font-mono text-[9px] font-normal text-slate-500">{date}</span>
                    </p>
                    <ul className="flex flex-col gap-1">
                      {items.map((a) => {
                        const tm = TYPE_META[a.type] || TYPE_META.adjust;
                        return (
                          <li key={a.id} className="flex items-center gap-2 px-1">
                            <span className={["shrink-0 rounded px-1 py-0.5 text-[9px] font-bold uppercase ring-1", tm.cls].join(" ")}>{tm.icon}</span>
                            <span className="flex-1 truncate text-xs text-slate-300">{a.description}</span>
                            <button onClick={() => removeAdj(a.id)} title="Remove" className="text-slate-600 transition hover:text-red-400">✕</button>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
