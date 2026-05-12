"""
Behavica – Firebase Cloud Function: biometric authentication.

Endpoint: POST /authenticate
Takes raw behavioral data from the Android app (touch points, keystrokes,
sensors, basic metrics), extracts the same features as extract_features.py,
compares them with the stored user profile and returns the auth result.

Flow: Android (Kotlin) → HTTP POST JSON → Cloud Function → model.pkl → JSON
"""

import json
import os
import pickle

import numpy as np
import pandas as pd
from firebase_admin import initialize_app
from firebase_functions import https_fn
from firebase_functions.options import set_global_options

initialize_app()

# Cloud Function config:
#   memory=512MB  – sklearn + pandas + numpy + 10MB model.pkl need more than default 256MB
#   timeout=120s  – cold start can take 20-30s, leave headroom for processing
#   max_instances=5 – enough for a research project
set_global_options(
    max_instances=5,
    memory=512,
    timeout_sec=120,
)

# Model is loaded once on cold start, not per request
_model = None


def _load_model():
    """Loads model.pkl from the function directory (bundled at deploy)."""
    global _model
    if _model is None:
        model_path = os.path.join(os.path.dirname(__file__), "model.pkl")
        with open(model_path, "rb") as f:
            _model = pickle.load(f)
    return _model


# Feature extraction – same logic as extract_features.py.
# Duplicated here (not imported) because functions/ is a standalone Python
# package without access to RandomForestAuth/.

def _std(s):
    """Safe std – returns 0 if there's only one element."""
    return float(s.std()) if len(s) > 1 else 0.0


def _extract_touch_features(touch_points: list) -> dict:
    """Extracts 19 touch features from raw touch points.

    Each point: timestamp, pressure, size, touchMajor, touchMinor, x, y,
    action, target.
    """
    # Zero defaults when there are no data
    empty = {k: 0.0 for k in [
        "tp_pressure_mean", "tp_pressure_std",
        "tp_size_mean", "tp_size_std",
        "tp_touchMajor_mean", "tp_touchMajor_std",
        "tp_touchMinor_mean", "tp_touchMinor_std",
        "tp_touch_shape_ratio",
        "tp_drag_vel_mean", "tp_drag_vel_std", "tp_drag_vel_max",
        "tp_all_vel_mean", "tp_all_vel_std",
        "tp_iti_mean", "tp_iti_std",
        "tp_x_range", "tp_y_range",
        "tp_down_count",
    ]}
    if not touch_points:
        return empty

    g = pd.DataFrame(touch_points).sort_values("timestamp")
    p     = g["pressure"]
    s_col = g["size"]

    # Drag velocity: ACTION_MOVE events targeting "dragTest" only
    drag_move = g[(g["action"] == "ACTION_MOVE") & (g["target"] == "dragTest")].copy()
    vels = []
    if len(drag_move) > 1:
        drag_move = drag_move.sort_values("timestamp")
        dx = drag_move["x"].diff()
        dy = drag_move["y"].diff()
        dt = drag_move["timestamp"].diff() / 1000.0
        dt = dt.replace(0, np.nan)
        v  = np.sqrt(dx**2 + dy**2) / dt
        vels = v.dropna().values

    # Total movement velocity (drag + typing)
    all_move = g[g["action"] == "ACTION_MOVE"].copy()
    all_vels = []
    if len(all_move) > 1:
        all_move = all_move.sort_values("timestamp")
        dx = all_move["x"].diff()
        dy = all_move["y"].diff()
        dt = all_move["timestamp"].diff() / 1000.0
        dt = dt.replace(0, np.nan)
        v  = np.sqrt(dx**2 + dy**2) / dt
        all_vels = v.dropna().values

    # Inter-touch interval: time between successive events
    dts = g["timestamp"].diff().dropna().values
    dts = dts[(dts > 0) & (dts < 5000)]

    # Touch shape: ratio of major/minor axis of the touch ellipse
    ratio = (g["touchMajor"] / g["touchMinor"].replace(0, np.nan)).dropna()

    return {
        "tp_pressure_mean":     float(p.mean()),
        "tp_pressure_std":      _std(p),
        "tp_size_mean":         float(s_col.mean()),
        "tp_size_std":          _std(s_col),
        "tp_touchMajor_mean":   float(g["touchMajor"].mean()),
        "tp_touchMajor_std":    _std(g["touchMajor"]),
        "tp_touchMinor_mean":   float(g["touchMinor"].mean()),
        "tp_touchMinor_std":    _std(g["touchMinor"]),
        "tp_touch_shape_ratio": float(ratio.mean()) if len(ratio) else 1.0,
        "tp_drag_vel_mean":     float(np.mean(vels))              if len(vels) else 0.0,
        # ddof=1 keeps std consistent with pandas _std() in extract_features.py
        "tp_drag_vel_std":      float(np.std(vels, ddof=1))      if len(vels) > 1 else 0.0,
        "tp_drag_vel_max":      float(np.max(vels))              if len(vels) else 0.0,
        "tp_all_vel_mean":      float(np.mean(all_vels))         if len(all_vels) else 0.0,
        "tp_all_vel_std":       float(np.std(all_vels, ddof=1))  if len(all_vels) > 1 else 0.0,
        "tp_iti_mean":          float(np.mean(dts))              if len(dts) else 0.0,
        "tp_iti_std":           float(np.std(dts, ddof=1))       if len(dts) > 1 else 0.0,
        "tp_x_range":           float(g["x"].max() - g["x"].min()),
        "tp_y_range":           float(g["y"].max() - g["y"].min()),
        "tp_down_count":        int((g["action"] == "ACTION_DOWN").sum()),
    }


def _extract_keystroke_features(keystrokes: list) -> dict:
    """Extracts 13 keystroke features from keyboard events.

    Each event: timestamp, type (insert/delete), word, count.
    """
    empty = {k: 0.0 for k in [
        "ks_total_events", "ks_insert_count", "ks_delete_count",
        "ks_delete_ratio", "ks_auto_count",
        "ks_iki_mean", "ks_iki_std", "ks_iki_min", "ks_iki_max",
        "ks_iki_q25", "ks_iki_q75",
        "ks_word_time_mean", "ks_word_time_std",
    ]}
    if not keystrokes:
        return empty

    g       = pd.DataFrame(keystrokes).sort_values("timestamp")
    inserts = g[g["type"] == "insert"]
    deletes = g[g["type"] == "delete"]
    total   = len(g)

    # Inter-key interval: time between successive keypresses
    iki = g["timestamp"].diff().dropna().values
    iki = iki[(iki > 0) & (iki < 10_000)]

    # Per-word time: from first to last keystroke within a word
    word_times = {}
    for word, wg in g.groupby("word"):
        wg = wg.sort_values("timestamp")
        if len(wg) > 1:
            word_times[word] = wg["timestamp"].iloc[-1] - wg["timestamp"].iloc[0]

    # Autocomplete/paste detection: count > 1 means multiple chars inserted at once
    auto_count = int((inserts["count"] > 1).sum()) if len(inserts) else 0

    return {
        "ks_total_events":   total,
        "ks_insert_count":   len(inserts),
        "ks_delete_count":   len(deletes),
        "ks_delete_ratio":   len(deletes) / max(total, 1),
        "ks_auto_count":     auto_count,
        "ks_iki_mean":       float(np.mean(iki))          if len(iki) else 0.0,
        "ks_iki_std":        float(np.std(iki, ddof=1))  if len(iki) > 1 else 0.0,
        "ks_iki_min":        float(np.min(iki))  if len(iki) else 0.0,
        "ks_iki_max":        float(np.max(iki))  if len(iki) else 0.0,
        "ks_iki_q25":        float(np.percentile(iki, 25)) if len(iki) else 0.0,
        "ks_iki_q75":        float(np.percentile(iki, 75)) if len(iki) else 0.0,
        "ks_word_time_mean": float(np.mean(list(word_times.values())))           if word_times else 0.0,
        "ks_word_time_std":  float(np.std(list(word_times.values()), ddof=1))   if len(word_times) > 1 else 0.0,
    }


def _extract_sensor_features(sensor_data: list) -> dict:
    """Extracts 22 sensor features from sensor readings.

    Each reading: accelX, accelY, accelZ, gyroX, gyroY, gyroZ.
    """
    empty = {k: 0.0 for k in [
        "sd_accelX_mean", "sd_accelX_std", "sd_accelX_range",
        "sd_accelY_mean", "sd_accelY_std", "sd_accelY_range",
        "sd_accelZ_mean", "sd_accelZ_std", "sd_accelZ_range",
        "sd_gyroX_mean",  "sd_gyroX_std",  "sd_gyroX_range",
        "sd_gyroY_mean",  "sd_gyroY_std",  "sd_gyroY_range",
        "sd_gyroZ_mean",  "sd_gyroZ_std",  "sd_gyroZ_range",
        "sd_accel_mag_mean", "sd_accel_mag_std",
        "sd_gyro_mag_mean",  "sd_gyro_mag_std",
    ]}
    if not sensor_data:
        return empty

    g = pd.DataFrame(sensor_data)

    # 3D magnitudes – independent of phone orientation
    accel_mag = np.sqrt(g["accelX"]**2 + g["accelY"]**2 + g["accelZ"]**2)
    gyro_mag  = np.sqrt(g["gyroX"]**2  + g["gyroY"]**2  + g["gyroZ"]**2)

    return {
        "sd_accelX_mean":    float(g["accelX"].mean()),
        "sd_accelX_std":     _std(g["accelX"]),
        "sd_accelX_range":   float(g["accelX"].max() - g["accelX"].min()),
        "sd_accelY_mean":    float(g["accelY"].mean()),
        "sd_accelY_std":     _std(g["accelY"]),
        "sd_accelY_range":   float(g["accelY"].max() - g["accelY"].min()),
        "sd_accelZ_mean":    float(g["accelZ"].mean()),
        "sd_accelZ_std":     _std(g["accelZ"]),
        "sd_accelZ_range":   float(g["accelZ"].max() - g["accelZ"].min()),
        "sd_gyroX_mean":     float(g["gyroX"].mean()),
        "sd_gyroX_std":      _std(g["gyroX"]),
        "sd_gyroX_range":    float(g["gyroX"].max() - g["gyroX"].min()),
        "sd_gyroY_mean":     float(g["gyroY"].mean()),
        "sd_gyroY_std":      _std(g["gyroY"]),
        "sd_gyroY_range":    float(g["gyroY"].max() - g["gyroY"].min()),
        "sd_gyroZ_mean":     float(g["gyroZ"].mean()),
        "sd_gyroZ_std":      _std(g["gyroZ"]),
        "sd_gyroZ_range":    float(g["gyroZ"].max() - g["gyroZ"].min()),
        "sd_accel_mag_mean": float(accel_mag.mean()),
        "sd_accel_mag_std":  _std(accel_mag),
        "sd_gyro_mag_mean":  float(gyro_mag.mean()),
        "sd_gyro_mag_std":   _std(gyro_mag),
    }


def _build_feature_vector(basic: dict, touch_feats: dict,
                          ks_feats: dict, sd_feats: dict,
                          feature_cols: list,
                          feature_medians: dict) -> np.ndarray:
    """Builds a feature vector in the exact feature_cols order from model.pkl.

    The order MUST match training, otherwise predictions are nonsense.
    """
    all_feats = {}
    all_feats.update(basic)
    all_feats.update(touch_feats)
    all_feats.update(ks_feats)
    all_feats.update(sd_feats)

    # Missing values → median from training (not 0, which is unrealistic)
    return np.array(
        [all_feats.get(col, feature_medians.get(col, 0.0)) for col in feature_cols],
        dtype=float,
    )


# Cloud function endpoint

@https_fn.on_request()
def authenticate(req: https_fn.Request) -> https_fn.Response:
    """HTTP POST endpoint for biometric authentication.

    Expected JSON input: userId, basic (metrics), touchPoints, keystrokes, sensorData.
    Response JSON: accepted, score, userId, email, eerThreshold, modelVariant, allScores.
    """
    # CORS headers – needed for cross-origin testing
    headers = {"Access-Control-Allow-Origin": "*"}

    if req.method == "OPTIONS":
        headers["Access-Control-Allow-Methods"] = "POST"
        headers["Access-Control-Allow-Headers"] = "Content-Type"
        return https_fn.Response("", status=204, headers=headers)

    if req.method != "POST":
        return https_fn.Response(
            json.dumps({"error": "Only POST is allowed"}),
            status=405, headers=headers, content_type="application/json"
        )

    try:
        data = req.get_json()
        if data is None:
            raise ValueError("Empty or invalid JSON")
    except Exception as e:
        return https_fn.Response(
            json.dumps({"error": f"Invalid JSON: {str(e)}"}),
            status=400, headers=headers, content_type="application/json"
        )

    claimed_user_id = data.get("userId")
    basic           = data.get("basic", {})
    touch_points    = data.get("touchPoints", [])
    keystrokes      = data.get("keystrokes", [])
    sensor_data     = data.get("sensorData", [])

    if not claimed_user_id:
        return https_fn.Response(
            json.dumps({"error": "Missing userId"}),
            status=400, headers=headers, content_type="application/json"
        )

    # Load model (cached after first call)
    try:
        model = _load_model()
    except FileNotFoundError:
        return https_fn.Response(
            json.dumps({"error": "model.pkl not found – run export_model.py and redeploy"}),
            status=500, headers=headers, content_type="application/json"
        )

    rf              = model["rf"]
    feature_cols    = model["feature_cols"]
    email_map       = {str(k): v for k, v in model["email_map"].items()}
    # EER threshold from CV – replaces hardcoded 0.5
    eer_threshold   = model.get("eer_threshold", 0.5)
    # Feature medians – replace 0.0 fallback in _build_feature_vector
    feature_medians = model.get("feature_medians", {})

    # Guard against unknown userId – RF would otherwise distribute probability
    # across known users and might falsely accept an attacker not in the model.
    known_classes = [str(c) for c in rf.classes_]
    if str(claimed_user_id) not in known_classes:
        result = {
            "accepted":  False,
            "score":     0.0,
            "userId":    claimed_user_id,
            "email":     "unknown",
            "allScores": {},
            "error":     "user_not_in_model",
        }
        return https_fn.Response(json.dumps(result), status=200,
                                 headers=headers, content_type="application/json")

    # Feature extraction (same logic as extract_features.py)
    touch_feats = _extract_touch_features(touch_points)
    ks_feats    = _extract_keystroke_features(keystrokes)
    sd_feats    = _extract_sensor_features(sensor_data)

    raw_vec = _build_feature_vector(basic, touch_feats, ks_feats, sd_feats,
                                    feature_cols, feature_medians)

    # RF prediction: probability per user
    proba   = rf.predict_proba(raw_vec.reshape(1, -1))[0]
    classes = [str(c) for c in rf.classes_]
    scores  = {cls: float(p) for cls, p in zip(classes, proba)}

    # Verification result – use EER threshold from CV instead of hardcoded 0.5
    claimed_score = scores.get(str(claimed_user_id), 0.0)
    best_user     = max(scores, key=scores.get)
    accepted = bool(best_user == str(claimed_user_id) and claimed_score >= eer_threshold)

    result = {
        "accepted":     accepted,
        "score":        round(claimed_score, 4),
        "userId":       claimed_user_id,
        "email":        email_map.get(str(claimed_user_id), "unknown"),
        "eerThreshold": round(eer_threshold, 4),
        "modelVariant": model.get("variant", "unknown"),
        "allScores":    {str(uid): round(float(s), 4) for uid, s in scores.items()},
    }

    return https_fn.Response(
        json.dumps(result),
        status=200, headers=headers, content_type="application/json"
    )
