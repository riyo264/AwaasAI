import { DEVICE_KIND } from "../../config/houseLayout.js";

// A single interactive device pinned at its physical spot on the floor plan.
// Click to toggle ON/OFF (OPEN/CLOSE for doors) — same semantics as before.
// Visual states: OFF (dim), ON (glow), anomalous (pulsing red ring + tooltip).
export default function DeviceSpot({ device, isOn, anomaly, onToggle, busy }) {
  const kind = DEVICE_KIND[device.type] || DEVICE_KIND.light;
  const isAnomaly = Boolean(anomaly);
  const pos = device.pos || { x: 50, y: 50 };

  return (
    <button
      type="button"
      disabled={busy}
      onClick={() => onToggle(device, isOn)}
      title={isAnomaly ? anomaly.detail : `${device.label} — ${isOn ? "ON" : "OFF"}`}
      className="group absolute z-10 flex -translate-x-1/2 -translate-y-1/2 flex-col items-center disabled:opacity-60"
      style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
    >
      <span
        className={[
          "relative grid h-12 w-12 place-items-center rounded-full border-2 text-2xl transition-transform group-hover:scale-110",
          isAnomaly
            ? "anomaly-pulse border-red-500/80 bg-red-500/15"
            : isOn
              ? "active-glow border-sky-400/60"
              : "border-slate-600/70 bg-slate-800/70",
        ].join(" ")}
        style={{
          background: !isAnomaly && isOn ? `${kind.onColor}2e` : undefined,
          filter: isOn || isAnomaly ? "none" : "grayscale(0.7) opacity(0.85)",
        }}
      >
        {kind.icon}
        <span
          className={[
            "absolute -right-1 -top-1 h-3.5 w-3.5 rounded-full border-2 border-slate-950",
            isAnomaly ? "bg-red-500" : isOn ? "bg-sky-400" : "bg-slate-600",
          ].join(" ")}
        />
      </span>
      <span className="pointer-events-none mt-1 max-w-28 truncate rounded-md bg-slate-950/75 px-1.5 py-0.5 text-[13px] font-semibold leading-tight text-slate-100">
        {device.label}
      </span>
      <span
        className={[
          "mt-0.5 text-[11px] font-bold uppercase tracking-wide",
          isAnomaly ? "text-red-300" : isOn ? "text-sky-300" : "text-slate-400",
        ].join(" ")}
      >
        {isAnomaly ? "⚠ anomaly" : statusLabel(device.type, isOn)}
      </span>
    </button>
  );
}

function statusLabel(type, on) {
  if (type === "door") return on ? "open" : "closed";
  return on ? "on" : "off";
}
