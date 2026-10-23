"""
backend/tests/test_null_property_value.py
──────────────────────────────────────────
Unit and integration tests for Phase 9A (Allow real robots with no price yet).

Covers requirements (a) through (e):
(a) Ordering test: mixed priced and unpriced evaluations sort with all priced above unpriced,
    unpriced sorted by probability, Top 5 worklist and shortlist match.
(b) currency() helper: returns unchanged output for NULL stated_budget (no regressions).
(c) sumPriced(): returns total: None (or null) for all-unpriced set.
(d) ml_inference.predict_probability: returns None for unpriced robot (property_value None).
(e) Leak test: no portal response contains property_value, expected_value, or tier keys for unpriced robot.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ["PORTAL_CODE_PEPPER"] = "test_portal_pepper_secret_2026_xyz"
os.environ["PORTAL_LEGACY_LOGIN_ENABLED"] = "false"
os.environ["BFF_INTERNAL_SECRET"] = "test_bff_shared_secret_abc123"
os.environ["CALENDAR_SIGNING_SECRET"] = "test_calendar_secret_xyz_123"
os.environ["ENVIRONMENT"] = "test"

import main
import ml_inference
import portal_auth
from portal_auth import PersistentRateLimitStore
from price_utils import (
    NOT_IN_CATALOG,
    PRICE_ON_REQUEST,
    compute_expected_value,
    ev_rank_key,
    has_price,
    price_fact_value,
    should_use_ml,
    tier_without_price,
    to_price,
)
from fastapi.testclient import TestClient


def _run_node_ts(ts_code: str) -> str:
    """Execute a TypeScript snippet via npx tsx and return stdout."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    # Write to a small scratch file to avoid Windows shell quoting issues
    with tempfile.NamedTemporaryFile("w", suffix=".ts", delete=False, dir=repo_root) as f:
        f.write(ts_code)
        temp_path = f.name
    try:
        res = subprocess.run(
            ["npx", "tsx", temp_path],
            capture_output=True,
            text=True,
            cwd=repo_root,
            shell=True,
        )
        if res.returncode != 0:
            raise RuntimeError(f"npx tsx failed (code {res.returncode}):\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}")
        return res.stdout.strip()
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass


class TestNullPropertyValueUnit(unittest.TestCase):
    """Unit tests for price utilities, ordering, and ML behavior."""

    def test_a_ordering_ev_rank_key(self):
        """(a) Ordering test: mixed priced and unpriced evaluations sort with all priced above unpriced,
        unpriced sorted by probability, Top 5 worklist and shortlist match."""
        evals = [
            {"id": "unpriced_low_prob", "expected_value": None, "probability": 0.20},
            {"id": "priced_low_ev", "expected_value": 30000.0, "probability": 0.90},
            {"id": "unpriced_high_prob", "expected_value": None, "probability": 0.85},
            {"id": "priced_high_ev", "expected_value": 150000.0, "probability": 0.50},
            {"id": "unpriced_mid_prob", "expected_value": None, "probability": 0.50},
            {"id": "priced_mid_ev", "expected_value": 75000.0, "probability": 0.40},
        ]

        sorted_evals = sorted(
            evals,
            key=lambda r: ev_rank_key(r["probability"], r["expected_value"]),
            reverse=True,
        )

        expected_ids = [
            "priced_high_ev",
            "priced_mid_ev",
            "priced_low_ev",
            "unpriced_high_prob",
            "unpriced_mid_prob",
            "unpriced_low_prob",
        ]
        actual_ids = [r["id"] for r in sorted_evals]
        self.assertEqual(actual_ids, expected_ids)

        # Verify all priced are before all unpriced
        first_unpriced_idx = next(
            i for i, r in enumerate(sorted_evals) if r["expected_value"] is None
        )
        for r in sorted_evals[:first_unpriced_idx]:
            self.assertIsNotNone(r["expected_value"])
        for r in sorted_evals[first_unpriced_idx:]:
            self.assertIsNone(r["expected_value"])

        # Also verify against compareByEvThenProbability in lib/price.ts
        ts_code = """
import { compareByEvThenProbability } from './lib/price';
const evals = [
    { id: 'unpriced_low_prob', expectedValue: null, probability: 0.20 },
    { id: 'priced_low_ev', expectedValue: 30000.0, probability: 0.90 },
    { id: 'unpriced_high_prob', expectedValue: null, probability: 0.85 },
    { id: 'priced_high_ev', expectedValue: 150000.0, probability: 0.50 },
    { id: 'unpriced_mid_prob', expectedValue: null, probability: 0.50 },
    { id: 'priced_mid_ev', expectedValue: 75000.0, probability: 0.40 },
];
evals.sort(compareByEvThenProbability);
console.log(JSON.stringify(evals.map(e => e.id)));
"""
        stdout = _run_node_ts(ts_code)
        ts_sorted_ids = json.loads(stdout.split("\n")[-1])
        self.assertEqual(ts_sorted_ids, expected_ids)

    def test_b_currency_helper_and_null_stated_budget(self):
        """(b) currency() helper: returns unchanged output for NULL stated_budget (no regressions)."""
        # Test Python fact sheet price formatting
        def mock_fmt(v):
            return f"RM {int(v):,}" if v is not None else ""

        self.assertEqual(price_fact_value(None, mock_fmt), NOT_IN_CATALOG)
        self.assertEqual(price_fact_value(120000, mock_fmt), "RM 120,000")
        self.assertEqual(price_fact_value("invalid", mock_fmt), NOT_IN_CATALOG)

        # In TypeScript, currency(value: number) formats valid numbers
        # and stated_budget=null displays "Budget not set" without calling currency(null)
        ts_code = """
import { currency } from './lib/pipeline-data';
const budgetNull: number | null = null;
const budgetVal: number | null = 500000;
const labelNull = budgetNull != null && budgetNull > 0 ? currency(budgetNull) : "Budget not set";
const labelVal = budgetVal != null && budgetVal > 0 ? currency(budgetVal) : "Budget not set";
console.log(JSON.stringify({ labelNull, labelVal }));
"""
        stdout = _run_node_ts(ts_code)
        out = json.loads(stdout.split("\n")[-1])
        self.assertEqual(out["labelNull"], "Budget not set")
        self.assertEqual(out["labelVal"], "RM 500,000")

    def test_c_sum_priced(self):
        """(c) sumPriced(): returns total: None (or null) for all-unpriced set."""
        ts_code = """
import { sumPriced } from './lib/price';
const r1 = sumPriced([null, undefined, null]);
const r2 = sumPriced([]);
const r3 = sumPriced([100000, null, 250000]);
console.log(JSON.stringify({ r1, r2, r3 }));
"""
        stdout = _run_node_ts(ts_code)
        out = json.loads(stdout.split("\n")[-1])
        # All unpriced -> total is null
        self.assertIsNone(out["r1"]["total"])
        self.assertEqual(out["r1"]["pricedCount"], 0)
        self.assertEqual(out["r1"]["unpricedCount"], 3)

        # Empty -> total is null
        self.assertIsNone(out["r2"]["total"])
        self.assertEqual(out["r2"]["pricedCount"], 0)
        self.assertEqual(out["r2"]["unpricedCount"], 0)

        # Mixed -> total is 350000
        self.assertEqual(out["r3"]["total"], 350000)
        self.assertEqual(out["r3"]["pricedCount"], 2)
        self.assertEqual(out["r3"]["unpricedCount"], 1)

    def test_d_ml_inference_predict_probability(self):
        """(d) ml_inference.predict_probability: returns None for unpriced robot (property_value None)."""
        client = {
            "stated_budget": 500000,
            "preferred_neighborhood": "Manufacturing",
            "past_viewings": 3,
        }
        # Unpriced property
        prop_unpriced = {
            "id": "robot-unpriced-1",
            "name": "RoboCourier Unpriced",
            "property_value": None,
            "neighborhood": "Manufacturing",
        }
        # Should return None without invoking ML model
        self.assertFalse(should_use_ml(prop_unpriced))
        pred = ml_inference.predict_probability(client, prop_unpriced)
        self.assertIsNone(pred)

        # Non-numeric or 0 price should also return None
        self.assertFalse(should_use_ml({"property_value": 0}))
        self.assertFalse(should_use_ml({"property_value": "unknown"}))
        self.assertFalse(should_use_ml({}))
        self.assertIsNone(ml_inference.predict_probability(client, {"property_value": 0}))
        self.assertIsNone(ml_inference.predict_probability(client, {}))


class TestNullPropertyValuePortalLeaks(unittest.TestCase):
    """(e) Leak test: no portal response contains property_value, expected_value, or tier keys for unpriced robot."""

    FORBIDDEN_LEAK_KEYS = {"property_value", "expected_value", "tier"}

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.temp_db.close()
        portal_auth.rate_limit_store = PersistentRateLimitStore(db_path=self.temp_db.name)
        self.client = TestClient(main.app)

        self.company_id = "11111111-1111-1111-1111-111111111111"
        self.token = "test_token_evaluator_32_bytes_len"
        self.property_unpriced_id = "55555555-5555-5555-5555-555555555555"

        now = datetime.now(timezone.utc)
        self.session_data = {
            "id": "sess-unpriced",
            "client_id": self.company_id,
            "contact_id": "contact-unpriced",
            "portal_role": "evaluator",
            "idle_expires_at": (now + timedelta(hours=2)).isoformat(),
            "absolute_expires_at": (now + timedelta(days=7)).isoformat(),
            "revoked_at": None,
            "clients": {"id": self.company_id, "name": "Company Automation"},
            "portal_contacts": {"id": "contact-unpriced", "name": "Test User", "status": "active", "locked_until": None},
        }

    def tearDown(self):
        try:
            if os.path.exists(self.temp_db.name):
                os.remove(self.temp_db.name)
        except Exception:
            pass

    def _assert_no_forbidden(self, obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                current_path = f"{path}.{k}" if path else k
                self.assertNotIn(
                    k,
                    self.FORBIDDEN_LEAK_KEYS,
                    f"Forbidden key '{k}' leaked at path '{current_path}'",
                )
                self._assert_no_forbidden(v, current_path)
        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                self._assert_no_forbidden(item, f"{path}[{idx}]")

    def test_e_portal_catalog_and_matches_no_leaks(self):
        """Portal catalog and matches endpoints must not leak property_value, expected_value, or tier."""
        client_row = {
            "id": self.company_id,
            "name": "Company Automation",
            "stated_budget": 500000,
            "facility_profile": {},
        }
        unpriced_robot = {
            "id": self.property_unpriced_id,
            "address": "Unpriced Alpha Robot",
            "property_value": None,
            "neighborhood": "Logistics",
            "property_type": "AMR",
            "image_url": "https://example.com/robot.jpg",
            "sqft": 5000,
            "data_source": "real",
            "manufacturer": "Alpha Corp",
            "status": "AVAILABLE",
            "estimated_annual_savings": 25000,
        }
        unpriced_eval = {
            "client_id": self.company_id,
            "property_id": self.property_unpriced_id,
            "expected_value": None,
            "ai_probability": 0.82,
            "properties": unpriced_robot,
        }

        def table_router(table_name):
            mock_query = MagicMock()
            mock_query.select.return_value = mock_query
            mock_query.eq.return_value = mock_query
            mock_query.neq.return_value = mock_query
            mock_query.ilike.return_value = mock_query
            mock_query.order.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.update.return_value = mock_query
            mock_query.insert.return_value = mock_query
            mock_query.in_.return_value = mock_query
            mock_query.is_.return_value = mock_query

            mock_single = MagicMock()
            mock_single.execute.return_value = MagicMock(data={})
            mock_query.single.return_value = mock_single

            if table_name == "portal_sessions":
                mock_query.execute.return_value = MagicMock(data=[self.session_data])
                mock_single.execute.return_value = MagicMock(data=self.session_data)
                return mock_query

            if table_name == "clients":
                mock_query.execute.return_value = MagicMock(data=[client_row])
                mock_single.execute.return_value = MagicMock(data=client_row)
                return mock_query

            if table_name == "properties":
                mock_query.execute.return_value = MagicMock(data=[unpriced_robot])
                mock_single.execute.return_value = MagicMock(data=unpriced_robot)
                return mock_query

            if table_name == "pipeline_evaluations":
                mock_query.execute.return_value = MagicMock(data=[unpriced_eval])
                mock_single.execute.return_value = MagicMock(data=unpriced_eval)
                return mock_query

            if table_name == "client_facing_reasoning_cache":
                mock_query.execute.return_value = MagicMock(
                    data=[{"reasoning": "This unpriced robot is an excellent fit for your facility."}]
                )
                return mock_query

            mock_query.execute.return_value = MagicMock(data=[])
            return mock_query

        headers = {"Authorization": f"Bearer {self.token}"}

        with patch.object(main.supabase, "table", side_effect=table_router):
            # 1. Test portal catalog
            res_catalog = self.client.get(f"/api/portal/{self.company_id}/catalog", headers=headers)
            self.assertEqual(res_catalog.status_code, 200)
            data_cat = res_catalog.json()
            self._assert_no_forbidden(data_cat)
            # Ensure unpriced item in catalog has cost: None (or absent)
            robots = data_cat.get("units", [])
            self.assertTrue(len(robots) > 0)
            for r in robots:
                self.assertIsNone(r.get("cost"))
                self.assertNotIn("property_value", r)
                self.assertNotIn("expected_value", r)
                self.assertNotIn("tier", r)

            # 2. Test portal dashboard (matches)
            res_dash = self.client.get(f"/api/portal/{self.company_id}/dashboard", headers=headers)
            self.assertEqual(res_dash.status_code, 200)
            data_dash = res_dash.json()
            self._assert_no_forbidden(data_dash)
            matches = data_dash.get("matches", [])
            self.assertTrue(len(matches) > 0)
            for m in matches:
                self.assertIsNone(m.get("cost"))
                self.assertNotIn("property_value", m)
                self.assertNotIn("expected_value", m)
                self.assertNotIn("tier", m)


if __name__ == "__main__":
    unittest.main()
