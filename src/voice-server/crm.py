"""
Mock CRM / LMS layer + n8n webhook trigger.

Runs out of the box with an in-memory store (great for a zero-setup demo).
If Google Sheets credentials are provided, it ALSO mirrors dispositions to a
sheet so you can show the "downstream system updated live" wow moment.
If an n8n webhook URL is set, every completed call fires the agentic workflow.
"""

from __future__ import annotations

import datetime as dt
import os
from threading import Lock
import time

import httpx

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
GOOGLE_CREDS_FILE = os.getenv("GOOGLE_CREDS_FILE", "")
GOOGLE_CRM_SHEET_NAME = os.getenv("GOOGLE_CRM_SHEET_NAME", "Collections")
GOOGLE_BORROWERS_SHEET_NAME = os.getenv("GOOGLE_BORROWERS_SHEET_NAME", "Borrowers")
GOOGLE_BORROWERS_CACHE_TTL_SEC = int(os.getenv("GOOGLE_BORROWERS_CACHE_TTL_SEC", "30"))

# ---------------------------------------------------------------------------
# Seed borrower book (mock). In production this is your LMS / core banking API.
# ---------------------------------------------------------------------------
BORROWERS: dict[str, dict] = {
    "L001": {
        "loan_id": "L001",
        "name": "Ramesh Kumar",
        "language": "hi-IN",
        "emi_amount": 4500,
        "due_date": "2026-07-05",
        "days_overdue": 12,
        "outstanding": 38000,
        "phone": "+91-90000-00001",
    },
    "L002": {
        "loan_id": "L002",
        "name": "Lakshmi Narayanan",
        "language": "ta-IN",
        "emi_amount": 6200,
        "due_date": "2026-07-02",
        "days_overdue": 15,
        "outstanding": 51000,
        "phone": "+91-90000-00002",
    },
    "L003": {
        "loan_id": "L003",
        "name": "Priya Sharma",
        "language": "en-IN",
        "emi_amount": 8900,
        "due_date": "2026-07-08",
        "days_overdue": 9,
        "outstanding": 72000,
        "phone": "+91-90000-00003",
    },
}

_lock = Lock()
_call_log: list[dict] = []  # in-memory disposition log for the metrics tile
_transcripts: dict[str, list[dict]] = {}  # session_id -> [{role, text}]
_borrower_cache: dict[str, dict] = {}
_borrower_cache_at: float = 0.0


def add_transcript(session_id: str, role: str, text: str) -> None:
    text = (text or "").strip()
    if not text:
        return
    with _lock:
        _transcripts.setdefault(session_id, []).append({"role": role, "text": text})


def get_transcript(session_id: str) -> list[dict]:
    with _lock:
        return list(_transcripts.get(session_id, []))


def clear_transcript(session_id: str) -> None:
    with _lock:
        _transcripts.pop(session_id, None)


def _norm_key(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "_")


def _to_int(v, default: int = 0) -> int:
    try:
        if v is None:
            return default
        if isinstance(v, (int, float)):
            return int(v)
        text = str(v).strip().replace(",", "")
        if not text:
            return default
        return int(float(text))
    except Exception:
        return default


def get_borrower(loan_id: str) -> dict:
    borrowers = _get_borrowers_live()
    if loan_id in borrowers:
        return borrowers[loan_id]
    # Fallback to first available row if an unknown loan_id is requested.
    try:
        return next(iter(borrowers.values()))
    except StopIteration:
        return BORROWERS["L001"]


def list_borrowers() -> list[dict]:
    return list(_get_borrowers_live().values())


def account_context(loan_id: str) -> str:
    b = get_borrower(loan_id)
    return (
        f"Name: {b['name']}\n"
        f"Loan ID: {b['loan_id']}\n"
        f"Preferred language: {b['language']}\n"
        f"Overdue EMI: Rs {b['emi_amount']}\n"
        f"Original due date: {b['due_date']} ({b['days_overdue']} days overdue)\n"
        f"Total outstanding: Rs {b['outstanding']}\n"
        f"Today's date: {dt.date.today().isoformat()}"
    )


def _google_sheet():
    """Lazily build a gspread worksheet, or return None if not configured."""
    if not (GOOGLE_SHEET_ID and GOOGLE_CREDS_FILE and os.path.exists(GOOGLE_CREDS_FILE)):
        return None
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(GOOGLE_CREDS_FILE, scopes=scopes)
        gc = gspread.authorize(creds)
        return gc.open_by_key(GOOGLE_SHEET_ID).sheet1
    except Exception as exc:  # noqa: BLE001 - never break a call over CRM issues
        print(f"[crm] Google Sheets disabled: {exc}")
        return None


def _google_sheet_by_name(sheet_name: str):
    """Open a specific worksheet by title, or return None if unavailable."""
    if not (GOOGLE_SHEET_ID and GOOGLE_CREDS_FILE and os.path.exists(GOOGLE_CREDS_FILE)):
        return None
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(GOOGLE_CREDS_FILE, scopes=scopes)
        gc = gspread.authorize(creds)
        return gc.open_by_key(GOOGLE_SHEET_ID).worksheet(sheet_name)
    except Exception as exc:  # noqa: BLE001
        print(f"[crm] worksheet '{sheet_name}' unavailable: {exc}")
        return None


def _load_borrowers_from_sheet() -> dict[str, dict]:
    """Load borrower rows from the Borrowers worksheet.

    Expected columns (case-insensitive):
      loan_id, name, language, emi_amount, due_date, days_overdue, outstanding, phone
    """
    ws = _google_sheet_by_name(GOOGLE_BORROWERS_SHEET_NAME)
    if ws is None:
        return {}
    try:
        rows = ws.get_all_records()
    except Exception as exc:  # noqa: BLE001
        print(f"[crm] borrowers read failed: {exc}")
        return {}

    out: dict[str, dict] = {}
    for row in rows:
        rr = {_norm_key(k): v for k, v in row.items()}
        loan_id = str(rr.get("loan_id", "")).strip()
        if not loan_id:
            continue
        out[loan_id] = {
            "loan_id": loan_id,
            "name": str(rr.get("name", "Unknown Borrower")).strip() or "Unknown Borrower",
            "language": str(rr.get("language", "hi-IN")).strip() or "hi-IN",
            "emi_amount": _to_int(rr.get("emi_amount"), 0),
            "due_date": str(rr.get("due_date", "")).strip() or dt.date.today().isoformat(),
            "days_overdue": _to_int(rr.get("days_overdue"), 0),
            "outstanding": _to_int(rr.get("outstanding"), 0),
            "phone": str(rr.get("phone", "")).strip(),
        }
    return out


def _get_borrowers_live() -> dict[str, dict]:
    """Borrower source of truth.

    Priority:
      1) Google Sheet Borrowers tab (cached for TTL)
      2) In-code BORROWERS fallback
    """
    global _borrower_cache_at, _borrower_cache
    now = time.time()
    if _borrower_cache and (now - _borrower_cache_at) < GOOGLE_BORROWERS_CACHE_TTL_SEC:
        return _borrower_cache

    live = _load_borrowers_from_sheet()
    if live:
        _borrower_cache = live
        _borrower_cache_at = now
        return _borrower_cache

    return BORROWERS


async def record_disposition(loan_id: str, result: dict) -> None:
    """Persist a call outcome: in-memory + optional Sheet + optional n8n trigger."""
    b = get_borrower(loan_id)
    row = {
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "loan_id": loan_id,
        "name": b["name"],
        "language": result.get("reply_language_code", b["language"]),
        "disposition": result.get("disposition", "other"),
        "promise_to_pay_date": result.get("promise_to_pay_date"),
        "escalate": result.get("escalate", False),
        "sentiment": result.get("sentiment", "neutral"),
        "emi_amount": b["emi_amount"],
    }

    with _lock:
        _call_log.append(row)

    # Mirror to Google Sheets (optional, non-blocking best-effort).
    ws = _google_sheet_by_name(GOOGLE_CRM_SHEET_NAME) or _google_sheet()
    if ws is not None:
        try:
            ws.append_row(
                [
                    row["timestamp"],
                    row["loan_id"],
                    row["name"],
                    row["language"],
                    row["disposition"],
                    row["promise_to_pay_date"] or "",
                    "YES" if row["escalate"] else "",
                    row["sentiment"],
                    row["emi_amount"],
                ]
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[crm] sheet append failed: {exc}")

    # Fire the n8n agentic workflow (optional).
    if N8N_WEBHOOK_URL:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(N8N_WEBHOOK_URL, json=row)
        except Exception as exc:  # noqa: BLE001
            print(f"[crm] n8n webhook failed: {exc}")


def recent_calls(limit: int = 20) -> list[dict]:
    with _lock:
        return list(reversed(_call_log[-limit:]))


def metrics() -> dict:
    """Aggregate numbers for the ROI tile."""
    with _lock:
        log = list(_call_log)
    total = len(log)
    ptp = sum(1 for r in log if r["disposition"] == "promise_to_pay")
    escalated = sum(1 for r in log if r["escalate"])
    # ROI assumptions (stated in the write-up): human ~Rs 80/call, bot ~Rs 5/call.
    human_cost = total * 80
    bot_cost = total * 5
    return {
        "calls_handled": total,
        "promise_to_pay": ptp,
        "escalated": escalated,
        "cost_per_call_bot": 5,
        "cost_per_call_human": 80,
        "savings": max(human_cost - bot_cost, 0),
    }
