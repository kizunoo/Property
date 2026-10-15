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

from scoring_engine import score, build_pick_skip_reasons


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


def test_client_with_null_budget():
    """Client with NULL budget: no crash, non-zero EV, confidence LOW, and pick/skip tags show 'Budget not set'."""
    client = make_client(budget=None, engagement_history=1)
    prop = make_property(property_value=1_500_000)

    result = score(client, prop)
    assert result["confidence"] == "LOW", result
    assert result["probability"] > 0, "Probability must be non-zero for positive signals"
    assert result["expected_value"] > 0, "Expected value must not be zero when unit price > 0"
    assert result["expected_value"] == round(result["probability"] * 1_500_000, 2)

    pick_reason, skip_reason = build_pick_skip_reasons(client, prop)
    assert "Budget not set" in skip_reason
    assert "100% below asking" not in skip_reason


def test_ml_inference_null_budget():
    """ml_inference.predict_probability must handle NULL budget without crashing."""
    from ml_inference import predict_probability
    client = {"budget": None, "preferred_neighborhood": "Manufacturing", "engagement_history": 1}
    prop = {"property_value": 750_000, "neighborhood": "Manufacturing"}
    prob = predict_probability(client, prop)
    if prob is not None:
        assert isinstance(prob, float)
        assert prob > 0


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
