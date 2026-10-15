"""
backend/tests/test_schema_consistency.py
────────────────────────────────────────
Automated unit test that executes check_schema_usage.py.
Validates:
1. Migration table creation ordering (portal_contacts before portal_sessions, agent_accounts before agent_sessions).
2. Every column read or written by the backend matches CREATE TABLE / ALTER TABLE definitions.
"""

import sys
from pathlib import Path

scripts_dir = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from check_schema_usage import check_schema_consistency


def test_schema_usage_matches_migrations():
    """All backend Supabase queries must strictly match migration columns and creation order."""
    res = check_schema_consistency()
    is_consistent = res[0]
    report = res[1]
    assert is_consistent, "\n".join(report)
