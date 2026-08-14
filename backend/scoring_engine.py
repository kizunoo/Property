"""
scoring_engine.py
─────────────────
Pure calculation module for PIPELINE.EV.

No imports from FastAPI, Supabase, or any network library.
All functions are deterministic and testable with plain dicts.

Inputs use the canonical ClientProfile shape:
    {
        "budget":               float | None,   # stated budget in RM
        "preferred_neighborhood": str | None,   # e.g. "Mont Kiara"
        "engagement_history":   int | None,     # number of past viewings
        "source":               str | None,     # lead source, e.g. "referral"
    }

Property dict shape:
    {
        "neighborhood":    str,
        "property_value":  float,
    }
"""

from __future__ import annotations

from typing import TypedDict


# ─── Output type ──────────────────────────────────────────────────────────────

class ScoringResult(TypedDict):
    probability:    float   # 0.0–1.0
    tier:           str     # "TIER_1" | "TIER_2" | "TIER_3"
    expected_value: float   # probability × property_value (RM)
    confidence:     str     # "HIGH" | "MEDIUM" | "LOW"


# ─── Confidence ───────────────────────────────────────────────────────────────

def _confidence(client: dict) -> str:
    """
    Assess data completeness of the client profile.

    HIGH   — budget, preferred_neighborhood, and engagement_history all present
    MEDIUM — budget present but engagement_history missing (or vice-versa)
    LOW    — budget missing (cannot assess financial fit at all)
    """
    has_budget      = client.get("budget") is not None
    has_engagement  = client.get("engagement_history") is not None
    has_neighborhood = bool(client.get("preferred_neighborhood"))

    if has_budget and has_engagement and has_neighborhood:
        return "HIGH"
    if not has_budget:
        return "LOW"
    return "MEDIUM"


# ─── Probability ──────────────────────────────────────────────────────────────

def _probability(client: dict, prop: dict) -> float:
    """
    Calculate P(Buy) for a client–property pair.

    Scoring breakdown (matches frontend ScoreBar display):
        Base probability          +10%  (always)
        Financial Fit             +40% max (scaled continuously by property value / budget match)
        Geo Match                 +30%  (preferred_neighborhood == neighborhood)
        Engagement Bonus          +10% per viewing, capped at +20%
    """
    prob = 0.10

    budget = client.get("budget")
    prop_value = prop.get("property_value", 0)
    if budget is not None and budget > 0 and prop_value > 0:
        if budget >= prop_value:
            # Full +40% when budget matches property value; scales smoothly (0.5 to 1.0) for lower-priced listings
            ratio = prop_value / budget
            prob += 0.40 * (0.5 + 0.5 * min(1.0, ratio))
        else:
            # Partial financial fit when listing exceeds budget
            ratio = budget / prop_value
            prob += 0.40 * (0.5 * max(0.0, ratio))

    pref_nbhd = client.get("preferred_neighborhood")
    if pref_nbhd and pref_nbhd == prop.get("neighborhood"):
        prob += 0.30

    viewings = client.get("engagement_history") or 0
    prob += min(viewings * 0.10, 0.20)

    return round(min(prob, 1.0), 4)


# ─── Tier assignment ──────────────────────────────────────────────────────────

def _tier(probability: float, expected_value: float) -> str:
    """
    Classify client–property pair into a segment tier.

    TIER_1  — High-value VIP: E(x) > RM 50,000 AND P(Buy) ≥ 65%
    TIER_2  — Warm lead:      P(Buy) ≥ 35%
    TIER_3  — Cold / monitor: everything else
    """
    if expected_value > 50_000 and probability >= 0.65:
        return "TIER_1"
    if probability >= 0.35:
        return "TIER_2"
    return "TIER_3"


# ─── Public API ───────────────────────────────────────────────────────────────

def score(client: dict, prop: dict) -> ScoringResult:
    """
    Score a single client–property pair.

    Parameters
    ----------
    client : dict
        Keys: budget, preferred_neighborhood, engagement_history, source
        (all optional — missing fields degrade confidence, not correctness)

    prop : dict
        Keys: neighborhood, property_value

    Returns
    -------
    ScoringResult
        probability, tier, expected_value, confidence
    """
    probability    = _probability(client, prop)
    expected_value = round(probability * prop.get("property_value", 0), 2)
    tier           = _tier(probability, expected_value)
    confidence     = _confidence(client)

    return ScoringResult(
        probability=probability,
        tier=tier,
        expected_value=expected_value,
        confidence=confidence,
    )
