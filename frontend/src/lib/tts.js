// Shared text-to-speech helpers so every spoken line (the Alexa notification
// stack, the Safety walkthrough) uses the same warm, natural voice instead of
// the browser's default robotic one.
import { getBcp47 } from "./lang.js";

// Voices load asynchronously in Chrome/Edge — cache them and refresh when the
// browser fires `voiceschanged`, so we always score against the full list.
let _cachedVoices = [];
function loadVoices() {
  const v =
    (typeof window !== "undefined" && window.speechSynthesis?.getVoices?.()) || [];
  if (v.length) _cachedVoices = v;
  return _cachedVoices;
}
if (typeof window !== "undefined" && window.speechSynthesis) {
  loadVoices();
  window.speechSynthesis.addEventListener?.("voiceschanged", loadVoices);
}

// Score a voice for how HUMAN it sounds. The naive first-match pick usually lands
// on the robotic local SAPI voices (Zira/David/Mark) — this instead strongly
// prefers modern neural/"Natural"/online voices (Edge's "… Online (Natural)",
// Chrome's "Google …") and known friendly assistant voices, penalising the old
// robotic ones. Language matching is handled by the pool in pickVoice.
function voiceQuality(v) {
  const name = (v.name || "").toLowerCase();
  let s = 0;
  if (/natural|neural/.test(name)) s += 70; // MS "Online (Natural)" neural voices
  if (v.localService === false) s += 30; // cloud/online voices are higher quality
  if (/google/.test(name)) s += 35; // Google voices sound natural
  if (
    /\b(aria|jenny|ava|emma|guy|michelle|sonia|libby|ryan|natasha|clara|neerja|prabhat|swara|kavya|rishi|samantha|allison|siri|nicky|serena|karen|moira)\b/.test(
      name,
    )
  )
    s += 22;
  if (
    /\b(david|mark|zira|hazel|george|susan|richard|eloquence|espeak|compact|pico|fred|albert|junior|ralph)\b/.test(
      name,
    )
  )
    s -= 45; // the classic robotic voices
  return s;
}

// Pick the most natural voice for the narration language: exact locale (hi-IN),
// then base language (hi), then any — and within that pool, the best-sounding.
export function pickVoice(bcp47 = "en-IN") {
  const voices = loadVoices();
  if (!voices.length) return null;
  const target = bcp47.toLowerCase();
  const base = target.split("-")[0];
  const exact = voices.filter((v) => (v.lang || "").toLowerCase() === target);
  const byBase = voices.filter((v) => (v.lang || "").toLowerCase().startsWith(base));
  const pool = exact.length ? exact : byBase.length ? byBase : voices;
  let best = pool[0];
  let bestScore = -Infinity;
  for (const v of pool) {
    const q = voiceQuality(v);
    if (q > bestScore) {
      bestScore = q;
      best = v;
    }
  }
  return best;
}

// Build a warm, natural-sounding utterance. A slightly slower rate reads calmer
// and less "computery"; pitch stays neutral so neural voices aren't distorted.
export function makeUtterance(text) {
  const utter = new SpeechSynthesisUtterance(text);
  const bcp47 = getBcp47();
  utter.lang = bcp47;
  const voice = pickVoice(bcp47);
  if (voice) utter.voice = voice;
  utter.rate = 0.95;
  utter.pitch = 1.0;
  utter.volume = 1;
  return utter;
}

// Fire-and-forget: cancel any current speech and speak one line naturally.
export function speak(text) {
  try {
    if (!text || typeof window === "undefined" || !("speechSynthesis" in window)) return;
    const synth = window.speechSynthesis;
    synth.cancel();
    // Some browsers need a tick after cancel() before speak() takes effect.
    setTimeout(() => synth.speak(makeUtterance(text)), 60);
  } catch {
    /* best-effort */
  }
}
