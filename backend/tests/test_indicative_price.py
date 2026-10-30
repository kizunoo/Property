import os
import sys
import unittest
from pathlib import Path

# Ensure root and backend are on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from validate_robots_catalog import check_indicative
from import_real_data import map_indicative, to_positive_num
from price_utils import compute_expected_value
from scoring_engine import score
from reply_context import product_sheet


class TestIndicativePrice(unittest.TestCase):
    def test_check_indicative_valid(self):
        errors, warnings = check_indicative({
            "indicative_price_myr": "79000",
            "indicative_price_note": "RobotLAB list, Oct 2026",
        })
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_check_indicative_missing_note(self):
        errors, warnings = check_indicative({
            "indicative_price_myr": "79000",
        })
        self.assertTrue(any("indicative_price_note is required" in e for e in errors))

    def test_check_indicative_zero(self):
        errors, warnings = check_indicative({
            "indicative_price_myr": "0",
            "indicative_price_note": "Some note",
        })
        self.assertTrue(any("must be a positive number" in e for e in errors))

    def test_check_indicative_negative(self):
        errors, warnings = check_indicative({
            "indicative_price_myr": "-1500",
            "indicative_price_note": "Some note",
        })
        self.assertTrue(any("must be a positive number" in e for e in errors))

    def test_check_indicative_text(self):
        errors, warnings = check_indicative({
            "indicative_price_myr": "invalid_amount",
            "indicative_price_note": "Some note",
        })
        self.assertTrue(any("must be a positive number" in e for e in errors))

    def test_check_indicative_nan(self):
        errors, warnings = check_indicative({
            "indicative_price_myr": "nan",
            "indicative_price_note": "Some note",
        })
        self.assertTrue(any("must be a positive number" in e for e in errors))

    def test_check_indicative_real_price_set_warning(self):
        errors, warnings = check_indicative({
            "price": "60000",
            "indicative_price_myr": "50000",
            "indicative_price_note": "Reseller quote",
        })
        self.assertEqual(errors, [])
        self.assertTrue(any("price is set, so the indicative price will be hidden" in w for w in warnings))

    def test_check_indicative_empty(self):
        errors, warnings = check_indicative({})
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_check_indicative_note_without_price(self):
        errors, warnings = check_indicative({
            "indicative_price_note": "Reseller quote with no price",
        })
        self.assertEqual(errors, [])
        self.assertTrue(any("without indicative_price_myr is ignored" in w for w in warnings))

    def test_importer_mapping(self):
        # Empty inputs map to None
        res_empty = map_indicative({"indicative_price_myr": "", "indicative_price_note": ""}, to_positive_num)
        self.assertEqual(res_empty, {"indicative_price_myr": None, "indicative_price_note": None})

        # Valid input maps correctly
        res_valid = map_indicative({
            "indicative_price_myr": "79,000.00",
            "indicative_price_note": "  RobotLAB quote  ",
        }, to_positive_num)
        self.assertEqual(res_valid, {"indicative_price_myr": 79000.0, "indicative_price_note": "RobotLAB quote"})

        # Invalid numeric inputs map to None
        for bad in ["0", "-100", "abc", "nan", "inf"]:
            res_bad = map_indicative({"indicative_price_myr": bad}, to_positive_num)
            self.assertIsNone(res_bad["indicative_price_myr"], f"Failed for {bad}")

    def test_scoring_and_ev_do_not_read_indicative_price(self):
        # compute_expected_value never computes an EV from indicative values
        self.assertIsNone(compute_expected_value(0.85, None))

        # score_pair with property having property_value=None but indicative_price_myr set
        client_profile = {
            "budget": None,
            "preferred_neighborhood": "Manufacturing",
            "engagement_history": 2,
            "source": "outbound",
        }
        prop_with_indicative = {
            "property_value": None,
            "indicative_price_myr": 85000,
            "indicative_price_note": "Oct 2026 benchmark",
            "neighborhood": "Manufacturing",
            "property_type": "AMR",
            "specs": {},
        }
        scored = score(client_profile, prop_with_indicative)
        self.assertIsNone(scored["expected_value"], "Expected value must be None when property_value is None")
        # Ensure tier did not trigger the >50,000 EV rule
        self.assertIn(scored["tier"], ["TIER_1", "TIER_2", "TIER_3"])

    def test_ai_fact_sheets_do_not_read_indicative_price(self):
        prop_row = {
            "address": "Ottonomy Ottobot",
            "property_value": None,
            "indicative_price_myr": 85000,
            "indicative_price_note": "Oct 2026 benchmark",
            "manufacturer": "Ottonomy",
            "specs": {"payload_kg": 50},
        }
        sheet = product_sheet(prop_row, why="Recommended for warehouse")
        facts = sheet.get("facts", [])

        # Confirm unit cost fact is NOT in the catalog and does NOT leak 85000
        cost_facts = [f for f in facts if f.get("label") == "Unit cost (RM)"]
        self.assertEqual(len(cost_facts), 1)
        self.assertEqual(cost_facts[0]["value"], "Not in the catalog")

        for f in facts:
            label = str(f.get("label", ""))
            val = str(f.get("value", ""))
            self.assertNotIn("indicative", label.lower())
            self.assertNotIn("85000", val)
            self.assertNotIn("85,000", val)


if __name__ == "__main__":
    unittest.main()
