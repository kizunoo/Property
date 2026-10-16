#!/usr/bin/env python3
"""
Scope guard for the copilot change. Run before committing:  python scripts/check_copilot_scope.py
Fails (exit 1) if the working tree touches files outside the allowlist, deletes lines from
files that must be additions-only, or adds something that looks like an API key.
Optional: --base <commit> to compare against something other than HEAD.
"""
from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys

FREE_EDIT = [  # may be created or edited freely
    "backend/copilot_tools.py", "backend/copilot_agent.py", "backend/copilot_routes.py",
    "backend/tests/test_copilot_tools.py", "backend/tests/test_copilot_routes.py",
    "components/pipeline/copilot-panel.tsx", "scripts/check_copilot_scope.py",
    "docs/COPILOT_BLUEPRINT.md", "docs/ROUTE_POLICY_MATRIX.md",
]
ADD_ONLY = [  # existing files: lines may be ADDED, none deleted or changed
    "backend/main.py", "backend/route_policies.py", "app/page.tsx",
    "requirements*.txt", "backend/requirements*.txt",
]
KEY_PATTERNS = [re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
                re.compile(r"(GOOGLE_API_KEY|GEMINI_API_KEY)\s*=\s*['\"]?[A-Za-z0-9_\-]{12,}")]


def sh(*cmd: str) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, p) for p in patterns)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="HEAD")
    base = ap.parse_args().base

    changed: dict[str, tuple[int, int]] = {}
    for line in sh("git", "diff", "--numstat", base).splitlines():
        added, deleted, path = line.split("\t", 2)
        changed[path] = (0 if added == "-" else int(added), 0 if deleted == "-" else int(deleted))
    untracked = [p for p in sh("git", "ls-files", "--others", "--exclude-standard").splitlines() if p]
    for p in untracked:
        changed.setdefault(p, (1, 0))

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
        print("Revert the out-of-scope changes (git checkout -- <file>) or stop and ask.")
        return 1
    print("SCOPE CHECK PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
