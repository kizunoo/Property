#!/usr/bin/env python3
"""
Triage doctor: shows which inquiries were labelled by the AI and which only by rules, and WHY the AI
did not label one. Read-only (never writes). Message text is only printed with --rerun.

    backend\\venv\\Scripts\\python scripts\\triage_doctor.py
    backend\\venv\\Scripts\\python scripts\\triage_doctor.py --rerun <first 8 characters of an inquiry id>
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
from copilot_doctor import hint, redact  # noqa: E402  (also loads backend/.env)


def minutes_ago(ts) -> float:
    try:
        d = datetime.fromisoformat(str(ts))
        d = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - d).total_seconds() / 60
    except (ValueError, TypeError):
        return 9e9


def main() -> int:
    import main as app_main
    import triage_service
    from copilot_tools import INQUIRY_TEXT_COL
    from triage_rules import sanitize_text

    sb = app_main.supabase
    triage_service.set_db(sb)
    rows = (sb.table("client_inquiries").select("*").order("created_at", desc=True)
            .limit(15).execute().data) or []
    names = {c["id"]: c.get("name") for c in
             (sb.table("clients").select("id,name").in_("id", list({r["client_id"] for r in rows}) or ["-"])
              .execute().data or [])}

    print("=== Triage doctor (read-only) ===\n")
    print(f"{'id':<9}{'company':<26}{'label by':<10}{'priority':<9}{'category':<20}{'age':<8}AI summary?")
    problems = {"stuck": 0, "failed": 0}
    for r in rows:
        age = minutes_ago(r.get("created_at"))
        status = r.get("triage_status") or "-"
        raw_summary = sanitize_text(r.get(INQUIRY_TEXT_COL), 160) == (r.get("triage_summary") or "")
        by = {"ai": "AI", "rules": "rules", "failed": "rules (AI failed)"}.get(status, status)
        if status == "rules" and age > 3:
            problems["stuck"] += 1
        if status == "failed":
            problems["failed"] += 1
        print(f"{str(r['id'])[:8]:<9}{(names.get(r['client_id']) or '')[:24]:<26}{by[:9]:<10}"
              f"{str(r.get('triage_priority') or '-'):<9}{str(r.get('triage_category') or '-')[:19]:<20}"
              f"{age:>5.0f}m  {'no (raw text)' if raw_summary else 'yes'}")

    print("\n=== Verdict ===")
    if problems["stuck"]:
        print(f"* {problems['stuck']} inquiry(ies) are still rules-only after 3+ minutes and never marked failed.")
        print("  The AI step never finished: the backend restarted mid-run, the per-company AI limit "
              "(5/hour) was hit, or too many AI runs were in flight.")
        print("  Check the backend terminal for lines containing 'triage'.")
    if problems["failed"]:
        print(f"* {problems['failed']} inquiry(ies) have status 'AI failed': the model errored or replied "
              "without the required JSON.")
        print("  Run with --rerun <id> to see the model's raw reply and the exact error.")
    if not any(problems.values()):
        print("* Nothing stuck or failed. Rows showing 'rules' under 3 minutes old are simply still being read by the AI.")

    if "--rerun" in sys.argv:
        prefix = sys.argv[sys.argv.index("--rerun") + 1]
        match = [r for r in rows if str(r["id"]).startswith(prefix)]
        if not match:
            print(f"\n--rerun: no inquiry among the latest 15 starts with '{prefix}'")
            return 1
        r = match[0]
        import triage_agent
        captured = {}
        original = triage_agent.parse_ai_output

        def spy(raw):
            captured["raw"] = raw
            return original(raw)

        triage_agent.parse_ai_output = spy
        print(f"\n=== Re-running the AI on inquiry {str(r['id'])[:8]} (your own test text) ===")
        try:
            result = triage_agent.run_triage_sync(str(r["client_id"]), r.get(INQUIRY_TEXT_COL) or "")
            print("Model raw reply:", redact(str(captured.get("raw"))[:700]))
            print("Parsed result  :", result if result else "NONE (reply was not the required JSON)")
        except Exception as e:  # noqa: BLE001
            print(f"ERROR: {type(e).__name__}: {redact(e)[:500]}")
            print("MEANING:", hint(f"{type(e).__name__}: {e}"))
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
