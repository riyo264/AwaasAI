import { useMemo, useState } from "react";
import { DEVICE_KIND } from "../../config/houseLayout.js";

const TABS = ["Context", "Patterns", "Events", "State"];

const CONTEXT_BADGE = {
  departure_anomaly: { label: "Departure Anomaly", color: "bg-red-500/20 text-red-300 ring-red-500/40" },
  duration_anomaly: { label: "Duration Anomaly", color: "bg-orange-500/20 text-orange-300 ring-orange-500/40" },
  routine_suggestion: { label: "Routine Suggestion", color: "bg-sky-500/20 text-sky-300 ring-sky-500/40" },
  normal: { label: "Normal", color: "bg-emerald-500/20 text-emerald-300 ring-emerald-500/40" },
};

const SEVERITY_STYLE = {
  high: "bg-red-500/20 text-red-300 ring-red-500/40",
  medium: "bg-orange-500/20 text-orange-300 ring-orange-500/40",
  low: "bg-amber-500/20 text-amber-200 ring-amber-500/40",
};

const PATTERN_META = {
  time_based: { label: "Time-based", icon: "🕒", color: "bg-sky-500/15 text-sky-300 ring-sky-500/40" },
  sequence: { label: "Sequence", icon: "🔗", color: "bg-violet-500/15 text-violet-300 ring-violet-500/40" },
  duration: { label: "Duration", icon: "⏱️", color: "bg-amber-500/15 text-amber-300 ring-amber-500/40" },
};

// Action → visual treatment for the event timeline.
const ACTION_STYLE = {
  ON: { cls: "bg-sky-500/20 text-sky-300", dot: "bg-sky-400" },
  OPEN: { cls: "bg-sky-500/20 text-sky-300", dot: "bg-sky-400" },
  ARRIVE: { cls: "bg-emerald-500/20 text-emerald-300", dot: "bg-emerald-400" },
  OFF: { cls: "bg-slate-600/40 text-slate-300", dot: "bg-slate-400" },
  CLOSE: { cls: "bg-slate-600/40 text-slate-300", dot: "bg-slate-400" },
  LEAVE: { cls: "bg-amber-500/20 text-amber-300", dot: "bg-amber-400" },
};

const TYPE_ICON = {
  fan: "🌀", light: "💡", ac: "❄️", tv: "📺", motor: "🛢️",
  door: "🚪", presence: "🚶", other: "🔌",
};

function deviceIcon(type) {
  return TYPE_ICON[type] || DEVICE_KIND[type]?.icon || "🔌";
}

export default function SidePanel({ context, patterns, state, events, loading }) {
  const [tab, setTab] = useState("Context");

  const counts = {
    Context: context?.anomalies?.length || 0,
    Patterns: patterns?.count ?? patterns?.patterns?.length ?? 0,
    Events: events?.length ?? 0,
    State: state?.active_devices?.length ?? 0,
  };

  return (
    <aside className="flex h-full flex-col rounded-2xl border border-slate-700/60 bg-slate-900/60 backdrop-blur">
      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-700/60 p-2">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={[
              "flex flex-1 items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-semibold transition",
              tab === t
                ? "bg-sky-500/20 text-sky-200"
                : "text-slate-400 hover:bg-slate-800",
            ].join(" ")}
          >
            {t}
            {counts[t] > 0 && (
              <span
                className={[
                  "rounded-full px-1.5 text-[10px] font-bold",
                  tab === t ? "bg-sky-400/30 text-sky-100" : "bg-slate-700/70 text-slate-300",
                ].join(" ")}
              >
                {counts[t]}
              </span>
            )}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {tab === "Context" && <ContextView context={context} loading={loading} />}
        {tab === "Patterns" && <PatternsView patterns={patterns} />}
        {tab === "Events" && <EventsView events={events} loading={loading} />}
        {tab === "State" && <StateView state={state} />}
      </div>
    </aside>
  );
}

/* ------------------------------------------------------------------ Context */

function ContextView({ context, loading }) {
  if (!context) {
    return <Empty text={loading ? "Generating context…" : "All normal. Paint the device states and hit ▶ Go to run a check."} />;
  }
  const badge = CONTEXT_BADGE[context.context_type] || CONTEXT_BADGE.normal;
  const people = Object.entries(context.people_home || {});
  const active = context.active_devices || [];

  return (
    <div className="space-y-4">
      {/* Headline classification card */}
      <div className="rounded-xl border border-slate-700/60 bg-linear-to-br from-slate-950/80 to-slate-900/40 p-3.5">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-[10px] uppercase tracking-wider text-slate-500">
            Context Classification
          </span>
          <span className="rounded bg-slate-800/70 px-1.5 py-0.5 text-[10px] font-medium text-slate-400">
            @ {context.current_time}
          </span>
        </div>
        <span className={`inline-block rounded-md px-2.5 py-1 text-xs font-bold ring-1 ${badge.color}`}>
          {badge.label}
        </span>
        <div className="mt-3 grid grid-cols-2 gap-2">
          <MiniStat label="People home" value={`${people.filter(([, v]) => v).length}/${people.length || "—"}`} />
          <MiniStat label="Active devices" value={active.length} />
          <MiniStat label="Anomalies" value={context.anomalies.length} tone={context.anomalies.length ? "warn" : "ok"} />
          <MiniStat label="Patterns matched" value={context.relevant_patterns.length} />
        </div>
      </div>

      {/* Anomaly cards */}
      <Section title={`Anomalies (${context.anomalies.length})`}>
        {context.anomalies.length === 0 ? (
          <p className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-2.5 text-xs text-emerald-300">
            ✓ Everything looks normal.
          </p>
        ) : (
          <ul className="space-y-2">
            {context.anomalies.map((a, i) => {
              const sev = SEVERITY_STYLE[a.severity] || SEVERITY_STYLE.medium;
              return (
                <li key={i} className="rounded-xl border border-red-500/40 bg-red-500/[0.07] p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-1.5 text-xs font-semibold capitalize text-red-200">
                      <span>⚠</span>
                      {a.type.replaceAll("_", " ")}
                    </span>
                    <span className={`rounded px-1.5 py-0.5 text-[9px] font-bold uppercase ring-1 ${sev}`}>
                      {a.severity}
                    </span>
                  </div>
                  {a.device && (
                    <div className="mt-1.5 inline-flex items-center gap-1 rounded-md bg-slate-900/60 px-2 py-0.5 text-[11px] font-medium text-slate-200">
                      <span>{deviceIcon(deviceTypeFromId(a.device))}</span>
                      {a.device}
                    </div>
                  )}
                  {a.detail && <p className="mt-1.5 text-[11px] leading-relaxed text-slate-400">{a.detail}</p>}
                  {a.related_pattern_id && (
                    <p className="mt-1.5 text-[10px] text-slate-500">
                      ↳ pattern <code className="text-slate-400">{a.related_pattern_id}</code>
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Section>

      {/* Relevant patterns */}
      <Section title={`Relevant Patterns (${context.relevant_patterns.length})`}>
        {context.relevant_patterns.length === 0 ? (
          <p className="text-[11px] text-slate-500">No patterns matched this moment.</p>
        ) : (
          <ul className="space-y-2">
            {context.relevant_patterns.map((p) => {
              const meta = PATTERN_META[p.pattern_type] || {};
              return (
                <li key={p.pattern_id} className="rounded-xl border border-slate-700/60 bg-slate-800/40 p-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-[11px] leading-snug text-slate-200">{p.description}</p>
                    <span className={`shrink-0 rounded px-1.5 py-0.5 text-[9px] font-semibold ring-1 ${meta.color || "bg-slate-700/50 text-slate-300"}`}>
                      {meta.icon} {meta.label || p.pattern_type}
                    </span>
                  </div>
                  {p.time && (
                    <div className="mt-1.5 inline-flex items-center gap-1 rounded-md bg-slate-900/60 px-2 py-0.5 text-[10px] font-medium text-sky-300">
                      🕒 {p.time}
                    </div>
                  )}
                  <ConfidenceBar value={p.confidence} />
                </li>
              );
            })}
          </ul>
        )}
      </Section>

      {/* Recent events tail */}
      {context.recent_events?.length > 0 && (
        <Section title={`Recent Events (${context.recent_events.length})`}>
          <ul className="space-y-1">
            {context.recent_events.map((e, i) => (
              <li key={i} className="flex items-center gap-2 rounded-lg bg-slate-800/30 px-2 py-1.5 text-[11px]">
                <span>{deviceIcon(deviceTypeFromId(e.device_id))}</span>
                <span className="flex-1 truncate text-slate-300">{e.device_id}</span>
                <ActionPill action={e.action} />
                <span className="text-[10px] text-slate-500">{shortTime(e.timestamp)}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* Raw JSON (Bedrock-ready payload) */}
      <Collapsible title="Bedrock-ready payload">
        <pre className="max-h-56 overflow-auto rounded-lg bg-slate-950/70 p-2 text-[10px] leading-relaxed text-slate-400">
          {JSON.stringify(context, null, 2)}
        </pre>
      </Collapsible>
    </div>
  );
}

/* ----------------------------------------------------------------- Patterns */

// A pattern's "owning" device(s). Time/duration patterns own a single device;
// a sequence touches several, so it surfaces under every device in its steps.
function patternDevices(p) {
  if (p.pattern_type === "sequence") {
    return Array.from(
      new Set((p.steps || []).map((s) => String(s).split(":")[0]).filter(Boolean)),
    );
  }
  return p.device ? [p.device] : [];
}

function typeCounts(items) {
  return items.reduce((acc, p) => {
    acc[p.pattern_type] = (acc[p.pattern_type] || 0) + 1;
    return acc;
  }, {});
}

function humanizeId(id = "") {
  return id.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function PatternsView({ patterns }) {
  const all = patterns?.patterns || [];
  const [mode, setMode] = useState("device"); // "device" | "type"
  const [selectedDevice, setSelectedDevice] = useState(null);

  // device -> patterns[] (sequences land under each participating device).
  const deviceMap = useMemo(() => {
    const m = new Map();
    for (const p of all) {
      for (const d of patternDevices(p)) {
        if (!m.has(d)) m.set(d, []);
        m.get(d).push(p);
      }
    }
    return m;
  }, [all]);

  const deviceEntries = useMemo(
    () =>
      [...deviceMap.entries()].sort(
        (a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]),
      ),
    [deviceMap],
  );

  // Highest-confidence first within each pattern-type group.
  const typeGroups = useMemo(() => {
    const g = {};
    for (const p of all) (g[p.pattern_type] ||= []).push(p);
    Object.values(g).forEach((arr) => arr.sort((a, b) => b.confidence - a.confidence));
    return g;
  }, [all]);

  if (!all.length) return <Empty text="No patterns learned yet. Load demo data." />;

  const selectedItems = selectedDevice ? deviceMap.get(selectedDevice) || [] : [];

  return (
    <div className="space-y-3">
      <p className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-2.5 text-[11px] text-slate-400">
        <span className="font-semibold text-slate-200">{patterns.count ?? all.length}</span>{" "}
        patterns across{" "}
        <span className="font-semibold text-slate-200">{deviceMap.size}</span> devices —
        learned deterministically, never by an LLM.
      </p>

      <Segmented
        value={mode}
        onChange={(m) => {
          setMode(m);
          setSelectedDevice(null);
        }}
        options={[
          { value: "device", label: "By Device" },
          { value: "type", label: "By Type" },
        ]}
      />

      {mode === "device" &&
        (selectedDevice ? (
          <DeviceDetail
            device={selectedDevice}
            items={selectedItems}
            onBack={() => setSelectedDevice(null)}
          />
        ) : (
          <div className="space-y-2">
            {deviceEntries.map(([device, items]) => (
              <DeviceRow
                key={device}
                device={device}
                items={items}
                onClick={() => setSelectedDevice(device)}
              />
            ))}
          </div>
        ))}

      {mode === "type" && (
        <div className="space-y-2.5">
          {Object.entries(typeGroups).map(([type, items]) => (
            <CollapsibleGroup key={type} type={type} items={items} />
          ))}
        </div>
      )}
    </div>
  );
}

// Two-way pill toggle used to switch the patterns browser between views.
function Segmented({ value, onChange, options }) {
  return (
    <div className="flex gap-1 rounded-lg bg-slate-800/60 p-1">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={[
            "flex-1 rounded-md px-2 py-1.5 text-[11px] font-semibold transition",
            value === o.value
              ? "bg-sky-500/25 text-sky-100"
              : "text-slate-400 hover:text-slate-200",
          ].join(" ")}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// One row in the device master list — icon, name, per-type breakdown, count.
function DeviceRow({ device, items, onClick }) {
  const counts = typeCounts(items);
  return (
    <button
      onClick={onClick}
      className="flex w-full items-center gap-2.5 rounded-xl border border-slate-700/60 bg-slate-800/40 p-2.5 text-left transition hover:border-sky-500/50 hover:bg-slate-800/70"
    >
      <span className="text-lg leading-none">{deviceIcon(deviceTypeFromId(device))}</span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-semibold text-slate-100">{humanizeId(device)}</p>
        <div className="mt-1 flex flex-wrap gap-1">
          {Object.entries(counts).map(([t, n]) => {
            const meta = PATTERN_META[t] || { icon: "•", color: "bg-slate-700/50 text-slate-300" };
            return (
              <span
                key={t}
                className={`rounded px-1 py-0.5 text-[9px] font-semibold ring-1 ${meta.color}`}
              >
                {meta.icon} {n}
              </span>
            );
          })}
        </div>
      </div>
      <span className="flex items-center gap-1.5 text-slate-500">
        <span className="rounded-full bg-slate-700/70 px-1.5 text-[10px] font-bold text-slate-300">
          {items.length}
        </span>
        <span className="text-base">›</span>
      </span>
    </button>
  );
}

// Drill-down for a single device: back link, header, type filter, cards.
function DeviceDetail({ device, items, onBack }) {
  const [typeFilter, setTypeFilter] = useState("all");
  const counts = typeCounts(items);
  const filtered = items
    .filter((p) => typeFilter === "all" || p.pattern_type === typeFilter)
    .sort((a, b) => b.confidence - a.confidence);

  return (
    <div className="space-y-3">
      <button
        onClick={onBack}
        className="flex items-center gap-1 text-[11px] font-semibold text-sky-300 transition hover:text-sky-200"
      >
        ← All devices
      </button>

      <div className="flex items-center gap-3 rounded-xl border border-slate-700/60 bg-linear-to-br from-slate-950/80 to-slate-900/40 p-3">
        <span className="text-2xl leading-none">{deviceIcon(deviceTypeFromId(device))}</span>
        <div className="min-w-0">
          <p className="truncate text-sm font-bold text-slate-100">{humanizeId(device)}</p>
          <p className="text-[10px] text-slate-500">
            {items.length} pattern{items.length === 1 ? "" : "s"} learned
          </p>
        </div>
      </div>

      <TypeFilter value={typeFilter} onChange={setTypeFilter} counts={counts} />

      <ul className="space-y-2.5">
        {filtered.map((p) => (
          <PatternCard
            key={p.pattern_id}
            p={p}
            meta={PATTERN_META[p.pattern_type] || { label: p.pattern_type, icon: "•", color: "" }}
          />
        ))}
      </ul>
    </div>
  );
}

// Chip row to filter a device's patterns by type (only shows types present).
function TypeFilter({ value, onChange, counts }) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const options = [
    { key: "all", label: "All", icon: "▦", n: total, color: "bg-slate-700/50 text-slate-200 ring-slate-500/40" },
    ...["time_based", "sequence", "duration"]
      .filter((t) => counts[t])
      .map((t) => ({ key: t, ...PATTERN_META[t], n: counts[t] })),
  ];
  if (options.length <= 2) return null; // only one real type → no point filtering

  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => {
        const active = value === o.key;
        return (
          <button
            key={o.key}
            onClick={() => onChange(o.key)}
            className={[
              "rounded-md px-2 py-1 text-[10px] font-semibold ring-1 transition",
              active ? o.color : "bg-slate-800/40 text-slate-400 ring-slate-700/60 hover:text-slate-200",
            ].join(" ")}
          >
            {o.icon} {o.label} ({o.n})
          </button>
        );
      })}
    </div>
  );
}

// Collapsible per-type section for the "By Type" view.
function CollapsibleGroup({ type, items }) {
  const [open, setOpen] = useState(true);
  const meta = PATTERN_META[type] || { label: type, icon: "•", color: "" };
  return (
    <div className="overflow-hidden rounded-xl border border-slate-700/60">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between bg-slate-800/50 px-3 py-2 transition hover:bg-slate-800/80"
      >
        <span className="flex items-center gap-2">
          <span className={`rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide ring-1 ${meta.color}`}>
            {meta.icon} {meta.label}
          </span>
          <span className="text-[11px] font-semibold text-slate-400">{items.length}</span>
        </span>
        <span className="text-slate-500">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <ul className="space-y-2.5 p-2.5">
          {items.map((p) => (
            <PatternCard key={p.pattern_id} p={p} meta={meta} />
          ))}
        </ul>
      )}
    </div>
  );
}

function PatternCard({ p, meta }) {
  return (
    <li className="rounded-xl border border-slate-700/60 bg-slate-800/40 p-3 shadow-sm transition hover:border-slate-600">
      <div className="flex items-start justify-between gap-2">
        <h5 className="text-xs font-semibold text-slate-100">{patternTitle(p)}</h5>
        <span className={`shrink-0 rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide ring-1 ${meta.color}`}>
          {meta.label}
        </span>
      </div>

      {/* Type-specific detail chips */}
      <div className="mt-2 flex flex-wrap gap-1.5">
        {patternDetailChips(p).map((c) => (
          <Chip key={c.label} label={c.label} value={c.value} />
        ))}
      </div>

      {/* Sequence steps rendered as a chain */}
      {p.pattern_type === "sequence" && Array.isArray(p.steps) && (
        <div className="mt-2 flex flex-wrap items-center gap-1">
          {p.steps.map((s, i) => (
            <span key={i} className="flex items-center gap-1">
              <span className="rounded-md bg-violet-500/15 px-1.5 py-0.5 text-[10px] font-medium text-violet-200 ring-1 ring-violet-500/30">
                {s}
              </span>
              {i < p.steps.length - 1 && <span className="text-slate-500">→</span>}
            </span>
          ))}
        </div>
      )}

      <ConfidenceBar value={p.confidence} />

      <div className="mt-2 flex items-center justify-between text-[10px] text-slate-500">
        <span>{p.occurrences} occurrences</span>
        <span>updated {shortDate(p.last_updated)}</span>
      </div>
      <p className="mt-1 truncate text-[9px] text-slate-600" title={p.pattern_id}>
        {p.pattern_id}
      </p>
    </li>
  );
}

function patternTitle(p) {
  if (p.pattern_type === "time_based") return `${p.device} usually ${p.action}`;
  if (p.pattern_type === "sequence") return p.description || "Routine sequence";
  if (p.pattern_type === "duration") return `${p.device} runtime`;
  return p.pattern_id;
}

function patternDetailChips(p) {
  if (p.pattern_type === "time_based") {
    return [
      { label: "Around", value: p.usual_time },
      { label: "Action", value: p.action },
      { label: "Window", value: `±${p.window_minutes}m` },
    ];
  }
  if (p.pattern_type === "duration") {
    return [
      { label: "Typical", value: `${Math.round(p.usual_duration_minutes)}m` },
      ...(p.usual_start_time ? [{ label: "Starts", value: p.usual_start_time }] : []),
      { label: "Std dev", value: `±${p.stddev_minutes?.toFixed(1) ?? 0}m` },
    ];
  }
  if (p.pattern_type === "sequence") {
    return [
      { label: "Steps", value: p.steps?.length ?? 0 },
      ...(p.usual_time ? [{ label: "Starts", value: p.usual_time }] : []),
    ];
  }
  return [];
}

/* ------------------------------------------------------------------- Events */

function EventsView({ events, loading }) {
  const [filter, setFilter] = useState("all");

  const days = useMemo(() => groupByDay(events || []), [events]);
  const rooms = useMemo(
    () => ["all", ...Array.from(new Set((events || []).map((e) => e.room))).sort()],
    [events]
  );

  if (!events) return <Empty text={loading ? "Loading event log…" : "No events yet."} />;
  if (events.length === 0) return <Empty text="No events in the last 30 days. Load demo data." />;

  const filteredDays = days
    .map(([day, evs]) => [day, filter === "all" ? evs : evs.filter((e) => e.room === filter)])
    .filter(([, evs]) => evs.length > 0);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] text-slate-400">
          <span className="font-semibold text-slate-200">{events.length}</span> events · last 30 days
        </p>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1 text-[11px] text-slate-200 outline-none focus:border-sky-500"
        >
          {rooms.map((r) => (
            <option key={r} value={r}>
              {r === "all" ? "All rooms" : r.replaceAll("_", " ")}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-4">
        {filteredDays.map(([day, evs]) => (
          <div key={day}>
            <div className="sticky top-0 z-10 -mx-1 mb-1.5 flex items-center gap-2 bg-slate-900/80 px-1 py-1 backdrop-blur">
              <h4 className="text-[11px] font-bold text-slate-300">{formatDayHeader(day)}</h4>
              <span className="rounded-full bg-slate-700/60 px-1.5 text-[9px] font-semibold text-slate-300">
                {evs.length}
              </span>
              <div className="h-px flex-1 bg-slate-700/50" />
            </div>

            <ol className="relative ml-2 space-y-1.5 border-l border-slate-700/60 pl-3">
              {evs.map((e) => (
                <EventRow key={e.event_id} e={e} />
              ))}
            </ol>
          </div>
        ))}
      </div>
    </div>
  );
}

function EventRow({ e }) {
  const a = ACTION_STYLE[e.action] || ACTION_STYLE.OFF;
  return (
    <li className="group relative">
      <span className={`absolute left-[-1.18rem] top-2 h-2 w-2 rounded-full ring-2 ring-slate-900 ${a.dot}`} />
      <div className="flex items-center gap-2 rounded-lg border border-slate-700/50 bg-slate-800/40 px-2.5 py-1.5 transition group-hover:border-slate-600">
        <span className="text-base leading-none">{deviceIcon(e.device_type)}</span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[11px] font-medium text-slate-200">{e.device_id}</p>
          <p className="truncate text-[10px] text-slate-500">
            {e.room.replaceAll("_", " ")} · by {e.triggered_by}
          </p>
        </div>
        <ActionPill action={e.action} />
        <span className="w-10 shrink-0 text-right text-[10px] text-slate-500">{shortTime(e.timestamp)}</span>
      </div>
    </li>
  );
}

/* -------------------------------------------------------------------- State */

function StateView({ state }) {
  if (!state) return <Empty text="No state yet." />;
  return (
    <div className="space-y-4">
      <Section title="People home">
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(state.people_home || {}).map(([p, home]) => (
            <span
              key={p}
              className={[
                "rounded-full px-2 py-1 text-[11px] font-medium capitalize",
                home ? "bg-emerald-500/15 text-emerald-300" : "bg-slate-700/40 text-slate-500",
              ].join(" ")}
            >
              {home ? "🟢" : "⚪"} {p}
            </span>
          ))}
          {Object.keys(state.people_home || {}).length === 0 && (
            <span className="text-[11px] text-slate-500">unknown</span>
          )}
        </div>
      </Section>

      <Section title={`Active devices (${state.active_devices?.length || 0})`}>
        {state.active_devices?.length ? (
          <ul className="space-y-1">
            {state.active_devices.map((d) => (
              <li
                key={d}
                className="flex items-center justify-between rounded-lg bg-slate-800/40 px-2 py-1.5 text-[11px] text-slate-200"
              >
                <span className="flex items-center gap-1.5">
                  <span>{deviceIcon(deviceTypeFromId(d))}</span>
                  {d}
                </span>
                {state.device_on_since?.[d] && (
                  <span className="text-[10px] text-slate-500">
                    since {new Date(state.device_on_since[d]).toLocaleString()}
                  </span>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[11px] text-slate-500">All devices off.</p>
        )}
      </Section>

      <Section title="Last updated">
        <p className="text-[11px] text-slate-400">
          {state.updated_at ? new Date(state.updated_at).toLocaleString() : "—"}
        </p>
      </Section>
    </div>
  );
}

/* ---------------------------------------------------------------- Primitives */

function ActionPill({ action }) {
  const a = ACTION_STYLE[action] || ACTION_STYLE.OFF;
  return (
    <span className={`shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide ${a.cls}`}>
      {action}
    </span>
  );
}

function Chip({ label, value }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-slate-900/60 px-1.5 py-0.5 text-[10px]">
      <span className="text-slate-500">{label}</span>
      <span className="font-semibold text-slate-200">{value}</span>
    </span>
  );
}

function MiniStat({ label, value, tone }) {
  const toneCls =
    tone === "warn"
      ? "text-red-300"
      : tone === "ok"
        ? "text-emerald-300"
        : "text-slate-100";
  return (
    <div className="rounded-lg bg-slate-900/50 px-2 py-1.5">
      <div className="text-[9px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className={`text-sm font-bold ${toneCls}`}>{value}</div>
    </div>
  );
}

function ConfidenceBar({ value }) {
  const pct = Math.round((value || 0) * 100);
  const bar =
    pct >= 85 ? "from-emerald-500 to-emerald-400"
      : pct >= 70 ? "from-sky-500 to-emerald-400"
        : "from-amber-500 to-orange-400";
  return (
    <div className="mt-2 flex items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-700">
        <div className={`h-full rounded-full bg-linear-to-r ${bar}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-8 text-right text-[10px] font-medium text-slate-400">{pct}%</span>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div>
      <h4 className="mb-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-500">{title}</h4>
      {children}
    </div>
  );
}

function Collapsible({ title, children }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between text-[10px] font-bold uppercase tracking-wider text-slate-500 hover:text-slate-300"
      >
        {title}
        <span>{open ? "▾" : "▸"}</span>
      </button>
      {open && <div className="mt-1.5">{children}</div>}
    </div>
  );
}

function Empty({ text }) {
  return (
    <div className="grid h-40 place-items-center text-center">
      <p className="text-xs text-slate-500">{text}</p>
    </div>
  );
}

/* ------------------------------------------------------------------ Helpers */

// Best-effort device-type inference from an id so we can show a matching icon
// (events already carry device_type; ids in context/state do not).
function deviceTypeFromId(id = "") {
  const s = id.toLowerCase();
  if (s.includes("presence")) return "presence";
  if (s.includes("fan")) return "fan";
  if (s.includes("light")) return "light";
  if (s.includes("ac")) return "ac";
  if (s.includes("tv")) return "tv";
  if (s.includes("motor")) return "motor";
  if (s.includes("door")) return "door";
  return "other";
}

function groupByDay(events) {
  const groups = new Map();
  for (const e of events) {
    const key = new Date(e.timestamp).toLocaleDateString("en-CA"); // YYYY-MM-DD local
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(e);
  }
  return [...groups.entries()]
    .sort((a, b) => (a[0] < b[0] ? 1 : -1))
    .map(([day, evs]) => [
      day,
      evs.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp)),
    ]);
}

function formatDayHeader(dayKey) {
  const d = new Date(`${dayKey}T00:00:00`);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  const same = (a, b) => a.toLocaleDateString("en-CA") === b.toLocaleDateString("en-CA");
  if (same(d, today)) return "Today";
  if (same(d, yesterday)) return "Yesterday";
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

function shortTime(ts) {
  return new Date(ts).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function shortDate(ts) {
  return new Date(ts).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
