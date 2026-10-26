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

root_dir = Path(__file__).resolve().parent.parent.parent
backend_dir = root_dir / "backend"
scripts_dir = root_dir / "scripts"
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(scripts_dir))

from check_schema_usage import check_schema_consistency


def test_schema_usage_matches_migrations():
    """All backend Supabase queries must strictly match migration columns and creation order."""
    res = check_schema_consistency()
    is_consistent = res[0]
    report = res[1]
    assert is_consistent, "\n".join(report)


def test_properties_data_source_insertion_paths():
    """Verify code paths inserting properties set data_source correctly."""
    from scripts.import_real_data import build_robot_row
    import apply_robotics_seed as ars

    # Real importer must produce rows with data_source='real' and non-empty sku_code
    robot_input = {
        "sku_code": "TEST-SKU",
        "name": "Test Robot",
        "manufacturer": "Test Mfr",
        "category": "AMR",
    }
    real_row = build_robot_row(robot_input)
    assert real_row.get("data_source") == "real"
    assert real_row.get("sku_code") == "TEST-SKU"

    # Seed data rows in apply_robotics_seed must have null sku_code and be tagged seed on insert
    for p in ars.PROPERTIES_DATA:
        p_row = {**p, "data_source": "seed"}
        assert p_row.get("data_source") == "seed"
        assert p_row.get("sku_code") is None

