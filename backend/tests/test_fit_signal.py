"""
backend/tests/test_fit_signal.py
────────────────────────────────
Unit and integration tests for PHASE 9B-3:
- Industry fit signal (match, mismatch, unknown facility type returns None, healthcare, list/string parsing)
- facility_profile parsing as dict and string
- Scoring for unpriced real robots (0.6667 on match, 0.1667 on mismatch)
- Ranking using probability only when expected_value is None
- Portal responses contain no neighborhood, specs, fit, or tier internals
- Pick/skip reasons include fit_reason with zero numbers
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fit_signal import (
    client_facility_type,
    fit_reason,
    industry_fit,
    parse_industries,
    renormalize,
    robot_target_industries,
)
from price_utils import ev_rank_key
from scoring_engine import build_pick_skip_reasons, score


class TestFitSignalUnit(unittest.TestCase):
    def test_parse_industries(self):
        self.assertEqual(parse_industries("logistics;warehousing"), {"logistics", "warehousing"})
        self.assertEqual(parse_industries("logistics, warehousing"), {"logistics", "warehousing"})
        self.assertEqual(parse_industries(["logistics", "warehousing"]), {"logistics", "warehousing"})
        self.assertEqual(parse_industries(None), set())
        self.assertEqual(parse_industries(""), set())

    def test_client_facility_type_dict_and_string(self):
        # facility_profile as dict
        self.assertEqual(client_facility_type({"facility_profile": {"facility_type": "warehouse"}}), "warehouse")
        # facility_profile as JSON string
        self.assertEqual(client_facility_type({"facility_profile": '{"facility_type": "manufacturing"}'}), "manufacturing")
        # plain clients.facility_type fallback
        self.assertEqual(client_facility_type({"facility_type": "logistics"}), "logistics")
        # None when unknown
        self.assertIsNone(client_facility_type({}))
        self.assertIsNone(client_facility_type(None))

    def test_robot_target_industries(self):
        # specs as dict
        self.assertEqual(
            robot_target_industries({"specs": {"target_industries": "logistics;warehousing"}}),
            {"logistics", "warehousing"},
        )
        # specs as JSON string
        self.assertEqual(
            robot_target_industries({"specs": '{"target_industries": "manufacturing"}'}),
            {"manufacturing"},
        )
        self.assertEqual(robot_target_industries({}), set())

    def test_industry_fit_match_and_mismatch(self):
        # Match
        self.assertEqual(industry_fit("warehouse", "logistics;warehousing"), 1.0)
        self.assertEqual(industry_fit("manufacturing", "manufacturing"), 1.0)
        # Mismatch
        self.assertEqual(industry_fit("warehouse", "healthcare"), 0.0)
        self.assertEqual(industry_fit("manufacturing", "retail"), 0.0)

    def test_unknown_facility_type_returns_none(self):
        # Never guesses: unknown facility type returns None
        self.assertIsNone(industry_fit("unlisted_aerospace_plant", "logistics"))
        self.assertIsNone(industry_fit("", "logistics"))
        self.assertIsNone(industry_fit(None, "logistics"))
        self.assertIsNone(industry_fit("warehouse", None))
        self.assertIsNone(industry_fit("warehouse", ""))

    def test_healthcare_synonyms(self):
        self.assertEqual(industry_fit("healthcare", "healthcare"), 1.0)
        self.assertEqual(industry_fit("hospital", "healthcare"), 1.0)
        self.assertEqual(industry_fit("hospital", ["healthcare", "cleanroom"]), 1.0)

    def test_fit_reason_has_no_numbers(self):
        r_match = fit_reason(1.0)
        r_mismatch = fit_reason(0.0)
        r_unknown = fit_reason(None)
        for r in (r_match, r_mismatch, r_unknown):
            self.assertFalse(any(c.isdigit() for c in r), f"Reason '{r}' must not contain numbers")


class TestScoringWithFitSignal(unittest.TestCase):
    def test_unpriced_real_robot_match(self):
        """Scoring for an unpriced real robot returns 0.6667 on match with six-company fixture."""
        client = {
            "budget": None,
            "facility_profile": {"facility_type": "warehouse"},
            "engagement_history": 0,
            "preferred_neighborhood": None,
        }
        prop = {
            "property_value": None,
            "neighborhood": None,
            "specs": {"target_industries": "warehousing;logistics"},
        }
        res = score(client, prop)
        self.assertEqual(res["probability"], 0.6667)
        self.assertEqual(res["tier"], "TIER_2")
        self.assertIsNone(res["expected_value"])

    def test_unpriced_real_robot_mismatch(self):
        """Scoring for an unpriced real robot returns 0.1667 on mismatch with six-company fixture."""
        client = {
            "budget": None,
            "facility_profile": {"facility_type": "warehouse"},
            "engagement_history": 0,
            "preferred_neighborhood": None,
        }
        prop = {
            "property_value": None,
            "neighborhood": None,
            "specs": {"target_industries": "healthcare"},
        }
        res = score(client, prop)
        self.assertEqual(res["probability"], 0.1667)
        self.assertEqual(res["tier"], "TIER_3")
        self.assertIsNone(res["expected_value"])

    def test_pick_skip_reasons_contain_fit_reason_without_numbers(self):
        client = {
            "budget": None,
            "facility_profile": {"facility_type": "warehouse"},
            "engagement_history": 0,
        }
        prop_match = {
            "property_value": None,
            "neighborhood": None,
            "specs": {"target_industries": "logistics"},
        }
        pick, skip = build_pick_skip_reasons(client, prop_match)
        self.assertIn("Facility type matches robot target industries", pick)
        self.assertNotIn("Area mismatch", skip)

        prop_mismatch = {
            "property_value": None,
            "neighborhood": None,
            "specs": {"target_industries": "healthcare"},
        }
        pick2, skip2 = build_pick_skip_reasons(client, prop_mismatch)
        self.assertIn("Facility type does not match robot target industries", skip2)
        self.assertNotIn("Area mismatch", skip2)

    def test_ranking_uses_probability_only_when_ev_is_none(self):
        """Ranking uses probability only when EV is None, and priced rows rank by EV."""
        item_priced_high_ev = {"id": "1", "ev": 200000.0, "prob": 0.50}
        item_priced_low_ev = {"id": "2", "ev": 50000.0, "prob": 0.80}
        item_unpriced_match = {"id": "3", "ev": None, "prob": 0.6667}
        item_unpriced_mismatch = {"id": "4", "ev": None, "prob": 0.1667}

        items = [item_unpriced_mismatch, item_priced_low_ev, item_unpriced_match, item_priced_high_ev]
        sorted_items = sorted(items, key=lambda x: ev_rank_key(x["prob"], x["ev"]), reverse=True)

        # Priced items sort by EV first
        self.assertEqual(sorted_items[0]["id"], "1")
        self.assertEqual(sorted_items[1]["id"], "2")
        # Unpriced items sort by probability
        self.assertEqual(sorted_items[2]["id"], "3")  # 0.6667
        self.assertEqual(sorted_items[3]["id"], "4")  # 0.1667


class TestPortalNoInternals(unittest.TestCase):
    def test_portal_matches_contain_no_internals(self):
        """No portal dashboard match response contains neighborhood, specs, fit, tier, or expected_value."""
        from fastapi.testclient import TestClient
        import main
        import portal_auth
        from portal_auth import PortalSession

        mock_session = PortalSession(
            session_id="test-session-uuid",
            client_id="test-client-uuid",
            contact_id="test-contact-uuid",
            contact_name="Lead Tester",
            portal_role="evaluator",
            client_name="Test Robotics Logistics",
            is_legacy=False,
        )

        main.app.dependency_overrides[portal_auth.get_current_portal_session] = lambda: mock_session

        mock_evals = [{
            "property_id": "prop-1",
            "probability": 0.6667,
            "expected_value": None,
            "properties": {
                "id": "prop-1",
                "address": "AMR-4000 Heavy Unit",
                "property_value": None,
                "neighborhood": None,
                "image_url": "https://example.com/robot.jpg",
                "property_type": "AMR",
            },
        }]

        try:
            with patch("main.require_company_access", return_value=None), \
                 patch("main.supabase") as mock_sb:

                mock_client_query = MagicMock()
                mock_client_query.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                    data={"id": "test-client-uuid", "name": "Test Robotics Logistics"}
                )
                mock_evals_query = MagicMock()
                mock_evals_query.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
                    data=mock_evals
                )
                mock_demos_query = MagicMock()
                mock_demos_query.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[]
                )

                def table_side_effect(tbl):
                    if tbl == "clients":
                        return mock_client_query
                    if tbl == "pipeline_evaluations":
                        return mock_evals_query
                    return mock_demos_query

                mock_sb.table.side_effect = table_side_effect

                client = TestClient(main.app)
                res = client.get("/api/portal/test-client-uuid/dashboard")
                self.assertEqual(res.status_code, 200)
                data = res.json()
                matches = data.get("matches", [])
                self.assertTrue(len(matches) > 0)
                for m in matches:
                    self.assertNotIn("neighborhood", m, "Portal match must not leak internal neighborhood key")
                    self.assertNotIn("specs", m, "Portal match must not leak internal specs key")
                    self.assertNotIn("fit", m, "Portal match must not leak internal fit key")
                    self.assertNotIn("tier", m, "Portal match must not leak internal tier key")
                    self.assertNotIn("expected_value", m, "Portal match must not leak expected_value")
                    self.assertNotIn("probability", m, "Portal match must not leak probability")
        finally:
            main.app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
