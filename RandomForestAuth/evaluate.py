"""
Behavica – Evaluácia behaviorálnej biometrie (Random Forest)
=============================================================

Čo tento skript robí:
  1. Načíta features CSV (výstup z extract_features.py).
  2. Spustí Stratified 5-Fold cross-validáciu s Random Forest.
  3. Vypočíta biometrické metriky: TAR, FAR, FRR, EER, AUC, Accuracy.
  4. Zobrazí prehľadné tabuľky a demo autentifikácie.
  5. Vygeneruje 3 figúry s grafmi.

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
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import confusion_matrix
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import warnings

# Potlačíme len nepodstatné sklearn varovania (FutureWarning, DeprecationWarning)
# UndefinedMetricWarning a iné dôležité varovania zostávajú viditeľné
warnings.filterwarnings("ignore", category=FutureWarning,      module="sklearn")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="sklearn")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="numpy")

DATA_DIR = Path(__file__).parent.parent / "BehavicaExport"


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

    Pre každý fold:
      – fituje StandardScaler IBA na tréningových dátach (bez data leakage)
      – natrénuje RF na škálovaných tréningových dátach
      – predikuje triedy a pravdepodobnosti pre testovaciu sadu (~20%)

    Na konci natrénuje finálny RF a scaler na VŠETKÝCH dátach
    (pre feature importance, demo autentifikáciu a export).

    Vracia:
      y_true      – skutočné triedy (userId) testovacích submissionov
      y_pred      – predikované triedy
      y_proba     – matica pravdepodobností [n_samples × n_classes]
      rf_classes  – poradie tried v y_proba
      rf          – finálny RF model (natrénovaný na všetkých dátach)
      scaler      – finálny scaler (natrénovaný na všetkých dátach)
    """
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    # 300 stromov, bez obmedzenia hĺbky
    rf  = RandomForestClassifier(n_estimators=300, max_depth=None,
                                 min_samples_leaf=1, random_state=42)

    y_true_list, y_pred_list, y_proba_list = [], [], []
    n_splits = skf.get_n_splits()
    correct  = 0
    total    = 0

    for fold_i, (train_idx, test_idx) in enumerate(skf.split(X_raw, y), start=1):
        X_tr_raw, X_te_raw = X_raw[train_idx], X_raw[test_idx]
        y_tr, y_te         = y[train_idx],     y[test_idx]

        # Scaler fitovaný IBA na tréningových dátach každého foldu → žiadny data leakage
        fold_scaler = StandardScaler()
        X_tr = fold_scaler.fit_transform(X_tr_raw)
        X_te = fold_scaler.transform(X_te_raw)

        rf.fit(X_tr, y_tr)
        preds  = rf.predict(X_te)
        probas = rf.predict_proba(X_te)

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

    # Finálny scaler a model natrénované na celých dátach
    # → slúžia pre feature importance, demo autentifikáciu a export
    final_scaler = StandardScaler()
    X_all = final_scaler.fit_transform(X_raw)
    rf.fit(X_all, y)

    return (np.array(y_true_list), np.array(y_pred_list),
            np.array(y_proba_list), rf.classes_, rf, final_scaler)


def rf_verification_scores(y_true, y_proba, rf_classes):
    """
    Konvertuje LOO/CV pravdepodobnosti RF na genuine a impostor skóre.

    Pre každý testovací submission od používateľa u:
      genuine score  = P(u)    – pravdepodobnosť, že RF zaradí submission správne
      impostor score = P(v≠u)  – pravdepodobnosti pre iné triedy
                                 (simulujeme: cudzí submission tvrdí, že je u)

    Celkovo: N genuine skóre (jedno na submission) + N×(K−1) impostor skóre.
    """
    genuine, impostor = [], []
    for yt, proba in zip(y_true, y_proba):
        cls_idx = int(np.where(rf_classes == yt)[0][0])
        genuine.append(proba[cls_idx])
        for j, c in enumerate(rf_classes):
            if c != yt:
                impostor.append(proba[j])
    return np.array(genuine), np.array(impostor)


# ══════════════════════════════════════════════════════════════════════════════
# 3. AUTENTIFIKÁCIA – POUŽITIE NA NOVÝ SUBMISSION
# ══════════════════════════════════════════════════════════════════════════════

def authenticate(raw_feature_vector: np.ndarray,
                 rf_model: RandomForestClassifier,
                 scaler: StandardScaler,
                 email_map: dict,
                 claimed_user_id=None) -> dict:
    """
    Autentifikuje jeden submission pomocou natrénovaného Random Forest modelu.

    Postup:
      1. Škáluje vstupný vektor pomocou natrénovaného scaleru.
      2. RF predikuje pravdepodobnosti pre každého používateľa.
      3. P(claimed_user) = skóre podobnosti pre verifikáciu.

    Parametre:
      raw_feature_vector  – 1D numpy pole príznakov (neškálovaných)
      rf_model            – natrénovaný RandomForestClassifier
      scaler              – natrénovaný StandardScaler (z tréningových dát)
      email_map           – slovník {userId: email} pre čitateľné výstupy
      claimed_user_id     – ak zadaný → verifikácia (1:1)
                            inak       → identifikácia (1:N)
    """
    x     = scaler.transform(raw_feature_vector.reshape(1, -1))
    proba = rf_model.predict_proba(x)[0]

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
        result.update({
            "claimed_user":   claimed_user_id,
            "claimed_email":  email_map.get(str(claimed_user_id), "?"),
            "score":          round(scores.get(str(claimed_user_id), 0.0), 4),
            "confidence_pct": pct.get(str(claimed_user_id), 0.0),
            # Akceptovaný = RF hovorí, že to je naozaj claimed_user
            "accepted":       best_user == str(claimed_user_id),
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


# ══════════════════════════════════════════════════════════════════════════════
# 4. VIZUALIZÁCIA
# ══════════════════════════════════════════════════════════════════════════════

COLORS = {
    "genuine":  "#2ecc71",   # zelená = správne príjatý
    "impostor": "#e74c3c",   # červená = útočník
    "rf":       "#9b59b6",   # fialová = Random Forest model
    "eer":      "#e67e22",   # oranžová = EER bod/prah
    "tar":      "#27ae60",   # tmavo zelená = TAR krivka
    "far":      "#c0392b",   # tmavo červená = FAR krivka
    "frr":      "#2980b9",   # modrá = FRR krivka
}


def _fig1_score_distributions(ax, g_rf, i_rf, m_rf):
    """
    Histogram genuine a impostor skóre Random Forest modelu.

    Ideálne: genuine skóre (zelená) vpravo, impostor skóre (červená) vľavo.
    Čím menší prekryv, tým lepší systém. EER prah (oranžová čiara)
    je optimálny bod, kde sa krivky skóre pretínajú.
    """
    bins = np.linspace(0, 1, 40)
    ax.hist(g_rf, bins=bins, alpha=0.65, color=COLORS["genuine"],
            label=f"Genuine  (n={len(g_rf)})",  density=True, edgecolor="white", lw=0.3)
    ax.hist(i_rf, bins=bins, alpha=0.65, color=COLORS["impostor"],
            label=f"Impostor (n={len(i_rf)})", density=True, edgecolor="white", lw=0.3)
    ax.axvline(m_rf["EER_threshold"], color=COLORS["eer"], lw=2.0, ls="--",
               label=f"EER prah = {m_rf['EER_threshold']:.3f}")
    ax.set_title("Random Forest verifikácia – distribúcia skóre", fontweight="bold")
    ax.set_xlabel("Skóre podobnosti  (0 = iný, 1 = rovnaký)")
    ax.set_ylabel("Hustota")
    ax.legend(fontsize=8)
    ax.set_xlim(0, 1)


def _fig2_tar_far_frr(ax, m_rf):
    """
    TAR, FAR a FRR krivky v závislosti od prahu (threshold sweep).

    Keď prah rastie (prísnejší systém):
      FAR klesá (menej falošných prijatí = bezpečnejšie)
      FRR rastie (viac falošných odmietnutí = menej pohodlné)
      TAR klesá (systém akceptuje menej genuínnych)
    EER = bod, kde FAR = FRR (kompromisný bod).
    """
    t = m_rf["thresholds"]
    ax.plot(t, m_rf["TAR"], color=COLORS["tar"], lw=2, label="TAR (True Accept Rate)")
    ax.plot(t, m_rf["FAR"], color=COLORS["far"], lw=2, label="FAR (False Accept Rate)")
    ax.plot(t, m_rf["FRR"], color=COLORS["frr"], lw=2, label="FRR (False Reject Rate)", ls="--")
    ax.axvline(m_rf["EER_threshold"], color=COLORS["eer"], lw=1.5, ls=":",
               label=f"EER = {m_rf['EER']*100:.1f}%  (prah={m_rf['EER_threshold']:.3f})")
    ax.set_title("Random Forest – TAR / FAR / FRR vs. prah", fontweight="bold")
    ax.set_xlabel("Prah rozhodovania")
    ax.set_ylabel("Miera  (0 – 1)")
    ax.legend(fontsize=7.5)
    ax.set_ylim(-0.02, 1.05)
    ax.set_xlim(t.min(), t.max())


def _fig3_roc(ax, m_rf):
    """
    ROC krivka – Random Forest.

    X-os: FAR (False Accept Rate) – koľko impostrov prenikne
    Y-os: TAR (True Accept Rate)  – koľko legitímnych používateľov prebehne

    Ideálna krivka: prechádza cez ľavý horný roh (FAR=0, TAR=1).
    AUC blízka 1.0 = výborný systém.
    """
    idx = np.argsort(m_rf["FAR"])
    ax.plot(m_rf["FAR"][idx], m_rf["TAR"][idx], color=COLORS["rf"], lw=2,
            label=f"Random Forest (AUC={m_rf['AUC']:.3f})")
    ax.plot(m_rf["EER"], 1 - m_rf["EER"], "o", color=COLORS["rf"], ms=9,
            label=f"EER = {m_rf['EER']*100:.1f}%")
    ax.plot([0, 1], [0, 1], "k--", lw=1, alpha=0.4, label="Náhodný klasifikátor (AUC=0.5)")
    ax.set_xlabel("FAR – False Accept Rate")
    ax.set_ylabel("TAR – True Accept Rate")
    ax.set_title("ROC krivka", fontweight="bold")
    ax.legend(fontsize=8)
    ax.set_xlim(-0.01, 1.01)
    ax.set_ylim(-0.01, 1.01)


def _fig4_confusion(ax, y_true, y_pred, classes, email_map):
    """
    Confusion matrix RF identifikácie (5-fold CV).

    Riadok = skutočný používateľ, stĺpec = predikovaný používateľ.
    Diagonála = správne identifikované submissiony (TA).
    Mimo diagonálu = chyby (zámenné identifikácie medzi používateľmi).
    """
    cm = confusion_matrix(y_true, y_pred, labels=classes)
    labels = [email_map.get(c, str(c)).split("@")[0] for c in classes]

    im = ax.imshow(cm, interpolation="nearest", cmap="Blues")
    ax.figure.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    ax.set(xticks=range(len(classes)), yticks=range(len(classes)),
           yticklabels=labels,
           ylabel="Skutočný používateľ", xlabel="Predikovaný používateľ")
    # X-axis labels rotované zhora-dole (vertikálne) aby sa neprekrývali
    ax.set_xticklabels(labels, rotation=90, ha="center", fontsize=8)
    ax.set_title("RF Confusion Matrix (5-Fold CV)", fontweight="bold")

    thresh = cm.max() / 2.0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, cm[i, j], ha="center", va="center",
                    color="white" if cm[i, j] > thresh else "black", fontsize=14)


def _fig5_feature_importance(ax, rf_model, feature_names):
    """
    Horizontálny bar chart VŠETKÝCH príznakov zoradených podľa RF Gini importance.

    Gini importance = priemerné zníženie nečistoty v strome → vyššia = príznak
    lepšie rozlišuje používateľov.

    Farby podľa zdrojového CSV:
      červená  → sensor_data.csv   (sd_*)
      modrá    → touch_points.csv  (tp_*)
      zelená   → keystrokes.csv    (ks_*)
      oranžová → submissions_basic.csv (drag*, textRewriteTime, ...)
    """
    importances = rf_model.feature_importances_
    idx         = np.argsort(importances)  # zoradiť vzostupne (pre barh)

    def feat_color(name):
        if name.startswith("sd_"):  return "#e74c3c"
        if name.startswith("tp_"):  return "#3498db"
        if name.startswith("ks_"):  return "#2ecc71"
        return "#f39c12"

    feat_labels = [feature_names[i] for i in idx]
    feat_vals   = [importances[i]   for i in idx]
    bar_colors  = [feat_color(n)    for n in feat_labels]

    bars = ax.barh(range(len(idx)), [v * 100 for v in feat_vals],
                   color=bar_colors, edgecolor="white")
    ax.set_yticks(range(len(idx)))
    ax.set_yticklabels(feat_labels, fontsize=7)

    # Číselná hodnota na konci každého baru v percentách
    xlim = ax.get_xlim()[1]
    for bar in bars:
        w = bar.get_width()
        ax.text(w + xlim * 0.005, bar.get_y() + bar.get_height() / 2,
                f"{w:.2f}%", va="center", ha="left", fontsize=6)

    ax.set_xlabel("Dôležitosť (%)")
    ax.set_title(f"Všetky príznaky ({len(idx)}) – RF Feature Importance",
                 fontweight="bold")

    from matplotlib.patches import Patch
    ax.legend(handles=[
        Patch(facecolor="#e74c3c", label="sensor_data.csv   (sd_*)"),
        Patch(facecolor="#3498db", label="touch_points.csv  (tp_*)"),
        Patch(facecolor="#2ecc71", label="keystrokes.csv    (ks_*)"),
        Patch(facecolor="#f39c12", label="submissions_basic.csv"),
    ], fontsize=7, loc="lower right")


def _fig6_per_user_scores(ax, y_true, y_proba, rf_classes, meta):
    """
    Box plot genuine vs. impostor skóre zvlášť pre každého používateľa (RF).

    Genuine skóre  = P(u) keď testovací submission naozaj patrí používateľovi u
    Impostor skóre = P(u) keď testovací submission patrí inému používateľovi

    Zelené boxy vpravo (vysoké skóre) a červené vľavo (nízke skóre) = dobrá separácia.
    """
    unique_users = rf_classes
    email_map    = dict(zip(meta["userId"], meta["email"]))
    labels       = [email_map.get(u, str(u)).split("@")[0] for u in unique_users]

    data_genuine  = []
    data_impostor = []
    for u in unique_users:
        u_idx = int(np.where(rf_classes == u)[0][0])
        genuine_mask  = y_true == u
        impostor_mask = y_true != u
        data_genuine.append(y_proba[genuine_mask,  u_idx])
        data_impostor.append(y_proba[impostor_mask, u_idx])

    positions_g = np.arange(len(unique_users)) * 2.5
    positions_i = positions_g + 0.9

    bp1 = ax.boxplot(data_genuine, positions=positions_g, widths=0.7,
                     patch_artist=True, medianprops={"color": "black", "lw": 2})
    for patch in bp1["boxes"]:
        patch.set_facecolor(COLORS["genuine"]); patch.set_alpha(0.75)

    bp2 = ax.boxplot(data_impostor, positions=positions_i, widths=0.7,
                     patch_artist=True, medianprops={"color": "black", "lw": 2})
    for patch in bp2["boxes"]:
        patch.set_facecolor(COLORS["impostor"]); patch.set_alpha(0.75)

    tick_pos = positions_g + 0.45
    ax.set_xticks(tick_pos)
    ax.set_xticklabels(labels, fontsize=7, rotation=90, ha="center")
    ax.set_ylabel("Skóre podobnosti")
    ax.set_title("Genuine vs. Impostor skóre per používateľ (RF)", fontweight="bold")

    from matplotlib.patches import Patch
    ax.legend(handles=[
        Patch(facecolor=COLORS["genuine"],  alpha=0.75, label="Genuine (vlastný submission)"),
        Patch(facecolor=COLORS["impostor"], alpha=0.75, label="Impostor (cudzí submission)"),
    ], fontsize=8)


def visualize_all(m_rf, g_rf, i_rf, y_true, y_pred, y_proba, rf_classes,
                  rf_model, feature_names, meta, csv_label: str = ""):
    """
    Vygeneruje 3 figúry:

    Figúra 1 – Verifikačné metriky (2×2):
      Distribúcia skóre | Per-user box plot
      TAR/FAR/FRR       | ROC krivka

    Figúra 2 – Confusion Matrix (samostatná)
    Figúra 3 – Feature Importance – VŠETKY príznaky (samostatná)
    """
    email_map = dict(zip(meta["userId"], meta["email"]))
    title_sfx = f"  [{csv_label}]" if csv_label else ""

    # ── Figúra 1: Verifikačné metriky ─────────────────────────────────────────
    fig1 = plt.figure(figsize=(16, 10))
    fig1.suptitle(f"Behavica – Biometrická verifikácia: Random Forest{title_sfx}",
                  fontsize=14, fontweight="bold", y=0.98)
    gs1 = gridspec.GridSpec(2, 2, figure=fig1, hspace=0.42, wspace=0.35)
    _fig1_score_distributions(fig1.add_subplot(gs1[0, 0]), g_rf, i_rf, m_rf)
    _fig6_per_user_scores(fig1.add_subplot(gs1[0, 1]), y_true, y_proba, rf_classes, meta)
    _fig2_tar_far_frr(fig1.add_subplot(gs1[1, 0]), m_rf)
    _fig3_roc(fig1.add_subplot(gs1[1, 1]), m_rf)

    # ── Figúra 2: Confusion Matrix ────────────────────────────────────────────
    n_users = len(rf_classes)
    fig2_h  = max(7, n_users * 0.45 + 2)
    fig2    = plt.figure(figsize=(max(9, n_users * 0.45 + 2), fig2_h))
    fig2.suptitle(f"Behavica – RF Confusion Matrix (5-Fold CV){title_sfx}",
                  fontsize=14, fontweight="bold", y=0.98)
    _fig4_confusion(fig2.add_subplot(1, 1, 1), y_true, y_pred, rf_classes, email_map)
    fig2.tight_layout(rect=[0, 0, 1, 0.96])

    # ── Figúra 3: Feature Importance ──────────────────────────────────────────
    n_feat = len(feature_names)
    fig3_h = max(8, n_feat * 0.28 + 2)
    fig3   = plt.figure(figsize=(10, fig3_h))
    fig3.suptitle(f"Behavica – RF Feature Importance{title_sfx}",
                  fontsize=14, fontweight="bold", y=0.98)
    _fig5_feature_importance(fig3.add_subplot(1, 1, 1), rf_model, feature_names)
    fig3.tight_layout(rect=[0, 0, 1, 0.96])

    plt.show()


# ══════════════════════════════════════════════════════════════════════════════
# 5. KONZOLOVÝ VÝPIS METRÍK
# ══════════════════════════════════════════════════════════════════════════════

def print_metrics_table(m_rf, rf_acc, meta, y_true, y_pred, csv_label: str = ""):
    """Vypíše prehľadnú tabuľku biometrických metrík do konzoly."""
    eer_idx   = int(np.argmin(np.abs(m_rf["FAR"] - m_rf["FRR"])))
    email_map = dict(zip(meta["userId"], meta["email"]))

    print("\n" + "═" * 56)
    print("   BEHAVICA – VÝSLEDKY BIOMETRICKEJ AUTENTIFIKÁCIE (RF)")
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
        ("Identifikačná Acc. (5-Fold CV)",   f"{rf_acc*100:.2f}%"),
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

    print(f"\n  Per-používateľ identifikácia (RF 5-Fold CV):")
    for u in np.unique(y_true):
        mask  = y_true == u
        acc_u = np.mean(y_pred[mask] == u)
        print(f"    {email_map.get(u, u):<40s}  "
              f"Acc: {acc_u*100:.1f}%  ({int(acc_u * mask.sum())}/{mask.sum()})")
    print("═" * 56)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    # ── Výber CSV súboru ───────────────────────────────────────────────────────
    script_dir = Path(__file__).parent

    if len(sys.argv) > 1:
        csv_path = Path(sys.argv[1])
        # Relatívna cesta → doplníme voči adresáru skriptu
        if not csv_path.is_absolute():
            csv_path = script_dir / csv_path
    else:
        # Ak nie je zadaný argument, zobrazíme dostupné CSV a pýtame sa
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

    # ── Načítanie metadát (emailové adresy pre výpisy) ─────────────────────────
    meta = pd.read_csv(DATA_DIR / "user_metadata.csv")

    # ── Stratified 5-Fold cross-validácia ─────────────────────────────────────
    print("Spúšťam RF Stratified 5-Fold cross-validáciu ...")
    y_true, y_pred, y_proba, rf_classes, rf_model, scaler = run_rf_cv(X_raw, y)
    rf_acc     = float(np.mean(y_true == y_pred))
    g_rf, i_rf = rf_verification_scores(y_true, y_proba, rf_classes)
    m_rf       = compute_metrics(g_rf, i_rf)

    # ── Výpis metrík ──────────────────────────────────────────────────────────
    print_metrics_table(m_rf, rf_acc, meta, y_true, y_pred, csv_label)

    # ── Demo autentifikácie ───────────────────────────────────────────────────
    # POZOR: Demo používa tréningové dáta a rf_model natrénovaný na celom datasete.
    # Výsledok NIE JE validný pre reálne hodnotenie – slúži len ako ukážka výstupu.
    # Pre skutočnú evaluáciu pozri 5-Fold CV výsledky vyššie.
    email_map = {str(k): v for k, v in zip(meta["userId"], meta["email"])}
    print("\n  DEMO: Verifikácia 1. dostupného submissnu každého používateľa")
    print("  (submission bol zahrnutý v tréningu – len ukážka výstupu)\n")
    for uid in np.unique(y):
        idx = np.where(df["userId"] == uid)[0]
        if len(idx) == 0:
            continue
        fvec = X_raw[idx[0]]
        res  = authenticate(fvec, rf_model, scaler, email_map, claimed_user_id=uid)
        print_auth_result(res)

    # ── Vizualizácia ──────────────────────────────────────────────────────────
    print("\nGenerujem vizualizácie ...")
    visualize_all(m_rf, g_rf, i_rf, y_true, y_pred, y_proba, rf_classes,
                  rf_model, feature_cols, meta, csv_label)


if __name__ == "__main__":
    main()
