import { HOUSEHOLDS } from "../../config/houseLayout.js";

// Top control bar: household switch, simulated clock, presence, demo actions.
export default function TopBar({
  householdId,
  onHouseholdChange,
  simTime,
  onSimTimeChange,
  dayType,
  onDayTypeChange,
  festival,
  onFestivalChange,
  peopleHome,
  onSeed,
  onRun,
  dirty,
  busy,
  connected,
}) {
  const people = HOUSEHOLDS[householdId].people;

  return (
    <header className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-700/60 bg-slate-900/60 px-4 py-3 backdrop-blur">
      {/* Brand */}
      <div className="flex items-center gap-2">
        <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-sky-500 to-indigo-600 text-lg shadow-lg">
          🏠
        </span>
        <div className="leading-tight">
          <h1 className="text-sm font-bold text-slate-100">Smart Home Intelligence</h1>
          <p className="text-[10px] text-slate-400">Context-aware · deterministic patterns</p>
        </div>
      </div>

      <div className="mx-1 hidden h-8 w-px bg-slate-700 sm:block" />

      {/* Household selector */}
      <label className="flex items-center gap-2 text-xs text-slate-400">
        Home
        <select
          value={householdId}
          onChange={(e) => onHouseholdChange(e.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs font-medium text-slate-100 outline-none focus:border-sky-500"
        >
          {Object.entries(HOUSEHOLDS).map(([id, h]) => (
            <option key={id} value={id}>
              {h.label}
            </option>
          ))}
        </select>
      </label>

      {/* Simulated clock */}
      <label className="flex items-center gap-2 text-xs text-slate-400">
        <span title="Simulated 'current time'. Set it, paint the device states, then hit Go.">🕒 Clock</span>
        <input
          type="time"
          value={simTime}
          onChange={(e) => onSimTimeChange(e.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs font-medium text-slate-100 outline-none focus:border-sky-500"
        />
      </label>

      {/* Simulated day type + festival — pauses weekday-only routines */}
      <div
        className="flex items-center gap-1.5 text-xs text-slate-400"
        title="Simulated day. On Weekend or a named festival, weekday-only routines (school run, office commute) are paused so they don't false-flag."
      >
        <span>🗓️</span>
        <div className="flex overflow-hidden rounded-lg border border-slate-700">
          {["weekday", "weekend"].map((d) => (
            <button
              key={d}
              onClick={() => onDayTypeChange(d)}
              className={[
                "px-2 py-1.5 text-xs font-medium capitalize transition",
                dayType === d
                  ? "bg-amber-500/25 text-amber-200"
                  : "bg-slate-800 text-slate-400 hover:text-slate-200",
              ].join(" ")}
            >
              {d}
            </button>
          ))}
        </div>
        <input
          type="text"
          value={festival || ""}
          onChange={(e) => onFestivalChange(e.target.value)}
          placeholder="Festival?"
          title="Optional festival name (e.g. Diwali) — pauses weekday routines for the day."
          className="w-24 rounded-lg border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs font-medium text-slate-100 outline-none placeholder:text-slate-600 focus:border-amber-500"
        />
      </div>

      {/* Presence pills */}
      <div className="flex items-center gap-1.5">
        {people.map((p) => {
          const home = Boolean(peopleHome?.[p]);
          return (
            <span
              key={p}
              title={`${p} is ${home ? "home" : "away"}`}
              className={[
                "flex items-center gap-1 rounded-full px-2 py-1 text-[10px] font-medium capitalize",
                home
                  ? "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/40"
                  : "bg-slate-700/40 text-slate-500",
              ].join(" ")}
            >
              {home ? "🟢" : "⚪"} {p}
            </span>
          );
        })}
      </div>

      <div className="ml-auto flex items-center gap-2">
        <span
          className={[
            "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-medium",
            connected
              ? "bg-emerald-500/15 text-emerald-300"
              : "bg-red-500/15 text-red-300",
          ].join(" ")}
        >
          <span className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-400" : "bg-red-400"}`} />
          {connected ? "API connected" : "API offline"}
        </span>

        <button
          onClick={onSeed}
          disabled={busy}
          className="rounded-lg border border-indigo-500/50 bg-indigo-500/15 px-3 py-1.5 text-xs font-semibold text-indigo-200 transition hover:bg-indigo-500/25 disabled:opacity-50"
        >
          ⤵ Load Demo Data
        </button>
        <button
          onClick={onRun}
          disabled={busy}
          title="Compare the painted device states + clock against the learned patterns"
          className={[
            "flex items-center gap-1.5 rounded-lg px-4 py-1.5 text-xs font-bold transition disabled:opacity-50",
            dirty
              ? "animate-pulse border border-emerald-400 bg-emerald-500/25 text-emerald-100 shadow-lg shadow-emerald-500/20"
              : "border border-emerald-500/50 bg-emerald-500/15 text-emerald-200 hover:bg-emerald-500/25",
          ].join(" ")}
        >
          {busy ? "… Checking" : dirty ? "▶ Go — Run Check" : "▶ Run Check"}
        </button>
      </div>
    </header>
  );
}
