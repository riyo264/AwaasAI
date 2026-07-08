// Floor-plan + device catalogue, driven entirely by data so the same canvas
// renders any household.
//
// The house is drawn as an ARCHITECTURAL TOP VIEW (a cross-section from above):
// - FLOOR_PLANS gives every space a real rectangle (x/y/w/h as % of the canvas),
//   an outer load-bearing wall, and door openings between rooms.
// - Each device carries a `pos` — its physical spot inside its room (% of the
//   room rect) — so appliances sit where they would in a real home.
// ROOMS keeps the display name + accent colour per room key. The col/row grid
// fields are ONLY used by the Devices page (DeviceControl), which still lays
// rooms out on a simple 3x3 grid — the Patterns floor plan ignores them.

export const ROOMS = {
  garden: { name: "Garden", col: "1 / 2", row: "1 / 2", accent: "#22c55e" },
  son_room: {
    name: "Son's Room",
    col: "2 / 3",
    row: "1 / 2",
    accent: "#a855f7",
  },
  bedroom: { name: "Bedroom", col: "3 / 4", row: "1 / 2", accent: "#6366f1" },
  porch: { name: "Porch", col: "1 / 2", row: "2 / 3", accent: "#eab308" },
  living_room: {
    name: "Living Room",
    col: "2 / 4",
    row: "2 / 3",
    accent: "#38bdf8",
  },
  entrance: { name: "Entrance", col: "1 / 2", row: "3 / 4", accent: "#f97316" },
  utility: { name: "Utility", col: "2 / 4", row: "3 / 4", accent: "#94a3b8" },

  // --- H003 (Indian-context home) rooms ---
  grandpa_room: { name: "Grandpa's Room", col: "1 / 2", row: "1 / 2", accent: "#f472b6" },
  pooja_room: { name: "Pooja Room", col: "3 / 4", row: "1 / 2", accent: "#fbbf24" },
  kitchen: { name: "Kitchen", col: "2 / 3", row: "2 / 3", accent: "#fb7185" },
  terrace: { name: "Terrace", col: "3 / 4", row: "2 / 3", accent: "#34d399" },
  store_room: { name: "Utility", col: "2 / 3", row: "3 / 4", accent: "#94a3b8" },
  grandma_room: { name: "Grandma's Room", col: "3 / 4", row: "3 / 4", accent: "#c084fc" },
  // H003 rooms that gained smart appliances (4th Devices-page grid row).
  bath: { name: "Bathroom", col: "1 / 2", row: "4 / 5", accent: "#22d3ee" },
  hall: { name: "Hall", col: "2 / 3", row: "4 / 5", accent: "#38bdf8" },
  dining: { name: "Dining", col: "3 / 4", row: "4 / 5", accent: "#f59e0b" },
};

// Per device-type rendering + on/off action semantics.
export const DEVICE_KIND = {
  fan: { icon: "🌀", onAction: "ON", offAction: "OFF", onColor: "#38bdf8" },
  light: { icon: "💡", onAction: "ON", offAction: "OFF", onColor: "#fde047" },
  ac: { icon: "❄️", onAction: "ON", offAction: "OFF", onColor: "#7dd3fc" },
  tv: { icon: "📺", onAction: "ON", offAction: "OFF", onColor: "#a78bfa" },
  motor: { icon: "🛢️", onAction: "ON", offAction: "OFF", onColor: "#fb923c" },
  door: {
    icon: "🚪",
    onAction: "OPEN",
    offAction: "CLOSE",
    onColor: "#f87171",
  },
  // --- Indian-context device kinds (H003) ---
  motor_inverter: { icon: "🔋", onAction: "ON", offAction: "OFF", onColor: "#4ade80" },
  geyser: { icon: "♨️", onAction: "ON", offAction: "OFF", onColor: "#fb7185" },
  stove: { icon: "🔥", onAction: "ON", offAction: "OFF", onColor: "#fb923c" },
  kettle: { icon: "🫖", onAction: "ON", offAction: "OFF", onColor: "#f59e0b" },
  bell: { icon: "🔔", onAction: "ON", offAction: "OFF", onColor: "#facc15" },
  speaker: { icon: "🔊", onAction: "ON", offAction: "OFF", onColor: "#a78bfa" },
  clothesline: { icon: "🧺", onAction: "ON", offAction: "OFF", onColor: "#38bdf8" },
  can: { icon: "🪣", onAction: "ON", offAction: "OFF", onColor: "#60a5fa" },
  // People / care sensors — momentary signals, shown for context.
  presence: { icon: "🧍", onAction: "ARRIVE", offAction: "LEAVE", onColor: "#34d399" },
  activity: { icon: "🚶", onAction: "ACTIVE", offAction: "IDLE", onColor: "#34d399" },
  medicine: { icon: "💊", onAction: "TAKEN", offAction: "PENDING", onColor: "#f472b6" },
};

// ── Architectural floor plans ───────────────────────────────────────────────
// Coordinates are percentages of the plan canvas (x → right, y → down).
// `wall` is the outer load-bearing wall of the built-up area. Spaces outside it
// (porch / terrace / garden) are `outdoor` and drawn with dashed boundaries.
// Spaces whose key is not in any household's device list (Hall, Bath, Dining)
// are ordinary rooms without smart devices — they exist so the plan reads like
// a real home. `doors` are openings on a wall: side + position along that side.
export const FLOOR_PLANS = {
  // Shared plan for H001 / H002 / H004: a compact single-floor home with a
  // side garden, front porch and a central living area.
  generic: {
    wall: { x: 18, y: 14, w: 82, h: 70 },
    spaces: [
      { key: "garden", x: 0, y: 14, w: 18, h: 70, outdoor: true },
      { key: "son_room", x: 18, y: 14, w: 28, h: 30, doors: [{ side: "bottom", at: 60 }] },
      { key: "bath", name: "Bath", x: 18, y: 44, w: 28, h: 16, doors: [{ side: "right", at: 50 }] },
      {
        key: "entrance",
        x: 18, y: 60, w: 28, h: 24,
        doors: [{ side: "bottom", at: 50 }, { side: "right", at: 40 }],
      },
      { key: "utility", x: 46, y: 14, w: 28, h: 30, doors: [{ side: "bottom", at: 50 }] },
      { key: "bedroom", x: 74, y: 14, w: 26, h: 30, doors: [{ side: "bottom", at: 40 }] },
      { key: "living_room", x: 46, y: 44, w: 54, h: 40 },
      { key: "porch", x: 20, y: 84, w: 24, h: 16, outdoor: true },
    ],
  },

  // H003 · Indian-context care home. Front (porch + entrance) faces the bottom;
  // the pooja room and kitchen sit at the back, the terrace opens off the
  // kitchen, and the grandparents' rooms line the quieter left wing.
  H003: {
    wall: { x: 0, y: 15, w: 100, h: 69 },
    spaces: [
      { key: "terrace", x: 64, y: 0, w: 36, h: 15, outdoor: true },
      { key: "grandpa_room", x: 0, y: 15, w: 28, h: 29, doors: [{ side: "right", at: 60 }] },
      { key: "grandma_room", x: 0, y: 44, w: 28, h: 24, doors: [{ side: "right", at: 50 }] },
      { key: "bath", name: "Bath", x: 0, y: 68, w: 28, h: 16, doors: [{ side: "right", at: 40 }] },
      { key: "pooja_room", x: 28, y: 15, w: 22, h: 29, doors: [{ side: "bottom", at: 50 }] },
      { key: "store_room", x: 50, y: 15, w: 14, h: 29, doors: [{ side: "bottom", at: 50 }] },
      {
        key: "kitchen",
        x: 64, y: 15, w: 36, h: 29,
        doors: [{ side: "left", at: 60 }, { side: "top", at: 80 }],
      },
      { key: "hall", name: "Hall", x: 28, y: 44, w: 36, h: 24 },
      { key: "son_room", x: 64, y: 44, w: 36, h: 24, doors: [{ side: "left", at: 50 }] },
      { key: "dining", name: "Dining", x: 64, y: 68, w: 36, h: 16, doors: [{ side: "left", at: 50 }] },
      {
        key: "entrance",
        x: 28, y: 68, w: 36, h: 16,
        doors: [{ side: "top", at: 50 }, { side: "bottom", at: 50 }],
      },
      { key: "porch", x: 30, y: 84, w: 32, h: 16, outdoor: true },
    ],
  },
};

export function floorPlanFor(householdId) {
  return FLOOR_PLANS[householdId] || FLOOR_PLANS.generic;
}

// Households: each device has id, label, type, room, and `pos` — where the
// appliance physically sits inside its room (% of the room's rectangle).
export const HOUSEHOLDS = {
  H001: {
    label: "H001 · Son Departure Home",
    people: ["father", "mother", "son"],
    devices: [
      { id: "son_room_fan", label: "Fan", type: "fan", room: "son_room", pos: { x: 40, y: 45 } },
      { id: "son_room_light", label: "Light", type: "light", room: "son_room", pos: { x: 76, y: 66 } },
      { id: "living_room_ac", label: "AC", type: "ac", room: "living_room", pos: { x: 87, y: 28 } },
      { id: "living_room_tv", label: "TV", type: "tv", room: "living_room", pos: { x: 45, y: 72 } },
      { id: "porch_light", label: "Porch Light", type: "light", room: "porch", pos: { x: 50, y: 42 } },
      {
        id: "water_motor",
        label: "Water Motor",
        type: "motor",
        room: "utility",
        pos: { x: 50, y: 52 },
      },
    ],
  },
  H002: {
    label: "H002 · AC / Motor / Light Home",
    people: ["father", "mother"],
    devices: [
      { id: "bedroom_ac", label: "Bedroom AC", type: "ac", room: "bedroom", pos: { x: 68, y: 40 } },
      {
        id: "living_room_light",
        label: "Light",
        type: "light",
        room: "living_room",
        pos: { x: 26, y: 32 },
      },
      { id: "living_room_ac", label: "AC", type: "ac", room: "living_room", pos: { x: 87, y: 28 } },
      {
        id: "garden_light",
        label: "Garden Light",
        type: "light",
        room: "garden",
        pos: { x: 50, y: 22 },
      },
      { id: "porch_light", label: "Porch Light", type: "light", room: "porch", pos: { x: 50, y: 42 } },
      {
        id: "borewell_motor",
        label: "Borewell Motor",
        type: "motor",
        room: "utility",
        pos: { x: 50, y: 52 },
      },
      { id: "front_door", label: "Front Door", type: "door", room: "entrance", pos: { x: 50, y: 76 } },
    ],
  },
  H004: {
    label: "H004 · Context-Aware Home ✨",
    people: ["father", "mother"],
    devices: [
      { id: "living_room_ac", label: "Living AC", type: "ac", room: "living_room", pos: { x: 87, y: 28 } },
      { id: "bedroom_ac", label: "Bedroom AC", type: "ac", room: "bedroom", pos: { x: 68, y: 40 } },
      { id: "porch_light", label: "Porch Light", type: "light", room: "porch", pos: { x: 50, y: 42 } },
      { id: "water_motor", label: "Water Motor", type: "motor", room: "utility", pos: { x: 50, y: 52 } },
      { id: "mother_presence", label: "Mother", type: "presence", room: "entrance", pos: { x: 50, y: 42 } },
    ],
  },
  H003: {
    label: "H003 · Indian-Context Care Home",
    people: ["grandpa", "grandma", "father", "mother", "son"],
    devices: [
      // Elderly care — the grandparents' rooms in the left wing.
      {
        id: "grandpa_activity",
        label: "Grandpa Activity",
        type: "activity",
        room: "grandpa_room",
        pos: { x: 50, y: 52 },
      },
      {
        id: "grandma_medicine",
        label: "Grandma Medicine",
        type: "medicine",
        room: "grandma_room",
        pos: { x: 50, y: 54 },
      },
      // Morning pooja — mandir room at the back of the hall.
      { id: "pooja_lamp", label: "Pooja Lamp", type: "light", room: "pooja_room", pos: { x: 26, y: 36 } },
      { id: "temple_bell", label: "Temple Bell", type: "bell", room: "pooja_room", pos: { x: 74, y: 36 } },
      {
        id: "bhajan_speaker",
        label: "Bhajan Speaker",
        type: "speaker",
        room: "pooja_room",
        pos: { x: 50, y: 78 },
      },
      // Son departure (ordinary appliances) — ceiling fan mid-room, lamp by the bed.
      { id: "son_room_fan", label: "Fan", type: "fan", room: "son_room", pos: { x: 32, y: 46 } },
      { id: "son_room_light", label: "Light", type: "light", room: "son_room", pos: { x: 72, y: 54 } },
      // Entrance: the smart main-door lock (a real, loggable device).
      { id: "main_door", label: "Main Door", type: "door", room: "entrance", pos: { x: 50, y: 56 } },
      // Bathroom: morning geyser (water heater) + light.
      { id: "bath_geyser", label: "Geyser", type: "geyser", room: "bath", pos: { x: 34, y: 58 } },
      { id: "bath_light", label: "Bath Light", type: "light", room: "bath", pos: { x: 70, y: 58 } },
      // Kitchen: stove + kettle on the back counter, light + water can down front.
      { id: "chai_kettle", label: "Chai Kettle", type: "kettle", room: "kitchen", pos: { x: 62, y: 32 } },
      { id: "kitchen_light", label: "Kitchen Light", type: "light", room: "kitchen", pos: { x: 84, y: 68 } },
      { id: "kitchen_gas_stove", label: "Gas Stove", type: "stove", room: "kitchen", pos: { x: 30, y: 32 } },
      { id: "water_can_refill", label: "Water Can", type: "can", room: "kitchen", pos: { x: 30, y: 82 } },
      // Hall: the family TV + light — the main evening living space.
      { id: "hall_tv", label: "TV", type: "tv", room: "hall", pos: { x: 36, y: 48 } },
      { id: "hall_light", label: "Hall Light", type: "light", room: "hall", pos: { x: 68, y: 48 } },
      // Dining: the dinner-table light.
      { id: "dining_light", label: "Dining Light", type: "light", room: "dining", pos: { x: 50, y: 58 } },
      // Terrace — clothesline in the open air off the kitchen.
      {
        id: "terrace_clothesline",
        label: "Clothesline",
        type: "clothesline",
        room: "terrace",
        pos: { x: 50, y: 50 },
      },
      // Porch security light over the front steps.
      { id: "porch_light", label: "Porch Light", type: "light", room: "porch", pos: { x: 50, y: 46 } },
      // Utility/store: overhead-tank motor above, inverter below (stacked to fit).
      { id: "water_motor", label: "Water Motor", type: "motor", room: "store_room", pos: { x: 50, y: 32 } },
      {
        id: "inverter",
        label: "Inverter",
        type: "motor_inverter",
        room: "store_room",
        pos: { x: 50, y: 74 },
      },
    ],
  },
};

// Which rooms to render for a given household (only rooms that hold a device).
export function roomsForHousehold(householdId) {
  const used = new Set(HOUSEHOLDS[householdId].devices.map((d) => d.room));
  return Object.entries(ROOMS)
    .filter(([key]) => used.has(key))
    .map(([key, room]) => ({ key, ...room }));
}
