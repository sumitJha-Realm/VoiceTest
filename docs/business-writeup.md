# Business Write-Up — AI Voice Collections Agent for NBFCs

**Prepared for:** VP Operations / CTO, Sahaj Finance (illustrative NBFC)
**Solution:** Multilingual voice collections agent + agentic post-call workflow, powered by Sarvam AI

---

## 1. The Problem

Indian lenders make **50M+ collection calls every month**, the bulk of them routine Tier-1
EMI reminders. A human tele-caller costs roughly **₹80 per call** (salary + telephony +
supervision) and can handle ~60–80 conversations a day. The work is repetitive, high-attrition,
and inconsistent — quality and compliance vary by agent, mood, and script adherence.

For a mid-size NBFC running **1,000,000 reminder calls/month**, that is **₹8 crore/month**,
of which **~70% are simple, first-touch reminders** that never needed a human.

## 2. Why AI

- **The end user** is a borrower in a Tier-2/3 town who speaks Hindi, Tamil, Marathi, or a
  **code-mix** ("sir salary nahi aayi, next month pakka") and has low digital literacy — they
  will not open an app or read an email, but they **will** answer a phone call in their language.
- A voice bot handles the 70% routine volume **24×7, consistently, and in-compliance** —
  never abusive, never off-script — freeing human agents for genuine hardship, disputes, and
  legal cases where empathy and judgement matter.
- Versus IVR ("press 1"), a **conversational** agent understands objections and negotiates a
  payment date — dramatically better completion and promise-to-pay capture.

## 3. Why Sarvam

| Requirement | Sarvam | Generic (US LLM + ElevenLabs) |
|---|---|---|
| Indian languages + **code-mixing** (Hinglish/Tanglish) | ✅ Native | ⚠️ Weak / brittle |
| Natural Indian-language voices | ✅ Bulbul, 37+ voices | ⚠️ Accented / limited |
| Low latency for real-time voice | ✅ Streaming STT/TTS | ⚠️ Higher round-trip |
| **Data sovereignty / on-prem** (RBI, borrower PII) | ✅ Available | ❌ Data leaves India |
| Cost per call at scale | ✅ India-optimised | ⚠️ Higher |

For a regulated BFSI buyer, **data sovereignty + code-mixing** are not nice-to-haves — they
are the deciding factors. This is where Sarvam wins that a generic stack structurally cannot.

## 4. Architecture Summary

A borrower talks to the agent in the browser (or, in production, over a real phone line).
**Sarvam Speech-to-Text** transcribes them, **Sarvam's LLM** reasons and replies in their
language following collections + RBI-compliance rules, and **Sarvam Text-to-Speech** speaks
back. When the call ends, a structured outcome triggers an **n8n agentic workflow** that
updates the CRM, schedules a follow-up, or escalates disputes to a human — automatically.
*(See the architecture diagram.)*

## 5. ROI / Business Case

**Assumptions:** 1,000,000 reminder calls/month · human ₹80/call · bot ₹5/call · 70% automatable.

| | Calls/mo | Cost/call | Monthly cost |
|---|---:|---:|---:|
| Today (all human) | 1,000,000 | ₹80 | **₹8.00 cr** |
| With bot (70% automated) | 700,000 bot + 300,000 human | ₹5 / ₹80 | ₹0.35 cr + ₹2.40 cr = **₹2.75 cr** |
| **Monthly saving** | | | **₹5.25 cr (~66%)** |

Beyond direct cost: **higher & more consistent contact rates**, better promise-to-pay capture,
100% call logging for audit, and **zero compliance breaches** from agent misbehaviour — which
also reduces regulatory and reputational risk.

## 6. Limitations & Next Steps

**Not yet in this PoC (for production):**
- Real telephony (outbound dialer via Exotel/Plivo) — architecture is ready, adapter pending.
- Live core-banking / LMS integration (currently a mock Google Sheet).
- Barge-in / interruption handling and call-recording consent flows.
- Authentication of borrower identity + DPDP/RBI-grade PII handling and on-prem deployment.
- Analytics dashboard (sentiment, recovery rate, agent-vs-bot A/B).

**90-day rollout:**
- **Weeks 1–3:** Integrate telephony + LMS; on-prem/VPC deployment; security review.
- **Weeks 4–7:** Pilot on one product/region (2 languages), human-in-the-loop, tune prompts.
- **Weeks 8–12:** A/B vs human agents, add languages, expand to full Tier-1 volume, live ROI dashboard.
