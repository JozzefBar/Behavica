"""
Behavica – Extrakcia príznakov a generovanie CSV variantov
===========================================================

Čo tento skript robí:
  1. Načíta surové dáta z 5 CSV súborov (BehavicaExport/).
  2. Odstráni 1. submission každého používateľa (učiaci/tréningový pokus).
  3. Extrahuje behaviorálne príznaky (touch, keystroke, sensor, základné).
  4. Uloží varianty CSV pre ablation study do ablation_csvs/:
       vsetky_priznaky.csv, len_senzory.csv, len_touch_points.csv, ...

Ako spustiť:
  python extract_features.py

Výstup:
  ablation_csvs/*.csv         – varianty pre jednotlivé skupiny príznakov

Potom spusti evaluate.py na konkrétnom CSV:
  python evaluate.py ablation_csvs/vsetky_priznaky.csv
  python evaluate.py ablation_csvs/len_senzory.csv
"""

import pandas as pd
import numpy as np
import sys
from pathlib import Path


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

# Cesta k priečinku so surovými CSV súbormi
DATA_DIR = Path(__file__).parent.parent / "BehavicaExport"
OUT_DIR  = Path(__file__).parent


# ══════════════════════════════════════════════════════════════════════════════
# 1. NAČÍTANIE DÁT
# ══════════════════════════════════════════════════════════════════════════════

def load_all():
    """Načíta všetkých 5 surových CSV súborov z BehavicaExport/."""
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

        # Rýchlosť dragu: len ACTION_MOVE udalosti v cieli "dragTest"
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

        # ── Celková rýchlosť pohybu (všetky dotykové udalosti v appke)
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
        # Odfiltrujeme záporné hodnoty a prílišne dlhé pauzy (> 5 sekúnd)
        dts = dts[(dts > 0) & (dts < 5000)]

        # ── Tvar dotyku: pomer dlhšej a kratšej osi elipsy dotyku prsta
        # Hodnota blízka 1 = okrúhly dotyk, > 1 = elipsovitý (šikmý prst)
        ratio = (g["touchMajor"] / g["touchMinor"].replace(0, np.nan)).dropna()

        rows.append({
            "userId": uid, "submissionNumber": sub,
            # — Tlak
            "tp_pressure_mean":     float(p.mean()),
            "tp_pressure_std":      _std(p),
            # — Veľkosť dotyku
            "tp_size_mean":         float(s_col.mean()),
            "tp_size_std":          _std(s_col),
            "tp_touchMajor_mean":   float(g["touchMajor"].mean()),
            "tp_touchMajor_std":    _std(g["touchMajor"]),
            "tp_touchMinor_mean":   float(g["touchMinor"].mean()),
            "tp_touchMinor_std":    _std(g["touchMinor"]),
            "tp_touch_shape_ratio": float(ratio.mean()) if len(ratio) else 1.0,
            # — Rýchlosť dragu
            "tp_drag_vel_mean":     float(np.mean(vels))             if len(vels) else 0.0,
            # ddof=1 – konzistentné s _std() ktorá používa pandas .std() (ddof=1)
            "tp_drag_vel_std":      float(np.std(vels, ddof=1))      if len(vels) > 1 else 0.0,
            "tp_drag_vel_max":      float(np.max(vels))              if len(vels) else 0.0,
            # — Celková rýchlosť pohybu
            "tp_all_vel_mean":      float(np.mean(all_vels))         if len(all_vels) else 0.0,
            # ddof=1
            "tp_all_vel_std":       float(np.std(all_vels, ddof=1))  if len(all_vels) > 1 else 0.0,
            # — Inter-touch interval
            "tp_iti_mean":          float(np.mean(dts))              if len(dts) else 0.0,
            # ddof=1
            "tp_iti_std":           float(np.std(dts, ddof=1))       if len(dts) > 1 else 0.0,
            # — Pokrytá plocha obrazovky
            "tp_x_range":           float(g["x"].max() - g["x"].min()),
            "tp_y_range":           float(g["y"].max() - g["y"].min()),
            # — Počet stlačení
            "tp_down_count":        int((g["action"] == "ACTION_DOWN").sum()),
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
        g       = g.sort_values("timestamp")
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
                # Trvanie písania jedného slova v milisekundách
                word_times[word] = wg["timestamp"].iloc[-1] - wg["timestamp"].iloc[0]

        # Detekcia autocomplete/paste: count > 1 = vložených viacero znakov naraz
        auto_count = int((inserts["count"] > 1).sum()) if len(inserts) else 0

        rows.append({
            "userId": uid, "submissionNumber": sub,
            "ks_total_events":   total,
            "ks_insert_count":   len(inserts),
            "ks_delete_count":   len(deletes),
            # Pomer zmazaní voči všetkým udalostiam → miera chybovosti
            "ks_delete_ratio":   len(deletes) / max(total, 1),
            "ks_auto_count":     auto_count,
            # Inter-key interval
            "ks_iki_mean":       float(np.mean(iki))           if len(iki) else 0.0,
            # ddof=1
            "ks_iki_std":        float(np.std(iki, ddof=1))   if len(iki) > 1 else 0.0,
            "ks_iki_min":        float(np.min(iki))  if len(iki) else 0.0,
            "ks_iki_max":        float(np.max(iki))  if len(iki) else 0.0,
            # Kvartilyy IKI – zachytávajú tvar rozdelenia rýchlosti písania
            "ks_iki_q25":        float(np.percentile(iki, 25)) if len(iki) else 0.0,
            "ks_iki_q75":        float(np.percentile(iki, 75)) if len(iki) else 0.0,
            # Čas per slovo (internet, wifi, laptop)
            "ks_word_time_mean": float(np.mean(list(word_times.values())))           if word_times else 0.0,
            # ddof=1
            "ks_word_time_std":  float(np.std(list(word_times.values()), ddof=1))   if len(word_times) > 1 else 0.0,
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
            "sd_accelX_mean":    float(g["accelX"].mean()),
            "sd_accelX_std":     _std(g["accelX"]),
            "sd_accelX_range":   float(g["accelX"].max() - g["accelX"].min()),
            "sd_accelY_mean":    float(g["accelY"].mean()),
            "sd_accelY_std":     _std(g["accelY"]),
            "sd_accelY_range":   float(g["accelY"].max() - g["accelY"].min()),
            "sd_accelZ_mean":    float(g["accelZ"].mean()),
            "sd_accelZ_std":     _std(g["accelZ"]),
            "sd_accelZ_range":   float(g["accelZ"].max() - g["accelZ"].min()),
            # — Gyroskop: každá os zvlášť (mean, std, rozsah)
            "sd_gyroX_mean":     float(g["gyroX"].mean()),
            "sd_gyroX_std":      _std(g["gyroX"]),
            "sd_gyroX_range":    float(g["gyroX"].max() - g["gyroX"].min()),
            "sd_gyroY_mean":     float(g["gyroY"].mean()),
            "sd_gyroY_std":      _std(g["gyroY"]),
            "sd_gyroY_range":    float(g["gyroY"].max() - g["gyroY"].min()),
            "sd_gyroZ_mean":     float(g["gyroZ"].mean()),
            "sd_gyroZ_std":      _std(g["gyroZ"]),
            "sd_gyroZ_range":    float(g["gyroZ"].max() - g["gyroZ"].min()),
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

    # FIX 5: Namiesto fillna(0) použijeme mediány – 0 je pre niektoré príznaky
    # nereálna hodnota (napr. tp_pressure_mean=0 by zmiatol model)
    feat_cols     = [c for c in df.columns if c not in ["userId", "submissionNumber"]]
    medians       = df[feat_cols].median()           # ignoruje NaN pri výpočte
    df[feat_cols] = df[feat_cols].fillna(medians)    # NaN → mediánová hodnota stĺpca
    df            = df.fillna(0.0)                   # fallback ak celý stĺpec je NaN
    medians_dict  = medians.fillna(0.0).to_dict()    # slovník pre export do model.pkl

    return df, medians_dict


# ══════════════════════════════════════════════════════════════════════════════
# 3. DEFINÍCIA VARIANTOV PRE ABLATION STUDY
# ══════════════════════════════════════════════════════════════════════════════

def get_ablation_combos(all_cols: list) -> list:
    """
    Vráti zoznam (názov, stĺpce) pre každú kombináciu skupín príznakov.

    Každý variant sa uloží ako samostatný CSV súbor pre neskoršiu evaluáciu
    pomocou evaluate.py.

    Skupiny príznakov podľa zdrojového CSV:
      sd_*      → sensor_data.csv        (akcelerometer + gyroskop)
      tp_*      → touch_points.csv       (dotykové body)
      ks_*      → keystrokes.csv         (klávesnicové udalosti)
      basic     → submissions_basic.csv  (všetkých 10 agregovaných metrík)
      drag      → drag-related príznaky  (agregované + dotykové rýchlosti)
    """
    def grp(prefixes):
        """Vyberie stĺpce ktorých názov začína niektorým z prefixov."""
        return [c for c in all_cols if any(c.startswith(p) for p in prefixes)]

    sensor_cols = grp(["sd_"])
    touch_cols  = grp(["tp_"])
    ks_cols     = grp(["ks_"])
    # Magnitúdové príznaky – izolovaný test ich prínosu v rámci senzorovej skupiny.
    # V portrait-locked appke je ich hlavný benefit (orientačná nezávislosť) sporný,
    # lebo per-axis príznaky už obsahujú informáciu o orientácii (gravitačný bias).
    mag_cols    = ["sd_accel_mag_mean", "sd_accel_mag_std",
                   "sd_gyro_mag_mean",  "sd_gyro_mag_std"]
    # Všetkých 10 agregovaných metrík z submissions_basic.csv
    basic_cols  = grp(["submissionDurationSec", "dragAttempts", "dragDistance",
                        "dragPathLength", "dragDurationSec", "textRewriteTime",
                        "averageWordTime", "textEditCount",
                        "touchPointsCount", "sensorDataCount"])
    # Všetko súvisiace s drag testom: agregované metriky + dotykové rýchlosti
    drag_cols   = grp(["drag", "tp_drag_"])

    # Device-independent podmnožina: časové/počtové/variabilitné príznaky,
    # bez means senzorov/touchu a bez screen-size závislých hodnôt.
    # Cieľ: simulovať hypotetický cross-device generalizačný scenár.
    device_indep_cols = [c for c in [
        # Basic (bez dragDistance/dragPathLength – závisia od veľkosti displeja)
        "submissionDurationSec", "dragAttempts", "dragDurationSec",
        "textRewriteTime", "averageWordTime", "textEditCount",
        "touchPointsCount", "sensorDataCount",
        # Touch – variabilita / časovanie / počty (bez means a range)
        "tp_pressure_std", "tp_size_std", "tp_touchMajor_std", "tp_touchMinor_std",
        "tp_iti_mean", "tp_iti_std", "tp_down_count",
        "tp_drag_vel_std", "tp_all_vel_std",
        # Keystrokes – všetko (timing/count/ratio)
        *ks_cols,
        # Sensor – len std a range (bez means → ignoruje gravitačný bias)
        "sd_accelX_std", "sd_accelX_range", "sd_accelY_std", "sd_accelY_range",
        "sd_accelZ_std", "sd_accelZ_range",
        "sd_gyroX_std", "sd_gyroX_range", "sd_gyroY_std", "sd_gyroY_range",
        "sd_gyroZ_std", "sd_gyroZ_range",
        "sd_accel_mag_std", "sd_gyro_mag_std",
    ] if c in all_cols]

    return [
        ("vsetky_priznaky",      all_cols),
        ("len_senzory",           sensor_cols),
        ("len_senzory_bez_magnitud", [c for c in sensor_cols if c not in mag_cols]),
        ("len_touch_points",      touch_cols),
        ("len_keystrokes",        ks_cols),
        ("len_drag",              drag_cols),
        ("agregovane_metriky",    basic_cols),
        ("senzory_a_touch",       sensor_cols + touch_cols),
        ("senzory_a_keystrokes",  sensor_cols + ks_cols),
        ("touch_a_keystrokes",    touch_cols  + ks_cols),
        ("bez_senzorov",          [c for c in all_cols if c not in sensor_cols]),
        ("device_independent",    device_indep_cols),
    ]


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    # Uloženie výstupu do TXT súboru v rovnakom priečinku ako CSV varianty
    ablation_dir = OUT_DIR / "ablation_csvs"
    ablation_dir.mkdir(exist_ok=True)
    log_path = ablation_dir / "extract_features_log.txt"
    log_file   = open(log_path, "w", encoding="utf-8")
    orig_stdout = sys.stdout            # uložíme originálny stdout pred nahradením
    sys.stdout  = _Tee(log_file)

    try:
        _main_logic()
    finally:
        # Obnovíme pôvodný stdout a zatvoríme súbor
        sys.stdout = orig_stdout
        log_file.close()
    print(f"  → Log uložený: {log_path}")


def _main_logic():
    print("Načítavam surové dáta z BehavicaExport/ ...")
    basic, tp, ks, sd, meta = load_all()
    all_count = len(basic)
    print(f"  → {all_count} submissionov načítaných pre "
          f"{basic['userId'].nunique()} používateľov")

    # Odstránime 1. submission každého používateľa PRED extrakciou príznakov –
    # slúžil ako "tréningový/učiaci" pokus a jeho vzory nemusia reprezentovať
    # bežné správanie. Odstraňujeme ho tu, aby sa nepremietol ani do mediánov
    # ani do žiadnych štatistík (napr. pri NaN imputácii v build_feature_matrix).
    basic = basic[basic["submissionNumber"] != 1].reset_index(drop=True)
    tp    = tp[tp["submissionNumber"] != 1].reset_index(drop=True)
    ks    = ks[ks["submissionNumber"] != 1].reset_index(drop=True)
    sd    = sd[sd["submissionNumber"] != 1].reset_index(drop=True)
    print(f"  → Odstránený 1. submission každého používateľa "
          f"({all_count - len(basic)} záznamov odfiltrovaných)")

    print("\nExtrahujem príznaky ...")
    tp_feat = extract_touch_features(tp)
    ks_feat = extract_keystroke_features(ks)
    sd_feat = extract_sensor_features(sd)
    # build_feature_matrix teraz vracia (df, medians_dict) – mediány nepotrebujeme tu
    df, _   = build_feature_matrix(basic, tp_feat, ks_feat, sd_feat)

    feature_cols = [c for c in df.columns if c not in ["userId", "submissionNumber"]]
    print(f"  → Dataset: {len(df)} submissionov | {len(feature_cols)} príznakov "
          f"| {df['userId'].nunique()} používatelia")

    # Uloženie variantov pre ablation study
    ablation_dir = OUT_DIR / "ablation_csvs"

    # Krátke popisy variantov – aby bolo z logu hneď jasné, čo ktorý CSV testuje.
    # Pridávané do print výstupu; nemenia obsah CSV súborov.
    descriptions = {
        "vsetky_priznaky":           "baseline – všetky príznaky spolu",
        "len_senzory":               "izolovaný prínos akcelerometra + gyroskopu",
        "len_senzory_bez_magnitud":  "senzory bez 3D magnitúd (test redundancie v portrait-only)",
        "len_touch_points":          "izolovaný prínos dotykových bodov",
        "len_keystrokes":            "izolovaný prínos klávesnicových udalostí",
        "len_drag":                  "izolovaný prínos drag & drop testu",
        "agregovane_metriky":        "len 10 hotových metrík zo submissions_basic.csv",
        "senzory_a_touch":           "senzory + touch (bez keystrokov)",
        "senzory_a_keystrokes":      "senzory + keystroky (bez touchu)",
        "touch_a_keystrokes":        "touch + keystroky (bez senzorov)",
        "bez_senzorov":              "všetko okrem senzorov – test scenára bez akcelerometra/gyroskopu",
        "device_independent":        "device-independent podmnožina (bez means a screen-závislých metrík)",
    }

    combos = get_ablation_combos(feature_cols)
    print(f"\nGenerujem {len(combos)} CSV variantov pre ablation study ...")
    # Šírka stĺpca s názvom CSV – dynamicky podľa najdlhšieho mena, aby boli popisy zarovnané.
    name_w = max(len(name) for name, _ in combos) + len(".csv")
    for csv_name, cols in combos:
        if not cols:
            print(f"  ✗ {csv_name}.csv – žiadne príznaky, preskakujem")
            continue
        path = ablation_dir / f"{csv_name}.csv"
        df[["userId", "submissionNumber"] + cols].to_csv(path, index=False)
        desc = descriptions.get(csv_name, "")
        print(f"  ✓ {(csv_name + '.csv'):<{name_w}}  ({len(cols):2d} príznakov)  – {desc}")

    # ── top-10 variant (dynamicky podľa feature importance RF modelu) ─────
    print(f"\nGenerujem top-10 variant podľa RF feature importance ...")
    from sklearn.ensemble import RandomForestClassifier
    X = df[feature_cols].values
    y = df["userId"].values
    rf = RandomForestClassifier(n_estimators=300, random_state=42, n_jobs=-1)
    rf.fit(X, y)
    imp = rf.feature_importances_
    top_idx = np.argsort(imp)[::-1][:10]
    top10_cols = [feature_cols[i] for i in top_idx]
    path = ablation_dir / "top10_priznaky.csv"
    df[["userId", "submissionNumber"] + top10_cols].to_csv(path, index=False)
    print(f"  ✓ top10_priznaky.csv  (10 príznakov)")
    for rank, (col, val) in enumerate(zip(top10_cols, imp[top_idx]), 1):
        print(f"      {rank:2d}. {col:<40s} {val*100:.3f}%")

    print(f"\nVšetky CSV súbory uložené.")
    print(f"  python evaluate.py ablation_csvs/vsetky_priznaky.csv")


if __name__ == "__main__":
    main()
