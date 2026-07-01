# -*- coding: utf-8 -*-
"""
【V2.6 升级版】负荷预测预测脚本
核心升级:
  P0: 并行预测替代递归预测（斩断误差累积链）
  P1: 光伏逆向扣减：关口电量 = 预测总需求 - 日前光伏估算
  P2: 按 Hour 路由到 24 个独立小时模型
  P3: 低负荷概率阈值可配
"""

import re
import glob
import pickle
import warnings
import numpy as np
import pandas as pd

from pathlib import Path

warnings.filterwarnings("ignore")


# =========================================================
# 1. 路径配置
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
# 2. 日志
# =========================================================
LOG_FILE = OUTPUT_LOGS / "02_predict_v2_6_upgraded_log.txt"


def log(msg):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")


with open(LOG_FILE, "w", encoding="utf-8") as f:
    f.write("=== V2.6_Upgraded 预测日志 ===\n")


# =========================================================
# 3. 读取运行配置
# =========================================================
CONFIG_PATH = OUTPUT_MODEL / "run_config_v2_6.csv"
if not CONFIG_PATH.exists():
    raise FileNotFoundError("未找到 run_config_v2_6.csv，请先运行 01.py")

RUN_CONFIG = pd.read_csv(CONFIG_PATH, encoding="utf-8-sig").iloc[0]
PREDICT_START_TS = pd.Timestamp(RUN_CONFIG["PREDICT_START"])
PREDICT_END_TS = pd.Timestamp(RUN_CONFIG["PREDICT_END"])
LOW_LOAD_THRESHOLD = float(RUN_CONFIG["LOW_LOAD_THRESHOLD"])
LOW_LOAD_PROBA_THRESHOLD = float(RUN_CONFIG["LOW_LOAD_PROBA_THRESHOLD"])


# =========================================================
# 4. 节假日配置
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
# 5. 通用函数
# =========================================================
def normalize_text(x):
    if pd.isna(x):
        return None
    x = str(x).strip()
    x = x.replace("\u3000", "").replace(" ", "")
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


# =========================================================
# 6. 光伏物理公式 (与训练完全一致)
# =========================================================
def estimate_pv_generation(radiation, temp, capacity):
    """标准光伏出力物理公式估算 (与训练完全一致)"""
    if pd.isna(radiation) or pd.isna(temp) or pd.isna(capacity):
        return 0.0
    if radiation <= 0:
        return 0.0
    temp_coeff = 1 + (-0.004) * (temp - 25)
    pv_estimated = capacity * 1000 * 0.75 * (radiation / 1000) * temp_coeff
    return max(0.0, pv_estimated)


# =========================================================
# 7. 节假日和时间特征
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
# 8. 气象读取
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
    log("读取小时气象...")
    weather_files = (
        glob.glob(str(WEATHER_DIR / "*.xlsx")) +
        glob.glob(str(WEATHER_DIR / "*.xls")) +
        glob.glob(str(WEATHER_DIR / "*.csv"))
    )

    if not weather_files:
        raise FileNotFoundError("未找到任何小时气象文件")

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
                district_list.append(normalize_text(district))

            df["所在市_norm"] = city_list
            df["所在区_norm"] = district_list
            weather_list.append(df)

            log(f"已读取气象：{Path(fp).name}")
        except Exception as e:
            log(f"[错误] 气象读取失败：{Path(fp).name} -> {e}")

    if not weather_list:
        raise ValueError("没有有效小时气象")

    weather_df = pd.concat(weather_list, ignore_index=True)
    weather_df["datetime"] = pd.to_datetime(weather_df["datetime"]).dt.floor("h")
    weather_df = (
        weather_df.sort_values("datetime")
        .drop_duplicates(subset=["所在市_norm", "所在区_norm", "datetime"], keep="last")
        .reset_index(drop=True)
    )
    return weather_df


# =========================================================
# 9. 主档案和预测骨架
# =========================================================
def load_user_master():
    df = safe_read_table(USER_MASTER_PATH)
    df.columns = [str(c).strip() for c in df.columns]
    df["用户名称_norm"] = df["用户名称"].apply(normalize_text)
    df["是否有光伏_flag"] = df["是否有光伏"].apply(convert_yes_no)

    if "光伏容量(MW)" in df.columns:
        df["光伏容量(MW)"] = pd.to_numeric(df["光伏容量(MW)"], errors="coerce").fillna(0)
    else:
        df["光伏容量(MW)"] = 0.0

    return df


def build_predict_skeleton(user_master_df):
    history_map_path = OUTPUT_PROCESSED / "user_account_map_v2_6.csv"
    account_map_df = pd.read_csv(history_map_path, encoding="utf-8-sig") if history_map_path.exists() else pd.DataFrame(columns=["用户编号", "户号"])
    account_map = dict(zip(account_map_df["用户编号"], account_map_df["户号"]))

    time_range = pd.date_range(start=PREDICT_START_TS, end=PREDICT_END_TS, freq="h", inclusive="left")

    rows = []
    files = glob.glob(str(LOAD_DIR / "*.xlsx")) + glob.glob(str(LOAD_DIR / "*.xls"))

    for fp in files:
        file_name = Path(fp).stem
        user_name_norm = normalize_text(file_name)
        matched = user_master_df[user_master_df["用户名称_norm"] == user_name_norm]
        if matched.empty:
            log(f"[警告] 预测骨架未匹配主档案：{file_name}")
            continue

        u = matched.iloc[0]

        if pd.isna(u["用户编号"]):
            log(f"[警告] 主档案用户编号为空，跳过：{u['用户名称']}")
            continue

        tmp = pd.DataFrame({"datetime": time_range})
        tmp["用户编号"] = u["用户编号"]
        tmp["用户名称"] = u["用户名称"]
        tmp["户号"] = account_map.get(u["用户编号"], u["用户名称"])
        tmp["所在市"] = u["所在市"]
        tmp["所在区"] = u["所在区"]
        tmp["用户类型"] = u["用户类型"]
        tmp["是否有光伏"] = u["是否有光伏"]
        tmp["是否有光伏_flag"] = u["是否有光伏_flag"]
        tmp["光伏容量(MW)"] = u["光伏容量(MW)"]
        rows.append(tmp)

    if not rows:
        raise ValueError("未生成任何预测骨架")

    df = pd.concat(rows, ignore_index=True)
    df["所在市_norm"] = df["所在市"].apply(normalize_text)
    df["所在区_norm"] = df["所在区"].apply(normalize_text)
    df["day_key"] = df["datetime"].dt.date
    df = df.dropna(subset=["用户编号", "datetime"]).copy()

    log(f"预测骨架生成完成，总记录数: {len(df)}")
    return df


# =========================================================
# 10. 匹配预测气象 + 特征生成
# =========================================================
def merge_predict_weather(predict_df, weather_df):
    log("为预测骨架匹配小时气象...")

    df = predict_df.copy()
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce").dt.floor("h")

    if "day_key" not in df.columns:
        df["day_key"] = df["datetime"].dt.date

    w = weather_df.copy()
    w["datetime"] = pd.to_datetime(w["datetime"], errors="coerce").dt.floor("h")

    # 1）严格按 市+区+小时 匹配
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

    # 2）城市级聚合天气
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

    # 3）区县匹配失败 -> 城市聚合回补
    if "temperature" in merged.columns:
        miss_mask = merged["temperature"].isna()
    else:
        miss_mask = pd.Series(False, index=merged.index)

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

    # 4）补节假日和时间行为特征
    merged = add_holiday_features(merged)
    merged = add_time_behavior_features(merged)

    # 5）补派生气象特征
    for c in ["rainfall", "wind_speed", "pressure", "visibility", "cloud",
              "dew_point", "shortwave_radiation", "air_quality"]:
        if c not in merged.columns:
            merged[c] = np.nan

    merged["cooling_degree"] = np.maximum(merged["temperature"] - 24, 0)
    merged["heating_degree"] = np.maximum(18 - merged["temperature"], 0)

    # 6）按天判断天气是否完整
    if "temperature" in merged.columns:
        day_ok = (
            merged.groupby(["用户编号", "day_key"])["temperature"]
            .apply(lambda x: x.notna().all())
            .reset_index(name="weather_day_complete")
        )
    else:
        day_ok = merged[["用户编号", "day_key"]].drop_duplicates().copy()
        day_ok["weather_day_complete"] = False

    merged = merged.merge(day_ok, on=["用户编号", "day_key"], how="left")

    # 7）字符列清洗
    for c in ["用户类型", "所在市", "所在区", "weather", "time_segment",
              "wind_direction", "holiday_name", "bias_segment"]:
        if c in merged.columns:
            merged[c] = merged[c].astype(str).str.strip()

    log(f"预测骨架总记录数: {len(df)}")
    log(f"天气表总记录数: {len(w)}")
    if "temperature" in merged.columns:
        log(f"merge 后 temperature 为空数: {merged['temperature'].isna().sum()}")
    log("天气匹配来源统计：")
    log(merged["weather_match_level"].value_counts(dropna=False).to_dict())

    return merged


# =========================================================
# 11. 历史特征构造（为预测骨架补 lag 特征）
# =========================================================
def build_predict_features(predict_df, history_df):
    """V2 并行模式：为所有预测时点一次性构造 lag 特征（不依赖已预测值）"""
    log("为预测数据构造历史 lag 特征...")

    pred = predict_df.copy()
    pred["datetime"] = pd.to_datetime(pred["datetime"])
    pred = pred.sort_values(["用户编号", "datetime"]).reset_index(drop=True)

    hist = history_df.copy()
    hist["datetime"] = pd.to_datetime(hist["datetime"])
    hist = hist.dropna(subset=["datetime", "用户编号"]).copy()

    # 对每个用户、每个预测时点，从 history 中获取 lag
    result_rows = []

    for uid in pred["用户编号"].unique():
        user_hist = hist[hist["用户编号"] == uid].sort_values("datetime").reset_index(drop=True)
        user_pred = pred[pred["用户编号"] == uid].sort_values("datetime").reset_index(drop=True)

        if user_hist.empty:
            log(f"[警告] 用户 {uid} 无历史数据")
            user_pred["load_lag_24"] = np.nan
            user_pred["load_lag_48"] = np.nan
            user_pred["load_lag_168"] = np.nan
            user_pred["load_same_hour_mean_3d"] = np.nan
            user_pred["load_same_hour_mean_7d"] = np.nan
            user_pred["load_same_weekday_hour_mean_4"] = np.nan
            user_pred["load_same_weekday_hour_mean_8"] = np.nan
            user_pred["workday_same_hour_mean_5"] = np.nan
            user_pred["restday_same_hour_mean_5"] = np.nan
            user_pred["load_roll_mean_24"] = np.nan
            user_pred["load_roll_std_24"] = np.nan
            user_pred["load_roll_mean_168"] = np.nan
            user_pred["recent_workhour_mean_3d"] = np.nan
            user_pred["recent_workhour_mean_7d"] = np.nan
            result_rows.append(user_pred)
            continue

        # 建立 datetime -> load 的快速查找
        hist_load_map = dict(zip(user_hist["datetime"], user_hist["load"]))
        hist_datetimes = user_hist["datetime"].values
        hist_loads = user_hist["load"].values

        for idx, row in user_pred.iterrows():
            current_time = row["datetime"]

            # Lag 特征
            def get_lag(hours_back):
                target_time = current_time - pd.Timedelta(hours=hours_back)
                if target_time in hist_load_map:
                    return hist_load_map[target_time]
                return np.nan

            row["load_lag_24"] = get_lag(24)
            row["load_lag_48"] = get_lag(48)
            row["load_lag_168"] = get_lag(168)

            # 历史数据（截止到当前时间之前）
            hist_before_mask = hist_datetimes < current_time
            hist_before_loads = hist_loads[hist_before_mask]
            hist_before_dts = hist_datetimes[hist_before_mask]

            # 滚动窗口统计
            row["load_roll_mean_24"] = np.mean(hist_before_loads[-24:]) if len(hist_before_loads) >= 1 else np.nan
            row["load_roll_std_24"] = np.std(hist_before_loads[-24:]) if len(hist_before_loads) >= 2 else 0.0
            row["load_roll_mean_168"] = np.mean(hist_before_loads[-168:]) if len(hist_before_loads) >= 1 else np.nan

            current_hour = current_time.hour

            # 同小时均值
            same_hour_mask = pd.to_datetime(hist_before_dts).hour == current_hour
            same_hour_loads = hist_before_loads[same_hour_mask]
            row["load_same_hour_mean_3d"] = np.mean(same_hour_loads[-3:]) if len(same_hour_loads) >= 1 else np.nan
            row["load_same_hour_mean_7d"] = np.mean(same_hour_loads[-7:]) if len(same_hour_loads) >= 1 else np.nan

            # 同星期几同小时均值
            current_weekday = current_time.weekday()
            same_weekday_hour_mask = (pd.to_datetime(hist_before_dts).weekday == current_weekday) & same_hour_mask
            swh_loads = hist_before_loads[same_weekday_hour_mask]
            row["load_same_weekday_hour_mean_4"] = np.mean(swh_loads[-4:]) if len(swh_loads) >= 1 else np.nan
            row["load_same_weekday_hour_mean_8"] = np.mean(swh_loads[-8:]) if len(swh_loads) >= 1 else np.nan

            # 工作日/休息日同小时均值
            is_workday_now = row.get("is_workday", 1)
            # 此处简化：用 is_weekend 近似判断
            if not hist_before_dts.size:
                row["workday_same_hour_mean_5"] = np.nan
                row["restday_same_hour_mean_5"] = np.nan
            else:
                hist_before_series = pd.Series(hist_before_dts)
                hist_weekday = hist_before_series.dt.weekday
                hist_is_weekend = (hist_weekday >= 5).astype(int)
                daytype_mask = (hist_is_weekend == 0) if is_workday_now == 1 else (hist_is_weekend == 1)
                # 准确判断需要考虑节假日，此处简化
                same_hour_daytype_mask = same_hour_mask & daytype_mask
                daytype_loads = hist_before_loads[same_hour_daytype_mask]
                daytype_mean = np.mean(daytype_loads[-5:]) if len(daytype_loads) >= 1 else np.nan
                row["workday_same_hour_mean_5"] = daytype_mean if is_workday_now == 1 else np.nan
                row["restday_same_hour_mean_5"] = daytype_mean if is_workday_now == 0 else np.nan

            # 最近工作时段均值
            workhour_mask = (pd.to_datetime(hist_before_dts).hour >= 8) & (pd.to_datetime(hist_before_dts).hour <= 19)
            workhour_loads = hist_before_loads[workhour_mask]
            row["recent_workhour_mean_3d"] = np.mean(workhour_loads[-36:]) if len(workhour_loads) >= 1 else np.nan
            row["recent_workhour_mean_7d"] = np.mean(workhour_loads[-84:]) if len(workhour_loads) >= 1 else np.nan

            user_pred.loc[idx] = row

        result_rows.append(user_pred)

    result = pd.concat(result_rows, ignore_index=True)
    log(f"预测特征构造完成，共 {len(result)} 条")
    return result


# =========================================================
# 12. 单步特征准备（与训练时 one-hot 对齐）
# =========================================================
def prepare_single_step_features(step_df, feature_meta):
    df = step_df.copy()
    use_features = feature_meta["use_features"]
    cat_cols = feature_meta["cat_cols"]
    num_cols = feature_meta["num_cols"]
    train_columns = feature_meta["train_columns"]
    num_fill_values = feature_meta["num_fill_values"]

    for col in cat_cols:
        if col not in df.columns:
            df[col] = "未知"
        df[col] = df[col].fillna("未知").astype(str)

    for col in num_cols:
        if col not in df.columns:
            df[col] = num_fill_values.get(col, 0)
        df[col] = df[col].fillna(num_fill_values.get(col, 0))

    X = df[use_features].copy()
    X = pd.get_dummies(X, columns=cat_cols, dummy_na=False)

    for c in train_columns:
        if c not in X.columns:
            X[c] = 0

    extra_cols = [c for c in X.columns if c not in train_columns]
    if extra_cols:
        X = X.drop(columns=extra_cols)

    X = X[train_columns].copy()
    return X


# =========================================================
# 13. 加载模型
# =========================================================
def load_models():
    log("加载 V2.6 模型库...")

    with open(OUTPUT_MODEL / "low_load_classifier_v2_6.pkl", "rb") as f:
        clf_model = pickle.load(f)

    with open(OUTPUT_MODEL / "low_load_regressor_v2_6.pkl", "rb") as f:
        low_reg_model = pickle.load(f)

    with open(OUTPUT_MODEL / "normal_load_regressors_v2_6_dict.pkl", "rb") as f:
        normal_regressors = pickle.load(f)

    with open(OUTPUT_MODEL / "feature_meta_classifier_v2_6.pkl", "rb") as f:
        clf_meta = pickle.load(f)

    with open(OUTPUT_MODEL / "feature_meta_low_reg_v2_6.pkl", "rb") as f:
        low_reg_meta = pickle.load(f)

    with open(OUTPUT_MODEL / "feature_meta_normal_reg_v2_6.pkl", "rb") as f:
        normal_reg_meta = pickle.load(f)

    log(f"模型加载完成: 分类器 + 低负荷回归器 + {len(normal_regressors)} 个独立小时模型")
    return clf_model, low_reg_model, normal_regressors, clf_meta, low_reg_meta, normal_reg_meta


# =========================================================
# 14. V2 并行预测（斩断递归链）
# =========================================================
def parallel_predict(clf_model, low_reg_model, normal_regressors,
                     clf_meta, low_reg_meta, normal_reg_meta, predict_df):
    log("开始 V2 并行预测（所有时点同时执行）...")

    pred = predict_df.copy()
    pred["pred_total_load"] = np.nan      # 中间变量：工厂真实用电需求
    pred["final_pred_net_load"] = np.nan  # 最终关口电量
    pred["is_low_load"] = 0
    pred["proba_low"] = np.nan

    # 先按 weather_day_complete 过滤
    weather_ok_mask = pred["weather_day_complete"].astype(bool)
    pred_df_ok = pred[weather_ok_mask].copy()
    pred_df_skip = pred[~weather_ok_mask].copy()

    log(f"天气完整可预测记录: {len(pred_df_ok)}, 天气缺失跳过: {len(pred_df_skip)}")

    if pred_df_ok.empty:
        log("[警告] 无天气完整记录，预测终止")
        return pred

    # 填充数值特征缺失
    use_features = clf_meta["use_features"]
    num_cols = clf_meta["num_cols"]
    num_fill_values = clf_meta["num_fill_values"]
    for col in num_cols:
        if col in pred_df_ok.columns:
            pred_df_ok[col] = pred_df_ok[col].fillna(num_fill_values.get(col, 0))

    # ==== 第一阶段：全量低负荷状态判定 ====
    log("第一阶段：执行全量低负荷状态判定...")
    X_pred = prepare_single_step_features(pred_df_ok, clf_meta)

    if hasattr(clf_model, "predict_proba"):
        proba_low = clf_model.predict_proba(X_pred)[:, 1]
        is_low = (proba_low >= LOW_LOAD_PROBA_THRESHOLD).astype(int)
        pred_df_ok["proba_low"] = proba_low
    else:
        is_low = clf_model.predict(X_pred)
        pred_df_ok["proba_low"] = np.nan

    pred_df_ok["is_low_load"] = is_low
    log(f"判定为低负荷时段: {is_low.sum()} / {len(is_low)}")

    # ==== 第二阶段：低负荷回归器 ====
    mask_low = pred_df_ok["is_low_load"] == 1
    if mask_low.any() and low_reg_model is not None:
        log(f"执行低负荷回归 ({mask_low.sum()} 个样本)...")
        X_low = prepare_single_step_features(pred_df_ok[mask_low], low_reg_meta)
        pred_low = low_reg_model.predict(X_low)
        pred_low = np.clip(pred_low, 0, None)
        pred_df_ok.loc[mask_low, "pred_total_load"] = pred_low

    # ==== 第三阶段：24个独立小时普通回归器（并行路由）====
    log("执行 24个独立的普通负荷回归器（并行路由）...")
    normal_predictions = {}

    for h in range(1, 25):
        hour_mask = (pred_df_ok["hour"] == h) & (pred_df_ok["is_low_load"] == 0)
        if not hour_mask.any():
            continue

        model_key = f"hour_{h}"
        model = normal_regressors.get(model_key)

        if model is None:
            log(f"[警告] Hour {h}:00 无对应模型，使用低负荷模型兜底")
            if low_reg_model is not None:
                X_fallback = prepare_single_step_features(pred_df_ok[hour_mask], low_reg_meta)
                fallback_pred = low_reg_model.predict(X_fallback)
                pred_df_ok.loc[hour_mask, "pred_total_load"] = np.clip(fallback_pred, 0, None)
            continue

        X_hour = prepare_single_step_features(pred_df_ok[hour_mask], clf_meta)
        pred_hour = model.predict(X_hour)
        pred_df_ok.loc[hour_mask, "pred_total_load"] = np.clip(pred_hour, 0, None)
        normal_predictions[h] = len(pred_hour)

    log(f"普通负荷预测统计: {normal_predictions}")

    # 合并回主表
    result_cols = ["pred_total_load", "is_low_load", "proba_low"]
    for c in result_cols:
        if c in pred_df_ok.columns:
            pred.loc[weather_ok_mask, c] = pred_df_ok[c].values

    # ==== P0: 光伏逆向扣减 ====
    log("执行光伏逆向扣减...")
    pred["pred_pv"] = 0.0
    pred["final_pred_net_load"] = pred["pred_total_load"]

    mask_pv_user = pred["是否有光伏_flag"] == 1
    if mask_pv_user.any():
        pred.loc[mask_pv_user, "pred_pv"] = pred[mask_pv_user].apply(
            lambda r: estimate_pv_generation(
                r["shortwave_radiation"], r["temperature"], r["光伏容量(MW)"]
            ), axis=1
        )
        # 关口表计 = 厂区实际需求 - 光伏实时发电
        pred.loc[mask_pv_user, "final_pred_net_load"] = (
            pred.loc[mask_pv_user, "pred_total_load"] - pred.loc[mask_pv_user, "pred_pv"]
        )

    # 物理底线：关口电量不小于0
    pred["final_pred_net_load"] = pred["final_pred_net_load"].clip(lower=0)

    # 对天气缺失的记录，标记为未预测
    pred["predict_status"] = np.where(
        weather_ok_mask, "已预测", "天气缺失未预测"
    )

    log(f"并行预测完成！")
    log(f"  - 有效预测: {weather_ok_mask.sum()} 条")
    log(f"  - 天气缺失: {(~weather_ok_mask).sum()} 条")
    if mask_pv_user.any():
        log(f"  - 光伏用户预测: {mask_pv_user.sum()} 条")

    return pred


# =========================================================
# 15. 导出预测结果为原始格式
# =========================================================
def build_output_sheet_like_original(one_user_pred_df, account_value):
    pred_start = PREDICT_START_TS.normalize()
    pred_end = PREDICT_END_TS.normalize()

    if PREDICT_END_TS != pred_end:
        day_range_end = pred_end
    else:
        day_range_end = pred_end - pd.Timedelta(days=1)

    day_range = pd.date_range(start=pred_start, end=day_range_end, freq="D")

    day_rows = []
    for day in day_range:
        row = {
            "电量年月日": day.strftime("%Y%m%d"),
            "户号": account_value
        }

        day_slice = one_user_pred_df.copy()
        day_slice["base_date"] = np.where(
            day_slice["datetime"].dt.hour == 0,
            (day_slice["datetime"] - pd.Timedelta(days=1)).dt.normalize(),
            day_slice["datetime"].dt.normalize()
        )
        day_slice["base_date"] = pd.to_datetime(day_slice["base_date"])

        one_day = day_slice[day_slice["base_date"] == day]

        all_empty = True
        total_value = 0.0

        for h in range(1, 25):
            target_dt = day + pd.Timedelta(days=1) if h == 24 else day + pd.Timedelta(hours=h)
            hit = one_day[one_day["datetime"] == target_dt]

            if not (PREDICT_START_TS <= target_dt < PREDICT_END_TS):
                v = np.nan
            elif hit.empty or pd.isna(hit["final_pred_net_load"].iloc[0]):
                v = np.nan
            else:
                v = float(hit["final_pred_net_load"].iloc[0])
                all_empty = False
                total_value += v

            row[f"{h}:00"] = v

        row["合计"] = np.nan if all_empty else total_value
        day_rows.append(row)

    final_cols = ["电量年月日", "户号"] + [f"{h}:00" for h in range(1, 25)] + ["合计"]
    return pd.DataFrame(day_rows)[final_cols]


def export_prediction_excels(final_pred):
    log("导出预测 Excel ...")
    grouped = final_pred.dropna(subset=["用户编号"]).groupby(["用户编号", "用户名称"])

    sheet_name = f"{str(PREDICT_START_TS.year)[2:]}.{PREDICT_START_TS.month}"

    for (uid, uname), g in grouped:
        g = g.copy().sort_values("datetime")
        account_value = g["户号"].dropna().astype(str).iloc[0] if g["户号"].notna().any() else uname
        out_sheet = build_output_sheet_like_original(g, account_value)

        safe_name = str(uname).replace("/", "_").replace("\\", "_")
        out_path = OUTPUT_PREDICTION / f"{safe_name}_v2_6.xlsx"

        with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
            out_sheet.to_excel(writer, sheet_name=sheet_name[:31], index=False)

        log(f"已导出：{out_path.name}")


# =========================================================
# 16. 主流程
# =========================================================
def main():
    log("=== 开始 V2.6_Upgraded 预测 ===")
    log(f"PREDICT_START = {PREDICT_START_TS}")
    log(f"PREDICT_END   = {PREDICT_END_TS}")
    log(f"LOW_LOAD_THRESHOLD       = {LOW_LOAD_THRESHOLD}")
    log(f"LOW_LOAD_PROBA_THRESHOLD = {LOW_LOAD_PROBA_THRESHOLD}")

    # 加载模型
    clf_model, low_reg_model, normal_regressors, clf_meta, low_reg_meta, normal_reg_meta = load_models()

    # 加载历史负荷
    history_path = OUTPUT_PROCESSED / "history_load_for_predict_v2_6.csv"
    if not history_path.exists():
        raise FileNotFoundError(f"未找到历史负荷文件: {history_path}")
    history_df = pd.read_csv(history_path, encoding="utf-8-sig")
    history_df["datetime"] = pd.to_datetime(history_df["datetime"], errors="coerce")
    log(f"历史负荷数据: {len(history_df)} 条")

    # 加载气象和主档案
    user_master_df = load_user_master()
    weather_df = load_hourly_weather()

    # 构建预测骨架 + 匹配天气
    predict_skeleton = build_predict_skeleton(user_master_df)
    predict_base_df = merge_predict_weather(predict_skeleton, weather_df)

    # 构造 lag 特征（从历史数据中提取）
    predict_feature_df = build_predict_features(predict_base_df, history_df)

    # V2: 并行预测
    final_pred = parallel_predict(
        clf_model=clf_model,
        low_reg_model=low_reg_model,
        normal_regressors=normal_regressors,
        clf_meta=clf_meta,
        low_reg_meta=low_reg_meta,
        normal_reg_meta=normal_reg_meta,
        predict_df=predict_feature_df
    )

    # 保存长表
    final_pred.to_csv(
        OUTPUT_PREDICTION / "predict_long_v2_6.csv",
        index=False,
        encoding="utf-8-sig"
    )

    # 导出 Excel
    export_prediction_excels(final_pred)

    log("=== V2.6_Upgraded 预测完成 ===")


if __name__ == "__main__":
    main()
