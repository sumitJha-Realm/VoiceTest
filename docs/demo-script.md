# Demo Script (3–5 min video)

Record while everything is warm. Keep the CRM/ROI panel visible the whole time.

## 0:00 — The pain (talk over a slide, no tech yet)
> "An NBFC makes ~1M EMI reminder calls a month at ₹80 each — ₹8 crore. 70% are routine.
> Here's how Sarvam automates them, in the borrower's own language."

## 0:30 — Call 1: Hindi + Hinglish, promise-to-pay (the differentiator)
- Select **Ramesh Kumar (hi-IN)**. Press Talk.
- Say (mix languages): *"Haan boliye… sir abhi salary nahi aayi, next month pakka kar dunga."*
- Show: agent replies in Hindi/Hinglish, stays polite, **captures a promise-to-pay date**.
- Point to the **CRM panel updating live** → chip turns green `promise to pay`.

## 1:30 — Call 2: Tamil, hardship → restructured plan
- Select **Lakshmi (ta-IN)**. Talk in Tamil: job loss / can't pay full.
- Show: agent offers a **split/restructured plan**, empathetic tone.

## 2:30 — Call 3: dispute/anger → escalation (shows judgement)
- Say: *"Maine already pay kar diya, baar baar call mat karo!"*
- Show: agent de-escalates and **escalates to a human** → red chip, metric ticks up.

## 3:15 — The agentic backend
- Flash the **n8n workflow** executing on the webhook (route → log / schedule / escalate).
- (If wired) show the **Google Sheet row** appear.

## 3:45 — The business close (last thing they remember)
- Point at the **ROI tile**: *"₹5 vs ₹80 a call — ~66% cost saved, 100% compliant, 24×7."*
- One line: *"A generic GPT + ElevenLabs stack can't do Tanglish collections, can't run
  on-prem for RBI, and costs more. That's why Sarvam."*

## Tips
- Narrate **business value**, not features ("natural Tamil voice → higher pickup"), not "this is Bulbul".
- Keep replies short so latency feels snappy; mention the ~1–2s round-trip once.
- Have the **text fallback** ready in case mic/audio glitches on camera.
