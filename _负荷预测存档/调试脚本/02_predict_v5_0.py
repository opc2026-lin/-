# -*- coding: utf-8 -*-
"""
Pipeline V3.0 棰勬祴鑴氭湰
鏋舵瀯锛氶潪閫掑綊骞惰棰勬祴 + 鍏変紡閫嗗悜鎵ｅ噺
- 绗竴姝ワ細鍏ㄩ噺浣庤礋鑽峰垎绫伙紙涓€娆℃€у垎绫绘墍鏈夐娴嬫椂娈碉級
- 绗簩姝ワ細浣庤礋鑽峰洖褰?+ 鎸夊皬鏃惰矾鐢卞埌鐙珛鏅€氬洖褰掓ā鍨?- 绗笁姝ワ細閫嗗悜鍏変紡鎵ｅ噺锛歠inal_net_load = predicted_total_load - pv_est

V3.1 淇锛?- 淇婊氬姩缁熻鍦ㄦ暟鎹┖绐楁湡杩斿洖绌哄€肩殑闂锛堟敼鐢ㄦ渶杩慛涓暟鎹偣锛?- 淇 _get_lag_from_history 杩斿洖瀵归綈闂
- 淇 recent_workhour 鍦ㄦ暟鎹┖绐楁湡鐨勯棶棰?"""

import argparse
import re
import glob
import pickle
import warnings
import calendar
import numpy as np
import pandas as pd
import openpyxl

from pathlib import Path

warnings.filterwarnings("ignore")

# =========================================================
# 1. 璺緞閰嶇疆
# =========================================================
BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parents[1]
INPUT_ROOT = PROJECT_DIR / "1-1璐熻嵎棰勬祴杈撳叆"
OUTPUT_ROOT = PROJECT_DIR / "1-2璐熻嵎棰勬祴杈撳嚭"

USER_MASTER_PATH = BASE_DIR / "input" / "user_master" / "01_鐢ㄦ埛涓绘。妗堣〃.csv"
WEATHER_DIR = BASE_DIR / "input" / "weather"
LOAD_DIR = BASE_DIR / "input" / "load"

OUTPUT_PROCESSED = BASE_DIR / "output" / "processed"
OUTPUT_MODEL = BASE_DIR / "output" / "model"
OUTPUT_PREDICTION = BASE_DIR / "output" / "prediction"
OUTPUT_LOGS = BASE_DIR / "output" / "logs"

# Override legacy in-script paths with the real project IO directories.
USER_MASTER_PATH = INPUT_ROOT / "鐢ㄦ埛涓绘。妗堣〃.xlsx"
WEATHER_DIR = INPUT_ROOT / "2.棰勬祴澶╂皵"
LOAD_DIR = INPUT_ROOT / "1.鍒嗘椂娈靛巻鍙茬敤鐢典俊鎭?

OUTPUT_PROCESSED = OUTPUT_ROOT / "processed"
OUTPUT_MODEL = OUTPUT_ROOT / "model"
OUTPUT_PREDICTION = OUTPUT_ROOT / "prediction"
OUTPUT_LOGS = OUTPUT_ROOT / "logs"

for p in [OUTPUT_PROCESSED, OUTPUT_MODEL, OUTPUT_PREDICTION, OUTPUT_LOGS]:
    p.mkdir(parents=True, exist_ok=True)

# =========================================================
# 2. 鏃ュ織
# =========================================================
LOG_FILE = OUTPUT_LOGS / "02_predict_v3_log.txt"

def log(msg):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")


def save_csv_with_fallback(df, output_path):
    try:
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        return output_path
    except PermissionError:
        timestamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
        fallback_path = output_path.with_name(f"{output_path.stem}_{timestamp}{output_path.suffix}")
        df.to_csv(fallback_path, index=False, encoding="utf-8-sig")
        log(f"鐩爣鏂囦欢琚崰鐢紝宸插彟瀛樹负: {fallback_path.name}")
        return fallback_path

with open(LOG_FILE, "w", encoding="utf-8") as f:
    f.write("=== V3.1 棰勬祴鏃ュ織 ===\n")

# =========================================================
# 3. 璇诲彇杩愯閰嶇疆
# =========================================================
CONFIG_PATH = OUTPUT_MODEL / "run_config_v3.csv"
if not CONFIG_PATH.exists():
    raise FileNotFoundError(f"鏈壘鍒?{CONFIG_PATH}锛岃鍏堣繍琛?01_train_v3.py")

RUN_CONFIG = pd.read_csv(CONFIG_PATH, encoding="utf-8-sig").iloc[0]
PREDICT_START_TS = pd.Timestamp(RUN_CONFIG["PREDICT_START"])
PREDICT_END_TS = pd.Timestamp(RUN_CONFIG["PREDICT_END"])
LOW_LOAD_THRESHOLD = float(RUN_CONFIG["LOW_LOAD_THRESHOLD"])
LOW_LOAD_PROBA_THRESHOLD = float(RUN_CONFIG["LOW_LOAD_PROBA_THRESHOLD"])
USER_MODEL_MIN_SAMPLES = int(RUN_CONFIG["USER_MODEL_MIN_SAMPLES"]) if "USER_MODEL_MIN_SAMPLES" in RUN_CONFIG.index else 24
USER_BIAS_BLEND = 0.35
GROUP_BIAS_BLEND = 0.55
LOW_LOAD_BIAS_BLEND = 0.15
BIAS_RATIO_MIN = 0.60
BIAS_RATIO_MAX = 1.40


def parse_runtime_args():
    parser = argparse.ArgumentParser(description="Load forecast prediction runner")
    parser.add_argument("--start-date", help="Prediction start date, format: YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=1, help="Number of forecast days")
    args, _ = parser.parse_known_args()
    return args


RUNTIME_ARGS = parse_runtime_args()
if RUNTIME_ARGS.start_date:
    _runtime_start = pd.Timestamp(RUNTIME_ARGS.start_date).normalize()
    _runtime_days = max(int(RUNTIME_ARGS.days or 1), 1)
    PREDICT_START_TS = _runtime_start
    PREDICT_END_TS = _runtime_start + pd.Timedelta(days=_runtime_days)

# =========================================================
# 4. 鍏変紡閰嶇疆
# =========================================================
PV_CAPACITY_MAP = {
    "绂忓缓淇婃澃鏂版潗鏂欑鎶€鑲′唤鏈夐檺鍏徃": 2.0,
    "绂忓缓鐪佽巻鐢板競鏂板叴杈鹃ゲ鏂欐湁闄愬叕鍙?: 0.9,
    "绂忓窞瓒呭簱椴滅敓渚涘簲閾剧鐞嗘湁闄愬叕鍙?: 0.4,
    "绂忓缓鐪佸痉鍖栧湥鍏夊伐鑹烘湁闄愬叕鍙?: 0.4,
}
PV_EFFICIENCY = 0.75
PV_TEMP_COEFF = -0.004

# =========================================================
# 5. 鑺傚亣鏃ラ厤缃?# =========================================================
HOLIDAY_MAP = {
    "2024-01-01": "鍏冩棪", "2024-02-10": "鏄ヨ妭", "2024-02-11": "鏄ヨ妭", "2024-02-12": "鏄ヨ妭",
    "2024-02-13": "鏄ヨ妭", "2024-02-14": "鏄ヨ妭", "2024-02-15": "鏄ヨ妭", "2024-02-16": "鏄ヨ妭", "2024-02-17": "鏄ヨ妭",
    "2024-04-04": "娓呮槑鑺?, "2024-04-05": "娓呮槑鑺?, "2024-04-06": "娓呮槑鑺?,
    "2024-05-01": "鍔冲姩鑺?, "2024-05-02": "鍔冲姩鑺?, "2024-05-03": "鍔冲姩鑺?, "2024-05-04": "鍔冲姩鑺?, "2024-05-05": "鍔冲姩鑺?,
    "2024-06-08": "绔崍鑺?, "2024-06-09": "绔崍鑺?, "2024-06-10": "绔崍鑺?,
    "2024-09-15": "涓鑺?, "2024-09-16": "涓鑺?, "2024-09-17": "涓鑺?,
    "2024-10-01": "鍥藉簡鑺?, "2024-10-02": "鍥藉簡鑺?, "2024-10-03": "鍥藉簡鑺?, "2024-10-04": "鍥藉簡鑺?,
    "2024-10-05": "鍥藉簡鑺?, "2024-10-06": "鍥藉簡鑺?, "2024-10-07": "鍥藉簡鑺?,
    "2025-01-01": "鍏冩棪", "2025-01-28": "鏄ヨ妭", "2025-01-29": "鏄ヨ妭", "2025-01-30": "鏄ヨ妭", "2025-01-31": "鏄ヨ妭",
    "2025-02-01": "鏄ヨ妭", "2025-02-02": "鏄ヨ妭", "2025-02-03": "鏄ヨ妭", "2025-02-04": "鏄ヨ妭",
    "2025-04-04": "娓呮槑鑺?, "2025-04-05": "娓呮槑鑺?, "2025-04-06": "娓呮槑鑺?,
    "2025-05-01": "鍔冲姩鑺?, "2025-05-02": "鍔冲姩鑺?, "2025-05-03": "鍔冲姩鑺?, "2025-05-04": "鍔冲姩鑺?, "2025-05-05": "鍔冲姩鑺?,
    "2025-05-31": "绔崍鑺?, "2025-06-01": "绔崍鑺?, "2025-06-02": "绔崍鑺?,
    "2025-10-01": "鍥藉簡鑺?, "2025-10-02": "鍥藉簡鑺?, "2025-10-03": "鍥藉簡鑺?, "2025-10-04": "鍥藉簡鑺?,
    "2025-10-05": "鍥藉簡鑺?, "2025-10-06": "鍥藉簡鑺?, "2025-10-07": "鍥藉簡鑺?, "2025-10-08": "涓鑺?,
    "2026-01-01": "鍏冩棪", "2026-02-17": "鏄ヨ妭", "2026-02-18": "鏄ヨ妭", "2026-02-19": "鏄ヨ妭", "2026-02-20": "鏄ヨ妭",
    "2026-02-21": "鏄ヨ妭", "2026-02-22": "鏄ヨ妭", "2026-02-23": "鏄ヨ妭",
    "2026-04-04": "娓呮槑鑺?, "2026-04-05": "娓呮槑鑺?, "2026-04-06": "娓呮槑鑺?,
    "2026-05-01": "鍔冲姩鑺?, "2026-05-02": "鍔冲姩鑺?, "2026-05-03": "鍔冲姩鑺?,
    "2026-06-19": "绔崍鑺?, "2026-06-20": "绔崍鑺?, "2026-06-21": "绔崍鑺?,
    "2026-09-25": "涓鑺?, "2026-09-26": "涓鑺?, "2026-09-27": "涓鑺?,
    "2026-10-01": "鍥藉簡鑺?, "2026-10-02": "鍥藉簡鑺?, "2026-10-03": "鍥藉簡鑺?, "2026-10-04": "鍥藉簡鑺?,
    "2026-10-05": "鍥藉簡鑺?, "2026-10-06": "鍥藉簡鑺?, "2026-10-07": "鍥藉簡鑺?,
}

ADJUST_WORKDAYS = set([
    "2024-02-04", "2024-02-18", "2024-04-07", "2024-04-28", "2024-05-11", "2024-09-14", "2024-09-29", "2024-10-12",
    "2025-01-26", "2025-02-08", "2025-04-27", "2025-09-28", "2025-10-11",
    "2026-02-15", "2026-02-28", "2026-04-26", "2026-05-09", "2026-09-27", "2026-10-10",
])

CITY_LAT_MAP = {"绂忓窞": 26.07, "瀹佸痉": 26.67, "鑾嗙敯": 25.45, "娉夊窞": 24.87}
WEATHER_SHEET_CITY_MAP = {
    "瀹佸痉_淇婃澃": "瀹佸痉", "鑾嗙敯_鏂板叴杈?: "鑾嗙敯", "绂忓窞_瓒呭簱椴滅敓": "绂忓窞", "娉夊窞_寰峰寲鍦ｅ厜": "娉夊窞",
    "7鏈?鏃?: None, "7鏈?鏃?: None,
}

def calculate_clear_sky_radiation(lat, day_of_year, hour):
    """璁＄畻鐞嗚鏅寸┖姘村钩闈㈡€昏緪灏?(W/m2)"""
    decl = 23.45 * np.sin(np.radians(360.0 / 365.0 * (284 + day_of_year)))
    solar_time = hour + 0.5
    hour_angle = (solar_time - 12.0) * 15.0
    lat_rad = np.radians(lat)
    decl_rad = np.radians(decl)
    ha_rad = np.radians(hour_angle)
    cos_zenith = np.sin(lat_rad) * np.sin(decl_rad) + np.cos(lat_rad) * np.cos(decl_rad) * np.cos(ha_rad)
    if cos_zenith <= 0:
        return 0.0
    S0 = 1367.0
    ecc = 1.0 + 0.033 * np.cos(2.0 * np.pi * day_of_year / 365.0)
    G0 = S0 * ecc * cos_zenith
    return G0 * 0.75

# =========================================================
# 6. 閫氱敤鍑芥暟
# =========================================================
def normalize_text(x):
    if pd.isna(x):
        return None
    x = str(x).strip().replace("\u3000", "").replace(" ", "")
    return x

def safe_read_table(path):
    path = str(path)
    if path.lower().endswith(".csv"):
        try:
            return pd.read_csv(path, encoding="utf-8-sig")
        except Exception:
            try:
                return pd.read_csv(path, encoding="gbk")
            except Exception:
                return pd.read_csv(path)
    else:
        return pd.read_excel(path)

def convert_yes_no(x):
    x = normalize_text(x)
    if x in ["鏄?, "鏈?, "1", "true", "True", "Y", "y"]:
        return 1
    return 0

def clean_col_name(c):
    c = str(c).strip().replace(" ", "").replace("\n", "").replace("\r", "").replace("\t", "")
    c = c.replace("锛?, "(").replace("锛?, ")").replace("锛?, ":")
    return c

def extract_city_district(region_text):
    if pd.isna(region_text):
        return None, None
    txt = str(region_text).strip().replace("鈥?, "-").replace("锛?, "-").replace("C", "-")
    parts = re.split(r"[\/\\\-\_\s]+", txt)
    parts = [p for p in parts if p]
    city, district = None, None
    if len(parts) >= 3:
        city = parts[-2]; district = parts[-1]
    elif len(parts) == 2:
        city = parts[-1]
    elif len(parts) == 1:
        city = parts[0]
    return city, district


def get_weather_file_priority(file_path):
    """Later forecast batch wins when duplicate city-hour weather exists."""
    name = Path(file_path).stem
    match = re.search(r"_(\d{8})-(\d{8})$", name)
    if match:
        return int(match.group(2))
    if re.search(r"\d{8}", name):
        return int(re.findall(r"\d{8}", name)[-1])
    return -1


PROPERTY_USER_KEYWORDS = ["瀹夋嵎鐗╀笟", "鍏冨叴鐗╀笟", "璞″洯琛楅亾"]
ENERGY_USER_KEYWORDS = ["娲ュお", "娲ユ嘲"]
LOW_LOAD_GUARD_USERS = ["涓夋竻"]


def normalize_user_type_tag(tag_text):
    text = normalize_text(tag_text) or ""
    if "鐗╀笟" in text or "鍥尯" in text:
        return "property"
    if "鑳芥簮" in text or "鍏呯數" in text:
        return "energy"
    return "industrial"


def infer_user_type_group(user_name, tag_text):
    name_text = normalize_text(user_name) or ""
    tag_group = normalize_user_type_tag(tag_text)
    if any(key in name_text for key in PROPERTY_USER_KEYWORDS):
        return "property"
    if any(key in name_text for key in ENERGY_USER_KEYWORDS):
        return "energy"
    if tag_group in {"property", "energy"}:
        return tag_group
    return "industrial"

# =========================================================
# 7. 鑺傚亣鏃ュ拰鏃堕棿鐗瑰緛锛堜笌璁粌涓€鑷达級
# =========================================================
def add_holiday_features(df):
    df = df.copy()
    ds = pd.to_datetime(df["datetime"]).dt.normalize().dt.strftime("%Y-%m-%d")
    date_only = pd.to_datetime(df["datetime"]).dt.normalize()
    df["is_holiday"] = ds.isin(HOLIDAY_MAP.keys()).astype(int)
    df["holiday_name"] = ds.map(HOLIDAY_MAP).fillna("闈炶妭鍋囨棩")
    df["is_adjust_workday"] = ds.isin(ADJUST_WORKDAYS).astype(int)
    weekend = (pd.to_datetime(df["datetime"]).dt.weekday >= 5).astype(int)
    df["is_real_restday"] = np.where(
        (df["is_holiday"] == 1) | ((weekend == 1) & (df["is_adjust_workday"] == 0)), 1, 0)
    df["is_month_start"] = df["datetime"].dt.day.isin([1, 2, 3]).astype(int)
    month_end_days = df["datetime"].dt.days_in_month
    df["is_month_end"] = ((month_end_days - df["datetime"].dt.day).isin([0, 1, 2])).astype(int)
    holiday_dates = sorted(pd.to_datetime(list(HOLIDAY_MAP.keys())))
    before_holiday_dates = set([(d - pd.Timedelta(days=1)).normalize() for d in holiday_dates])
    after_holiday_dates = set([(d + pd.Timedelta(days=1)).normalize() for d in holiday_dates])
    df["is_before_holiday"] = date_only.isin(before_holiday_dates).astype(int)
    df["is_after_holiday"] = date_only.isin(after_holiday_dates).astype(int)
    return df


def load_user_master_v41():
    df = load_user_master().copy()
    name_candidates = [c for c in df.columns if "鐢ㄦ埛鍚嶇О" in str(c)]
    type_candidates = [c for c in df.columns if "绫诲瀷" in str(c) and "鏍囩" in str(c)]
    name_col = name_candidates[0] if name_candidates else df.columns[1]
    type_col = type_candidates[0] if type_candidates else None
    if type_col is None:
        df["user_type_group"] = df[name_col].apply(lambda x: infer_user_type_group(x, ""))
    else:
        df["user_type_group"] = df.apply(
            lambda row: infer_user_type_group(row[name_col], row[type_col]),
            axis=1,
        )
    df["is_property_user"] = (df["user_type_group"] == "property").astype(int)
    df["is_energy_user"] = (df["user_type_group"] == "energy").astype(int)
    df["is_industrial_user"] = (df["user_type_group"] == "industrial").astype(int)
    return df

def add_time_behavior_features(df):
    df = df.copy()
    df["month"] = df["datetime"].dt.month
    df["day"] = df["datetime"].dt.day
    df["hour"] = df["datetime"].dt.hour
    df["weekday"] = df["datetime"].dt.weekday + 1
    df["is_weekend"] = (df["datetime"].dt.weekday >= 5).astype(int)
    df["is_workday"] = np.where((df["is_real_restday"] == 0) | (df["is_adjust_workday"] == 1), 1, 0)
    df["is_active_hour"] = ((df["hour"] >= 8) & (df["hour"] <= 22)).astype(int)
    df["is_workhour"] = ((df["hour"] >= 8) & (df["hour"] <= 19)).astype(int)
    df["is_daytime_8_19"] = ((df["hour"] >= 8) & (df["hour"] <= 19)).astype(int)

    df["is_morning_ramp"] = ((df["hour"] >= 8) & (df["hour"] <= 10)).astype(int)
    df["is_lunch_time"] = ((df["hour"] >= 11) & (df["hour"] <= 13)).astype(int)
    df["is_evening_peak"] = ((df["hour"] >= 18) & (df["hour"] <= 22)).astype(int)

    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24.0)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24.0)
    weekday0 = df["weekday"] - 1
    df["weekday_sin"] = np.sin(2 * np.pi * weekday0 / 7.0)
    df["weekday_cos"] = np.cos(2 * np.pi * weekday0 / 7.0)
    return df

# =========================================================
# 8. 涓绘。妗堣鍙?# =========================================================
def load_user_master():
    log("璇诲彇鐢ㄦ埛涓绘。妗堣〃...")
    df = safe_read_table(USER_MASTER_PATH)
    df.columns = [str(c).strip() for c in df.columns]
    df["鐢ㄦ埛鍚嶇О_norm"] = df["鐢ㄦ埛鍚嶇О"].apply(normalize_text)
    df["鏄惁鏈夊厜浼廮flag"] = df["鏄惁鏈夊厜浼?].apply(convert_yes_no)
    df["pv_capacity"] = df["鐢ㄦ埛鍚嶇О"].map(PV_CAPACITY_MAP).fillna(0)
    log(f"鐢ㄦ埛涓绘。妗堣〃璇诲彇瀹屾垚锛屽叡 {len(df)} 鏉?)
    return df

# =========================================================
# 9. 璇诲彇棰勬祴澶╂皵锛堝寘鍚瘡鏃ラ娴嬫牸寮忥級
# =========================================================
def load_prediction_weather():
    """璇诲彇棰勬祴澶╂皵"""
    log("璇诲彇棰勬祴澶╂皵...")
    weather_files = (
        glob.glob(str(WEATHER_DIR / "*.xlsx")) +
        glob.glob(str(WEATHER_DIR / "*.xls"))
    )
    weather_files = sorted(weather_files, key=get_weather_file_priority)
    all_records = []

    for fp in weather_files:
        fname = Path(fp).name
        source_priority = get_weather_file_priority(fp)
        try:
            xls = pd.ExcelFile(fp)
        except Exception as e:
            log(f"  [閿欒] 鎵撳紑澶辫触: {e}")
            continue

        for sheet_name in xls.sheet_names:
            try:
                if re.search(r"\d+鏈圽d+鏃?, sheet_name):
                    parsed = _parse_prediction_weather_sheet(fp, sheet_name, xls, source_priority)
                    if parsed is not None and len(parsed) > 0:
                        all_records.extend(parsed)
                        log(f"  瑙ｆ瀽棰勬祴澶╂皵: {sheet_name} -> {len(parsed)} 鏉?)
                else:
                    df = pd.read_excel(fp, sheet_name=sheet_name, header=None)
                    if len(df) > 1 and "鍙橀噺" in str(df.iloc[1, 0]):
                        city = WEATHER_SHEET_CITY_MAP.get(sheet_name)
                        if city is None:
                            for key in WEATHER_SHEET_CITY_MAP:
                                if key in sheet_name:
                                    city = WEATHER_SHEET_CITY_MAP[key]
                                    break
                        if city is None:
                            continue
                        i = 0
                        while i < len(df):
                            row0 = str(df.iloc[i, 0]).strip()
                            date_match = re.match(r"(\d+)鏈?\d+)鏃s*\|", row0)
                            if not date_match:
                                i += 1
                                continue
                            month = int(date_match.group(1))
                            day = int(date_match.group(2))
                            year = 2026
                            temp_row = i + 2
                            rad_row = i + 3
                            cloud_row = i + 4
                            hum_row = i + 5
                            rain_row = i + 6
                            for h in range(24):
                                dt = pd.Timestamp(year=year, month=month, day=day, hour=h)
                                temp = df.iloc[temp_row, h + 1] if temp_row < len(df) else np.nan
                                rad = df.iloc[rad_row, h + 1] if rad_row < len(df) else np.nan
                                cloud_val = df.iloc[cloud_row, h + 1] if cloud_row < len(df) else np.nan
                                hum = df.iloc[hum_row, h + 1] if hum_row < len(df) else np.nan
                                rain = df.iloc[rain_row, h + 1] if rain_row < len(df) else np.nan
                                all_records.append({
                                    "鎵€鍦ㄥ競_norm": city,
                                    "datetime": dt,
                                    "temperature": pd.to_numeric(temp, errors="coerce"),
                                    "shortwave_radiation": pd.to_numeric(rad, errors="coerce"),
                                    "cloud": pd.to_numeric(cloud_val, errors="coerce"),
                                    "humidity": pd.to_numeric(hum, errors="coerce"),
                                    "rainfall": pd.to_numeric(rain, errors="coerce"),
                                    "__source_priority": source_priority,
                                    "__source_file": fname,
                                })
                            i += 8
            except Exception as e:
                log(f"  [閿欒] 瑙ｆ瀽 {sheet_name} 澶辫触: {e}")
                continue

    if not all_records:
        raise ValueError("娌℃湁鎴愬姛瑙ｆ瀽浠讳綍鏈夋晥棰勬祴澶╂皵鏁版嵁")

    weather_df = pd.DataFrame(all_records)
    weather_df["datetime"] = pd.to_datetime(weather_df["datetime"]).dt.floor("h")
    weather_df = weather_df.sort_values(["鎵€鍦ㄥ競_norm", "datetime", "__source_priority"]).drop_duplicates(
        subset=["鎵€鍦ㄥ競_norm", "datetime"], keep="last").reset_index(drop=True)

    mask = (weather_df["datetime"] >= PREDICT_START_TS) & (weather_df["datetime"] < PREDICT_END_TS)
    weather_pred_df = weather_df[mask].reset_index(drop=True)

    log(f"棰勬祴澶╂皵璇诲彇瀹屾垚锛屽叡 {len(weather_pred_df)} 鏉★紙鍦ㄩ娴嬪尯闂村唴锛?)
    if "__source_file" in weather_pred_df.columns:
        used_files = sorted(weather_pred_df["__source_file"].dropna().unique().tolist())
        log(f"澶╂皵鍘婚噸鍚庡疄闄呴噰鐢ㄦ枃浠? {used_files}")
    return weather_pred_df


def _parse_prediction_weather_sheet(fp, sheet_name, xls, source_priority):
    """瑙ｆ瀽棰勬祴鏃ュぉ姘旀牸寮忥紙fujian_pv_daily鏍煎紡锛?""
    try:
        df = pd.read_excel(fp, sheet_name=sheet_name, header=None)
        date_match = re.match(r"(\d+)鏈?\d+)鏃?, sheet_name)
        if not date_match:
            return None
        month = int(date_match.group(1))
        day = int(date_match.group(2))
        year = 2026

        records = []
        i = 0
        while i < len(df):
            header = str(df.iloc[i, 0]).strip()
            if header == "nan" or not header:
                i += 1
                continue
            city_name = None
            for c in CITY_LAT_MAP.keys():
                if c in header:
                    city_name = c
                    break
            if city_name is None:
                i += 1
                continue

            temp_row = i + 2 if i + 2 < len(df) else None
            rad_row = i + 3 if i + 3 < len(df) else None

            for h in range(24):
                dt = pd.Timestamp(year=year, month=month, day=day, hour=h)
                col = h + 1
                temp = pd.to_numeric(df.iloc[temp_row, col], errors="coerce") if temp_row is not None else np.nan
                rad = pd.to_numeric(df.iloc[rad_row, col], errors="coerce") if rad_row is not None else np.nan

                records.append({
                    "鎵€鍦ㄥ競_norm": city_name,
                    "datetime": dt,
                    "temperature": temp,
                    "shortwave_radiation": rad,
                    "cloud": np.nan,
                    "humidity": np.nan,
                    "rainfall": np.nan,
                    "__source_priority": source_priority,
                    "__source_file": Path(fp).name,
                })

            i += 5

        return records
    except Exception:
        return None

# =========================================================
# 10. 鏋勫缓棰勬祴楠ㄦ灦
# =========================================================
def build_prediction_skeleton(user_master_df, weather_pred_df):
    """瀵规瘡涓敤鎴凤紝姣忎釜棰勬祴鏃舵鐢熸垚楠ㄦ灦"""
    log("鏋勫缓棰勬祴楠ㄦ灦...")
    all_records = []

    uid_to_city = {}
    for _, row in user_master_df.iterrows():
        uid_to_city[row["鐢ㄦ埛缂栧彿"]] = normalize_text(row["鎵€鍦ㄥ競"])

    uid_to_pvcap = dict(zip(user_master_df["鐢ㄦ埛缂栧彿"], user_master_df["pv_capacity"]))
    uid_to_name = dict(zip(user_master_df["鐢ㄦ埛缂栧彿"], user_master_df["鐢ㄦ埛鍚嶇О"]))
    uid_to_group = dict(zip(user_master_df["鐢ㄦ埛缂栧彿"], user_master_df["user_type_group"]))
    uid_to_property = dict(zip(user_master_df["鐢ㄦ埛缂栧彿"], user_master_df["is_property_user"]))
    uid_to_energy = dict(zip(user_master_df["鐢ㄦ埛缂栧彿"], user_master_df["is_energy_user"]))
    uid_to_industrial = dict(zip(user_master_df["鐢ㄦ埛缂栧彿"], user_master_df["is_industrial_user"]))

    for _, weather_row in weather_pred_df.iterrows():
        city = weather_row["鎵€鍦ㄥ競_norm"]
        dt = weather_row["datetime"]
        for uid, user_city in uid_to_city.items():
            if user_city == city:
                all_records.append({
                    "鐢ㄦ埛缂栧彿": uid,
                    "鐢ㄦ埛鍚嶇О": uid_to_name[uid],
                    "datetime": dt,
                    "鎵€鍦ㄥ競_norm": city,
                    "pv_capacity": uid_to_pvcap[uid],
                    "user_type_group": uid_to_group[uid],
                    "is_property_user": uid_to_property[uid],
                    "is_energy_user": uid_to_energy[uid],
                    "is_industrial_user": uid_to_industrial[uid],
                })

    skeleton_df = pd.DataFrame(all_records)
    skeleton_df = skeleton_df.merge(
        weather_pred_df[["鎵€鍦ㄥ競_norm", "datetime", "temperature", "shortwave_radiation",
                         "cloud", "humidity", "rainfall"]],
        on=["鎵€鍦ㄥ競_norm", "datetime"], how="left")

    # 纭繚鎺掑簭锛氭寜鐢ㄦ埛缂栧彿 + 鏃堕棿鎺掑簭锛屼繚璇佸悗缁?groupby 杩唬椤哄簭涓€鑷?    skeleton_df = skeleton_df.sort_values(["鐢ㄦ埛缂栧彿", "datetime"]).reset_index(drop=True)

    log(f"棰勬祴楠ㄦ灦鏋勫缓瀹屾垚锛屽叡 {len(skeleton_df)} 鏉?)
    return skeleton_df

# =========================================================
# 11. 浠庡巻鍙茶幏鍙栨粸鍚庣壒寰侊紙闈為€掑綊鏂规锛屼慨澶嶅榻愰棶棰橈級
# =========================================================
def _get_lag_from_history(pred_df, history_df, lag_hours):
    """
    浠庡巻鍙叉暟鎹幏鍙栨粸鍚庣壒寰侊紝杩斿洖涓?pred_df 瀵归綈鐨?list銆?    绛栫暐锛?    1. 绮剧‘鍖归厤 lag_dt
    2. 涓婂懆鍚屽ぉ鍚屽皬鏃讹紙卤1澶╋級
    3. 鏈€杩戝悓灏忔椂锛堟渶杩?鏉″潎鍊硷級
    4. 缁濆鍏滃簳锛氳鐢ㄦ埛鏈€杩戜竴鏉℃暟鎹?    """
    value_col = "total_load" if "total_load" in history_df.columns else "load"
    results = []
    for _, row in pred_df.iterrows():
        uid = row["鐢ㄦ埛缂栧彿"]
        target_dt = row["datetime"]
        lag_dt = target_dt - pd.Timedelta(hours=lag_hours)
        hist_user = history_df[history_df["鐢ㄦ埛缂栧彿"] == uid]

        # 1. 绮剧‘鍖归厤
        match = hist_user[hist_user["datetime"] == lag_dt]
        if len(match) > 0:
            results.append(match.iloc[0][value_col])
            continue

        # 2. 涓婂懆鍚屽ぉ鍚屽皬鏃讹紙卤1澶╋級
        lag_dt_week = target_dt - pd.Timedelta(days=7)
        match_week = hist_user[
            (hist_user["datetime"].dt.hour == lag_dt.hour) &
            (abs((hist_user["datetime"] - lag_dt_week).dt.days) <= 1)
        ]
        if len(match_week) > 0:
            results.append(match_week[value_col].mean())
            continue

        # 3. 鏈€杩戝悓灏忔椂锛堟渶杩?鏉★級
        match_hour = hist_user[hist_user["datetime"].dt.hour == lag_dt.hour]
        if len(match_hour) > 0:
            results.append(match_hour[value_col].tail(5).mean())
            continue

        # 4. 缁濆鍏滃簳锛氳鐢ㄦ埛鏈€杩戜竴鏉℃暟鎹?        hist_user_sorted = hist_user.sort_values("datetime")
        if len(hist_user_sorted) > 0:
            results.append(hist_user_sorted.iloc[-1][value_col])
        else:
            results.append(np.nan)

    return results


def _compute_rolling_from_history(hist_user, pred_g, window_size, stat_func):
    """
    浠庡巻鍙叉暟鎹绠楁粴鍔ㄧ粺璁°€?    浼樺厛浣跨敤鏃堕棿绐楀彛锛堟渶杩?window_size 灏忔椂锛夛紝
    濡傛灉鏃堕棿绐楀彛涓虹┖锛堟暟鎹┖绐楁湡锛夛紝鍒欏洖閫€鍒版渶杩?window_size 鏉℃暟鎹€?    """
    value_col = "total_load" if "total_load" in hist_user.columns else "load"
    results = []
    for _, row in pred_g.iterrows():
        target_dt = row["datetime"]
        window_end = target_dt - pd.Timedelta(hours=1)
        window_start = window_end - pd.Timedelta(hours=window_size)

        # 鏃堕棿绐楀彛
        window = hist_user[(hist_user["datetime"] > window_start) & (hist_user["datetime"] <= window_end)]
        if len(window) == 0:
            # 鍥為€€锛氫娇鐢ㄦ渶杩?window_size 鏉℃暟鎹?            hist_sorted = hist_user.sort_values("datetime")
            window = hist_sorted.tail(window_size)

        if len(window) > 0:
            results.append(stat_func(window[value_col]))
        else:
            results.append(np.nan)
    return results


def _compute_same_hour_from_history(hist_user, pred_g, n_records):
    """浠庡巻鍙叉暟鎹彇鏈€杩?N 鏉″悓灏忔椂璁板綍"""
    value_col = "total_load" if "total_load" in hist_user.columns else "load"
    results = []
    hist_same_hour = hist_user[hist_user["datetime"].dt.hour == pred_g.iloc[0]["datetime"].hour] if len(pred_g) > 0 else pd.DataFrame()
    for _, row in pred_g.iterrows():
        h = row["datetime"].hour
        sh = hist_user[hist_user["datetime"].dt.hour == h]
        val = sh.tail(n_records)[value_col].mean() if len(sh) > 0 else np.nan
        results.append(val)
    return results

# =========================================================
# 12. 鐗瑰緛宸ョ▼锛堜笌璁粌涓€鑷达紝淇绌虹獥鏈熼棶棰橈級
# =========================================================
def build_prediction_features(skeleton_df, history_df):
    """鐢熸垚棰勬祴鐗瑰緛锛屾墍鏈夌壒寰侀兘浠庡巻鍙叉暟鎹潪閫掑綊璁＄畻"""
    log("鐢熸垚棰勬祴鐗瑰緛锛圴3.1锛?..")
    df = skeleton_df.copy()
    df = add_holiday_features(df)
    df = add_time_behavior_features(df)

    # 娲剧敓姘旇薄鐗瑰緛
    for c in ["rainfall", "cloud", "shortwave_radiation"]:
        if c not in df.columns:
            df[c] = np.nan

    df["cooling_degree"] = np.maximum(df["temperature"] - 24, 0)
    df["heating_degree"] = np.maximum(18 - df["temperature"], 0)
    df["is_rainy"] = (df["rainfall"] > 0).astype(int)
    df["rainfall_intensity"] = np.where(df["rainfall"] > 0, df["rainfall"], 0)
    df["is_high_humidity"] = (df["humidity"] > 80).astype(int)
    dew = df["dew_point"].fillna(df["temperature"] - 5) if "dew_point" in df.columns else (df["temperature"] - 5)
    df["temp_humidity_index"] = df["temperature"] + 0.555 * (
        6.11 * np.exp(5417.753 * (1/273.16 - 1/(dew + 273.15))) - 10)
    df["temp_squared"] = df["temperature"] ** 2
    df["humidity_squared"] = df["humidity"] ** 2
    df["cloud_squared"] = df["cloud"] ** 2
    df["radiation_squared"] = df["shortwave_radiation"] ** 2
    df["property_cooling_degree"] = df["is_property_user"] * np.maximum(df["temperature"] - 26, 0)
    df["property_hot_degree"] = df["is_property_user"] * np.maximum(df["temperature"] - 28, 0)
    df["property_workhour_hot"] = df["property_hot_degree"] * df["is_workhour"]
    df["property_active_hour_hot"] = df["property_hot_degree"] * df["is_active_hour"]
    df["energy_cooling_degree"] = df["is_energy_user"] * np.maximum(df["temperature"] - 24, 0)
    df["energy_active_hour_hot"] = df["energy_cooling_degree"] * df["is_active_hour"]
    # ===== 婊炲悗鐗瑰緛锛堜粠鍘嗗彶鑾峰彇锛岄潪閫掑綊锛?====
    for lag in [24, 48, 168]:
        df[f"load_lag_{lag}"] = _get_lag_from_history(df, history_df, lag)

    # ===== 婊氬姩缁熻锛堜慨澶嶏細绌虹獥鏈熷洖閫€鍒版渶杩慛鏉℃暟鎹級=====
    roll_mean_24, roll_std_24, roll_mean_168, roll_std_168 = [], [], [], []
    roll_max_24, roll_min_24, roll_median_24 = [], [], []

    for uid, g in df.groupby("鐢ㄦ埛缂栧彿"):
        hist_user = history_df[history_df["鐢ㄦ埛缂栧彿"] == uid].sort_values("datetime")

        # 24灏忔椂绐楀彛
        rm24 = _compute_rolling_from_history(hist_user, g, 24, lambda x: x.mean())
        rs24 = _compute_rolling_from_history(hist_user, g, 24, lambda x: x.std() if len(x) >= 2 else np.nan)
        rmax24 = _compute_rolling_from_history(hist_user, g, 24, lambda x: x.max())
        rmin24 = _compute_rolling_from_history(hist_user, g, 24, lambda x: x.min())
        rmed24 = _compute_rolling_from_history(hist_user, g, 24, lambda x: x.median())

        # 168灏忔椂绐楀彛
        rm168 = _compute_rolling_from_history(hist_user, g, 168, lambda x: x.mean())
        rs168 = _compute_rolling_from_history(hist_user, g, 168, lambda x: x.std() if len(x) >= 2 else np.nan)

        roll_mean_24.extend(rm24)
        roll_std_24.extend(rs24)
        roll_mean_168.extend(rm168)
        roll_std_168.extend(rs168)
        roll_max_24.extend(rmax24)
        roll_min_24.extend(rmin24)
        roll_median_24.extend(rmed24)

    df["load_roll_mean_24"] = roll_mean_24
    df["load_roll_std_24"] = roll_std_24
    df["load_roll_mean_168"] = roll_mean_168
    df["load_roll_std_168"] = roll_std_168
    df["load_roll_max_24"] = roll_max_24
    df["load_roll_min_24"] = roll_min_24
    df["load_roll_median_24"] = roll_median_24

    # ===== 鍚屽皬鏃跺潎鍊?=====
    same_hour_3d, same_hour_7d, same_hour_14d = [], [], []
    for uid, g in df.groupby("鐢ㄦ埛缂栧彿"):
        hist_user = history_df[history_df["鐢ㄦ埛缂栧彿"] == uid]
        sh3 = _compute_same_hour_from_history(hist_user, g, 3)
        sh7 = _compute_same_hour_from_history(hist_user, g, 7)
        sh14 = _compute_same_hour_from_history(hist_user, g, 14)
        same_hour_3d.extend(sh3)
        same_hour_7d.extend(sh7)
        same_hour_14d.extend(sh14)

    df["load_same_hour_mean_3d"] = same_hour_3d
    df["load_same_hour_mean_7d"] = same_hour_7d
    df["load_same_hour_mean_14d"] = same_hour_14d

    # ===== 鍚屾槦鏈熷嚑鍚屽皬鏃?=====
    same_weekday_hour_4, same_weekday_hour_8 = [], []
    for uid, g in df.groupby("鐢ㄦ埛缂栧彿"):
        hist_user = history_df[history_df["鐢ㄦ埛缂栧彿"] == uid]
        for _, row in g.iterrows():
            h = row["datetime"].hour
            wd = row["datetime"].weekday()
            past_sw = hist_user[(hist_user["datetime"].dt.hour == h) & (hist_user["datetime"].dt.weekday == wd)]
            value_col = "total_load" if "total_load" in past_sw.columns else "load"
            sw4 = past_sw.tail(4)[value_col].mean() if len(past_sw) > 0 else np.nan
            sw8 = past_sw.tail(8)[value_col].mean() if len(past_sw) > 0 else np.nan
            same_weekday_hour_4.append(sw4)
            same_weekday_hour_8.append(sw8)
    df["load_same_weekday_hour_mean_4"] = same_weekday_hour_4
    df["load_same_weekday_hour_mean_8"] = same_weekday_hour_8

    # ===== 宸ヤ綔鏃?浼戞伅鏃ュ悓灏忔椂 =====
    workday_same_hour, restday_same_hour = [], []
    for uid, g in df.groupby("鐢ㄦ埛缂栧彿"):
        hist_user = history_df[history_df["鐢ㄦ埛缂栧彿"] == uid]
        for _, row in g.iterrows():
            h = row["datetime"].hour
            wd_past = hist_user[(hist_user["datetime"].dt.hour == h) & (hist_user["datetime"].dt.weekday < 5)]
            we_past = hist_user[(hist_user["datetime"].dt.hour == h) & (hist_user["datetime"].dt.weekday >= 5)]
            value_col = "total_load" if "total_load" in hist_user.columns else "load"
            workday_same_hour.append(wd_past.tail(5)[value_col].mean() if len(wd_past) > 0 else np.nan)
            restday_same_hour.append(we_past.tail(5)[value_col].mean() if len(we_past) > 0 else np.nan)
    df["workday_same_hour_mean_5"] = workday_same_hour
    df["restday_same_hour_mean_5"] = restday_same_hour

    # ===== 鏈€杩戝伐浣滄椂娈碉紙淇锛氱┖绐楁湡鍥為€€鍒版渶杩慛鏉″伐浣滄椂娈垫暟鎹級=====
    recent_workhour_3d, recent_workhour_7d = [], []
    for uid, g in df.groupby("鐢ㄦ埛缂栧彿"):
        hist_user = history_df[history_df["鐢ㄦ埛缂栧彿"] == uid].sort_values("datetime")
        hist_wh = hist_user[(hist_user["datetime"].dt.hour >= 8) & (hist_user["datetime"].dt.hour <= 19)]
        for _, row in g.iterrows():
            target_dt = row["datetime"]
            window_end = target_dt - pd.Timedelta(hours=1)
            window_3d_start = window_end - pd.Timedelta(days=3)
            window_7d_start = window_end - pd.Timedelta(days=7)

            past_wh_3d = hist_user[
                (hist_user["datetime"] > window_3d_start) & (hist_user["datetime"] <= window_end) &
                (hist_user["datetime"].dt.hour >= 8) & (hist_user["datetime"].dt.hour <= 19)
            ]
            past_wh_7d = hist_user[
                (hist_user["datetime"] > window_7d_start) & (hist_user["datetime"] <= window_end) &
                (hist_user["datetime"].dt.hour >= 8) & (hist_user["datetime"].dt.hour <= 19)
            ]

            # 绌虹獥鏈熷洖閫€鍒版渶杩慛鏉″伐浣滄椂娈垫暟鎹?            if len(past_wh_3d) == 0:
                past_wh_3d = hist_wh.tail(36)
            if len(past_wh_7d) == 0:
                past_wh_7d = hist_wh.tail(84)

            value_col = "total_load" if "total_load" in hist_user.columns else "load"
            recent_workhour_3d.append(past_wh_3d[value_col].mean() if len(past_wh_3d) > 0 else np.nan)
            recent_workhour_7d.append(past_wh_7d[value_col].mean() if len(past_wh_7d) > 0 else np.nan)
    df["recent_workhour_mean_3d"] = recent_workhour_3d
    df["recent_workhour_mean_7d"] = recent_workhour_7d

    # ===== 鍏変紡浜や簰鐗瑰緛 =====
    user_master = load_user_master_v41()
    pv_map = dict(zip(user_master["鐢ㄦ埛缂栧彿"], user_master["鏄惁鏈夊厜浼廮flag"]))
    df["鏄惁鏈夊厜浼廮flag"] = df["鐢ㄦ埛缂栧彿"].map(pv_map).fillna(0).astype(int)
    df["pv_radiation_effect"] = df["鏄惁鏈夊厜浼廮flag"] * df["shortwave_radiation"]
    df["pv_temp_effect"] = df["鏄惁鏈夊厜浼廮flag"] * df["temperature"]
    df["pv_temp_radiation_effect"] = df["鏄惁鏈夊厜浼廮flag"] * df["shortwave_radiation"] * df["temperature"]
    df["pv_daytime_radiation"] = df["鏄惁鏈夊厜浼廮flag"] * df["shortwave_radiation"] * df["is_active_hour"]
    df["pv_workhour_radiation"] = df["鏄惁鏈夊厜浼廮flag"] * df["shortwave_radiation"] * df["is_workhour"]

    # ===== V2.6 鏂板鐗瑰緛 =====
    df["day_of_year"] = df["datetime"].dt.dayofyear
    df["day_of_year_sin"] = np.sin(2 * np.pi * df["day_of_year"] / 365.0)
    df["day_of_year_cos"] = np.cos(2 * np.pi * df["day_of_year"] / 365.0)
    df["temperature_diff_1h"] = df.groupby("鐢ㄦ埛缂栧彿")["temperature"].diff(1)
    df["temperature_diff_24h"] = df.groupby("鐢ㄦ埛缂栧彿")["temperature"].diff(24)
    df["temp_humidity_interaction"] = df["temperature"] * df["humidity"]
    df["temp_cloud_interaction"] = df["temperature"] * df["cloud"]
    df["load_change_24_48"] = df["load_lag_24"] - df["load_lag_48"]

    def _get_city_lat(city_name):
        return CITY_LAT_MAP.get(str(city_name).strip(), 26.07)
    df["_city_lat"] = df["鎵€鍦ㄥ競_norm"].apply(_get_city_lat)
    df["clear_sky_index"] = df.apply(
        lambda row: calculate_clear_sky_radiation(row["_city_lat"], row["day_of_year"], row["hour"])
        if not pd.isna(row["shortwave_radiation"]) else np.nan, axis=1)
    df["clear_sky_index"] = np.where(df["clear_sky_index"] > 10,
                                     df["shortwave_radiation"] / df["clear_sky_index"], np.nan)
    df["clear_sky_index"] = df["clear_sky_index"].clip(0, 2.0)
    df = df.drop(columns=["_city_lat", "day_of_year"])

    # ===== V3.0 鍏変紡鍒嗚В =====
    df["pv_est"] = 0.0
    pv_mask = df["pv_capacity"] > 0
    df.loc[pv_mask, "pv_est"] = (
        df.loc[pv_mask, "pv_capacity"] * 1000 * PV_EFFICIENCY *
        (df.loc[pv_mask, "shortwave_radiation"] / 1000) *
        (1 + PV_TEMP_COEFF * (df.loc[pv_mask, "temperature"] - 25))
    )
    df["pv_est"] = df["pv_est"].clip(lower=0)

    # ===== 濉厖鎵€鏈?NaN =====
    with open(OUTPUT_MODEL / "available_features_v3.pkl", "rb") as f:
        available_features = pickle.load(f)

    for col in available_features:
        if col in df.columns and df[col].isna().any():
            med = df[col].median()
            if pd.isna(med):
                med = 0
            df[col] = df[col].fillna(med)

    log("V3.1棰勬祴鐗瑰緛鐢熸垚瀹屾垚")
    return df, available_features

# =========================================================
# 13. 缂栫爜棰勬祴鐗瑰緛锛堝榻愯缁冨垪锛?# =========================================================
def encode_prediction_features(pred_df, available_features, clf_meta):
    """瀵归綈璁粌鏃剁殑鍒楅『搴?""
    X = pred_df[available_features].copy()
    X = X.astype(float)
    train_columns = clf_meta["train_columns"]
    for c in train_columns:
        if c not in X.columns:
            X[c] = 0.0
    X = X[train_columns]
    return X


def _weighted_average(values, weights):
    valid_pairs = []
    for value, weight in zip(values, weights):
        if pd.notna(value) and float(value) > 0 and weight > 0:
            valid_pairs.append((float(value), float(weight)))
    if not valid_pairs:
        return np.nan
    total_weight = sum(weight for _, weight in valid_pairs)
    return sum(value * weight for value, weight in valid_pairs) / total_weight


def build_recent_anchor(row):
    day_type_anchor = row["workday_same_hour_mean_5"] if row.get("is_workday", 0) == 1 else row["restday_same_hour_mean_5"]
    values = [
        row["load_same_hour_mean_3d"],
        row["load_same_hour_mean_7d"],
        row["load_same_weekday_hour_mean_4"],
        day_type_anchor,
        row["recent_workhour_mean_3d"] if row.get("is_workhour", 0) == 1 else np.nan,
    ]
    weights = [0.35, 0.25, 0.20, 0.15, 0.05]
    return _weighted_average(values, weights)


def apply_recent_anchor_correction(feature_df):
    feature_df = feature_df.copy()
    feature_df["pred_total_load_raw"] = feature_df["pred_total_load"]
    feature_df["bias_anchor_load"] = feature_df.apply(build_recent_anchor, axis=1)
    feature_df["bias_alpha"] = 0.0

    user_route_mask = feature_df["model_route"].astype(str).str.startswith("user_")
    group_route_mask = feature_df["model_route"].astype(str).str.startswith(("property_", "energy_", "hour_"))
    low_route_mask = feature_df["model_route"] == "low_load_regressor"

    feature_df.loc[user_route_mask, "bias_alpha"] = USER_BIAS_BLEND
    feature_df.loc[group_route_mask, "bias_alpha"] = GROUP_BIAS_BLEND
    feature_df.loc[low_route_mask, "bias_alpha"] = LOW_LOAD_BIAS_BLEND

    valid_mask = (
        feature_df["pred_total_load_raw"].notna()
        & feature_df["bias_anchor_load"].notna()
        & feature_df["bias_alpha"].gt(0)
    )
    if not valid_mask.any():
        return feature_df

    raw_values = feature_df.loc[valid_mask, "pred_total_load_raw"].astype(float)
    anchor_values = feature_df.loc[valid_mask, "bias_anchor_load"].astype(float)
    ratio = (anchor_values / raw_values.replace(0, np.nan)).clip(BIAS_RATIO_MIN, BIAS_RATIO_MAX)
    ratio = ratio.replace([np.inf, -np.inf], np.nan).fillna(1.0)
    alpha = feature_df.loc[valid_mask, "bias_alpha"].astype(float)
    corrected = raw_values * (1.0 - alpha) + raw_values * ratio * alpha

    zero_raw_mask = valid_mask & feature_df["pred_total_load_raw"].le(0) & feature_df["bias_anchor_load"].gt(0)
    if zero_raw_mask.any():
        corrected.loc[zero_raw_mask[zero_raw_mask].index] = (
            feature_df.loc[zero_raw_mask, "bias_anchor_load"].astype(float)
            * feature_df.loc[zero_raw_mask, "bias_alpha"].astype(float)
        )

    feature_df.loc[valid_mask, "pred_total_load"] = corrected
    return feature_df

# =========================================================
# 14. 涓婚娴嬫祦绋?# =========================================================
def main():
    log("=== 开始V5.0预测：单用户优先 + 分组回退 + 近期锚点修正 ===")
    log(f"预测区间: {PREDICT_START_TS} to {PREDICT_END_TS}")

    log("加载模型...")
    with open(OUTPUT_MODEL / "low_load_classifier_v3.pkl", "rb") as f:
        clf_model = pickle.load(f)
    with open(OUTPUT_MODEL / "feature_meta_classifier_v3.pkl", "rb") as f:
        clf_meta = pickle.load(f)
    with open(OUTPUT_MODEL / "low_load_regressor_v3.pkl", "rb") as f:
        low_reg_model = pickle.load(f)
    with open(OUTPUT_MODEL / "feature_meta_low_reg_v3.pkl", "rb") as f:
        low_meta = pickle.load(f)
    with open(OUTPUT_MODEL / "normal_load_regressors_v3_dict.pkl", "rb") as f:
        normal_regressors = pickle.load(f)
    with open(OUTPUT_MODEL / "normal_reg_metas_v3_dict.pkl", "rb") as f:
        normal_metas = pickle.load(f)
    log("模型加载完成")

    history_path = OUTPUT_PROCESSED / "history_load_for_predict_v3.csv"
    if not history_path.exists():
        raise FileNotFoundError(f"未找到历史特征数据: {history_path}，请先运行训练脚本")
    history_df = pd.read_csv(history_path, encoding="utf-8-sig")
    history_df["datetime"] = pd.to_datetime(history_df["datetime"])
    log(f"读取历史负荷完成: {len(history_df)} 行")

    user_master_df = load_user_master_v41()
    weather_pred_df = load_prediction_weather()
    skeleton_df = build_prediction_skeleton(user_master_df, weather_pred_df)
    feature_df, available_features = build_prediction_features(skeleton_df, history_df)

    log("步骤1: 低负荷分类")
    X_clf = encode_prediction_features(feature_df, available_features, clf_meta)
    feature_df["proba_low"] = clf_model.predict_proba(X_clf)[:, 1]
    feature_df["is_low_load_pred"] = (feature_df["proba_low"] >= LOW_LOAD_PROBA_THRESHOLD).astype(int)

    guard_mask = feature_df["用户名称"].astype(str).apply(lambda x: any(k in x for k in LOW_LOAD_GUARD_USERS))
    guard_history_mask = (
        feature_df["load_same_hour_mean_14d"].fillna(0).ge(55)
        | feature_df["load_same_hour_mean_7d"].fillna(0).ge(55)
        | feature_df["recent_workhour_mean_7d"].fillna(0).ge(65)
    )
    guard_override_mask = guard_mask & guard_history_mask & (feature_df["proba_low"] < 0.999)
    if guard_override_mask.any():
        feature_df.loc[guard_override_mask, "is_low_load_pred"] = 0
        log(f"低负荷保护生效: {guard_override_mask.sum()} 个时段改走普通模型")

    low_count = int(feature_df["is_low_load_pred"].sum())
    normal_count = int((feature_df["is_low_load_pred"] == 0).sum())
    log(f"分类完成: 低负荷 {low_count} 条, 普通负荷 {normal_count} 条")

    log("步骤2: 低负荷回归")
    feature_df["pred_total_load"] = 0.0
    feature_df["model_route"] = "unassigned"
    low_mask = feature_df["is_low_load_pred"] == 1
    if low_mask.any():
        X_low = encode_prediction_features(feature_df.loc[low_mask], available_features, low_meta)
        feature_df.loc[low_mask, "pred_total_load"] = low_reg_model.predict(X_low)

        low_industrial_mask = low_mask & (feature_df["user_type_group"] == "industrial")
        if low_industrial_mask.any():
            industrial_floor = np.maximum(
                feature_df.loc[low_industrial_mask, "load_same_hour_mean_7d"].fillna(0) * 0.50,
                feature_df.loc[low_industrial_mask, "load_same_hour_mean_14d"].fillna(0) * 0.40,
            )
            industrial_floor = np.maximum(industrial_floor, 0.001)
            feature_df.loc[low_industrial_mask, "pred_total_load"] = np.maximum(
                feature_df.loc[low_industrial_mask, "pred_total_load"],
                industrial_floor,
            )

        feature_df.loc[low_mask, "model_route"] = "low_load_regressor"
        log(f"低负荷回归完成: {int(low_mask.sum())} 条")

    log("步骤3: 普通负荷按 单用户 -> 分组 -> 全局 路由")
    for h in range(24):
        hour_mask = (feature_df["hour"] == h) & (feature_df["is_low_load_pred"] == 0)
        if not hour_mask.any():
            continue

        hour_df = feature_df.loc[hour_mask].copy()
        predicted_indexes = set()

        for user_id, user_rows in hour_df.groupby("用户编号"):
            model_key = f"user_{user_id}_hour_{h}"
            if model_key not in normal_regressors:
                continue
            meta = normal_metas[model_key]
            X_user = encode_prediction_features(user_rows, available_features, meta)
            feature_df.loc[user_rows.index, "pred_total_load"] = normal_regressors[model_key].predict(X_user)
            feature_df.loc[user_rows.index, "model_route"] = model_key
            predicted_indexes.update(user_rows.index.tolist())
            log(f"  Hour {h:02d}:00 | user {user_id} -> {model_key}")

        remaining_df = hour_df.loc[~hour_df.index.isin(predicted_indexes)].copy() if predicted_indexes else hour_df
        for group_name, group_rows in remaining_df.groupby("user_type_group"):
            model_key = f"{group_name}_hour_{h}" if f"{group_name}_hour_{h}" in normal_regressors else f"hour_{h}"
            if model_key not in normal_regressors:
                log(f"  Warning: hour {h:02d}:00 无可用模型")
                continue
            meta = normal_metas[model_key]
            X_group = encode_prediction_features(group_rows, available_features, meta)
            feature_df.loc[group_rows.index, "pred_total_load"] = normal_regressors[model_key].predict(X_group)
            feature_df.loc[group_rows.index, "model_route"] = model_key
            log(f"  Hour {h:02d}:00 | {group_name} -> {model_key}")

    feature_df = apply_recent_anchor_correction(feature_df)

    log("步骤4: 光伏扣减并生成净负荷")
    feature_df["pred_total_load"] = feature_df["pred_total_load"].clip(lower=0)
    feature_df["pred_net_load"] = (feature_df["pred_total_load"] - feature_df["pv_est"]).clip(lower=0)
    feature_df["bias_anchor_load"] = feature_df["bias_anchor_load"].round(3)
    feature_df["pred_total_load_raw"] = feature_df["pred_total_load_raw"].round(3)
    feature_df["pv_est"] = feature_df["pv_est"].round(3)
    feature_df["pred_total_load"] = feature_df["pred_total_load"].round(3)
    feature_df["pred_net_load"] = feature_df["pred_net_load"].round(3)

    result_long = feature_df[[
        "用户编号", "用户名称", "datetime", "hour", "user_type_group", "model_route",
        "pv_capacity", "pv_est", "proba_low", "is_low_load_pred",
        "bias_anchor_load", "bias_alpha", "pred_total_load_raw", "pred_total_load", "pred_net_load"
    ]].copy()
    result_long_path = save_csv_with_fallback(result_long, OUTPUT_PREDICTION / "prediction_result_v3_long.csv")
    log(f"预测结果长表已保存: {result_long_path.name} | {len(result_long)} 行")

    pred_date = PREDICT_START_TS.strftime("%Y-%m-%d")
    pivot = result_long.pivot(index="用户名称", columns="hour", values="pred_net_load")
    pivot_mwh = (pivot / 1000.0).reindex(columns=range(24))
    hour_cols = [f"{h+1}:00" for h in range(24)]
    pivot_mwh.columns = hour_cols
    pivot_mwh = pivot_mwh.reset_index()
    pivot_mwh.insert(0, "序号", range(1, len(pivot_mwh) + 1))
    pivot_mwh["日合计"] = pivot_mwh[hour_cols].sum(axis=1)

    hourly_sum = pivot_mwh[hour_cols].sum(axis=0).tolist()
    daily_total = float(pivot_mwh["日合计"].sum())
    total_row = pd.DataFrame([{
        "序号": "",
        "用户名称": "24时段合计",
        **{hcol: hourly_sum[i] for i, hcol in enumerate(hour_cols)},
        "日合计": daily_total,
    }])
    pivot_mwh = pd.concat([pivot_mwh, total_row], ignore_index=True)
    pivot_mwh[hour_cols] = pivot_mwh[hour_cols].round(3)
    pivot_mwh["日合计"] = pivot_mwh["日合计"].round(3)

    wide_path = save_csv_with_fallback(pivot_mwh, OUTPUT_PREDICTION / f"prediction_{pred_date}_v3.csv")
    log(f"预测宽表已保存: {wide_path.name}")
    log(f"总预测电量: {daily_total:.3f} MWh")

    log("\n=== 预测摘要 ===")
    log(f"全网总关口电量: {daily_total:.3f} MWh")
    log(f"低负荷分类占比: {low_count}/{len(feature_df)} = {low_count/len(feature_df)*100:.1f}%")
    log(f"光伏总估算: {feature_df['pv_est'].sum()/1000:.3f} MWh")
    log(f"预测总负荷均值: {feature_df['pred_total_load'].mean():.3f} kW")
    log(f"预测净负荷均值: {feature_df['pred_net_load'].mean():.3f} kW")
    log("=== V5.0 预测完成 ===")

if __name__ == "__main__":
    main()
