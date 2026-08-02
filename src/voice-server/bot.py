"""
Pipecat streaming voice bot for the Sarvam collections agent.

Real-time pipeline (all streaming, low latency, barge-in supported):

    WebRTC mic ─▶ Sarvam STT (saaras:v3, WS) ─▶ Sarvam LLM (streaming) ─▶
                                                 Sarvam TTS (bulbul:v3, WS) ─▶ WebRTC audio

A TurnLogger taps the stream to (a) push live transcript to the UI and
(b) classify each turn in the background to drive the CRM + n8n workflow.

Endpoints:
    POST /api/offer?loan_id=&session_id=   WebRTC signaling (starts a bot)
    GET  /api/borrowers | /api/crm | /api/metrics | /api/transcript
    GET  /health | /api/wake
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

load_dotenv()

import collections_agent as agent  # noqa: E402
import crm  # noqa: E402

from pipecat.audio.vad.silero import SileroVADAnalyzer  # noqa: E402
from pipecat.frames.frames import (  # noqa: E402
    LLMFullResponseEndFrame,
    LLMRunFrame,
    LLMTextFrame,
    TranscriptionFrame,
)
from pipecat.pipeline.pipeline import Pipeline  # noqa: E402
from pipecat.pipeline.runner import PipelineRunner  # noqa: E402
from pipecat.pipeline.task import PipelineParams, PipelineTask  # noqa: E402
from pipecat.processors.aggregators.llm_context import LLMContext  # noqa: E402
from pipecat.processors.aggregators.llm_response_universal import (  # noqa: E402
    LLMContextAggregatorPair,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor  # noqa: E402
from pipecat.services.sarvam.llm import SarvamLLMService, SarvamLLMSettings  # noqa: E402
from pipecat.services.sarvam.stt import SarvamSTTService  # noqa: E402
from pipecat.services.sarvam.tts import SarvamTTSService  # noqa: E402
from pipecat.transports.base_transport import TransportParams  # noqa: E402
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection  # noqa: E402
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport  # noqa: E402

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
LLM_MODEL = os.getenv("SARVAM_LLM_MODEL", "sarvam-30b")
STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v3")
TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3")
TTS_SPEAKER = os.getenv("SARVAM_TTS_SPEAKER", "priya")

app = FastAPI(title="Sarvam Collections — Streaming Voice Bot")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_connections: dict[str, SmallWebRTCConnection] = {}


class NoReasoningSarvamLLM(SarvamLLMService):
    """Sarvam LLM with chain-of-thought reasoning disabled.

    Pipecat omits `reasoning_effort` when it is None, so Sarvam falls back to its
    default 'medium' reasoning — which makes the model 'think' instead of replying,
    adding latency and (in streaming) emitting no speakable content. We force
    `reasoning_effort: null` into the request body via extra_body so the model
    answers directly and fast.
    """

    def build_chat_completion_params(self, params_from_context) -> dict:
        params = super().build_chat_completion_params(params_from_context)
        extra = dict(params.get("extra_body") or {})
        extra["reasoning_effort"] = None
        params["extra_body"] = extra
        return params


class TurnLogger(FrameProcessor):
    """Taps the stream for live transcript + background CRM classification."""

    def __init__(self, session_id: str, loan_id: str):
        super().__init__()
        self.session_id = session_id
        self.loan_id = loan_id
        self._assistant_buf = ""
        self._last_user = ""

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame):
            if frame.text and frame.text.strip():
                self._last_user = frame.text.strip()
                crm.add_transcript(self.session_id, "user", self._last_user)
        elif isinstance(frame, LLMTextFrame):
            self._assistant_buf += frame.text
        elif isinstance(frame, LLMFullResponseEndFrame):
            reply = self._assistant_buf.strip()
            self._assistant_buf = ""
            if reply:
                crm.add_transcript(self.session_id, "assistant", reply)
                asyncio.create_task(self._classify(self._last_user, reply))

        await self.push_frame(frame, direction)

    async def _classify(self, user_text: str, reply: str):
        try:
            result = await agent.classify_disposition(
                user_text or "(greeting)", reply, dt.date.today().isoformat()
            )
            await crm.record_disposition(self.loan_id, result)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"disposition classify failed: {exc}")


async def run_bot(connection: SmallWebRTCConnection, loan_id: str, session_id: str):
    borrower = crm.get_borrower(loan_id)
    lang = borrower.get("language", "hi-IN")
    context_text = crm.account_context(loan_id)

    transport = SmallWebRTCTransport(
        webrtc_connection=connection,
        params=TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    stt = SarvamSTTService(
        api_key=SARVAM_API_KEY,
        settings=SarvamSTTService.Settings(model=STT_MODEL, language=lang),
    )
    llm = NoReasoningSarvamLLM(
        api_key=SARVAM_API_KEY,
        settings=SarvamLLMSettings(
            model=LLM_MODEL,
            system_instruction=agent.build_conversation_system(context_text, lang),
            temperature=0.4,
            max_tokens=120,
        ),
    )
    tts = SarvamTTSService(
        api_key=SARVAM_API_KEY,
        settings=SarvamTTSService.Settings(
            model=TTS_MODEL, voice=TTS_SPEAKER, language=lang
        ),
    )

    context = LLMContext()
    aggregators = LLMContextAggregatorPair(context)
    turn_logger = TurnLogger(session_id, loan_id)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            aggregators.user(),
            llm,
            turn_logger,
            tts,
            transport.output(),
            aggregators.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(allow_interruptions=True, enable_metrics=True),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):  # noqa: ANN001
        logger.info(f"client connected loan={loan_id} session={session_id}")
        crm.clear_transcript(session_id)
        lang_name = agent._LANG_NAMES.get(lang, "Hindi")
        context.add_message(
            {
                "role": "system",
                "content": f"Start the call now. Greet {borrower['name']} warmly by name "
                f"and mention the overdue EMI of Rs {borrower['emi_amount']} in ONE short "
                f"sentence, speaking in {lang_name} ({lang}) using its native script.",
            }
        )
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):  # noqa: ANN001
        logger.info("client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)


@app.post("/api/offer")
async def offer(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    loan_id = request.query_params.get("loan_id", "L001")
    session_id = request.query_params.get("session_id", "default")

    pc_id = body.get("pc_id")
    if pc_id and pc_id in _connections:
        conn = _connections[pc_id]
        await conn.renegotiate(sdp=body["sdp"], type=body["type"])
    else:
        conn = SmallWebRTCConnection()
        await conn.initialize(sdp=body["sdp"], type=body["type"])

        @conn.event_handler("closed")
        async def on_closed(c: SmallWebRTCConnection):
            _connections.pop(c.pc_id, None)

        _connections[conn.pc_id] = conn
        background_tasks.add_task(run_bot, conn, loan_id, session_id)

    answer = conn.get_answer()
    return answer


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/wake")
async def wake():
    return {"awake": True}


@app.get("/api/borrowers")
async def borrowers():
    return {"borrowers": crm.list_borrowers()}


@app.get("/api/transcript")
async def transcript(session_id: str = "default"):
    return {"turns": crm.get_transcript(session_id)}


@app.get("/api/crm")
async def crm_view():
    return {"calls": crm.recent_calls()}


@app.get("/api/metrics")
async def metrics_view():
    return crm.metrics()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("bot:app", host="0.0.0.0", port=int(os.getenv("PORT", "7860")))
