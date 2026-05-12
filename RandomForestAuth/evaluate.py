"""
Behavica – behavioral biometrics evaluation (Random Forest).

Two independent evaluations:
  a) Stratified 5-Fold CV  – standard, literature-comparable metric.
  b) Temporal evaluation   – chronological split (train sub 2–11, test 12–15),
                             simulates real deployment, more realistic results.

Produces TAR/FAR/FRR/EER/AUC/Accuracy, console tables, demo authentications,
and 6 figures (2 per eval + 2 feature importance).

Why two evaluations: 5-Fold CV shuffles submissions; all 14 submissions per
user come from one short session, so test samples are very similar to train
samples and metrics are optimistically biased. The temporal split exposes
real generalization capability.

Run:
  python evaluate.py                                    ← asks for CSV
  python evaluate.py features_extracted.csv
  python evaluate.py ablation_csvs/len_senzory.csv

Requires user_metadata.csv in BehavicaExport/; CSV must contain userId,
submissionNumber + feature columns.
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold
import warnings

# Suppress only non-essential sklearn/numpy warnings;
# UndefinedMetricWarning and other important ones stay visible.
warnings.filterwarnings("ignore", category=FutureWarning,      module="sklearn")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="sklearn")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="numpy")

DATA_DIR = Path(__file__).parent.parent / "BehavicaExport"
LOG_PATH = Path(__file__).parent / "evaluate_log.txt"


# Logging – output goes to console and evaluate_log.txt simultaneously.
# The log is overwritten on each run (mode="w").

class _Tee:
    """Writes output to both console (stdout) and a file."""
    def __init__(self, file):
        self._file   = file
        self._stdout = sys.stdout
    def write(self, data):
        self._stdout.write(data)
        self._file.write(data)
    def flush(self):
        self._stdout.flush()
        self._file.flush()


def _start_logging():
    """Routes stdout through _Tee → console + evaluate_log.txt."""
    log_file = open(LOG_PATH, "w", encoding="utf-8")
    sys.stdout = _Tee(log_file)
    return log_file


def _stop_logging(log_file):
    """Restores stdout and closes the log file."""
    sys.stdout = sys.stdout._stdout
    log_file.close()
    print(f"  → Log uložený: {LOG_PATH}")


# Biometric metrics:
#   TA/FR/FA/TR – true/false accept/reject counts.
#   TAR = TA / (TA + FR)   FAR = FA / (FA + TR)   FRR = FR / (TA + FR) = 1 − TAR
#   EER – threshold where FAR = FRR (lower = better; ideally 0%).
#   Accuracy = (TA + TR) / (TA + FR + FA + TR) at the EER threshold.
#   AUC – area under TAR vs. FAR (1.0 = perfect, 0.5 = random).

def compute_metrics(genuine_scores: np.ndarray, impostor_scores: np.ndarray) -> dict:
    """Sweeps thresholds, returns TAR/FAR/FRR per threshold, plus EER and AUC.

    Decision rule: score >= threshold → ACCEPT, otherwise REJECT.
    """
    all_scores = np.concatenate([genuine_scores, impostor_scores])
    thresholds = np.linspace(all_scores.min(), all_scores.max(), 1000)

    tars, fars, frrs = [], [], []
    for thr in thresholds:
        TA = np.sum(genuine_scores >= thr)
        FR = np.sum(genuine_scores <  thr)
        FA = np.sum(impostor_scores >= thr)     # security risk if elevated
        TR = np.sum(impostor_scores <  thr)
        tars.append(TA / max(TA + FR, 1))
        fars.append(FA / max(FA + TR, 1))
        frrs.append(FR / max(TA + FR, 1))

    tars = np.array(tars); fars = np.array(fars); frrs = np.array(frrs)

    # EER = threshold minimizing |FAR − FRR|
    eer_idx = int(np.argmin(np.abs(fars - frrs)))
    eer     = float((fars[eer_idx] + frrs[eer_idx]) / 2)
    eer_thr = float(thresholds[eer_idx])

    # Metrics at the EER threshold
    thr = eer_thr
    TA = int(np.sum(genuine_scores >= thr))
    FR = int(np.sum(genuine_scores <  thr))
    FA = int(np.sum(impostor_scores >= thr))
    TR = int(np.sum(impostor_scores <  thr))
    accuracy = (TA + TR) / max(TA + FR + FA + TR, 1)

    sorted_idx = np.argsort(fars)
    auc = float(np.trapezoid(tars[sorted_idx], fars[sorted_idx]))

    return {
        "thresholds":    thresholds,
        "TAR": tars, "FAR": fars, "FRR": frrs,
        "EER": eer,  "EER_threshold": eer_thr,
        "AUC": auc,
        "Accuracy": accuracy,
        "TA": TA, "FA": FA, "TR": TR, "FR": FR,
        "n_genuine":  len(genuine_scores),
        "n_impostor": len(impostor_scores),
    }


# Random Forest – Stratified 5-Fold cross-validation

def run_rf_cv(X_raw: np.ndarray, y: np.ndarray):
    """Stratified 5-Fold CV with a Random Forest classifier.

    Each fold uses ~80% train / ~20% test, with proportional representation
    of all users in both parts.

    Caveat: optimistic metric — submissions from the same session can land in
    both train and test folds. For a more realistic estimate see
    run_temporal_eval().

    A final RF is also trained on ALL data (used for feature importance,
    demo authentication and export).

    Note: StandardScaler was removed; RF is scale-invariant (threshold-based).

    Returns: (y_true, y_pred, y_proba, rf_classes, final_rf, eer_threshold).
    """
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    # Stricter regularization (max_depth=10, min_samples_leaf=5) prevents the
    # model from memorizing session-specific patterns — all 14 submissions per
    # user come from one short session and are very similar. Looser params
    # (depth=20, leaf=3) reached ~99.8% locally but generalized poorly in prod.
    rf_params = dict(
        n_estimators=300,
        max_depth=10,
        min_samples_leaf=5,
        max_features="sqrt",
        random_state=42,
    )

    y_true_list, y_pred_list, y_proba_list = [], [], []
    fold_classes = None
    n_splits = skf.get_n_splits()
    correct  = 0
    total    = 0

    for fold_i, (train_idx, test_idx) in enumerate(skf.split(X_raw, y), start=1):
        X_tr, X_te = X_raw[train_idx], X_raw[test_idx]
        y_tr, y_te = y[train_idx],     y[test_idx]

        # Fresh RF per fold – no state carryover
        fold_rf = RandomForestClassifier(**rf_params)
        fold_rf.fit(X_tr, y_tr)
        preds        = fold_rf.predict(X_te)
        probas       = fold_rf.predict_proba(X_te)
        fold_classes = fold_rf.classes_   # same across folds (stratified)

        correct += int(np.sum(preds == y_te))
        total   += len(y_te)
        y_true_list.extend(y_te)
        y_pred_list.extend(preds)
        y_proba_list.extend(probas)

        acc = correct / total * 100
        bar = "█" * fold_i + "░" * (n_splits - fold_i)
        print(f"  [{bar}] Fold {fold_i}/{n_splits}  "
              f"train={len(train_idx)}  test={len(test_idx)}  "
              f"priebežná acc: {acc:.1f}%")

    print()

    y_true  = np.array(y_true_list)
    y_pred  = np.array(y_pred_list)
    y_proba = np.array(y_proba_list)

    # EER threshold from CV scores (not training data); exported to model.pkl
    # and used in main.py instead of a hardcoded 0.5.
    g_cv, i_cv    = rf_verification_scores(y_true, y_proba, fold_classes)
    cv_metrics    = compute_metrics(g_cv, i_cv)
    eer_threshold = cv_metrics["EER_threshold"]

    # Final model on full data – used for feature importance and export
    final_rf = RandomForestClassifier(**rf_params)
    final_rf.fit(X_raw, y)

    return (y_true, y_pred, y_proba, fold_classes, final_rf, eer_threshold)


def rf_verification_scores(y_true, y_proba, rf_classes, top_k=3):
    """Converts CV probabilities to genuine and impostor scores.

    For each test submission by user u:
      genuine  = P(u)
      impostor = top-K of P(v≠u)  (strongest competitors only)

    Why top-K instead of all: with many classes most P(v≠u) are tiny
    (~0.00–0.04) because RF splits 1.0 across many users; including them
    artificially lowers FAR. Top-K (default 3) keeps only the realistic
    threats.

    Returns N genuine + N×top_k impostor scores.
    """
    genuine, impostor = [], []
    for yt, proba in zip(y_true, y_proba):
        cls_idx = int(np.where(rf_classes == yt)[0][0])
        genuine.append(proba[cls_idx])
        imp_scores = sorted(
            [proba[j] for j, c in enumerate(rf_classes) if c != yt],
            reverse=True,
        )
        impostor.extend(imp_scores[:top_k])
    return np.array(genuine), np.array(impostor)


# Temporal evaluation – chronological train/test split.
# Trains on submissions 2–11 and tests on 12–15. Reveals real generalization
# to future behavior (not just other samples from the same session).

def run_temporal_eval(df: pd.DataFrame, feature_cols: list):
    """Chronological train/test eval — older submissions train, newer test.

    Split (submission 1 already dropped in extract_features.py):
      TRAIN = sub 2–11 (~10 per user)
      TEST  = sub 12–15 (~4 per user)

    Same return shape as run_rf_cv for consistent downstream handling.
    """
    train_mask = df["submissionNumber"] <= 11
    test_mask  = df["submissionNumber"] > 11

    X_tr_raw = df.loc[train_mask, feature_cols].values
    y_tr     = df.loc[train_mask, "userId"].values
    X_te_raw = df.loc[test_mask,  feature_cols].values
    y_te     = df.loc[test_mask,  "userId"].values

    print(f"  Temporálny split: train={len(X_tr_raw)} (sub 2–11)  "
          f"test={len(X_te_raw)} (sub 12–15)")

    # Same RF params as run_rf_cv
    rf_params = dict(
        n_estimators=300,
        max_depth=10,
        min_samples_leaf=5,
        max_features="sqrt",
        random_state=42,
    )

    rf = RandomForestClassifier(**rf_params)
    rf.fit(X_tr_raw, y_tr)

    y_pred = rf.predict(X_te_raw)
    y_proba = rf.predict_proba(X_te_raw)

    acc = float(np.mean(y_pred == y_te))
    print(f"  Temporálna identifikačná presnosť: {acc*100:.1f}%\n")

    # EER threshold from temporal scores – used by the demo verification
    g_t, i_t    = rf_verification_scores(y_te, y_proba, rf.classes_)
    t_metrics   = compute_metrics(g_t, i_t)
    eer_threshold = t_metrics["EER_threshold"]

    return y_te, y_pred, y_proba, rf.classes_, eer_threshold, rf


# Authentication – use on a single submission

def authenticate(raw_feature_vector: np.ndarray,
                 rf_model: RandomForestClassifier,
                 email_map: dict,
                 claimed_user_id=None,
                 eer_threshold: float = 0.5) -> dict:
    """Authenticates one submission against a trained Random Forest.

    With claimed_user_id → verification (1:1); without → identification (1:N).
    eer_threshold must match the one used in Cloud Function main.py.
    """
    proba = rf_model.predict_proba(raw_feature_vector.reshape(1, -1))[0]

    scores    = {str(c): float(p) for c, p in zip(rf_model.classes_, proba)}
    best_user = max(scores, key=scores.get)

    total = sum(scores.values())
    pct   = {uid: round(s / total * 100, 2) for uid, s in scores.items()}

    result = {
        "mode":       "verification" if claimed_user_id else "identification",
        "all_scores": scores,
        "all_pct":    pct,
        "email_map":  email_map,
    }

    if claimed_user_id:
        # Verification: "I claim to be user X – am I really?"
        claimed_score = scores.get(str(claimed_user_id), 0.0)
        result.update({
            "claimed_user":   claimed_user_id,
            "claimed_email":  email_map.get(str(claimed_user_id), "?"),
            "score":          round(claimed_score, 4),
            "confidence_pct": pct.get(str(claimed_user_id), 0.0),
            # Same condition as Cloud Function main.py
            "accepted":       best_user == str(claimed_user_id) and claimed_score >= eer_threshold,
        })
    else:
        # Identification: "Which of the N users is this?"
        result.update({
            "predicted_user":  best_user,
            "predicted_email": email_map.get(best_user, "?"),
            "confidence_pct":  pct[best_user],
        })
    return result


def print_auth_result(res: dict):
    """Prints an authentication result to the console with a small bar chart."""
    print("\n" + "─" * 52)
    if res["mode"] == "identification":
        print(f"  IDENTIFIKÁCIA")
        print(f"  Predikovaný používateľ : {res['predicted_email']}")
        print(f"  Istota                 : {res['confidence_pct']:.1f}%")
    else:
        status = "✓ AKCEPTOVANÝ" if res["accepted"] else "✗ ODMIETNUTÝ"
        print(f"  VERIFIKÁCIA – {status}")
        print(f"  Požadovaný používateľ  : {res['claimed_email']}")
        print(f"  Skóre podobnosti       : {res['score']:.4f}  ({res['confidence_pct']:.1f}%)")

    print("\n  Rozdelenie skóre (% z celkového):")
    sorted_pct = sorted(res["all_pct"].items(), key=lambda x: x[1], reverse=True)
    for uid, pct in sorted_pct:
        bar   = "█" * int(pct / 2)
        email = res["email_map"].get(uid, str(uid))
        print(f"    {uid:<8s}  {email:<40s}  {pct:5.1f}%  {bar}")
    print("─" * 52)


    # Visualization lives in visualize.py


# Console metrics table

def print_metrics_table(m_rf, rf_acc, meta, y_true, y_pred, csv_label: str = "",
                        eval_name: str = ""):
    """Prints a readable table of biometric metrics."""
    eer_idx   = int(np.argmin(np.abs(m_rf["FAR"] - m_rf["FRR"])))
    email_map = dict(zip(meta["userId"], meta["email"]))

    print("\n" + "═" * 56)
    title = f"   BEHAVICA – VÝSLEDKY ({eval_name})" if eval_name else \
            "   BEHAVICA – VÝSLEDKY BIOMETRICKEJ AUTENTIFIKÁCIE (RF)"
    print(title)
    if csv_label:
        print(f"   Dataset: {csv_label}")
    print("═" * 56)
    print(f"  {'Metrika':<38s} {'RF':>10s}")
    print("  " + "─" * 50)

    rows = [
        ("EER  (Equal Error Rate)",          f"{m_rf['EER']*100:.2f}%"),
        ("TAR pri EER",                      f"{m_rf['TAR'][eer_idx]*100:.2f}%"),
        ("FAR pri EER",                      f"{m_rf['FAR'][eer_idx]*100:.2f}%"),
        ("FRR pri EER",                      f"{m_rf['FRR'][eer_idx]*100:.2f}%"),
        ("Accuracy pri EER prahu",           f"{m_rf['Accuracy']*100:.2f}%"),
        ("AUC (plocha pod ROC krivkou)",     f"{m_rf['AUC']*100:.2f}%"),
        (f"Identifikačná Acc. ({eval_name or '5-Fold CV'})", f"{rf_acc*100:.2f}%"),
        ("", ""),
        ("Genuine vzorky (celkom)",          str(m_rf["n_genuine"])),
        ("Impostor vzorky (celkom)",         str(m_rf["n_impostor"])),
    ]
    for label, val in rows:
        if label == "":
            print()
        else:
            print(f"  {label:<38s} {val:>10s}")

    print(f"\n  Confusion matrix pri EER prahu (RF):")
    print(f"    TA={m_rf['TA']}  FR={m_rf['FR']}  FA={m_rf['FA']}  TR={m_rf['TR']}")

    print(f"\n  Per-používateľ identifikácia (RF {eval_name or '5-Fold CV'}):")
    for u in np.unique(y_true):
        mask  = y_true == u
        acc_u = np.mean(y_pred[mask] == u)
        print(f"    {str(email_map.get(u, u)):<40s}  "
              f"Acc: {acc_u*100:.1f}%  ({int(acc_u * mask.sum())}/{mask.sum()})")
    print("═" * 56)


# Main

def _print_demo(y_true, y_proba, rf_classes, eer_threshold, email_map,
                eval_name: str = ""):
    """Prints a demo authentication – first prediction per user."""
    classes_l = list(rf_classes)
    label = f" ({eval_name})" if eval_name else ""
    print(f"\n  DEMO VERIFIKÁCIA{label}: Prvá predikcia za každého používateľa")
    print(f"  (EER prah = {eer_threshold*100:.2f}%)\n")

    for uid in np.unique(y_true):
        uid_idx = np.where(y_true == uid)[0]
        if len(uid_idx) == 0:
            continue

        proba_row     = y_proba[uid_idx[0]]
        claimed_score = float(proba_row[classes_l.index(uid)])
        accepted      = claimed_score >= eer_threshold
        email         = email_map.get(str(uid), str(uid))
        status        = "✓ AKCEPTOVANÝ" if accepted else "✗ ODMIETNUTÝ"

        all_scores = sorted(zip(classes_l, proba_row), key=lambda x: x[1], reverse=True)
        user_rank  = next(i + 1 for i, (c, _) in enumerate(all_scores) if c == uid)
        n_users    = len(all_scores)
        best_uid   = all_scores[0][0]
        best_email = email_map.get(str(best_uid), str(best_uid))
        best_score = all_scores[0][1]

        print(f"  {status}  {email:<42s}  skóre={claimed_score*100:.1f}%  "
              f"rank=#{user_rank}/{n_users}")

        if user_rank > 1:
            print(f"  {'':>14s}  → najlepší: {best_email:<42s}  skóre={best_score*100:.1f}%")

        print(f"  {'':>14s}  Top-5: ", end="")
        for rank_i, (c, s) in enumerate(all_scores[:5], 1):
            marker = "◀" if c == uid else " "
            print(f"#{rank_i} {email_map.get(str(c), str(c)).split('@')[0]}={s*100:.1f}%{marker}  ", end="")
        print()


def main():
    # CSV selection
    script_dir = Path(__file__).parent

    if len(sys.argv) > 1:
        csv_path = Path(sys.argv[1])
        if not csv_path.is_absolute():
            csv_path = script_dir / csv_path
    else:
        available = sorted(script_dir.glob("*.csv")) + \
                    sorted((script_dir / "ablation_csvs").glob("*.csv")
                           if (script_dir / "ablation_csvs").exists() else [])
        if not available:
            print("Nenájdené žiadne CSV súbory. Najprv spusti extract_features.py")
            sys.exit(1)

        print("Dostupné CSV súbory:")
        for i, p in enumerate(available, 1):
            rel = p.relative_to(script_dir)
            print(f"  [{i}] {rel}")
        choice = input("\nZadaj číslo alebo cestu k CSV: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(available):
            csv_path = available[int(choice) - 1]
        else:
            csv_path = script_dir / choice
            if not csv_path.exists():
                csv_path = Path(choice)

    if not csv_path.exists():
        print(f"Súbor nenájdený: {csv_path}")
        sys.exit(1)

    csv_label = csv_path.name

    # Start logging (console + evaluate_log.txt)
    log_file = _start_logging()

    try:
        _run_evaluation(csv_path, csv_label)
    finally:
        _stop_logging(log_file)


def _run_evaluation(csv_path: Path, csv_label: str):
    """Core evaluation logic – separated from CSV picking I/O."""
    from visualize import visualize_eval, plot_feature_importance, show_all

    print(f"\nNačítavam: {csv_path}")

    df = pd.read_csv(csv_path)
    if "userId" not in df.columns or "submissionNumber" not in df.columns:
        print("CSV musí obsahovať stĺpce 'userId' a 'submissionNumber'.")
        sys.exit(1)

    feature_cols = [c for c in df.columns if c not in ["userId", "submissionNumber"]]
    X_raw = df[feature_cols].values
    y     = df["userId"].values

    print(f"Dataset: {len(df)} submissionov | {len(feature_cols)} príznakov "
          f"| {len(np.unique(y))} používatelia\n")

    meta = pd.read_csv(DATA_DIR / "user_metadata.csv")
    email_map = {str(k): v for k, v in zip(meta["userId"], meta["email"])}

    # Evaluation 1: Stratified 5-Fold CV
    print("Spúšťam RF Stratified 5-Fold cross-validáciu ...")
    y_true, y_pred, y_proba, rf_classes, rf_model, eer_threshold = run_rf_cv(X_raw, y)
    rf_acc     = float(np.mean(y_true == y_pred))
    g_rf, i_rf = rf_verification_scores(y_true, y_proba, rf_classes)
    m_rf       = compute_metrics(g_rf, i_rf)

    print_metrics_table(m_rf, rf_acc, meta, y_true, y_pred, csv_label,
                        eval_name="5-Fold CV")

    _print_demo(y_true, y_proba, rf_classes, eer_threshold, email_map,
                eval_name="5-Fold CV")

    # Evaluation 2: Temporal (chronological split)
    print("\nSpúšťam temporálnu evaluáciu (train=sub 2–11, test=sub 12–15) ...")
    t_true, t_pred, t_proba, t_classes, t_eer_thr, t_rf_model = run_temporal_eval(df, feature_cols)
    t_acc     = float(np.mean(t_true == t_pred))
    t_g, t_i  = rf_verification_scores(t_true, t_proba, t_classes)
    t_metrics = compute_metrics(t_g, t_i)

    print_metrics_table(t_metrics, t_acc, meta, t_true, t_pred, csv_label,
                        eval_name="Temporálna (train 2–11, test 12–15)")

    _print_demo(t_true, t_proba, t_classes, t_eer_thr, email_map,
                eval_name="Temporálna")

    # Visualizations: both evaluations + feature importance
    print("\nGenerujem vizualizácie ...")

    # Figures 1-2: 5-Fold CV (score distribution, violin, TAR/FAR/FRR, ROC, confusion)
    visualize_eval(m_rf, g_rf, i_rf, y_true, y_pred, y_proba, rf_classes,
                   eval_name="5-Fold CV", csv_label=csv_label)

    # Figures 3-4: Temporal evaluation (same plots)
    visualize_eval(t_metrics, t_g, t_i, t_true, t_pred, t_proba, t_classes,
                   eval_name="Temporálna (train 2–11, test 12–15)",
                   csv_label=csv_label)

    # Figure 5: Feature importance – 5-Fold CV model
    plot_feature_importance(rf_model, feature_cols, csv_label,
                            title_suffix="(5-Fold CV model)")

    # Figure 6: Feature importance – temporal model (train sub 2–11)
    plot_feature_importance(t_rf_model, feature_cols, csv_label,
                            title_suffix="(temporálny model – train sub 2–11)")

    show_all()


if __name__ == "__main__":
    main()
