// Global narration language — a tiny module store the API clients + the TTS read
// at call time, so switching language instantly affects every new LLM narration
// and the spoken voice, without threading props through every component.

export const LANGS = [
  { code: "en", label: "English", flag: "🇬🇧", bcp47: "en-IN" },
  { code: "hi", label: "हिंदी", flag: "🇮🇳", bcp47: "hi-IN" },
  { code: "hinglish", label: "Hinglish", flag: "🇮🇳", bcp47: "en-IN" },
  { code: "ta", label: "தமிழ்", flag: "🇮🇳", bcp47: "ta-IN" },
  { code: "te", label: "తెలుగు", flag: "🇮🇳", bcp47: "te-IN" },
  { code: "bn", label: "বাংলা", flag: "🇮🇳", bcp47: "bn-IN" },
  { code: "mr", label: "मराठी", flag: "🇮🇳", bcp47: "mr-IN" },
];

const KEY = "awaas_lang";
let current = "en";
try {
  const saved = localStorage.getItem(KEY);
  if (saved && LANGS.some((l) => l.code === saved)) current = saved;
} catch {
  /* ignore */
}

const subscribers = new Set();

export function getLang() {
  return current;
}

export function getBcp47() {
  return (LANGS.find((l) => l.code === current) || LANGS[0]).bcp47;
}

export function setLang(code) {
  current = code;
  try {
    localStorage.setItem(KEY, code);
  } catch {
    /* ignore */
  }
  subscribers.forEach((fn) => fn(code));
}

export function subscribeLang(fn) {
  subscribers.add(fn);
  return () => subscribers.delete(fn);
}
