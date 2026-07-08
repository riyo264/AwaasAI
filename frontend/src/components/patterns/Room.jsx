import DeviceSpot from "./DeviceSpot.jsx";
import { ROOMS } from "../../config/houseLayout.js";

// One space on the floor plan, drawn at its real position: wall partitions,
// door openings, an accent-tinted floor, and devices at their physical spots.
// Outdoor spaces (porch / terrace / garden) get dashed open-air boundaries.
export default function Room({ space, devices, activeSet, anomalyMap, onToggle, busy }) {
  const meta = ROOMS[space.key];
  const name = space.name ?? meta?.name ?? space.key;
  const accent = meta?.accent ?? "#64748b";
  const hasDevices = devices.length > 0;

  return (
    <div
      className={[
        "absolute",
        space.outdoor
          ? "rounded-md border-2 border-dashed border-slate-600/60"
          : "border-2",
      ].join(" ")}
      style={{
        left: `${space.x}%`,
        top: `${space.y}%`,
        width: `${space.w}%`,
        height: `${space.h}%`,
        borderColor: space.outdoor ? undefined : "var(--pp-border-strong)",
        background: hasDevices
          ? `color-mix(in srgb, ${accent} 9%, var(--pp-inset))`
          : "var(--pp-inset)",
      }}
    >
      {/* Room label */}
      <div className="pointer-events-none absolute left-2 top-1.5 z-6 flex items-center gap-1.5">
        <span
          className="h-2 w-2 shrink-0 rounded-full"
          style={{
            background: accent,
            boxShadow: hasDevices ? `0 0 8px ${accent}` : "none",
            opacity: hasDevices ? 1 : 0.45,
          }}
        />
        <span
          className={[
            "truncate text-[11px] font-bold uppercase tracking-wider",
            hasDevices ? "text-slate-300" : "text-slate-500",
          ].join(" ")}
        >
          {name}
        </span>
      </div>

      {/* Door openings on the walls */}
      {(space.doors || []).map((door, i) => (
        <DoorGap key={i} door={door} />
      ))}

      {/* Devices pinned at their physical positions */}
      {devices.map((d) => (
        <DeviceSpot
          key={d.id}
          device={d}
          isOn={activeSet.has(d.id)}
          anomaly={anomalyMap.get(d.id)}
          onToggle={onToggle}
          busy={busy}
        />
      ))}
    </div>
  );
}

// A door opening: a wooden threshold bar bridging the wall between two spaces.
function DoorGap({ door }) {
  const horizontal = door.side === "top" || door.side === "bottom";
  const style = horizontal
    ? {
        left: `${door.at}%`,
        [door.side]: -8,
        width: 22,
        height: 12,
        transform: "translateX(-50%)",
      }
    : {
        top: `${door.at}%`,
        [door.side]: -8,
        width: 12,
        height: 22,
        transform: "translateY(-50%)",
      };
  return <span className="absolute z-5 rounded-[3px] bg-[#b98a4a]" style={style} />;
}
