"""
Feature extraction for the ML probability model.
Mirrors the inputs used in scoring_engine.py, so the trained model
learns from the same signals (financial fit, geo match, engagement,
and verified past property purchase track record).
"""

def extract_features(client: dict, prop: dict) -> dict:
    budget = client.get("budget")
    prop_value = prop.get("property_value") or 1  # avoid div by zero
    preferred_neighborhood = client.get("preferred_neighborhood")
    neighborhood = prop.get("neighborhood")
    engagement_history = client.get("engagement_history") or 0
    past_purchases = client.get("past_purchases") or []

    budget_to_price_ratio = (budget / prop_value) if (budget is not None and prop_value) else 0.0
    geo_match = 1 if preferred_neighborhood and preferred_neighborhood == neighborhood else 0
    engagement_capped = min(engagement_history, 2)  # matches the formula's cap at 2 viewings
    has_prior_purchase = 1.0 if len(past_purchases) > 0 else 0.0
    repeat_neighborhood = 1.0 if (neighborhood and any(p.get("neighborhood") == neighborhood for p in past_purchases)) else 0.0

    return {
        "budget_to_price_ratio": budget_to_price_ratio,
        "geo_match": geo_match,
        "engagement_capped": engagement_capped,
        "property_value": prop_value,
        "has_prior_purchase": has_prior_purchase,
        "repeat_neighborhood": repeat_neighborhood,
    }


def features_to_vector(features: dict) -> list:
    """Fixed feature order — must match exactly between training and inference."""
    return [
        features["budget_to_price_ratio"],
        features["geo_match"],
        features["engagement_capped"],
        features["property_value"],
        features.get("has_prior_purchase", 0.0),
        features.get("repeat_neighborhood", 0.0),
    ]


FEATURE_NAMES = [
    "budget_to_price_ratio",
    "geo_match",
    "engagement_capped",
    "property_value",
    "has_prior_purchase",
    "repeat_neighborhood",
]
