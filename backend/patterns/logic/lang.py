"""Language directive for the narrator LLMs.

The models (Groq LLaMA, Gemini) are natively multilingual, so responding in an
Indian language is just a prompt instruction. We only ever localise the
human-facing TEXT values; JSON keys / device ids stay English so parsing is safe.
"""
from __future__ import annotations

# key -> how to describe the language to the model
_LANG = {
    "en": None,
    "hi": "Hindi (हिंदी, in Devanagari script)",
    "hinglish": "Hinglish — Hindi written in the Roman/Latin script the way Indian "
                "families chat (e.g. 'gas band kar dijiye, cooker ki seeti baj gayi')",
    "ta": "Tamil (தமிழ், in Tamil script)",
    "te": "Telugu (తెలుగు, in Telugu script)",
    "bn": "Bengali (বাংলা, in Bengali script)",
    "mr": "Marathi (मराठी, in Devanagari script)",
}


def directive(language: str | None) -> str:
    """A system-prompt suffix that switches the spoken output language.

    Returns "" for English (or unknown) so English behaviour is unchanged.
    """
    name = _LANG.get((language or "en").strip().lower())
    if not name:
        return ""
    return (
        "\n\nLANGUAGE: Write ALL human-facing text values (the spoken line, any "
        f"prompt, message, or explanation) ENTIRELY in {name}. Keep the JSON keys "
        "and any device ids in English. Sound natural and native to a home in "
        "India — not a stiff word-for-word translation."
    )
