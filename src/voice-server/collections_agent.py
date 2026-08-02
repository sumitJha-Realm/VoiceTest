"""
Collections agent brain: the system prompt + response contract.

The agent plays a polite, RBI-fair-practice-compliant EMI collections officer for
an NBFC ("Sahaj Finance"). It:
  - greets and identifies the borrower,
  - states the overdue EMI,
  - handles objections (denial, hardship, anger, "already paid"),
  - offers a restructured payment plan when there is genuine hardship,
  - captures a promise-to-pay date,
  - escalates disputes / distress to a human,
  - NEVER threatens, abuses, or calls at odd hours (compliance).

It replies in the SAME language / code-mix the borrower uses (Hindi, Tamil,
English, Hinglish, Tanglish).

The model must return a small JSON object so the backend can drive the CRM.
"""

from __future__ import annotations

import json
import re

SYSTEM_PROMPT = """\
You are "Meera", a warm, professional loan-collections voice agent for Sahaj Finance (an Indian NBFC), calling a borrower about an overdue EMI.

STYLE: Reply in the user's most recent utterance language/code-mix (Hindi, Tamil, English, Hinglish, Tanglish). If they switch language, you must switch too in the very next reply. Exactly ONE short spoken sentence, max 12 words — warm and human, use contractions and fillers ("ji", "achha", "theek hai"). Acknowledge what they said first. No emojis, no lists, never two sentences.

COMPLIANCE (RBI): Always respectful and empathetic. Never threaten, shame, or pressure. De-escalate anger; escalate genuine disputes or distress to a human.

FLOW: confirm borrower → state overdue EMI → handle objection → if they'll pay, get a promise-to-pay date → if hardship, offer a simple restructured plan (split/extension) → if dispute/distress/abuse, escalate. Use the account context; never invent numbers.

Respond with ONLY this JSON object, nothing else:
{"reply":"<spoken reply in their language>","reply_language_code":"<hi-IN|ta-IN|en-IN>","disposition":"<greeting|promise_to_pay|dispute|hardship_plan_offered|refused|escalate|resolved|other>","promise_to_pay_date":"<YYYY-MM-DD or null>","escalate":<true|false>,"sentiment":"<positive|neutral|negative>"}
"""


_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
_TAMIL_RE = re.compile(r"[\u0B80-\u0BFF]")


def detect_reply_language_code(user_text: str, preferred: str = "hi-IN") -> str:
    """Infer response language from the latest utterance script/content.

    Priority:
      1) Tamil script -> ta-IN
      2) Devanagari script -> hi-IN
      3) ASCII-heavy text -> en-IN (covers English/Hinglish typed in Latin)
      4) Fallback to account preferred language
    """
    text = (user_text or "").strip()
    if not text:
        return preferred or "hi-IN"

    if _TAMIL_RE.search(text):
        return "ta-IN"
    if _DEVANAGARI_RE.search(text):
        return "hi-IN"

    ascii_letters = sum(1 for ch in text if "a" <= ch.lower() <= "z")
    if ascii_letters >= max(3, len(text) // 4):
        return "en-IN"

    return preferred or "hi-IN"


def build_messages(account_context: str, history: list[dict], user_text: str) -> list[dict]:
    """Assemble the chat messages for one turn."""
    preferred = "hi-IN"
    for line in account_context.splitlines():
        if line.lower().startswith("preferred language:"):
            preferred = line.split(":", 1)[1].strip() or "hi-IN"
            break

    current_lang = detect_reply_language_code(user_text, preferred)

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"BORROWER ACCOUNT CONTEXT:\n{account_context}"},
        {
            "role": "system",
            "content": (
                "TURN LANGUAGE RULE: Reply language_code MUST be "
                f"{current_lang} for this turn, based on latest user utterance."
            ),
        },
    ]
    messages.extend(history)
    messages.append({"role": "user", "content": user_text})
    return messages


def parse_agent_json(raw: str) -> dict:
    """Robustly extract the JSON object the model returns."""
    raw = raw.strip()
    # Strip code fences if the model added them.
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1:
        raw = raw[start : end + 1]
    try:
        data = json.loads(raw)
    except Exception:
        # Fallback: treat the whole thing as a plain spoken reply.
        return {
            "reply": raw,
            "reply_language_code": "hi-IN",
            "disposition": "other",
            "promise_to_pay_date": None,
            "escalate": False,
            "sentiment": "neutral",
        }
    data.setdefault("reply", "")
    data.setdefault("reply_language_code", "hi-IN")
    data.setdefault("disposition", "other")
    data.setdefault("promise_to_pay_date", None)
    data.setdefault("escalate", False)
    data.setdefault("sentiment", "neutral")
    return data


# ---------------------------------------------------------------------------
# Streaming (Pipecat) path: plain conversational speech, no JSON in the reply.
# ---------------------------------------------------------------------------
CONVERSATION_PROMPT = """\
You are "Meera", a warm, professional loan-collections voice agent for Sahaj Finance (an Indian NBFC). You are on a phone call with a borrower about an overdue EMI. Your words are spoken aloud.

LANGUAGE (VERY IMPORTANT):
- The borrower's preferred language is {LANGUAGE}. Speak ONLY in {LANGUAGE} by default.
- Write {LANGUAGE} in its native script (e.g. Devanagari for Hindi, Tamil script for Tamil).
- Do NOT reply in English unless the borrower is clearly speaking English. Match the borrower's language and code-mix (Hinglish / Tanglish) if they mix.

STYLE:
- Reply in ONE short, natural spoken sentence (max ~15 words). No emojis, no lists, no formatting.
- Sound human and warm: use contractions and natural fillers ("ji", "achha", "theek hai"). Acknowledge what they said first.

COMPLIANCE (RBI Fair Practices): Always respectful and empathetic. Never threaten, shame, or pressure. De-escalate anger. If there is a genuine dispute or the borrower is in distress, calmly say you'll connect them to a human colleague.

CALL FLOW: Greet and confirm you're speaking to the borrower, mention the overdue EMI, handle their objection honestly, and if they can pay, gently confirm a date. If hardship, offer a simple split/extension. Use the account facts below; never invent numbers.
"""

_LANG_NAMES = {"hi-IN": "Hindi", "ta-IN": "Tamil", "en-IN": "English"}


def build_conversation_system(account_context: str, language_code: str = "hi-IN") -> str:
    """Single system-instruction string for the Pipecat SarvamLLMService."""
    language = _LANG_NAMES.get(language_code, "Hindi")
    prompt = CONVERSATION_PROMPT.replace("{LANGUAGE}", language)
    return f"{prompt}\n\nBORROWER ACCOUNT CONTEXT:\n{account_context}"


CLASSIFY_PROMPT = """\
You classify one turn of a loan-collections call. Given the borrower's line and the agent's reply, respond with ONLY this JSON (no extra text):
{"disposition":"<greeting|promise_to_pay|dispute|hardship_plan_offered|refused|escalate|resolved|other>","promise_to_pay_date":"<YYYY-MM-DD or null>","escalate":<true|false>,"sentiment":"<positive|neutral|negative>","language":"<hi-IN|ta-IN|en-IN>"}
"""


async def classify_disposition(user_text: str, agent_text: str, today: str) -> dict:
    """Lightweight, non-blocking classification used to drive the CRM."""
    import sarvam_client as sarvam  # local import to avoid cycles

    messages = [
        {"role": "system", "content": CLASSIFY_PROMPT + f"\nToday is {today}."},
        {"role": "user", "content": f"Borrower: {user_text}\nAgent: {agent_text}"},
    ]
    raw = await sarvam.chat(messages)
    data = parse_agent_json(raw)
    # parse_agent_json guarantees the shared keys; map language->reply_language_code
    data.setdefault("language", "hi-IN")
    data["reply_language_code"] = data.get("language", "hi-IN")
    return data
