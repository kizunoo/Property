"""backend/price_utils.py  (reference for PHASE 9A; place unchanged, then call it from the sites listed in the prompt)

One place that decides what "no price yet" means, so no module invents a number.
Rules: a missing/0/negative/NaN/non-numeric price is None. None is never turned into 0 or 1.
"""
from __future__ import annotations

import math
from typing import Any, Optional

PRICE_ON_REQUEST = "Price on request"
NOT_IN_CATALOG = "Not in the catalog"   # same wording reply_context already uses for missing facts

# ADAPT-ME: probability cut-offs used for tiers when expected value is unavailable.
# Copy the share of TIER_1/TIER_2 you get today before choosing; the T2 value comes from the approved plan.
UNPRICED_TIER1_PROB = 0.70
UNPRICED_TIER2_PROB = 0.35


def to_price(value: Any) -> Optional[float]:
    """Return a positive finite price, else None. Never returns 0 for 'missing'."""
    if value is None or isinstance(value, bool):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v) or v <= 0:
        return None
    return v


def has_price(prop: dict | None, col: str = "property_value") -> bool:
    return to_price((prop or {}).get(col)) is not None


def compute_expected_value(probability: Optional[float], price: Any) -> Optional[float]:
    """EV = probability x price. None when either side is unknown (never 0, never imputed)."""
    p = to_price(price)
    if p is None or probability is None:
        return None
    return round(float(probability) * p, 2)


def ev_rank_key(probability: Optional[float], expected_value: Optional[float]) -> tuple:
    """Sort key, HIGHER IS BETTER. Use: sorted(rows, key=lambda r: ev_rank_key(...), reverse=True).
    Priced rows rank by EV (RM). Unpriced rows rank by probability (0-1) and sit below priced rows,
    so RM and probability are never compared with each other and None never reaches a comparison."""
    if expected_value is not None:
        return (1, float(expected_value), float(probability or 0.0))
    return (0, float(probability or 0.0), 0.0)


def tier_without_price(probability: Optional[float]) -> str:
    """Tier when expected value is None. Keep the existing EV-based branch for priced rows."""
    p = float(probability or 0.0)
    if p >= UNPRICED_TIER1_PROB:
        return "TIER_1"
    if p >= UNPRICED_TIER2_PROB:
        return "TIER_2"
    return "TIER_3"


def should_use_ml(prop: dict | None) -> bool:
    """The ML model was trained with a budget/price ratio. With no price, skip it (return None
    from predict_probability) so the deterministic formula decides, instead of feeding a fake ratio."""
    return has_price(prop)


def price_fact_value(price: Any, fmt_myr) -> str:
    """For reply_context fact sheets: formatted RM when known, else the standard missing-fact text.
    fmt_myr is the existing formatter in reply_context (so formatting does not change)."""
    p = to_price(price)
    return fmt_myr(p) if p is not None else NOT_IN_CATALOG
