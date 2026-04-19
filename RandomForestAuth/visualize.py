"""
Behavica – Vizualizácie biometrickej autentifikácie
=====================================================

Modul obsahuje všetky vizualizačné funkcie pre evaluate.py.
Generuje grafy pre ľubovoľnú evaluáciu (5-Fold CV aj temporálnu).

Funkcie:
  visualize_eval()        – 3 figúry pre jednu evaluáciu (distribúcia, metriky, confusion)
  plot_feature_importance() – feature importance z finálneho modelu (len raz, nie per eval)
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from sklearn.metrics import confusion_matrix


# ══════════════════════════════════════════════════════════════════════════════
# FARBY – konzistentné naprieč všetkými grafmi
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


# ══════════════════════════════════════════════════════════════════════════════
# JEDNOTLIVÉ SUBPLOT FUNKCIE
# ══════════════════════════════════════════════════════════════════════════════

def _plot_score_distributions(ax, genuine, impostor, metrics):
    """
    Histogram genuine a impostor skóre.

    Ideálne: genuine skóre (zelená) vpravo, impostor skóre (červená) vľavo.
    Čím menší prekryv, tým lepší systém. EER prah (oranžová čiara)
    je optimálny bod kde sa krivky pretínajú.
    """
    bins = np.linspace(0, 1, 40)
    ax.hist(genuine, bins=bins, alpha=0.65, color=COLORS["genuine"],
            label=f"Genuine  (n={len(genuine)})", density=True, edgecolor="white", lw=0.3)
    ax.hist(impostor, bins=bins, alpha=0.65, color=COLORS["impostor"],
            label=f"Impostor (n={len(impostor)})", density=True, edgecolor="white", lw=0.3)
    ax.axvline(metrics["EER_threshold"], color=COLORS["eer"], lw=2.0, ls="--",
               label=f"EER prah = {metrics['EER_threshold']:.3f}")
    ax.set_title("Distribúcia skóre", fontweight="bold")
    ax.set_xlabel("Skóre podobnosti  (0 = iný, 1 = rovnaký)")
    ax.set_ylabel("Hustota")
    ax.legend(fontsize=8)
    ax.set_xlim(0, 1)


def _plot_tar_far_frr(ax, metrics):
    """
    TAR, FAR a FRR krivky v závislosti od prahu.

    Keď prah rastie (prísnejší systém):
      FAR klesá (menej falošných prijatí = bezpečnejšie)
      FRR rastie (viac falošných odmietnutí = menej pohodlné)
      TAR klesá (systém akceptuje menej genuínnych)
    EER = bod kde FAR = FRR (kompromisný bod).
    """
    t = metrics["thresholds"]
    ax.plot(t, metrics["TAR"], color=COLORS["tar"], lw=2, label="TAR (True Accept Rate)")
    ax.plot(t, metrics["FAR"], color=COLORS["far"], lw=2, label="FAR (False Accept Rate)")
    ax.plot(t, metrics["FRR"], color=COLORS["frr"], lw=2, label="FRR (False Reject Rate)", ls="--")
    ax.axvline(metrics["EER_threshold"], color=COLORS["eer"], lw=1.5, ls=":",
               label=f"EER = {metrics['EER']*100:.2f}%  (prah={metrics['EER_threshold']:.3f})")
    ax.set_title("TAR / FAR / FRR vs. prah", fontweight="bold")
    ax.set_xlabel("Prah rozhodovania")
    ax.set_ylabel("Miera  (0 – 1)")
    ax.legend(fontsize=7.5)
    ax.set_ylim(-0.02, 1.05)
    ax.set_xlim(t.min(), t.max())


def _plot_roc(ax, metrics):
    """
    ROC krivka.

    X-os: FAR (koľko impostrov prenikne)
    Y-os: TAR (koľko legitímnych používateľov prebehne)
    Ideálna krivka: ľavý horný roh (FAR=0, TAR=1). AUC=1.0 = perfektný.
    """
    idx = np.argsort(metrics["FAR"])
    ax.plot(metrics["FAR"][idx], metrics["TAR"][idx], color=COLORS["rf"], lw=2,
            label=f"Random Forest (AUC={metrics['AUC']:.3f})")
    ax.plot(metrics["EER"], 1 - metrics["EER"], "o", color=COLORS["rf"], ms=9,
            label=f"EER = {metrics['EER']*100:.2f}%")
    ax.plot([0, 1], [0, 1], "k--", lw=1, alpha=0.4, label="Náhodný klasifikátor (AUC=0.5)")
    ax.set_xlabel("FAR – False Accept Rate")
    ax.set_ylabel("TAR – True Accept Rate")
    ax.set_title("ROC krivka", fontweight="bold")
    ax.legend(fontsize=8)
    ax.set_xlim(-0.01, 1.01)
    ax.set_ylim(-0.01, 1.01)


def _plot_confusion(ax, y_true, y_pred, classes, eval_name=""):
    """
    Confusion matrix identifikácie.

    Riadok = skutočný používateľ, stĺpec = predikovaný.
    Diagonála = správne, mimo = chyby.
    """
    cm = confusion_matrix(y_true, y_pred, labels=classes)
    labels = [str(c) for c in classes]

    im = ax.imshow(cm, interpolation="nearest", cmap="Blues")
    ax.figure.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    ax.set(xticks=range(len(classes)), yticks=range(len(classes)),
           ylabel="Skutočný používateľ", xlabel="Predikovaný používateľ")
    ax.set_yticklabels(labels, fontsize=7)
    ax.set_xticklabels(labels, rotation=90, ha="center", fontsize=7)
    title = f"Konfúzna matica ({eval_name})" if eval_name else "Konfúzna matica"
    ax.set_title(title, fontweight="bold")

    thresh = cm.max() / 2.0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, cm[i, j], ha="center", va="center",
                    color="white" if cm[i, j] > thresh else "black", fontsize=6)


def _plot_per_user_scores(ax, y_true, y_proba, rf_classes):
    """
    Violin plot genuine vs. impostor skóre pre každého používateľa.

    Genuine  = P(u) keď submission naozaj patrí u
    Impostor = P(u) keď submission patrí inému
    Tvar violin ukazuje hustotu rozdelenia skóre.
    """
    from matplotlib.patches import Patch

    unique_users = rf_classes
    labels       = [str(u) for u in unique_users]

    data_genuine  = []
    data_impostor = []
    for u in unique_users:
        u_idx = int(np.where(rf_classes == u)[0][0])
        data_genuine.append(y_proba[y_true == u, u_idx])
        data_impostor.append(y_proba[y_true != u, u_idx])

    positions_g = np.arange(len(unique_users)) * 2.5
    positions_i = positions_g + 0.9

    # Genuine violin (zelený)
    vp1 = ax.violinplot(data_genuine, positions=positions_g, widths=0.7,
                        showmeans=False, showmedians=True, showextrema=False)
    for body in vp1["bodies"]:
        body.set_facecolor(COLORS["genuine"])
        body.set_edgecolor(COLORS["genuine"])
        body.set_alpha(0.65)
    vp1["cmedians"].set_color("black")
    vp1["cmedians"].set_linewidth(2)

    # Impostor violin (červený)
    vp2 = ax.violinplot(data_impostor, positions=positions_i, widths=0.7,
                        showmeans=False, showmedians=True, showextrema=False)
    for body in vp2["bodies"]:
        body.set_facecolor(COLORS["impostor"])
        body.set_edgecolor(COLORS["impostor"])
        body.set_alpha(0.65)
    vp2["cmedians"].set_color("black")
    vp2["cmedians"].set_linewidth(2)

    tick_pos = positions_g + 0.45
    ax.set_xticks(tick_pos)
    ax.set_xticklabels(labels, fontsize=7, rotation=90, ha="center")
    ax.set_ylabel("Skóre podobnosti")
    ax.set_title("Genuine vs. Impostor skóre per používateľ", fontweight="bold")
    ax.legend(handles=[
        Patch(facecolor=COLORS["genuine"],  alpha=0.65, label="Genuine (vlastný submission)"),
        Patch(facecolor=COLORS["impostor"], alpha=0.65, label="Impostor (cudzí submission)"),
    ], fontsize=8)


# ══════════════════════════════════════════════════════════════════════════════
# HLAVNÉ FUNKCIE – volané z evaluate.py
# ══════════════════════════════════════════════════════════════════════════════

def visualize_eval(metrics, genuine, impostor,
                   y_true, y_pred, y_proba, rf_classes,
                   eval_name: str = "", csv_label: str = ""):
    """
    Vygeneruje 2 figúry pre jednu evaluáciu (5-Fold CV alebo temporálnu):

    Figúra 1 – Verifikačné metriky (2×2):
      Distribúcia skóre | Per-user violin plot
      TAR/FAR/FRR       | ROC krivka

    Figúra 2 – Konfúzna matica (samostatná)
    """
    title_sfx = f"  [{csv_label}]" if csv_label else ""

    # ── Figúra 1: Verifikačné metriky (2×2) ──────────────────────────────────
    fig1 = plt.figure(figsize=(16, 10))
    fig1.suptitle(f"Behavica – {eval_name}: Verifikačné metriky{title_sfx}",
                  fontsize=14, fontweight="bold", y=0.98)
    gs1 = gridspec.GridSpec(2, 2, figure=fig1, hspace=0.42, wspace=0.35)

    _plot_score_distributions(fig1.add_subplot(gs1[0, 0]), genuine, impostor, metrics)
    _plot_per_user_scores(fig1.add_subplot(gs1[0, 1]), y_true, y_proba, rf_classes)
    _plot_tar_far_frr(fig1.add_subplot(gs1[1, 0]), metrics)
    _plot_roc(fig1.add_subplot(gs1[1, 1]), metrics)

    # ── Figúra 2: Konfúzna matica ────────────────────────────────────────────
    n_users = len(rf_classes)
    fig2_size = max(10, n_users * 0.45 + 3)
    fig2    = plt.figure(figsize=(fig2_size, fig2_size))
    fig2.suptitle(f"Behavica – {eval_name}: Konfúzna matica{title_sfx}",
                  fontsize=14, fontweight="bold", y=0.99)
    ax2 = fig2.add_subplot(1, 1, 1)
    _plot_confusion(ax2, y_true, y_pred, rf_classes, eval_name)
    fig2.subplots_adjust(left=0.18, bottom=0.18, right=0.95, top=0.92)


def plot_feature_importance(rf_model, feature_names, csv_label: str = "",
                            title_suffix: str = ""):
    """
    Feature importance – horizontálny bar chart VŠETKÝCH príznakov.

    Gini importance = priemerné zníženie nečistoty v strome.
    Vyššia = príznak lepšie rozlišuje používateľov.

    Farby podľa zdrojového CSV:
      červená  → sensor_data.csv   (sd_*)
      modrá    → touch_points.csv  (tp_*)
      zelená   → keystrokes.csv    (ks_*)
      oranžová → submissions_basic.csv
    """
    from matplotlib.patches import Patch

    importances = rf_model.feature_importances_
    idx         = np.argsort(importances)

    def feat_color(name):
        if name.startswith("sd_"):  return "#e74c3c"
        if name.startswith("tp_"):  return "#3498db"
        if name.startswith("ks_"):  return "#2ecc71"
        return "#f39c12"

    feat_labels = [feature_names[i] for i in idx]
    feat_vals   = [importances[i]   for i in idx]
    bar_colors  = [feat_color(n)    for n in feat_labels]

    title_sfx = f"  [{csv_label}]" if csv_label else ""
    if title_suffix:
        title_sfx += f"  {title_suffix}"
    n_feat = len(feature_names)
    fig_h  = max(8, n_feat * 0.28 + 2)
    fig    = plt.figure(figsize=(10, fig_h))
    fig.suptitle(f"Behavica – Dôležitosť príznakov{title_sfx}",
                 fontsize=14, fontweight="bold", y=0.98)
    ax = fig.add_subplot(1, 1, 1)

    bars = ax.barh(range(len(idx)), [v * 100 for v in feat_vals],
                   color=bar_colors, edgecolor="white")
    ax.set_yticks(range(len(idx)))
    ax.set_yticklabels(feat_labels, fontsize=7)

    xlim = ax.get_xlim()[1]
    for bar in bars:
        w = bar.get_width()
        ax.text(w + xlim * 0.005, bar.get_y() + bar.get_height() / 2,
                f"{w:.2f}%", va="center", ha="left", fontsize=6)

    ax.set_xlabel("Dôležitosť (%)")
    ax.set_title(f"Všetky príznaky ({len(idx)}) – Dôležitosť príznakov",
                 fontweight="bold")
    ax.legend(handles=[
        Patch(facecolor="#e74c3c", label="Senzory (akcelerometer, gyroskop)"),
        Patch(facecolor="#3498db", label="Dotykové príznaky"),
        Patch(facecolor="#2ecc71", label="Klávesnicové príznaky"),
        Patch(facecolor="#f39c12", label="Základné metriky"),
    ], fontsize=8, loc="lower right")

    fig.tight_layout(rect=[0, 0, 1, 0.96])


def show_all():
    """Zobrazí všetky vygenerované figúry naraz."""
    plt.show()
