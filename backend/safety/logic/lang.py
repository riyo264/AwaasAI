"""Language directive for the safety narrator + Guardian LLMs.

Mirror of ``patterns.logic.lang`` — the safety engine is an independent twin, so
it keeps its own copy. Localises only human-facing TEXT; JSON keys stay English.
"""
from __future__ import annotations

_LANG = {
    "en": None,
    "hi": "Hindi (हिंदी, in Devanagari script)",
    "hinglish": "Hinglish — Hindi written in the Roman/Latin script the way Indian "
                "families chat (e.g. 'dadi, aap theek ho? main family ko bata deta hoon')",
    "ta": "Tamil (தமிழ், in Tamil script)",
    "te": "Telugu (తెలుగు, in Telugu script)",
    "bn": "Bengali (বাংলা, in Bengali script)",
    "mr": "Marathi (मराठी, in Devanagari script)",
}


def directive(language: str | None) -> str:
    name = _LANG.get((language or "en").strip().lower())
    if not name:
        return ""
    return (
        "\n\nLANGUAGE: Write ALL human-facing text values (the spoken line, the "
        f"check-in question, the family message, the reason) ENTIRELY in {name}. "
        "Keep the JSON keys and any device ids in English. Sound natural and native "
        "to a family in India, warm and caring — not a stiff translation."
    )
