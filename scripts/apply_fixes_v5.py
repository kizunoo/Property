#!/usr/bin/env python3
"""
One command for: inquiry resolution + company history, AI reply suggestions, and label polish.

    backend\\venv\\Scripts\\python scripts\\apply_fixes_v5.py                       # patch + test + type-check
    backend\\venv\\Scripts\\python scripts\\apply_fixes_v5.py --backfill            # ...and re-label existing inquiries with the AI
    backend\\venv\\Scripts\\python scripts\\apply_fixes_v5.py --commit --backfill   # ...and commit + push if everything passes

Run `npm run db:push -- --approve 20261019100000` FIRST (the script checks and stops if the columns are missing).

Edits (exact-text, all-or-nothing; if your code differs nothing is written):
  * triage_rules.py   : on a tie the AI's category wins (except problems/safety); weight/speed/warranty/
                        dimension questions are recognised as technical.
  * triage_service.py : resolved inquiries leave the priority list and no longer count toward the
                        "3 or more inquiries this week" bump.
Optional (skipped quietly if the file differs): import_real_data.py learns weight_kg, speed_mps,
warranty_months and dimensions so real robot specs can answer weight/size questions.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()

LABEL_EDITS = [
    ("backend/triage_rules.py",
     "    if RANK[r_pri] >= RANK[a_pri]:\n",
     "    # On a tie the AI's category is usually the more informative one, except for problems/safety.\n"
     "    if RANK[r_pri] > RANK[a_pri] or (RANK[r_pri] == RANK[a_pri] and rules_category == \"complaint_issue\"):\n",
     "tie goes to the AI's category (except problems/safety)"),
    ("backend/triage_rules.py",
     'r"\\b(spec\\w*|payload|battery|',
     'r"\\b(spec\\w*|payload|weigh\\w*|dimension\\w*|warranty|speed|battery|',
     "weight / dimension / warranty / speed questions are technical"),
    ("backend/triage_service.py",
     '"triage_summary,triage_reasons,triage_status")',
     '"triage_summary,triage_reasons,triage_status,resolved_at")',
     "priority list also reads resolved_at"),
    ("backend/triage_service.py",
     '    rows = [r for r in rows if r.get("triage_priority") and r.get("status") in INQUIRY_OPEN_STATUSES]\n',
     '    rows = [r for r in rows if r.get("triage_priority") and r.get("status") in INQUIRY_OPEN_STATUSES\n'
     '            and not r.get("resolved_at")]\n',
     "resolved inquiries leave the priority list"),
    ("backend/triage_service.py",
     '.select("id,status,created_at")',
     '.select("id,status,created_at,resolved_at")',
     "facts read resolved_at"),
    ("backend/triage_service.py",
     '                  if (d := _parse(i.get("created_at"))) and d >= now - timedelta(days=7))\n',
     '                  if not i.get("resolved_at")\n'
     '                  and (d := _parse(i.get("created_at"))) and d >= now - timedelta(days=7))\n',
     "resolved inquiries don't count toward the repeat-contact bump"),
    ("backend/triage_service.py",
     '        i.get("id") != inquiry_id and i.get("status") in UNANSWERED_STATUSES\n',
     '        i.get("id") != inquiry_id and i.get("status") in UNANSWERED_STATUSES\n'
     '        and not i.get("resolved_at")\n',
     "resolved inquiries are not 'still unanswered'"),
]
IMPORT_EDITS = [
    ("scripts/import_real_data.py",
     'ROBOT_OPTIONAL_NUM = ["lease_monthly", "payload_kg", "battery_hours"]',
     'ROBOT_OPTIONAL_NUM = ["lease_monthly", "payload_kg", "battery_hours", "weight_kg", "speed_mps",\n'
     '                      "warranty_months"]',
     "importer accepts weight_kg, speed_mps, warranty_months"),
    ("scripts/import_real_data.py",
     '+ ["key_specs", "target_industries"]',
     '+ ["key_specs", "target_industries", "dimensions"]',
     "importer accepts dimensions"),
]
COMMIT_FILES = [
    "supabase/migrations/20261019100000_inquiry_resolution.sql",
    "backend/inquiry_detail.py", "backend/inquiry_resolution.py", "backend/reply_context.py",
    "backend/reply_agent.py", "backend/inquiry_actions_routes.py",
    "backend/triage_rules.py", "backend/triage_service.py",
    "backend/tests/test_inquiry_resolution.py", "backend/tests/test_reply_context.py",
    "backend/tests/test_inquiry_actions_routes.py", "backend/tests/test_triage_resolution_effects.py",
    "components/pipeline/inquiry-detail-modal.tsx", "components/pipeline/priority-inquiries.tsx",
    "scripts/retriage_inquiries.py", "scripts/apply_fixes_v5.py",
    "scripts/import_real_data.py", "data/templates/robots_catalog.csv",
]


def read(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def plan(edits):
    texts, problems = {}, []
    for rel, old, new, desc in edits:
        path = ROOT / rel
        if not path.exists():
            problems.append(f"{rel}: not found (run from the project root)")
            continue
        text = texts.get(rel, read(path))
        eol = "\r\n" if "\r\n" in text else "\n"
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        if n in text:
            print(f"  SKIP     {rel}: {desc} (already applied)")
        elif text.count(o) == 1:
            text = text.replace(o, n)
            print(f"  APPLY    {rel}: {desc}")
        else:
            problems.append(f"{rel}: '{desc}' (code differs from what was reviewed)")
        texts[rel] = text
    return texts, problems


def write(texts: dict) -> None:
    for rel, text in texts.items():
        with open(ROOT / rel, "w", encoding="utf-8", newline="") as f:
            f.write(text)


def run(cmd, shell=False) -> int:
    print("\n$", cmd if shell else " ".join(cmd))
    return subprocess.run(cmd, shell=shell).returncode


def migration_applied() -> bool:
    sys.path.insert(0, str(ROOT / "backend"))
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import copilot_doctor  # noqa: F401  (loads backend/.env)
        import main as app_main
        app_main.supabase.table("client_inquiries").select("resolved_at,resolved_by,resolution_note") \
            .limit(1).execute()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  Could not read the new columns ({type(e).__name__}).")
        return False


def main() -> int:
    args = set(sys.argv[1:])
    if "--skip-db-check" not in args and not migration_applied():
        print("\nSTOPPED: the database migration is not applied yet. Run this first, then run this script again:")
        print("    npm run db:push -- --approve 20261019100000")
        return 1

    print("Planning label/priority edits (all-or-nothing)...")
    texts, problems = plan(LABEL_EDITS)
    if problems:
        print("\nNOTHING WAS CHANGED. Problems:")
        for p in problems:
            print("  -", p)
        print("Send me these lines plus the current text of those functions.")
        return 1
    write(texts)
    t2, p2 = plan(IMPORT_EDITS)
    if p2:
        print("  (importer edits skipped: import_real_data.py differs; weights can be added later)")
    else:
        write(t2)

    ok = True
    if "--no-tests" not in args:
        ok = run([sys.executable, "-m", "pytest",
                  "backend/tests/test_triage_rules.py", "backend/tests/test_triage_safety.py",
                  "backend/tests/test_triage_service.py", "backend/tests/test_triage_merge.py",
                  "backend/tests/test_triage_resolution_effects.py", "backend/tests/test_inquiry_detail.py",
                  "backend/tests/test_inquiry_resolution.py", "backend/tests/test_reply_context.py",
                  "backend/tests/test_inquiry_routes.py", "backend/tests/test_inquiry_actions_routes.py",
                  "-q"]) == 0
        print("\nPYTHON TESTS " + ("PASSED." if ok else "FAILED."))
    if "--no-tsc" not in args:
        tsc_ok = run("npx tsc --noEmit", shell=True) == 0
        print("TYPE CHECK " + ("PASSED." if tsc_ok else "FAILED."))
        ok = ok and tsc_ok
    if ok and "--backfill" in args:
        run([sys.executable, "scripts/retriage_inquiries.py", "--apply", "--ai", "--all"])

    if "--commit" not in args:
        return 0 if ok else 1
    if not ok:
        print("Not committing: something failed.")
        return 1
    branch = subprocess.run(["git", "branch", "--show-current"], capture_output=True,
                            text=True).stdout.strip()
    if branch != "portal-v2":
        print(f"Refusing to commit: on '{branch}', expected 'portal-v2'.")
        return 1
    files = [f for f in COMMIT_FILES if (ROOT / f).exists()]
    if run(["git", "add", *files]) or run(
            ["git", "commit", "-m", "feat: inquiry resolution + company history, grounded AI reply suggestions, label polish"]):
        return 1
    return run(["git", "push", "origin", "portal-v2"])


if __name__ == "__main__":
    sys.exit(main())
