#!/usr/bin/env python3
"""
UI polish + safety rule. One command:

    backend\\venv\\Scripts\\python scripts\\apply_fixes_v3.py            # patch + test + type-check
    backend\\venv\\Scripts\\python scripts\\apply_fixes_v3.py --commit   # ...and commit + push if all pass

 1. triage_rules.py: questions about hazards / safety / injury / smoke / overheating are now treated
    as high priority (they were being labelled "normal").
 2. copilot-panel.tsx: moves the Ask Copilot button and panel left so the WhatsApp bubble no longer covers it.
Exact-text edits only; any edit whose code differs from what was reviewed is skipped with a warning.
The restyled priority-inquiries.tsx comes with the bundle (unzip it over the old file).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()

SAFETY_DEF = '''_SAFETY = re.compile(
    r"\\b(hazard\\w*|danger\\w*|unsafe|safety|injur\\w*|accident\\w*|harm\\w*|fire|smok\\w*|burn\\w*|"
    r"spark\\w*|overheat\\w*|explo\\w*|electric shock|toxic|bahaya)\\b", re.I)
'''

EDITS = [
    ("backend/triage_rules.py",
     "@dataclass(frozen=True)\nclass Facts:",
     SAFETY_DEF + "\n\n@dataclass(frozen=True)\nclass Facts:",
     "safety wording pattern"),
    ("backend/triage_rules.py",
     '    category = "general"\n    for name, pattern in _RULES:\n',
     '    if _SAFETY.search(t):  # safety concerns always reach a human quickly\n'
     '        return "complaint_issue", bool(_URGENT.search(t))\n'
     '    category = "general"\n    for name, pattern in _RULES:\n',
     "safety questions classified as problem/safety concern"),
    ("backend/triage_rules.py",
     '    "complaint_issue": "Complaint or problem",',
     '    "complaint_issue": "Problem or safety concern",',
     "category label mentions safety"),
    ("components/pipeline/copilot-panel.tsx",
     "fixed bottom-4 right-4 z-50",
     "fixed bottom-4 right-24 z-50",
     "Ask Copilot button clear of the WhatsApp bubble"),
    ("components/pipeline/copilot-panel.tsx",
     "fixed bottom-16 right-4 z-50",
     "fixed bottom-16 right-24 z-50",
     "Copilot panel clear of the WhatsApp bubble"),
]


def patch_all() -> None:
    for rel, old, new, desc in EDITS:
        path = ROOT / rel
        if not path.exists():
            print(f"  SKIP     {rel}: not found (run from the project root)")
            continue
        with open(path, encoding="utf-8", newline="") as f:
            text = f.read()
        eol = "\r\n" if "\r\n" in text else "\n"
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        if n in text:
            print(f"  SKIP     {rel}: {desc} (already applied)")
        elif text.count(o) == 1:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text.replace(o, n))
            print(f"  APPLY    {rel}: {desc}")
        else:
            print(f"  SKIP     {rel}: {desc} (code differs from what was reviewed; nothing changed)")


def run(cmd, shell=False) -> int:
    print("\n$", cmd if shell else " ".join(cmd))
    return subprocess.run(cmd, shell=shell).returncode


def main() -> int:
    print("Applying fixes...")
    patch_all()
    ok = True
    if "--no-tests" not in sys.argv:
        ok = run([sys.executable, "-m", "pytest", "backend/tests/test_triage_rules.py",
                  "backend/tests/test_triage_safety.py", "backend/tests/test_triage_service.py",
                  "-q"]) == 0
        print("\nPYTHON TESTS " + ("PASSED." if ok else "FAILED."))
    if "--no-tsc" not in sys.argv:
        tsc_ok = run("npx tsc --noEmit", shell=True) == 0
        print("TYPE CHECK " + ("PASSED." if tsc_ok else "FAILED."))
        ok = ok and tsc_ok
    if "--commit" not in sys.argv:
        return 0 if ok else 1
    if not ok:
        print("Not committing: something failed.")
        return 1
    branch = subprocess.run(["git", "branch", "--show-current"], capture_output=True,
                            text=True).stdout.strip()
    if branch != "portal-v2":
        print(f"Refusing to commit: on '{branch}', expected 'portal-v2'.")
        return 1
    files = [f for f in ("backend/triage_rules.py", "backend/tests/test_triage_safety.py",
                         "components/pipeline/priority-inquiries.tsx",
                         "components/pipeline/copilot-panel.tsx", "scripts/apply_fixes_v3.py")
             if (ROOT / f).exists()]
    if run(["git", "add", *files]) or run(
            ["git", "commit", "-m", "feat(ui): restyle priority inquiries, safety triage rule, copilot button clear of WhatsApp"]):
        return 1
    return run(["git", "push", "origin", "portal-v2"])


if __name__ == "__main__":
    sys.exit(main())
