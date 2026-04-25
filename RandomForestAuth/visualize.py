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
    ax.set_title("Distribúcia skóre", fontweight="bold", fontsize=14)
    ax.set_xlabel("Skóre podobnosti  (0 = iný, 1 = rovnaký)", fontsize=12)
    ax.set_ylabel("Hustota", fontsize=12)
    ax.tick_params(axis="both", labelsize=11)
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
    ax.set_title("TAR / FAR / FRR vs. prah", fontweight="bold", fontsize=14)
    ax.set_xlabel("Prah rozhodovania", fontsize=12)
    ax.set_ylabel("Miera  (0 – 1)", fontsize=12)
    ax.tick_params(axis="both", labelsize=11)
    ax.legend(fontsize=8, loc="center right")
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
    ax.set_xlabel("FAR – False Accept Rate", fontsize=12)
    ax.set_ylabel("TAR – True Accept Rate", fontsize=12)
    ax.set_title("ROC krivka", fontweight="bold", fontsize=14)
    ax.tick_params(axis="both", labelsize=11)
    ax.legend(fontsize=8, loc="lower right")
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
    ax.set(xticks=range(len(classes)), yticks=range(len(classes)))
    ax.set_xlabel("Predikovaný používateľ", fontsize=13)
    ax.set_ylabel("Skutočný používateľ", fontsize=13)
    ax.set_yticklabels(labels, fontsize=10)
    ax.set_xticklabels(labels, rotation=90, ha="center", fontsize=10)
    title = f"Konfúzna matica ({eval_name})" if eval_name else "Konfúzna matica"
    ax.set_title(title, fontweight="bold", fontsize=15)

    thresh = cm.max() / 2.0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, cm[i, j], ha="center", va="center",
                    color="white" if cm[i, j] > thresh else "black",
                    fontsize=11, fontweight="bold")


def _plot_per_user_scores(ax, y_true, y_proba, rf_classes, eer_threshold=None):
    """
    Violin plot genuine vs. impostor skóre pre každého používateľa.

    Genuine  = P(u) keď submission naozaj patrí u
    Impostor = P(u) keď submission patrí inému
    Tvar violin ukazuje hustotu rozdelenia skóre.

    Ak je zadaný eer_threshold, zobrazí sa ako vodorovná čiara
    – pre každého usera vidno aké % zeleného violinu je nad prahom (TAR)
      a aké % červeného je pod prahom (TRR).
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
    ax.set_xticklabels(labels, fontsize=10, rotation=90, ha="center")
    ax.tick_params(axis="y", labelsize=11)
    ax.set_ylabel("Skóre podobnosti", fontsize=12)
    ax.set_title("Skóre genuine vs. impostor pre jednotlivých používateľov",
                 fontweight="bold", fontsize=14)

    legend_handles = [
        Patch(facecolor=COLORS["genuine"],  alpha=0.65, label="Genuine (vlastný submission)"),
        Patch(facecolor=COLORS["impostor"], alpha=0.65, label="Impostor (cudzí submission)"),
    ]
    if eer_threshold is not None:
        thr_line = ax.axhline(eer_threshold, color=COLORS["eer"], lw=1.8, ls="--",
                              label=f"EER prah = {eer_threshold*100:.2f} %")
        legend_handles.append(thr_line)
    ax.legend(handles=legend_handles, fontsize=8, loc="upper left")


def _plot_per_user_rank_distribution(ax, y_true, y_proba, rf_classes, eer_threshold):
    """
    Per-submission rank scatter – Y-os = rank skutočného usera (1 hore, N dole),
    submissiony zoskupené podľa skutočného usera (ticky 36 userov pod osou X).

    Markery rozlišujú rozhodnutie pri EER prahu:
      ● zelený bod  = rank 1 + akceptovaný (ideál)
      ▽ oranžový ▽  = rank 1, ale skóre pod prahom (False Reject)
      ✗ červený ✗   = rank > 1 (misidentifikácia)
    """
    order     = np.argsort(y_true)
    y_true_s  = np.array(y_true)[order]
    y_proba_s = y_proba[order]

    n_users  = len(rf_classes)
    ranks    = []
    accepted = []
    for i, true_cls in enumerate(y_true_s):
        true_idx = int(np.where(rf_classes == true_cls)[0][0])
        g_score  = y_proba_s[i, true_idx]
        rank     = 1 + int(np.sum(y_proba_s[i] > g_score))
        ranks.append(rank)
        accepted.append(g_score >= eer_threshold)

    ranks    = np.array(ranks)
    accepted = np.array(accepted)
    x        = np.arange(len(ranks))

    ok_mask  = (ranks == 1) & accepted
    fr_mask  = (ranks == 1) & ~accepted
    bad_mask = ranks > 1

    ax.scatter(x[ok_mask],  ranks[ok_mask],  s=22, color=COLORS["genuine"],
               label=f"Rank 1 + akceptovaný ({int(ok_mask.sum())})", zorder=3)
    ax.scatter(x[fr_mask],  ranks[fr_mask],  s=30, color=COLORS["eer"],
               marker="v",
               label=f"Rank 1, ale pod prahom ({int(fr_mask.sum())})", zorder=4)
    ax.scatter(x[bad_mask], ranks[bad_mask], s=36, color=COLORS["impostor"],
               marker="x",
               label=f"Misidentifikácia – rank > 1 ({int(bad_mask.sum())})", zorder=5)

    ax.axhline(1, color=COLORS["genuine"], ls="--", lw=1.2, alpha=0.5,
               label="Ideál = rank 1")

    boundaries = np.where(np.diff(y_true_s) != 0)[0] + 0.5
    for b in boundaries:
        ax.axvline(b, color="lightgray", lw=0.4, alpha=0.6, zorder=0)

    unique_users, first_idx = np.unique(y_true_s, return_index=True)
    counts  = np.array([np.sum(y_true_s == u) for u in unique_users])
    centers = first_idx + counts / 2 - 0.5

    ax.set_xticks(centers)
    ax.set_xticklabels([str(u) for u in unique_users], rotation=90, fontsize=10)
    ax.tick_params(axis="y", labelsize=11)
    ax.set_xlim(-1, len(x))
    ax.set_ylim(n_users + 0.5, 0.5)
    ax.set_xlabel("Testovací submission (zoskupené podľa skutočného usera)", fontsize=12)
    ax.set_ylabel(f"Rank skutočného usera  (1 = najlepší, {n_users} = najhorší)", fontsize=12)
    mean_rank = ranks.mean()
    ax.set_title(f"Per-user rank pri EER prahu ({eer_threshold*100:.2f} %) – "
                 f"priemer {mean_rank:.2f}, {int((ranks==1).sum())}/{len(ranks)} s rank 1",
                 fontweight="bold", fontsize=14)
    ax.legend(fontsize=10, loc="lower right")


# ══════════════════════════════════════════════════════════════════════════════
# HLAVNÉ FUNKCIE – volané z evaluate.py
# ══════════════════════════════════════════════════════════════════════════════

def visualize_eval(metrics, genuine, impostor,
                   y_true, y_pred, y_proba, rf_classes,
                   eval_name: str = "", csv_label: str = ""):
    """
    Vygeneruje 3 figúry pre jednu evaluáciu (5-Fold CV alebo temporálnu):

    Figúra 1 – Verifikačné metriky (2×2):
      Distribúcia skóre | Per-user violin plot
      TAR/FAR/FRR       | ROC krivka

    Figúra 2 – Konfúzna matica (samostatná)

    Figúra 3 – Per-user rank pri EER prahu (Y-os = rank, zoskupené po useroch)
    """
    title_sfx     = f"  [{csv_label}]" if csv_label else ""
    eer_threshold = metrics["EER_threshold"]

    # ── Figúra 1: Verifikačné metriky (2×2) ──────────────────────────────────
    fig1 = plt.figure(figsize=(16, 10))
    fig1.suptitle(f"Behavica – {eval_name}: Verifikačné metriky{title_sfx}",
                  fontsize=16, fontweight="bold", y=0.98)
    gs1 = gridspec.GridSpec(2, 2, figure=fig1, hspace=0.42, wspace=0.35)

    _plot_score_distributions(fig1.add_subplot(gs1[0, 0]), genuine, impostor, metrics)
    _plot_per_user_scores(fig1.add_subplot(gs1[0, 1]), y_true, y_proba, rf_classes, eer_threshold)
    _plot_tar_far_frr(fig1.add_subplot(gs1[1, 0]), metrics)
    _plot_roc(fig1.add_subplot(gs1[1, 1]), metrics)

    # ── Figúra 2: Konfúzna matica ────────────────────────────────────────────
    n_users = len(rf_classes)
    fig2_size = max(10, n_users * 0.45 + 3)
    fig2    = plt.figure(figsize=(fig2_size, fig2_size))
    fig2.suptitle(f"Behavica – {eval_name}: Konfúzna matica{title_sfx}",
                  fontsize=16, fontweight="bold", y=0.99)
    ax2 = fig2.add_subplot(1, 1, 1)
    _plot_confusion(ax2, y_true, y_pred, rf_classes, eval_name)
    fig2.subplots_adjust(left=0.18, bottom=0.18, right=0.95, top=0.92)

    # ── Figúra 3: Per-user rank scatter ──────────────────────────────────────
    fig3 = plt.figure(figsize=(max(14, len(y_true) * 0.035 + 4), 6))
    fig3.suptitle(f"Behavica – {eval_name}: Per-user rank{title_sfx}",
                  fontsize=16, fontweight="bold", y=0.98)
    ax3 = fig3.add_subplot(1, 1, 1)
    _plot_per_user_rank_distribution(ax3, y_true, y_proba, rf_classes, eer_threshold)
    fig3.tight_layout(rect=[0, 0, 1, 0.94])


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
    ax.set_yticklabels(feat_labels, fontsize=10)
    ax.tick_params(axis="x", labelsize=11)

    xlim = ax.get_xlim()[1]
    for bar in bars:
        w = bar.get_width()
        ax.text(w + xlim * 0.005, bar.get_y() + bar.get_height() / 2,
                f"{w:.2f}%", va="center", ha="left", fontsize=9)

    ax.set_xlabel("Dôležitosť (%)", fontsize=12)
    ax.set_title(f"Všetky príznaky ({len(idx)}) – Dôležitosť príznakov",
                 fontweight="bold", fontsize=14)
    ax.legend(handles=[
        Patch(facecolor="#e74c3c", label="Senzory (akcelerometer, gyroskop)"),
        Patch(facecolor="#3498db", label="Dotykové príznaky"),
        Patch(facecolor="#2ecc71", label="Klávesnicové príznaky"),
        Patch(facecolor="#f39c12", label="Základné metriky"),
    ], fontsize=11, loc="lower right")

    fig.tight_layout(rect=[0, 0, 1, 0.96])


def show_all():
    """Zobrazí všetky vygenerované figúry naraz."""
    plt.show()
