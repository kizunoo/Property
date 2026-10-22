"""
Resolve / reopen company inquiries and list a company's inquiry history (rep side only).
An inquiry is "open" while resolved_at is empty; the existing `status` column is never touched.
Every function returns the same "not_found" for missing AND not-yours, so existence never leaks.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from copilot_tools import Identity, can_access
from inquiry_detail import (CLIENT_NAME_COL, CLIENT_TABLE, INQUIRY_TABLE, MESSAGE_TABLE, _UUID,
                            agent_names, clean_message)
from triage_rules import CATEGORY_LABEL, sanitize_text


def _load(db, identity: Identity, inquiry_id: str) -> Optional[dict]:
    if not _UUID.match(str(inquiry_id or "")):
        return None
    rows = (db.table(INQUIRY_TABLE).select("id,client_id,resolved_at").eq("id", inquiry_id)
            .limit(1).execute().data) or []
    if not rows or not rows[0].get("client_id") or not can_access(db, identity, str(rows[0]["client_id"])):
        return None
    return rows[0]


def resolve_inquiry(db, identity: Identity, inquiry_id: str, note: Optional[str] = None) -> str:
    """Returns 'ok' | 'not_found' | 'already_resolved'."""
    row = _load(db, identity, inquiry_id)
    if row is None:
        return "not_found"
    if row.get("resolved_at"):
        return "already_resolved"
    updated = (db.table(INQUIRY_TABLE).update({
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "resolved_by": str(identity.agent_id),
        "resolution_note": clean_message(note, 500) or None,
    }).eq("id", inquiry_id).is_("resolved_at", "null").execute().data)
    return "ok" if updated else "already_resolved"  # the conditional update loses a double-click race safely


def reopen_inquiry(db, identity: Identity, inquiry_id: str) -> str:
    """Returns 'ok' | 'not_found' | 'not_resolved'."""
    row = _load(db, identity, inquiry_id)
    if row is None:
        return "not_found"
    if not row.get("resolved_at"):
        return "not_resolved"
    db.table(INQUIRY_TABLE).update({"resolved_at": None, "resolved_by": None,
                                    "resolution_note": None}).eq("id", inquiry_id).execute()
    return "ok"


def list_company_history(db, identity: Identity, client_id: str) -> Optional[dict]:
    if not _UUID.match(str(client_id or "")) or not can_access(db, identity, str(client_id)):
        return None
    client = (db.table(CLIENT_TABLE).select(f"id,{CLIENT_NAME_COL}").eq("id", client_id)
              .limit(1).execute().data or [{}])[0]
    rows = (db.table(INQUIRY_TABLE)
            .select("id,created_at,resolved_at,resolved_by,resolution_note,triage_priority,"
                    "triage_category,triage_summary")
            .eq("client_id", client_id).order("created_at", desc=True).limit(100).execute().data) or []
    replies: dict = {}
    ids = [r["id"] for r in rows]
    if ids:
        msgs = (db.table(MESSAGE_TABLE).select("inquiry_id,sender").in_("inquiry_id", ids)
                .limit(1000).execute().data) or []
        for m in msgs:
            if m.get("sender") == "rep":
                replies[m["inquiry_id"]] = replies.get(m["inquiry_id"], 0) + 1
    names = agent_names(db, [r.get("resolved_by") for r in rows])
    return {
        "client_id": client_id,
        "company": sanitize_text(client.get(CLIENT_NAME_COL), 120),
        "inquiries": [{
            "inquiry_id": r["id"],
            "created_at": r.get("created_at"),
            "state": "resolved" if r.get("resolved_at") else "open",
            "resolved_at": r.get("resolved_at"),
            "resolved_by": names.get(str(r.get("resolved_by"))),
            "resolution_note": clean_message(r.get("resolution_note"), 500) or None,
            "priority": r.get("triage_priority"),
            "category_label": CATEGORY_LABEL.get(r.get("triage_category"), "Message"),
            "summary": sanitize_text(r.get("triage_summary"), 200),
            "replies": replies.get(r["id"], 0),
        } for r in rows],
    }
