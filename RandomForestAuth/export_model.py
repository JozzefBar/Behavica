"""
export_model.py
===============
Natrénuje Random Forest model na existujúcich dátach a uloží ho do
functions/model.pkl, odkiaľ ho Firebase Cloud Function načíta pri štarte.

Čo sa uloží do model.pkl:
  - rf           : finálny RandomForestClassifier (natrénovaný na všetkých dátach)
  - feature_cols : presný zoznam a poradie features (musí sa zhodovať s Cloud Function)
  - email_map    : {userId: email} – pre čitateľné výstupy
  - eer_threshold: EER prah z CV (kde FAR = FRR)
  - feature_medians: mediány príznakov pre NaN imputáciu

Dôležité:
  run_rf_cv() robí dve veci naraz:
    1. Stratified 5-Fold CV → férové metriky
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

    # Odstránime 1. submission PRED extrakciou príznakov – rovnako ako v extract_features.py
    # Tým sa submission 1 nepremietne ani do mediánov ani do žiadnych štatistík.
    basic = basic[basic["submissionNumber"] != 1].reset_index(drop=True)
    tp    = tp[tp["submissionNumber"] != 1].reset_index(drop=True)
    ks    = ks[ks["submissionNumber"] != 1].reset_index(drop=True)
    sd    = sd[sd["submissionNumber"] != 1].reset_index(drop=True)

    print("Extrahujem príznaky...")
    tp_feat = extract_touch_features(tp)
    ks_feat = extract_keystroke_features(ks)
    sd_feat = extract_sensor_features(sd)
    # FIX 5: build_feature_matrix teraz vracia (df, medians_dict) – mediány exportujeme do model.pkl
    df, feature_medians = build_feature_matrix(basic, tp_feat, ks_feat, sd_feat)

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
    #   eer_threshold            → EER prah z CV ← exportujeme
    #
    # Používame "_" pre hodnoty ktoré nepotrebujeme (konvencia v Pythone)
    print("Spúšťam 5-Fold CV a trénujem finálny model (môže chvíľu trvať)...")
    y_true, y_pred, _, _, rf_model, eer_threshold = run_rf_cv(X_raw, y)
    import numpy as np
    cv_acc = float(np.mean(y_true == y_pred))

    email_map = dict(zip(meta["userId"], meta["email"]))

    # ── Uložíme všetko potrebné pre Cloud Function
    model_data = {
        "rf":               rf_model,         # RandomForestClassifier – rovnaký ako v evaluate.py
        "feature_cols":     feature_cols,     # presné poradie features – kľúčové pre správnu predikciu
        "email_map":        email_map,        # {userId: email} – pre výpis výsledkov
        "eer_threshold":    eer_threshold,    # EER prah z CV – nahrádza hardcoded 0.5 v main.py
        "feature_medians":  feature_medians,  # mediány príznakov – nahrádza fillna(0) v main.py
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "wb") as f:
        pickle.dump(model_data, f)

    n_samples = len(X_raw)
    n_users = len(rf_model.classes_)
    fold_train = int(n_samples * 0.8)
    fold_test = n_samples - fold_train

    print(f"\n{'='*60}")
    print(f"  MODEL EXPORTOVANÝ")
    print(f"{'='*60}")
    print(f"  Súbor:            {OUTPUT_PATH}")
    print(f"  Používatelia:     {n_users}")
    print(f"  Príznakov:        {len(feature_cols)}")
    print(f"")
    print(f"  Finálny model:    trénovaný na VŠETKÝCH {n_samples} submissionoch")
    print(f"                    (tento ide do produkcie)")
    print(f"")
    print(f"  5-Fold CV:        5x tréning na ~{fold_train} / test na ~{fold_test} submissionoch")
    print(f"                    (slúži len na výpočet metrík a EER prahu)")
    print(f"  CV presnosť:      {cv_acc*100:.1f}%")
    print(f"  EER threshold:    {eer_threshold*100:.2f}%  (prah z CV kde FAR = FRR)")
    print(f"{'='*56}")
    print(f"\n  Registrovaní používatelia:")
    for uid in rf_model.classes_:
        email = email_map.get(uid, email_map.get(str(uid), "?"))
        print(f"    {int(uid):>6d}  {email}")
    print(f"\n  Teraz spusti:")
    print(f"    cd ..")
    print(f"    firebase deploy --only functions")


if __name__ == "__main__":
    export()