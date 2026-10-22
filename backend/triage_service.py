"""
Inquiry triage service. Flow:
  1. A company inquiry is saved by the existing portal endpoint.
  2. triage_new_inquiry() labels it IMMEDIATELY with rules (no AI, no waiting) and alerts the rep
     if it is high/urgent.
  3. In the background, an AI agent re-reads it. The AI may only ESCALATE the label.
  4. If the AI fails, the rules label stands (status 'failed'). Inquiry submission never breaks.
Labels are rep-side only: they must never appear in any portal (company) response.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from copilot_tools import Identity, _scoped_client_ids
from triage_rules import (CATEGORY_LABEL, RANK, AiTriage, Facts, classify_by_rules,
                          compute_priority, escalate_only, merge_label, sanitize_text)

log = logging.getLogger("triage")

# ---------------------------------------------------------------------------
# ADAPT-ME: real names/values (check supabase/migrations/ and backend/main.py)
# ---------------------------------------------------------------------------
INQUIRY_TABLE = "client_inquiries"
INQUIRY_OPEN_STATUSES = ("open", "new", "pending", "in_progress")   # shown on the rep side
UNANSWERED_STATUSES = ("open", "new", "pending")                     # no rep reply yet
QUOTE_TABLE, OPEN_QUOTE_STATUSES = "portal_quotes", ("requested", "sent")
VIEWING_TABLE, PENDING_DEMO_VALUES = "scheduled_viewings", ("requested", "offered")
CLIENT_TABLE, CLIENT_NAME_COL = "clients", "name"

MAX_AI_PER_CLIENT_PER_HOUR = 5
_ai_slots = threading.BoundedSemaphore(4)  # at most 4 AI triage runs at once

_db = None
_signal_hook: Optional[Callable[[str, str, str, str], None]] = None
_ai_runner: Optional[Callable[[str, str], Optional[AiTriage]]] = None


def set_db(db) -> None:
    global _db
    _db = db


def get_db():
    return _db


def set_signal_hook(fn: Callable[[str, str, str, str], None]) -> None:
    """fn(client_id, title, body, priority) creates a rep signal using the project's existing
    signal mechanism. Copy must never contain internal scores."""
    global _signal_hook
    _signal_hook = fn


def set_ai_runner(fn) -> None:
    """fn(client_id, text) -> AiTriage | None. Defaults to triage_agent.run_triage_sync."""
    global _ai_runner
    _ai_runner = fn


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts) -> Optional[datetime]:
    try:
        d = datetime.fromisoformat(str(ts))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def gather_facts(db, client_id: str, inquiry_id: str) -> Facts:
    now = _now()
    quotes = db.table(QUOTE_TABLE).select("status").eq("client_id", client_id).execute().data or []
    demos = (db.table(VIEWING_TABLE).select("confirmation_status")
             .eq("client_id", client_id).execute().data) or []
    inquiries = (db.table(INQUIRY_TABLE).select("id,status,created_at")
                 .eq("client_id", client_id).limit(200).execute().data) or []
    last_7d = sum(1 for i in inquiries
                  if (d := _parse(i.get("created_at"))) and d >= now - timedelta(days=7))
    stale = now - timedelta(hours=48)
    prior_unanswered = any(
        i.get("id") != inquiry_id and i.get("status") in UNANSWERED_STATUSES
        and (d := _parse(i.get("created_at"))) and d < stale
        for i in inquiries)
    return Facts(
        has_open_quote=any(q.get("status") in OPEN_QUOTE_STATUSES for q in quotes),
        has_pending_demo=any(d.get("confirmation_status") in PENDING_DEMO_VALUES for d in demos),
        prior_unanswered=prior_unanswered,
        inquiries_last_7d=last_7d,
    )


def account_context(db, client_id: str) -> dict:
    """What the triage agent may see about the company. No EV/ML scores, ever."""
    client = (db.table(CLIENT_TABLE).select("*").eq("id", client_id).limit(1).execute().data
              or [{}])[0]
    f = gather_facts(db, client_id, "")
    return {
        "company": sanitize_text(client.get(CLIENT_NAME_COL), 120),
        "facility_profile": client.get("facility_profile") or {},
        "has_open_quote": f.has_open_quote,
        "has_pending_demo": f.has_pending_demo,
        "has_unanswered_earlier_inquiry": f.prior_unanswered,
        "inquiries_last_7_days": f.inquiries_last_7d,
    }


def _company_name(db, client_id: str) -> str:
    rows = (db.table(CLIENT_TABLE).select(CLIENT_NAME_COL).eq("id", client_id)
            .limit(1).execute().data) or [{}]
    return sanitize_text(rows[0].get(CLIENT_NAME_COL), 120) or "a client"


def _maybe_alert(db, client_id: str, inquiry_id: str, priority: str, category: str,
                 summary: str) -> None:
    if priority not in ("urgent", "high") or _signal_hook is None:
        return
    claimed = (db.table(INQUIRY_TABLE).update({"triage_alerted": True})
               .eq("id", inquiry_id).eq("triage_alerted", False).execute().data)
    if not claimed:
        return  # already alerted
    try:
        _signal_hook(
            client_id,
            f"{priority.upper()} priority inquiry",
            f"{CATEGORY_LABEL.get(category, 'Message')} from {_company_name(db, client_id)}. "
            f"{sanitize_text(summary, 160)}",
            priority)
    except Exception as e:  # noqa: BLE001
        log.warning("triage signal failed: %s", type(e).__name__)
        db.table(INQUIRY_TABLE).update({"triage_alerted": False}).eq("id", inquiry_id).execute()


def _ai_budget_ok(db, client_id: str) -> bool:
    rows = (db.table(INQUIRY_TABLE).select("triage_status,triaged_at")
            .eq("client_id", client_id).limit(200).execute().data) or []
    cutoff = _now() - timedelta(hours=1)
    recent = sum(1 for r in rows if r.get("triage_status") == "ai"
                 and (d := _parse(r.get("triaged_at"))) and d >= cutoff)
    return recent < MAX_AI_PER_CLIENT_PER_HOUR


def triage_new_inquiry(db, client_id: str, inquiry_id: str, text: str,
                       background: bool = True) -> dict:
    """Call right after a company inquiry is saved. Never raises into the caller's flow."""
    facts = gather_facts(db, client_id, inquiry_id)
    category, ts = classify_by_rules(text)
    priority, reasons = compute_priority(category, ts, facts)
    summary = sanitize_text(text, 160)
    db.table(INQUIRY_TABLE).update({
        "triage_status": "rules", "triage_priority": priority, "triage_category": category,
        "triage_summary": summary, "triage_reasons": reasons, "triaged_at": _now().isoformat(),
    }).eq("id", inquiry_id).execute()
    _maybe_alert(db, client_id, inquiry_id, priority, category, summary)

    if _ai_budget_ok(db, client_id):
        job = (db, client_id, inquiry_id, text, priority, ts, facts)
        if background:
            threading.Thread(target=_ai_refine, args=job, daemon=True).start()
        else:
            _ai_refine(*job)
    return {"priority": priority, "category": category}


def _run_ai(client_id: str, text: str) -> Optional[AiTriage]:
    runner = _ai_runner
    if runner is None:
        from triage_agent import run_triage_sync  # lazy: app boots even if ADK is missing
        runner = run_triage_sync
    return runner(client_id, text)


def _ai_refine(db, client_id, inquiry_id, text, rules_priority, rules_ts, facts) -> None:
    if not _ai_slots.acquire(blocking=False):
        return  # too many AI runs in flight: the rules label stands
    try:
        try:
            ai = _run_ai(client_id, text)
        except Exception as e:  # noqa: BLE001
            log.warning("triage AI failed: %s", type(e).__name__)
            ai = None
        if ai is None:
            db.table(INQUIRY_TABLE).update({"triage_status": "failed"}).eq("id", inquiry_id).execute()
            return
        rules_category, _ = classify_by_rules(text)
        final, category, reasons = merge_label(rules_category, rules_ts, ai, facts)
        db.table(INQUIRY_TABLE).update({
            "triage_status": "ai", "triage_priority": final, "triage_category": category,
            "triage_summary": ai.summary, "triage_reasons": reasons,
            "triaged_at": _now().isoformat(),
        }).eq("id", inquiry_id).execute()
        _maybe_alert(db, client_id, inquiry_id, final, category, ai.summary)
    except Exception as e:  # noqa: BLE001
        log.warning("triage refine error: %s", type(e).__name__)
    finally:
        _ai_slots.release()


def list_priority_inquiries(db, identity: Identity, limit: int = 20) -> list[dict]:
    limit = max(1, min(int(limit), 50))
    ids = _scoped_client_ids(db, identity)
    if ids == []:
        return []
    q = db.table(INQUIRY_TABLE).select(
        "id,client_id,status,created_at,triage_priority,triage_category,"
        "triage_summary,triage_reasons,triage_status")
    if ids is not None:
        q = q.in_("client_id", ids)
    rows = q.order("created_at", desc=True).limit(200).execute().data or []
    rows = [r for r in rows if r.get("triage_priority") and r.get("status") in INQUIRY_OPEN_STATUSES]
    rows.sort(key=lambda r: RANK.get(r["triage_priority"], 0), reverse=True)  # stable: newest first within rank
    rows = rows[:limit]
    names = {}
    if rows:
        found = (db.table(CLIENT_TABLE).select(f"id,{CLIENT_NAME_COL}")
                 .in_("id", list({r["client_id"] for r in rows})).execute().data) or []
        names = {c["id"]: c.get(CLIENT_NAME_COL) for c in found}
    return [{
        "inquiry_id": r["id"], "client_id": r["client_id"],
        "company": sanitize_text(names.get(r["client_id"]), 120),
        "priority": r["triage_priority"], "category": r.get("triage_category"),
        "summary": sanitize_text(r.get("triage_summary"), 200),
        "reasons": [sanitize_text(x, 80) for x in (r.get("triage_reasons") or [])][:5],
        "status": r.get("status"), "created_at": r.get("created_at"),
        "triage_status": r.get("triage_status"),
    } for r in rows]
