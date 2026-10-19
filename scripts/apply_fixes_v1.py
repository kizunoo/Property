#!/usr/bin/env python3
"""
Applies the three reviewed fixes to your repo, verifies them, and (optionally) commits + pushes.
Run from the project root:

    backend\\venv\\Scripts\\python scripts\\apply_fixes_v1.py            # apply + run tests
    backend\\venv\\Scripts\\python scripts\\apply_fixes_v1.py --commit   # ...and commit + push if tests pass

Safe by design:
  * Every edit is an exact-text match. If the code differs from what was reviewed, NOTHING is written.
  * Re-running is harmless (already-applied edits are detected).
  * --commit stages ONLY the files named below. Other people's uncommitted files stay untouched.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()

NEW_LOOKUP = '''        rows = q.limit(2).execute().data or []
        if len(rows) == 1:
            return rows[0]
        if len(rows) > 1:
            return None  # ambiguous name: refuse rather than guess
'''
OLD_LOOKUP = '''        rows = q.limit(1).execute().data or []
        if rows:
            return rows[0]
'''
OLD_FALLBACK = '''    if not robots:
        robots = (db.table(ROBOT_TABLE)
                  .select(f"{ROBOT_NAME_COL},manufacturer,specs,{ROBOT_PRICE_COL}")
                  .limit(30).execute().data) or []
'''
OLD_ERR = '{"error": "Client not found or not assigned to you."}'
NEW_ERR = ('{"error": "Client not found, not assigned to you, or the name matches several '
           'companies. Use the full company name."}')
OLD_LOGIN = 'raise HTTPException(status_code=500, detail=f"Login handler error: {exc}")'
NEW_LOGIN = 'raise HTTPException(status_code=500, detail="Login failed due to a server error.")'

# (file, old, new, expected_count_of_old, description)
EDITS = [
    ("backend/agent_routes.py", OLD_LOGIN, NEW_LOGIN, 1,
     "login errors no longer leak exception text"),
    ("backend/copilot_tools.py", OLD_FALLBACK, "", 1,
     "copilot never lists dummy robots as the real catalog"),
    ("backend/copilot_tools.py", OLD_LOOKUP, NEW_LOOKUP, 1,
     "ambiguous company names are refused instead of guessed"),
    ("backend/copilot_tools.py", OLD_ERR, NEW_ERR, 2,
     "clearer 'not found / ambiguous name' message"),
]
COMMIT_FILES = [
    "backend/agent_routes.py", "backend/copilot_tools.py", "backend/copilot_agent.py",
    "backend/tests/test_copilot_fixes.py", "scripts/apply_fixes_v1.py", "scripts/copilot_doctor.py",
]


def read(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def plan() -> dict[str, str]:
    """Compute new file contents for every edit, or exit without writing anything."""
    contents: dict[str, str] = {}
    problems = []
    for rel, old, new, count, desc in EDITS:
        path = ROOT / rel
        if not path.exists():
            problems.append(f"{rel}: file not found (run this from the project root)")
            continue
        text = contents.get(rel, read(path))
        eol = "\r\n" if "\r\n" in text else "\n"
        o, n = old.replace("\n", eol), new.replace("\n", eol)
        found = text.count(o)
        if found == count:
            contents[rel] = text.replace(o, n)
            print(f"  APPLY    {rel}: {desc}")
        elif found == 0 and (n and n in text or not n):
            contents[rel] = text
            print(f"  SKIP     {rel}: {desc} (already applied)")
        else:
            problems.append(f"{rel}: expected {count} match(es) for '{desc}', found {found}. "
                            "The code differs from what was reviewed.")
    if problems:
        print("\nNOTHING WAS CHANGED. Problems:")
        for p in problems:
            print("  -", p)
        print("Send me these lines and the current text of the file around them.")
        sys.exit(1)
    return contents


def run(cmd: list[str]) -> int:
    print("\n$", " ".join(cmd))
    return subprocess.run(cmd).returncode


def main() -> int:
    commit = "--commit" in sys.argv
    skip_tests = "--no-tests" in sys.argv
    print("Planning edits (nothing written yet)...")
    contents = plan()
    for rel, text in contents.items():
        with open(ROOT / rel, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    print("\nEdits written.")

    if skip_tests:
        return 0
    code = run([sys.executable, "-m", "pytest", "backend/tests/test_copilot_fixes.py",
                "backend/tests/test_copilot_tools.py", "-q"])
    if code:
        print("\nTESTS FAILED. Nothing was committed. Paste the output above to me.")
        return 1
    print("\nTESTS PASSED.")
    if not commit:
        print("Run again with --commit to commit and push these files.")
        return 0

    branch = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True).stdout.strip()
    if branch != "portal-v2":
        print(f"Refusing to commit: you are on '{branch}', expected 'portal-v2'.")
        return 1
    files = [f for f in COMMIT_FILES if (ROOT / f).exists()]
    if run(["git", "add", *files]) or run(
            ["git", "commit", "-m",
             "fix: honest robot catalog, safe login errors, unambiguous copilot name lookup"]):
        return 1
    return run(["git", "push", "origin", "portal-v2"])


if __name__ == "__main__":
    sys.exit(main())
