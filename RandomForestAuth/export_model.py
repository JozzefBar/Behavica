"""
export_model.py
===============
Natrénuje Random Forest model na ľubovoľnom ablation CSV variante a uloží ho do
functions/model.pkl, odkiaľ ho Firebase Cloud Function načíta pri štarte.

Voľba CSV variantu (a teda zoznamu príznakov):
  python export_model.py                              # default = vsetky_priznaky
  python export_model.py top10_priznaky               # iba top-10 najdôležitejších
  python export_model.py device_independent_priznaky  # device-independent subset
  python export_model.py len_keystrokes               # iba klávesnicové príznaky
  python export_model.py ablation_csvs/top10_priznaky.csv   # plná cesta tiež OK

Cieľ: vedieť rýchlo otestovať aký RF vyjde pre rôzne podmnožiny príznakov,
hlavne pre cross-device generalizáciu (device-independent variant).

Čo sa uloží do model.pkl:
  - rf            : finálny RandomForestClassifier (natrénovaný na všetkých dátach)
  - feature_cols  : presný zoznam a poradie features (Cloud Function ho použije)
  - email_map     : {userId: email} – pre čitateľné výstupy
  - eer_threshold : EER prah z 5-Fold CV
  - feature_medians: mediány príznakov pre NaN imputáciu

Predpoklad:
  Pred spustením musí existovať príslušný CSV v ablation_csvs/.
  Ak chýba – spusti najprv:  python extract_features.py
"""

import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from evaluate import run_rf_cv

OUTPUT_PATH = Path(__file__).parent.parent / "functions" / "model.pkl"
ABLATION_DIR = Path(__file__).parent / "ablation_csvs"
META_CSV     = Path(__file__).parent.parent / "BehavicaExport" / "user_metadata.csv"


def _resolve_csv_path(arg: str | None) -> Path:
    """
    Z argumentu (napr. "top10_priznaky" alebo "ablation_csvs/top10_priznaky.csv"
    alebo None) vyrobí cestu k existujúcemu CSV v ablation_csvs/.
    """
    if arg is None:
        return ABLATION_DIR / "vsetky_priznaky.csv"

    p = Path(arg)
    # Ak používateľ zadal plnú cestu
    if p.is_file():
        return p
    # Skús ako relatívna cesta od pwd
    if (Path.cwd() / p).is_file():
        return Path.cwd() / p
    # Skús pridať .csv ak nie je
    name = p.name if p.suffix == ".csv" else f"{p.name}.csv"
    candidate = ABLATION_DIR / name
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(
        f"Nenašiel som '{arg}'. Skúšané: {p}, {Path.cwd() / p}, {candidate}.\n"
        f"Spusti najprv: python extract_features.py"
    )


def export(csv_arg: str | None = None):
    csv_path = _resolve_csv_path(csv_arg)
    variant  = csv_path.stem  # napr. "top10_priznaky"

    print(f"Načítavam CSV variant: {csv_path}")
    df = pd.read_csv(csv_path)

    # Stĺpce príznakov = všetky okrem userId a submissionNumber
    feature_cols = [c for c in df.columns if c not in ("userId", "submissionNumber")]
    if not feature_cols:
        raise ValueError(f"V CSV {csv_path} nie sú žiadne príznakové stĺpce.")

    X_raw = df[feature_cols].values.astype(float)
    y     = df["userId"].values

    # Mediány na NaN imputáciu (Cloud Function ich použije pri chýbajúcich hodnotách)
    feature_medians = {
        col: float(df[col].median()) for col in feature_cols
    }

    print(f"Dataset: {len(df)} submissionov | {len(feature_cols)} príznakov | "
          f"{len(set(y))} používateľov")
    print(f"Variant: {variant}")
    print(f"\nSpúšťam 5-Fold CV a trénujem finálny model (môže chvíľu trvať)...")

    y_true, y_pred, _, _, rf_model, eer_threshold = run_rf_cv(X_raw, y)
    cv_acc = float(np.mean(y_true == y_pred))

    # Email map z user_metadata.csv
    if META_CSV.is_file():
        meta = pd.read_csv(META_CSV)
        email_map = dict(zip(meta["userId"], meta["email"]))
    else:
        print(f"  ⚠ {META_CSV} nenájdený, email_map bude prázdny")
        email_map = {}

    model_data = {
        "rf":              rf_model,
        "feature_cols":    feature_cols,
        "email_map":       email_map,
        "eer_threshold":   eer_threshold,
        "feature_medians": feature_medians,
        "variant":         variant,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "wb") as f:
        pickle.dump(model_data, f)

    n_samples = len(X_raw)
    n_users   = len(rf_model.classes_)

    print(f"\n{'='*60}")
    print(f"  MODEL EXPORTOVANÝ ({variant})")
    print(f"{'='*60}")
    print(f"  Súbor:            {OUTPUT_PATH}")
    print(f"  Variant:          {variant}")
    print(f"  Príznakov:        {len(feature_cols)}")
    print(f"  Používateľov:     {n_users}")
    print(f"  Submissionov:     {n_samples} (trénovaný na všetkých)")
    print(f"  CV presnosť:      {cv_acc*100:.2f}%")
    print(f"  EER threshold:    {eer_threshold*100:.2f}%   (z CV, kde FAR = FRR)")
    print(f"{'='*60}")

    print(f"\n  Príznaky v modeli ({len(feature_cols)}):")
    for i, col in enumerate(feature_cols, 1):
        print(f"    {i:3d}. {col}")

    print(f"\n  Registrovaní používatelia:")
    for uid in rf_model.classes_:
        email = email_map.get(uid, email_map.get(str(uid), "?"))
        print(f"    {int(uid):>6d}  {email}")

    print(f"\n  Prejdi späť: cd ..")
    print(f"\n  Teraz spusti:  firebase deploy --only functions")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    export(arg)
