"""
Behavica – Evaluácia behaviorálnej biometrie (Random Forest)
=============================================================

Čo tento skript robí:
  1. Načíta features CSV (výstup z extract_features.py).
  2. Spustí DVE nezávislé evaluácie:
     a) Stratified 5-Fold CV – štandardná metrika, porovnateľná s literatúrou.
     b) Temporálna evaluácia – chronologický split (train sub 2–11, test 12–15),
        simuluje reálne nasadenie a dáva realistickejšie výsledky.
  3. Vypočíta biometrické metriky: TAR, FAR, FRR, EER, AUC, Accuracy.
  4. Zobrazí prehľadné tabuľky a demo autentifikácie.
  5. Vygeneruje 6 figúr s grafmi (2 per evaluácia + 2 feature importance).

Prečo dve evaluácie:
  5-Fold CV náhodne miešavoľa submissiony medzi train/test. Keďže všetkých
  14 submissionov jedného používateľa pochádza z krátkeho obdobia (rovnaká
  session), test vzorky sú veľmi podobné tréningovým → metriky sú optimisticky
  skreslené. Temporálna evaluácia to rieši chronologickým rozdelením,
  čím odhaľuje reálnu generalizačnú schopnosť modelu.

Ako spustiť:
  python evaluate.py                                    ← pýta sa na CSV
  python evaluate.py features_extracted.csv             ← konkrétny CSV
  python evaluate.py ablation_csvs/len_senzory.csv      ← len senzory

Predpoklady:
  - Súbor user_metadata.csv musí byť v BehavicaExport/
    (potrebný pre email_map a per-user výpisy)
  - CSV musí mať stĺpce: userId, submissionNumber, + príznaky
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold
import warnings

# Potlačíme len nepodstatné sklearn varovania (FutureWarning, DeprecationWarning)
# UndefinedMetricWarning a iné dôležité varovania zostávajú viditeľné
warnings.filterwarnings("ignore", category=FutureWarning,      module="sklearn")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="sklearn")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="numpy")

DATA_DIR = Path(__file__).parent.parent / "BehavicaExport"
LOG_PATH = Path(__file__).parent / "evaluate_log.txt"


# ══════════════════════════════════════════════════════════════════════════════
# LOGGING – výstup ide súčasne na konzolu aj do evaluate_log.txt
# ══════════════════════════════════════════════════════════════════════════════
#
# Log sa PREPISUJE pri každom spustení (mode="w"), takže vždy obsahuje len
# posledný beh. Toto je užitočné pre rýchle porovnanie výsledkov.

class _Tee:
    """Zapisuje výstup súčasne na konzolu (stdout) aj do súboru."""
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
    """Presmeruje stdout cez _Tee → konzola + evaluate_log.txt."""
    log_file = open(LOG_PATH, "w", encoding="utf-8")
    sys.stdout = _Tee(log_file)
    return log_file


def _stop_logging(log_file):
    """Obnoví pôvodný stdout a zatvorí log súbor."""
    sys.stdout = sys.stdout._stdout
    log_file.close()
    print(f"  → Log uložený: {LOG_PATH}")


# ══════════════════════════════════════════════════════════════════════════════
# 1. VÝPOČET BIOMETRICKÝCH METRÍK
# ══════════════════════════════════════════════════════════════════════════════
#
# Štandardné biometrické metriky:
#
#   TA (True Accept)   = genuine submission bol SPRÁVNE akceptovaný
#   FR (False Reject)  = genuine submission bol NESPRÁVNE odmietnutý
#   FA (False Accept)  = impostor submission bol NESPRÁVNE akceptovaný
#   TR (True Reject)   = impostor submission bol SPRÁVNE odmietnutý
#
#   TAR = TA / (TA + FR)   → miera správneho prijatia (True Accept Rate)
#   FAR = FA / (FA + TR)   → miera falošného prijatia (False Accept Rate)
#   FRR = FR / (TA + FR)   → miera falošného zamietnutia (False Reject Rate)
#                          → pozor: FRR = 1 − TAR
#
#   EER (Equal Error Rate) = bod, kde FAR = FRR
#     → čím nižší EER, tým lepší systém (ideálne EER = 0%)
#
#   Accuracy = (TA + TR) / (TA + FR + FA + TR)  [pri prahu EER]
#
#   AUC (Area Under ROC Curve) = plocha pod krivkou TAR vs. FAR
#     → 1.0 = perfektný systém, 0.5 = náhodný klasifikátor
# ══════════════════════════════════════════════════════════════════════════════

def compute_metrics(genuine_scores: np.ndarray, impostor_scores: np.ndarray) -> dict:
    """
    Sweepuje cez prahy a vypočíta TAR, FAR, FRR pri každom prahu.
    Nájde EER (kde FAR ≈ FRR) a AUC (plocha pod ROC krivkou).

    Logika prahového rozhodovania:
      score >= prah → AKCEPTUJ
      score <  prah → ODMIETNI
    """
    all_scores = np.concatenate([genuine_scores, impostor_scores])
    # 1000 rovnomerne rozdelených prahov
    thresholds = np.linspace(all_scores.min(), all_scores.max(), 1000)

    tars, fars, frrs = [], [], []
    for thr in thresholds:
        # Počet prípadov pre každú kategóriu
        TA = np.sum(genuine_scores >= thr)      # genuine  akceptovaný → správne
        FR = np.sum(genuine_scores <  thr)      # genuine  odmietnutý  → chyba
        FA = np.sum(impostor_scores >= thr)     # impostor akceptovaný → chyba (bezpečnostné riziko!)
        TR = np.sum(impostor_scores <  thr)     # impostor odmietnutý  → správne
        tars.append(TA / max(TA + FR, 1))
        fars.append(FA / max(FA + TR, 1))
        frrs.append(FR / max(TA + FR, 1))

    tars = np.array(tars); fars = np.array(fars); frrs = np.array(frrs)

    # EER = prah kde |FAR - FRR| je minimálne
    eer_idx = int(np.argmin(np.abs(fars - frrs)))
    eer     = float((fars[eer_idx] + frrs[eer_idx]) / 2)
    eer_thr = float(thresholds[eer_idx])

    # Metriky pri EER prahu
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


# ══════════════════════════════════════════════════════════════════════════════
# 2. RANDOM FOREST – STRATIFIED 5-FOLD CROSS-VALIDÁCIA
# ══════════════════════════════════════════════════════════════════════════════

def run_rf_cv(X_raw: np.ndarray, y: np.ndarray):
    """
    Stratified 5-Fold cross-validácia s Random Forest klasifikátorom.

    Dataset sa rozdelí na 5 foldov – každý fold má ~80% tréning a ~20% test.
    "Stratified" = každý fold obsahuje proporcionálne zastúpenie všetkých
    používateľov v train aj test časti.

    POZOR: Táto metrika je optimistická – submissiony z rovnakej session sa
    môžu ocitnúť v train aj test folde, čo nafukuje presnosť. Pre realistickejší
    odhad produkčnej výkonnosti pozri run_temporal_eval().

    Pre každý fold:
      – natrénuje RF na tréningových dátach
      – predikuje triedy a pravdepodobnosti pre testovaciu sadu (~20%)

    Na konci natrénuje finálny RF na VŠETKÝCH dátach
    (pre feature importance, demo autentifikáciu a export).

    Poznámka: StandardScaler bol odstránený – Random Forest je invariantný voči
    škálovaniu (rozhoduje sa na základe prahov, nie vzdialeností), takže scaler
    nemal žiadny vplyv na výsledky.

    Vracia:
      y_true        – skutočné triedy (userId) testovacích submissionov
      y_pred        – predikované triedy
      y_proba       – matica pravdepodobností [n_samples × n_classes]
      rf_classes    – poradie tried v y_proba
      rf            – finálny RF model (natrénovaný na všetkých dátach)
      eer_threshold – EER prah z CV skóre (exportovaný do model.pkl)
    """
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    # RF parametre definované raz ako slovník – neopakujú sa a ľahko sa menia.
    # max_depth=10 a min_samples_leaf=5 sú prísnejšia regularizácia, ktorá zabraňuje
    # modelu zapamätať si session-specific vzory (všetkých 14 submissionov jedného
    # používateľa pochádza z krátkeho obdobia → sú si veľmi podobné).
    # Pri voľnejších parametroch (depth=20, leaf=3) model dosahoval ~99.8% lokálne,
    # ale v produkcii výrazne horšie – stromy sa naučili jemné rozdiely medzi
    # submissionmi z rovnakej session, ktoré v reálnom použití neexistujú.
    rf_params = dict(
        n_estimators=300,
        max_depth=10,          # obmedzenie hĺbky (20 = príliš voľné pre ~500 vzoriek)
        min_samples_leaf=5,    # min. 5 vzoriek v liste (3 = stále overfit)
        max_features="sqrt",   # sqrt príznakov pri každom splite
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

        # Nový RF objekt v každom folde – čistejší kód, žiadne prekrývanie stavu
        fold_rf = RandomForestClassifier(**rf_params)
        fold_rf.fit(X_tr, y_tr)
        preds        = fold_rf.predict(X_te)
        probas       = fold_rf.predict_proba(X_te)
        fold_classes = fold_rf.classes_   # triedy sú rovnaké vo všetkých foldoch (stratified)

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

    # EER prah vypočítaný z CV skóre – nie z tréningových dát.
    # Tento prah sa exportuje do model.pkl a používa v main.py namiesto hardcoded 0.5.
    g_cv, i_cv    = rf_verification_scores(y_true, y_proba, fold_classes)
    cv_metrics    = compute_metrics(g_cv, i_cv)
    eer_threshold = cv_metrics["EER_threshold"]

    # Finálny model natrénovaný na celých dátach
    # → slúži pre feature importance a export do model.pkl
    final_rf = RandomForestClassifier(**rf_params)
    final_rf.fit(X_raw, y)

    return (y_true, y_pred, y_proba, fold_classes, final_rf, eer_threshold)


def rf_verification_scores(y_true, y_proba, rf_classes, top_k=3):
    """
    Konvertuje LOO/CV pravdepodobnosti RF na genuine a impostor skóre.

    Pre každý testovací submission od používateľa u:
      genuine score  = P(u)    – pravdepodobnosť, že RF zaradí submission správne
      impostor score = top-K najvyšších P(v≠u) – najsilnejší konkurenti

    Prečo top-K namiesto všetkých:
      Pri 26 triedach väčšina P(v≠u) je ~0.00-0.04 (triviálne nízke), pretože
      RF rozdeľuje 1.0 medzi 26 tried. Tieto triviálne nulové skóre umelo
      znižujú FAR a nafukujú metriky. Top-K (default=3) berie len najsilnejších
      konkurentov → realistickejšie skóre simulujúce reálny útok.

    Celkovo: N genuine skóre + N×top_k impostor skóre.
    """
    genuine, impostor = [], []
    for yt, proba in zip(y_true, y_proba):
        cls_idx = int(np.where(rf_classes == yt)[0][0])
        genuine.append(proba[cls_idx])
        # Zozbierame skóre všetkých tried okrem skutočnej a zoradíme zostupne
        imp_scores = sorted(
            [proba[j] for j, c in enumerate(rf_classes) if c != yt],
            reverse=True,
        )
        # Vezmeme len top-K najsilnejších impostrov (najrealistickejšie hrozby)
        impostor.extend(imp_scores[:top_k])
    return np.array(genuine), np.array(impostor)


# ══════════════════════════════════════════════════════════════════════════════
# 2b. TEMPORÁLNA EVALUÁCIA – CHRONOLOGICKÉ ROZDELENIE TRAIN/TEST
# ══════════════════════════════════════════════════════════════════════════════
#
# Prečo je to potrebné:
#   5-Fold CV náhodne miešavoľa submissiony medzi train a test. Keďže všetkých
#   14 submissionov jedného používateľa pochádza z krátkeho obdobia (jedna session),
#   test vzorky sú prakticky kópie tréningových → metriky sú optimisticky skreslené.
#
#   Temporálna evaluácia rozdelí dáta chronologicky:
#     TRAIN = submissiony 2–11 (prvých 10 opakovaní po vynechaní 1.)
#     TEST  = submissiony 12–15 (posledné 4 opakovania)
#
#   Toto simuluje reálnu situáciu: model sa natrénuje na zozbieraných dátach
#   a neskôr prichádza nový submission, ktorý nebol súčasťou tréningových dát.
#   Výsledky sú preto bližšie k reálnej výkonnosti v produkcii.
# ══════════════════════════════════════════════════════════════════════════════

def run_temporal_eval(df: pd.DataFrame, feature_cols: list):
    """
    Chronologická train/test evaluácia – trénuje na starších, testuje na novších submissionoch.

    Na rozdiel od 5-fold CV, kde sa náhodne miešajú submissiony z rovnakej session,
    tu je rozdelenie striktne chronologické. Toto odhaľuje, ako dobre model
    generalizuje na budúce správanie používateľa – nie len na iné vzorky
    z rovnakej session.

    Rozdelenie:
      TRAIN = submissiony 2–11 (index po vynechaní 1.) → ~10 per user
      TEST  = submissiony 12–15                         → ~4 per user

    Vracia rovnakú štruktúru ako run_rf_cv pre konzistentné vyhodnotenie.
    """
    # Submissiony 2–11 na tréning, 12–15 na test
    # (submission 1 bol už odstránený v extract_features.py)
    train_mask = df["submissionNumber"] <= 11
    test_mask  = df["submissionNumber"] > 11

    X_tr_raw = df.loc[train_mask, feature_cols].values
    y_tr     = df.loc[train_mask, "userId"].values
    X_te_raw = df.loc[test_mask,  feature_cols].values
    y_te     = df.loc[test_mask,  "userId"].values

    print(f"  Temporálny split: train={len(X_tr_raw)} (sub 2–11)  "
          f"test={len(X_te_raw)} (sub 12–15)")

    # Rovnaké RF parametre ako v run_rf_cv
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

    # EER threshold z temporálnych skóre – pre demo verifikáciu
    g_t, i_t    = rf_verification_scores(y_te, y_proba, rf.classes_)
    t_metrics   = compute_metrics(g_t, i_t)
    eer_threshold = t_metrics["EER_threshold"]

    return y_te, y_pred, y_proba, rf.classes_, eer_threshold, rf


# ══════════════════════════════════════════════════════════════════════════════
# 3. AUTENTIFIKÁCIA – POUŽITIE NA NOVÝ SUBMISSION
# ══════════════════════════════════════════════════════════════════════════════

def authenticate(raw_feature_vector: np.ndarray,
                 rf_model: RandomForestClassifier,
                 email_map: dict,
                 claimed_user_id=None,
                 eer_threshold: float = 0.5) -> dict:
    """
    Autentifikuje jeden submission pomocou natrénovaného Random Forest modelu.

    Postup:
      1. RF predikuje pravdepodobnosti pre každého používateľa.
      2. P(claimed_user) = skóre podobnosti pre verifikáciu.

    Parametre:
      raw_feature_vector  – 1D numpy pole príznakov
      rf_model            – natrénovaný RandomForestClassifier
      email_map           – slovník {userId: email} pre čitateľné výstupy
      claimed_user_id     – ak zadaný → verifikácia (1:1)
                            inak       → identifikácia (1:N)
      eer_threshold       – EER prah z CV (rovnaký ako v Cloud Function main.py)
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
        # VERIFIKÁCIA: "Som používateľ X, je to naozaj ja?"
        claimed_score = scores.get(str(claimed_user_id), 0.0)
        result.update({
            "claimed_user":   claimed_user_id,
            "claimed_email":  email_map.get(str(claimed_user_id), "?"),
            "score":          round(claimed_score, 4),
            "confidence_pct": pct.get(str(claimed_user_id), 0.0),
            # Akceptovaný = best_user je claimed_user A skóre >= EER prah
            # Konzistentné s Cloud Function (main.py) – rovnaká podmienka
            "accepted":       best_user == str(claimed_user_id) and claimed_score >= eer_threshold,
        })
    else:
        # IDENTIFIKÁCIA: "Kto z N používateľov to je?"
        result.update({
            "predicted_user":  best_user,
            "predicted_email": email_map.get(best_user, "?"),
            "confidence_pct":  pct[best_user],
        })
    return result


def print_auth_result(res: dict):
    """Vypíše výsledok autentifikácie do konzoly s vizuálnym bar chartom."""
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


    # Vizualizácia je v samostatnom module visualize.py


# ══════════════════════════════════════════════════════════════════════════════
# 5. KONZOLOVÝ VÝPIS METRÍK
# ══════════════════════════════════════════════════════════════════════════════

def print_metrics_table(m_rf, rf_acc, meta, y_true, y_pred, csv_label: str = "",
                        eval_name: str = ""):
    """Vypíše prehľadnú tabuľku biometrických metrík do konzoly."""
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


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def _print_demo(y_true, y_proba, rf_classes, eer_threshold, email_map,
                eval_name: str = ""):
    """Vypíše demo autentifikáciu – prvú predikciu za každého používateľa."""
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
    # ── Výber CSV súboru ───────────────────────────────────────────────────────
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

    # ── Zapnúť logging (konzola + evaluate_log.txt) ──────────────────────────
    log_file = _start_logging()

    try:
        _run_evaluation(csv_path, csv_label)
    finally:
        _stop_logging(log_file)


def _run_evaluation(csv_path: Path, csv_label: str):
    """Hlavná logika evaluácie – oddelená od I/O výberu súboru."""
    from visualize import visualize_eval, plot_feature_importance, show_all

    print(f"\nNačítavam: {csv_path}")

    # ── Načítanie features CSV ─────────────────────────────────────────────────
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

    # ══════════════════════════════════════════════════════════════════════════
    # EVALUÁCIA 1: Stratified 5-Fold CV
    # ══════════════════════════════════════════════════════════════════════════
    print("Spúšťam RF Stratified 5-Fold cross-validáciu ...")
    y_true, y_pred, y_proba, rf_classes, rf_model, eer_threshold = run_rf_cv(X_raw, y)
    rf_acc     = float(np.mean(y_true == y_pred))
    g_rf, i_rf = rf_verification_scores(y_true, y_proba, rf_classes)
    m_rf       = compute_metrics(g_rf, i_rf)

    print_metrics_table(m_rf, rf_acc, meta, y_true, y_pred, csv_label,
                        eval_name="5-Fold CV")

    _print_demo(y_true, y_proba, rf_classes, eer_threshold, email_map,
                eval_name="5-Fold CV")

    # ══════════════════════════════════════════════════════════════════════════
    # EVALUÁCIA 2: Temporálna (chronologický split)
    # ══════════════════════════════════════════════════════════════════════════
    print("\nSpúšťam temporálnu evaluáciu (train=sub 2–11, test=sub 12–15) ...")
    t_true, t_pred, t_proba, t_classes, t_eer_thr, t_rf_model = run_temporal_eval(df, feature_cols)
    t_acc     = float(np.mean(t_true == t_pred))
    t_g, t_i  = rf_verification_scores(t_true, t_proba, t_classes)
    t_metrics = compute_metrics(t_g, t_i)

    print_metrics_table(t_metrics, t_acc, meta, t_true, t_pred, csv_label,
                        eval_name="Temporálna (train 2–11, test 12–15)")

    _print_demo(t_true, t_proba, t_classes, t_eer_thr, email_map,
                eval_name="Temporálna")

    # ══════════════════════════════════════════════════════════════════════════
    # VIZUALIZÁCIE – obe evaluácie + feature importance
    # ══════════════════════════════════════════════════════════════════════════
    print("\nGenerujem vizualizácie ...")

    # Figúry 1-2: 5-Fold CV (distribúcia skóre, violin, TAR/FAR/FRR, ROC, confusion)
    visualize_eval(m_rf, g_rf, i_rf, y_true, y_pred, y_proba, rf_classes,
                   meta, eval_name="5-Fold CV", csv_label=csv_label)

    # Figúry 3-4: Temporálna evaluácia (rovnaké grafy)
    visualize_eval(t_metrics, t_g, t_i, t_true, t_pred, t_proba, t_classes,
                   meta, eval_name="Temporálna (train 2–11, test 12–15)",
                   csv_label=csv_label)

    # Figúra 5: Feature importance – 5-Fold CV model
    plot_feature_importance(rf_model, feature_cols, csv_label,
                            title_suffix="(5-Fold CV model)")

    # Figúra 6: Feature importance – temporálny model (train sub 2–11)
    plot_feature_importance(t_rf_model, feature_cols, csv_label,
                            title_suffix="(temporálny model – train sub 2–11)")

    show_all()


if __name__ == "__main__":
    main()
