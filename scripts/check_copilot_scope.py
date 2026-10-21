#!/usr/bin/env python3
"""
Scope guard for the copilot change. Run before committing:  python scripts/check_copilot_scope.py
Fails (exit 1) if the working tree touches files outside the allowlist, deletes lines from
files that must be additions-only, or adds something that looks like an API key.
Pre-existing uncommitted work you did NOT ask for (other people's edits) is handled without
stashing or reverting anything:
  python scripts/check_copilot_scope.py --snapshot   # run ONCE before starting; records dirty files
Files whose content is unchanged since the snapshot are ignored by the check.
Optional: --base <commit> to compare against something other than HEAD.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys

FREE_EDIT = [  # may be created or edited freely
    "backend/copilot_tools.py", "backend/copilot_agent.py", "backend/copilot_routes.py",
    "backend/tests/test_copilot_tools.py", "backend/tests/test_copilot_routes.py",
    "components/pipeline/copilot-panel.tsx", "scripts/check_copilot_scope.py",
    "docs/COPILOT_BLUEPRINT.md", "docs/ROUTE_POLICY_MATRIX.md",
    # inquiry triage
    "backend/triage_rules.py", "backend/triage_service.py", "backend/triage_agent.py",
    "backend/triage_routes.py", "backend/tests/test_triage_rules.py",
    "backend/tests/test_triage_service.py", "backend/tests/test_triage_routes.py",
    "backend/tests/test_triage_portal_leak.py", "components/pipeline/priority-inquiries.tsx",
    "supabase/migrations/20261017100000_inquiry_triage.sql", "docs/TRIAGE_BLUEPRINT.md",
    # rep-side inquiry view
    "backend/inquiry_detail.py", "backend/inquiry_routes.py",
    "backend/tests/test_inquiry_detail.py", "backend/tests/test_inquiry_routes.py",
    "components/pipeline/inquiry-detail-modal.tsx", "components/pipeline/priority-inquiries.tsx",
    "backend/tests/test_triage_safety.py", "scripts/apply_fixes_v3.py",
    ".scope_snapshot.json",
]
ADD_ONLY = [  # existing files: lines may be ADDED, none deleted or changed
    "backend/main.py", "backend/route_policies.py", "app/page.tsx",
    "requirements*.txt", "backend/requirements*.txt", "scripts/db_verify.py",
]
SNAPSHOT = ".scope_snapshot.json"
KEY_PATTERNS = [re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
                re.compile(r"(GOOGLE_API_KEY|GEMINI_API_KEY)\s*=\s*['\"]?[A-Za-z0-9_\-]{12,}")]


def sh(*cmd: str) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def file_hash(path: str) -> str:
    return sh("git", "hash-object", path).strip() if os.path.exists(path) else "deleted"


def current_changes(base: str) -> dict[str, tuple[int, int]]:
    changed: dict[str, tuple[int, int]] = {}
    for line in sh("git", "diff", "--numstat", base).splitlines():
        added, deleted, path = line.split("\t", 2)
        changed[path] = (0 if added == "-" else int(added), 0 if deleted == "-" else int(deleted))
    for p in sh("git", "ls-files", "--others", "--exclude-standard").splitlines():
        if p:
            changed.setdefault(p, (1, 0))
    return changed


def matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, p) for p in patterns)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="HEAD")
    ap.add_argument("--snapshot", action="store_true",
                    help="record currently-dirty files so pre-existing edits are ignored")
    args = ap.parse_args()
    base = args.base

    if args.snapshot:
        snap = {p: file_hash(p) for p in current_changes(base) if p != SNAPSHOT}
        with open(SNAPSHOT, "w", encoding="utf-8") as f:
            json.dump(snap, f, indent=1)
        print(f"Snapshot saved: {len(snap)} pre-existing changed file(s) will be ignored if untouched.")
        return 0

    snap = {}
    if os.path.exists(SNAPSHOT):
        with open(SNAPSHOT, encoding="utf-8") as f:
            snap = json.load(f)

    changed = {p: v for p, v in current_changes(base).items()
               if not (p in snap and snap[p] == file_hash(p))}
    untracked = [p for p in sh("git", "ls-files", "--others", "--exclude-standard").splitlines()
                 if p and p in changed]

    problems = []
    for path, (added, deleted) in sorted(changed.items()):
        if matches(path, FREE_EDIT):
            continue
        if matches(path, ADD_ONLY):
            if deleted:
                problems.append(f"{path}: {deleted} line(s) deleted/changed (additions only allowed)")
            continue
        problems.append(f"{path}: not on the allowlist")

    added_text = sh("git", "diff", "-U0", base)
    for p in untracked:
        try:
            added_text += "\n+" + open(p, encoding="utf-8", errors="ignore").read()
        except OSError:
            pass
    for pat in KEY_PATTERNS:
        if pat.search("\n".join(l for l in added_text.splitlines() if l.startswith("+"))):
            problems.append("an API key / key assignment appears in added lines (remove it)")
            break

    print(f"Checked {len(changed)} changed file(s) against {base}.")
    if problems:
        print("SCOPE CHECK FAILED:")
        for p in problems:
            print("  -", p)
        print("Revert only changes YOU made out of scope. Never revert or stash files that were already "
              "modified before you started; if unsure, stop and ask the human.")
        return 1
    print("SCOPE CHECK PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
