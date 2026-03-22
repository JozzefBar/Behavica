"""
Behavica Behavioral Biometric Authenticator
============================================

Čo tento skript robí:
  1. Načíta dáta z 5 CSV súborov (submissions_basic, touch_points,
     keystrokes, sensor_data, user_metadata).
  2. Extrahuje príznaky (features) z každého záznamu (submission).
  3. Natrénuje a vyhodnotí Random Forest klasifikátor (LOO-CV):
       – identifikácia: určí, ktorý z N používateľov submission vytvoril
       – verifikácia: P(claimed_user) sa použije ako skóre podobnosti
  4. Vypočíta biometrické metriky: TAR, FAR, FRR, EER, Accuracy, AUC.
  5. Ukáže demo autentifikácie každého používateľa.
  6. Zobrazí komplexnú vizualizáciu výsledkov (2 figúry, 6 grafov).

Ako spustiť:
  pip install -r requirements.txt
  python authenticator.py
"""

import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import LeaveOneOut
from sklearn.metrics import confusion_matrix
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import warnings

# Potlačíme len nepodstatné sklearn varovania (FutureWarning, DeprecationWarning)
# UndefinedMetricWarning a iné dôležité varovania zostávajú viditeľné
warnings.filterwarnings("ignore", category=FutureWarning, module="sklearn")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="sklearn")

# Cesta k priečinku s CSV súbormi – automaticky sa odvodí od umiestnenia
# tohto skriptu (RandomForestAuth/../BehavicaExport)
DATA_DIR = Path(__file__).parent.parent / "BehavicaExport"


# ══════════════════════════════════════════════════════════════════════════════
# 1. NAČÍTANIE DÁT
# ══════════════════════════════════════════════════════════════════════════════

def load_all():
    """Načíta všetkých 5 CSV súborov a vráti ich ako pandas DataFrame."""
    basic = pd.read_csv(DATA_DIR / "submissions_basic.csv")   # agregované metriky
    tp    = pd.read_csv(DATA_DIR / "touch_points.csv")        # surové dotykové body
    ks    = pd.read_csv(DATA_DIR / "keystrokes.csv")          # klávesnicové udalosti
    sd    = pd.read_csv(DATA_DIR / "sensor_data.csv")         # akcelerometer + gyroskop
    meta  = pd.read_csv(DATA_DIR / "user_metadata.csv")       # info o používateľoch
    return basic, tp, ks, sd, meta


# ══════════════════════════════════════════════════════════════════════════════
# 2. EXTRAKCIA PRÍZNAKOV
# ══════════════════════════════════════════════════════════════════════════════
#
# Každý "submission" (jedno opakovanie) musíme opísať číselným vektorom.
# Z každého CSV vypočítame štatistiky (priemer, smerodajná odchýlka, ...)
# a spojíme ich do jedného riadku → feature vektor per submission.
#
# Skupiny príznakov:
#   – základné metriky  (submissions_basic.csv) : 10 príznakov
#   – touch príznaky    (touch_points.csv)       : 19 príznakov
#   – keystroke príznaky(keystrokes.csv)         : 13 príznakov
#   – senzorové príznaky(sensor_data.csv)        : 22 príznakov
#   ────────────────────────────────────────────
#   SPOLU                                        : ~64 príznakov
# ══════════════════════════════════════════════════════════════════════════════

def _std(s):
    """Bezpečná smerodajná odchýlka – vráti 0 ak je len 1 prvok (nedá sa počítať)."""
    return float(s.std()) if len(s) > 1 else 0.0


def extract_touch_features(tp: pd.DataFrame) -> pd.DataFrame:
    """
    Extrahuje per-submission príznaky zo surových dotykových bodov.

    Každý riadok v touch_points.csv je jedna udalosť dotyku:
      – ACTION_DOWN  ... prst sa dotkol obrazovky
      – ACTION_MOVE  ... prst sa pohybuje po obrazovke
      – ACTION_UP    ... prst sa zdvihol

    Čo vypočítame:
      • Tlak (pressure) a veľkosť dotyku (size, touchMajor, touchMinor)
        → opisujú fyzické vlastnosti dotyku prsta; každý človek tlačí inak.
      • Rýchlosť pohybu (velocity) počas dragu
        → ako rýchlo používateľ presúva prst pri drag & drop teste.
      • Celková rýchlosť pohybu (všetky MOVE udalosti)
        → zahŕňa aj písanie na klávesnici (pohyb po obrazovke).
      • Inter-touch interval (ITI)
        → čas medzi po sebe idúcimi dotykmi; tempo interakcie.
      • Pokrytá plocha (x_range, y_range)
        → aká veľká časť obrazovky bola využívaná.
      • Počet stlačení (ACTION_DOWN count)
        → celkový počet kliknutí / klepnutí v jednom opakovaní.
    """
    rows = []
    # Spracovávame každý submission samostatne (každú skupinu userId + submissionNumber)
    for (uid, sub), g in tp.groupby(["userId", "submissionNumber"]):
        g = g.sort_values("timestamp")  # zoradíme chronologicky

        p     = g["pressure"]
        s_col = g["size"]

        # ── Rýchlosť dragu: len ACTION_MOVE udalosti v cieli "dragTest"
        drag_move = g[(g["action"] == "ACTION_MOVE") & (g["target"] == "dragTest")].copy()
        vels = []
        if len(drag_move) > 1:
            drag_move = drag_move.sort_values("timestamp")
            dx = drag_move["x"].diff()           # zmena polohy X (pixely)
            dy = drag_move["y"].diff()           # zmena polohy Y (pixely)
            dt = drag_move["timestamp"].diff() / 1000.0  # čas v sekundách
            dt = dt.replace(0, np.nan)           # vyhnutie sa deleniu nulou
            v  = np.sqrt(dx**2 + dy**2) / dt    # rýchlosť = vzdialenosť / čas
            vels = v.dropna().values

        # ── # ── Celková rýchlosť pohybu (všetky dotykové udalosti v appke)
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

        # ── Inter-touch interval: čas medzi po sebe idúcimi udalosťami
        dts = g["timestamp"].diff().dropna().values
        # Odfiltrujeme záporné hodnoty a prílišne dlhé pauzy (> 5 sekúnd)
        dts = dts[(dts > 0) & (dts < 5000)]

        # ── Tvar dotyku: pomer dlhšej a kratšej osi elipsy dotyku prsta
        # Hodnota blízka 1 = okrúhly dotyk, > 1 = elipsovitý (šikmý prst)
        ratio = (g["touchMajor"] / g["touchMinor"].replace(0, np.nan)).dropna()

        rows.append({
            "userId": uid, "submissionNumber": sub,
            # — Tlak
            "tp_pressure_mean":        float(p.mean()),
            "tp_pressure_std":         _std(p),
            # — Veľkosť dotyku
            "tp_size_mean":            float(s_col.mean()),
            "tp_size_std":             _std(s_col),
            "tp_touchMajor_mean":      float(g["touchMajor"].mean()),
            "tp_touchMajor_std":       _std(g["touchMajor"]),
            "tp_touchMinor_mean":      float(g["touchMinor"].mean()),
            "tp_touchMinor_std":       _std(g["touchMinor"]),
            "tp_touch_shape_ratio":    float(ratio.mean()) if len(ratio) else 1.0,
            # — Rýchlosť dragu
            "tp_drag_vel_mean":        float(np.mean(vels))   if len(vels) else 0.0,
            "tp_drag_vel_std":         float(np.std(vels))    if len(vels) else 0.0,
            "tp_drag_vel_max":         float(np.max(vels))    if len(vels) else 0.0,
            # — Celková rýchlosť pohybu (vrátane písania)
            "tp_all_vel_mean":         float(np.mean(all_vels)) if len(all_vels) else 0.0,
            "tp_all_vel_std":          float(np.std(all_vels))  if len(all_vels) else 0.0,
            # — Inter-touch interval
            "tp_iti_mean":             float(np.mean(dts)) if len(dts) else 0.0,
            "tp_iti_std":              float(np.std(dts))  if len(dts) else 0.0,
            # — Pokrytá plocha obrazovky
            "tp_x_range":              float(g["x"].max() - g["x"].min()),
            "tp_y_range":              float(g["y"].max() - g["y"].min()),
            # — Počet stlačení
            "tp_down_count":           int((g["action"] == "ACTION_DOWN").sum()),
        })
    return pd.DataFrame(rows)


def extract_keystroke_features(ks: pd.DataFrame) -> pd.DataFrame:
    """
    Extrahuje per-submission príznaky z klávesnicových udalostí.

    Každý riadok v keystrokes.csv je jedno stlačenie klávesu:
      type = "insert" ... napísanie znaku
      type = "delete" ... zmazanie znaku (Backspace)
      count > 1       ... viacero znakov naraz (autocomplete / paste)

    Čo vypočítame:
      • Inter-Key Interval (IKI) – čas medzi po sebe idúcimi stlačeniami
        → najdôležitejší biometrický príznak pri písaní; každý človek píše
          vlastným rytmom (rýchlo / pomaly, s pauzami medzi slovami atď.).
      • Pomer mazania (delete ratio)
        → ako často robí používateľ chyby a maže; odráža presnosť písania.
      • Autocomplete / paste detekcia
        → ak count > 1 pri insert udalosti, používateľ vložil viacero znakov
          naraz (napoveda klávesnice, kopírovanie) – dôležité pre behaviorálny profil.
      • Čas na každé slovo
        → rozdiel medzi prvým a posledným keystrokom v rámci slova "internet",
          "wifi", "laptop"; každý používateľ ich píše inak rýchlo.
    """
    rows = []
    for (uid, sub), g in ks.groupby(["userId", "submissionNumber"]):
        g = g.sort_values("timestamp")

        inserts = g[g["type"] == "insert"]
        deletes = g[g["type"] == "delete"]
        total   = len(g)

        # ── Inter-key interval (IKI)
        # Čas medzi po sebe idúcimi klávesnicovými udalosťami v ms
        iki = g["timestamp"].diff().dropna().values
        # Odfiltrujeme nerealistické hodnoty (< 0 ms a > 10 sekúnd)
        iki = iki[(iki > 0) & (iki < 10_000)]

        # ── Čas per slovo: čas od prvého do posledného keystroke v danom slove
        word_times = {}
        for word, wg in g.groupby("word"):
            wg = wg.sort_values("timestamp")
            if len(wg) > 1:
                # Trvanie písania jedného slova v milisekundách
                word_times[word] = wg["timestamp"].iloc[-1] - wg["timestamp"].iloc[0]

        # ── Autocomplete / paste detekcia
        # count = koľko znakov bolo vložených naraz; > 1 znamená nie ručné písanie
        auto_count = int((inserts["count"] > 1).sum()) if len(inserts) else 0

        rows.append({
            "userId": uid, "submissionNumber": sub,
            "ks_total_events":    total,
            "ks_insert_count":    len(inserts),
            "ks_delete_count":    len(deletes),
            # Pomer zmazaní voči všetkým udalostiam → miera chybovosti
            "ks_delete_ratio":    len(deletes) / max(total, 1),
            "ks_auto_count":      auto_count,
            # Inter-key interval (kľúčový biometrický príznak písania)
            "ks_iki_mean":        float(np.mean(iki)) if len(iki) else 0.0,
            "ks_iki_std":         float(np.std(iki))  if len(iki) else 0.0,
            "ks_iki_min":         float(np.min(iki))  if len(iki) else 0.0,
            "ks_iki_max":         float(np.max(iki))  if len(iki) else 0.0,
            # Kvartilyy IKI – zachytávajú tvar rozdelenia rýchlosti písania
            "ks_iki_q25":         float(np.percentile(iki, 25)) if len(iki) else 0.0,
            "ks_iki_q75":         float(np.percentile(iki, 75)) if len(iki) else 0.0,
            # Čas per slovo (internet, wifi, laptop)
            "ks_word_time_mean":  float(np.mean(list(word_times.values()))) if word_times else 0.0,
            "ks_word_time_std":   float(np.std(list(word_times.values())))  if word_times else 0.0,
        })
    return pd.DataFrame(rows)


def extract_sensor_features(sd: pd.DataFrame) -> pd.DataFrame:
    """
    Extrahuje per-submission štatistiky zo senzorov telefónu.

    Akcelerometer (accelX/Y/Z):
      – meria zrýchlenie zariadenia vrátane gravitácie (m/s²)
      – odráža, ako používateľ drží telefón a ako s ním pohybuje
      – os Z typicky dominuje (gravitácia ≈ 9.8 m/s² pri zvislom telefóne)

    Gyroskop (gyroX/Y/Z):
      – meria uhlové zrýchlenie (rad/s) – rotáciu telefónu
      – veľmi citlivý na chvenie ruky a spôsob ovládania

    Vypočítame:
      • mean, std, range pre každú os → celkom 18 príznakov
      • magnitudy vektorov (sqrt(X² + Y² + Z²)) → 4 príznaky
        (amplitúda pohybu bez ohľadu na orientáciu telefónu)
    """
    rows = []
    for (uid, sub), g in sd.groupby(["userId", "submissionNumber"]):
        # Magnitúda akcelerometra – celková "sila" pohybu v 3D priestore
        accel_mag = np.sqrt(g["accelX"]**2 + g["accelY"]**2 + g["accelZ"]**2)
        # Magnitúda gyroskopu – celková "sila" rotácie v 3D priestore
        gyro_mag  = np.sqrt(g["gyroX"]**2  + g["gyroY"]**2  + g["gyroZ"]**2)

        rows.append({
            "userId": uid, "submissionNumber": sub,
            # — Akcelerometer: každá os zvlášť (mean, std, rozsah)
            "sd_accelX_mean":  float(g["accelX"].mean()),
            "sd_accelX_std":   _std(g["accelX"]),
            "sd_accelX_range": float(g["accelX"].max() - g["accelX"].min()),
            "sd_accelY_mean":  float(g["accelY"].mean()),
            "sd_accelY_std":   _std(g["accelY"]),
            "sd_accelY_range": float(g["accelY"].max() - g["accelY"].min()),
            "sd_accelZ_mean":  float(g["accelZ"].mean()),
            "sd_accelZ_std":   _std(g["accelZ"]),
            "sd_accelZ_range": float(g["accelZ"].max() - g["accelZ"].min()),
            # — Gyroskop: každá os zvlášť (mean, std, rozsah)
            "sd_gyroX_mean":   float(g["gyroX"].mean()),
            "sd_gyroX_std":    _std(g["gyroX"]),
            "sd_gyroX_range":  float(g["gyroX"].max() - g["gyroX"].min()),
            "sd_gyroY_mean":   float(g["gyroY"].mean()),
            "sd_gyroY_std":    _std(g["gyroY"]),
            "sd_gyroY_range":  float(g["gyroY"].max() - g["gyroY"].min()),
            "sd_gyroZ_mean":   float(g["gyroZ"].mean()),
            "sd_gyroZ_std":    _std(g["gyroZ"]),
            "sd_gyroZ_range":  float(g["gyroZ"].max() - g["gyroZ"].min()),
            # — 3D magnitudy (orientačne nezávislé)
            "sd_accel_mag_mean": float(accel_mag.mean()),
            "sd_accel_mag_std":  _std(accel_mag),
            "sd_gyro_mag_mean":  float(gyro_mag.mean()),
            "sd_gyro_mag_std":   _std(gyro_mag),
        })
    return pd.DataFrame(rows)


def build_feature_matrix(basic, tp_feat, ks_feat, sd_feat) -> pd.DataFrame:
    """
    Spojí všetky feature tabuľky do jedného riadku per (userId, submissionNumber).

    Z submissions_basic vezmeme priamo tieto agregované metriky:
      submissionDurationSec – celkové trvanie záznamu
      dragAttempts          – počet pokusov pre drag test
      dragDistance          – presnosť dotiahnutia (vzdialenosť stredu A od B)
      dragPathLength        – celková prejdená vzdialenosť pri dragu (px)
      dragDurationSec       – trvanie dragu
      textRewriteTime       – celkový čas prepisovania textu
      averageWordTime       – priemerný čas na jedno slovo
      textEditCount         – počet editácií (18 = žiadne chyby)
      touchPointsCount      – celkový počet dotykových bodov
      sensorDataCount       – celkový počet senzorových meraní
    """
    basic_cols = [
        "userId", "submissionNumber",
        "submissionDurationSec", "dragAttempts", "dragDistance",
        "dragPathLength", "dragDurationSec", "textRewriteTime",
        "averageWordTime", "textEditCount", "touchPointsCount", "sensorDataCount",
    ]
    df = basic[basic_cols].copy()
    # Pripojiť touch, keystroke a senzorové príznaky (join cez userId + submissionNumber)
    for feat_df in [tp_feat, ks_feat, sd_feat]:
        df = df.merge(feat_df, on=["userId", "submissionNumber"], how="left")
    # Doplniť prípadné NaN nulami (niektoré submissiony nemusia mať všetky typy záznamov)
    df = df.fillna(0.0)
    return df


# ══════════════════════════════════════════════════════════════════════════════
# 3. RANDOM FOREST – VERIFIKAČNÉ SKÓRE (LOO-CV)
# ══════════════════════════════════════════════════════════════════════════════
#
# Genuine skóre = P(true_user) z RF pre vlastný submission (LOO-CV)
# Impostor skóre = P(target_user) z RF pre cudzí submission
# → čím vyššie genuine skóre a nižšie impostor skóre, tým lepší model
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
# 4. VÝPOČET BIOMETRICKÝCH METRÍK
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
    Sweepuje cez prahy od min do max skóre a pri každom prahu vypočíta
    TAR, FAR a FRR. Potom nájde EER (kde FAR ≈ FRR).

    Logika prahového rozhodovania:
      – ak score >= prah → AKCEPTUJ (systém si myslí, že to je správny používateľ)
      – ak score <  prah → ODMIETNI

    Výstup je slovník obsahujúci polia pre každý prah aj súhrnné metriky.
    """
    all_scores = np.concatenate([genuine_scores, impostor_scores])
    # 1000 rovnomerne rozdelených prahov medzi minimálnym a maximálnym skóre
    thresholds = np.linspace(all_scores.min(), all_scores.max(), 1000)

    tars, fars, frrs = [], [], []

    for t in thresholds:
        # Počet prípadov pre každú kategóriu
        TA = np.sum(genuine_scores  >= t)   # genuine  akceptovaný → správne
        FR = np.sum(genuine_scores  <  t)   # genuine  odmietnutý  → chyba
        FA = np.sum(impostor_scores >= t)   # impostor akceptovaný → chyba (bezpečnostné riziko!)
        TR = np.sum(impostor_scores <  t)   # impostor odmietnutý  → správne

        # Výpočet metrík (ošetrenie delenia nulou)
        TAR = TA / (TA + FR) if (TA + FR) > 0 else 0.0
        FAR = FA / (FA + TR) if (FA + TR) > 0 else 0.0
        FRR = FR / (TA + FR) if (TA + FR) > 0 else 0.0

        tars.append(TAR)
        fars.append(FAR)
        frrs.append(FRR)

    tars  = np.array(tars)
    fars  = np.array(fars)
    frrs  = np.array(frrs)

    # ── EER: prah, kde je absolútny rozdiel |FAR - FRR| minimálny
    eer_idx = int(np.argmin(np.abs(fars - frrs)))
    # EER = priemer FAR a FRR v tomto bode (lepšia aproximácia ako len jedna hodnota)
    eer     = float((fars[eer_idx] + frrs[eer_idx]) / 2.0)
    eer_thr = float(thresholds[eer_idx])

    # ── AUC: plocha pod ROC krivkou (FAR na x-osi, TAR na y-osi)
    sorted_idx = np.argsort(fars)
    auc = float(np.trapz(tars[sorted_idx], fars[sorted_idx]))

    # ── Accuracy pri EER prahu
    t  = eer_thr
    TA = int(np.sum(genuine_scores  >= t))
    FR = int(np.sum(genuine_scores  <  t))
    FA = int(np.sum(impostor_scores >= t))
    TR = int(np.sum(impostor_scores <  t))
    accuracy = (TA + TR) / (TA + FR + FA + TR)

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
# 5. RANDOM FOREST – IDENTIFIKÁCIA (LOO-CV)
# ══════════════════════════════════════════════════════════════════════════════
#
# Random Forest je súbor rozhodovacích stromov, kde každý strom hlasuje
# o triede (používateľovi). Výstupom je vektor pravdepodobností [P(u1), P(u2), ...].
#
# Identifikácia (1:N) = "Kto z N používateľov to je?" → argmax(P)
# Verifikácia  (1:1)  = "Je to naozaj používateľ X?"  → P(X) vs. prah
#
# LOO-CV s RF:
#   – N submissionov celkovo (K používateľov × počet submissionov každého)
#   – v každom fold: N−1 tréning, 1 test → N foldov celkovo
#   – záverečný RF model (natrénovaný na všetkých N) slúži pre feature importance
# ══════════════════════════════════════════════════════════════════════════════

def run_rf_loo(X_raw: np.ndarray, y: np.ndarray):
    """
    Leave-One-Out cross-validácia s Random Forest klasifikátorom.

    Pre každý fold:
      – fituje StandardScaler IBA na tréningových dátach (bez data leakage)
      – natrénuje RF na škálovaných tréningových dátach
      – predikuje triedu (userId) a pravdepodobnosti pre 1 testovací submission
      – zaznačí predikciu a pravdepodobnosti

    Na konci natrénuje plný RF a finálny scaler na všetkých dátach
    (pre feature importance a reálne nasadenie).

    Vracia:
      y_true      – skutočné triedy (userId) testovacích submissionov
      y_pred      – predikované triedy
      y_proba     – matica pravdepodobností [n_samples × n_classes]
      rf_classes  – poradie tried v y_proba
      rf          – plný RF model (natrénovaný na všetkých dátach)
      final_scaler– finálny scaler natrénovaný na všetkých dátach (pre export/demo)
    """
    loo = LeaveOneOut()
    y_true_list, y_pred_list, y_proba_list = [], [], []

    # 300 stromov, bez obmedzenia hĺbky (malý dataset → nízke riziko pretrénovania pri LOO)
    rf = RandomForestClassifier(n_estimators=300, max_depth=None,
                                min_samples_leaf=1, random_state=42)

    n_splits = len(X_raw)
    correct  = 0
    for fold_i, (train_idx, test_idx) in enumerate(loo.split(X_raw), start=1):
        X_tr_raw, X_te_raw = X_raw[train_idx], X_raw[test_idx]
        y_tr, y_te         = y[train_idx],     y[test_idx]

        # Scaler fitovaný IBA na tréningových dátach každého foldu → žiadny data leakage
        fold_scaler = StandardScaler()
        X_tr = fold_scaler.fit_transform(X_tr_raw)
        X_te = fold_scaler.transform(X_te_raw)

        rf.fit(X_tr, y_tr)
        pred = rf.predict(X_te)[0]
        correct += int(pred == y_te[0])
        y_true_list.append(y_te[0])
        y_pred_list.append(pred)
        y_proba_list.append(rf.predict_proba(X_te)[0])
        # Priebežný výpis každých 10 foldov
        if fold_i % 10 == 0 or fold_i == n_splits:
            pct = fold_i / n_splits * 100
            acc = correct / fold_i * 100
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            print(f"  [{bar}] {fold_i:>3}/{n_splits}  ({pct:5.1f}%)   priebežná acc: {acc:.1f}%", end="\r", flush=True)
    print()  # nový riadok po dokončení

    # Finálny scaler a plný model natrénované na celých dátach
    # → slúžia pre feature importance, demo autentifikáciu a export
    final_scaler = StandardScaler()
    X_all = final_scaler.fit_transform(X_raw)
    rf.fit(X_all, y)
    return (np.array(y_true_list), np.array(y_pred_list),
            np.array(y_proba_list), rf.classes_, rf, final_scaler)


def rf_verification_scores(y_true, y_proba, rf_classes):
    """
    Konvertuje LOO pravdepodobnosti RF na genuine a impostor skóre.

    Pre každý testovací submission od používateľa u:
      genuine score  = P(u)     – pravdepodobnosť, že RF zaradí submission správne
      impostor score = P(v≠u)   – pravdepodobnosti pre iné triedy
                                  (simulujeme: cudzí submission tvrdí, že je u)

    Celkovo: N genuine skóre (jedno na submission) + N×(K−1) impostor skóre
    (pre každý submission sa ostatných K−1 používateľov považuje za impostora).
    """
    genuine, impostor = [], []
    for yt, proba in zip(y_true, y_proba):
        # Index skutočnej triedy v poradí tried RF
        cls_idx = int(np.where(rf_classes == yt)[0][0])
        genuine.append(proba[cls_idx])          # P(true_class) = genuine score
        for j, c in enumerate(rf_classes):
            if c != yt:
                impostor.append(proba[j])       # P(other_class) = impostor score
    return np.array(genuine), np.array(impostor)


# ══════════════════════════════════════════════════════════════════════════════
# 6. AUTENTIFIKÁCIA – POUŽITIE NA NOVÝ SUBMISSION (Random Forest)
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
    x = scaler.transform(raw_feature_vector.reshape(1, -1))
    proba = rf_model.predict_proba(x)[0]

    # Skóre = priama pravdepodobnosť z RF (0..1) pre každého používateľa
    scores = {str(c): float(p) for c, p in zip(rf_model.classes_, proba)}
    best_user = max(scores, key=scores.get)

    # Percentuálne rozdelenie pre čitateľný výstup (súčet = 100%)
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
        # ASCII bar chart pre rýchly vizuálny prehľad
        bar   = "█" * int(pct / 2)
        email = res["email_map"].get(uid, str(uid))
        print(f"    {uid:<8s}  {email:<40s}  {pct:5.1f}%  {bar}")
    print("─" * 52)


# ══════════════════════════════════════════════════════════════════════════════
# 7. VIZUALIZÁCIA
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

    Interpretácia:
      – Keď prah rastie (prísnejší systém):
          FAR klesá (menej falošných prijatí = bezpečnejšie)
          FRR rastie (viac falošných odmietnutí = menej pohodlné)
          TAR klesá (systém akceptuje menej genuínnych)
      – EER = bod, kde FAR = FRR (kompromisný bod)
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
    ROC (Receiver Operating Characteristic) krivka – Random Forest.

    X-os: FAR (False Accept Rate) – koľko impostrov prenikne
    Y-os: TAR (True Accept Rate)  – koľko legitímnych používateľov prebehne

    Ideálna krivka: prechádza cez ľavý horný roh (FAR=0, TAR=1).
    AUC (plocha pod krivkou) blízka 1.0 = výborný systém.
    Bod EER leží na diagonále tam, kde FAR = FRR = 1 − TAR.
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
    Confusion matrix RF identifikácie (LOO-CV).

    Riadok = skutočný používateľ, stĺpec = predikovaný používateľ.
    Diagonála = správne identifikované submissiony (TA).
    Mimo diagonálu = chyby (zámenné identifikácie medzi používateľmi).
    """
    cm = confusion_matrix(y_true, y_pred, labels=classes)
    # Skrátiť email na meno pred @ pre lepšiu čitateľnosť osi
    labels = [email_map.get(c, str(c)).split("@")[0] for c in classes]

    im = ax.imshow(cm, interpolation="nearest", cmap="Blues")
    ax.figure.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    ax.set(xticks=range(len(classes)), yticks=range(len(classes)),
           yticklabels=labels,
           ylabel="Skutočný používateľ", xlabel="Predikovaný používateľ")
    # X-axis labels rotované zhora-dole (vertikálne) aby sa neprekrývali
    ax.set_xticklabels(labels, rotation=90, ha="center", fontsize=8)
    ax.set_title("RF Confusion Matrix (LOO-CV)", fontweight="bold")

    # Čísla v bunkách (biely text pre tmavé bunky, čierny pre svetlé)
    thresh = cm.max() / 2.0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, cm[i, j], ha="center", va="center",
                    color="white" if cm[i, j] > thresh else "black", fontsize=14)


def _fig5_feature_importance(ax, rf_model, feature_names, top_n=None):
    """
    Horizontálny bar chart príznakov zoradených podľa RF Gini importance.

    Gini importance = priemerné zníženie nečistoty (impurity) v strome,
    ktoré daný príznak spôsobí → vyššia hodnota = príznak lepšie rozlišuje používateľov.

    Farby stĺpcov podľa skupiny príznakov:
      červená  = senzorové príznaky (accel/gyro)
      modrá    = touch point príznaky
      zelená   = keystroke príznaky
      oranžová = drag metriky
      fialová  = textové metriky

    top_n=None → zobrazí VŠETKY príznaky.
    """
    importances = rf_model.feature_importances_
    n = len(importances) if top_n is None else top_n
    # Zoradiť zostupne a vziať n príznakov
    idx = np.argsort(importances)[-n:][::-1]

    # Farby podľa zdrojového CSV súboru:
    #   sensor_data.csv      → červená  (sd_*)
    #   touch_points.csv     → modrá    (tp_*)
    #   keystrokes.csv       → zelená   (ks_*)
    #   submissions_basic.csv→ oranžová (všetko ostatné: drag*, text*, submission*, averageWordTime, touchPointsCount, sensorDataCount)
    def feat_color(name):
        if name.startswith("sd_"):
            return "#e74c3c"   # sensor_data.csv
        if name.startswith("tp_"):
            return "#3498db"   # touch_points.csv
        if name.startswith("ks_"):
            return "#2ecc71"   # keystrokes.csv
        return "#f39c12"       # submissions_basic.csv

    feat_labels = [feature_names[i] for i in idx]
    feat_vals   = [importances[i] for i in idx]
    bar_colors  = [feat_color(n) for n in feat_labels]

    # Vykreslíme od najmenej dôležitého (dole) po najdôležitejší (hore) – hodnoty v %
    bars = ax.barh(range(len(idx)), [v * 100 for v in feat_vals[::-1]], color=bar_colors[::-1], edgecolor="white")
    ax.set_yticks(range(len(idx)))
    ax.set_yticklabels(feat_labels[::-1], fontsize=7)
    # Číselná hodnota na konci každého baru (bar.get_width() je už v %, stačí zobraziť priamo)
    for bar in bars:
        w = bar.get_width()
        ax.text(w + ax.get_xlim()[1] * 0.005, bar.get_y() + bar.get_height() / 2,
                f"{w:.2f}%", va="center", ha="left", fontsize=6)
    ax.set_xlabel("Dôležitosť (%)")
    title = f"Všetky príznaky ({len(idx)}) – RF Feature Importance" if top_n is None else f"Top {top_n} príznakov – RF Feature Importance"
    ax.set_title(title, fontweight="bold")

    from matplotlib.patches import Patch
    legend_elems = [
        Patch(facecolor="#e74c3c", label="sensor_data.csv   (sd_*)"),
        Patch(facecolor="#3498db", label="touch_points.csv  (tp_*)"),
        Patch(facecolor="#2ecc71", label="keystrokes.csv    (ks_*)"),
        Patch(facecolor="#f39c12", label="submissions_basic.csv"),
    ]
    ax.legend(handles=legend_elems, fontsize=7, loc="lower right")


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

    # Pre každého používateľa u zostavíme genuine a impostor skóre z LOO výsledkov
    data_genuine  = []
    data_impostor = []
    for u in unique_users:
        u_idx = int(np.where(rf_classes == u)[0][0])
        # Genuine: submissiony ktoré NAOZAJ patria používateľovi u
        genuine_mask  = y_true == u
        # Impostor: submissiony od iných používateľov, ale hodnotené ako P(u)
        impostor_mask = y_true != u
        data_genuine.append(y_proba[genuine_mask,  u_idx])
        data_impostor.append(y_proba[impostor_mask, u_idx])

    positions_g = np.arange(len(unique_users)) * 2.5
    positions_i = positions_g + 0.9

    bp1 = ax.boxplot(data_genuine, positions=positions_g, widths=0.7,
                     patch_artist=True, medianprops={"color": "black", "lw": 2})
    for patch in bp1["boxes"]:
        patch.set_facecolor(COLORS["genuine"])
        patch.set_alpha(0.75)

    bp2 = ax.boxplot(data_impostor, positions=positions_i, widths=0.7,
                     patch_artist=True, medianprops={"color": "black", "lw": 2})
    for patch in bp2["boxes"]:
        patch.set_facecolor(COLORS["impostor"])
        patch.set_alpha(0.75)

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


def visualize_all(m_rf, g_rf, i_rf, y_true, y_pred, y_proba, rf_classes, rf_model,
                  feature_names, meta):
    """
    Vygeneruje 2 figúry so 6 grafmi (Random Forest):

    Figúra 1 (verifikačné metriky):
      [0,0] Distribúcia skóre – RF genuine vs. impostor
      [0,1] Per-user box plot (genuine vs. impostor)
      [1,0] TAR/FAR/FRR vs. prah – RF
      [1,1] ROC krivka – RF

    Figúra 2 (RF identifikácia):
      [0,0] Confusion Matrix (LOO-CV)
      [0,1] Feature Importance (top 20 príznakov)
    """
    email_map = dict(zip(meta["userId"], meta["email"]))

    # ── Figúra 1: Verifikačné metriky ─────────────────────────────────────────
    fig1 = plt.figure(figsize=(16, 10))
    fig1.suptitle(
        "Behavica – Biometrická verifikácia: Random Forest",
        fontsize=14, fontweight="bold", y=0.98)

    gs1 = gridspec.GridSpec(2, 2, figure=fig1, hspace=0.42, wspace=0.35)
    ax_hist = fig1.add_subplot(gs1[0, 0])
    ax_user = fig1.add_subplot(gs1[0, 1])
    ax_thr  = fig1.add_subplot(gs1[1, 0])
    ax_roc  = fig1.add_subplot(gs1[1, 1])

    _fig1_score_distributions(ax_hist, g_rf, i_rf, m_rf)
    _fig6_per_user_scores(ax_user, y_true, y_proba, rf_classes, meta)
    _fig2_tar_far_frr(ax_thr, m_rf)
    _fig3_roc(ax_roc, m_rf)

    # ── Figúra 2: Confusion Matrix (samostatná) ───────────────────────────────
    n_users = len(rf_classes)
    # Výška figúry rastie s počtom používateľov aby sa mená neprekrývali
    fig2_h = max(7, n_users * 0.45 + 2)
    fig2 = plt.figure(figsize=(max(9, n_users * 0.45 + 2), fig2_h))
    fig2.suptitle(
        "Behavica – RF Confusion Matrix (LOO-CV)",
        fontsize=14, fontweight="bold", y=0.98)
    ax_cm = fig2.add_subplot(1, 1, 1)
    _fig4_confusion(ax_cm, y_true, y_pred, rf_classes, email_map)
    fig2.tight_layout(rect=[0, 0, 1, 0.96])

    # ── Figúra 3: Feature Importance – VŠETKY príznaky (samostatná) ───────────
    n_feat = len(feature_names)
    fig3_h = max(8, n_feat * 0.28 + 2)
    fig3 = plt.figure(figsize=(10, fig3_h))
    fig3.suptitle(
        "Behavica – RF Feature Importance (všetky príznaky)",
        fontsize=14, fontweight="bold", y=0.98)
    ax_feat = fig3.add_subplot(1, 1, 1)
    _fig5_feature_importance(ax_feat, rf_model, feature_names, top_n=None)
    fig3.tight_layout(rect=[0, 0, 1, 0.96])

    plt.show()


# ══════════════════════════════════════════════════════════════════════════════
# 8. KONZOLOVÝ VÝPIS METRÍK
# ══════════════════════════════════════════════════════════════════════════════

def print_metrics_table(m_rf, rf_acc, meta, y_true, y_pred):
    """Vypíše prehľadnú tabuľku biometrických metrík do konzoly (Random Forest)."""
    eer_idx = int(np.argmin(np.abs(m_rf["FAR"] - m_rf["FRR"])))
    email_map = dict(zip(meta["userId"], meta["email"]))

    print("\n" + "═" * 56)
    print("   BEHAVICA – VÝSLEDKY BIOMETRICKEJ AUTENTIFIKÁCIE (RF)")
    print("═" * 56)
    print(f"  {'Metrika':<38s} {'RF':>10s}")
    print("  " + "─" * 50)

    rows_data = [
        ("EER  (Equal Error Rate)",          f"{m_rf['EER']*100:.2f}%"),
        ("TAR pri EER",                      f"{m_rf['TAR'][eer_idx]*100:.2f}%"),
        ("FAR pri EER",                      f"{m_rf['FAR'][eer_idx]*100:.2f}%"),
        ("FRR pri EER",                      f"{m_rf['FRR'][eer_idx]*100:.2f}%"),
        ("Accuracy pri EER prahu",           f"{m_rf['Accuracy']*100:.2f}%"),
        ("AUC (plocha pod ROC krivkou)",     f"{m_rf['AUC']:.4f}"),
        ("Identifikačná Acc. (LOO)",         f"{rf_acc*100:.2f}%"),
        ("",  ""),
        ("Genuine vzorky (celkom)",          str(m_rf["n_genuine"])),
        ("Impostor vzorky (celkom)",         str(m_rf["n_impostor"])),
    ]

    for row in rows_data:
        if row[0] == "":
            print()
            continue
        print(f"  {row[0]:<38s} {row[1]:>10s}")

    print(f"\n  Confusion matrix pri EER prahu (RF):")
    print(f"    TA={m_rf['TA']}  FR={m_rf['FR']}  FA={m_rf['FA']}  TR={m_rf['TR']}")

    print(f"\n  Per-používateľ identifikácia (RF LOO-CV):")
    for u in np.unique(y_true):
        mask  = y_true == u
        acc_u = np.mean(y_pred[mask] == u)
        print(f"    {email_map.get(u, u):<40s}  "
              f"Acc: {acc_u*100:.1f}%  ({int(acc_u * mask.sum())}/{mask.sum()})")
    print("═" * 56)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN – hlavný tok programu
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("Načítavam dáta...")
    basic, tp, ks, sd, meta = load_all()

    print("Extrahujem príznaky z touch points, keystrokes a senzorov...")
    tp_feat = extract_touch_features(tp)
    ks_feat = extract_keystroke_features(ks)
    sd_feat = extract_sensor_features(sd)
    df      = build_feature_matrix(basic, tp_feat, ks_feat, sd_feat)

    # Stĺpce príznakov = všetky okrem identifikátorov
    feature_cols = [c for c in df.columns if c not in ["userId", "submissionNumber"]]
    X_raw = df[feature_cols].values   # neškálované hodnoty
    y     = df["userId"].values       # labely (userId)

    print(f"\nDataset: {len(df)} submissionov | {len(feature_cols)} príznakov "
          f"| {len(np.unique(y))} používatelia\n")

    # ── Random Forest identifikácia a verifikácia (LOO-CV)
    # Normalizácia (StandardScaler) prebieha VNÚTRI run_rf_loo per fold – bez data leakage.
    # Finálny scaler (natrénovaný na všetkých dátach) sa vráti spolu s modelom.
    print("Spúšťam RF LOO cross-validáciu (môže chvíľu trvať) ...")
    y_true, y_pred, y_proba, rf_classes, rf_model, scaler = run_rf_loo(X_raw, y)
    rf_acc     = float(np.mean(y_true == y_pred))
    g_rf, i_rf = rf_verification_scores(y_true, y_proba, rf_classes)
    m_rf       = compute_metrics(g_rf, i_rf)

    # ── Výpis súhrnných metrík
    print_metrics_table(m_rf, rf_acc, meta, y_true, y_pred)

    # ── Demo autentifikácie: každý používateľ verifikuje svoj 1. submission
    # Kľúče konvertujeme na string – userId môže byť numpy.int64, ale scores používajú str
    email_map = {str(k): v for k, v in zip(meta["userId"], meta["email"])}

    # POZOR: Táto demo sekcia používa tréningové dáta (X_raw[idx[0]]) a rf_model
    # natrénovaný na celom datasete. Výsledok NIE JE validný pre reálne hodnotenie –
    # slúži iba ako ukážka výstupu funkcie authenticate().
    # Pre skutočnú evaluáciu pozri LOO-CV výsledky vyššie.
    print("\n  DEMO: Verifikácia 1. submissnu každého používateľa\n"
          "  (submission bol zahrnutý v tréningu – len ukážka výstupu)")
    for uid in np.unique(y):
        idx  = np.where((df["userId"] == uid) & (df["submissionNumber"] == 1))[0]
        if len(idx) == 0:
            continue
        fvec = X_raw[idx[0]]
        res  = authenticate(fvec, rf_model, scaler, email_map, claimed_user_id=uid)
        print_auth_result(res)

    # ── Vizualizácia (otvorí 2 figúry)
    print("\nGenerujem vizualizácie ...")
    visualize_all(m_rf, g_rf, i_rf, y_true, y_pred, y_proba, rf_classes, rf_model,
                  feature_cols, meta)


if __name__ == "__main__":
    main()
