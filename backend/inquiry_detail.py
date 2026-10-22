"""
Rep-side inquiry view: one inquiry plus its message thread, scoped to the rep's own clients.
Customer-written text is cleaned (control characters removed, length capped) and must be rendered
as plain text by the UI. Returns None for "missing" AND "not yours" so existence never leaks.
"""
from __future__ import annotations

import re
from typing import Optional

from copilot_tools import INQUIRY_TEXT_COL, Identity, can_access
from triage_rules import CATEGORY_LABEL, sanitize_text

INQUIRY_TABLE = "client_inquiries"
MESSAGE_TABLE = "inquiry_messages"
CLIENT_TABLE, CLIENT_NAME_COL = "clients", "name"
AGENT_TABLE, AGENT_NAME_COL = "agent_accounts", "name"
MAX_BODY = 4000
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def clean_message(value, limit: int = MAX_BODY) -> str:
    s = "" if value is None else str(value)
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", s)  # keep newlines and tabs
    return s.strip()[:limit]


def agent_names(db, ids) -> dict:
    """Best-effort id -> display name for reps (never raises)."""
    ids = [str(i) for i in ids if i]
    if not ids:
        return {}
    try:
        rows = db.table(AGENT_TABLE).select(f"id,{AGENT_NAME_COL}").in_("id", ids).execute().data or []
        return {str(r["id"]): sanitize_text(r.get(AGENT_NAME_COL), 80) for r in rows}
    except Exception:  # noqa: BLE001
        return {}


def get_inquiry_detail(db, identity: Identity, inquiry_id: str) -> Optional[dict]:
    if not _UUID.match(str(inquiry_id or "")):
        return None
    rows = db.table(INQUIRY_TABLE).select("*").eq("id", inquiry_id).limit(1).execute().data or []
    if not rows:
        return None
    inq = rows[0]
    client_id = inq.get("client_id")
    if not client_id or not can_access(db, identity, str(client_id)):
        return None

    client = (db.table(CLIENT_TABLE).select(f"id,{CLIENT_NAME_COL}").eq("id", client_id)
              .limit(1).execute().data or [{}])[0]
    raw = (db.table(MESSAGE_TABLE).select("sender,body,created_at").eq("inquiry_id", inquiry_id)
           .order("created_at").limit(100).execute().data) or []

    original = clean_message(inq.get(INQUIRY_TEXT_COL))
    messages = []
    for m in raw:
        body = clean_message(m.get("body"))
        if body:
            messages.append({"sender": "rep" if m.get("sender") == "rep" else "company",
                             "body": body, "created_at": m.get("created_at")})
    if messages and messages[0]["sender"] == "company" and messages[0]["body"] == original:
        messages = messages[1:]  # the first stored message just repeats the original

    category = inq.get("triage_category")
    resolver = agent_names(db, [inq.get("resolved_by")]).get(str(inq.get("resolved_by")))
    return {
        "inquiry": {
            "inquiry_id": inq.get("id"),
            "client_id": client_id,
            "company": sanitize_text(client.get(CLIENT_NAME_COL), 120),
            "status": inq.get("status"),
            "created_at": inq.get("created_at"),
            "priority": inq.get("triage_priority"),
            "category": category,
            "category_label": CATEGORY_LABEL.get(category, "Message"),
            "reasons": [sanitize_text(r, 80) for r in (inq.get("triage_reasons") or [])][:5],
            "summary": sanitize_text(inq.get("triage_summary"), 200),
            "triage_status": inq.get("triage_status"),
            "resolved_at": inq.get("resolved_at"),
            "resolved_by": resolver,
            "resolution_note": clean_message(inq.get("resolution_note"), 500) or None,
        },
        "original_message": original,
        "messages": messages,
    }
