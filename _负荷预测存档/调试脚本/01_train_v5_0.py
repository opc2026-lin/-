# -*- coding: utf-8 -*-
"""
Pipeline V3.0 训练脚本
架构升级：
  1. 显式光伏物理分解：PV_est = capacity × eff × (radiation/1000) × (1+tc×(temp-25))
     训练目标 total_load = 实际负荷 + PV_est（还原真实用电需求）
  2. 24 个独立小时普通负荷回归器（每小时独立建模，消除小时间模式干扰）
  3. 验证集 + Early Stopping（防止过拟合）
  4. 增强超参数：num_leaves=63, n_estimators=1500, reg_alpha=0.5
  5. 预测模式：非递归并行预测（消除误差累积）
  6. 移除 lag_1/2/3/6/12 特征（非递归预测无法计算）
  7. 自适应数据格式：支持按月聚合负荷 + 四城市历史天气
"""

import argparse
import re
import glob
import pickle
import warnings
import calendar
import numpy as np
import pandas as pd
import lightgbm as lgb

from pathlib import Path
from sklearn.metrics import mean_absolute_error, mean_squared_error, accuracy_score, f1_score

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
OUTPUT_VALIDATION = BASE_DIR / "output" / "validation"

# Override legacy in-script paths with the real project IO directories.
USER_MASTER_PATH = INPUT_ROOT / "用户主档案表.xlsx"
WEATHER_DIR = INPUT_ROOT / "3.真实天气"
LOAD_DIR = INPUT_ROOT / "1.分时段历史用电信息"

OUTPUT_PROCESSED = OUTPUT_ROOT / "processed"
OUTPUT_MODEL = OUTPUT_ROOT / "model"
OUTPUT_PREDICTION = OUTPUT_ROOT / "prediction"
OUTPUT_LOGS = OUTPUT_ROOT / "logs"
OUTPUT_VALIDATION = OUTPUT_ROOT / "validation"

for p in [OUTPUT_PROCESSED, OUTPUT_MODEL, OUTPUT_PREDICTION, OUTPUT_LOGS, OUTPUT_VALIDATION]:
    p.mkdir(parents=True, exist_ok=True)

# =========================================================
# 2. 预测配置
# =========================================================
PREDICT_START = "2026-07-02 00:00:00"
PREDICT_END = "2026-07-03 00:00:00"
TRAIN_MONTHS = 24
LOW_LOAD_THRESHOLD = 80
LOW_LOAD_PROBA_THRESHOLD = 0.4
USER_MODEL_MIN_SAMPLES = 24
USER_MODEL_MIN_DISTINCT_DAYS = 12


def parse_runtime_args():
    parser = argparse.ArgumentParser(description="Load forecast training runner")
    parser.add_argument("--start-date", help="Prediction start date, format: YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=1, help="Number of forecast days")
    args, _ = parser.parse_known_args()
    return args


RUNTIME_ARGS = parse_runtime_args()
if RUNTIME_ARGS.start_date:
    _runtime_start = pd.Timestamp(RUNTIME_ARGS.start_date).normalize()
    _runtime_days = max(int(RUNTIME_ARGS.days or 1), 1)
    PREDICT_START = _runtime_start.strftime("%Y-%m-%d 00:00:00")
    PREDICT_END = (_runtime_start + pd.Timedelta(days=_runtime_days)).strftime("%Y-%m-%d 00:00:00")

# =========================================================
# 3. 光伏配置
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
# 4. 城市映射（天气 sheet → 城市名）
# =========================================================
WEATHER_SHEET_CITY_MAP = {
    "宁德_俊杰": "宁德",
    "莆田_新兴达": "莆田",
    "福州_超库鲜生": "福州",
    "泉州_德化圣光": "泉州",
}

# =========================================================
# 5. 日志
# =========================================================
LOG_FILE = OUTPUT_LOGS / "01_train_v3_log.txt"

def log(msg):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")

with open(LOG_FILE, "w", encoding="utf-8") as f:
    f.write("=== V3.0 训练日志 ===\n")

# =========================================================
# 6. 节假日配置
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

def calculate_clear_sky_radiation(lat, day_of_year, hour):
    """计算理论晴空水平面总辐射 (W/m²)"""
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
# 7. 通用函数
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

def month_day_count(year, month):
    return calendar.monthrange(year, month)[1]


def normalize_user_type_tag(tag_text):
    text = normalize_text(tag_text) or ""
    if "物业" in text or "园区" in text:
        return "property"
    if "工业" in text or "制造" in text:
        return "industrial"
    if "能源" in text or "充电" in text:
        return "energy"
    return "other"


PROPERTY_USER_KEYWORDS = ["安捷物业", "元兴物业", "象园街道"]
ENERGY_USER_KEYWORDS = ["津太", "津泰"]


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
# 8. 节假日和时间特征
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


def load_user_master_v41():
    df = load_user_master().copy()
    name_candidates = [c for c in df.columns if "用户名称" in str(c)]
    type_candidates = [c for c in df.columns if "类型" in str(c) and "标签" in str(c)]
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

    def get_bias_segment(h):
        if 8 <= h <= 10: return "seg_8_10"
        elif 11 <= h <= 13: return "seg_11_13"
        elif 14 <= h <= 17: return "seg_14_17"
        elif 18 <= h <= 19: return "seg_18_19"
        else: return "seg_other"
    df["bias_segment"] = df["hour"].apply(get_bias_segment)

    df["is_morning_ramp"] = ((df["hour"] >= 8) & (df["hour"] <= 10)).astype(int)
    df["is_lunch_time"] = ((df["hour"] >= 11) & (df["hour"] <= 13)).astype(int)
    df["is_evening_peak"] = ((df["hour"] >= 18) & (df["hour"] <= 22)).astype(int)

    def get_time_segment(h):
        if 0 <= h <= 6: return "night"
        elif 7 <= h <= 10: return "morning_start"
        elif 11 <= h <= 13: return "lunch"
        elif 14 <= h <= 17: return "afternoon"
        elif 18 <= h <= 22: return "evening_peak"
        else: return "late_night"
    df["time_segment"] = df["hour"].apply(get_time_segment)

    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24.0)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24.0)
    weekday0 = df["weekday"] - 1
    df["weekday_sin"] = np.sin(2 * np.pi * weekday0 / 7.0)
    df["weekday_cos"] = np.cos(2 * np.pi * weekday0 / 7.0)
    return df

# =========================================================
# 9. 主档案读取
# =========================================================
def load_user_master():
    log("读取用户主档案表...")
    df = safe_read_table(USER_MASTER_PATH)
    df.columns = [str(c).strip() for c in df.columns]
    if "用户类型标签" not in df.columns:
        df["用户类型标签"] = ""
    df["用户名称_norm"] = df["用户名称"].apply(normalize_text)
    df["是否有光伏_flag"] = df["是否有光伏"].apply(convert_yes_no)
    if "所在区" not in df.columns:
        df["所在区"] = df["所在市"] + "区"
    df["所在市_norm"] = df["所在市"].apply(normalize_text)
    df["所在区_norm"] = df["所在区"].apply(normalize_text)
    log(f"用户主档案表读取完成，共 {len(df)} 条")
    return df

# =========================================================
# 10. 负荷读取（支持按月聚合格式）
# =========================================================
def load_all_user_loads(user_master_df):
    """
    读取负荷数据。支持两种格式：
    1. 按用户拆分文件（每个用户一个Excel，sheet名=月份）
    2. 按月聚合文件（每个文件一个sheet，包含所有用户）
    """
    log("读取所有用户训练负荷文件...")
    files = glob.glob(str(LOAD_DIR / "*.xlsx")) + glob.glob(str(LOAD_DIR / "*.xls"))
    if not files:
        raise FileNotFoundError("未找到任何负荷 Excel 文件")

    all_records = []
    user_account_map = {}

    # 构建用户名称匹配索引
    name_to_uid = {}
    for _, row in user_master_df.iterrows():
        name_to_uid[row["用户名称_norm"]] = row["用户编号"]
        # 也加入去除后缀的版本（如去掉"(套餐用户)"）
        clean_name = row["用户名称_norm"]
        if "(" in clean_name:
            name_to_uid[clean_name.split("(")[0]] = row["用户编号"]

    for fp in files:
        file_name = Path(fp).stem
        log(f"  处理负荷文件: {file_name}")
        try:
            xls = pd.ExcelFile(fp)
        except Exception as e:
            log(f"  [错误] 打开失败: {e}")
            continue

        for sheet_name in xls.sheet_names:
            try:
                df = pd.read_excel(fp, sheet_name=sheet_name)
                df.columns = [str(c).strip() for c in df.columns]
            except Exception as e:
                log(f"  [错误] 读取sheet {sheet_name} 失败: {e}")
                continue

            # 检测格式：按用户拆分 or 按月聚合
            if "电力用户名称" in df.columns:
                # 按月聚合格式：电力用户名称 + 电量年月日 + 1:00~24:00
                df = _parse_monthly_load(df, name_to_uid, user_account_map)
            elif "户号" in df.columns:
                # 按用户拆分格式：户号 + 电量年月日 + 1:00~24:00
                df = _parse_user_load(df, fp, sheet_name, user_master_df, user_account_map)
            else:
                log(f"  [警告] 无法识别格式: {sheet_name}")
                continue

            if df is not None and not df.empty:
                all_records.append(df)

    if not all_records:
        raise ValueError("未读取到任何有效训练负荷数据")

    load_df = pd.concat(all_records, ignore_index=True)
    load_df = load_df.dropna(subset=["用户编号", "datetime"])
    load_df = load_df.sort_values(["用户编号", "datetime"]).reset_index(drop=True)
    log(f"训练负荷合并完成，共 {len(load_df)} 条")

    pd.DataFrame([
        {"用户编号": k, "户号": v} for k, v in user_account_map.items()
    ]).to_csv(OUTPUT_PROCESSED / "user_account_map_v3.csv", index=False, encoding="utf-8-sig")
    return load_df, user_account_map


def _parse_monthly_load(df, name_to_uid, user_account_map):
    """解析按月聚合格式：电力用户名称 + 电量年月日 + 1:00~24:00"""
    if "电量年月日" not in df.columns:
        return None

    # 识别24小时列
    hour_cols = []
    for c in df.columns:
        c1 = str(c).strip()
        if re.fullmatch(r"(1?\d|2[0-4]):00", c1):
            hour_cols.append(c1)
    hour_cols = sorted(hour_cols, key=lambda x: int(x.split(":")[0]))

    if len(hour_cols) < 20:
        return None

    records = []
    for _, row in df.iterrows():
        user_name_raw = str(row.get("电力用户名称", "")).strip()
        if not user_name_raw or user_name_raw == "nan":
            continue

        user_name_norm = normalize_text(user_name_raw)
        uid = name_to_uid.get(user_name_norm)
        if uid is None:
            # 尝试去掉括号后缀
            clean = user_name_norm.split("(")[0]
            uid = name_to_uid.get(clean)

        if uid is None:
            continue

        date_str = str(row["电量年月日"]).strip()
        if len(date_str) != 8 or not date_str.isdigit():
            continue

        for h_str in hour_cols:
            h = int(h_str.split(":")[0])
            val = row.get(h_str)
            if pd.isna(val) or val == 0:
                continue
            if h == 24:
                base_date = pd.Timestamp(f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}")
                dt = base_date + pd.Timedelta(days=1)
            else:
                dt = pd.Timestamp(f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {h:02d}:00:00")
            records.append({
                "用户编号": uid,
                "datetime": dt,
                "load": float(val),
            })

    return pd.DataFrame(records)


def _parse_user_load(df, fp, sheet_name, user_master_df, user_account_map):
    """解析按用户拆分格式：户号 + 电量年月日 + 1:00~24:00"""
    file_name = Path(fp).stem
    user_name_norm = normalize_text(file_name)
    matched = user_master_df[user_master_df["用户名称_norm"] == user_name_norm]
    if matched.empty:
        return None

    user_info = matched.iloc[0]
    uid = user_info["用户编号"]
    if pd.isna(uid):
        return None

    # 提取户号
    if "户号" in df.columns and uid not in user_account_map:
        acc = df["户号"].dropna()
        if len(acc) > 0:
            user_account_map[uid] = str(acc.iloc[0]).strip()

    # 提取24小时列
    hour_cols = []
    for c in df.columns:
        c1 = str(c).strip()
        if re.fullmatch(r"(1?\d|2[0-4]):00", c1):
            hour_cols.append(c1)
    hour_cols = sorted(hour_cols, key=lambda x: int(x.split(":")[0]))

    if len(hour_cols) < 20:
        return None

    df["电量年月日"] = df["电量年月日"].astype(str).str.strip()
    df = df[df["电量年月日"].str.fullmatch(r"\d{8}", na=False)]

    records = []
    for _, row in df.iterrows():
        date_str = row["电量年月日"]
        for h_str in hour_cols:
            h = int(h_str.split(":")[0])
            val = row.get(h_str)
            if pd.isna(val) or val == 0:
                continue
            if h == 24:
                base_date = pd.Timestamp(f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}")
                dt = base_date + pd.Timedelta(days=1)
            else:
                dt = pd.Timestamp(f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {h:02d}:00:00")
            records.append({
                "用户编号": uid,
                "datetime": dt,
                "load": float(val),
            })

    return pd.DataFrame(records)


# =========================================================
# 11. 天气读取（支持四城市历史天气格式）
# =========================================================
def load_hourly_weather():
    """
    读取历史天气数据。支持两种格式：
    1. 标准格式：region + datetime + temperature + ... 列
    2. 四城市历史格式：每sheet一个城市，日期列内含24小时数据
    """
    log("读取小时气象数据...")
    weather_files = (
        glob.glob(str(WEATHER_DIR / "*.xlsx")) +
        glob.glob(str(WEATHER_DIR / "*.xls")) +
        glob.glob(str(WEATHER_DIR / "*.csv"))
    )
    if not weather_files:
        raise FileNotFoundError("未找到任何小时气象文件")

    all_weather = []

    for fp in weather_files:
        fname = Path(fp).name
        log(f"  处理气象文件: {fname}")
        try:
            xls = pd.ExcelFile(fp)
        except Exception as e:
            log(f"  [错误] 打开失败: {e}")
            continue

        for sheet_name in xls.sheet_names:
            # 跳过预测天气 sheet
            if re.search(r"\d+月\d+日", sheet_name):
                continue

            try:
                df = pd.read_excel(fp, sheet_name=sheet_name, header=None)
            except Exception:
                continue

            # 检测格式
            if len(df) > 1 and "变量" in str(df.iloc[1, 0]):
                # 四城市历史天气格式
                parsed = _parse_historical_weather(df, sheet_name)
                if parsed is not None and not parsed.empty:
                    all_weather.append(parsed)
                    log(f"    解析历史天气: {sheet_name} -> {len(parsed)} 条")
            else:
                # 尝试标准格式
                parsed = _parse_standard_weather(fp, sheet_name)
                if parsed is not None and not parsed.empty:
                    all_weather.append(parsed)
                    log(f"    解析标准天气: {sheet_name} -> {len(parsed)} 条")

    if not all_weather:
        raise ValueError("没有成功解析任何有效天气数据")

    weather_df = pd.concat(all_weather, ignore_index=True)
    weather_df["datetime"] = pd.to_datetime(weather_df["datetime"]).dt.floor("h")
    weather_df = weather_df.sort_values("datetime").drop_duplicates(
        subset=["所在市_norm", "所在区_norm", "datetime"], keep="last").reset_index(drop=True)
    log(f"小时气象合并完成，共 {len(weather_df)} 条")
    return weather_df


def _parse_historical_weather(df, sheet_name):
    """
    解析四城市历史天气格式：
    - 每8行一组：日期行、变量行、温度行、辐射行、云量行、湿度行、降雨行、空行
    - 列1-24是小时数据
    """
    city = WEATHER_SHEET_CITY_MAP.get(sheet_name)
    if city is None:
        # 尝试从 sheet 名提取城市
        for key in WEATHER_SHEET_CITY_MAP:
            if key in sheet_name:
                city = WEATHER_SHEET_CITY_MAP[key]
                break
    if city is None:
        return None

    records = []
    i = 0
    while i < len(df):
        row0 = str(df.iloc[i, 0]).strip()
        # 寻找日期行（格式：X月X日 | ...）
        date_match = re.match(r"(\d+)月(\d+)日\s*\|", row0)
        if not date_match:
            i += 1
            continue

        month = int(date_match.group(1))
        day = int(date_match.group(2))
        year = 2026  # 默认年份

        # 根据文件名判断年份：1-5月是2026年，6月是2026年
        # 也可以根据数据上下文推断

        # 变量行 (i+1)
        # 温度行 (i+2)
        temp_row = i + 2 if i + 2 < len(df) else None
        # 辐射行 (i+3)
        rad_row = i + 3 if i + 3 < len(df) else None
        # 云量行 (i+4)
        cloud_row = i + 4 if i + 4 < len(df) else None
        # 湿度行 (i+5)
        hum_row = i + 5 if i + 5 < len(df) else None
        # 降雨行 (i+6)
        rain_row = i + 6 if i + 6 < len(df) else None

        for h in range(24):
            dt = pd.Timestamp(year=year, month=month, day=day, hour=h)

            temp = df.iloc[temp_row, h + 1] if temp_row is not None else np.nan
            rad = df.iloc[rad_row, h + 1] if rad_row is not None else np.nan
            cloud_val = df.iloc[cloud_row, h + 1] if cloud_row is not None else np.nan
            hum = df.iloc[hum_row, h + 1] if hum_row is not None else np.nan
            rain = df.iloc[rain_row, h + 1] if rain_row is not None else np.nan

            records.append({
                "region": f"{city}-{city}区",
                "datetime": dt,
                "temperature": pd.to_numeric(temp, errors="coerce"),
                "shortwave_radiation": pd.to_numeric(rad, errors="coerce"),
                "cloud": pd.to_numeric(cloud_val, errors="coerce"),
                "humidity": pd.to_numeric(hum, errors="coerce"),
                "rainfall": pd.to_numeric(rain, errors="coerce"),
                "所在市_norm": city,
                "所在区_norm": city + "区",
                "weather": "未知",
            })

        i += 8  # 跳过一组（8行）

    if not records:
        return None

    result = pd.DataFrame(records)
    result["datetime"] = pd.to_datetime(result["datetime"])
    return result


def _parse_standard_weather(fp, sheet_name):
    """尝试解析标准天气格式"""
    try:
        for header_row in [0, 1, 2, 3, 4, 5]:
            df = pd.read_excel(fp, sheet_name=sheet_name, header=header_row)
            cols_clean = [clean_col_name(c) for c in df.columns]
            joined = "".join(cols_clean)
            keys = ["地区", "时间", "天气", "温度", "降水量", "湿度"]
            if sum([1 for k in keys if k in joined]) < 4:
                continue

            # 列名映射
            mapping = {}
            for c in df.columns:
                c1 = clean_col_name(c)
                if c1 == "地区": mapping[c] = "region"
                elif c1 == "时间": mapping[c] = "datetime"
                elif c1 == "天气": mapping[c] = "weather"
                elif "温度" in c1 and "露点" not in c1: mapping[c] = "temperature"
                elif "降水量" in c1: mapping[c] = "rainfall"
                elif "湿度" in c1: mapping[c] = "humidity"
                elif "云量" in c1: mapping[c] = "cloud"
                elif "短波辐射" in c1: mapping[c] = "shortwave_radiation"

            df = df.rename(columns=mapping)
            df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
            df = df.dropna(subset=["datetime"])

            city_list, district_list = [], []
            for x in df["region"]:
                city, district = extract_city_district(x)
                city_list.append(normalize_text(city))
                district_list.append(normalize_text(district))
            df["所在市_norm"] = city_list
            df["所在区_norm"] = district_list

            for c in ["temperature", "rainfall", "humidity", "cloud", "shortwave_radiation"]:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")

            return df
    except Exception:
        pass
    return None


# =========================================================
# 12. 合并负荷与天气
# =========================================================
def merge_load_weather_hourly(load_df, weather_df):
    log("合并训练负荷与小时气象...")
    w = weather_df.copy()
    w["datetime"] = pd.to_datetime(w["datetime"], errors="coerce").dt.floor("h")
    load_df = load_df.copy()
    load_df["datetime"] = pd.to_datetime(load_df["datetime"], errors="coerce").dt.floor("h")

    user_master_df = load_user_master_v41()
    uid_to_city = {}
    for _, row in user_master_df.iterrows():
        uid_to_city[row["用户编号"]] = (normalize_text(row["所在市"]), normalize_text(row["所在区"]))

    load_df["所在市_norm"] = load_df["用户编号"].map(lambda x: uid_to_city.get(x, (None, None))[0])
    load_df["所在区_norm"] = load_df["用户编号"].map(lambda x: uid_to_city.get(x, (None, None))[1])

    merged = load_df.merge(w, on=["所在市_norm", "所在区_norm", "datetime"], how="left", suffixes=("", "_w"))

    # 城市级回补
    numeric_weather_cols = [c for c in ["temperature", "rainfall", "wind_level", "wind_speed",
        "wind_angle", "pressure", "humidity", "air_quality", "visibility", "cloud", "dew_point",
        "shortwave_radiation"] if c in w.columns]

    if numeric_weather_cols:
        city_numeric = w.groupby(["所在市_norm", "datetime"], as_index=False)[numeric_weather_cols].mean()
        miss_mask = merged["temperature"].isna() if "temperature" in merged.columns else pd.Series(False, index=merged.index)
        if miss_mask.any():
            retry_base = merged.loc[miss_mask, ["所在市_norm", "datetime"]].reset_index(drop=True)
            retry = retry_base.merge(city_numeric, on=["所在市_norm", "datetime"], how="left")
            for c in numeric_weather_cols:
                if c in retry.columns:
                    merged.loc[miss_mask, c] = retry[c].values

    merged["weather_match_level"] = "district_exact"
    log(f"训练数据合并完成，共 {len(merged)} 条")
    return merged

# =========================================================
# 13. 特征工程（继承 V2.6 全部特征 + V3.0 光伏分解）
# =========================================================
def create_train_features(df):
    log("生成V3.0训练特征...")
    df = df.copy()
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    df = add_holiday_features(df)
    df = add_time_behavior_features(df)

    # 派生气象特征
    for c in ["rainfall", "wind_speed", "pressure", "visibility", "cloud", "dew_point",
              "shortwave_radiation", "air_quality", "wind_level", "wind_angle"]:
        if c not in df.columns:
            df[c] = np.nan
    df["cooling_degree"] = np.maximum(df["temperature"] - 24, 0)
    df["heating_degree"] = np.maximum(18 - df["temperature"], 0)
    df["is_rainy"] = (df["rainfall"] > 0).astype(int)
    df["rainfall_intensity"] = np.where(df["rainfall"] > 0, df["rainfall"], 0)
    df["is_high_humidity"] = (df["humidity"] > 80).astype(int)
    # THI 指数
    dew = df["dew_point"].fillna(df["temperature"] - 5)
    df["temp_humidity_index"] = df["temperature"] + 0.555 * (
        6.11 * np.exp(5417.753 * (1/273.16 - 1/(dew + 273.15))) - 10)
    df["temp_squared"] = df["temperature"] ** 2
    df["humidity_squared"] = df["humidity"] ** 2
    df["cloud_squared"] = df["cloud"] ** 2
    df["radiation_squared"] = df["shortwave_radiation"] ** 2
    user_master = load_user_master_v41()
    type_group_map = dict(zip(user_master["用户编号"], user_master["user_type_group"]))
    property_map = dict(zip(user_master["用户编号"], user_master["is_property_user"]))
    energy_map = dict(zip(user_master["用户编号"], user_master["is_energy_user"]))
    industrial_map = dict(zip(user_master["用户编号"], user_master["is_industrial_user"]))
    df["user_type_group"] = df["用户编号"].map(type_group_map).fillna("industrial")
    df["is_property_user"] = df["用户编号"].map(property_map).fillna(0).astype(int)
    df["is_energy_user"] = df["用户编号"].map(energy_map).fillna(0).astype(int)
    df["is_industrial_user"] = df["用户编号"].map(industrial_map).fillna(1).astype(int)
    df["property_cooling_degree"] = df["is_property_user"] * np.maximum(df["temperature"] - 26, 0)
    df["property_hot_degree"] = df["is_property_user"] * np.maximum(df["temperature"] - 28, 0)
    df["property_workhour_hot"] = df["property_hot_degree"] * df["is_workhour"]
    df["property_active_hour_hot"] = df["property_hot_degree"] * df["is_active_hour"]
    df["energy_cooling_degree"] = df["is_energy_user"] * np.maximum(df["temperature"] - 24, 0)
    df["energy_active_hour_hot"] = df["energy_cooling_degree"] * df["is_active_hour"]
    uid_to_name = dict(zip(user_master["用户编号"], user_master["用户名称"]))
    df["_user_name"] = df["用户编号"].map(uid_to_name)
    df["pv_capacity"] = df["_user_name"].map(PV_CAPACITY_MAP).fillna(0)
    df["pv_est"] = 0.0
    pv_mask = df["pv_capacity"] > 0
    df.loc[pv_mask, "pv_est"] = (
        df.loc[pv_mask, "pv_capacity"] * 1000 * PV_EFFICIENCY *
        (df.loc[pv_mask, "shortwave_radiation"] / 1000) *
        (1 + PV_TEMP_COEFF * (df.loc[pv_mask, "temperature"] - 25))
    )
    df["pv_est"] = df["pv_est"].clip(lower=0)
    df["total_load"] = df["load"] + df["pv_est"]

    # 滞后特征（仅保留始终可计算的 lag_24/48/168）
    df = df.sort_values(["用户编号", "datetime"]).reset_index(drop=True)
    for lag in [24, 48, 168]:
        df[f"load_lag_{lag}"] = df.groupby("用户编号")["total_load"].shift(lag)

    # 滚动统计
    gb = df.groupby("用户编号")["total_load"]
    df["load_roll_mean_24"] = gb.transform(lambda x: x.shift().rolling(24, min_periods=1).mean())
    df["load_roll_std_24"] = gb.transform(lambda x: x.shift().rolling(24, min_periods=2).std())
    df["load_roll_mean_168"] = gb.transform(lambda x: x.shift().rolling(168, min_periods=1).mean())
    df["load_roll_std_168"] = gb.transform(lambda x: x.shift().rolling(168, min_periods=2).std())
    df["load_roll_max_24"] = gb.transform(lambda x: x.shift().rolling(24, min_periods=1).max())
    df["load_roll_min_24"] = gb.transform(lambda x: x.shift().rolling(24, min_periods=1).min())
    df["load_roll_median_24"] = gb.transform(lambda x: x.shift().rolling(24, min_periods=1).median())

    # 同小时/同星期几/工作日特征，改为向量化计算，避免逐行遍历过慢
    hour_gb = df.groupby(["用户编号", "hour"])["total_load"]
    df["load_same_hour_mean_3d"] = hour_gb.transform(lambda x: x.shift().rolling(3, min_periods=1).mean())
    df["load_same_hour_mean_7d"] = hour_gb.transform(lambda x: x.shift().rolling(7, min_periods=1).mean())
    df["load_same_hour_mean_14d"] = hour_gb.transform(lambda x: x.shift().rolling(14, min_periods=1).mean())

    weekday_hour_gb = df.groupby(["用户编号", "hour", "weekday"])["total_load"]
    df["load_same_weekday_hour_mean_4"] = weekday_hour_gb.transform(lambda x: x.shift().rolling(4, min_periods=1).mean())
    df["load_same_weekday_hour_mean_8"] = weekday_hour_gb.transform(lambda x: x.shift().rolling(8, min_periods=1).mean())

    workday_hour = df["is_workday"].fillna(0).astype(int)
    restday_hour = 1 - workday_hour
    workday_gb = df.groupby(["用户编号", "hour", workday_hour])["total_load"]
    restday_gb = df.groupby(["用户编号", "hour", restday_hour])["total_load"]
    df["workday_same_hour_mean_5"] = workday_gb.transform(lambda x: x.shift().rolling(5, min_periods=1).mean())
    df["restday_same_hour_mean_5"] = restday_gb.transform(lambda x: x.shift().rolling(5, min_periods=1).mean())

    workhour_load = df["total_load"].where(df["is_workhour"] == 1)
    df["recent_workhour_mean_3d"] = workhour_load.groupby(df["用户编号"]).transform(lambda x: x.shift().rolling(36, min_periods=1).mean())
    df["recent_workhour_mean_7d"] = workhour_load.groupby(df["用户编号"]).transform(lambda x: x.shift().rolling(84, min_periods=1).mean())


    # 光伏交互特征
    user_master = load_user_master_v41()
    pv_map = dict(zip(user_master["用户编号"], user_master["是否有光伏_flag"]))
    df["是否有光伏_flag"] = df["用户编号"].map(pv_map).fillna(0).astype(int)
    df["pv_radiation_effect"] = df["是否有光伏_flag"] * df["shortwave_radiation"]
    df["pv_temp_effect"] = df["是否有光伏_flag"] * df["temperature"]
    df["pv_temp_radiation_effect"] = df["是否有光伏_flag"] * df["shortwave_radiation"] * df["temperature"]
    df["pv_daytime_radiation"] = df["是否有光伏_flag"] * df["shortwave_radiation"] * df["is_active_hour"]
    df["pv_workhour_radiation"] = df["是否有光伏_flag"] * df["shortwave_radiation"] * df["is_workhour"]

    # V2.6 新增特征
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
    df["_city_lat"] = df["所在市"].apply(_get_city_lat) if "所在市" in df.columns else 26.07
    df["_clear_sky_rad"] = df.apply(
        lambda row: calculate_clear_sky_radiation(row["_city_lat"], row["day_of_year"], row["hour"])
        if not pd.isna(row["shortwave_radiation"]) else np.nan, axis=1)
    df["clear_sky_index"] = np.where(df["_clear_sky_rad"] > 10,
                                     df["shortwave_radiation"] / df["_clear_sky_rad"], np.nan)
    df["clear_sky_index"] = df["clear_sky_index"].clip(0, 2.0)
    df = df.drop(columns=["_city_lat", "_clear_sky_rad", "day_of_year"])

    # ===== V3.0 光伏分解 =====
    uid_to_name = dict(zip(user_master["用户编号"], user_master["用户名称"]))
    df["_user_name"] = df["用户编号"].map(uid_to_name)
    df["pv_capacity"] = df["_user_name"].map(PV_CAPACITY_MAP).fillna(0)
    df["pv_est"] = 0.0
    pv_mask = df["pv_capacity"] > 0
    df.loc[pv_mask, "pv_est"] = (
        df.loc[pv_mask, "pv_capacity"] * 1000 * PV_EFFICIENCY *
        (df.loc[pv_mask, "shortwave_radiation"] / 1000) *
        (1 + PV_TEMP_COEFF * (df.loc[pv_mask, "temperature"] - 25))
    )
    df["pv_est"] = df["pv_est"].clip(lower=0)
    # 训练目标：total_load = 实际负荷 + PV 发电量（还原真实用电需求）
    df["total_load"] = df["load"] + df["pv_est"]
    df = df.drop(columns=["_user_name"])

    # 低负荷标签
    df["is_low_load"] = (df["total_load"] < LOW_LOAD_THRESHOLD).astype(int)

    # 样本权重
    df["datetime"] = pd.to_datetime(df["datetime"])
    max_date = df["datetime"].max()
    df["days_before_end"] = (max_date - df["datetime"]).dt.days
    df["sample_weight"] = 1.0 / (df["days_before_end"] + 1)
    df["sample_weight"] = df["sample_weight"] / df["sample_weight"].mean()
    df["sample_weight"] = df["sample_weight"].clip(0.2, 2.0)

    log(f"V3.0训练特征生成完成")
    return df

# =========================================================
# 14. 特征列表
# =========================================================
def get_feature_list():
    return [
        "hour", "month", "day", "weekday", "is_weekend", "is_workday",
        "is_active_hour", "is_workhour", "is_daytime_8_19",
        "is_morning_ramp", "is_lunch_time", "is_evening_peak",
        "hour_sin", "hour_cos", "weekday_sin", "weekday_cos",
        "is_holiday", "is_adjust_workday", "is_real_restday",
        "is_before_holiday", "is_after_holiday",
        "is_month_start", "is_month_end",
        "temperature", "rainfall", "wind_speed", "pressure", "humidity",
        "visibility", "cloud", "dew_point", "shortwave_radiation", "air_quality",
        "wind_level", "wind_angle",
        "cooling_degree", "heating_degree",
        "is_rainy", "rainfall_intensity", "is_high_humidity",
        "temp_humidity_index", "temp_squared", "humidity_squared",
        "cloud_squared", "radiation_squared",
        "load_lag_24", "load_lag_48", "load_lag_168",
        "load_roll_mean_24", "load_roll_std_24", "load_roll_mean_168", "load_roll_std_168",
        "load_roll_max_24", "load_roll_min_24", "load_roll_median_24",
        "load_same_hour_mean_3d", "load_same_hour_mean_7d", "load_same_hour_mean_14d",
        "load_same_weekday_hour_mean_4", "load_same_weekday_hour_mean_8",
        "workday_same_hour_mean_5", "restday_same_hour_mean_5",
        "recent_workhour_mean_3d", "recent_workhour_mean_7d",
        "是否有光伏_flag",
        "is_property_user", "is_energy_user", "is_industrial_user",
        "property_cooling_degree", "property_hot_degree",
        "property_workhour_hot", "property_active_hour_hot",
        "energy_cooling_degree", "energy_active_hour_hot",
        "pv_radiation_effect", "pv_temp_effect", "pv_temp_radiation_effect",
        "pv_daytime_radiation", "pv_workhour_radiation",
        "day_of_year_sin", "day_of_year_cos",
        "temperature_diff_1h", "temperature_diff_24h",
        "temp_humidity_interaction", "temp_cloud_interaction",
        "load_change_24_48", "clear_sky_index",
        "pv_capacity", "pv_est",
    ]

# =========================================================
# 15. 准备 LightGBM 训练矩阵
# =========================================================
def prepare_model_matrix(feature_df, feature_list, return_meta=True, train_columns_ref=None):
    df = feature_df.copy()
    use_features = [f for f in feature_list if f in df.columns]
    num_cols = use_features  # 所有特征都作为数值特征处理

    num_fill = {}
    for col in num_cols:
        med = df[col].median()
        if pd.isna(med):
            med = 0
        df[col] = df[col].fillna(med)
        num_fill[col] = med

    X = df[use_features].copy()
    X = X.astype(float)

    # 对齐列：预测时使用训练时的列
    if train_columns_ref is not None:
        for c in train_columns_ref:
            if c not in X.columns:
                X[c] = 0.0
        X = X[train_columns_ref]

    train_columns = X.columns.tolist()

    meta = {
        "use_features": use_features,
        "cat_cols": [],
        "num_cols": num_cols,
        "train_columns": train_columns,
        "num_fill_values": num_fill,
    }
    if return_meta:
        return X, meta
    return X

# =========================================================
# 16. 训练主流程
# =========================================================
def main():
    log("=== 开始V3.0训练：光伏分解+24小时独立模型+验证集 Early Stopping ===")
    log(f"PREDICT_START = {PREDICT_START}")
    log(f"PREDICT_END   = {PREDICT_END}")
    log(f"TRAIN_MONTHS  = {TRAIN_MONTHS}")
    log(f"LOW_LOAD_THRESHOLD = {LOW_LOAD_THRESHOLD}")

    # 保存运行配置
    pd.DataFrame([{
        "PREDICT_START": PREDICT_START, "PREDICT_END": PREDICT_END,
        "TRAIN_MONTHS": TRAIN_MONTHS, "LOW_LOAD_THRESHOLD": LOW_LOAD_THRESHOLD,
        "LOW_LOAD_PROBA_THRESHOLD": LOW_LOAD_PROBA_THRESHOLD,
        "USER_MODEL_MIN_SAMPLES": USER_MODEL_MIN_SAMPLES,
        "USER_MODEL_MIN_DISTINCT_DAYS": USER_MODEL_MIN_DISTINCT_DAYS,
        "MODEL_STRATEGY": "user_first_then_group_then_global_with_recent_anchor",
    }]).to_csv(OUTPUT_MODEL / "run_config_v3.csv", index=False, encoding="utf-8-sig")

    # 加载数据
    user_master_df = load_user_master_v41()
    load_df, user_account_map = load_all_user_loads(user_master_df)
    weather_df = load_hourly_weather()
    train_raw_df = merge_load_weather_hourly(load_df, weather_df)

    # 特征工程 + 光伏分解
    feature_df = create_train_features(train_raw_df)
    feature_df = feature_df.dropna(subset=["total_load"]).copy()

    feature_list = get_feature_list()
    available_features = [f for f in feature_list if f in feature_df.columns]
    log(f"特征总数: {len(feature_list)}, 可用: {len(available_features)}")

    # 截止到 PREDICT_START 之前的数据用于训练
    train_mask = feature_df["datetime"] < pd.Timestamp(PREDICT_START)
    train_df = feature_df[train_mask].copy()

    # 自动移除 100% NaN 的特征（数据中不存在）
    nan_ratio = train_df[available_features].isna().mean()
    bad_features = nan_ratio[nan_ratio == 1.0].index.tolist()
    if bad_features:
        log(f"移除 100% 缺失特征: {bad_features}")
        available_features = [f for f in available_features if f not in bad_features]

    # 其余特征填充 NaN
    for col in available_features:
        if train_df[col].isna().any():
            fill_val = train_df[col].median()
            if pd.isna(fill_val):
                fill_val = 0
            train_df[col] = train_df[col].fillna(fill_val)

    # 过滤特征缺失
    train_df = train_df.dropna(subset=available_features + ["total_load", "is_low_load"]).copy()

    # 保存可用特征列表（供预测脚本使用）
    with open(OUTPUT_MODEL / "available_features_v3.pkl", "wb") as f:
        pickle.dump(available_features, f)
    log(f"分类样本数: {len(train_df)}")
    log(f"低负荷样本数: {train_df['is_low_load'].sum()}")
    log(f"普通样本数: {(train_df['is_low_load'] == 0).sum()}")

    # 保存历史负荷供预测使用（使用原始load_df，包含所有时间点，不依赖天气）
    # 保存完整的 load_df 给预测脚本用于滞后特征计算
    history_for_predict = feature_df[["用户编号", "datetime", "total_load"]].copy()
    history_for_predict["datetime"] = pd.to_datetime(history_for_predict["datetime"])
    history_for_predict = history_for_predict.dropna(subset=["total_load"]).sort_values(["用户编号", "datetime"])
    history_for_predict.to_csv(OUTPUT_PROCESSED / "history_load_for_predict_v3.csv",
                               index=False, encoding="utf-8-sig")

    # --- 训练低负荷分类器 ---
    log("开始训练低负荷分类模型：lightgbm")
    X_clf, clf_meta = prepare_model_matrix(train_df, available_features)
    y_clf = train_df["is_low_load"]
    clf_model = lgb.LGBMClassifier(
        n_estimators=500, random_state=42, n_jobs=-1, verbose=-1)
    clf_model.fit(X_clf, y_clf)
    y_clf_pred = clf_model.predict(X_clf)
    acc = accuracy_score(y_clf, y_clf_pred)
    f1 = f1_score(y_clf, y_clf_pred)
    log(f"低负荷分类模型 Accuracy: {acc:.4f}")
    log(f"低负荷分类模型 F1: {f1:.4f}")

    with open(OUTPUT_MODEL / "low_load_classifier_v3.pkl", "wb") as f:
        pickle.dump(clf_model, f)
    with open(OUTPUT_MODEL / "feature_meta_classifier_v3.pkl", "wb") as f:
        pickle.dump(clf_meta, f)

    # --- 训练低负荷回归器 ---
    log("开始训练回归模型 low_load_regressor：lightgbm")
    train_low = train_df[train_df["is_low_load"] == 1].copy()
    if len(train_low) > 0:
        X_low, low_meta = prepare_model_matrix(train_low, available_features)
        y_low = train_low["total_load"]
        low_reg_model = lgb.LGBMRegressor(
            n_estimators=500, objective='regression_l1', random_state=42, n_jobs=-1, verbose=-1)
        low_reg_model.fit(X_low, y_low)
        y_low_pred = low_reg_model.predict(X_low)
        low_mae = mean_absolute_error(y_low, y_low_pred)
        low_rmse = np.sqrt(mean_squared_error(y_low, y_low_pred))
        log(f"train_metrics_low_regressor_v3 -> MAE: {low_mae:.4f}, RMSE: {low_rmse:.4f}")

        with open(OUTPUT_MODEL / "low_load_regressor_v3.pkl", "wb") as f:
            pickle.dump(low_reg_model, f)
        with open(OUTPUT_MODEL / "feature_meta_low_reg_v3.pkl", "wb") as f:
            pickle.dump(low_meta, f)
    else:
        log("[警告] 无低负荷样本，跳过低负荷回归器训练")
        low_mae, low_rmse = np.nan, np.nan

    # --- 训练 24 个独立小时普通负荷回归器 ---
    log("开始训练 24 个独立小时普通负荷回归器 (Hour-specific Models)...")
    train_normal = train_df[train_df["is_low_load"] == 0].copy()
    val_date = pd.Timestamp(PREDICT_START) - pd.DateOffset(months=1)

    normal_regressors = {}
    normal_metas = {}
    all_val_metrics = []

    for h in range(24):
        df_hour = train_normal[train_normal["hour"] == h].copy()
        if df_hour.empty:
            log(f"  Hour {h}:00 无训练数据，跳过")
            continue

        train_h = df_hour[df_hour["datetime"] < val_date]
        val_h = df_hour[df_hour["datetime"] >= val_date]

        if len(train_h) < 50:
            log(f"  Hour {h}:00 训练数据不足 ({len(train_h)}条)，跳过")
            continue

        X_train, meta_h = prepare_model_matrix(train_h, available_features)
        y_train = train_h["total_load"]

        model = lgb.LGBMRegressor(
            n_estimators=1500,
            learning_rate=0.03,
            num_leaves=63,
            max_depth=8,
            min_child_samples=50,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.5,
            random_state=42,
            n_jobs=-1,
            verbose=-1,
        )

        if len(val_h) > 0:
            X_val = prepare_model_matrix(val_h, available_features, return_meta=False, train_columns_ref=X_train.columns.tolist())
            y_val = val_h["total_load"]
            model.fit(X_train, y_train,
                      eval_set=[(X_val, y_val)],
                      callbacks=[lgb.early_stopping(stopping_rounds=50, verbose=False)])
            y_val_pred = model.predict(X_val)
            val_mae = mean_absolute_error(y_val, y_val_pred)
            val_rmse = np.sqrt(mean_squared_error(y_val, y_val_pred))
        else:
            model.fit(X_train, y_train)
            val_mae = np.nan
            val_rmse = np.nan

        normal_regressors[f"hour_{h}"] = model
        normal_metas[f"hour_{h}"] = meta_h

        for user_id, df_user in df_hour.groupby("用户编号"):
            train_u = df_user[df_user["datetime"] < val_date]
            val_u = df_user[df_user["datetime"] >= val_date]
            distinct_days = train_u["datetime"].dt.normalize().nunique()
            if len(train_u) < USER_MODEL_MIN_SAMPLES or distinct_days < USER_MODEL_MIN_DISTINCT_DAYS:
                continue

            X_train_u, meta_u = prepare_model_matrix(train_u, available_features)
            y_train_u = train_u["total_load"]
            model_u = lgb.LGBMRegressor(
                n_estimators=1000,
                learning_rate=0.03,
                num_leaves=31,
                max_depth=8,
                min_child_samples=12,
                subsample=0.9,
                colsample_bytree=0.9,
                reg_alpha=0.2,
                random_state=42,
                n_jobs=-1,
                verbose=-1,
            )

            if len(val_u) > 0:
                X_val_u = prepare_model_matrix(
                    val_u, available_features, return_meta=False, train_columns_ref=X_train_u.columns.tolist()
                )
                y_val_u = val_u["total_load"]
                model_u.fit(
                    X_train_u, y_train_u,
                    eval_set=[(X_val_u, y_val_u)],
                    callbacks=[lgb.early_stopping(stopping_rounds=50, verbose=False)],
                )
            else:
                model_u.fit(X_train_u, y_train_u)

            model_key_u = f"user_{user_id}_hour_{h}"
            normal_regressors[model_key_u] = model_u
            normal_metas[model_key_u] = meta_u
            log(f"    user {user_id} Hour {h:02d}:00 单用户模型训练完成 (train={len(train_u)}, val={len(val_u)})")

        for group_name in ["property", "energy"]:
            df_group = df_hour[df_hour["user_type_group"] == group_name].copy()
            if df_group.empty:
                continue
            train_g = df_group[df_group["datetime"] < val_date]
            val_g = df_group[df_group["datetime"] >= val_date]
            if len(train_g) < 30:
                log(f"    {group_name} Hour {h:02d}:00 鏍锋湰涓嶈冻 ({len(train_g)}鏉★級锛屽洖閫€鍒伴€氱敤妯″瀷")
                continue

            X_train_g, meta_g = prepare_model_matrix(train_g, available_features)
            y_train_g = train_g["total_load"]
            model_g = lgb.LGBMRegressor(
                n_estimators=1200,
                learning_rate=0.03,
                num_leaves=31,
                max_depth=8,
                min_child_samples=20,
                subsample=0.85,
                colsample_bytree=0.85,
                reg_alpha=0.3,
                random_state=42,
                n_jobs=-1,
                verbose=-1,
            )

            if len(val_g) > 0:
                X_val_g = prepare_model_matrix(
                    val_g, available_features, return_meta=False, train_columns_ref=X_train_g.columns.tolist())
                y_val_g = val_g["total_load"]
                model_g.fit(
                    X_train_g, y_train_g,
                    eval_set=[(X_val_g, y_val_g)],
                    callbacks=[lgb.early_stopping(stopping_rounds=50, verbose=False)],
                )
            else:
                model_g.fit(X_train_g, y_train_g)

            model_key_g = f"{group_name}_hour_{h}"
            normal_regressors[model_key_g] = model_g
            normal_metas[model_key_g] = meta_g
            log(f"    {group_name} Hour {h:02d}:00 专用模型训练完成 (train={len(train_g)}, val={len(val_g)})")

        all_val_metrics.append({
            "hour": h, "n_train": len(train_h), "n_val": len(val_h),
            "val_mae": val_mae, "val_rmse": val_rmse,
        })
        log(f"  Hour {h:02d}:00 训练完成 (train={len(train_h)}, val={len(val_h)}, val_mae={val_mae:.2f}, val_rmse={val_rmse:.2f})")

    # 保存 24 个模型
    with open(OUTPUT_MODEL / "normal_load_regressors_v3_dict.pkl", "wb") as f:
        pickle.dump(normal_regressors, f)
    with open(OUTPUT_MODEL / "normal_reg_metas_v3_dict.pkl", "wb") as f:
        pickle.dump(normal_metas, f)

    # 保存验证指标
    val_df = pd.DataFrame(all_val_metrics)
    val_df.to_csv(OUTPUT_VALIDATION / "val_metrics_hourly_v3.csv", index=False, encoding="utf-8-sig")

    # 汇总
    log(f"\n=== 训练完成汇总 ===")
    log(f"低负荷分类: Accuracy={acc:.4f}, F1={f1:.4f}")
    log(f"低负荷回归: MAE={low_mae:.2f} kW, RMSE={low_rmse:.2f} kW" if not pd.isna(low_mae) else "低负荷回归: 无数据")
    log(f"普通回归(24小时独立): {len(normal_regressors)} 个模型")
    if all_val_metrics:
        avg_val_mae = np.nanmean([m["val_mae"] for m in all_val_metrics])
        avg_val_rmse = np.nanmean([m["val_rmse"] for m in all_val_metrics])
        log(f"普通回归验证集平均: MAE={avg_val_mae:.2f} kW, RMSE={avg_val_rmse:.2f} kW")
    log("=== V3.0 训练完成 ===")

if __name__ == "__main__":
    main()






