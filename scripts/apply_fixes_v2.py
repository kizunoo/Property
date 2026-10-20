#!/usr/bin/env python3
"""
One command: fixes triage for repeated use, adds the missing portal secret, tests, runs the doctor.

    backend\\venv\\Scripts\\python scripts\\apply_fixes_v2.py            # fix + test + doctor
    backend\\venv\\Scripts\\python scripts\\apply_fixes_v2.py --commit   # ...and commit + push if tests pass

 1. triage_agent.py: build a fresh agent per run. Each triage run uses a new event loop; a shared
    agent can keep a network client tied to a closed loop and fail on the 2nd+ inquiry.
 2. backend/.env: add PORTAL_CODE_PEPPER if it is missing or empty (random value, never printed).
    Note: changing it invalidates any portal login codes already issued. None exist for real clients yet.
 3. Runs the triage + copilot tests, then scripts/copilot_doctor.py.
Exact-text edits only; if the code differs from what was reviewed it skips that edit and says so.
"""
from __future__ import annotations

import re
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()

OLD = '''async def _run(client_id: str, text: str) -> Optional[AiTriage]:
    sessions = InMemorySessionService()  # fresh per run: no state shared between customers
    runner = Runner(agent=triage_agent, app_name=APP_NAME, session_service=sessions)
'''
NEW = '''def _make_agent() -> Agent:
    """A fresh agent per run: asyncio.run() creates a new event loop each time, and a shared agent
    can keep a network client tied to a loop that has already been closed."""
    return Agent(name="inquiry_triage", model=MODEL,
                 description="Classifies inbound customer inquiries for the rep team.",
                 instruction=INSTRUCTION, tools=[get_account_context])


async def _run(client_id: str, text: str) -> Optional[AiTriage]:
    sessions = InMemorySessionService()  # fresh per run: no state shared between customers
    runner = Runner(agent=_make_agent(), app_name=APP_NAME, session_service=sessions)
'''


def patch_triage() -> None:
    path = ROOT / "backend" / "triage_agent.py"
    if not path.exists():
        print("  SKIP     backend/triage_agent.py not found (run from the project root)")
        return
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    eol = "\r\n" if "\r\n" in text else "\n"
    old, new = OLD.replace("\n", eol), NEW.replace("\n", eol)
    if "_make_agent()" in text:
        print("  SKIP     triage_agent.py: fresh agent per run (already applied)")
    elif text.count(old) == 1:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text.replace(old, new))
        print("  APPLY    triage_agent.py: fresh agent per run")
    else:
        print("  SKIP     triage_agent.py: code differs from what was reviewed; nothing changed")


def ensure_pepper() -> None:
    env = ROOT / "backend" / ".env"
    if not env.exists():
        print("  SKIP     backend/.env not found")
        return
    with open(env, encoding="utf-8", newline="") as f:
        lines = f.read().splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"\s*PORTAL_CODE_PEPPER\s*=\s*(.*)$", line)
        if m:
            if m.group(1).strip().strip("'\""):
                print("  SKIP     PORTAL_CODE_PEPPER already set")
                return
            lines[i] = f"PORTAL_CODE_PEPPER={secrets.token_urlsafe(48)}"
            break
    else:
        lines.append(f"PORTAL_CODE_PEPPER={secrets.token_urlsafe(48)}")
    with open(env, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines) + "\n")
    print("  APPLY    PORTAL_CODE_PEPPER added to backend/.env (value not shown)")


def run(cmd: list[str]) -> int:
    print("\n$", " ".join(cmd))
    return subprocess.run(cmd).returncode


def main() -> int:
    args = set(sys.argv[1:])
    print("Applying fixes...")
    patch_triage()
    ensure_pepper()

    tests_ok = True
    if "--no-tests" not in args:
        tests_ok = run([sys.executable, "-m", "pytest", "backend/tests/test_triage_rules.py",
                        "backend/tests/test_triage_service.py", "backend/tests/test_triage_routes.py",
                        "backend/tests/test_copilot_fixes.py", "-q"]) == 0
        print("\nTESTS PASSED." if tests_ok else "\nTESTS FAILED.")
    if "--no-doctor" not in args:
        run([sys.executable, "scripts/copilot_doctor.py"])

    if "--commit" in args:
        if not tests_ok:
            print("Not committing: tests failed.")
            return 1
        branch = subprocess.run(["git", "branch", "--show-current"], capture_output=True,
                                text=True).stdout.strip()
        if branch != "portal-v2":
            print(f"Refusing to commit: on '{branch}', expected 'portal-v2'.")
            return 1
        files = [f for f in ("backend/triage_agent.py", "scripts/copilot_doctor.py",
                             "scripts/apply_fixes_v2.py") if (ROOT / f).exists()]
        if run(["git", "add", *files]) or run(
                ["git", "commit", "-m", "fix: triage agent fresh per run; doctor client bug"]):
            return 1
        return run(["git", "push", "origin", "portal-v2"])
    return 0 if tests_ok else 1


if __name__ == "__main__":
    sys.exit(main())
