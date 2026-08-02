"""
Thin async client for Sarvam AI APIs used by the collections bot.

Sarvam APIs used
----------------
1. Speech-to-Text (Saaras / Saarika)  -> transcribe borrower audio
2. Chat Completions  (sarvam-m)       -> reason + generate collections reply
3. Text-to-Speech    (Bulbul)         -> speak the reply back
4. Translate (optional)               -> normalise/route mixed-language text

Model IDs and endpoints are read from environment variables so you can bump
versions (e.g. Saaras v3 / Bulbul v3) without touching code. Verify the exact
current model IDs in https://dashboard.sarvam.ai.
"""

from __future__ import annotations

import base64
import os

import httpx

SARVAM_BASE_URL = os.getenv("SARVAM_BASE_URL", "https://api.sarvam.ai")
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")

# Model IDs are configurable — defaults reflect the latest non-deprecated models
# per https://docs.sarvam.ai/api/developer-tools/mcp. Verify in the dashboard.
STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v3")
TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3")
# sarvam-30b (reasoning disabled) is ~1s faster than 105b and plenty for short replies.
LLM_MODEL = os.getenv("SARVAM_LLM_MODEL", "sarvam-30b")
TTS_SPEAKER = os.getenv("SARVAM_TTS_SPEAKER", "priya")

# TTS voice shaping. Note: bulbul:v3 does NOT support pitch/loudness.
TTS_PACE = float(os.getenv("SARVAM_TTS_PACE", "1.0"))
TTS_SAMPLE_RATE = int(os.getenv("SARVAM_TTS_SAMPLE_RATE", "22050"))

_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


def _headers() -> dict[str, str]:
    if not SARVAM_API_KEY:
        raise RuntimeError(
            "SARVAM_API_KEY is not set. Copy .env.example to .env and add your key "
            "from https://dashboard.sarvam.ai."
        )
    return {"api-subscription-key": SARVAM_API_KEY}


async def speech_to_text(
    audio_bytes: bytes,
    language_code: str = "unknown",
    filename: str = "audio.wav",
    content_type: str = "audio/wav",
) -> str:
    """Transcribe an audio clip. language_code='unknown' lets Sarvam auto-detect."""
    files = {"file": (filename, audio_bytes, content_type)}
    data = {"model": STT_MODEL, "language_code": language_code}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{SARVAM_BASE_URL}/speech-to-text",
            headers=_headers(),
            files=files,
            data=data,
        )
        resp.raise_for_status()
        payload = resp.json()
    # Sarvam returns {"transcript": "...", "language_code": "hi-IN", ...}
    return payload.get("transcript", "").strip()


async def chat(messages: list[dict], temperature: float = 0.3) -> str:
    """OpenAI-compatible chat completion. reasoning_effort=None disables slow
    chain-of-thought so we get the final answer fast (<1s)."""
    body = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 300,
        "reasoning_effort": None,
    }
    headers = {**_headers(), "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{SARVAM_BASE_URL}/v1/chat/completions",
            headers=headers,
            json=body,
        )
        resp.raise_for_status()
        payload = resp.json()
    msg = payload["choices"][0]["message"]
    content = msg.get("content") or msg.get("reasoning_content") or ""
    return content.strip()


async def text_to_speech(text: str, target_language_code: str = "hi-IN") -> str:
    """Synthesise speech. Returns base64-encoded WAV audio (ready for the browser)."""
    body = {
        "text": text,
        "target_language_code": target_language_code,
        "speaker": TTS_SPEAKER,
        "model": TTS_MODEL,
        "pace": TTS_PACE,
        "speech_sample_rate": TTS_SAMPLE_RATE,
        "enable_preprocessing": True,
    }
    headers = {**_headers(), "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{SARVAM_BASE_URL}/text-to-speech",
            headers=headers,
            json=body,
        )
        resp.raise_for_status()
        payload = resp.json()
    audios = payload.get("audios") or []
    if not audios:
        return ""
    # Already base64 from Sarvam; return as-is for the frontend <audio> tag.
    audio_b64 = audios[0]
    # Validate it decodes; if Sarvam ever returns raw bytes, re-encode.
    try:
        base64.b64decode(audio_b64)
    except Exception:
        audio_b64 = base64.b64encode(audios[0]).decode()
    return audio_b64


async def translate(text: str, target_language_code: str = "en-IN") -> str:
    """Optional: normalise mixed-language text to one language for routing/logging."""
    body = {
        "input": text,
        "source_language_code": "auto",
        "target_language_code": target_language_code,
    }
    headers = {**_headers(), "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{SARVAM_BASE_URL}/translate",
            headers=headers,
            json=body,
        )
        resp.raise_for_status()
        payload = resp.json()
    return payload.get("translated_text", text)
