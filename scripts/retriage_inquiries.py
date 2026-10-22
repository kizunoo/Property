#!/usr/bin/env python3
"""
Re-labels EXISTING open inquiries with the current rules (and optionally re-runs the AI on rows the AI
never labelled). Writes only triage_priority / triage_category / triage_reasons (and the AI summary
and status for rows it re-ran). Creates NO alerts. Prints company names and ids only, never message text.

    backend\\venv\\Scripts\\python scripts\\retriage_inquiries.py              # preview only
    backend\\venv\\Scripts\\python scripts\\retriage_inquiries.py --apply      # write changes
    ... --apply --ai       # also re-run the AI for rows that were rules-only (max 20, 1 per second)
    ... --apply --ai --all # re-run the AI for every open inquiry
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
import copilot_doctor  # noqa: E402,F401  (loads backend/.env)
from triage_rules import (CATEGORIES, AiTriage, classify_by_rules, compute_priority,  # noqa: E402
                          merge_label, sanitize_text)


def relabel(row: dict, text: str, facts, ai: AiTriage | None = None):
    """Pure: returns (priority, category, reasons) for an existing inquiry."""
    rules_category, rules_ts = classify_by_rules(text)
    if ai is None and row.get("triage_status") == "ai" and row.get("triage_category") in CATEGORIES:
        ai = AiTriage(row["triage_category"], False, row.get("triage_summary") or "stored")
    if ai is not None:
        return merge_label(rules_category, rules_ts, ai, facts)
    priority, reasons = compute_priority(rules_category, rules_ts, facts)
    return priority, rules_category, reasons


def main() -> int:
    import main as app_main
    import triage_service
    from copilot_tools import INQUIRY_TEXT_COL

    apply, use_ai, rerun_all = "--apply" in sys.argv, "--ai" in sys.argv, "--all" in sys.argv
    sb = app_main.supabase
    triage_service.set_db(sb)
    rows = (sb.table("client_inquiries").select("*").order("created_at", desc=True)
            .limit(200).execute().data) or []
    rows = [r for r in rows if r.get("status") in triage_service.INQUIRY_OPEN_STATUSES]
    names = {c["id"]: c.get("name") for c in
             (sb.table("clients").select("id,name").in_("id", list({r["client_id"] for r in rows}) or ["-"])
              .execute().data or [])}
    ai_budget, changed = 20, 0
    print(f"{'APPLYING' if apply else 'PREVIEW'}: {len(rows)} open inquiries\n")
    for r in rows:
        text = r.get(INQUIRY_TEXT_COL) or ""
        facts = triage_service.gather_facts(sb, r["client_id"], r["id"])
        ai = None
        if use_ai and (rerun_all or r.get("triage_status") != "ai") and ai_budget > 0:
            ai_budget -= 1
            time.sleep(1)
            try:
                import triage_agent
                ai = triage_agent.run_triage_sync(str(r["client_id"]), text)
            except Exception as e:  # noqa: BLE001
                print(f"  (AI unavailable for {str(r['id'])[:8]}: {type(e).__name__})")
        priority, category, reasons = relabel(r, text, facts, ai)
        if (priority, category) == (r.get("triage_priority"), r.get("triage_category")) and not ai:
            continue
        changed += 1
        print(f"{str(r['id'])[:8]}  {(names.get(r['client_id']) or '')[:28]:<28} "
              f"{str(r.get('triage_priority')).upper():>7} -> {priority.upper():<7} "
              f"{r.get('triage_category')} -> {category}")
        if apply:
            update = {"triage_priority": priority, "triage_category": category, "triage_reasons": reasons}
            if ai:
                update.update({"triage_status": "ai", "triage_summary": sanitize_text(ai.summary, 200)})
            sb.table("client_inquiries").update(update).eq("id", r["id"]).execute()
    print(f"\n{changed} inquiry label(s) {'updated' if apply else 'would change'}.")
    if not apply and changed:
        print("Run again with --apply to write them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
