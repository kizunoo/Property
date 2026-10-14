"""Loads the trained model and produces predictions. Falls back gracefully
if no model has been trained yet."""
import os
import joblib
from ml_features import extract_features, features_to_vector

MODEL_PATH = os.path.join(os.path.dirname(__file__), "ml_model.pkl")
_model = None
_model_loaded_attempted = False


def get_model():
    global _model, _model_loaded_attempted
    if _model is None and not _model_loaded_attempted:
        _model_loaded_attempted = True
        if os.path.exists(MODEL_PATH):
            try:
                _model = joblib.load(MODEL_PATH)
            except Exception as exc:
                print(f"Failed to load model from {MODEL_PATH}: {exc}")
                _model = None
    return _model


def reload_model():
    """Forces reloading the model from disk after a training run."""
    global _model, _model_loaded_attempted
    _model_loaded_attempted = False
    _model = None
    return get_model()


def predict_probability(client: dict, prop: dict) -> float | None:
    model = get_model()
    if model is None:
        return None  # no model trained yet — caller should handle gracefully
    try:
        features = extract_features(client, prop)
        raw_vec = features_to_vector(features)
        # Slicing guard: if loaded model was trained on fewer features (e.g. 4 vs 6), adapt seamlessly
        if hasattr(model, "n_features_in_") and model.n_features_in_ < len(raw_vec):
            raw_vec = raw_vec[:model.n_features_in_]
        return round(float(model.predict_proba([raw_vec])[0][1]), 4)
    except Exception as exc:
        print(f"Error during predict_probability: {exc}")
        return None
