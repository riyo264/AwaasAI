import { DEVICE_KIND } from "../../config/houseLayout.js";

// A single interactive device. Click to toggle ON/OFF (OPEN/CLOSE for doors).
// Visual states: OFF (dim), ON (glow), anomalous (pulsing red ring + tooltip).
export default function DeviceTile({ device, isOn, anomaly, onToggle, busy }) {
  const kind = DEVICE_KIND[device.type] || DEVICE_KIND.light;
  const isAnomaly = Boolean(anomaly);

  return (
    <button
      type="button"
      disabled={busy}
      onClick={() => onToggle(device, isOn)}
      title={isAnomaly ? anomaly.detail : `${device.label} — ${isOn ? "ON" : "OFF"}`}
      className={[
        "group relative flex w-full items-center gap-2 rounded-xl border px-2.5 py-2 text-left transition-all",
        "backdrop-blur-sm disabled:opacity-60",
        isAnomaly
          ? "anomaly-pulse border-red-500/70 bg-red-500/10"
          : isOn
            ? "active-glow border-sky-400/50 bg-sky-400/10"
            : "border-slate-700/70 bg-slate-800/40 hover:border-slate-500",
      ].join(" ")}
    >
      <span
        className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-lg transition-transform group-hover:scale-110"
        style={{
          background: isOn ? `${kind.onColor}22` : "var(--color-slate-800)",
          filter: isOn ? "none" : "grayscale(0.7) opacity(0.8)",
        }}
      >
        {kind.icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-xs font-medium text-slate-100">
          {device.label}
        </span>
        <span
          className={[
            "text-[10px] font-semibold uppercase tracking-wide",
            isAnomaly ? "text-red-300" : isOn ? "text-sky-300" : "text-slate-500",
          ].join(" ")}
        >
          {isAnomaly ? "⚠ anomaly" : isOn ? statusLabel(device.type, true) : statusLabel(device.type, false)}
        </span>
      </span>
    </button>
  );
}

function statusLabel(type, on) {
  if (type === "door") return on ? "open" : "closed";
  return on ? "on" : "off";
}
