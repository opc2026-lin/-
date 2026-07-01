# -*- coding: utf-8 -*-

import re
import glob
import pickle
import warnings
import numpy as np
import pandas as pd

from pathlib import Path
from sklearn.metrics import mean_absolute_error, mean_squared_error

warnings.filterwarnings("ignore")

try:
    from lightgbm import LGBMRegressor
    MODEL_NAME = "lightgbm"
except Exception:
    from sklearn.ensemble import RandomForestRegressor
    MODEL_NAME = "random_forest"


# =========================================================
# 1. 参数配置
# =========================================================
TARGET_USER_NAME = "福州年盛机电有限公司"

PREDICT_START = "2026-05-01 00:00:00"   # 左闭
PREDICT_END = "2026-06-01 00:00:00"     # 右开
TRAIN_MONTHS = 2

BIAS_LOOKBACK_DAYS = 14


# =========================================================
# 2. 路径配置
# =========================================================
BASE_DIR = Path(__file__).resolve().parent

USER_MASTER_PATH = BASE_DIR / "input" / "user_master" / "01_用户主档案表.csv"
WEATHER_DIR = BASE_DIR / "input" / "weather"
LOAD_DIR = BASE_DIR / "input" / "load"

OUTPUT_PROCESSED = BASE_DIR / "output" / "processed"
OUTPUT_MODEL = BASE_DIR / "output" / "model"
OUTPUT_PREDICTION = BASE_DIR / "output" / "prediction"
OUTPUT_LOGS = BASE_DIR / "output" / "logs"

for p in [OUTPUT_PROCESSED, OUTPUT_MODEL, OUTPUT_PREDICTION, OUTPUT_LOGS]:
    p.mkdir(parents=True, exist_ok=True)


# =========================================================
# 3. 日志
# =========================================================
SAFE_USER_NAME = TARGET_USER_NAME.replace("/", "_").replace("\\", "_")
LOG_FILE = OUTPUT_LOGS / f"01_train_single_user_{SAFE_USER_NAME}.log"


def log(msg):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")


with open(LOG_FILE, "w", encoding="utf-8") as f:
    f.write("=== 单用户训练日志 ===\n")


# =========================================================
# 4. 时间范围
# =========================================================
PREDICT_START_TS = pd.Timestamp(PREDICT_START)
PREDICT_END_TS = pd.Timestamp(PREDICT_END)
TRAIN_END = PREDICT_START_TS
TRAIN_START = PREDICT_START_TS - pd.DateOffset(months=TRAIN_MONTHS)


# =========================================================
# 5. 节假日配置
# =========================================================
HOLIDAY_MAP = {
    "2024-01-01": "元旦",
    "2024-02-10": "春节", "2024-02-11": "春节", "2024-02-12": "春节", "2024-02-13": "春节",
    "2024-02-14": "春节", "2024-02-15": "春节", "2024-02-16": "春节", "2024-02-17": "春节",
    "2024-04-04": "清明节", "2024-04-05": "清明节", "2024-04-06": "清明节",
    "2024-05-01": "劳动节", "2024-05-02": "劳动节", "2024-05-03": "劳动节", "2024-05-04": "劳动节", "2024-05-05": "劳动节",
    "2024-06-08": "端午节", "2024-06-09": "端午节", "2024-06-10": "端午节",
    "2024-09-15": "中秋节", "2024-09-16": "中秋节", "2024-09-17": "中秋节",
    "2024-10-01": "国庆节", "2024-10-02": "国庆节", "2024-10-03": "国庆节", "2024-10-04": "国庆节",
    "2024-10-05": "国庆节", "2024-10-06": "国庆节", "2024-10-07": "国庆节",

    "2025-01-01": "元旦",
    "2025-01-28": "春节", "2025-01-29": "春节", "2025-01-30": "春节", "2025-01-31": "春节",
    "2025-02-01": "春节", "2025-02-02": "春节", "2025-02-03": "春节", "2025-02-04": "春节",
    "2025-04-04": "清明节", "2025-04-05": "清明节", "2025-04-06": "清明节",
    "2025-05-01": "劳动节", "2025-05-02": "劳动节", "2025-05-03": "劳动节", "2025-05-04": "劳动节", "2025-05-05": "劳动节",
    "2025-05-31": "端午节", "2025-06-01": "端午节", "2025-06-02": "端午节",
    "2025-10-01": "国庆节", "2025-10-02": "国庆节", "2025-10-03": "国庆节", "2025-10-04": "国庆节",
    "2025-10-05": "国庆节", "2025-10-06": "国庆节", "2025-10-07": "国庆节", "2025-10-08": "中秋节",

    "2026-01-01": "元旦",
    "2026-02-17": "春节", "2026-02-18": "春节", "2026-02-19": "春节", "2026-02-20": "春节",
    "2026-02-21": "春节", "2026-02-22": "春节", "2026-02-23": "春节",
    "2026-04-04": "清明节", "2026-04-05": "清明节", "2026-04-06": "清明节",
    "2026-05-01": "劳动节", "2026-05-02": "劳动节", "2026-05-03": "劳动节",
    "2026-06-19": "端午节", "2026-06-20": "端午节", "2026-06-21": "端午节",
    "2026-09-25": "中秋节", "2026-09-26": "中秋节", "2026-09-27": "中秋节",
    "2026-10-01": "国庆节", "2026-10-02": "国庆节", "2026-10-03": "国庆节", "2026-10-04": "国庆节",
    "2026-10-05": "国庆节", "2026-10-06": "国庆节", "2026-10-07": "国庆节",
}

ADJUST_WORKDAYS = set([
    "2024-02-04", "2024-02-18", "2024-04-07", "2024-04-28", "2024-05-11", "2024-09-14", "2024-09-29", "2024-10-12",
    "2025-01-26", "2025-02-08", "2025-04-27", "2025-09-28", "2025-10-11",
    "2026-02-15", "2026-02-28", "2026-04-26", "2026-05-09", "2026-09-27", "2026-10-10",
])


# =========================================================
# 6. 工具函数
# =========================================================
def normalize_text(x):
    if pd.isna(x):
        return None
    x = str(x).strip()
    x = x.replace("　", "").replace(" ", "")
    return x


def normalize_region_name(x):
    x = normalize_text(x)
    if x is None:
        return None
    x = re.sub(r"(区|县|市)$", "", x)
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
    return pd.read_excel(path)


def convert_yes_no(x):
    x = normalize_text(x)
    if x in ["是", "有", "1", "true", "True", "Y", "y"]:
        return 1
    return 0


def clean_col_name(c):
    c = str(c).strip()
    c = c.replace(" ", "").replace("\n", "").replace("\r", "").replace("\t", "")
    c = c.replace("（", "(").replace("）", ")")
    c = c.replace("：", ":")
    return c


def extract_city_district(region_text):
    if pd.isna(region_text):
        return None, None

    txt = str(region_text).strip()
    txt = txt.replace("―", "-").replace("－", "-").replace("C", "-")
    parts = re.split(r"[\/\\\-\_\s]+", txt)
    parts = [p for p in parts if p]

    city, district = None, None
    if len(parts) >= 3:
        city = parts[-2]
        district = parts[-1]
    elif len(parts) == 2:
        city = parts[-1]
    elif len(parts) == 1:
        city = parts[0]

    return city, district


def parse_sheet_yy_m(sheet_name):
    s = str(sheet_name).strip()
    m = re.fullmatch(r"(\d{2})\.(\d{1,2})", s)
    if not m:
        return None
    yy = int(m.group(1))
    mm = int(m.group(2))
    year = 2000 + yy
    if mm < 1 or mm > 12:
        return None
    return year, mm


def in_train_sheet_range(sheet_name):
    ym = parse_sheet_yy_m(sheet_name)
    if ym is None:
        return False

    y, m = ym
    sheet_start = pd.Timestamp(year=y, month=m, day=1)
    sheet_end = sheet_start + pd.offsets.MonthBegin(1)

    return not (sheet_end <= TRAIN_START or sheet_start >= TRAIN_END)


# =========================================================
# 7. 用户主档案
# =========================================================
def load_user_master():
    log("读取用户主档案表...")
    df = safe_read_table(USER_MASTER_PATH)
    df.columns = [str(c).strip() for c in df.columns]

    required_cols = ["用户编号", "用户名称", "所在市", "所在区", "用户类型", "是否有光伏"]
    for c in required_cols:
        if c not in df.columns:
            raise ValueError(f"用户主档案表缺少字段: {c}")

    df["用户名称_norm"] = df["用户名称"].apply(normalize_text)
    df["所在市_norm"] = df["所在市"].apply(normalize_text)
    df["所在区_norm"] = df["所在区"].apply(normalize_region_name)
    df["是否有光伏_flag"] = df["是否有光伏"].apply(convert_yes_no)

    log(f"用户主档案表读取完成，共 {len(df)} 条")
    return df


# =========================================================
# 8. 负荷表清洗与解析
# =========================================================
def normalize_load_sheet(df):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    header_row_idx = None
    for i in range(min(len(df), 10)):
        row_values = [str(x).strip() for x in df.iloc[i].tolist()]
        joined = "".join(row_values)
        if ("电量年月日" in joined) and ("户号" in joined):
            header_row_idx = i
            break

    if header_row_idx is not None:
        new_header = [str(x).strip() for x in df.iloc[header_row_idx].tolist()]
        df = df.iloc[header_row_idx + 1:].copy()
        df.columns = new_header
    else:
        if "电量年月日" not in df.columns or "户号" not in df.columns:
            raise ValueError("未识别到负荷表头（电量年月日/户号）")

    df.columns = [str(c).strip() for c in df.columns]
    return df


def parse_one_load_sheet(file_path, sheet_name, user_info):
    raw = pd.read_excel(file_path, sheet_name=sheet_name, header=0)
    df = normalize_load_sheet(raw)

    required = ["电量年月日", "户号"]
    for c in required:
        if c not in df.columns:
            raise ValueError(f"{Path(file_path).name}-{sheet_name} 缺少字段: {c}")

    hour_cols = [f"{h}:00" for h in range(1, 25)]
    for c in hour_cols:
        if c not in df.columns:
            raise ValueError(f"{Path(file_path).name}-{sheet_name} 缺少小时列: {c}")

    df["电量年月日"] = df["电量年月日"].astype(str).str.strip()
    df = df[df["电量年月日"].str.fullmatch(r"\d{8}", na=False)].copy()
    if df.empty:
        return None

    long_df = df.melt(
        id_vars=["电量年月日", "户号"],
        value_vars=hour_cols,
        var_name="hour_str",
        value_name="load"
    )

    long_df["date"] = pd.to_datetime(long_df["电量年月日"], format="%Y%m%d", errors="coerce")
    long_df["load"] = pd.to_numeric(long_df["load"], errors="coerce")
    long_df["户号"] = long_df["户号"].astype(str).str.strip()

    def build_datetime(row):
        d = row["date"]
        h = int(str(row["hour_str"]).split(":")[0])
        if pd.isna(d):
            return pd.NaT
        if h == 24:
            return d + pd.Timedelta(days=1)
        return d + pd.Timedelta(hours=h)

    long_df["datetime"] = long_df.apply(build_datetime, axis=1)
    long_df["用户编号"] = user_info["用户编号"]
    long_df["用户名称"] = user_info["用户名称"]
    long_df["所在市"] = user_info["所在市"]
    long_df["所在区"] = user_info["所在区"]
    long_df["用户类型"] = user_info["用户类型"]
    long_df["是否有光伏"] = user_info["是否有光伏"]
    long_df["是否有光伏_flag"] = user_info["是否有光伏_flag"]

    out_cols = [
        "用户编号", "用户名称", "户号",
        "所在市", "所在区", "用户类型",
        "是否有光伏", "是否有光伏_flag",
        "date", "datetime", "load"
    ]

    return long_df[out_cols].dropna(subset=["datetime"]).sort_values("datetime")


# =========================================================
# 9. 读取单用户负荷
# =========================================================
def load_single_user_load(user_master_df):
    log(f"读取单用户负荷：{TARGET_USER_NAME}")

    target_norm = normalize_text(TARGET_USER_NAME)
    matched = user_master_df[user_master_df["用户名称_norm"] == target_norm]

    if matched.empty:
        raise ValueError(f"主档案表中未找到目标用户：{TARGET_USER_NAME}")

    user_info = matched.iloc[0]

    files = glob.glob(str(LOAD_DIR / "*.xlsx")) + glob.glob(str(LOAD_DIR / "*.xls"))
    target_file = None

    for fp in files:
        if normalize_text(Path(fp).stem) == target_norm:
            target_file = fp
            break

    if target_file is None:
        raise FileNotFoundError(f"未在 load 目录中找到该用户文件：{TARGET_USER_NAME}")

    xls = pd.ExcelFile(target_file)
    valid_sheets = [s for s in xls.sheet_names if in_train_sheet_range(s)]

    all_list = []
    account_value = None

    for s in valid_sheets:
        try:
            one = parse_one_load_sheet(target_file, s, user_info)
            if one is not None and not one.empty:
                all_list.append(one)
                if account_value is None and one["户号"].notna().any():
                    account_value = str(one["户号"].iloc[0]).strip()
                log(f"已读取负荷：{Path(target_file).name} - {s}")
        except Exception as e:
            log(f"[错误] 读取失败：{Path(target_file).name} - {s} -> {e}")

    if not all_list:
        raise ValueError(f"该用户未读取到任何有效训练负荷数据：{TARGET_USER_NAME}")

    df = pd.concat(all_list, ignore_index=True)
    df = df.sort_values("datetime").reset_index(drop=True)

    log(f"单用户训练负荷读取完成，共 {len(df)} 条")
    return df, user_info, account_value


# =========================================================
# 10. 节假日 / 时间特征
# =========================================================
def add_holiday_features(df):
    df = df.copy()
    ds = pd.to_datetime(df["datetime"]).dt.normalize().dt.strftime("%Y-%m-%d")
    date_only = pd.to_datetime(df["datetime"]).dt.normalize()

    df["is_holiday"] = ds.isin(HOLIDAY_MAP.keys()).astype(int)
    df["holiday_name"] = ds.map(HOLIDAY_MAP).fillna("非节假日")
    df["is_adjust_workday"] = ds.isin(ADJUST_WORKDAYS).astype(int)

    weekend = (pd.to_datetime(df["datetime"]).dt.weekday >= 5).astype(int)
    df["is_real_restday"] = np.where(
        (df["is_holiday"] == 1) | ((weekend == 1) & (df["is_adjust_workday"] == 0)),
        1, 0
    )

    df["is_month_start"] = df["datetime"].dt.day.isin([1, 2, 3]).astype(int)
    month_end_days = df["datetime"].dt.days_in_month
    df["is_month_end"] = ((month_end_days - df["datetime"].dt.day).isin([0, 1, 2])).astype(int)

    holiday_dates = sorted(pd.to_datetime(list(HOLIDAY_MAP.keys())))
    before_holiday_dates = set([(d - pd.Timedelta(days=1)).normalize() for d in holiday_dates])
    after_holiday_dates = set([(d + pd.Timedelta(days=1)).normalize() for d in holiday_dates])

    df["is_before_holiday"] = date_only.isin(before_holiday_dates).astype(int)
    df["is_after_holiday"] = date_only.isin(after_holiday_dates).astype(int)

    return df


def add_time_behavior_features(df):
    df = df.copy()

    df["month"] = df["datetime"].dt.month
    df["day"] = df["datetime"].dt.day
    df["hour"] = df["datetime"].dt.hour
    df["weekday"] = df["datetime"].dt.weekday + 1
    df["is_weekend"] = (df["datetime"].dt.weekday >= 5).astype(int)

    df["is_workday"] = np.where(
        (df["is_real_restday"] == 0) | (df["is_adjust_workday"] == 1),
        1, 0
    )

    df["is_active_hour"] = ((df["hour"] >= 8) & (df["hour"] <= 22)).astype(int)
    df["is_workhour"] = ((df["hour"] >= 8) & (df["hour"] <= 19)).astype(int)
    df["is_daytime_8_19"] = ((df["hour"] >= 8) & (df["hour"] <= 19)).astype(int)

    def get_bias_segment(h):
        if 8 <= h <= 10:
            return "seg_8_10"
        elif 11 <= h <= 13:
            return "seg_11_13"
        elif 14 <= h <= 17:
            return "seg_14_17"
        elif 18 <= h <= 19:
            return "seg_18_19"
        else:
            return "seg_other"

    df["bias_segment"] = df["hour"].apply(get_bias_segment)

    df["is_morning_ramp"] = ((df["hour"] >= 8) & (df["hour"] <= 10)).astype(int)
    df["is_lunch_time"] = ((df["hour"] >= 11) & (df["hour"] <= 13)).astype(int)
    df["is_evening_peak"] = ((df["hour"] >= 18) & (df["hour"] <= 22)).astype(int)

    def get_time_segment(h):
        if 0 <= h <= 6:
            return "night"
        elif 7 <= h <= 10:
            return "morning_start"
        elif 11 <= h <= 13:
            return "lunch"
        elif 14 <= h <= 17:
            return "afternoon"
        elif 18 <= h <= 22:
            return "evening_peak"
        else:
            return "late_night"

    df["time_segment"] = df["hour"].apply(get_time_segment)

    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24.0)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24.0)

    weekday0 = df["weekday"] - 1
    df["weekday_sin"] = np.sin(2 * np.pi * weekday0 / 7.0)
    df["weekday_cos"] = np.cos(2 * np.pi * weekday0 / 7.0)

    return df


# =========================================================
# 11. 样本权重
# =========================================================
def add_recency_weight(df, train_end):
    df = df.copy()
    days_diff = (train_end.normalize() - df["datetime"].dt.normalize()).dt.days

    def get_weight(d):
        if d <= 31:
            return 1.00
        elif d <= 92:
            return 0.42
        elif d <= 183:
            return 0.22
        elif d <= 365:
            return 0.12
        else:
            return 0.06

    df["recency_weight"] = days_diff.apply(get_weight)
    return df


def add_time_segment_weight(df):
    df = df.copy()

    def get_time_weight(h):
        if 8 <= h <= 10:
            return 1.50
        elif 11 <= h <= 13:
            return 1.40
        elif 14 <= h <= 17:
            return 1.40
        elif 18 <= h <= 19:
            return 1.50
        elif 0 <= h <= 7:
            return 0.90
        else:
            return 1.00

    df["time_weight"] = df["hour"].apply(get_time_weight)
    return df


def add_special_day_weight(df):
    df = df.copy()

    df["special_day_weight"] = 1.0
    df.loc[(df["is_month_start"] == 1) | (df["is_month_end"] == 1), "special_day_weight"] = 1.15
    df.loc[(df["is_before_holiday"] == 1) | (df["is_after_holiday"] == 1), "special_day_weight"] = 1.20
    df.loc[df["is_holiday"] == 1, "special_day_weight"] = 1.30

    return df


# =========================================================
# 12. 读取天气
# =========================================================
def hourly_weather_column_mapper(cols):
    mapping = {}
    for c in cols:
        c1 = clean_col_name(c)
        if c1 == "地区":
            mapping[c] = "region"
        elif c1 == "时间":
            mapping[c] = "datetime"
        elif c1 == "天气":
            mapping[c] = "weather"
        elif "温度" in c1 and "露点" not in c1 and "体感" not in c1:
            mapping[c] = "temperature"
        elif "降水量" in c1:
            mapping[c] = "rainfall"
        elif c1 == "风向":
            mapping[c] = "wind_direction"
        elif "风力" in c1:
            mapping[c] = "wind_level"
        elif "风速" in c1:
            mapping[c] = "wind_speed"
        elif "风向角度" in c1:
            mapping[c] = "wind_angle"
        elif "气压" in c1:
            mapping[c] = "pressure"
        elif "湿度" in c1:
            mapping[c] = "humidity"
        elif "空气质量" in c1:
            mapping[c] = "air_quality"
        elif "能见度" in c1:
            mapping[c] = "visibility"
        elif "云量" in c1:
            mapping[c] = "cloud"
        elif "露点" in c1:
            mapping[c] = "dew_point"
        elif "短波辐射" in c1 and "总量" not in c1:
            mapping[c] = "shortwave_radiation"
    return mapping


def looks_like_hourly_weather_columns(cols):
    cols_clean = [clean_col_name(c) for c in cols]
    joined = "".join(cols_clean)
    keys = ["地区", "时间", "天气", "温度", "降水量", "湿度"]
    return sum([1 for k in keys if k in joined]) >= 4


def smart_read_hourly_weather_file(path):
    path = str(path)
    if path.lower().endswith(".csv"):
        for enc in ["utf-8-sig", "gbk", "utf-8"]:
            try:
                df = pd.read_csv(path, encoding=enc)
                if looks_like_hourly_weather_columns(df.columns):
                    return df
            except Exception:
                pass
        return pd.read_csv(path)

    xls = pd.ExcelFile(path)
    for sheet_name in xls.sheet_names:
        for header_row in [0, 1, 2, 3, 4, 5]:
            try:
                df = pd.read_excel(path, sheet_name=sheet_name, header=header_row)
                if looks_like_hourly_weather_columns(df.columns):
                    return df
            except Exception:
                continue
    return pd.read_excel(path, sheet_name=0)


def load_hourly_weather():
    log("读取天气...")
    weather_files = (
        glob.glob(str(WEATHER_DIR / "*.xlsx")) +
        glob.glob(str(WEATHER_DIR / "*.xls")) +
        glob.glob(str(WEATHER_DIR / "*.csv"))
    )
    weather_files = [fp for fp in weather_files if not Path(fp).name.startswith("~$")]

    if not weather_files:
        raise FileNotFoundError("未找到任何天气文件")

    weather_list = []
    for fp in weather_files:
        try:
            df = smart_read_hourly_weather_file(fp)
            df = df.rename(columns=hourly_weather_column_mapper(df.columns))

            required = ["region", "datetime", "weather", "temperature", "humidity"]
            if any([c not in df.columns for c in required]):
                continue

            df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
            df = df.dropna(subset=["datetime"]).copy()

            num_cols = [
                "temperature", "rainfall", "wind_speed", "pressure",
                "humidity", "visibility", "cloud", "dew_point",
                "shortwave_radiation", "air_quality"
            ]
            for c in num_cols:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")

            city_list, district_list = [], []
            for x in df["region"]:
                city, district = extract_city_district(x)
                city_list.append(normalize_text(city))
                district_list.append(normalize_region_name(district))

            df["所在市_norm"] = city_list
            df["所在区_norm"] = district_list
            weather_list.append(df)

            log(f"已读取天气：{Path(fp).name}")
        except Exception as e:
            log(f"[错误] 读取天气失败：{Path(fp).name} -> {e}")

    if not weather_list:
        raise ValueError("没有有效天气数据")

    weather_df = pd.concat(weather_list, ignore_index=True)
    weather_df["datetime"] = pd.to_datetime(weather_df["datetime"]).dt.floor("h")
    weather_df = (
        weather_df.sort_values("datetime")
        .drop_duplicates(subset=["所在市_norm", "所在区_norm", "datetime"], keep="last")
        .reset_index(drop=True)
    )
    return weather_df


# =========================================================
# 13. 合并训练负荷与天气（天气修正版）
# =========================================================
def merge_load_weather_hourly(load_df, weather_df):
    log("合并训练负荷与小时气象（天气修正版+区县标准化）...")

    df = load_df.copy()
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce").dt.floor("h")
    df["所在市_norm"] = df["所在市"].apply(normalize_text)
    df["所在区_norm"] = df["所在区"].apply(normalize_region_name)
    df["day_key"] = df["datetime"].dt.date

    w = weather_df.copy()
    w["datetime"] = pd.to_datetime(w["datetime"], errors="coerce").dt.floor("h")

    merged = df.merge(
        w,
        on=["所在市_norm", "所在区_norm", "datetime"],
        how="left",
        suffixes=("", "_w")
    )

    numeric_weather_cols = [
        c for c in [
            "temperature", "rainfall", "wind_level", "wind_speed", "wind_angle",
            "pressure", "humidity", "air_quality", "visibility", "cloud",
            "dew_point", "shortwave_radiation"
        ] if c in w.columns
    ]

    city_numeric = (
        w.groupby(["所在市_norm", "datetime"], as_index=False)[numeric_weather_cols]
        .mean()
    )

    def mode_or_nan(x):
        x = x.dropna()
        if x.empty:
            return np.nan
        m = x.mode()
        if m.empty:
            return np.nan
        return m.iloc[0]

    city_cate_cols = [c for c in ["weather", "wind_direction"] if c in w.columns]
    if city_cate_cols:
        city_cate = (
            w.groupby(["所在市_norm", "datetime"], as_index=False)[city_cate_cols]
            .agg(mode_or_nan)
        )
        weather_city = city_numeric.merge(city_cate, on=["所在市_norm", "datetime"], how="left")
    else:
        weather_city = city_numeric.copy()

    miss_mask = merged["temperature"].isna() if "temperature" in merged.columns else pd.Series(False, index=merged.index)

    if miss_mask.any():
        retry_base = merged.loc[miss_mask, ["所在市_norm", "datetime"]].reset_index(drop=True)
        retry = retry_base.merge(weather_city, on=["所在市_norm", "datetime"], how="left")

        for c in numeric_weather_cols + city_cate_cols:
            if c in retry.columns:
                merged.loc[miss_mask, c] = retry[c].values

        merged.loc[miss_mask, "weather_match_level"] = "city_agg"

    if "weather_match_level" not in merged.columns:
        merged["weather_match_level"] = "district_exact"
    else:
        merged["weather_match_level"] = merged["weather_match_level"].fillna("district_exact")

    day_ok = (
        merged.groupby(["用户编号", "day_key"])["temperature"]
        .apply(lambda x: x.notna().all())
        .reset_index(name="weather_day_complete")
    )
    merged = merged.merge(day_ok, on=["用户编号", "day_key"], how="left")
    merged = merged[merged["weather_day_complete"] == True].copy()

    log(f"训练数据合并完成，共 {len(merged)} 条")
    log("weather_match_level 统计：")
    log(merged["weather_match_level"].value_counts(dropna=False).to_dict())

    return merged


# =========================================================
# 14. 特征工程
# =========================================================
def create_train_features(df):
    log("生成单用户V6训练特征...")
    df = df.copy()
    df = df.sort_values("datetime").reset_index(drop=True)

    for c in ["rainfall", "wind_speed", "pressure", "visibility", "cloud", "dew_point", "shortwave_radiation", "air_quality"]:
        if c not in df.columns:
            df[c] = np.nan

    df = add_holiday_features(df)
    df = add_time_behavior_features(df)

    df["cooling_degree"] = np.maximum(df["temperature"] - 24, 0)
    df["heating_degree"] = np.maximum(18 - df["temperature"], 0)

    df["load_lag_24"] = df["load"].shift(24)
    df["load_lag_48"] = df["load"].shift(48)
    df["load_lag_168"] = df["load"].shift(168)

    same_hour_series = df.groupby("hour")["load"]

    df["load_same_hour_mean_3d"] = (
        same_hour_series.shift(1)
        .groupby(df["hour"])
        .rolling(3, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    df["load_same_hour_mean_7d"] = (
        same_hour_series.shift(1)
        .groupby(df["hour"])
        .rolling(7, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    df["weekday_hour_key"] = df["weekday"].astype(str) + "_" + df["hour"].astype(str)
    weekday_hour_series = df.groupby("weekday_hour_key")["load"]

    df["load_same_weekday_hour_mean_4"] = (
        weekday_hour_series.shift(1)
        .groupby(df["weekday_hour_key"])
        .rolling(4, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    df["load_same_weekday_hour_mean_8"] = (
        weekday_hour_series.shift(1)
        .groupby(df["weekday_hour_key"])
        .rolling(8, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    df["day_type_tmp"] = np.where(df["is_workday"] == 1, "workday", "restday")
    df["daytype_hour_key"] = df["day_type_tmp"].astype(str) + "_" + df["hour"].astype(str)
    daytype_hour_series = df.groupby("daytype_hour_key")["load"]

    df["daytype_same_hour_mean_5"] = (
        daytype_hour_series.shift(1)
        .groupby(df["daytype_hour_key"])
        .rolling(5, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    df["workday_same_hour_mean_5"] = np.where(df["is_workday"] == 1, df["daytype_same_hour_mean_5"], np.nan)
    df["restday_same_hour_mean_5"] = np.where(df["is_workday"] == 0, df["daytype_same_hour_mean_5"], np.nan)

    df["load_roll_mean_24"] = df["load"].shift(1).rolling(24, min_periods=1).mean()
    df["load_roll_std_24"] = df["load"].shift(1).rolling(24, min_periods=1).std()
    df["load_roll_mean_168"] = df["load"].shift(1).rolling(168, min_periods=1).mean()

    df["load_workhour_only"] = np.where(df["is_workhour"] == 1, df["load"], np.nan)
    df["recent_workhour_mean_3d"] = df["load_workhour_only"].shift(1).rolling(72, min_periods=1).mean()
    df["recent_workhour_mean_7d"] = df["load_workhour_only"].shift(1).rolling(168, min_periods=1).mean()

    # ===== 日级特征构造 =====
    df["date_day"] = df["datetime"].dt.normalize()
    df["daytime_load"] = np.where(df["is_daytime_8_19"] == 1, df["load"], 0)
    df["night_load"] = np.where(df["is_daytime_8_19"] == 0, df["load"], 0)

    daily = df.groupby("date_day").agg({
        "load": ["sum", "mean", "max", "min"],
        "daytime_load": ["sum", "mean"],
        "night_load": ["sum", "mean"],
        "temperature": ["mean", "max", "min"],
        "humidity": ["mean"],
        "rainfall": ["sum"],
        "shortwave_radiation": ["sum", "mean", "max"],
        "is_workday": ["max"],
        "is_holiday": ["max"],
        "is_before_holiday": ["max"],
        "is_after_holiday": ["max"],
        "is_month_start": ["max"],
        "is_month_end": ["max"]
    })

    daily.columns = [
        "_".join([str(i) for i in col if str(i) != ""])
        for col in daily.columns
    ]
    daily = daily.reset_index()

    daily = daily.rename(columns={
        "load_sum": "daily_total_load",
        "load_mean": "day_mean_load",
        "load_max": "day_peak_load",
        "load_min": "day_valley_load",
        "daytime_load_sum": "daytime_total_load",
        "daytime_load_mean": "daytime_mean_load",
        "night_load_sum": "night_total_load",
        "night_load_mean": "night_mean_load",
        "temperature_mean": "temp_mean",
        "temperature_max": "temp_max",
        "temperature_min": "temp_min",
        "humidity_mean": "humidity_mean",
        "rainfall_sum": "rainfall_total",
        "shortwave_radiation_sum": "radiation_total",
        "shortwave_radiation_mean": "radiation_mean",
        "shortwave_radiation_max": "radiation_max",
        "is_workday_max": "day_is_workday",
        "is_holiday_max": "day_is_holiday",
        "is_before_holiday_max": "day_is_before_holiday",
        "is_after_holiday_max": "day_is_after_holiday",
        "is_month_start_max": "day_is_month_start",
        "is_month_end_max": "day_is_month_end"
    })

    daily = daily.sort_values("date_day").reset_index(drop=True)

    daily["daily_total_load_lag_1"] = daily["daily_total_load"].shift(1)
    daily["daily_total_load_roll_mean_3"] = daily["daily_total_load"].shift(1).rolling(3, min_periods=1).mean()
    daily["daily_total_load_roll_mean_7"] = daily["daily_total_load"].shift(1).rolling(7, min_periods=1).mean()

    daily["daytime_total_load_lag_1"] = daily["daytime_total_load"].shift(1)
    daily["daytime_total_load_roll_mean_3"] = daily["daytime_total_load"].shift(1).rolling(3, min_periods=1).mean()
    daily["daytime_total_load_roll_mean_7"] = daily["daytime_total_load"].shift(1).rolling(7, min_periods=1).mean()

    q30 = daily["daytime_total_load"].quantile(0.3)
    q70 = daily["daytime_total_load"].quantile(0.7)

    def map_day_type(x):
        if pd.isna(x):
            return "mid_day"
        elif x <= q30:
            return "low_day"
        elif x <= q70:
            return "mid_day"
        else:
            return "high_day"

    daily["day_type"] = daily["daytime_total_load"].apply(map_day_type)

    # 合并回小时表
    df = df.merge(daily, on="date_day", how="left")

    log("单用户V6训练特征生成完成")
    return df, daily, q30, q70


# =========================================================
# 15. 特征列表
# =========================================================
def get_day_feature_list(daily_df):
    use_features = [
        "day_is_workday", "day_is_holiday",
        "day_is_before_holiday", "day_is_after_holiday",
        "day_is_month_start", "day_is_month_end",

        "temp_mean", "temp_max", "temp_min",
        "humidity_mean", "rainfall_total",
        "radiation_total", "radiation_mean", "radiation_max",

        "daily_total_load_lag_1",
        "daily_total_load_roll_mean_3",
        "daily_total_load_roll_mean_7",
        "daytime_total_load_lag_1",
        "daytime_total_load_roll_mean_3",
        "daytime_total_load_roll_mean_7",
    ]
    return [c for c in use_features if c in daily_df.columns]


def get_hour_feature_list(train_df):
    use_features = [
        "month", "day", "hour", "weekday",
        "is_weekend", "is_workday", "is_active_hour", "is_workhour",
        "is_daytime_8_19", "bias_segment",
        "is_morning_ramp", "is_lunch_time", "is_evening_peak",
        "time_segment", "hour_sin", "hour_cos", "weekday_sin", "weekday_cos",

        "is_holiday", "is_adjust_workday", "is_real_restday", "holiday_name",
        "is_month_start", "is_month_end", "is_before_holiday", "is_after_holiday",

        "weather", "wind_direction",
        "temperature", "rainfall", "wind_speed", "pressure", "humidity",
        "visibility", "cloud", "dew_point", "shortwave_radiation", "air_quality",
        "cooling_degree", "heating_degree",

        "load_lag_24", "load_lag_48", "load_lag_168",
        "load_same_hour_mean_3d", "load_same_hour_mean_7d",
        "load_same_weekday_hour_mean_4", "load_same_weekday_hour_mean_8",
        "workday_same_hour_mean_5", "restday_same_hour_mean_5",
        "load_roll_mean_24", "load_roll_std_24", "load_roll_mean_168",
        "recent_workhour_mean_3d", "recent_workhour_mean_7d",

        "pred_daytime_total_load",
        "day_type",
    ]
    return [c for c in use_features if c in train_df.columns]


# =========================================================
# 16. 训练矩阵准备
# =========================================================
def prepare_matrix(df, target_col, use_features):
    data = df.copy()
    data = data.dropna(subset=[target_col]).copy()

    if target_col == "load":
        lag_cols = [c for c in ["load_lag_24", "load_lag_48", "load_lag_168"] if c in data.columns]
        if lag_cols:
            data = data.dropna(subset=lag_cols)

    if data.empty:
        return None, None, None, None, None

    cat_cols = [c for c in ["weather", "time_segment", "wind_direction", "holiday_name", "bias_segment", "day_type"] if c in use_features]
    num_cols = [c for c in use_features if c not in cat_cols]

    for col in cat_cols:
        if col in data.columns:
            data[col] = data[col].fillna("未知").astype(str)

    for col in num_cols:
        if col in data.columns:
            med = data[col].median()
            data[col] = data[col].fillna(med)

    X = data[use_features].copy()
    y = data[target_col].copy()
    sample_weight = data["sample_weight"].copy() if "sample_weight" in data.columns else None

    X = pd.get_dummies(X, columns=cat_cols, dummy_na=False)

    meta = {
        "use_features": use_features,
        "cat_cols": cat_cols,
        "num_cols": num_cols,
        "train_columns": X.columns.tolist(),
        "num_fill_values": {c: data[c].median() if c in data.columns else 0 for c in num_cols},
    }

    return data, X, y, sample_weight, meta


# =========================================================
# 17. 训练模型
# =========================================================
def train_day_regressor(X_train, y_train, sample_weight=None):
    log(f"开始训练日级白天总量回归器：{MODEL_NAME}")

    if MODEL_NAME == "lightgbm":
        model = LGBMRegressor(
            n_estimators=600,
            learning_rate=0.03,
            num_leaves=31,
            subsample=0.9,
            colsample_bytree=0.9,
            min_child_samples=10,
            random_state=42
        )
    else:
        model = RandomForestRegressor(
            n_estimators=300,
            random_state=42,
            n_jobs=-1
        )

    if sample_weight is not None:
        model.fit(X_train, y_train, sample_weight=sample_weight)
    else:
        model.fit(X_train, y_train)

    return model


def train_hour_regressor(X_train, y_train, sample_weight=None):
    log(f"开始训练小时负荷回归器：{MODEL_NAME}")

    if MODEL_NAME == "lightgbm":
        model = LGBMRegressor(
            n_estimators=800,
            learning_rate=0.03,
            num_leaves=31,
            subsample=0.9,
            colsample_bytree=0.9,
            min_child_samples=20,
            random_state=42
        )
    else:
        model = RandomForestRegressor(
            n_estimators=300,
            random_state=42,
            n_jobs=-1
        )

    if sample_weight is not None:
        model.fit(X_train, y_train, sample_weight=sample_weight)
    else:
        model.fit(X_train, y_train)

    return model


# =========================================================
# 18. 导出结果
# =========================================================
def export_feature_importance(model, X_train, file_name):
    if hasattr(model, "feature_importances_"):
        fi = pd.DataFrame({
            "feature": X_train.columns,
            "importance": model.feature_importances_
        }).sort_values("importance", ascending=False)
        fi.to_csv(
            OUTPUT_PREDICTION / file_name,
            index=False,
            encoding="utf-8-sig"
        )


def export_day_regressor_metrics(model, X_train, y_train):
    pred = model.predict(X_train)

    eval_df = pd.DataFrame({
        "y_true": pd.to_numeric(y_train, errors="coerce"),
        "y_pred": pd.to_numeric(pred, errors="coerce")
    }).dropna()

    if eval_df.empty:
        log("[警告] 日级回归训练评估样本为空")
        return

    mae = mean_absolute_error(eval_df["y_true"], eval_df["y_pred"])
    rmse = np.sqrt(mean_squared_error(eval_df["y_true"], eval_df["y_pred"]))
    ape = np.where(
        (eval_df["y_true"] != 0),
        np.abs(eval_df["y_pred"] - eval_df["y_true"]) / np.abs(eval_df["y_true"]),
        np.nan
    )
    mape = np.nanmean(ape)

    out = pd.DataFrame([
        {"metric": "mae", "value": mae},
        {"metric": "rmse", "value": rmse},
        {"metric": "mape", "value": mape},
    ])
    out.to_csv(
        OUTPUT_PREDICTION / f"train_metrics_day_load_regressor_v6_{SAFE_USER_NAME}.csv",
        index=False,
        encoding="utf-8-sig"
    )

    log(f"日级白天总量回归 MAE: {mae:.4f}")
    log(f"日级白天总量回归 RMSE: {rmse:.4f}")
    log(f"日级白天总量回归 MAPE: {mape:.4%}")


def export_hour_regressor_metrics(model, X_train, y_train):
    pred = model.predict(X_train)

    eval_df = pd.DataFrame({
        "y_true": pd.to_numeric(y_train, errors="coerce"),
        "y_pred": pd.to_numeric(pred, errors="coerce")
    }).dropna()

    if eval_df.empty:
        log("[警告] 小时回归训练评估样本为空")
        return

    mae = mean_absolute_error(eval_df["y_true"], eval_df["y_pred"])
    rmse = np.sqrt(mean_squared_error(eval_df["y_true"], eval_df["y_pred"]))

    ape = np.where(
        (eval_df["y_true"] != 0),
        np.abs(eval_df["y_pred"] - eval_df["y_true"]) / np.abs(eval_df["y_true"]),
        np.nan
    )
    mape = np.nanmean(ape)

    out = pd.DataFrame([
        {"metric": "mae", "value": mae},
        {"metric": "rmse", "value": rmse},
        {"metric": "mape", "value": mape},
    ])
    out.to_csv(
        OUTPUT_PREDICTION / f"train_metrics_hour_regressor_v6_{SAFE_USER_NAME}.csv",
        index=False,
        encoding="utf-8-sig"
    )

    log(f"小时回归训练 MAE: {mae:.4f}")
    log(f"小时回归训练 RMSE: {rmse:.4f}")
    log(f"小时回归训练 MAPE: {mape:.4%}")


# =========================================================
# 19. 主流程
# =========================================================
def main():
    log("=== 开始单用户V6训练：日级总量回归 + 小时预测 ===")
    log(f"目标用户 = {TARGET_USER_NAME}")
    log(f"PREDICT_START = {PREDICT_START_TS}")
    log(f"PREDICT_END   = {PREDICT_END_TS}")
    log(f"TRAIN_START   = {TRAIN_START}")
    log(f"TRAIN_END     = {TRAIN_END}")
    log(f"TRAIN_MONTHS  = {TRAIN_MONTHS}")
    log(f"BIAS_LOOKBACK_DAYS = {BIAS_LOOKBACK_DAYS}")

    user_master_df = load_user_master()
    load_df, user_info, account_value = load_single_user_load(user_master_df)
    weather_df = load_hourly_weather()

    train_raw_df = merge_load_weather_hourly(load_df, weather_df)
    train_feature_df, daily_df, q30, q70 = create_train_features(train_raw_df)

    train_feature_df = train_feature_df[
        (train_feature_df["datetime"] >= TRAIN_START) &
        (train_feature_df["datetime"] < TRAIN_END)
    ].copy()

    daily_df = daily_df[
        (daily_df["date_day"] >= TRAIN_START.normalize()) &
        (daily_df["date_day"] < TRAIN_END.normalize())
    ].copy()

    if train_feature_df.empty or daily_df.empty:
        raise ValueError("单用户V6训练数据为空，请检查训练时间范围是否有数据")

    train_feature_df = add_recency_weight(train_feature_df, TRAIN_END)
    train_feature_df = add_time_segment_weight(train_feature_df)
    train_feature_df = add_special_day_weight(train_feature_df)

    train_feature_df["sample_weight"] = (
        train_feature_df["recency_weight"] *
        train_feature_df["time_weight"] *
        train_feature_df["special_day_weight"]
    ).clip(lower=0.05, upper=3.0)

    day_weight_df = (
        train_feature_df.groupby("date_day", as_index=False)["sample_weight"]
        .mean()
        .rename(columns={"sample_weight": "day_sample_weight"})
    )
    daily_df = daily_df.merge(day_weight_df, on="date_day", how="left")

    log(
        "小时样本权重统计："
        f" min={train_feature_df['sample_weight'].min():.4f},"
        f" max={train_feature_df['sample_weight'].max():.4f},"
        f" mean={train_feature_df['sample_weight'].mean():.4f}"
    )

    # 训练日级白天总量回归器
    day_features = get_day_feature_list(daily_df)
    daily_df_for_train = daily_df.rename(columns={"day_sample_weight": "sample_weight"}).copy()

    _, X_day, y_day, w_day, day_meta = prepare_matrix(
        daily_df_for_train,
        "daytime_total_load",
        day_features
    )

    if X_day is None or X_day.empty:
        raise ValueError("日级白天总量回归训练矩阵为空")

    day_reg_model = train_day_regressor(X_day, y_day, sample_weight=w_day)

    with open(OUTPUT_MODEL / f"single_user_day_load_regressor_{SAFE_USER_NAME}.pkl", "wb") as f:
        pickle.dump(day_reg_model, f)

    with open(OUTPUT_MODEL / f"single_user_day_feature_meta_{SAFE_USER_NAME}.pkl", "wb") as f:
        pickle.dump(day_meta, f)

    export_feature_importance(day_reg_model, X_day, f"feature_importance_day_load_regressor_v6_{SAFE_USER_NAME}.csv")
    export_day_regressor_metrics(day_reg_model, X_day, y_day)

    # 用训练期真实日总量映射 day_type，训练小时模型
    train_feature_df["pred_daytime_total_load"] = train_feature_df["date_day"].map(
        daily_df.set_index("date_day")["daytime_total_load"].to_dict()
    )
    train_feature_df["day_type"] = train_feature_df["date_day"].map(
        daily_df.set_index("date_day")["day_type"].to_dict()
    )

    hour_features = get_hour_feature_list(train_feature_df)
    train_df, X_hour, y_hour, w_hour, hour_meta = prepare_matrix(
        train_feature_df,
        "load",
        hour_features
    )

    if X_hour is None or X_hour.empty:
        raise ValueError("小时回归训练矩阵为空")

    hour_model = train_hour_regressor(X_hour, y_hour, sample_weight=w_hour)

    with open(OUTPUT_MODEL / f"single_user_hour_model_{SAFE_USER_NAME}.pkl", "wb") as f:
        pickle.dump(hour_model, f)

    with open(OUTPUT_MODEL / f"single_user_hour_feature_meta_{SAFE_USER_NAME}.pkl", "wb") as f:
        pickle.dump(hour_meta, f)

    export_feature_importance(hour_model, X_hour, f"feature_importance_hour_model_v6_{SAFE_USER_NAME}.csv")
    export_hour_regressor_metrics(hour_model, X_hour, y_hour)

    history_df = load_df[
        (load_df["datetime"] >= TRAIN_START - pd.Timedelta(days=60)) &
        (load_df["datetime"] < PREDICT_START_TS)
    ].copy()
    history_df.to_csv(
        OUTPUT_PROCESSED / f"single_user_history_v6_{SAFE_USER_NAME}.csv",
        index=False,
        encoding="utf-8-sig"
    )

    train_feature_df.to_csv(
        OUTPUT_PROCESSED / f"single_user_train_dataset_v6_{SAFE_USER_NAME}.csv",
        index=False,
        encoding="utf-8-sig"
    )

    daily_df.to_csv(
        OUTPUT_PROCESSED / f"single_user_train_daily_dataset_v6_{SAFE_USER_NAME}.csv",
        index=False,
        encoding="utf-8-sig"
    )

    config_df = pd.DataFrame([{
        "TARGET_USER_NAME": TARGET_USER_NAME,
        "用户编号": user_info["用户编号"],
        "户号": account_value,
        "所在市": user_info["所在市"],
        "所在区": user_info["所在区"],
        "用户类型": user_info["用户类型"],
        "是否有光伏": user_info["是否有光伏"],
        "是否有光伏_flag": user_info["是否有光伏_flag"],
        "PREDICT_START": str(PREDICT_START_TS),
        "PREDICT_END": str(PREDICT_END_TS),
        "TRAIN_START": str(TRAIN_START),
        "TRAIN_END": str(TRAIN_END),
        "TRAIN_MONTHS": TRAIN_MONTHS,
        "BIAS_LOOKBACK_DAYS": BIAS_LOOKBACK_DAYS,
        "DAYTYPE_Q30": q30,
        "DAYTYPE_Q70": q70
    }])
    config_df.to_csv(
        OUTPUT_MODEL / f"single_user_run_config_v6_{SAFE_USER_NAME}.csv",
        index=False,
        encoding="utf-8-sig"
    )

    log(f"单用户V6日级样本数: {len(X_day)}")
    log(f"单用户V6小时样本数: {len(X_hour)}")
    log("=== 单用户V6训练完成 ===")


if __name__ == "__main__":
    main()