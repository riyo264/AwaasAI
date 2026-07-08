import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../patternsApi.js";

// ════════════════════════════════════════════════════════════════════════════
//  ADAPTED ROUTINE — the learned day, re-arranged for the occasion
//  ---------------------------------------------------------------------------
//  A vertical day-timeline (grouped Morning → Night). When an occasion overlay
//  is applied, affected lines light up in place — shifted ⏱ / added ➕ /
//  skipped ⛔ / tweaked ✨ — each with its reason. The visible payoff of the
//  voice/text context feature.
// ════════════════════════════════════════════════════════════════════════════

const STATUS = {
  normal: { badge: "", chip: "", ring: "border-slate-800", dot: "bg-slate-600", text: "text-slate-200" },
  shifted: { badge: "⏱ shifted", chip: "bg-sky-500/20 text-sky-200", ring: "border-sky-500/50 bg-sky-500/[0.06]", dot: "bg-sky-400", text: "text-sky-100" },
  added: { badge: "➕ added", chip: "bg-emerald-500/20 text-emerald-200", ring: "border-emerald-500/50 bg-emerald-500/[0.06]", dot: "bg-emerald-400", text: "text-emerald-100" },
  suppressed: { badge: "⛔ skipped", chip: "bg-rose-500/20 text-rose-200", ring: "border-rose-500/40 bg-rose-500/[0.05]", dot: "bg-rose-500", text: "text-rose-200/70 line-through" },
  tweaked: { badge: "✨ tweaked", chip: "bg-violet-500/20 text-violet-200", ring: "border-violet-500/50 bg-violet-500/[0.06]", dot: "bg-violet-400", text: "text-violet-100" },
};

const CHANGE_ORDER = ["shifted", "added", "suppressed", "tweaked"];
const CHANGE_LABEL = { shifted: "shifted", added: "added", suppressed: "skipped", tweaked: "tweaked" };

const GROUPS = [
  { key: "morning", label: "Morning", icon: "🌅", test: (h) => h >= 5 && h < 12 },
  { key: "afternoon", label: "Afternoon", icon: "☀️", test: (h) => h >= 12 && h < 17 },
  { key: "evening", label: "Evening", icon: "🌆", test: (h) => h >= 17 && h < 21 },
  { key: "night", label: "Night", icon: "🌙", test: (h) => h >= 21 || h < 5 },
];

function hourOf(t) {
  if (!t || !t.includes(":")) return null;
  const h = parseInt(t.split(":")[0], 10);
  return Number.isNaN(h) ? null : h;
}

export function deviceIcon(id = "", label = "") {
  const d = `${id} ${label}`.toLowerCase();
  if (/(pooja|lamp|diya)/.test(d)) return "🪔";
  if (/(bhajan|speaker|music|radio)/.test(d)) return "🔊";
  if (/bell/.test(d)) return "🔔";
  if (/(gas|stove|kadai)/.test(d)) return "🔥";
  if (/(kettle|chai|tea)/.test(d)) return "🫖";
  if (/\bac\b|air.?con/.test(d)) return "❄️";
  if (/fan/.test(d)) return "🌀";
  if (/(decor|light|lamp)/.test(d)) return "💡";
  if (/(motor|borewell|water|tap|ro\b)/.test(d)) return "🛢️";
  if (/door/.test(d)) return "🚪";
  if (/\btv\b|televis/.test(d)) return "📺";
  if (/medic|pill/.test(d)) return "💊";
  if (/(activity|presence|arrive|leave|movement)/.test(d)) return "🚶";
  if (/inverter/.test(d)) return "🔋";
  if (/(clothes|laundry)/.test(d)) return "🧺";
  if (/(milk|delivery|vendor)/.test(d)) return "🥛";
  if (/(departure|sequence|routine)/.test(d)) return "🔗";
  if (/vacuum|clean/.test(d)) return "🧹";
  return "•";
}

export default function AdjustedRoutine({ householdId, refreshKey, onOverlayChange }) {
  const [sched, setSched] = useState(null);
  const [busy, setBusy] = useState(false);
  const [onlyChanges, setOnlyChanges] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const s = await api.effectiveSchedule(householdId);
      setSched(s);
      setOnlyChanges((s?.adjusted_count || 0) > 0);
    } catch {
      setSched(null);
    } finally {
      setBusy(false);
    }
  }, [householdId]);

  useEffect(() => { load(); }, [load, refreshKey]);

  const reset = useCallback(async () => {
    try {
      await api.clearAdjustments(householdId);
      if (onOverlayChange) onOverlayChange();
      else load();
    } catch { /* ignore */ }
  }, [householdId, load, onOverlayChange]);

  const adapted = (sched?.adjusted_count || 0) > 0;

  // Counts per change type for the summary strip.
  const counts = useMemo(() => {
    const c = {};
    (sched?.entries || []).forEach((e) => { if (e.status !== "normal") c[e.status] = (c[e.status] || 0) + 1; });
    return c;
  }, [sched]);

  // Group visible entries by time-of-day.
  const groups = useMemo(() => {
    const all = sched?.entries || [];
    const shown = onlyChanges ? all.filter((e) => e.status !== "normal") : all;
    const buckets = GROUPS.map((g) => ({ ...g, items: [] }));
    const anytime = { key: "anytime", label: "Anytime", icon: "🕘", items: [] };
    shown.forEach((e) => {
      const h = hourOf(e.time);
      if (h === null) { anytime.items.push(e); return; }
      (buckets.find((g) => g.test(h)) || anytime).items.push(e);
    });
    return [...buckets, anytime].filter((g) => g.items.length);
  }, [sched, onlyChanges]);

  return (
    <section className={["overflow-hidden rounded-2xl border bg-slate-900/50", adapted ? "border-indigo-500/50 shadow-lg shadow-indigo-900/20" : "border-slate-700/60"].join(" ")}>
      {/* Header */}
      <div className={["flex flex-wrap items-center gap-2 px-4 py-3", adapted ? "bg-gradient-to-r from-indigo-600/20 to-violet-600/10" : ""].join(" ")}>
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-amber-500 to-orange-600 text-base shadow">📅</span>
        <div className="leading-tight">
          <h2 className="text-sm font-bold text-slate-100">
            {adapted ? "The day, adapted" : "Today’s learned routine"}
          </h2>
          <p className="text-[10px] text-slate-400">
            {adapted
              ? <>Re-arranged for <span className="font-semibold text-indigo-300">{sched.occasions.join(" · ")}</span></>
              : "Deterministic schedule from your event logs — apply an occasion to see it adapt."}
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {adapted && (
            <>
              <button onClick={() => setOnlyChanges((v) => !v)}
                className="rounded-lg border border-slate-600/60 bg-slate-800/60 px-2 py-1 text-[10px] font-medium text-slate-300 hover:bg-slate-700">
                {onlyChanges ? "Show full day" : "Only changes"}
              </button>
              <button onClick={reset} title="Remove all occasion adjustments"
                className="rounded-lg border border-slate-600/60 bg-slate-800/60 px-2 py-1 text-[10px] font-medium text-slate-400 hover:text-rose-300 hover:border-rose-500/40">
                ↺ Reset
              </button>
            </>
          )}
        </div>
      </div>

      {/* Change-summary strip */}
      {adapted && (
        <div className="flex flex-wrap items-center gap-1.5 border-b border-slate-800 bg-slate-950/40 px-4 py-2">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{sched.adjusted_count} changes</span>
          {CHANGE_ORDER.filter((k) => counts[k]).map((k) => (
            <span key={k} className={["rounded-full px-2 py-0.5 text-[10px] font-bold", STATUS[k].chip].join(" ")}>
              {STATUS[k].badge.split(" ")[0]} {counts[k]} {CHANGE_LABEL[k]}
            </span>
          ))}
          <span className="ml-auto text-[10px] text-slate-500">on top of the learned routine · reversible</span>
        </div>
      )}

      <div className="p-3">
        {busy && !sched && (
          <div className="flex flex-col gap-2 p-2">
            {[82, 64, 90, 58, 74, 68].map((w, i) => (
              <div key={i} className="flex items-center gap-3">
                <span className="pp-skeleton h-3 w-12 shrink-0 rounded" />
                <span className="pp-skeleton h-7 w-7 shrink-0 rounded-lg" />
                <span className="pp-skeleton h-3 rounded" style={{ width: `${w}%` }} />
              </div>
            ))}
          </div>
        )}
        {sched && groups.length === 0 && (
          <p className="rounded-lg bg-slate-800/40 px-3 py-4 text-center text-[11px] text-slate-500">
            {adapted ? "No changed lines." : "No timed routines learned yet — hit Load Demo Data first."}
          </p>
        )}

        <div className="flex flex-col gap-3">
          {groups.map((g) => (
            <div key={g.key}>
              <div className="mb-1.5 flex items-center gap-1.5 px-1">
                <span className="text-xs">{g.icon}</span>
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{g.label}</span>
                <span className="h-px flex-1 bg-slate-800" />
                <span className="text-[9px] text-slate-600">{g.items.length}</span>
              </div>

              {/* Timeline rail */}
              <ul className="ml-1 flex flex-col gap-1 border-l border-slate-800 pl-3">
                {g.items.map((e, i) => {
                  const st = STATUS[e.status] || STATUS.normal;
                  const changed = e.status !== "normal";
                  return (
                    <li key={`${e.pattern_id || e.label}-${i}`} className={changed ? "pp-rise relative" : "relative"}>
                      {/* rail dot */}
                      <span className={["absolute -left-[17px] top-2.5 h-2 w-2 rounded-full ring-2 ring-slate-900", st.dot].join(" ")} />
                      <div className={["flex items-center gap-2 rounded-lg border px-2.5 py-2 transition", changed ? st.ring : "border-transparent hover:bg-slate-800/30"].join(" ")}>
                        {/* time */}
                        <span className="w-[76px] shrink-0 font-mono text-xs tabular-nums">
                          {e.status === "shifted" && e.old_time ? (
                            <><span className="text-slate-600 line-through">{e.old_time}</span> <span className="font-semibold text-sky-300">{e.time}</span></>
                          ) : (
                            <span className="text-slate-400">{e.time || "—"}</span>
                          )}
                        </span>
                        <span className="text-base">{deviceIcon(e.device, e.label)}</span>
                        <span className={["flex-1 truncate text-[13px]", st.text].join(" ")}>{e.label}</span>
                        {changed && (
                          <span className={["shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold", st.chip].join(" ")}>
                            {st.badge}
                          </span>
                        )}
                      </div>
                      {changed && e.reason && (
                        <p className="ml-[84px] mt-0.5 text-[11px] italic text-slate-500">↳ {e.reason}</p>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
