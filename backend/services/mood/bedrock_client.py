"""
Mood Analysis Client — Dual provider:
  Primary: AWS Bedrock (Nvidia Nemotron Super 3 120B)
  Backup:  Groq (LLaMA 3.3 70B)

Audio transcription always uses Groq Whisper (Bedrock doesn't do STT).
Includes response caching for identical text inputs.
"""
import json
import logging
import base64
import tempfile
import os
from typing import Optional

import httpx

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import settings
from services.llm_cache import mood_cache, make_cache_key

logger = logging.getLogger(__name__)

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_WHISPER_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


MOOD_ANALYSIS_PROMPT = """You are a mood and cognitive load analyzer for a smart home AI assistant.

Analyze the user's speech for emotional state and cognitive load. Consider word choice, sentence structure, expressed emotions, and urgency.

Respond with JSON only:
{
  "mood": "one of: calm, happy, stressed, anxious, frustrated, sad, energetic, tired, neutral",
  "confidence": 0.0-1.0,
  "cognitive_load": "one of: low, moderate, high, overloaded",
  "speech_features": {
    "sentiment": "positive/negative/neutral",
    "complexity": "simple/moderate/complex",
    "urgency": "low/medium/high"
  },
  "reasoning": "Brief explanation"
}"""


class MoodAnalyzer:
    """
    Dual-provider mood analyzer:
    - STT: Groq Whisper (always — Bedrock doesn't offer Whisper)
    - Mood analysis: Bedrock primary, Groq backup
    """

    def __init__(self):
        self.provider = settings.llm_provider
        self.bedrock_model_id = settings.bedrock_model_id
        self.groq_api_key = settings.groq_api_key
        self.groq_model = settings.groq_llm_model
        logger.info(
            f"Mood analyzer initialized: provider={self.provider}, "
            f"bedrock_model={self.bedrock_model_id}, "
            f"groq_key={'configured' if self.groq_api_key else 'NOT SET'}"
        )

    # ─── Speech-to-Text (always Groq Whisper) ────────────────────────────────

    async def transcribe_audio(self, audio_base64: str, audio_format: str = "webm") -> str:
        """Transcribe audio using Groq Whisper."""
        if not self.groq_api_key:
            raise Exception("GROQ_API_KEY not configured — needed for Whisper STT.")

        audio_bytes = base64.b64decode(audio_base64)
        suffix = f".{audio_format}"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                with open(tmp_path, "rb") as audio_file:
                    response = await client.post(
                        GROQ_WHISPER_URL,
                        headers={"Authorization": f"Bearer {self.groq_api_key}"},
                        files={"file": (f"audio{suffix}", audio_file, f"audio/{audio_format}")},
                        data={"model": "whisper-large-v3-turbo", "response_format": "json"},
                    )

                if response.status_code != 200:
                    logger.error(f"Groq Whisper error: {response.status_code} - {response.text}")
                    raise Exception(f"Whisper failed: {response.text}")

                transcript = response.json().get("text", "")
                logger.info(f"Transcription: '{transcript[:80]}'")
                return transcript
        finally:
            os.unlink(tmp_path)

    # ─── Mood Analysis (Bedrock primary, Groq backup) ────────────────────────

    async def analyze_text_mood(self, text: str) -> dict:
        """Analyze mood from text. Checks cache first, then tries Bedrock/Groq."""
        # Check cache — same text returns same mood
        cache_key = make_cache_key("mood_analysis", text)
        cached = mood_cache.get(cache_key)
        if cached:
            logger.info(f"Mood analysis CACHE HIT — saved LLM call ({mood_cache.stats['hit_rate']} hit rate)")
            return cached

        if self.provider == "bedrock":
            result = await self._analyze_via_bedrock(text)
            if result:
                mood_cache.set(cache_key, result)
                return result
            logger.warning("Bedrock mood analysis failed, falling back to Groq")
            result = await self._analyze_via_groq(text)
            if result:
                mood_cache.set(cache_key, result)
                return result
        else:
            result = await self._analyze_via_groq(text)
            if result:
                mood_cache.set(cache_key, result)
                return result
            logger.warning("Groq mood analysis failed, falling back to Bedrock")
            result = await self._analyze_via_bedrock(text)
            if result:
                mood_cache.set(cache_key, result)
                return result

        raise Exception("Both Bedrock and Groq mood analysis failed")

    # ─── Bedrock (Nvidia Nemotron) ───────────────────────────────────────────

    async def _analyze_via_bedrock(self, text: str) -> Optional[dict]:
        """Call AWS Bedrock Converse API for mood analysis."""
        try:
            import asyncio
            import boto3

            client = boto3.client(
                "bedrock-runtime",
                region_name=settings.aws_region,
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
            )

            def _sync_call():
                response = client.converse(
                    modelId=self.bedrock_model_id,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"text": f"{MOOD_ANALYSIS_PROMPT}\n\n---\n\nUser speech: \"{text}\""}
                            ],
                        }
                    ],
                    inferenceConfig={
                        "temperature": 0.3,
                        "maxTokens": 512,
                    },
                )
                output = response.get("output", {})
                message = output.get("message", {})
                content_blocks = message.get("content", [])
                response_text = ""
                for block in content_blocks:
                    if "text" in block:
                        response_text = block["text"]
                        break
                return response_text

            response_text = await asyncio.to_thread(_sync_call)
            if not response_text:
                return None

            # Parse JSON (handle markdown code blocks)
            response_text = response_text.strip()
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                response_text = "\n".join(lines)

            result = json.loads(response_text)
            logger.info("Bedrock mood analysis complete")
            return result

        except ImportError:
            logger.error("boto3 not installed — cannot use Bedrock")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Bedrock returned invalid JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Bedrock mood analysis error: {type(e).__name__}: {e}")
            return None

    # ─── Groq (Backup) ───────────────────────────────────────────────────────

    async def _analyze_via_groq(self, text: str) -> Optional[dict]:
        """Call Groq API for mood analysis (backup)."""
        if not self.groq_api_key:
            logger.warning("GROQ_API_KEY not set, skipping Groq")
            return None

        payload = {
            "model": self.groq_model,
            "messages": [
                {"role": "system", "content": MOOD_ANALYSIS_PROMPT},
                {"role": "user", "content": f'User speech: "{text}"'},
            ],
            "temperature": 0.3,
            "max_tokens": 512,
            "response_format": {"type": "json_object"},
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    GROQ_CHAT_URL,
                    headers={
                        "Authorization": f"Bearer {self.groq_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )

                if response.status_code != 200:
                    logger.error(f"Groq LLM error: {response.status_code} - {response.text}")
                    return None

                result = response.json()
                content = result["choices"][0]["message"]["content"]
                logger.info("Groq mood analysis complete")
                return json.loads(content)

        except Exception as e:
            logger.error(f"Groq mood analysis error: {type(e).__name__}: {e}")
            return None

    # ─── Combined: Audio → Transcript → Mood ────────────────────────────────

    async def analyze_speech_mood(self, audio_base64: str, audio_format: str = "webm") -> dict:
        """Full pipeline: Audio → Whisper → LLM → Mood."""
        transcript = await self.transcribe_audio(audio_base64, audio_format)

        if not transcript.strip():
            return {
                "mood": "neutral",
                "confidence": 0.3,
                "cognitive_load": "moderate",
                "speech_features": {"transcript": ""},
                "reasoning": "No speech detected in audio",
            }

        result = await self.analyze_text_mood(transcript)
        if "speech_features" not in result:
            result["speech_features"] = {}
        result["speech_features"]["transcript"] = transcript
        return result


# Singleton (kept as bedrock_analyzer for compatibility with main.py imports)
bedrock_analyzer = MoodAnalyzer()
