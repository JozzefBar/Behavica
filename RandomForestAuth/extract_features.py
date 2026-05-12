"""
Behavica – feature extraction and ablation-CSV generation.

  1. Loads 5 raw CSVs from BehavicaExport/.
  2. Drops the 1st submission of each user (training round).
  3. Extracts behavioral features (touch, keystroke, sensor, basic).
  4. Writes ablation-study CSV variants into ablation_csvs/:
       vsetky_priznaky.csv, len_senzory.csv, len_touch_points.csv, ...

Run: `python extract_features.py`, then `python evaluate.py ablation_csvs/<file>.csv`.
"""

import pandas as pd
import numpy as np
import sys
from pathlib import Path


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

DATA_DIR = Path(__file__).parent.parent / "BehavicaExport"
OUT_DIR  = Path(__file__).parent


# Data loading

def load_all():
    """Loads all 5 raw CSVs from BehavicaExport/."""
    basic = pd.read_csv(DATA_DIR / "submissions_basic.csv")   # aggregated metrics
    tp    = pd.read_csv(DATA_DIR / "touch_points.csv")        # raw touch points
    ks    = pd.read_csv(DATA_DIR / "keystrokes.csv")          # keystroke events
    sd    = pd.read_csv(DATA_DIR / "sensor_data.csv")         # accel + gyro
    meta  = pd.read_csv(DATA_DIR / "user_metadata.csv")       # user info
    return basic, tp, ks, sd, meta


# Feature extraction
# Feature groups: basic (10), touch (19), keystroke (13), sensor (22) → ~64 total.

def _std(s):
    """Safe std – returns 0 when only one element is present."""
    return float(s.std()) if len(s) > 1 else 0.0


def extract_touch_features(tp: pd.DataFrame) -> pd.DataFrame:
    """Per-submission features from raw touch points.

    Each touch_points.csv row is one event (ACTION_DOWN/MOVE/UP). Captures
    pressure & size, drag/overall velocity, inter-touch interval, screen
    coverage and tap count.
    """
    rows = []
    for (uid, sub), g in tp.groupby(["userId", "submissionNumber"]):
        g = g.sort_values("timestamp")
        p     = g["pressure"]
        s_col = g["size"]

        # Drag velocity: ACTION_MOVE events targeting "dragTest"
        drag_move = g[(g["action"] == "ACTION_MOVE") & (g["target"] == "dragTest")].copy()
        vels = []
        if len(drag_move) > 1:
            drag_move = drag_move.sort_values("timestamp")
            dx = drag_move["x"].diff()
            dy = drag_move["y"].diff()
            dt = drag_move["timestamp"].diff() / 1000.0
            dt = dt.replace(0, np.nan)
            v  = np.sqrt(dx**2 + dy**2) / dt
            vels = v.dropna().values

        # Overall movement velocity (all touch events)
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

        # Inter-touch interval; drop negatives and pauses > 5 s
        dts = g["timestamp"].diff().dropna().values
        dts = dts[(dts > 0) & (dts < 5000)]

        # Touch shape: major/minor axis ratio (≈1 round, >1 elongated)
        ratio = (g["touchMajor"] / g["touchMinor"].replace(0, np.nan)).dropna()

        rows.append({
            "userId": uid, "submissionNumber": sub,
            "tp_pressure_mean":     float(p.mean()),
            "tp_pressure_std":      _std(p),
            "tp_size_mean":         float(s_col.mean()),
            "tp_size_std":          _std(s_col),
            "tp_touchMajor_mean":   float(g["touchMajor"].mean()),
            "tp_touchMajor_std":    _std(g["touchMajor"]),
            "tp_touchMinor_mean":   float(g["touchMinor"].mean()),
            "tp_touchMinor_std":    _std(g["touchMinor"]),
            "tp_touch_shape_ratio": float(ratio.mean()) if len(ratio) else 1.0,
            "tp_drag_vel_mean":     float(np.mean(vels))             if len(vels) else 0.0,
            # ddof=1 to stay consistent with pandas .std() in _std()
            "tp_drag_vel_std":      float(np.std(vels, ddof=1))      if len(vels) > 1 else 0.0,
            "tp_drag_vel_max":      float(np.max(vels))              if len(vels) else 0.0,
            "tp_all_vel_mean":      float(np.mean(all_vels))         if len(all_vels) else 0.0,
            "tp_all_vel_std":       float(np.std(all_vels, ddof=1))  if len(all_vels) > 1 else 0.0,
            "tp_iti_mean":          float(np.mean(dts))              if len(dts) else 0.0,
            "tp_iti_std":           float(np.std(dts, ddof=1))       if len(dts) > 1 else 0.0,
            "tp_x_range":           float(g["x"].max() - g["x"].min()),
            "tp_y_range":           float(g["y"].max() - g["y"].min()),
            "tp_down_count":        int((g["action"] == "ACTION_DOWN").sum()),
        })
    return pd.DataFrame(rows)


def extract_keystroke_features(ks: pd.DataFrame) -> pd.DataFrame:
    """Per-submission features from keystroke events.

    Each row is one keypress (type=insert/delete; count>1 means autocomplete
    or paste). Captures inter-key interval (rhythm), delete ratio (error rate),
    auto/paste count, and per-word typing time for words "internet", "wifi",
    "laptop".
    """
    rows = []
    for (uid, sub), g in ks.groupby(["userId", "submissionNumber"]):
        g       = g.sort_values("timestamp")
        inserts = g[g["type"] == "insert"]
        deletes = g[g["type"] == "delete"]
        total   = len(g)

        # Inter-key interval
        iki = g["timestamp"].diff().dropna().values
        iki = iki[(iki > 0) & (iki < 10_000)]

        # Per-word time: first to last keystroke within a word, in ms
        word_times = {}
        for word, wg in g.groupby("word"):
            wg = wg.sort_values("timestamp")
            if len(wg) > 1:
                word_times[word] = wg["timestamp"].iloc[-1] - wg["timestamp"].iloc[0]

        # Autocomplete/paste detection
        auto_count = int((inserts["count"] > 1).sum()) if len(inserts) else 0

        rows.append({
            "userId": uid, "submissionNumber": sub,
            "ks_total_events":   total,
            "ks_insert_count":   len(inserts),
            "ks_delete_count":   len(deletes),
            "ks_delete_ratio":   len(deletes) / max(total, 1),
            "ks_auto_count":     auto_count,
            "ks_iki_mean":       float(np.mean(iki))           if len(iki) else 0.0,
            "ks_iki_std":        float(np.std(iki, ddof=1))   if len(iki) > 1 else 0.0,
            "ks_iki_min":        float(np.min(iki))  if len(iki) else 0.0,
            "ks_iki_max":        float(np.max(iki))  if len(iki) else 0.0,
            # IKI quartiles – shape of the typing-speed distribution
            "ks_iki_q25":        float(np.percentile(iki, 25)) if len(iki) else 0.0,
            "ks_iki_q75":        float(np.percentile(iki, 75)) if len(iki) else 0.0,
            "ks_word_time_mean": float(np.mean(list(word_times.values())))           if word_times else 0.0,
            "ks_word_time_std":  float(np.std(list(word_times.values()), ddof=1))   if len(word_times) > 1 else 0.0,
        })
    return pd.DataFrame(rows)


def extract_sensor_features(sd: pd.DataFrame) -> pd.DataFrame:
    """Per-submission stats from accelerometer (m/s²) and gyroscope (rad/s).

    mean/std/range per axis (18 features) + 3D magnitudes
    sqrt(X²+Y²+Z²) — orientation-independent amplitude (4 features).
    """
    rows = []
    for (uid, sub), g in sd.groupby(["userId", "submissionNumber"]):
        accel_mag = np.sqrt(g["accelX"]**2 + g["accelY"]**2 + g["accelZ"]**2)
        gyro_mag  = np.sqrt(g["gyroX"]**2  + g["gyroY"]**2  + g["gyroZ"]**2)

        rows.append({
            "userId": uid, "submissionNumber": sub,
            "sd_accelX_mean":    float(g["accelX"].mean()),
            "sd_accelX_std":     _std(g["accelX"]),
            "sd_accelX_range":   float(g["accelX"].max() - g["accelX"].min()),
            "sd_accelY_mean":    float(g["accelY"].mean()),
            "sd_accelY_std":     _std(g["accelY"]),
            "sd_accelY_range":   float(g["accelY"].max() - g["accelY"].min()),
            "sd_accelZ_mean":    float(g["accelZ"].mean()),
            "sd_accelZ_std":     _std(g["accelZ"]),
            "sd_accelZ_range":   float(g["accelZ"].max() - g["accelZ"].min()),
            "sd_gyroX_mean":     float(g["gyroX"].mean()),
            "sd_gyroX_std":      _std(g["gyroX"]),
            "sd_gyroX_range":    float(g["gyroX"].max() - g["gyroX"].min()),
            "sd_gyroY_mean":     float(g["gyroY"].mean()),
            "sd_gyroY_std":      _std(g["gyroY"]),
            "sd_gyroY_range":    float(g["gyroY"].max() - g["gyroY"].min()),
            "sd_gyroZ_mean":     float(g["gyroZ"].mean()),
            "sd_gyroZ_std":      _std(g["gyroZ"]),
            "sd_gyroZ_range":    float(g["gyroZ"].max() - g["gyroZ"].min()),
            "sd_accel_mag_mean": float(accel_mag.mean()),
            "sd_accel_mag_std":  _std(accel_mag),
            "sd_gyro_mag_mean":  float(gyro_mag.mean()),
            "sd_gyro_mag_std":   _std(gyro_mag),
        })
    return pd.DataFrame(rows)


def build_feature_matrix(basic, tp_feat, ks_feat, sd_feat) -> pd.DataFrame:
    """Joins all feature tables into one row per (userId, submissionNumber).

    Takes the 10 aggregated metrics directly from submissions_basic
    (submissionDurationSec, drag*, textRewriteTime, averageWordTime,
    textEditCount, touchPointsCount, sensorDataCount).
    """
    basic_cols = [
        "userId", "submissionNumber",
        "submissionDurationSec", "dragAttempts", "dragDistance",
        "dragPathLength", "dragDurationSec", "textRewriteTime",
        "averageWordTime", "textEditCount", "touchPointsCount", "sensorDataCount",
    ]
    df = basic[basic_cols].copy()
    for feat_df in [tp_feat, ks_feat, sd_feat]:
        df = df.merge(feat_df, on=["userId", "submissionNumber"], how="left")

    # Impute NaN with column median (0 is unrealistic for e.g. tp_pressure_mean).
    feat_cols     = [c for c in df.columns if c not in ["userId", "submissionNumber"]]
    medians       = df[feat_cols].median()
    df[feat_cols] = df[feat_cols].fillna(medians)
    df            = df.fillna(0.0)                   # fallback if whole column is NaN
    medians_dict  = medians.fillna(0.0).to_dict()    # for export into model.pkl

    return df, medians_dict


# Ablation-study variants

def get_ablation_combos(all_cols: list) -> list:
    """Returns (name, columns) for every feature-group combination.

    Prefixes: sd_* sensor, tp_* touch, ks_* keystroke; basic and drag are
    direct columns from submissions_basic.
    """
    def grp(prefixes):
        return [c for c in all_cols if any(c.startswith(p) for p in prefixes)]

    sensor_cols = grp(["sd_"])
    touch_cols  = grp(["tp_"])
    ks_cols     = grp(["ks_"])
    # Magnitude features – isolated to test their contribution. In a
    # portrait-locked app their orientation-independence benefit is debatable
    # because per-axis features already encode the gravitational bias.
    mag_cols    = ["sd_accel_mag_mean", "sd_accel_mag_std",
                   "sd_gyro_mag_mean",  "sd_gyro_mag_std"]
    basic_cols  = grp(["submissionDurationSec", "dragAttempts", "dragDistance",
                        "dragPathLength", "dragDurationSec", "textRewriteTime",
                        "averageWordTime", "textEditCount",
                        "touchPointsCount", "sensorDataCount"])
    drag_cols   = grp(["drag", "tp_drag_"])

    # Device-independent subset: timing / count / variability features only;
    # no sensor/touch means, no screen-size-dependent values. Simulates a
    # cross-device generalization scenario.
    device_indep_cols = [c for c in [
        # Basic (no dragDistance/dragPathLength – screen-size dependent)
        "submissionDurationSec", "dragAttempts", "dragDurationSec",
        "textRewriteTime", "averageWordTime", "textEditCount",
        "touchPointsCount", "sensorDataCount",
        # Touch – variability / timing / counts (no means, no range)
        "tp_pressure_std", "tp_size_std", "tp_touchMajor_std", "tp_touchMinor_std",
        "tp_iti_mean", "tp_iti_std", "tp_down_count",
        "tp_drag_vel_std", "tp_all_vel_std",
        # Keystrokes – all (timing/count/ratio)
        *ks_cols,
        # Sensor – std and range only (means dropped → ignores gravity bias)
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


# Main

def main():
    # Tee stdout into a log file next to the generated CSV variants
    ablation_dir = OUT_DIR / "ablation_csvs"
    ablation_dir.mkdir(exist_ok=True)
    log_path = ablation_dir / "extract_features_log.txt"
    log_file   = open(log_path, "w", encoding="utf-8")
    orig_stdout = sys.stdout
    sys.stdout  = _Tee(log_file)

    try:
        _main_logic()
    finally:
        sys.stdout = orig_stdout
        log_file.close()
    print(f"  → Log uložený: {log_path}")


def _main_logic():
    print("Načítavam surové dáta z BehavicaExport/ ...")
    basic, tp, ks, sd, meta = load_all()
    all_count = len(basic)
    print(f"  → {all_count} submissionov načítaných pre "
          f"{basic['userId'].nunique()} používateľov")

    # Drop submission #1 of each user BEFORE feature extraction — it was a
    # training round and its patterns are not representative; excluding it
    # also keeps it out of medians used for NaN imputation.
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
    # medians_dict not needed here
    df, _   = build_feature_matrix(basic, tp_feat, ks_feat, sd_feat)

    feature_cols = [c for c in df.columns if c not in ["userId", "submissionNumber"]]
    print(f"  → Dataset: {len(df)} submissionov | {len(feature_cols)} príznakov "
          f"| {df['userId'].nunique()} používatelia")

    ablation_dir = OUT_DIR / "ablation_csvs"

    # Short variant descriptions – just for log output; do not affect CSV contents
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
    # Align descriptions: column width = longest CSV name
    name_w = max(len(name) for name, _ in combos) + len(".csv")
    for csv_name, cols in combos:
        if not cols:
            print(f"  ✗ {csv_name}.csv – žiadne príznaky, preskakujem")
            continue
        path = ablation_dir / f"{csv_name}.csv"
        df[["userId", "submissionNumber"] + cols].to_csv(path, index=False)
        desc = descriptions.get(csv_name, "")
        print(f"  ✓ {(csv_name + '.csv'):<{name_w}}  ({len(cols):2d} príznakov)  – {desc}")

    # Top-10 variant – picked dynamically by RF feature importance
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
