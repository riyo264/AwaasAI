"""
Action Engine — Dual-provider LLM powered.

Primary: AWS Bedrock (Nvidia Nemotron Super 3 120B)
Backup:  Groq (LLaMA 3.3 70B)

Takes ALL signals (voice, behavior, patterns) and decides device actions.
Includes response caching to save tokens on repetitive inputs.
"""

import json
import logging
from typing import Optional
import functools
import httpx

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import settings
from services.llm_cache import action_cache, make_cache_key

logger = logging.getLogger(__name__)

@functools.lru_cache(maxsize=1)
def _verify_ctx():
    """TLS verification for outbound Groq calls.

    Behind a corporate TLS-intercepting proxy the proxy's root CA lives in the
    OS trust store but NOT in certifi's bundle, so httpx's default verification
    fails with CERTIFICATE_VERIFY_FAILED and the action engine silently falls
    back to preset logic. ``truststore`` builds an SSLContext backed by the OS
    trust store. Scoped to the httpx client only (never the global ssl module)
    so boto3 is unaffected. Falls back to httpx's default when unavailable.
    """
    try:
        import ssl

        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:  # pragma: no cover - default verification is fine
        return True

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

ACTION_ENGINE_PROMPT = """You are MoodSense AI — an intelligent smart home environment controller connected to Alexa.

You receive input signals about the user and must decide EXACTLY what device actions to take.

## INPUT SIGNALS (you may receive any combination):

### 1. VOICE/MOOD DATA (from speech analysis)
- What the user said (transcribed text)
- Detected mood and confidence
- Speech characteristics

### 2. BEHAVIOR TRACKING DATA (from Alexa-connected devices)
- Cognitive load level: how mentally strained the user is
- Agitation score: 0-100%
- Patterns: aggressive_tapping, fast_scrolling, prolonged_inactivity, erratic_swiping

### 3. PATTERN RECOGNITION DATA (from device usage history)
- Learned household routines and confidence scores
- Anomalies: devices left on, exceeded duration
- People home/away

## DEVICES YOU CONTROL
- Lights: color (hex), brightness (0-100), color_temperature_k (2000=warm, 6500=cool)
- Music: genre (ambient, nature_sounds, lo-fi, classical, uplifting, electronic, sleep, upbeat, or null), volume (0-100)
- Notifications: mode (normal, reduced, dnd)

## RULES
- Stressed/Anxious → Cool blue/lavender, dim, ambient/nature sounds
- Frustrated → Teal tones, lo-fi beats, medium brightness
- Sad → Warm gold, uplifting music, brighter
- Tired → Very dim warm orange, sleep sounds, DND
- Happy/Energetic → Bright vibrant, upbeat music
- High cognitive load → Reduce ALL stimuli

## NOTIFICATION RULES (STRICT)
- HIGH cognitive load or OVERLOADED → notification_mode: "normal" (user is focused, don't hide important things)
- MODERATE cognitive load → notification_mode: "normal"
- LOW cognitive load (idle/resting) → notification_mode: "reduced" (user is resting, minimize disturbances)
- FRUSTRATED/STRESSED → notification_mode: "reduced" (reduce distractions)

- If behavior contradicts speech, trust behavior
- Consider the time of day

## ALEXA RESPONSE TONE (CRITICAL — follow strictly)
- HIGH cognitive load / FRUSTRATED / STRESSED / OVERLOADED: VERY short (5-8 words). Just act. Examples: "Adjusting the room." or "On it." or "Calming things down."
- LOW cognitive load / TIRED / IDLE / SLEEPING: Gentle and slightly longer (1-2 short sentences, caring tone). Examples: "It looks like you're winding down. I've dimmed the lights and set things quiet." or "Rest easy — everything's set for sleep."
- CALM / NEUTRAL / HAPPY: Warm and conversational (1-2 sentences). Show personality.
- SAD: Gentle, brief, one supportive sentence.
- IMPORTANT: The alexa_response MUST be different every time. Never repeat the exact same phrase. Vary your wording based on context, time, and current state.

Respond with JSON only:
{
  "mood_assessment": "what you think the user is experiencing",
  "detected_mood": "calm/happy/stressed/anxious/frustrated/sad/energetic/tired/neutral",
  "cognitive_load": "low/moderate/high/overloaded",
  "confidence": 0.0-1.0,
  "actions": {
    "light_color": "#hex",
    "light_brightness": 0-100,
    "light_temperature_k": 2000-6500,
    "music_genre": "genre or null",
    "music_volume": 0-100,
    "notification_mode": "normal/reduced/dnd"
  },
  "alexa_response": "What Alexa says to the user",
  "reasoning": "Why you chose these actions"
}"""


class ActionEngine:
    """Dual-provider action decision engine: Bedrock primary, Groq backup."""

    def __init__(self):
        self.provider = settings.llm_provider  # "bedrock" or "groq"
        self.bedrock_model_id = settings.bedrock_model_id
        self.groq_api_key = settings.groq_api_key
        self.groq_model = settings.groq_llm_model
        logger.info(
            f"Action Engine initialized: provider={self.provider}, "
            f"bedrock_model={self.bedrock_model_id}, groq_model={self.groq_model}"
        )

    async def decide_actions(
        self,
        mood=None,
        mood_confidence: float = 0.0,
        speech_text: Optional[str] = None,
        speech_features: Optional[dict] = None,
        behavior_result=None,
        pattern_context: Optional[dict] = None,
        room_id: str = "living-room",
        time_of_day: Optional[str] = None,
    ) -> dict:
        """Send all signals to LLM and get actions back. Bedrock first, Groq fallback."""
        user_context = self._build_context(
            mood, mood_confidence, speech_text, speech_features,
            behavior_result, pattern_context, room_id, time_of_day,
        )

        # Check cache first — identical context returns cached response
        cache_key = make_cache_key("action_engine", user_context)
        cached = action_cache.get(cache_key)
        if cached:
            logger.info(f"Action Engine CACHE HIT — saved LLM call ({action_cache.stats['hit_rate']} hit rate)")
            return cached

        # Try primary provider
        if self.provider == "bedrock":
            result = await self._call_bedrock(user_context)
            if result:
                action_cache.set(cache_key, result)
                return result
            # Bedrock failed — try Groq as backup
            logger.warning("Bedrock failed, falling back to Groq")
            result = await self._call_groq(user_context)
            if result:
                action_cache.set(cache_key, result)
                return result
        else:
            # Provider is "groq" — try Groq first, Bedrock backup
            result = await self._call_groq(user_context)
            if result:
                action_cache.set(cache_key, result)
                return result
            logger.warning("Groq failed, falling back to Bedrock")
            result = await self._call_bedrock(user_context)
            if result:
                action_cache.set(cache_key, result)
                return result

        # Both failed
        logger.error("Both Bedrock and Groq unavailable, using fallback")
        return self._fallback_decision()

    # ─── Bedrock (Nvidia Nemotron) ───────────────────────────────────────────

    async def _call_bedrock(self, user_context: str) -> Optional[dict]:
        """Call AWS Bedrock with the Converse API."""
        try:
            import boto3

            client = boto3.client(
                "bedrock-runtime",
                region_name=settings.aws_region,
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
            )

            # Use the Converse API (works with all Bedrock models)
            response = await self._invoke_bedrock_converse(client, user_context)
            return response

        except ImportError:
            logger.error("boto3 not installed — cannot use Bedrock")
            return None
        except Exception as e:
            logger.error(f"Bedrock Action Engine error: {type(e).__name__}: {e}")
            return None

    async def _invoke_bedrock_converse(self, client, user_context: str) -> Optional[dict]:
        """Invoke Bedrock Converse API in a thread (boto3 is sync)."""
        import asyncio

        def _sync_call():
            response = client.converse(
                modelId=self.bedrock_model_id,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"text": f"{ACTION_ENGINE_PROMPT}\n\n---\n\n{user_context}"}
                        ],
                    }
                ],
                inferenceConfig={
                    "temperature": 0.4,
                    "maxTokens": 1024,
                },
            )
            # Extract text from Converse response
            output = response.get("output", {})
            message = output.get("message", {})
            content_blocks = message.get("content", [])
            text = ""
            for block in content_blocks:
                if "text" in block:
                    text = block["text"]
                    break

            if not text:
                return None

            # Parse JSON from the response (handle markdown code blocks)
            text = text.strip()
            if text.startswith("```"):
                # Strip ```json ... ``` wrapper
                lines = text.split("\n")
                lines = lines[1:]  # remove opening ```json
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                text = "\n".join(lines)

            return json.loads(text)

        try:
            result = await asyncio.to_thread(_sync_call)
            if result:
                logger.info(f"Bedrock Action Engine: {result.get('mood_assessment', '')[:60]}")
            return result
        except json.JSONDecodeError as e:
            logger.error(f"Bedrock returned invalid JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Bedrock Converse error: {type(e).__name__}: {e}")
            return None

    # ─── Groq (Backup) ───────────────────────────────────────────────────────

    async def _call_groq(self, user_context: str) -> Optional[dict]:
        """Call Groq API as backup provider."""
        if not self.groq_api_key:
            logger.warning("GROQ_API_KEY not set, skipping Groq")
            return None

        payload = {
            "model": self.groq_model,
            "messages": [
                {"role": "system", "content": ACTION_ENGINE_PROMPT},
                {"role": "user", "content": user_context},
            ],
            "temperature": 0.4,
            "max_tokens": 1024,
            "response_format": {"type": "json_object"},
        }

        try:
            async with httpx.AsyncClient(timeout=20.0, verify = _verify_ctx()) as client:
                response = await client.post(
                    GROQ_CHAT_URL,
                    headers={
                        "Authorization": f"Bearer {self.groq_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )

                if response.status_code != 200:
                    logger.error(f"Groq Action Engine error: {response.status_code} - {response.text}")
                    return None

                result = response.json()
                content = result["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                logger.info(f"Groq Action Engine: {parsed.get('mood_assessment', '')[:60]}")
                return parsed

        except Exception as e:
            logger.error(f"Groq Action Engine error: {type(e).__name__}: {e}")
            return None

    # ─── Context Builder ─────────────────────────────────────────────────────

    def _build_context(self, mood, mood_confidence, speech_text, speech_features,
                       behavior_result, pattern_context, room_id, time_of_day) -> str:
        parts = []
        parts.append(f"Room: {room_id}")
        if time_of_day:
            parts.append(f"Time: {time_of_day}")

        parts.append("\n## Voice & Mood Data")
        if speech_text:
            parts.append(f'User said: "{speech_text}"')
        if mood:
            mood_val = mood.value if hasattr(mood, 'value') else str(mood)
            parts.append(f"Detected mood: {mood_val} (confidence: {mood_confidence:.0%})")
        if speech_features:
            parts.append(f"Speech features: {json.dumps(speech_features)}")
        if not mood and not speech_text:
            parts.append("No voice data available.")

        parts.append("\n## Behavior Tracking Data")
        if behavior_result:
            if hasattr(behavior_result, 'cognitive_load'):
                parts.append(f"Cognitive load: {behavior_result.cognitive_load.value}")
                parts.append(f"Agitation: {behavior_result.agitation_level:.0%}")
                if behavior_result.patterns_detected:
                    parts.append(f"Patterns: {', '.join(behavior_result.patterns_detected)}")
            elif isinstance(behavior_result, dict):
                parts.append(f"Cognitive load: {behavior_result.get('cognitive_load')}")
                parts.append(f"Agitation: {behavior_result.get('agitation_level', 0):.0%}")
                if behavior_result.get('patterns_detected'):
                    parts.append(f"Patterns: {', '.join(behavior_result['patterns_detected'])}")
        else:
            parts.append("No behavior data available.")

        if pattern_context:
            parts.append("\n## Device Pattern Data")
            parts.append(f"Context: {pattern_context.get('context_type', 'normal')}")
            parts.append(f"People home: {pattern_context.get('people_home', {})}")
            parts.append(f"Active devices: {pattern_context.get('active_devices', [])}")
            if pattern_context.get("relevant_patterns"):
                for p in pattern_context["relevant_patterns"]:
                    parts.append(f"  - {p.get('description')} ({p.get('confidence', 0):.0%})")
            if pattern_context.get("anomalies"):
                parts.append("Anomalies:")
                for a in pattern_context["anomalies"]:
                    parts.append(f"  - [{a.get('severity')}] {a.get('detail', a.get('type'))}")

        return "\n".join(parts)

    def _fallback_decision(self) -> dict:
        return {
            "mood_assessment": "Fallback — both LLM providers unavailable",
            "detected_mood": "neutral",
            "cognitive_load": "moderate",
            "confidence": 0.3,
            "actions": {
                "light_color": "#FFFFFF",
                "light_brightness": 65,
                "light_temperature_k": 4000,
                "music_genre": None,
                "music_volume": 0,
                "notification_mode": "normal",
            },
            "alexa_response": "I'm having trouble reaching my AI services. Settings are at default.",
            "reasoning": "Fallback: both Bedrock and Groq unavailable",
        }


# Singleton
action_engine = ActionEngine()
