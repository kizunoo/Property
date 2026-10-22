#!/usr/bin/env python3
"""
Fixes the AI labelling problems seen in the Priority inquiries card. One command:

    backend\\venv\\Scripts\\python scripts\\apply_fixes_v4.py                       # fix + test + type-check + doctor
    backend\\venv\\Scripts\\python scripts\\apply_fixes_v4.py --backfill            # ...and re-label existing inquiries (uses the AI)
    backend\\venv\\Scripts\\python scripts\\apply_fixes_v4.py --commit --backfill   # ...and commit + push if everything passes

What it fixes
 1. Label coherence: category + reasons now come from the analysis that produced the priority
    (before: "Technical / URGENT / 3 inquiries this week" for a safety question, because the AI's
    category replaced the rules' safety category while the rules still set the priority).
 2. Gibberish: the AI may lower an "unclear" message to LOW when the rules found nothing in it,
    and unclear messages no longer get repeat-contact bumps. A real request can't be hidden by
    "ignore your rules": when the rules found any signal the AI still can't lower it.
 3. Silent AI failures: a log line now says when the model's reply was not valid JSON.
The matching UI (AI / rules-only tag per row, faster refresh while the AI is working) comes in the bundle.
Label edits are all-or-nothing: if the code differs from what was reviewed, nothing is written.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()

MERGE_FN = '''def merge_label(rules_category: str, rules_ts: bool, ai: AiTriage,
                facts: Facts) -> tuple[str, str, list[str]]:
    """Combine the rules' view and the AI's view into ONE coherent label: (priority, category, reasons).
    The higher priority wins and its category and reasons are kept, so the label always explains itself.
    The AI may only LOWER a label for a message the rules found nothing in (no keywords, no urgency):
    that turns gibberish into 'low' while a hidden "mark me low" cannot bury a real request."""
    if ai.category == "unclear" and rules_category in ("general", "unclear") and not rules_ts:
        return "low", "unclear", [CATEGORY_LABEL["unclear"]]
    r_pri, r_reasons = compute_priority(rules_category, rules_ts, facts)
    a_pri, a_reasons = compute_priority(ai.category, ai.time_sensitive or rules_ts, facts)
    if RANK[r_pri] >= RANK[a_pri]:
        return r_pri, rules_category, r_reasons
    return a_pri, ai.category, a_reasons


'''
SANITIZE_DEF = "def sanitize_text(value, limit: int = SUMMARY_MAX) -> str:"

LABEL_EDITS = [
    ("backend/triage_rules.py",
     '    reasons = [CATEGORY_LABEL.get(category, CATEGORY_LABEL["general"])]\n    bump = 0\n',
     '    reasons = [CATEGORY_LABEL.get(category, CATEGORY_LABEL["general"])]\n'
     '    if category == "unclear":\n'
     '        return "low", reasons  # nothing to act on: repeat contact, quotes etc. never raise it\n'
     '    bump = 0\n',
     "unclear messages get no priority bumps"),
    ("backend/triage_rules.py", SANITIZE_DEF, MERGE_FN + SANITIZE_DEF,
     "coherent label merge (priority, category, reasons)"),
    ("backend/triage_service.py",
     "compute_priority, escalate_only, sanitize_text)",
     "compute_priority, escalate_only, merge_label, sanitize_text)",
     "import merge_label"),
    ("backend/triage_service.py",
     '''        ai_priority, reasons = compute_priority(ai.category, ai.time_sensitive or rules_ts, facts)
        final = escalate_only(rules_priority, ai_priority)
        db.table(INQUIRY_TABLE).update({
            "triage_status": "ai", "triage_priority": final, "triage_category": ai.category,
            "triage_summary": ai.summary, "triage_reasons": reasons,
            "triaged_at": _now().isoformat(),
        }).eq("id", inquiry_id).execute()
        _maybe_alert(db, client_id, inquiry_id, final, ai.category, ai.summary)
''',
     '''        rules_category, _ = classify_by_rules(text)
        final, category, reasons = merge_label(rules_category, rules_ts, ai, facts)
        db.table(INQUIRY_TABLE).update({
            "triage_status": "ai", "triage_priority": final, "triage_category": category,
            "triage_summary": ai.summary, "triage_reasons": reasons,
            "triaged_at": _now().isoformat(),
        }).eq("id", inquiry_id).execute()
        _maybe_alert(db, client_id, inquiry_id, final, category, ai.summary)
''',
     "stored label uses the merged, self-explaining result"),
]
LOG_EDIT = ("backend/triage_agent.py",
            "    return parse_ai_output(final)\n",
            '    result = parse_ai_output(final)\n'
            '    if result is None:\n'
            '        import logging\n'
            '        logging.getLogger("triage").warning(\n'
            '            "triage model reply was not valid JSON (%d chars)", len(final))\n'
            '    return result\n',
            "log when the model reply is not valid JSON")


def read(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def plan(edits):
    """Return ({file: new_text}, problems, applied_count). Nothing is written here."""
    texts, problems, applied = {}, [], 0
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
            applied += 1
            print(f"  APPLY    {rel}: {desc}")
        else:
            problems.append(f"{rel}: '{desc}' (code differs from what was reviewed)")
        texts[rel] = text
    return texts, problems, applied


def write(texts: dict) -> None:
    for rel, text in texts.items():
        with open(ROOT / rel, "w", encoding="utf-8", newline="") as f:
            f.write(text)


def run(cmd, shell=False) -> int:
    print("\n$", cmd if shell else " ".join(cmd))
    return subprocess.run(cmd, shell=shell).returncode


def main() -> int:
    args = set(sys.argv[1:])
    print("Planning label fixes (all-or-nothing)...")
    texts, problems, applied = plan(LABEL_EDITS)
    if problems:
        print("\nNOTHING WAS CHANGED. Problems:")
        for p in problems:
            print("  -", p)
        print("Send me these lines plus the current text of those functions.")
        return 1
    write(texts)
    t2, p2, _ = plan([LOG_EDIT])
    if p2:
        print("  (log edit skipped: triage_agent.py differs from what was reviewed; fixes still work)")
    else:
        write(t2)

    ok = True
    if "--no-tests" not in args:
        ok = run([sys.executable, "-m", "pytest", "backend/tests/test_triage_rules.py",
                  "backend/tests/test_triage_safety.py", "backend/tests/test_triage_service.py",
                  "backend/tests/test_triage_merge.py", "-q"]) == 0
        print("\nPYTHON TESTS " + ("PASSED." if ok else "FAILED."))
    if "--no-tsc" not in args:
        tsc_ok = run("npx tsc --noEmit", shell=True) == 0
        print("TYPE CHECK " + ("PASSED." if tsc_ok else "FAILED."))
        ok = ok and tsc_ok
    if ok and "--backfill" in args:
        run([sys.executable, "scripts/retriage_inquiries.py", "--apply", "--ai"])
    if "--no-doctor" not in args:
        run([sys.executable, "scripts/triage_doctor.py"])

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
    files = [f for f in ("backend/triage_rules.py", "backend/triage_service.py", "backend/triage_agent.py",
                         "backend/tests/test_triage_merge.py",
                         "components/pipeline/priority-inquiries.tsx",
                         "components/pipeline/inquiry-detail-modal.tsx",
                         "scripts/apply_fixes_v4.py", "scripts/triage_doctor.py",
                         "scripts/retriage_inquiries.py") if (ROOT / f).exists()]
    if run(["git", "add", *files]) or run(
            ["git", "commit", "-m", "fix: coherent AI triage labels, gibberish handling, AI/rules tag, triage doctor"]):
        return 1
    return run(["git", "push", "origin", "portal-v2"])


if __name__ == "__main__":
    sys.exit(main())
