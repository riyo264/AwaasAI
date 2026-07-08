import Room from "./Room.jsx";
import { HOUSEHOLDS, floorPlanFor } from "../../config/houseLayout.js";

// Architectural top-view floor plan: rooms sit at their real positions inside
// an outer load-bearing wall (porch / terrace / garden outside it), and every
// appliance is pinned at its physical spot in its room.
export default function HouseFloor({
  householdId,
  activeSet,
  anomalyMap,
  onToggle,
  busy,
}) {
  const plan = floorPlanFor(householdId);
  const devices = HOUSEHOLDS[householdId].devices;
  const devicesByRoom = (roomKey) => devices.filter((d) => d.room === roomKey);

  return (
    <div className="relative rounded-3xl border border-slate-700/50 bg-slate-950/40 p-4 shadow-2xl">
      {/* House outline label */}
      <div className="pointer-events-none absolute right-5 top-4 z-20 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-600">
        Top View · Live
      </div>

      <div
        className="relative w-full"
        style={{ aspectRatio: "16 / 11", minHeight: "520px" }}
      >
        {plan.spaces.map((space) => (
          <Room
            key={space.key}
            space={space}
            devices={devicesByRoom(space.key)}
            activeSet={activeSet}
            anomalyMap={anomalyMap}
            onToggle={onToggle}
            busy={busy}
          />
        ))}

        {/* Outer load-bearing wall, drawn over the room partitions. */}
        <div
          className="pointer-events-none absolute z-4 border-[3px]"
          style={{
            left: `${plan.wall.x}%`,
            top: `${plan.wall.y}%`,
            width: `${plan.wall.w}%`,
            height: `${plan.wall.h}%`,
            borderColor: "var(--pp-border-strong)",
          }}
        />
      </div>
    </div>
  );
}
