"""
Behavica – Firebase Cloud Function: Biometrická autentifikácia
==============================================================

Endpoint: POST /authenticate
Prijme surové behaviorálne dáta z Android apky (touch body, keystrokes,
senzory, základné metriky), extrahuje rovnaké príznaky ako extract_features.py,
porovná ich s uloženým profilom používateľa a vráti výsledok autentifikácie.

Tok:
  Android (Kotlin) → HTTP POST JSON → Cloud Function → model.pkl → odpoveď JSON
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

# ── Model sa načíta raz pri cold starte, nie pri každom volaní ────────────────
_model = None


def _load_model():
    """Načíta model.pkl z priečinka funkcie (bundlovaný pri deploy)."""
    global _model
    if _model is None:
        model_path = os.path.join(os.path.dirname(__file__), "model.pkl")
        with open(model_path, "rb") as f:
            _model = pickle.load(f)
    return _model


# ══════════════════════════════════════════════════════════════════════════════
# EXTRAKCIA PRÍZNAKOV – rovnaká logika ako extract_features.py
# Funkcie sú duplikované tu (nie importované) pretože functions/ je
# samostatný Python balík bez prístupu k RandomForestAuth/
# ══════════════════════════════════════════════════════════════════════════════

def _std(s):
    """Bezpečná smerodajná odchýlka – vráti 0 ak je len 1 prvok."""
    return float(s.std()) if len(s) > 1 else 0.0


def _extract_touch_features(touch_points: list) -> dict:
    """
    Extrahuje 19 touch príznakov zo zoznamu surových dotykových bodov.
    Každý bod je dict s kľúčmi: timestamp, pressure, size, touchMajor,
    touchMinor, x, y, action, target.
    """
    # Nulové hodnoty ak nie sú žiadne dáta
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

    # Rýchlosť dragu: len ACTION_MOVE udalosti v cieli "dragTest"
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

    # Celková rýchlosť pohybu (drag aj písanie)
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

    # Inter-touch interval: čas medzi po sebe idúcimi udalosťami
    dts = g["timestamp"].diff().dropna().values
    dts = dts[(dts > 0) & (dts < 5000)]

    # Tvar dotyku: pomer dlhšej a kratšej osi elipsy dotyku
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
        # FIX 6: ddof=1 – konzistentné s _std() v extract_features.py (pandas ddof=1)
        "tp_drag_vel_std":      float(np.std(vels, ddof=1))      if len(vels) > 1 else 0.0,
        "tp_drag_vel_max":      float(np.max(vels))              if len(vels) else 0.0,
        "tp_all_vel_mean":      float(np.mean(all_vels))         if len(all_vels) else 0.0,
        # FIX 6: ddof=1
        "tp_all_vel_std":       float(np.std(all_vels, ddof=1))  if len(all_vels) > 1 else 0.0,
        "tp_iti_mean":          float(np.mean(dts))              if len(dts) else 0.0,
        # FIX 6: ddof=1
        "tp_iti_std":           float(np.std(dts, ddof=1))       if len(dts) > 1 else 0.0,
        "tp_x_range":           float(g["x"].max() - g["x"].min()),
        "tp_y_range":           float(g["y"].max() - g["y"].min()),
        "tp_down_count":        int((g["action"] == "ACTION_DOWN").sum()),
    }


def _extract_keystroke_features(keystrokes: list) -> dict:
    """
    Extrahuje 13 keystroke príznakov zo zoznamu klávesnicových udalostí.
    Každá udalosť je dict s kľúčmi: timestamp, type (insert/delete), word, count.
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

    # Inter-key interval: čas medzi po sebe idúcimi stlačeniami kláves
    iki = g["timestamp"].diff().dropna().values
    iki = iki[(iki > 0) & (iki < 10_000)]

    # Čas per slovo: od prvého do posledného keystroke v rámci slova
    word_times = {}
    for word, wg in g.groupby("word"):
        wg = wg.sort_values("timestamp")
        if len(wg) > 1:
            word_times[word] = wg["timestamp"].iloc[-1] - wg["timestamp"].iloc[0]

    # Detekcia autocomplete/paste: count > 1 = vložených viacero znakov naraz
    auto_count = int((inserts["count"] > 1).sum()) if len(inserts) else 0

    return {
        "ks_total_events":   total,
        "ks_insert_count":   len(inserts),
        "ks_delete_count":   len(deletes),
        "ks_delete_ratio":   len(deletes) / max(total, 1),
        "ks_auto_count":     auto_count,
        "ks_iki_mean":       float(np.mean(iki))          if len(iki) else 0.0,
        # FIX 6: ddof=1
        "ks_iki_std":        float(np.std(iki, ddof=1))  if len(iki) > 1 else 0.0,
        "ks_iki_min":        float(np.min(iki))  if len(iki) else 0.0,
        "ks_iki_max":        float(np.max(iki))  if len(iki) else 0.0,
        "ks_iki_q25":        float(np.percentile(iki, 25)) if len(iki) else 0.0,
        "ks_iki_q75":        float(np.percentile(iki, 75)) if len(iki) else 0.0,
        "ks_word_time_mean": float(np.mean(list(word_times.values())))           if word_times else 0.0,
        # FIX 6: ddof=1
        "ks_word_time_std":  float(np.std(list(word_times.values()), ddof=1))   if len(word_times) > 1 else 0.0,
    }


def _extract_sensor_features(sensor_data: list) -> dict:
    """
    Extrahuje 22 senzorových príznakov zo zoznamu meraní.
    Každé meranie je dict s kľúčmi: accelX, accelY, accelZ, gyroX, gyroY, gyroZ.
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

    # 3D magnitúdy – nezávislé od orientácie telefónu
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
    """
    Zostaví feature vektor v presnom poradí feature_cols (z model.pkl).
    Toto poradie musí byť identické s tréningom, inak by model predikoval nesprávne.
    """
    # Spojíme všetky features do jedného slovníka
    all_feats = {}
    all_feats.update(basic)        # submissionDurationSec, dragAttempts, ...
    all_feats.update(touch_feats)  # tp_pressure_mean, ...
    all_feats.update(ks_feats)     # ks_iki_mean, ...
    all_feats.update(sd_feats)     # sd_accelX_mean, ...

    # FIX 5: Chýbajúce hodnoty → mediánová hodnota z tréningu (nie 0, čo je nereálne)
    return np.array(
        [all_feats.get(col, feature_medians.get(col, 0.0)) for col in feature_cols],
        dtype=float,
    )


# ══════════════════════════════════════════════════════════════════════════════
# CLOUD FUNCTION ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════

@https_fn.on_request()
def authenticate(req: https_fn.Request) -> https_fn.Response:
    """
    HTTP POST endpoint pre biometrickú autentifikáciu.

    Očakávaný JSON vstup:
    {
      "userId": "68017",              // ID používateľa ktorý tvrdí že je prihlásený
      "basic": {                      // základné metriky zo SubmissionActivity
        "submissionDurationSec": 45.2,
        "dragAttempts": 1,
        "dragDistance": 12.5,
        "dragPathLength": 320.0,
        "dragDurationSec": 1.8,
        "textRewriteTime": 18000.0,
        "averageWordTime": 6000.0,
        "textEditCount": 18,
        "touchPointsCount": 142,
        "sensorDataCount": 890
      },
      "touchPoints": [                // surové dotykové body z BehaviorTracker
        {"timestamp": 1234, "pressure": 0.5, "size": 0.3,
         "touchMajor": 45.0, "touchMinor": 38.0,
         "x": 512.0, "y": 800.0, "action": "ACTION_DOWN", "target": "dragTest"},
        ...
      ],
      "keystrokes": [                 // klávesnicové udalosti z BehaviorTracker
        {"timestamp": 2000, "type": "insert", "word": "internet", "count": 1},
        ...
      ],
      "sensorData": [                 // senzorové merania zo SensorDataCollector
        {"accelX": 0.1, "accelY": 9.8, "accelZ": 0.3,
         "gyroX": 0.01, "gyroY": 0.02, "gyroZ": 0.0},
        ...
      ]
    }

    Odpoveď JSON:
    {
      "accepted": true,               // či bol používateľ prijatý
      "score": 0.847,                 // skóre podobnosti (0..1)
      "userId": "68017",
      "email": "daniela.chuda@stuba.sk"
    }
    """
    # ── CORS hlavičky – potrebné ak budeš testovať z browsera / inej domény
    headers = {"Access-Control-Allow-Origin": "*"}

    if req.method == "OPTIONS":
        headers["Access-Control-Allow-Methods"] = "POST"
        headers["Access-Control-Allow-Headers"] = "Content-Type"
        return https_fn.Response("", status=204, headers=headers)

    if req.method != "POST":
        return https_fn.Response(
            json.dumps({"error": "Len POST metóda je povolená"}),
            status=405, headers=headers, content_type="application/json"
        )

    # ── Parsovanie vstupu
    try:
        data = req.get_json()
        if data is None:
            raise ValueError("Prázdny alebo neplatný JSON")
    except Exception as e:
        return https_fn.Response(
            json.dumps({"error": f"Neplatný JSON: {str(e)}"}),
            status=400, headers=headers, content_type="application/json"
        )

    claimed_user_id = data.get("userId")
    basic           = data.get("basic", {})
    touch_points    = data.get("touchPoints", [])
    keystrokes      = data.get("keystrokes", [])
    sensor_data     = data.get("sensorData", [])

    if not claimed_user_id:
        return https_fn.Response(
            json.dumps({"error": "Chýba userId"}),
            status=400, headers=headers, content_type="application/json"
        )

    # ── Načítanie modelu (cached po prvom volaní)
    try:
        model = _load_model()
    except FileNotFoundError:
        return https_fn.Response(
            json.dumps({"error": "model.pkl nenájdený – spusti export_model.py a redeploy"}),
            status=500, headers=headers, content_type="application/json"
        )

    scaler          = model["scaler"]
    rf              = model["rf"]
    feature_cols    = model["feature_cols"]
    email_map       = {str(k): v for k, v in model["email_map"].items()}
    # FIX 3: EER prah z CV – nahrádza hardcoded 0.5
    eer_threshold   = model.get("eer_threshold", 0.5)
    # FIX 5: mediány príznakov – nahrádza fallback 0.0 v _build_feature_vector
    feature_medians = model.get("feature_medians", {})

    # FIX 4: Ochrana proti neznámemu userId – RF by inak pridelil skóre existujúcim
    # používateľom a mohol by falošne akceptovať útočníka ktorý nie je v modeli
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

    # ── Extrakcia príznakov (rovnaká logika ako v extract_features.py)
    touch_feats = _extract_touch_features(touch_points)
    ks_feats    = _extract_keystroke_features(keystrokes)
    sd_feats    = _extract_sensor_features(sensor_data)

    # ── Zostavenie feature vektora v správnom poradí
    raw_vec = _build_feature_vector(basic, touch_feats, ks_feats, sd_feats,
                                    feature_cols, feature_medians)

    # ── Škálovanie: rovnaký scaler ako pri tréningu
    x_scaled = scaler.transform(raw_vec.reshape(1, -1))

    # ── RF predikcia: pravdepodobnosť pre každého používateľa
    proba   = rf.predict_proba(x_scaled)[0]
    classes = [str(c) for c in rf.classes_]
    scores  = {cls: float(p) for cls, p in zip(classes, proba)}

    # ── Výsledok verifikácie
    claimed_score = scores.get(str(claimed_user_id), 0.0)
    best_user     = max(scores, key=scores.get)
    # FIX 3: EER prah z CV namiesto hardcoded 0.5 – prah má reálny vzťah k výkonu modelu
    accepted = bool(best_user == str(claimed_user_id) and claimed_score >= eer_threshold)

    result = {
        "accepted":     accepted,
        "score":        round(claimed_score, 4),
        "userId":       claimed_user_id,
        "email":        email_map.get(str(claimed_user_id), "neznámy"),
        "eerThreshold": round(eer_threshold, 4),
        # All scores – for debugging / visualization on Android side
        "allScores":    {str(uid): round(float(s), 4) for uid, s in scores.items()},
    }

    return https_fn.Response(
        json.dumps(result),
        status=200, headers=headers, content_type="application/json"
    )
