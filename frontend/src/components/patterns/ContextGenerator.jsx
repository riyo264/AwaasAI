import { HOUSEHOLDS } from "../../config/houseLayout.js";

// The context generator — the panel of inputs that set up a what-if scene
// (home, clock, day/festival) plus the demo-seed and Run actions. It sits
// beside the house map; running a check evaluates the painted scene.
export default function ContextGenerator({
  householdId,
  onHouseholdChange,
  simTime,
  onSimTimeChange,
  dayType,
  onDayTypeChange,
  festival,
  onFestivalChange,
  onSeed,
  onRun,
  dirty,
  busy,
}) {
  return (
    <aside className="flex h-full flex-col gap-4 rounded-2xl border border-slate-700/70 bg-slate-900/70 p-4 backdrop-blur">
      {/* Panel header */}
      <div className="flex items-center gap-2.5">
        <span className="grid h-9 w-9 place-items-center rounded-lg bg-[var(--pp-accent-weak)] text-lg">
          🎛️
        </span>
        <div className="leading-tight">
          <h2 className="text-sm font-bold text-slate-100">Context Generator</h2>
          <p className="text-xs text-slate-400">Set the scene, then run a check</p>
        </div>
      </div>

      {/* Household selector */}
      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          Home
        </span>
        <select
          value={householdId}
          onChange={(e) => onHouseholdChange(e.target.value)}
          className="w-full rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-2 text-sm font-medium text-slate-100 outline-none focus:border-[var(--pp-accent)]"
        >
          {Object.entries(HOUSEHOLDS).map(([id, h]) => (
            <option key={id} value={id}>
              {h.label}
            </option>
          ))}
        </select>
      </label>

      {/* Simulated clock */}
      <label className="flex flex-col gap-1.5">
        <span
          className="text-xs font-semibold uppercase tracking-wider text-slate-500"
          title="Simulated 'current time'. Set it, paint the device states, then hit Run."
        >
          🕒 Simulated time
        </span>
        <input
          type="time"
          value={simTime}
          onChange={(e) => onSimTimeChange(e.target.value)}
          className="w-full rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-2 text-sm font-medium text-slate-100 outline-none focus:border-[var(--pp-accent)]"
        />
      </label>

      {/* Simulated day type + festival — pauses weekday-only routines */}
      <div className="flex flex-col gap-1.5">
        <span
          className="text-xs font-semibold uppercase tracking-wider text-slate-500"
          title="Simulated day. On Weekend or a named festival, weekday-only routines (school run, office commute) are paused so they don't false-flag."
        >
          🗓️ Simulated day
        </span>
        <div className="flex overflow-hidden rounded-lg border border-slate-700">
          {["weekday", "weekend"].map((d) => (
            <button
              key={d}
              onClick={() => onDayTypeChange(d)}
              className={[
                "flex-1 px-2.5 py-2 text-sm font-medium capitalize transition",
                dayType === d
                  ? "bg-[var(--pp-accent-weak)] text-[var(--pp-accent-text)]"
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
          placeholder="Festival? (e.g. Diwali)"
          title="Optional festival name (e.g. Diwali) — pauses weekday routines for the day."
          className="w-full rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-2 text-sm font-medium text-slate-100 outline-none placeholder:text-slate-500 focus:border-[var(--pp-accent)]"
        />
      </div>

      {/* Actions — pinned to the bottom of the panel */}
      <div className="mt-auto flex flex-col gap-2 pt-2">
        <button
          onClick={onRun}
          disabled={busy}
          title="Compare the painted device states + clock against the learned patterns"
          className={[
            "pp-btn-primary flex items-center justify-center gap-1.5 rounded-lg px-5 py-2.5 text-sm transition disabled:opacity-50",
            dirty ? "animate-pulse shadow-lg" : "",
          ].join(" ")}
        >
          {busy ? "… Checking" : "▶ Run Check"}
        </button>
        <button
          onClick={onSeed}
          disabled={busy}
          className="pp-btn rounded-lg px-3 py-2 text-sm font-semibold transition disabled:opacity-50"
        >
          ⤵ Load Demo Data
        </button>
      </div>
    </aside>
  );
}
