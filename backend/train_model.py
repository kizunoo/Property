"""
Trains a logistic regression model on real + synthetic outcomes.
Run manually via `python backend/train_model.py`, or triggered via the
/api/retrain_model endpoint in main.py.

IMPORTANT: real outcomes are weighted much more heavily than synthetic ones
(sample_weight), so as real Won/Lost data accumulates, the model progressively
learns more from actual results and less from the synthetic bootstrap —
this is deliberate and must not be changed to weight them equally.
"""
import os
import json
import random
from datetime import datetime, timezone
import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, roc_auc_score
from dotenv import load_dotenv
from supabase import create_client

from ml_features import extract_features, features_to_vector

load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

REAL_SAMPLE_WEIGHT = 5.0    # real outcomes count 5x as much as synthetic in training
SYNTHETIC_SAMPLE_WEIGHT = 1.0
MODEL_PATH = os.path.join(os.path.dirname(__file__), "ml_model.pkl")


def fetch_real_outcomes():
    """Fetch every evaluation with a real recorded outcome (won/lost), joining past purchases if available."""
    # Try fetching past purchases to attach to clients
    past_purchases_by_client: dict[str, list[dict]] = {}
    try:
        purch_res = supabase.table("client_past_purchases").select("*").execute()
        if purch_res.data:
            for p in purch_res.data:
                cid = p.get("client_id")
                if cid:
                    past_purchases_by_client.setdefault(cid, []).append(p)
    except Exception:
        pass

    try:
        rows = supabase.table("pipeline_evaluations") \
            .select("*, clients(id, stated_budget, preferred_neighborhood, past_viewings), properties(property_value, neighborhood)") \
            .neq("outcome", "pending") \
            .execute().data or []
    except Exception as exc:
        try:
            rows = supabase.table("pipeline_evaluations") \
                .select("*, clients!pipeline_evaluations_client_id_fkey(id, stated_budget, preferred_neighborhood, past_viewings), properties!pipeline_evaluations_property_id_fkey(property_value, neighborhood)") \
                .neq("outcome", "pending") \
                .execute().data or []
        except Exception as exc2:
            print(f"Warning fetching real outcomes: {exc} (fallback error: {exc2})")
            rows = []

    X, y, weights = [], [], []
    for row in rows:
        client_data = row.get("clients") or {}
        prop_data = row.get("properties") or {}
        cid = client_data.get("id") or row.get("client_id")
        client = {
            "budget": client_data.get("stated_budget") if client_data.get("stated_budget") is not None else client_data.get("budget", 0),
            "preferred_neighborhood": client_data.get("preferred_neighborhood"),
            "engagement_history": client_data.get("past_viewings", 0),
            "past_purchases": past_purchases_by_client.get(cid, []),
        }
        prop = {
            "property_value": prop_data.get("property_value", 1),
            "neighborhood": prop_data.get("neighborhood"),
        }
        features = extract_features(client, prop)
        X.append(features_to_vector(features))
        y.append(1 if row.get("outcome") == "won" else 0)
        weights.append(REAL_SAMPLE_WEIGHT)

    return X, y, weights, len(rows)


def generate_synthetic_outcomes(n=300):
    """
    Generates a synthetic training set by sampling realistic client/property
    combinations and simulating an outcome probabilistically based on the
    formula's logic, including proven purchase track record, plus noise.
    """
    neighborhoods = ["Bangsar", "Damansara Heights", "KLCC", "Mont Kiara",
                      "Desa ParkCity", "Taman Desa", "Taman Tun Dr Ismail", "Bandar Sri Damansara"]

    X, y, weights = [], [], []
    for _ in range(n):
        budget = random.uniform(500_000, 12_000_000)
        prop_value = random.uniform(400_000, 9_000_000)
        pref_neighborhood = random.choice(neighborhoods)
        prop_neighborhood = random.choice(neighborhoods)
        viewings = random.choice([0, 0, 1, 1, 2, 2, 3])

        # ~35% of synthetic clients have prior purchase history
        has_prior = random.random() < 0.35
        past_purchases = []
        if has_prior:
            past_nbhd = prop_neighborhood if random.random() < 0.5 else random.choice(neighborhoods)
            past_purchases.append({
                "property_name": "Prior Property",
                "neighborhood": past_nbhd,
                "purchase_price": budget * random.uniform(0.7, 1.1),
            })

        client = {
            "budget": budget,
            "preferred_neighborhood": pref_neighborhood,
            "engagement_history": viewings,
            "past_purchases": past_purchases,
        }
        prop = {"property_value": prop_value, "neighborhood": prop_neighborhood}
        features = extract_features(client, prop)

        ratio = features["budget_to_price_ratio"]
        financial_component = min(0.4, 0.4 * (0.5 + 0.5 * min(1.0, ratio))) if ratio >= 1 else 0.4 * 0.5 * max(0, ratio)
        geo_component = 0.3 if features["geo_match"] else 0
        engagement_component = min(features["engagement_capped"] * 0.1, 0.2)
        track_record_component = 0.05 if features["has_prior_purchase"] else 0
        repeat_area_component = 0.05 if features["repeat_neighborhood"] else 0

        simulated_prob = min(1.0, 0.1 + financial_component + geo_component + engagement_component + track_record_component + repeat_area_component)

        noisy_prob = min(1.0, max(0.0, simulated_prob + random.gauss(0, 0.08)))
        outcome = 1 if random.random() < noisy_prob else 0

        X.append(features_to_vector(features))
        y.append(outcome)
        weights.append(SYNTHETIC_SAMPLE_WEIGHT)

    return X, y, weights


def train():
    real_X, real_y, real_w, real_count = fetch_real_outcomes()
    synth_X, synth_y, synth_w = generate_synthetic_outcomes(n=300)

    X = np.array(real_X + synth_X)
    y = np.array(real_y + synth_y)
    weights = np.array(real_w + synth_w)

    X_train, X_test, y_train, y_test, w_train, w_test = train_test_split(
        X, y, weights, test_size=0.2, random_state=42
    )

    model = LogisticRegression(max_iter=1000)
    model.fit(X_train, y_train, sample_weight=w_train)

    train_acc = float(accuracy_score(y_train, model.predict(X_train)))
    test_acc = float(accuracy_score(y_test, model.predict(X_test)))
    try:
        test_auc = float(roc_auc_score(y_test, model.predict_proba(X_test)[:, 1]))
    except ValueError:
        test_auc = None  # can happen if test set has only one class

    joblib.dump(model, MODEL_PATH)

    insert_payload = {
        "real_outcome_count": real_count,
        "synthetic_outcome_count": len(synth_X),
        "train_accuracy": round(train_acc, 4),
        "test_accuracy": round(test_acc, 4),
        "test_auc": round(test_auc, 4) if test_auc is not None else None,
        "notes": f"Real outcomes weighted {REAL_SAMPLE_WEIGHT}x synthetic",
    }
    try:
        supabase.table("model_training_runs").insert(insert_payload).execute()
    except Exception as exc:
        print(f"Warning: could not insert into model_training_runs: {exc}")

    # Also persist locally so API can serve stats even if Supabase table is not yet migrated
    status_file = os.path.join(os.path.dirname(__file__), "latest_training_run.json")
    try:
        local_payload = {
            "trained": True,
            "trained_at": datetime.now(timezone.utc).isoformat(),
            **insert_payload,
        }
        with open(status_file, "w") as f:
            json.dump(local_payload, f, indent=2)
    except Exception as exc:
        print(f"Warning saving local training run record: {exc}")

    print(f"Trained on {real_count} real + {len(synth_X)} synthetic outcomes")
    print(f"Train accuracy: {train_acc:.3f} | Test accuracy: {test_acc:.3f} | Test AUC: {test_auc}")
    return {
        "real_outcome_count": real_count,
        "synthetic_outcome_count": len(synth_X),
        "train_accuracy": train_acc,
        "test_accuracy": test_acc,
        "test_auc": test_auc,
    }


if __name__ == "__main__":
    train()
