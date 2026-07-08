import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../patternsApi.js";
import ContextGenerator from "../components/patterns/ContextGenerator.jsx";
import HouseFloor from "../components/patterns/HouseFloor.jsx";
import {
  ContextView,
  PatternsView,
  EventsView,
  StateView,
} from "../components/patterns/SidePanel.jsx";
import AlexaNotification from "../components/patterns/AlexaNotification.jsx";
import ContextualPatterns from "../components/patterns/ContextualPatterns.jsx";
import ContextNotes from "../components/patterns/ContextNotes.jsx";
import AdjustedRoutine from "../components/patterns/AdjustedRoutine.jsx";
import HomeProfile from "../components/patterns/HomeProfile.jsx";

function nowHHMM() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export default function Patterns() {
  const [householdId, setHouseholdId] = useState("H001");
  // Bumped whenever the occasion overlay changes, so the adapted routine refetches.
  const [overlayVersion, setOverlayVersion] = useState(0);
  const [simTime, setSimTime] = useState(nowHHMM());
  // Simulated day: on "weekend" or a named festival the backend pauses
  // weekday-only routines so they don't false-flag as missed.
  const [dayType, setDayType] = useState("weekday");
  const [festival, setFestival] = useState("");
  const [state, setState] = useState(null);
  const [patterns, setPatterns] = useState(null);
  const [context, setContext] = useState(null);
  const [events, setEvents] = useState(null);
  // Light / dark theme (Amazon palette), persisted across sessions.
  const [theme, setTheme] = useState(
    () => localStorage.getItem("pp-theme") || "dark",
  );
  // Which "Explore" section is expanded (accordion; null = all collapsed).
  const [openSection, setOpenSection] = useState(null);
  // The user-painted "what-if" scenario: which devices are ON right now.
  // Local only — toggling never writes to the backend, so the demo data is
  // never polluted. Hitting "Run" evaluates this against the learned patterns.
  const [draftActive, setDraftActive] = useState(() => new Set());
  // True when the draft state or clock changed since the last evaluation.
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [connected, setConnected] = useState(true);
  const [toast, setToast] = useState(null);
  // Alexa-voice popups driven by the LLM narrator. Each detected issue is
  // narrated separately (so no detail is lost) and queued; the queue is played
  // one-by-one as a sequence of floating notifications. Index 0 is on screen.
  const [alexaQueue, setAlexaQueue] = useState([]);

  useEffect(() => {
    localStorage.setItem("pp-theme", theme);
  }, [theme]);

  const flash = useCallback((msg, ok = true) => {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 2600);
  }, []);

  // Ask the backend to phrase a context as spoken Alexa lines — ONE focused
  // line per detected issue — then queue them so they appear and are read out
  // one after another. Never throws — narration is best-effort.
  const speak = useCallback(async (ctx) => {
    if (!ctx) return;
    try {
      const { narrations } = await api.narrateEach(ctx);
      const items = (narrations || [])
        .filter((n) => n && n.alexa_response)
        .map((n, i) => ({
          id: `${Date.now()}-${i}-${n.device || "all"}`,
          text: n.alexa_response,
          explanation: n.explanation,
          llmPowered: n.llm_powered,
          tone:
            n.severity === "high" || n.severity === "medium" ? "alert" : "calm",
        }));
      setAlexaQueue(items);
    } catch {
      /* narration is optional; ignore failures */
    }
  }, []);

  // Evaluate the current draft scenario (devices + clock) against the learned
  // patterns. This is the "Run" action — the heart of the flow.
  const runCheck = useCallback(
    async (
      hid = householdId,
      time = simTime,
      active = draftActive,
      people = state?.people_home,
    ) => {
      setBusy(true);
      try {
        const c = await api.evaluate(hid, {
          at: time,
          activeDevices: [...active],
          peopleHome: people || {},
          dayType,
          festival: festival.trim() || null,
        });
        setContext(c);
        setDirty(false);
        setConnected(true);
        speak(c);
        return c;
      } catch (e) {
        setConnected(false);
        flash(`Evaluation failed — is the backend running? (${e.message})`, false);
      } finally {
        setBusy(false);
      }
    },
    [householdId, simTime, draftActive, state, dayType, festival, flash, speak],
  );

  // Load reference data (patterns, persisted snapshot, events). The floor plan
  // starts in a CLEAN, all-off state with no anomalies or notifications — the
  // user paints the scenario and hits "Run" to start a simulation. We do NOT
  // auto-evaluate or auto-speak on first load, so arriving on the page always
  // shows a calm, normal home until the user explicitly runs a check.
  const loadAll = useCallback(
    async (hid = householdId) => {
      setBusy(true);
      try {
        const [s, p, e] = await Promise.all([
          api.getState(hid),
          api.getPatterns(hid),
          api.getEvents(hid),
        ]);
        setState(s);
        setPatterns(p);
        setEvents(e);
        // Start with everything OFF (empty draft) — a clean slate.
        setDraftActive(new Set());
        setContext(null);
        setAlexaQueue([]);
        setDirty(false);
        setConnected(true);
      } catch (e) {
        setConnected(false);
        flash(
          `Cannot reach API — is the backend running? (${e.message})`,
          false,
        );
      } finally {
        setBusy(false);
      }
    },
    [householdId, flash],
  );

  // Initial + on household change.
  useEffect(() => {
    loadAll(householdId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [householdId]);

  // The floor plan reflects the user's painted scenario.
  const activeSet = draftActive;

  const anomalyMap = useMemo(() => {
    const m = new Map();
    (context?.anomalies || []).forEach((a) => {
      if (a.device) m.set(a.device, a);
    });
    return m;
  }, [context]);

  // Toggle a device in the *draft* scenario — local only, no backend write.
  const toggleDraft = useCallback((device) => {
    setDraftActive((prev) => {
      const next = new Set(prev);
      if (next.has(device.id)) next.delete(device.id);
      else next.add(device.id);
      return next;
    });
    setDirty(true);
  }, []);

  // Changing the clock marks the scenario dirty; the user re-runs with "Run".
  const handleSimTime = useCallback((t) => {
    setSimTime(t);
    setDirty(true);
  }, []);

  // Changing the simulated day / festival also marks the scenario dirty.
  const handleDayType = useCallback((d) => {
    setDayType(d);
    setDirty(true);
  }, []);
  const handleFestival = useCallback((f) => {
    setFestival(f);
    setDirty(true);
  }, []);

  const handleSeed = useCallback(async () => {
    setBusy(true);
    try {
      const res = await api.seed(householdId);
      flash(
        `Seeded ${res.events_stored} events · ${res.patterns_extracted} patterns`,
      );
      // After loading demo data, return to the clean all-off slate so the user
      // starts the simulation themselves.
      await loadAll(householdId);
      // New patterns exist → refresh the adapted-routine + context panels.
      setOverlayVersion((v) => v + 1);
    } catch (e) {
      flash(`Seed failed: ${e.message}`, false);
    } finally {
      setBusy(false);
    }
  }, [householdId, loadAll, flash]);

  const bump = () => setOverlayVersion((v) => v + 1);

  // The "Explore" drawer — everything that isn't the house or the live context
  // lives here, collapsed by default so the page stays calm. One opens at a time.
  const sections = [
    {
      key: "patterns",
      label: "Learned Patterns",
      icon: "🧠",
      count: patterns?.count ?? patterns?.patterns?.length ?? 0,
      render: () => <PatternsView patterns={patterns} />,
    },
    {
      key: "events",
      label: "Event History",
      icon: "📅",
      count: events?.length ?? 0,
      render: () => <EventsView events={events} loading={busy} />,
    },
    {
      key: "state",
      label: "Live State",
      icon: "📡",
      count: state?.active_devices?.length ?? 0,
      render: () => <StateView state={state} />,
    },
    {
      key: "routines",
      label: "My Routines",
      icon: "🏠",
      render: () => <HomeProfile householdId={householdId} />,
    },
    {
      key: "occasion",
      label: "Occasion Overlay",
      icon: "🗣️",
      render: () => (
        <ContextNotes
          householdId={householdId}
          refreshKey={overlayVersion}
          onOverlayChange={bump}
        />
      ),
    },
    {
      key: "adapted",
      label: "Adapted Routine",
      icon: "🗓️",
      render: () => (
        <AdjustedRoutine
          householdId={householdId}
          refreshKey={overlayVersion}
          onOverlayChange={bump}
        />
      ),
    },
    {
      key: "conditional",
      label: "Conditional Patterns",
      icon: "🌡️",
      render: () => <ContextualPatterns householdId={householdId} />,
    },
  ];
  const active = sections.find((s) => s.key === openSection);

  return (
    <div className="pp-app min-h-full" data-ptheme={theme}>
      <div className="mx-auto flex min-h-full max-w-[1500px] flex-col gap-4 p-4">
        {/* Above-the-fold stage: a simple heading + the house map with the
            context generator beside it. Sized to fill the viewport so the
            live context result naturally sits below, revealed on scroll. */}
        <section className="flex flex-col gap-4 xl:min-h-[calc(100vh-6rem)]">
          <PageHeader
            connected={connected}
            theme={theme}
            onThemeToggle={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
          />

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_360px]">
            <main className="flex flex-col gap-3">
              <HouseFloor
                householdId={householdId}
                activeSet={activeSet}
                anomalyMap={anomalyMap}
                onToggle={toggleDraft}
                busy={busy}
              />
              <Legend dirty={dirty} />
              <DayAdaptationBanner adaptation={context?.day_adaptation} />
            </main>

            <ContextGenerator
              householdId={householdId}
              onHouseholdChange={setHouseholdId}
              simTime={simTime}
              onSimTimeChange={handleSimTime}
              dayType={dayType}
              onDayTypeChange={handleDayType}
              festival={festival}
              onFestivalChange={handleFestival}
              onSeed={handleSeed}
              onRun={() => runCheck()}
              dirty={dirty}
              busy={busy}
            />
          </div>
        </section>

        {/* Below the fold: what the home concludes from the current scene. */}
        <ContextPanel context={context} loading={busy} />

        {/* Explore drawer — collapsed by default to keep the page uncluttered. */}
        <ExploreDrawer
          sections={sections}
          openKey={openSection}
          active={active}
          onToggle={(k) => setOpenSection((cur) => (cur === k ? null : k))}
        />

        {toast && (
          <div
            className={[
              "fixed bottom-5 left-1/2 -translate-x-1/2 rounded-xl px-4 py-2 text-sm font-medium shadow-xl",
              toast.ok
                ? "bg-emerald-500/90 text-white"
                : "bg-red-500/90 text-white",
            ].join(" ")}
          >
            {toast.msg}
          </div>
        )}

        <AlexaNotification
          notifications={alexaQueue}
          onDismiss={(id) => setAlexaQueue((q) => q.filter((n) => n.id !== id))}
          onDismissAll={() => setAlexaQueue([])}
          maxVisible={4}
        />
      </div>
    </div>
  );
}

// Simple page heading — the app title plus the global connection + theme
// controls. Kept intentionally minimal so the house map stays the focus.
function PageHeader({ connected, theme, onThemeToggle }) {
  return (
    <header className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-700/70 bg-slate-900/70 px-5 py-3 backdrop-blur">
      <span className="grid h-10 w-10 place-items-center rounded-xl bg-[var(--pp-accent)] text-xl shadow-lg">
        🏠
      </span>
      <div className="leading-tight">
        <h1 className="text-lg font-bold text-slate-100">Smart Home Intelligence</h1>
        <p className="text-xs text-slate-400">Context-aware · deterministic patterns</p>
      </div>

      <div className="ml-auto flex items-center gap-2">
        <span
          className={[
            "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium",
            connected
              ? "bg-emerald-500/15 text-emerald-300"
              : "bg-red-500/15 text-red-300",
          ].join(" ")}
        >
          <span className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-400" : "bg-red-400"}`} />
          {connected ? "API connected" : "API offline"}
        </span>
        <button
          onClick={onThemeToggle}
          title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          className="grid h-9 w-9 place-items-center rounded-lg border border-slate-700 bg-slate-800 text-base text-slate-300 transition hover:border-slate-500"
        >
          {theme === "dark" ? "☀️" : "🌙"}
        </button>
      </div>
    </header>
  );
}

// The live context result (the context-generator output). Sits below the map,
// full-width, revealed on scroll.
function ContextPanel({ context, loading }) {
  return (
    <aside className="flex flex-col rounded-2xl border border-slate-700/60 bg-slate-900/60 backdrop-blur">
      <div className="flex items-center gap-2 border-b border-slate-700/60 px-4 py-3">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-[var(--pp-blue-weak)] text-base">
          🧭
        </span>
        <div className="leading-tight">
          <h2 className="text-sm font-bold text-slate-100">Live Context</h2>
          <p className="text-xs text-slate-400">What the home concludes right now</p>
        </div>
      </div>
      <div className="max-h-[70vh] flex-1 overflow-y-auto p-3">
        <ContextView context={context} loading={loading} />
      </div>
    </aside>
  );
}

// Row of heading buttons that reveal one panel at a time below them.
function ExploreDrawer({ sections, openKey, active, onToggle }) {
  return (
    <section className="rounded-2xl border border-slate-700/60 bg-slate-900/50 p-3">
      <div className="mb-1 flex items-center gap-2 px-1">
        <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
          Explore
        </span>
        <span className="text-xs text-slate-500">
          — details are tucked away; open what you need
        </span>
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

// Shows how the learned routines were adapted for the simulated day: on a
// weekend / festival, weekday-only routines are paused so they don't false-flag.
function DayAdaptationBanner({ adaptation }) {
  if (!adaptation || !adaptation.active) return null;
  const { day_type, festival, paused, kept_count, llm_powered } = adaptation;
  const dayLabel = festival || (day_type === "weekend" ? "the weekend" : "today");
  return (
    <section className="overflow-hidden rounded-2xl border border-amber-500/40 bg-amber-500/[0.06]">
      <div className="flex flex-wrap items-center gap-2 px-4 py-2.5">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-amber-500/20 text-base">
          🗓️
        </span>
        <div className="leading-tight">
          <p className="text-sm font-bold text-amber-100">
            Routines adapted for {dayLabel}
          </p>
          <p className="text-xs text-amber-200/70">
            {paused.length} weekday-only {paused.length === 1 ? "routine" : "routines"} paused ·{" "}
            {kept_count} still expected ·{" "}
            {llm_powered ? "decided by LLM" : "keyword fallback"}
          </p>
        </div>
      </div>
      <ul className="flex flex-col gap-1 px-4 pb-3">
        {paused.map((p) => (
          <li
            key={p.pattern_id}
            className="flex items-start gap-2 rounded-lg border border-amber-500/20 bg-slate-950/30 px-2.5 py-1.5"
          >
            <span className="mt-0.5 text-xs">⛔</span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm text-slate-200">{p.description}</p>
              <p className="text-xs italic text-amber-200/60">↳ {p.reason}</p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Legend({ dirty }) {
  const items = [
    { c: "border-slate-700 bg-slate-800/40", t: "Off" },
    { c: "active-glow border-sky-400/50 bg-sky-400/10", t: "On" },
    { c: "anomaly-pulse border-red-500/70 bg-red-500/10", t: "Anomaly" },
  ];
  return (
    <div className="flex flex-wrap items-center gap-4 rounded-xl border border-slate-700/50 bg-slate-900/40 px-4 py-2.5 text-xs text-slate-400">
      <span className="font-semibold uppercase tracking-wider text-slate-500">
        Legend
      </span>
      {items.map((i) => (
        <span key={i.t} className="flex items-center gap-1.5">
          <span className={`h-4 w-6 rounded-md border ${i.c}`} />
          {i.t}
        </span>
      ))}
      <span className="ml-auto text-slate-500">
        {dirty
          ? "⚠ Scenario changed — hit Run to re-check anomalies"
          : "Paint device states · set the clock · hit Run to detect anomalies"}
      </span>
    </div>
  );
}
