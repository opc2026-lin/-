# -*- coding: utf-8 -*-
"""
Pipeline V3.0 预测脚本
架构：非递归并行预测 + 光伏逆向扣减
- 第一步：全量低负荷分类（一次性分类所有预测时段）
- 第二步：低负荷回归 + 按小时路由到独立普通回归模型
- 第三步：逆向光伏扣减：final_net_load = predicted_total_load - pv_est

V3.1 修复：
- 修复滚动统计在数据空窗期返回空值的问题（改用最近N个数据点）
- 修复 _get_lag_from_history 返回对齐问题
- 修复 recent_workhour 在数据空窗期的问题
"""

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
# 1. 路径配置
# =========================================================
BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parents[1]
INPUT_ROOT = PROJECT_DIR / "1-1负荷预测输入"
OUTPUT_ROOT = PROJECT_DIR / "1-2负荷预测输出"

USER_MASTER_PATH = BASE_DIR / "input" / "user_master" / "01_用户主档案表.csv"
WEATHER_DIR = BASE_DIR / "input" / "weather"
LOAD_DIR = BASE_DIR / "input" / "load"

OUTPUT_PROCESSED = BASE_DIR / "output" / "processed"
OUTPUT_MODEL = BASE_DIR / "output" / "model"
OUTPUT_PREDICTION = BASE_DIR / "output" / "prediction"
OUTPUT_LOGS = BASE_DIR / "output" / "logs"

# Override legacy in-script paths with the real project IO directories.
USER_MASTER_PATH = INPUT_ROOT / "用户主档案表.xlsx"
WEATHER_DIR = INPUT_ROOT / "2.预测天气"
LOAD_DIR = INPUT_ROOT / "1.分时段历史用电信息"

OUTPUT_PROCESSED = OUTPUT_ROOT / "processed"
OUTPUT_MODEL = OUTPUT_ROOT / "model"
OUTPUT_PREDICTION = OUTPUT_ROOT / "prediction"
OUTPUT_LOGS = OUTPUT_ROOT / "logs"

for p in [OUTPUT_PROCESSED, OUTPUT_MODEL, OUTPUT_PREDICTION, OUTPUT_LOGS]:
    p.mkdir(parents=True, exist_ok=True)

# =========================================================
# 2. 日志
# =========================================================
LOG_FILE = OUTPUT_LOGS / "02_predict_v3_log.txt"

def log(msg):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")

with open(LOG_FILE, "w", encoding="utf-8") as f:
    f.write("=== V3.1 预测日志 ===\n")

# =========================================================
# 3. 读取运行配置
# =========================================================
CONFIG_PATH = OUTPUT_MODEL / "run_config_v3.csv"
if not CONFIG_PATH.exists():
    raise FileNotFoundError(f"未找到 {CONFIG_PATH}，请先运行 01_train_v3.py")

RUN_CONFIG = pd.read_csv(CONFIG_PATH, encoding="utf-8-sig").iloc[0]
PREDICT_START_TS = pd.Timestamp(RUN_CONFIG["PREDICT_START"])
PREDICT_END_TS = pd.Timestamp(RUN_CONFIG["PREDICT_END"])
LOW_LOAD_THRESHOLD = float(RUN_CONFIG["LOW_LOAD_THRESHOLD"])
LOW_LOAD_PROBA_THRESHOLD = float(RUN_CONFIG["LOW_LOAD_PROBA_THRESHOLD"])

# =========================================================
# 4. 光伏配置
# =========================================================
PV_CAPACITY_MAP = {
    "福建俊杰新材料科技股份有限公司": 2.0,
    "福建省莆田市新兴达饲料有限公司": 0.9,
    "福州超库鲜生供应链管理有限公司": 0.4,
    "福建省德化圣光工艺有限公司": 0.4,
}
PV_EFFICIENCY = 0.75
PV_TEMP_COEFF = -0.004

# =========================================================
# 5. 节假日配置
# =========================================================
HOLIDAY_MAP = {
    "2024-01-01": "元旦", "2024-02-10": "春节", "2024-02-11": "春节", "2024-02-12": "春节",
    "2024-02-13": "春节", "2024-02-14": "春节", "2024-02-15": "春节", "2024-02-16": "春节", "2024-02-17": "春节",
    "2024-04-04": "清明节", "2024-04-05": "清明节", "2024-04-06": "清明节",
    "2024-05-01": "劳动节", "2024-05-02": "劳动节", "2024-05-03": "劳动节", "2024-05-04": "劳动节", "2024-05-05": "劳动节",
    "2024-06-08": "端午节", "2024-06-09": "端午节", "2024-06-10": "端午节",
    "2024-09-15": "中秋节", "2024-09-16": "中秋节", "2024-09-17": "中秋节",
    "2024-10-01": "国庆节", "2024-10-02": "国庆节", "2024-10-03": "国庆节", "2024-10-04": "国庆节",
    "2024-10-05": "国庆节", "2024-10-06": "国庆节", "2024-10-07": "国庆节",
    "2025-01-01": "元旦", "2025-01-28": "春节", "2025-01-29": "春节", "2025-01-30": "春节", "2025-01-31": "春节",
    "2025-02-01": "春节", "2025-02-02": "春节", "2025-02-03": "春节", "2025-02-04": "春节",
    "2025-04-04": "清明节", "2025-04-05": "清明节", "2025-04-06": "清明节",
    "2025-05-01": "劳动节", "2025-05-02": "劳动节", "2025-05-03": "劳动节", "2025-05-04": "劳动节", "2025-05-05": "劳动节",
    "2025-05-31": "端午节", "2025-06-01": "端午节", "2025-06-02": "端午节",
    "2025-10-01": "国庆节", "2025-10-02": "国庆节", "2025-10-03": "国庆节", "2025-10-04": "国庆节",
    "2025-10-05": "国庆节", "2025-10-06": "国庆节", "2025-10-07": "国庆节", "2025-10-08": "中秋节",
    "2026-01-01": "元旦", "2026-02-17": "春节", "2026-02-18": "春节", "2026-02-19": "春节", "2026-02-20": "春节",
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

CITY_LAT_MAP = {"福州": 26.07, "宁德": 26.67, "莆田": 25.45, "泉州": 24.87}
WEATHER_SHEET_CITY_MAP = {
    "宁德_俊杰": "宁德", "莆田_新兴达": "莆田", "福州_超库鲜生": "福州", "泉州_德化圣光": "泉州",
    "7月1日": None, "7月2日": None,
}

def calculate_clear_sky_radiation(lat, day_of_year, hour):
    """计算理论晴空水平面总辐射 (W/m2)"""
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
# 6. 通用函数
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
    if x in ["是", "有", "1", "true", "True", "Y", "y"]:
        return 1
    return 0

def clean_col_name(c):
    c = str(c).strip().replace(" ", "").replace("\n", "").replace("\r", "").replace("\t", "")
    c = c.replace("（", "(").replace("）", ")").replace("：", ":")
    return c

def extract_city_district(region_text):
    if pd.isna(region_text):
        return None, None
    txt = str(region_text).strip().replace("―", "-").replace("－", "-").replace("C", "-")
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

# =========================================================
# 7. 节假日和时间特征（与训练一致）
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
# 8. 主档案读取
# =========================================================
def load_user_master():
    log("读取用户主档案表...")
    df = safe_read_table(USER_MASTER_PATH)
    df.columns = [str(c).strip() for c in df.columns]
    df["用户名称_norm"] = df["用户名称"].apply(normalize_text)
    df["是否有光伏_flag"] = df["是否有光伏"].apply(convert_yes_no)
    df["pv_capacity"] = df["用户名称"].map(PV_CAPACITY_MAP).fillna(0)
    log(f"用户主档案表读取完成，共 {len(df)} 条")
    return df

# =========================================================
# 9. 读取预测天气（包含每日预测格式）
# =========================================================
def load_prediction_weather():
    """读取预测天气"""
    log("读取预测天气...")
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
            log(f"  [错误] 打开失败: {e}")
            continue

        for sheet_name in xls.sheet_names:
            try:
                if re.search(r"\d+月\d+日", sheet_name):
                    parsed = _parse_prediction_weather_sheet(fp, sheet_name, xls, source_priority)
                    if parsed is not None and len(parsed) > 0:
                        all_records.extend(parsed)
                        log(f"  解析预测天气: {sheet_name} -> {len(parsed)} 条")
                else:
                    df = pd.read_excel(fp, sheet_name=sheet_name, header=None)
                    if len(df) > 1 and "变量" in str(df.iloc[1, 0]):
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
                            date_match = re.match(r"(\d+)月(\d+)日\s*\|", row0)
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
                                    "所在市_norm": city,
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
                log(f"  [错误] 解析 {sheet_name} 失败: {e}")
                continue

    if not all_records:
        raise ValueError("没有成功解析任何有效预测天气数据")

    weather_df = pd.DataFrame(all_records)
    weather_df["datetime"] = pd.to_datetime(weather_df["datetime"]).dt.floor("h")
    weather_df = weather_df.sort_values(["所在市_norm", "datetime", "__source_priority"]).drop_duplicates(
        subset=["所在市_norm", "datetime"], keep="last").reset_index(drop=True)

    mask = (weather_df["datetime"] >= PREDICT_START_TS) & (weather_df["datetime"] < PREDICT_END_TS)
    weather_pred_df = weather_df[mask].reset_index(drop=True)

    log(f"预测天气读取完成，共 {len(weather_pred_df)} 条（在预测区间内）")
    if "__source_file" in weather_pred_df.columns:
        used_files = sorted(weather_pred_df["__source_file"].dropna().unique().tolist())
        log(f"天气去重后实际采用文件: {used_files}")
    return weather_pred_df


def _parse_prediction_weather_sheet(fp, sheet_name, xls, source_priority):
    """解析预测日天气格式（fujian_pv_daily格式）"""
    try:
        df = pd.read_excel(fp, sheet_name=sheet_name, header=None)
        date_match = re.match(r"(\d+)月(\d+)日", sheet_name)
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
                    "所在市_norm": city_name,
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
# 10. 构建预测骨架
# =========================================================
def build_prediction_skeleton(user_master_df, weather_pred_df):
    """对每个用户，每个预测时段生成骨架"""
    log("构建预测骨架...")
    all_records = []

    uid_to_city = {}
    for _, row in user_master_df.iterrows():
        uid_to_city[row["用户编号"]] = normalize_text(row["所在市"])

    uid_to_pvcap = dict(zip(user_master_df["用户编号"], user_master_df["pv_capacity"]))
    uid_to_name = dict(zip(user_master_df["用户编号"], user_master_df["用户名称"]))

    for _, weather_row in weather_pred_df.iterrows():
        city = weather_row["所在市_norm"]
        dt = weather_row["datetime"]
        for uid, user_city in uid_to_city.items():
            if user_city == city:
                all_records.append({
                    "用户编号": uid,
                    "用户名称": uid_to_name[uid],
                    "datetime": dt,
                    "所在市_norm": city,
                    "pv_capacity": uid_to_pvcap[uid],
                })

    skeleton_df = pd.DataFrame(all_records)
    skeleton_df = skeleton_df.merge(
        weather_pred_df[["所在市_norm", "datetime", "temperature", "shortwave_radiation",
                         "cloud", "humidity", "rainfall"]],
        on=["所在市_norm", "datetime"], how="left")

    # 确保排序：按用户编号 + 时间排序，保证后续 groupby 迭代顺序一致
    skeleton_df = skeleton_df.sort_values(["用户编号", "datetime"]).reset_index(drop=True)

    log(f"预测骨架构建完成，共 {len(skeleton_df)} 条")
    return skeleton_df

# =========================================================
# 11. 从历史获取滞后特征（非递归方案，修复对齐问题）
# =========================================================
def _get_lag_from_history(pred_df, history_df, lag_hours):
    """
    从历史数据获取滞后特征，返回与 pred_df 对齐的 list。
    策略：
    1. 精确匹配 lag_dt
    2. 上周同天同小时（±1天）
    3. 最近同小时（最近5条均值）
    4. 绝对兜底：该用户最近一条数据
    """
    value_col = "total_load" if "total_load" in history_df.columns else "load"
    results = []
    for _, row in pred_df.iterrows():
        uid = row["用户编号"]
        target_dt = row["datetime"]
        lag_dt = target_dt - pd.Timedelta(hours=lag_hours)
        hist_user = history_df[history_df["用户编号"] == uid]

        # 1. 精确匹配
        match = hist_user[hist_user["datetime"] == lag_dt]
        if len(match) > 0:
            results.append(match.iloc[0][value_col])
            continue

        # 2. 上周同天同小时（±1天）
        lag_dt_week = target_dt - pd.Timedelta(days=7)
        match_week = hist_user[
            (hist_user["datetime"].dt.hour == lag_dt.hour) &
            (abs((hist_user["datetime"] - lag_dt_week).dt.days) <= 1)
        ]
        if len(match_week) > 0:
            results.append(match_week[value_col].mean())
            continue

        # 3. 最近同小时（最近5条）
        match_hour = hist_user[hist_user["datetime"].dt.hour == lag_dt.hour]
        if len(match_hour) > 0:
            results.append(match_hour[value_col].tail(5).mean())
            continue

        # 4. 绝对兜底：该用户最近一条数据
        hist_user_sorted = hist_user.sort_values("datetime")
        if len(hist_user_sorted) > 0:
            results.append(hist_user_sorted.iloc[-1][value_col])
        else:
            results.append(np.nan)

    return results


def _compute_rolling_from_history(hist_user, pred_g, window_size, stat_func):
    """
    从历史数据计算滚动统计。
    优先使用时间窗口（最近 window_size 小时），
    如果时间窗口为空（数据空窗期），则回退到最近 window_size 条数据。
    """
    value_col = "total_load" if "total_load" in hist_user.columns else "load"
    results = []
    for _, row in pred_g.iterrows():
        target_dt = row["datetime"]
        window_end = target_dt - pd.Timedelta(hours=1)
        window_start = window_end - pd.Timedelta(hours=window_size)

        # 时间窗口
        window = hist_user[(hist_user["datetime"] > window_start) & (hist_user["datetime"] <= window_end)]
        if len(window) == 0:
            # 回退：使用最近 window_size 条数据
            hist_sorted = hist_user.sort_values("datetime")
            window = hist_sorted.tail(window_size)

        if len(window) > 0:
            results.append(stat_func(window[value_col]))
        else:
            results.append(np.nan)
    return results


def _compute_same_hour_from_history(hist_user, pred_g, n_records):
    """从历史数据取最近 N 条同小时记录"""
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
# 12. 特征工程（与训练一致，修复空窗期问题）
# =========================================================
def build_prediction_features(skeleton_df, history_df):
    """生成预测特征，所有特征都从历史数据非递归计算"""
    log("生成预测特征（V3.1）...")
    df = skeleton_df.copy()
    df = add_holiday_features(df)
    df = add_time_behavior_features(df)

    # 派生气象特征
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

    # ===== 滞后特征（从历史获取，非递归）=====
    for lag in [24, 48, 168]:
        df[f"load_lag_{lag}"] = _get_lag_from_history(df, history_df, lag)

    # ===== 滚动统计（修复：空窗期回退到最近N条数据）=====
    roll_mean_24, roll_std_24, roll_mean_168, roll_std_168 = [], [], [], []
    roll_max_24, roll_min_24, roll_median_24 = [], [], []

    for uid, g in df.groupby("用户编号"):
        hist_user = history_df[history_df["用户编号"] == uid].sort_values("datetime")

        # 24小时窗口
        rm24 = _compute_rolling_from_history(hist_user, g, 24, lambda x: x.mean())
        rs24 = _compute_rolling_from_history(hist_user, g, 24, lambda x: x.std() if len(x) >= 2 else np.nan)
        rmax24 = _compute_rolling_from_history(hist_user, g, 24, lambda x: x.max())
        rmin24 = _compute_rolling_from_history(hist_user, g, 24, lambda x: x.min())
        rmed24 = _compute_rolling_from_history(hist_user, g, 24, lambda x: x.median())

        # 168小时窗口
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

    # ===== 同小时均值 =====
    same_hour_3d, same_hour_7d, same_hour_14d = [], [], []
    for uid, g in df.groupby("用户编号"):
        hist_user = history_df[history_df["用户编号"] == uid]
        sh3 = _compute_same_hour_from_history(hist_user, g, 3)
        sh7 = _compute_same_hour_from_history(hist_user, g, 7)
        sh14 = _compute_same_hour_from_history(hist_user, g, 14)
        same_hour_3d.extend(sh3)
        same_hour_7d.extend(sh7)
        same_hour_14d.extend(sh14)

    df["load_same_hour_mean_3d"] = same_hour_3d
    df["load_same_hour_mean_7d"] = same_hour_7d
    df["load_same_hour_mean_14d"] = same_hour_14d

    # ===== 同星期几同小时 =====
    same_weekday_hour_4, same_weekday_hour_8 = [], []
    for uid, g in df.groupby("用户编号"):
        hist_user = history_df[history_df["用户编号"] == uid]
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

    # ===== 工作日/休息日同小时 =====
    workday_same_hour, restday_same_hour = [], []
    for uid, g in df.groupby("用户编号"):
        hist_user = history_df[history_df["用户编号"] == uid]
        for _, row in g.iterrows():
            h = row["datetime"].hour
            wd_past = hist_user[(hist_user["datetime"].dt.hour == h) & (hist_user["datetime"].dt.weekday < 5)]
            we_past = hist_user[(hist_user["datetime"].dt.hour == h) & (hist_user["datetime"].dt.weekday >= 5)]
            value_col = "total_load" if "total_load" in hist_user.columns else "load"
            workday_same_hour.append(wd_past.tail(5)[value_col].mean() if len(wd_past) > 0 else np.nan)
            restday_same_hour.append(we_past.tail(5)[value_col].mean() if len(we_past) > 0 else np.nan)
    df["workday_same_hour_mean_5"] = workday_same_hour
    df["restday_same_hour_mean_5"] = restday_same_hour

    # ===== 最近工作时段（修复：空窗期回退到最近N条工作时段数据）=====
    recent_workhour_3d, recent_workhour_7d = [], []
    for uid, g in df.groupby("用户编号"):
        hist_user = history_df[history_df["用户编号"] == uid].sort_values("datetime")
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

            # 空窗期回退到最近N条工作时段数据
            if len(past_wh_3d) == 0:
                past_wh_3d = hist_wh.tail(36)
            if len(past_wh_7d) == 0:
                past_wh_7d = hist_wh.tail(84)

            value_col = "total_load" if "total_load" in hist_user.columns else "load"
            recent_workhour_3d.append(past_wh_3d[value_col].mean() if len(past_wh_3d) > 0 else np.nan)
            recent_workhour_7d.append(past_wh_7d[value_col].mean() if len(past_wh_7d) > 0 else np.nan)
    df["recent_workhour_mean_3d"] = recent_workhour_3d
    df["recent_workhour_mean_7d"] = recent_workhour_7d

    # ===== 光伏交互特征 =====
    user_master = load_user_master()
    pv_map = dict(zip(user_master["用户编号"], user_master["是否有光伏_flag"]))
    df["是否有光伏_flag"] = df["用户编号"].map(pv_map).fillna(0).astype(int)
    df["pv_radiation_effect"] = df["是否有光伏_flag"] * df["shortwave_radiation"]
    df["pv_temp_effect"] = df["是否有光伏_flag"] * df["temperature"]
    df["pv_temp_radiation_effect"] = df["是否有光伏_flag"] * df["shortwave_radiation"] * df["temperature"]
    df["pv_daytime_radiation"] = df["是否有光伏_flag"] * df["shortwave_radiation"] * df["is_active_hour"]
    df["pv_workhour_radiation"] = df["是否有光伏_flag"] * df["shortwave_radiation"] * df["is_workhour"]

    # ===== V2.6 新增特征 =====
    df["day_of_year"] = df["datetime"].dt.dayofyear
    df["day_of_year_sin"] = np.sin(2 * np.pi * df["day_of_year"] / 365.0)
    df["day_of_year_cos"] = np.cos(2 * np.pi * df["day_of_year"] / 365.0)
    df["temperature_diff_1h"] = df.groupby("用户编号")["temperature"].diff(1)
    df["temperature_diff_24h"] = df.groupby("用户编号")["temperature"].diff(24)
    df["temp_humidity_interaction"] = df["temperature"] * df["humidity"]
    df["temp_cloud_interaction"] = df["temperature"] * df["cloud"]
    df["load_change_24_48"] = df["load_lag_24"] - df["load_lag_48"]

    def _get_city_lat(city_name):
        return CITY_LAT_MAP.get(str(city_name).strip(), 26.07)
    df["_city_lat"] = df["所在市_norm"].apply(_get_city_lat)
    df["clear_sky_index"] = df.apply(
        lambda row: calculate_clear_sky_radiation(row["_city_lat"], row["day_of_year"], row["hour"])
        if not pd.isna(row["shortwave_radiation"]) else np.nan, axis=1)
    df["clear_sky_index"] = np.where(df["clear_sky_index"] > 10,
                                     df["shortwave_radiation"] / df["clear_sky_index"], np.nan)
    df["clear_sky_index"] = df["clear_sky_index"].clip(0, 2.0)
    df = df.drop(columns=["_city_lat", "day_of_year"])

    # ===== V3.0 光伏分解 =====
    df["pv_est"] = 0.0
    pv_mask = df["pv_capacity"] > 0
    df.loc[pv_mask, "pv_est"] = (
        df.loc[pv_mask, "pv_capacity"] * 1000 * PV_EFFICIENCY *
        (df.loc[pv_mask, "shortwave_radiation"] / 1000) *
        (1 + PV_TEMP_COEFF * (df.loc[pv_mask, "temperature"] - 25))
    )
    df["pv_est"] = df["pv_est"].clip(lower=0)

    # ===== 填充所有 NaN =====
    with open(OUTPUT_MODEL / "available_features_v3.pkl", "rb") as f:
        available_features = pickle.load(f)

    for col in available_features:
        if col in df.columns and df[col].isna().any():
            med = df[col].median()
            if pd.isna(med):
                med = 0
            df[col] = df[col].fillna(med)

    log("V3.1预测特征生成完成")
    return df, available_features

# =========================================================
# 13. 编码预测特征（对齐训练列）
# =========================================================
def encode_prediction_features(pred_df, available_features, clf_meta):
    """对齐训练时的列顺序"""
    X = pred_df[available_features].copy()
    X = X.astype(float)
    train_columns = clf_meta["train_columns"]
    for c in train_columns:
        if c not in X.columns:
            X[c] = 0.0
    X = X[train_columns]
    return X

# =========================================================
# 14. 主预测流程
# =========================================================
def main():
    log("=== 开始V3.1预测：非递归并行预测 + 光伏逆向扣减 ===")
    log(f"预测区间: {PREDICT_START_TS} to {PREDICT_END_TS}")

    # 加载模型
    log("加载训练好的模型...")
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

    # 读取历史供滞后特征
    history_path = OUTPUT_PROCESSED / "history_load_for_predict_v3.csv"
    if not history_path.exists():
        raise FileNotFoundError(f"未找到历史数据 {history_path}，请先运行训练")
    history_df = pd.read_csv(history_path, encoding="utf-8-sig")
    history_df["datetime"] = pd.to_datetime(history_df["datetime"])
    log(f"读取历史负荷，共 {len(history_df)} 条")

    # 预测流程
    user_master_df = load_user_master()
    weather_pred_df = load_prediction_weather()
    skeleton_df = build_prediction_skeleton(user_master_df, weather_pred_df)
    feature_df, available_features = build_prediction_features(skeleton_df, history_df)

    # 第一步：全量低负荷分类
    log("第一步：全量低负荷分类...")
    X_clf = encode_prediction_features(feature_df, available_features, clf_meta)
    feature_df["proba_low"] = clf_model.predict_proba(X_clf)[:, 1]
    feature_df["is_low_load_pred"] = (feature_df["proba_low"] >= LOW_LOAD_PROBA_THRESHOLD).astype(int)
    low_count = feature_df["is_low_load_pred"].sum()
    normal_count = (feature_df["is_low_load_pred"] == 0).sum()
    log(f"分类完成：预测低负荷 {low_count} 个 ({low_count/len(feature_df)*100:.1f}%)，普通负荷 {normal_count} 个 ({normal_count/len(feature_df)*100:.1f}%)")

    # 第二步：低负荷回归
    log("第二步：低负荷回归...")
    feature_df["pred_total_load"] = 0.0
    low_mask = feature_df["is_low_load_pred"] == 1
    if low_mask.any():
        X_low = encode_prediction_features(feature_df[low_mask], available_features, low_meta)
        feature_df.loc[low_mask, "pred_total_load"] = low_reg_model.predict(X_low)
        log(f"完成低负荷回归：{low_mask.sum()} 时段")

    # 第三步：普通负荷按小时路由到独立模型
    log("第三步：普通负荷按小时路由到独立模型...")
    for h in range(24):
        hour_mask = (feature_df["hour"] == h) & (feature_df["is_low_load_pred"] == 0)
        if not hour_mask.any():
            continue
        model_key = f"hour_{h}"
        if model_key not in normal_regressors:
            log(f"  警告：Hour {h}:00 无模型，跳过")
            continue
        model = normal_regressors[model_key]
        meta = normal_metas[model_key]
        X_h = encode_prediction_features(feature_df[hour_mask], available_features, meta)
        feature_df.loc[hour_mask, "pred_total_load"] = model.predict(X_h)
        log(f"  Hour {h:02d}:00 完成预测")

    # 第四步：光伏逆向扣减：最终净负荷 = 预测总负荷 - 光伏估算
    log("第四步：光伏逆向扣减生成最终关口预测...")
    feature_df["pred_net_load"] = feature_df["pred_total_load"] - feature_df["pv_est"]
    feature_df["pred_net_load"] = feature_df["pred_net_load"].clip(lower=0)

    # 保存结果长表
    result_long = feature_df[[
        "用户编号", "用户名称", "datetime", "hour", "pv_capacity", "pv_est",
        "proba_low", "is_low_load_pred", "pred_total_load", "pred_net_load"
    ]].copy()
    result_long.to_csv(OUTPUT_PREDICTION / "prediction_result_v3_long.csv",
                       index=False, encoding="utf-8-sig")
    log(f"预测结果长表已保存：{len(result_long)} 条")

    # 生成宽表（用户 x 小时）
    log("生成预测宽表...")
    pred_date = PREDICT_START_TS.strftime("%Y-%m-%d")
    weekday_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][PREDICT_START_TS.weekday()]

    pivot = result_long.pivot(index="用户名称", columns="hour", values="pred_net_load")
    pivot_mwh = pivot / 1000.0
    pivot_mwh = pivot_mwh.reindex(columns=range(24))
    hour_cols = [f"{h+1}:00" for h in range(24)]
    pivot_mwh.columns = hour_cols
    pivot_mwh = pivot_mwh.reset_index()
    pivot_mwh.insert(0, "序号", range(1, len(pivot_mwh) + 1))
    pivot_mwh["日合计"] = pivot_mwh[hour_cols].sum(axis=1)

    # ===== 24时段分时汇总行 =====
    hourly_sum = pivot_mwh[hour_cols].sum(axis=0).tolist()
    # 用户日合计已经计算好了，所以total_dayly_total就是用户日合计之和
    daily_total = pivot_mwh["日合计"].sum()
    total_row = pd.DataFrame([{
        "序号": "", "用户名称": "24时段合计",
        **{hcol: hourly_sum[i] for i, hcol in enumerate(hour_cols)},
        "日合计": daily_total,
    }])
    pivot_mwh = pd.concat([pivot_mwh, total_row], ignore_index=True)

    pivot_mwh.to_csv(OUTPUT_PREDICTION / f"prediction_{pred_date}_v3.csv",
                    index=False, encoding="utf-8-sig")
    log(f"预测宽表已保存（含24时段分时汇总）")
    log(f"总预测电量: {daily_total:.2f} MWh")

    # 输出关键统计
    log(f"\n=== 预测摘要 ===")
    log(f"全网总关口电量: {daily_total:.2f} MWh")
    log(f"低负荷分类占比: {low_count}/{len(feature_df)} = {low_count/len(feature_df)*100:.1f}%")
    log(f"光伏总估算: {feature_df['pv_est'].sum()/1000:.2f} MWh")
    log(f"预测总需求均值: {feature_df['pred_total_load'].mean():.2f} kW")
    log(f"预测关口均值: {feature_df['pred_net_load'].mean():.2f} kW")
    log("=== V3.1 预测完成 ===")

if __name__ == "__main__":
    main()
