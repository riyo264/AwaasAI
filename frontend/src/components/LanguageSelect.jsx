import { useState } from "react";
import { Languages } from "lucide-react";
import { LANGS, getLang, setLang } from "../lib/lang.js";

// Global language picker for the assistant's LLM narration + spoken voice.
export default function LanguageSelect() {
  const [lang, setL] = useState(getLang());
  return (
    <label className="flex items-center gap-2 text-xs text-gray-400">
      <Languages className="w-4 h-4 shrink-0 text-indigo-400" />
      <select
        value={lang}
        onChange={(e) => { setL(e.target.value); setLang(e.target.value); }}
        title="Assistant voice & narration language"
        className="w-full rounded-lg border border-gray-700 bg-gray-800 px-2 py-1.5 text-xs font-medium text-gray-100 outline-none focus:border-indigo-500"
      >
        {LANGS.map((l) => (
          <option key={l.code} value={l.code}>
            {l.label}
          </option>
        ))}
      </select>
    </label>
  );
}
