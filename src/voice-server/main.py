"""
FastAPI voice server for the Sarvam multilingual collections bot.

Flow per turn:
    borrower audio ─▶ Sarvam STT ─▶ collections LLM (sarvam-m) ─▶ Sarvam TTS ─▶ audio
                                          │
                                          └─▶ CRM disposition + n8n workflow trigger

Endpoints
    GET  /health        liveness
    GET  /api/wake      cold-start warmup ping (free hosting)
    POST /api/chat      one conversation turn (audio OR text in, text+audio out)
    POST /api/reset     clear a session's history
    GET  /api/crm       recent call dispositions (for the live CRM panel)
    GET  /api/metrics   aggregate ROI numbers (for the metrics tile)
    GET  /api/borrowers list demo borrowers
"""

from __future__ import annotations

import os
from collections import defaultdict

from dotenv import load_dotenv
from fastapi import FastAPI, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

import collections_agent as agent  # noqa: E402
import crm  # noqa: E402
import sarvam_client as sarvam  # noqa: E402

app = FastAPI(title="Sahaj Finance — Sarvam Collections Bot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory conversation history per session: {session_id: [ {role, content}, ... ]}
_sessions: dict[str, list[dict]] = defaultdict(list)
_MAX_TURNS = 12  # keep context short for latency


class ChatResponse(BaseModel):
    transcript: str
    reply: str
    reply_language_code: str
    audio_base64: str
    disposition: str
    promise_to_pay_date: str | None
    escalate: bool
    sentiment: str


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/wake")
async def wake() -> dict:
    """Ping to warm a sleeping free-tier instance before the user talks."""
    return {"awake": True}


@app.get("/api/borrowers")
async def borrowers() -> dict:
    return {"borrowers": crm.list_borrowers()}


@app.post("/api/reset")
async def reset(session_id: str = Form("default")) -> dict:
    _sessions.pop(session_id, None)
    return {"reset": True}


@app.get("/api/crm")
async def crm_view() -> dict:
    return {"calls": crm.recent_calls()}


@app.get("/api/metrics")
async def metrics_view() -> dict:
    return crm.metrics()


@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    session_id: str = Form("default"),
    loan_id: str = Form("L001"),
    text: str | None = Form(None),
    audio: UploadFile | None = None,
) -> ChatResponse:
    # 1. Get the borrower's utterance — from audio (STT) or a typed fallback.
    if audio is not None:
        audio_bytes = await audio.read()
        transcript = await sarvam.speech_to_text(
            audio_bytes,
            filename=audio.filename or "audio.webm",
            content_type=audio.content_type or "application/octet-stream",
        )
    else:
        transcript = (text or "").strip()

    if not transcript:
        transcript = "(no speech detected)"

    history = _sessions[session_id]
    context = crm.account_context(loan_id)
    borrower = crm.get_borrower(loan_id)
    fallback_lang = borrower.get("language", "hi-IN")
    target_lang = agent.detect_reply_language_code(transcript, fallback_lang)

    # 2. Reason + generate reply with the collections LLM.
    messages = agent.build_messages(context, history, transcript)
    try:
        raw = await sarvam.chat(messages)
        result = agent.parse_agent_json(raw)
        # Enforce per-turn language derived from the latest utterance.
        model_lang = result.get("reply_language_code") or fallback_lang
        result["reply_language_code"] = target_lang
        reply_candidate = (result.get("reply") or "").strip()
        should_translate = (
            reply_candidate
            and (
                model_lang != target_lang
                or target_lang in {"en-IN", "ta-IN"}
            )
        )
        if should_translate:
            try:
                result["reply"] = await sarvam.translate(
                    reply_candidate, target_language_code=target_lang
                )
            except Exception:
                # If translation fails, keep model text but preserve target TTS language.
                pass
    except Exception:
        result = {
            "reply": (
                "Thanks for your response. Our automated assistant is temporarily "
                "unavailable. A follow-up will be scheduled shortly."
            ),
            "reply_language_code": target_lang,
            "disposition": "other",
            "promise_to_pay_date": None,
            "escalate": True,
            "sentiment": "neutral",
        }
    reply_text = result["reply"] or "Maaf kijiye, kya aap dobara bata sakte hain?"

    # 3. Update short conversation memory.
    history.append({"role": "user", "content": transcript})
    history.append({"role": "assistant", "content": reply_text})
    _sessions[session_id] = history[-_MAX_TURNS * 2 :]

    # 4. Speak the reply in the borrower's language.
    try:
        audio_b64 = await sarvam.text_to_speech(
            reply_text, target_language_code=result["reply_language_code"]
        )
    except Exception:
        audio_b64 = ""

    # 5. Drive the downstream: CRM disposition + n8n agentic workflow.
    try:
        await crm.record_disposition(loan_id, result)
    except Exception:
        pass

    return ChatResponse(
        transcript=transcript,
        reply=reply_text,
        reply_language_code=result["reply_language_code"],
        audio_base64=audio_b64,
        disposition=result["disposition"],
        promise_to_pay_date=result.get("promise_to_pay_date"),
        escalate=bool(result.get("escalate")),
        sentiment=result.get("sentiment", "neutral"),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "7860")),
        reload=bool(os.getenv("DEV")),
    )
