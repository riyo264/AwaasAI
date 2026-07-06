import { useCallback, useEffect, useState } from "react";
import { api } from "../../patternsApi.js";

const DEVICE_TYPES = [
  "fan", "light", "ac", "tv", "door", "motor", "presence", "activity", "medicine", "other",
];

const ACTIONS = ["ON", "OFF", "OPEN", "CLOSE", "ARRIVE", "LEAVE", "ACTIVE", "TAKEN"];

const DAY_OPTIONS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

const DEVICE_EMOJI = {
  fan: "🌀", light: "💡", ac: "❄️", tv: "📺", door: "🚪",
  motor: "💧", presence: "👤", activity: "🏃", medicine: "💊", other: "🔌",
};

const ACTION_COLOR = {
  ON: "text-emerald-300", OFF: "text-slate-400", OPEN: "text-sky-300",
  CLOSE: "text-slate-400", ARRIVE: "text-emerald-300", LEAVE: "text-rose-300",
  ACTIVE: "text-amber-300", TAKEN: "text-violet-300",
};

function emptyForm() {
  return {
    label: "",
    device_id: "",
    device_type: "fan",
    room: "",
    action: "ON",
    usual_time: "07:00",
    window_minutes: 20,
    days: ["all"],
    duration_minutes: "",
  };
}

function DayChip({ day, active, onToggle }) {
  return (
    <button
      type="button"
      onClick={() => onToggle(day)}
      className={[
        "rounded-full px-2 py-0.5 text-[10px] font-bold uppercase transition ring-1",
        active
          ? "bg-indigo-500/30 text-indigo-200 ring-indigo-500/60"
          : "bg-slate-800 text-slate-500 ring-slate-700 hover:text-slate-300",
      ].join(" ")}
    >
      {day === "all" ? "All" : day}
    </button>
  );
}

export default function HomeProfile({ householdId }) {
  const [routines, setRoutines] = useState([]);
  const [form, setForm] = useState(emptyForm());
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(null);
  const [open, setOpen] = useState(true);

  const load = useCallback(async () => {
    try {
      const { routines: r } = await api.getProfileRoutines(householdId);
      setRoutines(r || []);
    } catch { /* ignore on first load if table not yet created */ }
  }, [householdId]);

  useEffect(() => { load(); }, [load]);

  const setField = (key, val) => setForm((f) => ({ ...f, [key]: val }));

  const toggleDay = (day) => {
    setForm((f) => {
      if (day === "all") return { ...f, days: ["all"] };
      const without = f.days.filter((d) => d !== "all" && d !== day);
      const next = f.days.includes(day) ? without : [...without, day];
      return { ...f, days: next.length ? next : ["all"] };
    });
  };

  const submit = useCallback(async () => {
    if (!form.label.trim() || !form.device_id.trim() || !form.room.trim()) {
      setNote("Label, device ID and room are required.");
      return;
    }
    setBusy(true);
    setNote(null);
    try {
      await api.addProfileRoutine(householdId, {
        label: form.label.trim(),
        device_id: form.device_id.trim(),
        device_type: form.device_type,
        room: form.room.trim(),
        action: form.action,
        usual_time: form.usual_time,
        window_minutes: Number(form.window_minutes) || 20,
        days: form.days,
        duration_minutes: form.duration_minutes ? Number(form.duration_minutes) : null,
      });
      setForm(emptyForm());
      load();
    } catch (e) {
      setNote(`Failed: ${e.message}`);
    } finally {
      setBusy(false);
    }
  }, [form, householdId, load]);

  const remove = useCallback(async (routineId) => {
    try {
      await api.deleteProfileRoutine(householdId, routineId);
      load();
    } catch { /* ignore */ }
  }, [householdId, load]);

  return (
    <section className="overflow-hidden rounded-2xl border border-teal-500/40 bg-slate-900/50 shadow-lg shadow-teal-900/10">
      {/* Header */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full flex-wrap items-center gap-2 bg-gradient-to-r from-teal-600/25 to-cyan-600/10 px-4 py-3 text-left"
      >
        <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-teal-500 to-cyan-600 text-lg shadow">🏠</span>
        <div className="flex-1 leading-tight">
          <h2 className="text-sm font-bold text-slate-100">My Home Routines</h2>
          <p className="text-[10px] text-slate-400">
            Define your own schedule — device, state, and time — fed directly into the anomaly engine
          </p>
        </div>
        <span className="text-xs text-slate-500">{routines.length} saved · {open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="p-4 space-y-4">
          {/* Form */}
          <div className="rounded-xl border border-slate-700 bg-slate-800/50 p-3 space-y-3">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Add a routine</p>

            {/* Label */}
            <input
              value={form.label}
              onChange={(e) => setField("label", e.target.value)}
              placeholder="Label  e.g. Morning fan"
              className="w-full rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-600 focus:border-teal-500"
            />

            {/* Device ID + Type */}
            <div className="flex gap-2">
              <input
                value={form.device_id}
                onChange={(e) => setField("device_id", e.target.value)}
                placeholder="Device ID  e.g. son_room_fan"
                className="flex-1 rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-600 focus:border-teal-500"
              />
              <select
                value={form.device_type}
                onChange={(e) => setField("device_type", e.target.value)}
                className="rounded-lg border border-slate-700 bg-slate-900/60 px-2 py-2 text-sm text-slate-200 outline-none focus:border-teal-500"
              >
                {DEVICE_TYPES.map((t) => (
                  <option key={t} value={t}>{DEVICE_EMOJI[t]} {t}</option>
                ))}
              </select>
            </div>

            {/* Room + Action */}
            <div className="flex gap-2">
              <input
                value={form.room}
                onChange={(e) => setField("room", e.target.value)}
                placeholder="Room  e.g. son_room"
                className="flex-1 rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-600 focus:border-teal-500"
              />
              <select
                value={form.action}
                onChange={(e) => setField("action", e.target.value)}
                className="rounded-lg border border-slate-700 bg-slate-900/60 px-2 py-2 text-sm text-slate-200 outline-none focus:border-teal-500"
              >
                {ACTIONS.map((a) => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
            </div>

            {/* Time + Window */}
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-1.5">
                <span className="text-[10px] text-slate-500">Time</span>
                <input
                  type="time"
                  value={form.usual_time}
                  onChange={(e) => setField("usual_time", e.target.value)}
                  className="bg-transparent text-sm text-teal-300 outline-none"
                />
              </div>
              <div className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-1.5">
                <span className="text-[10px] text-slate-500">±</span>
                <input
                  type="number"
                  min={5}
                  max={120}
                  value={form.window_minutes}
                  onChange={(e) => setField("window_minutes", e.target.value)}
                  className="w-10 bg-transparent text-sm text-slate-200 outline-none"
                />
                <span className="text-[10px] text-slate-500">min</span>
              </div>
              <div className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-1.5">
                <span className="text-[10px] text-slate-500">runs for</span>
                <input
                  type="number"
                  min={1}
                  value={form.duration_minutes}
                  onChange={(e) => setField("duration_minutes", e.target.value)}
                  placeholder="—"
                  className="w-10 bg-transparent text-sm text-slate-200 outline-none placeholder:text-slate-600"
                />
                <span className="text-[10px] text-slate-500">min</span>
              </div>
            </div>

            {/* Days */}
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[10px] text-slate-500">Days:</span>
              <DayChip day="all" active={form.days.includes("all")} onToggle={toggleDay} />
              {DAY_OPTIONS.map((d) => (
                <DayChip key={d} day={d} active={form.days.includes(d)} onToggle={toggleDay} />
              ))}
            </div>

            {note && <p className="text-[11px] text-rose-400">{note}</p>}

            <button
              type="button"
              onClick={submit}
              disabled={busy}
              className="rounded-lg bg-teal-500/90 px-4 py-1.5 text-xs font-bold text-white transition hover:bg-teal-500 disabled:opacity-40"
            >
              {busy ? "Saving…" : "＋ Add routine"}
            </button>
          </div>

          {/* Saved routines */}
          {routines.length > 0 && (
            <div>
              <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                Saved routines ({routines.length})
              </p>
              <ul className="flex flex-col gap-2">
                {routines.map((r) => (
                  <li
                    key={r.routine_id}
                    className="flex items-start gap-3 rounded-xl border border-slate-800 bg-slate-950/50 px-3 py-2"
                  >
                    <span className="mt-0.5 text-xl">{DEVICE_EMOJI[r.device_type] || "🔌"}</span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-slate-100 truncate">{r.label}</p>
                      <p className="text-[11px] text-slate-400">
                        <span className="font-mono text-slate-300">{r.device_id}</span>
                        {" · "}
                        <span className={ACTION_COLOR[r.action] || "text-slate-300"}>{r.action}</span>
                        {" · "}
                        <span className="text-teal-300">@{r.usual_time}</span>
                        <span className="text-slate-600"> ±{r.window_minutes}m</span>
                        {r.duration_minutes && (
                          <span className="text-slate-500"> · runs {r.duration_minutes}m</span>
                        )}
                      </p>
                      <p className="text-[10px] text-slate-600">
                        {r.room} · {r.days.join(", ")}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => remove(r.routine_id)}
                      title="Delete"
                      className="mt-0.5 text-slate-600 transition hover:text-rose-400"
                    >
                      ✕
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {routines.length === 0 && (
            <p className="text-center text-[11px] text-slate-600 py-2">
              No routines yet — add one above and the anomaly engine will use it immediately.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
