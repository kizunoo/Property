"""backend/fit_signal.py  (reference for PHASE 9B-3; place unchanged and call from scoring_engine)

Industry-fit signal for real robots, replacing the geo component when a robot has target_industries.
Never guesses: unknown facility type or unknown robot industries -> None (component excluded, weights renormalized).
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Optional

FIT_WEIGHT = 0.30  # takes the slot geo had; ADAPT-ME if scoring_engine's geo weight is different

# ADAPT-ME: company facility_type (normalized) -> robot target_industries tokens that count as a match.
# Add synonyms only when a real company uses them. Unlisted facility types give NO signal (None).
FACILITY_TO_INDUSTRIES: dict[str, set[str]] = {
    "warehouse": {"warehousing", "logistics"},
    "logistics": {"logistics", "warehousing"},
    "distribution centre": {"logistics", "warehousing"},
    "distribution center": {"logistics", "warehousing"},
    "manufacturing": {"manufacturing"},
    "factory": {"manufacturing"},
    "healthcare": {"healthcare"},
    "hospital": {"healthcare"},
    "hospitality": {"hospitality"},
    "hotel": {"hospitality"},
    "office": {"office"},
    "education": {"education"},
}


def _norm(s: Any) -> str:
    return " ".join(str(s or "").lower().replace("_", " ").replace("-", " ").split())


def _as_dict(v: Any) -> dict:
    if isinstance(v, dict):
        return v
    if isinstance(v, str) and v.strip():
        try:
            d = json.loads(v)
            return d if isinstance(d, dict) else {}
        except ValueError:
            return {}
    return {}


def parse_industries(raw: Any) -> set[str]:
    """'logistics;warehousing' / 'a, b' / ['a','b'] -> {'logistics','warehousing'}"""
    if raw is None:
        return set()
    if isinstance(raw, str):
        parts: Iterable[str] = raw.replace(",", ";").split(";")
    elif isinstance(raw, (list, tuple, set)):
        parts = [str(x) for x in raw]
    else:
        return set()
    return {_norm(p) for p in parts if _norm(p)}


def client_facility_type(client: dict | None) -> Optional[str]:
    """facility_profile.facility_type first (that is where the portal and importer store it),
    then the plain clients.facility_type column."""
    c = client or {}
    ft = _as_dict(c.get("facility_profile")).get("facility_type") or c.get("facility_type")
    ft = _norm(ft)
    return ft or None


def robot_target_industries(prop: dict | None) -> set[str]:
    return parse_industries(_as_dict((prop or {}).get("specs")).get("target_industries"))


def industry_fit(facility_type: Any, target_industries: Any) -> Optional[float]:
    """1.0 match, 0.0 no match, None when it cannot be judged (never guesses)."""
    ft = _norm(facility_type)
    inds = parse_industries(target_industries)
    if not ft or not inds:
        return None
    wanted = FACILITY_TO_INDUSTRIES.get(ft)
    if wanted is None:
        return None
    return 1.0 if wanted & inds else 0.0


def fit_reason(fit: Optional[float]) -> str:
    if fit is None:
        return "Facility type or robot industries unknown"
    return ("Facility type matches robot target industries" if fit >= 1.0
            else "Facility type does not match robot target industries")


def renormalize(points: float, available_weight: float) -> float:
    """points = sum of earned component points; available_weight = sum of the weights of components
    that could be evaluated (price and/or fit/geo left out when unknown). Result is capped at 1.0."""
    if available_weight <= 0:
        return 0.0
    return round(min(1.0, max(0.0, points / available_weight)), 4)
