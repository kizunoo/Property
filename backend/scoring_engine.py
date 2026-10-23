"""
scoring_engine.py
─────────────────
Pure calculation module for PIPELINE.EV.

No imports from FastAPI, Supabase, or any network library.
All functions are deterministic and testable with plain dicts.

Inputs use the canonical ClientProfile shape:
    {
        "budget":                   float | None,   # stated budget in RM
        "preferred_neighborhood":   str | None,     # e.g. "Mont Kiara"
        "engagement_history":       int | None,     # number of past viewings
        "source":                   str | None,     # lead source, e.g. "referral"
        # Rich profile fields (additive bonuses — all optional):
        "financing_status":         str | None,     # "cash"|"pre-approved"|"in-progress"|"unspecified"
        "move_in_timeline":         str | None,     # "< 3 months"|"3-6 months"|"6-12 months"|"flexible"
        "property_type_preference": str | None,     # "condo"|"terrace"|"semi-d"|"bungalow"|"serviced_apt"|"any"
        "secondary_neighborhood":   str | None,     # secondary preferred area
        # Past acquisition history (optional track record):
        "past_purchases":           list[dict] | None, # [{"property_name": str, "neighborhood": str, "purchase_price": float, ...}]
    }

Property dict shape:
    {
        "neighborhood":   str,
        "property_value": float,
        # Rich profile fields (optional):
        "property_type":  str | None,   # "condo"|"terrace"|"semi-d"|"bungalow"|"serviced_apt"
    }
"""

from __future__ import annotations

from typing import TypedDict


from price_utils import compute_expected_value, has_price, tier_without_price, to_price


# ─── Output type ──────────────────────────────────────────────────────────────

class ScoringResult(TypedDict):
    probability:    float          # 0.0–1.0
    tier:           str            # "TIER_1" | "TIER_2" | "TIER_3"
    expected_value: float | None   # probability × property_value (RM) or None if unpriced
    confidence:     str            # "HIGH" | "MEDIUM" | "LOW"


# ─── Score component breakdown ────────────────────────────────────────────────

class ScoreBreakdown(TypedDict):
    base:           float   # always 0.10
    financial:      float   # 0.0 – 0.40
    geo_primary:    float   # 0.0 or 0.30
    engagement:     float   # 0.0 – 0.20
    financing:      float   # 0.0 or 0.05 (rich profile bonus)
    timeline:       float   # 0.0 or 0.05 (rich profile bonus)
    type_match:     float   # 0.0 or 0.05 (rich profile bonus)
    geo_secondary:  float   # 0.0 or 0.10 (rich profile bonus)
    track_record:   float   # 0.0 or 0.05 (proven buyer track record)
    repeat_area:    float   # 0.0 or 0.05 (repeat neighborhood owner)


# ─── Confidence ───────────────────────────────────────────────────────────────

def _confidence(client: dict) -> str:
    """
    Assess data completeness of the client profile.

    HIGH   — budget, preferred_neighborhood, and engagement_history all present
             OR buyer has verified past purchase history with stated budget
    MEDIUM — budget present but engagement_history missing (or vice-versa)
    LOW    — budget missing (cannot assess financial fit at all)
    """
    has_budget       = client.get("budget") is not None
    has_engagement   = client.get("engagement_history") is not None
    has_neighborhood = bool(client.get("preferred_neighborhood"))
    has_purchases    = bool(client.get("past_purchases"))

    if has_budget and (has_purchases or (has_engagement and has_neighborhood)):
        return "HIGH"
    if not has_budget:
        return "LOW"
    return "MEDIUM"


# ─── Score breakdown ──────────────────────────────────────────────────────────

def _score_breakdown(client: dict, prop: dict) -> ScoreBreakdown:
    """
    Compute each component of the probability score separately.
    All rich-profile bonuses are additive and optional (default 0.0).
    """
    # ── Core signals ─────────────────────────────────────────────────────────

    # Base: always +10%
    base = 0.10

    # Financial Fit: up to +40%
    budget     = client.get("budget")
    prop_value = to_price(prop.get("property_value"))
    financial  = 0.0
    if budget is not None and budget > 0 and prop_value is not None:
        if budget >= prop_value:
            ratio = prop_value / budget
            financial = 0.40 * (0.5 + 0.5 * min(1.0, ratio))
        else:
            ratio = budget / prop_value
            financial = 0.40 * (0.5 * max(0.0, ratio))

    # Geo match (primary): +30% exact match
    pref_nbhd   = client.get("preferred_neighborhood")
    prop_nbhd   = prop.get("neighborhood")
    geo_primary = 0.30 if (pref_nbhd and pref_nbhd == prop_nbhd) else 0.0

    # Engagement: +10% per viewing, capped at +20%
    viewings   = client.get("engagement_history") or 0
    engagement = min(viewings * 0.10, 0.20)

    # ── Rich-profile bonuses (all additive, all optional) ────────────────────

    # Financing bonus: +5% if cash or pre-approved
    fin_status = client.get("financing_status")
    financing  = 0.05 if fin_status in ("cash", "pre-approved") else 0.0

    # Timeline urgency bonus: +5% if moving within 6 months
    timeline_val = client.get("move_in_timeline")
    timeline     = 0.05 if timeline_val in ("< 3 months", "3-6 months") else 0.0

    # Property type match bonus: +5% if preference matches listing
    type_pref  = client.get("property_type_preference")
    prop_type  = prop.get("property_type")
    type_match = (
        0.05
        if (type_pref and prop_type and type_pref not in ("any",) and type_pref == prop_type)
        else 0.0
    )

    # Secondary geo bonus: +10% if secondary_neighborhood matches (only if primary did not fire)
    sec_nbhd      = client.get("secondary_neighborhood")
    geo_secondary = (
        0.10
        if (sec_nbhd and prop_nbhd and sec_nbhd == prop_nbhd and geo_primary == 0.0)
        else 0.0
    )

    # ── Past acquisition track record bonuses ────────────────────────────────

    past_purchases = client.get("past_purchases") or []
    # Track record bonus: +5% if client has at least 1 verified prior purchase
    track_record = 0.05 if len(past_purchases) > 0 else 0.0

    # Repeat area affinity bonus: +5% if any prior purchase was in the property's neighborhood
    repeat_area = (
        0.05
        if (prop_nbhd and any(p.get("neighborhood") == prop_nbhd for p in past_purchases))
        else 0.0
    )

    return ScoreBreakdown(
        base=base,
        financial=financial,
        geo_primary=geo_primary,
        engagement=engagement,
        financing=financing,
        timeline=timeline,
        type_match=type_match,
        geo_secondary=geo_secondary,
        track_record=track_record,
        repeat_area=repeat_area,
    )


# ─── Probability ──────────────────────────────────────────────────────────────

def _probability(client: dict, prop: dict) -> float:
    """
    Calculate P(Buy) for a client–property pair.

    Scoring breakdown:
        Base probability          +10%  (always)
        Financial Fit             +40% max (scaled continuously by budget/price ratio)
        Geo Match (primary)       +30%  (preferred_neighborhood == neighborhood)
        Engagement Bonus          +10% per viewing, capped at +20%
        Financing bonus           +5%   (cash or pre-approved — rich profile)
        Timeline urgency          +5%   (< 6 month move-in — rich profile)
        Type match                +5%   (property_type preference matches — rich profile)
        Geo secondary             +10%  (secondary_neighborhood matches — rich profile)
        Proven Buyer Track Record +5%   (has >= 1 verified past purchase)
        Repeat Area Owner         +5%   (previously bought in target neighborhood)
    """
    bd = _score_breakdown(client, prop)
    if not has_price(prop):
        # When price is None, the financial component is excluded and the
        # remaining non-financial weights (summing to 0.60 core) are renormalized
        # so a missing price neither helps nor hurts.
        non_financial = (
            bd["base"]
            + bd["geo_primary"]
            + bd["engagement"]
            + bd["financing"]
            + bd["timeline"]
            + bd["type_match"]
            + bd["geo_secondary"]
            + bd["track_record"]
            + bd["repeat_area"]
        )
        return round(min(non_financial / 0.60, 1.0), 4)

    total = (
        bd["base"]
        + bd["financial"]
        + bd["geo_primary"]
        + bd["engagement"]
        + bd["financing"]
        + bd["timeline"]
        + bd["type_match"]
        + bd["geo_secondary"]
        + bd["track_record"]
        + bd["repeat_area"]
    )
    return round(min(total, 1.0), 4)


# ─── Tier assignment ──────────────────────────────────────────────────────────

def _tier(probability: float, expected_value: float | None) -> str:
    """
    Classify client–property pair into a segment tier.

    TIER_1  — High-value VIP: E(x) > RM 50,000 AND P(Buy) ≥ 65%
    TIER_2  — Warm lead:      P(Buy) ≥ 35%
    TIER_3  — Cold / monitor: everything else
    """
    if expected_value is not None:
        if expected_value > 50_000 and probability >= 0.65:
            return "TIER_1"
        if probability >= 0.35:
            return "TIER_2"
        return "TIER_3"
    return tier_without_price(probability)


# ─── Pick / Skip reason builder ───────────────────────────────────────────────

def build_pick_skip_reasons(client: dict, prop: dict) -> tuple[str, str]:
    """
    Return (pick_reason, skip_reason) as human-readable tag strings.
    Both are always computed; callers decide which to show based on tier.

    pick_reason  — positive signals (shown for TIER_1 / TIER_2)
    skip_reason  — negative signals (shown for TIER_3)
    """
    bd             = _score_breakdown(client, prop)
    raw_budget     = client.get("budget")
    prop_v         = to_price(prop.get("property_value"))
    viewings       = client.get("engagement_history") or 0
    past_purchases = client.get("past_purchases") or []

    pick_tags: list[str] = []
    skip_tags: list[str] = []

    # Financial fit (must not compare against any price when unpriced)
    if prop_v is not None:
        if raw_budget is None:
            skip_tags.append("Budget not set")
        elif raw_budget >= prop_v:
            pick_tags.append("✓ Budget covers asking")
        elif raw_budget > 0 and (raw_budget / prop_v) >= 0.8:
            pick_tags.append("✓ Budget near asking")
        else:
            ratio_pct = int((raw_budget / prop_v) * 100) if prop_v > 0 else 0
            skip_tags.append(f"✗ Budget {100 - ratio_pct}% below asking")

    # Past acquisition track record
    if len(past_purchases) > 0:
        max_past_price = max((float(p.get("purchase_price") or 0) for p in past_purchases), default=0)
        if max_past_price >= 1_000_000:
            price_str = f"RM {max_past_price / 1_000_000:.1f}M"
        else:
            price_str = f"RM {max_past_price:,.0f}"

        if bd["repeat_area"] > 0:
            prop_nbhd = prop.get("neighborhood", "")
            pick_tags.append(f"✓ Repeat {prop_nbhd} owner ({price_str})")
        else:
            pick_tags.append(f"✓ Proven buyer ({price_str} track record)")

    # Primary geo
    pref = client.get("preferred_neighborhood", "")
    if bd["geo_primary"] > 0:
        pick_tags.append(f"✓ Area match ({pref})")
    else:
        skip_tags.append("✗ Area mismatch")

    # Secondary geo bonus
    if bd["geo_secondary"] > 0:
        skip_tags.clear()  # secondary match overrides the area-mismatch tag
        pick_tags.append(f"✓ Secondary area match")

    # Engagement
    if viewings >= 2:
        pick_tags.append(f"✓ {viewings} viewings")
    elif viewings == 1:
        pick_tags.append("✓ 1 viewing")
    else:
        skip_tags.append("✗ No viewings yet")

    # Rich-profile bonuses
    if bd["financing"] > 0:
        fin = client.get("financing_status", "")
        pick_tags.append(f"✓ {fin.replace('-', ' ').title()}")

    if bd["timeline"] > 0:
        tl = client.get("move_in_timeline", "")
        pick_tags.append(f"✓ Urgent ({tl})")

    if bd["type_match"] > 0:
        pick_tags.append("✓ Property type match")

    pick_reason = " · ".join(pick_tags) if pick_tags else "No strong signals"
    skip_reason = " · ".join(skip_tags) if skip_tags else "Low overall fit"

    return pick_reason, skip_reason


# ─── Public API ───────────────────────────────────────────────────────────────

def score(client: dict, prop: dict) -> ScoringResult:
    """
    Score a single client–property pair.

    Parameters
    ----------
    client : dict
        Keys: budget, preferred_neighborhood, engagement_history, source
              financing_status, move_in_timeline, property_type_preference,
              secondary_neighborhood, past_purchases
        (all optional — missing fields degrade confidence, not correctness)

    prop : dict
        Keys: neighborhood, property_value, property_type

    Returns
    -------
    ScoringResult
        probability, tier, expected_value, confidence
    """
    probability    = _probability(client, prop)
    expected_value = compute_expected_value(probability, prop.get("property_value"))
    tier           = _tier(probability, expected_value)
    confidence     = _confidence(client)

    return ScoringResult(
        probability=probability,
        tier=tier,
        expected_value=expected_value,
        confidence=confidence,
    )
