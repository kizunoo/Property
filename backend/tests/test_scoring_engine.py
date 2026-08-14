"""
tests/test_scoring_engine.py
─────────────────────────────
Unit tests for scoring_engine.score().
Run with: python -m pytest tests/ -v
          (or: python tests/test_scoring_engine.py)

No network calls, no Supabase, no FastAPI.
"""

import sys
import os

# Allow running from repo root without installing the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scoring_engine import score


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_client(**kwargs) -> dict:
    """Build a ClientProfile dict; any field can be overridden or omitted."""
    base = {
        "budget":                2_000_000,
        "preferred_neighborhood": "Mont Kiara",
        "engagement_history":    2,
        "source":                "referral",
    }
    base.update(kwargs)
    return base


def make_property(**kwargs) -> dict:
    base = {
        "neighborhood":   "Mont Kiara",
        "property_value": 1_850_000,
    }
    base.update(kwargs)
    return base


# ─── Probability ──────────────────────────────────────────────────────────────

def test_all_signals_match():
    """Budget 2M vs 1.85M prop (ratio 0.925 -> fin 0.385) + Geo match (0.30) + 2 viewings (0.20) + Base (0.10) → 0.985"""
    result = score(make_client(budget=2_000_000, engagement_history=2),
                   make_property(property_value=1_850_000))
    assert result["probability"] == 0.985, result


def test_only_base():
    """No budget, no geo match, no viewings → 0.10"""
    result = score(
        {"budget": None, "preferred_neighborhood": None, "engagement_history": 0, "source": None},
        make_property(),
    )
    assert result["probability"] == 0.10, result


def test_financial_fit_only():
    """Budget 2M vs 1.85M prop (fin 0.385), geo mismatch, no viewings → 0.10 + 0.385 = 0.485"""
    result = score(
        make_client(preferred_neighborhood="Bangsar", engagement_history=0),
        make_property(neighborhood="Mont Kiara"),
    )
    assert result["probability"] == 0.485, result


def test_geo_fit_only():
    """Budget 500k vs 1.85M prop (ratio 0.270 -> fin 0.0541), geo match (0.30), no viewings → 0.10 + 0.0541 + 0.30 = 0.4541"""
    result = score(
        make_client(budget=500_000, preferred_neighborhood="Mont Kiara", engagement_history=0),
        make_property(property_value=1_850_000),
    )
    assert result["probability"] == 0.4541, result


def test_engagement_capped_at_20():
    """10 viewings capped at +0.20 bonus"""
    result = score(make_client(engagement_history=10), make_property())
    assert result["probability"] == 0.985, result


# ─── Tier ─────────────────────────────────────────────────────────────────────

def test_tier_1():
    """High EV + high probability → TIER_1"""
    result = score(make_client(budget=6_000_000, engagement_history=2),
                   make_property(property_value=5_200_000))
    assert result["tier"] == "TIER_1", result


def test_tier_2():
    """Moderate probability → TIER_2"""
    result = score(
        make_client(preferred_neighborhood="Bangsar", engagement_history=0),
        make_property(neighborhood="Mont Kiara"),
    )
    # probability = 0.50 (no geo match, budget OK) → TIER_2
    assert result["tier"] == "TIER_2", result


def test_tier_3():
    """Low probability → TIER_3"""
    result = score(
        {"budget": None, "preferred_neighborhood": "KLCC", "engagement_history": 0, "source": None},
        make_property(),
    )
    assert result["tier"] == "TIER_3", result


# ─── Expected Value ────────────────────────────────────────────────────────────

def test_expected_value_formula():
    """E(x) = probability × property_value"""
    result = score(
        make_client(preferred_neighborhood="Bangsar", engagement_history=0),
        make_property(property_value=1_850_000),
    )
    # probability = 0.485
    assert result["expected_value"] == round(0.485 * 1_850_000, 2), result


# ─── Confidence ───────────────────────────────────────────────────────────────

def test_confidence_high():
    result = score(make_client(), make_property())
    assert result["confidence"] == "HIGH", result


def test_confidence_medium_missing_engagement():
    result = score(make_client(engagement_history=None), make_property())
    assert result["confidence"] == "MEDIUM", result


def test_confidence_low_missing_budget():
    result = score(make_client(budget=None), make_property())
    assert result["confidence"] == "LOW", result


def test_confidence_low_budget_zero_treated_as_present():
    """Budget of 0 is a valid (if unlikely) value — should not be treated as missing."""
    result = score(make_client(budget=0), make_property())
    # Budget present (0 is not None), engagement present → HIGH
    assert result["confidence"] == "HIGH", result


# ─── Run standalone ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  OK   {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL {fn.__name__} -- {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
