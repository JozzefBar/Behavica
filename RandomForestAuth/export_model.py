"""
export_model.py
===============
Natrénuje Random Forest model na existujúcich dátach a uloží ho do
functions/model.pkl, odkiaľ ho Firebase Cloud Function načíta pri štarte.

Čo sa uloží do model.pkl:
  - scaler       : finálny StandardScaler (natrénovaný na všetkých dátach)
  - rf           : finálny RandomForestClassifier (natrénovaný na všetkých dátach)
  - feature_cols : presný zoznam a poradie features (musí sa zhodovať s Cloud Function)
  - email_map    : {userId: email} – pre čitateľné výstupy

Dôležité:
  run_rf_cv() robí dve veci naraz:
    1. Stratified 5-Fold CV → férové metriky (každý fold má vlastný scaler bez data leakage)
    2. Finálny model → natrénovaný na VŠETKÝCH dátach (tento sa exportuje)

  Exportujeme finálny model z run_rf_cv – nie nový samostatný model.
  Tým pádom je export_model.py konzistentný s evaluate.py.

Spustenie:
  cd RandomForestAuth
  python export_model.py
"""

import pickle
from pathlib import Path

# Extrakcia príznakov z extract_features.py
from extract_features import (
    load_all,
    extract_touch_features,
    extract_keystroke_features,
    extract_sensor_features,
    build_feature_matrix,
)
# Tréning a CV z evaluate.py – používame rovnaký model ako pri evaluácii
from evaluate import run_rf_cv

# Cieľový súbor – priamo v priečinku functions/
OUTPUT_PATH = Path(__file__).parent.parent / "functions" / "model.pkl"


def export():
    print("Načítavam dáta z CSV...")
    basic, tp, ks, sd, meta = load_all()

    print("Extrahujem príznaky...")
    tp_feat = extract_touch_features(tp)
    ks_feat = extract_keystroke_features(ks)
    sd_feat = extract_sensor_features(sd)
    df      = build_feature_matrix(basic, tp_feat, ks_feat, sd_feat)

    # Odstránime 1. submission každého používateľa – rovnako ako v evaluate.py
    df = df[df["submissionNumber"] != 1].reset_index(drop=True)

    # Stĺpce príznakov v presnom poradí – toto poradie musí Cloud Function dodržať
    feature_cols = [c for c in df.columns if c not in ["userId", "submissionNumber"]]
    X_raw = df[feature_cols].values
    y     = df["userId"].values

    print(f"Dataset: {len(df)} submissionov | {len(feature_cols)} príznakov | {len(set(y))} používatelia\n")

    # ── Spustíme run_rf_cv – robí 5-Fold CV (férové metriky) aj finálny model naraz
    #
    # run_rf_cv vracia 6 hodnôt:
    #   y_true, y_pred, y_proba  → CV výsledky pre metriky (tu ich nepotrebujeme)
    #   rf_classes               → poradie tried (tu nepotrebujeme)
    #   rf_model                 → finálny RF natrénovaný na VŠETKÝCH dátach ← exportujeme
    #   final_scaler             → finálny scaler natrénovaný na VŠETKÝCH dátach ← exportujeme
    #
    # Používame "_" pre hodnoty ktoré nepotrebujeme (konvencia v Pythone)
    print("Spúšťam 5-Fold CV a trénujem finálny model (môže chvíľu trvať)...")
    _, _, _, _, rf_model, final_scaler = run_rf_cv(X_raw, y)

    email_map = dict(zip(meta["userId"], meta["email"]))

    # ── Uložíme všetko potrebné pre Cloud Function
    model_data = {
        "scaler":       final_scaler,  # StandardScaler – rovnaký ako v evaluate.py
        "rf":           rf_model,      # RandomForestClassifier – rovnaký ako v evaluate.py
        "feature_cols": feature_cols,  # presné poradie features – kľúčové pre správnu predikciu
        "email_map":    email_map,     # {userId: email} – pre výpis výsledkov
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "wb") as f:
        pickle.dump(model_data, f)

    print(f"\nModel uložený: {OUTPUT_PATH}")
    print(f"Triedy v modeli: {list(rf_model.classes_)}")
    print(f"Príznakov: {len(feature_cols)}")
    print("\nHotovo. Teraz spusti:")
    print("  cd ..")
    print("  firebase deploy --only functions")


if __name__ == "__main__":
    export()