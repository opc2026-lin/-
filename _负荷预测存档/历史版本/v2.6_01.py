# -*- coding: utf-8 -*-
"""
【V2.6 升级版】负荷预测训练脚本
核心升级:
  P0: 光伏显式物理分解（解耦光伏，还原工厂真实用电需求）
  P1: 24个独立小时模型替代全局回归器（斩断递归依赖）
  P2: 验证集 + Early Stopping 防过拟合
  P3: 增强超参数（num_leaves=63, min_child_samples=50, reg_alpha=0.5）
  P4: 低负荷阈值从 50kW 提升至 80kW
"""

import re
import glob
import pickle
import warnings
import numpy as np
import pandas as pd

from pathlib import Path
from sklearn.metrics import mean_absolute_error, mean_squared_error, accuracy_score, f1_score

warnings.filterwarnings("ignore")

try:
    import lightgbm as lgb
    from lightgbm import LGBMRegressor, LGBMClassifier, early_stopping
    MODEL_NAME = "lightgbm"
except Exception:
    from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
    MODEL_NAME = "random_forest"
    log_print = print


# =========================================================
# 1. 参数配置
# =========================================================
PREDICT_START = "2026-06-28 00:00:00"   # 左闭
PREDICT_END = "2026-07-01 00:00:00"     # 右开
TRAIN_MONTHS = 24

LOW_LOAD_THRESHOLD = 80       # V2: 从 50 提升到 80
LOW_LOAD_PROBA_THRESHOLD = 0.40


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
LOG_FILE = OUTPUT_LOGS / "01_train_v2_6_upgraded_log.txt"


def log(msg):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")


with open(LOG_FILE, "w", encoding="utf-8") as f:
    f.write("=== V2.6_Upgraded 训练日志 ===\n")


# =========================================================
# 4. 时间范围
# =========================================================
PREDICT_START_TS = pd.Timestamp(PREDICT_START)
PREDICT_END_TS = pd.Timestamp(PREDICT_END)
TRAIN_END = PREDICT_START_TS
TRAIN_START = PREDICT_START_TS - pd.DateOffset(months=TRAIN_MONTHS)

# V2: 验证集 = 预测起点前30天 (用于 Early Stopping)
VAL_SPLIT_DAYS = 30
VAL_START = PREDICT_START_TS - pd.Timedelta(days=VAL_SPLIT_DAYS)


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
# 6. 通用函数
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
# 7. V2核心: 光伏物理估算
# =========================================================
def estimate_pv_generation(radiation, temp, capacity):
    """标准光伏出力物理公式估算 (V2 显式分解)"""
    if pd.isna(radiation) or pd.isna(temp) or pd.isna(capacity):
        return 0.0
    if radiation <= 0:
        return 0.0
    # 温度系数劣化（以25度为基准，每升1度效率下降0.4%）
    temp_coeff = 1 + (-0.004) * (temp - 25)
    # 容量(MW)转为kW需乘以1000, 系统效率取0.75
    pv_estimated = capacity * 1000 * 0.75 * (radiation / 1000) * temp_coeff
    return max(0.0, pv_estimated)


# =========================================================
# 8. 节假日特征
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


# =========================================================
# 9. 时间行为特征
# =========================================================
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
# 10. 样本权重
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
# 11. 小时气象读取
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


# =========================================================
# 12. 读取主档案
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
    df["所在区_norm"] = df["所在区"].apply(normalize_text)
    df["是否有光伏_flag"] = df["是否有光伏"].apply(convert_yes_no)

    # V2: 读取光伏容量列（如果存在）
    if "光伏容量(MW)" in df.columns:
        df["光伏容量(MW)"] = pd.to_numeric(df["光伏容量(MW)"], errors="coerce").fillna(0)
    else:
        # 尝试推算：如果有光伏且没有容量列，设定默认容量
        log("[警告] 用户主档案表中未找到 '光伏容量(MW)' 列，将使用默认值 0")
        df["光伏容量(MW)"] = 0.0

    log(f"用户主档案表读取完成，共 {len(df)} 条")
    return df


# =========================================================
# 13. 读取负荷
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

    hour_cols = []
    for c in df.columns:
        c1 = str(c).strip()
        if re.fullmatch(r"(1?\d|2[0-4]):00", c1):
            hour_cols.append(c1)
    hour_cols = sorted(hour_cols, key=lambda x: int(x.split(":")[0]))

    if len(hour_cols) != 24:
        raise ValueError(f"{Path(file_path).name}-{sheet_name} 未识别完整 1:00~24:00 列")

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

    def build_datetime(row):
        d = row["date"]
        h = int(str(row["hour_str"]).split(":")[0])
        if pd.isna(d):
            return pd.NaT
        if h == 24:
            return d + pd.Timedelta(days=1)
        return d + pd.Timedelta(hours=h)

    long_df["datetime"] = long_df.apply(build_datetime, axis=1)
    long_df["户号"] = long_df["户号"].astype(str).str.strip()

    # 合并用户档案信息
    long_df["用户编号"] = user_info["用户编号"]
    long_df["用户名称"] = user_info["用户名称"]
    long_df["所在市"] = user_info["所在市"]
    long_df["所在区"] = user_info["所在区"]
    long_df["用户类型"] = user_info["用户类型"]
    long_df["是否有光伏"] = user_info["是否有光伏"]
    long_df["是否有光伏_flag"] = user_info["是否有光伏_flag"]
    long_df["光伏容量(MW)"] = user_info.get("光伏容量(MW)", 0)

    out_cols = [
        "用户编号", "用户名称", "户号", "所在市", "所在区", "用户类型",
        "是否有光伏", "是否有光伏_flag", "光伏容量(MW)", "date", "datetime", "load"
    ]
    return long_df[out_cols].dropna(subset=["datetime"]).sort_values("datetime")


def load_all_user_loads(user_master_df):
    log("读取所有用户训练负荷文件...")
    files = glob.glob(str(LOAD_DIR / "*.xlsx")) + glob.glob(str(LOAD_DIR / "*.xls"))
    if not files:
        raise FileNotFoundError("未找到任何负荷 Excel 文件")

    all_list = []
    user_account_map = {}

    for fp in files:
        file_name = Path(fp).stem
        user_name_norm = normalize_text(file_name)

        matched = user_master_df[user_master_df["用户名称_norm"] == user_name_norm]
        if matched.empty:
            log(f"[警告] 未匹配到主档案：{file_name}")
            continue

        user_info = matched.iloc[0]

        try:
            xls = pd.ExcelFile(fp)
        except Exception as e:
            log(f"[错误] 打开负荷文件失败：{Path(fp).name} -> {e}")
            continue

        valid_sheets = [s for s in xls.sheet_names if in_train_sheet_range(s)]
        for s in valid_sheets:
            try:
                one = parse_one_load_sheet(fp, s, user_info)
                if one is not None and not one.empty:
                    all_list.append(one)
                    if user_info["用户编号"] not in user_account_map and one["户号"].notna().any():
                        user_account_map[user_info["用户编号"]] = str(one["户号"].iloc[0]).strip()
                    log(f"已读取负荷：{Path(fp).name} - {s}")
            except Exception as e:
                log(f"[错误] 读取失败：{Path(fp).name} - {s} -> {e}")

    if not all_list:
        raise ValueError("未读取到任何有效训练负荷数据")

    df = pd.concat(all_list, ignore_index=True)
    df = df.sort_values(["用户编号", "datetime"]).reset_index(drop=True)
    log(f"训练负荷合并完成，共 {len(df)} 条")
    return df, user_account_map


# =========================================================
# 14. 读取小时气象
# =========================================================
def load_hourly_weather():
    log("读取所有小时气象文件...")
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
            missing = [c for c in required if c not in df.columns]
            if missing:
                log(f"[警告] 气象文件缺少关键字段，跳过：{Path(fp).name} -> {missing}")
                continue

            df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
            df = df.dropna(subset=["datetime"]).copy()

            numeric_cols = [
                "temperature", "rainfall", "wind_level", "wind_speed", "wind_angle",
                "pressure", "humidity", "air_quality", "visibility", "cloud",
                "dew_point", "shortwave_radiation"
            ]
            for c in numeric_cols:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")

            df["weather"] = df["weather"].astype(str).str.strip()

            city_list, district_list = [], []
            for x in df["region"]:
                city, district = extract_city_district(x)
                city_list.append(normalize_text(city))
                district_list.append(normalize_text(district))

            df["所在市_norm"] = city_list
            df["所在区_norm"] = district_list
            weather_list.append(df)

            log(f"已读取小时气象：{Path(fp).name}，记录数 {len(df)}")
        except Exception as e:
            log(f"[错误] 读取气象失败：{Path(fp).name} -> {e}")

    if not weather_list:
        raise ValueError("没有成功读取任何有效小时气象文件")

    weather_df = pd.concat(weather_list, ignore_index=True)
    weather_df["datetime"] = pd.to_datetime(weather_df["datetime"]).dt.floor("h")
    weather_df = (
        weather_df.sort_values(["datetime"])
        .drop_duplicates(subset=["所在市_norm", "所在区_norm", "datetime"], keep="last")
        .reset_index(drop=True)
    )

    log(f"小时气象合并完成，共 {len(weather_df)} 条")
    return weather_df


# =========================================================
# 15. 合并训练负荷与气象
# =========================================================
def merge_load_weather_hourly(load_df, weather_df):
    log("合并训练负荷与小时气象...")

    df = load_df.copy()
    df["datetime"] = pd.to_datetime(df["datetime"]).dt.floor("h")
    df["所在市_norm"] = df["所在市"].apply(normalize_text)
    df["所在区_norm"] = df["所在区"].apply(normalize_text)
    df["day_key"] = df["datetime"].dt.date

    w = weather_df.copy()
    w["datetime"] = pd.to_datetime(w["datetime"]).dt.floor("h")

    # 1）严格区县匹配
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

    # 3）某天任一小时仍缺关键天气，则整天训练忽略
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
# 16. 特征工程 (V2: 光伏解耦版本)
# =========================================================
def create_train_features(df):
    log("生成 V2.6 训练特征（光伏解耦版）...")
    df = df.copy()
    df = df.sort_values(["用户编号", "datetime"]).reset_index(drop=True)

    # 补缺失气象列
    for c in ["rainfall", "wind_speed", "pressure", "visibility", "cloud",
              "dew_point", "shortwave_radiation", "air_quality"]:
        if c not in df.columns:
            df[c] = np.nan

    df = add_holiday_features(df)
    df = add_time_behavior_features(df)

    df["cooling_degree"] = np.maximum(df["temperature"] - 24, 0)
    df["heating_degree"] = np.maximum(18 - df["temperature"], 0)

    # ==== V2 核心 P0: 光伏物理估算 + 总负荷还原 ====
    log("正在进行光伏净负荷解耦，还原工厂真实用电需求...")
    df["pv_est"] = 0.0
    mask_pv = df["是否有光伏_flag"] == 1

    if mask_pv.any():
        df.loc[mask_pv, "pv_est"] = df[mask_pv].apply(
            lambda r: estimate_pv_generation(
                r["shortwave_radiation"], r["temperature"], r["光伏容量(MW)"]
            ), axis=1
        )

    # total_load = 关口实际负荷 + 光伏估算发电 → 还原工厂真实用电需求
    df["total_load"] = df["load"] + df["pv_est"]
    # 原始关口负荷保留
    df["actual_load"] = df["load"]
    # 训练目标改为 total_load
    df["load"] = df["total_load"]  # 后续 lag 特征基于 total_load 构建

    # ==== Lag 特征（基于 total_load 构建）====
    df["load_lag_24"] = df.groupby("用户编号")["load"].shift(24)
    df["load_lag_48"] = df.groupby("用户编号")["load"].shift(48)
    df["load_lag_168"] = df.groupby("用户编号")["load"].shift(168)

    same_hour_series = df.groupby(["用户编号", "hour"])["load"]

    df["load_same_hour_mean_3d"] = (
        same_hour_series.shift(1)
        .groupby([df["用户编号"], df["hour"]])
        .rolling(3, min_periods=1)
        .mean()
        .reset_index(level=[0, 1], drop=True)
    )

    df["load_same_hour_mean_7d"] = (
        same_hour_series.shift(1)
        .groupby([df["用户编号"], df["hour"]])
        .rolling(7, min_periods=1)
        .mean()
        .reset_index(level=[0, 1], drop=True)
    )

    df["weekday_hour_key"] = df["weekday"].astype(str) + "_" + df["hour"].astype(str)
    weekday_hour_series = df.groupby(["用户编号", "weekday_hour_key"])["load"]

    df["load_same_weekday_hour_mean_4"] = (
        weekday_hour_series.shift(1)
        .groupby([df["用户编号"], df["weekday_hour_key"]])
        .rolling(4, min_periods=1)
        .mean()
        .reset_index(level=[0, 1], drop=True)
    )

    df["load_same_weekday_hour_mean_8"] = (
        weekday_hour_series.shift(1)
        .groupby([df["用户编号"], df["weekday_hour_key"]])
        .rolling(8, min_periods=1)
        .mean()
        .reset_index(level=[0, 1], drop=True)
    )

    # 工作日/休息日同小时均值
    df["day_type"] = np.where(df["is_workday"] == 1, "workday", "restday")
    df["daytype_hour_key"] = df["day_type"].astype(str) + "_" + df["hour"].astype(str)
    daytype_hour_series = df.groupby(["用户编号", "daytype_hour_key"])["load"]

    df["daytype_same_hour_mean_5"] = (
        daytype_hour_series.shift(1)
        .groupby([df["用户编号"], df["daytype_hour_key"]])
        .rolling(5, min_periods=1)
        .mean()
        .reset_index(level=[0, 1], drop=True)
    )

    df["workday_same_hour_mean_5"] = np.where(df["is_workday"] == 1, df["daytype_same_hour_mean_5"], np.nan)
    df["restday_same_hour_mean_5"] = np.where(df["is_workday"] == 0, df["daytype_same_hour_mean_5"], np.nan)

    # 滚动窗口统计
    df["load_roll_mean_24"] = (
        df.groupby("用户编号")["load"]
        .shift(1)
        .rolling(24, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    df["load_roll_std_24"] = (
        df.groupby("用户编号")["load"]
        .shift(1)
        .rolling(24, min_periods=1)
        .std()
        .reset_index(level=0, drop=True)
    )

    df["load_roll_mean_168"] = (
        df.groupby("用户编号")["load"]
        .shift(1)
        .rolling(168, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    df["load_workhour_only"] = np.where(df["is_workhour"] == 1, df["load"], np.nan)

    df["recent_workhour_mean_3d"] = (
        df.groupby("用户编号")["load_workhour_only"]
        .shift(1)
        .rolling(72, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    df["recent_workhour_mean_7d"] = (
        df.groupby("用户编号")["load_workhour_only"]
        .shift(1)
        .rolling(168, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    # ==== V2: 去掉隐式光伏交互特征（已由显式物理分解替代）====
    # 这里不再生成 pv_radiation_effect 等特征

    # ==== V2: 低负荷标签基于 total_load (V2 阈值 80kW) ====
    df["is_low_load"] = (df["load"] < LOW_LOAD_THRESHOLD).astype(int)

    # 字符列清洗
    for c in ["用户类型", "所在市", "所在区", "weather", "time_segment",
              "wind_direction", "holiday_name", "bias_segment"]:
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip()

    log("V2.6 训练特征生成完成")
    return df


# =========================================================
# 17. 特征列表 (V2: 去掉隐式光伏特征)
# =========================================================
def get_feature_list(train_df):
    use_features = [
        "用户类型", "是否有光伏_flag", "所在市", "所在区",

        "month", "day", "hour", "weekday",
        "is_weekend", "is_workday", "is_active_hour", "is_workhour",
        "is_daytime_8_19",
        "is_morning_ramp", "is_lunch_time", "is_evening_peak",
        "time_segment", "bias_segment",
        "hour_sin", "hour_cos", "weekday_sin", "weekday_cos",

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

        # V2: 不再使用隐式光伏交互特征 (pv_radiation_effect 等)
    ]
    use_features = [c for c in use_features if c in train_df.columns]
    return use_features


# =========================================================
# 18. 训练矩阵准备
# =========================================================
def prepare_matrix(df, target_col, use_features):
    data = df.copy()
    data = data.dropna(subset=[target_col]).copy()

    lag_cols = [c for c in ["load_lag_24", "load_lag_48", "load_lag_168"] if c in data.columns]
    if lag_cols:
        data = data.dropna(subset=lag_cols)

    if data.empty:
        return None, None, None, None, None

    cat_cols = [c for c in ["用户类型", "所在市", "所在区", "weather", "time_segment",
                            "wind_direction", "holiday_name", "bias_segment"] if c in use_features]
    num_cols = [c for c in use_features if c not in cat_cols]

    for col in cat_cols:
        data[col] = data[col].fillna("未知").astype(str)

    for col in num_cols:
        med = data[col].median() if col in data.columns else 0
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
# 19. 导出结果
# =========================================================
def export_feature_importance(model, X_train, file_name):
    if hasattr(model, "feature_importances_"):
        fi = pd.DataFrame({
            "feature": X_train.columns,
            "importance": model.feature_importances_
        }).sort_values("importance", ascending=False)
        fi.to_csv(OUTPUT_PREDICTION / file_name, index=False, encoding="utf-8-sig")


def export_train_metrics_classifier(model, X_train, y_train, file_name):
    pred_cls = model.predict(X_train)
    acc = accuracy_score(y_train, pred_cls)
    f1 = f1_score(y_train, pred_cls)

    out = pd.DataFrame([
        {"metric": "low_load_classifier_accuracy", "value": acc},
        {"metric": "low_load_classifier_f1", "value": f1},
    ])
    out.to_csv(OUTPUT_PREDICTION / file_name, index=False, encoding="utf-8-sig")
    log(f"低负荷分类模型 Accuracy: {acc:.4f}")
    log(f"低负荷分类模型 F1: {f1:.4f}")


def export_train_metrics_regressor(model, X_train, y_train, file_name):
    pred = model.predict(X_train)

    eval_df = pd.DataFrame({
        "y_true": pd.to_numeric(y_train, errors="coerce"),
        "y_pred": pd.to_numeric(pred, errors="coerce")
    }).dropna()

    if eval_df.empty:
        log(f"[警告] {file_name} 无有效评估样本")
        return

    mae = mean_absolute_error(eval_df["y_true"], eval_df["y_pred"])
    rmse = np.sqrt(mean_squared_error(eval_df["y_true"], eval_df["y_pred"]))

    out = pd.DataFrame([
        {"metric": "mae", "value": mae},
        {"metric": "rmse", "value": rmse},
    ])
    out.to_csv(OUTPUT_PREDICTION / file_name, index=False, encoding="utf-8-sig")
    log(f"{file_name} -> MAE: {mae:.4f}, RMSE: {rmse:.4f}")


# =========================================================
# 20. 主流程
# =========================================================
def main():
    log("=== 开始 V2.6_Upgraded 训练 ===")
    log(f"PREDICT_START  = {PREDICT_START_TS}")
    log(f"PREDICT_END    = {PREDICT_END_TS}")
    log(f"TRAIN_START    = {TRAIN_START}")
    log(f"TRAIN_END      = {TRAIN_END}")
    log(f"TRAIN_MONTHS   = {TRAIN_MONTHS}")
    log(f"VAL_SPLIT_DATE = {VAL_START}")
    log(f"LOW_LOAD_THRESHOLD        = {LOW_LOAD_THRESHOLD}")
    log(f"LOW_LOAD_PROBA_THRESHOLD  = {LOW_LOAD_PROBA_THRESHOLD}")
    log("核心升级: P0光伏显式分解 + P1_24小时独立模型 + P2_EarlyStopping")

    # 数据加载
    user_master_df = load_user_master()
    load_df, user_account_map = load_all_user_loads(user_master_df)
    weather_df = load_hourly_weather()

    # 合并
    train_raw_df = merge_load_weather_hourly(load_df, weather_df)
    train_feature_df = create_train_features(train_raw_df)

    # 时间过滤
    train_feature_df = train_feature_df[
        (train_feature_df["datetime"] >= TRAIN_START) &
        (train_feature_df["datetime"] < TRAIN_END)
    ].copy()

    if train_feature_df.empty:
        raise ValueError("V2.6 训练数据为空，请检查负荷与气象数据")

    # 样本权重
    train_feature_df = add_recency_weight(train_feature_df, TRAIN_END)
    train_feature_df = add_time_segment_weight(train_feature_df)
    train_feature_df = add_special_day_weight(train_feature_df)

    train_feature_df["sample_weight"] = (
        train_feature_df["recency_weight"] *
        train_feature_df["time_weight"] *
        train_feature_df["special_day_weight"]
    ).clip(lower=0.05, upper=3.0)

    log(f"样本权重统计: min={train_feature_df['sample_weight'].min():.4f}, "
        f"max={train_feature_df['sample_weight'].max():.4f}, "
        f"mean={train_feature_df['sample_weight'].mean():.4f}")

    use_features = get_feature_list(train_feature_df)
    log(f"使用特征数: {len(use_features)}")
    log(f"特征列表: {use_features}")

    # ======== 1) 低负荷分类模型 ========
    log("\n[阶段1] 训练低负荷分类器...")
    clf_df, X_clf, y_clf, w_clf, clf_meta = prepare_matrix(
        train_feature_df, "is_low_load", use_features
    )
    if X_clf is None or X_clf.empty:
        raise ValueError("分类训练矩阵为空")

    clf_model = LGBMClassifier(
        n_estimators=800,
        learning_rate=0.03,
        num_leaves=31,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=42
    )

    if w_clf is not None:
        clf_model.fit(X_clf, y_clf, sample_weight=w_clf)
    else:
        clf_model.fit(X_clf, y_clf)

    with open(OUTPUT_MODEL / "low_load_classifier_v2_6.pkl", "wb") as f:
        pickle.dump(clf_model, f)

    with open(OUTPUT_MODEL / "feature_meta_classifier_v2_6.pkl", "wb") as f:
        pickle.dump(clf_meta, f)

    export_feature_importance(clf_model, X_clf, "feature_importance_classifier_v2_6.csv")
    export_train_metrics_classifier(clf_model, X_clf, y_clf, "train_metrics_classifier_v2_6.csv")
    log(f"分类样本数: {len(X_clf)}, 低负荷样本数: {y_clf.sum()}")

    # ======== 2) 低负荷回归模型 ========
    log("\n[阶段2] 训练低负荷回归器...")
    low_df_raw = train_feature_df[train_feature_df["is_low_load"] == 1].copy()
    low_df, X_low, y_low, w_low, low_meta = prepare_matrix(
        low_df_raw, "load", use_features
    )

    if X_low is None or X_low.empty:
        log("[警告] 低负荷回归训练矩阵为空，将使用零模型")
        low_model = None
        low_meta = {"use_features": use_features, "cat_cols": [], "num_cols": [],
                    "train_columns": [], "num_fill_values": {}}
    else:
        low_model = LGBMRegressor(
            n_estimators=500,
            objective='regression_l1',
            random_state=42,
            n_jobs=-1
        )

        if w_low is not None:
            low_model.fit(X_low, y_low, sample_weight=w_low)
        else:
            low_model.fit(X_low, y_low)

        export_feature_importance(low_model, X_low, "feature_importance_low_regressor_v2_6.csv")
        export_train_metrics_regressor(low_model, X_low, y_low, "train_metrics_low_regressor_v2_6.csv")

    with open(OUTPUT_MODEL / "low_load_regressor_v2_6.pkl", "wb") as f:
        pickle.dump(low_model, f)

    with open(OUTPUT_MODEL / "feature_meta_low_reg_v2_6.pkl", "wb") as f:
        pickle.dump(low_meta, f)

    log(f"低负荷回归样本数: {len(X_low) if X_low is not None else 0}")

    # ======== 3) P1核心: 24个独立小时普通负荷回归器 ========
    log("\n[阶段3] 训练 24个独立的普通负荷回归器 (Hour-specific Models)...")
    df_normal = train_feature_df[train_feature_df["is_low_load"] == 0].copy()
    log(f"普通负荷训练样本数 (全局): {len(df_normal)}")

    normal_regressors = {}
    val_results = []

    for h in range(1, 25):
        df_hour = df_normal[df_normal["hour"] == h]
        if df_hour.empty:
            log(f"Hour {h}:00 无训练数据，跳过")
            normal_regressors[f"hour_{h}"] = None
            continue

        # 划分训练集和验证集（验证集 = 预测起点前30天）
        train_mask = pd.to_datetime(df_hour["电量年月日"] if "电量年月日" in df_hour.columns
                                     else df_hour["datetime"].dt.date) < VAL_START.date()
        val_mask = ~train_mask

        # 准备训练矩阵
        _, X_train_hour, y_train_hour, _, _ = prepare_matrix(
            df_hour.loc[train_mask], "load", use_features
        )
        _, X_val_hour, y_val_hour, _, _ = prepare_matrix(
            df_hour.loc[val_mask], "load", use_features
        )

        if X_train_hour is None or X_train_hour.empty:
            log(f"Hour {h}:00 训练集为空，跳过")
            normal_regressors[f"hour_{h}"] = None
            continue

        # V2: 增强超参数矩阵
        model = LGBMRegressor(
            n_estimators=1500,         # 放大上限，交给 early_stopping 控制
            learning_rate=0.03,
            num_leaves=63,             # 从 31 提高到 63
            max_depth=8,
            min_child_samples=50,      # 增强噪声过滤
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.5,
            random_state=42,
            n_jobs=-1,
            verbose=-1
        )

        # V2: 启用 Early Stopping
        if X_val_hour is not None and len(X_val_hour) > 0 and len(y_val_hour) > 0:
            model.fit(
                X_train_hour, y_train_hour,
                eval_set=[(X_val_hour, y_val_hour)],
                callbacks=[lgb.early_stopping(stopping_rounds=50, verbose=False)]
            )

            # 记录验证集表现
            val_pred = model.predict(X_val_hour)
            val_mae = mean_absolute_error(y_val_hour, val_pred)
            val_rmse = np.sqrt(mean_squared_error(y_val_hour, val_pred))
            val_results.append({
                "hour": h,
                "train_samples": len(X_train_hour),
                "val_samples": len(X_val_hour),
                "val_mae": val_mae,
                "val_rmse": val_rmse,
                "best_iteration": model.best_iteration_
            })
            log(f"Hour {h}:00 训练完成 (train={len(X_train_hour)}, val={len(X_val_hour)}, "
                f"best_iter={model.best_iteration_}, val_mae={val_mae:.2f}, val_rmse={val_rmse:.2f})")
        else:
            model.fit(X_train_hour, y_train_hour)
            val_results.append({
                "hour": h,
                "train_samples": len(X_train_hour),
                "val_samples": 0,
                "val_mae": np.nan,
                "val_rmse": np.nan,
                "best_iteration": model.best_iteration_ if hasattr(model, "best_iteration_") else model.n_estimators
            })
            log(f"Hour {h}:00 训练完成 (全量训练, train={len(X_train_hour)})")

        normal_regressors[f"hour_{h}"] = model

    # 保存24个模型字典
    with open(OUTPUT_MODEL / "normal_load_regressors_v2_6_dict.pkl", "wb") as f:
        pickle.dump(normal_regressors, f)

    # 保存验证集结果
    val_df = pd.DataFrame(val_results)
    val_df.to_csv(OUTPUT_PREDICTION / "validation_hour_model_results_v2_6.csv", index=False, encoding="utf-8-sig")

    # 保存特征元信息（用第一个小时模型的列）
    sample_hour_model = next((m for m in normal_regressors.values() if m is not None), None)
    if sample_hour_model and X_train_hour is not None:
        normal_meta = clf_meta  # 使用相同特征集
        with open(OUTPUT_MODEL / "feature_meta_normal_reg_v2_6.pkl", "wb") as f:
            pickle.dump(normal_meta, f)

    # ======== 导出数据文件用于预测 ========
    # 历史负荷输出
    history_df = load_df[
        (load_df["datetime"] >= pd.Timestamp("2024-01-01 00:00:00")) &
        (load_df["datetime"] < PREDICT_START_TS)
    ].copy()
    history_df.to_csv(OUTPUT_PROCESSED / "history_load_for_predict_v2_6.csv",
                      index=False, encoding="utf-8-sig")

    pd.DataFrame([
        {"用户编号": k, "户号": v} for k, v in user_account_map.items()
    ]).to_csv(OUTPUT_PROCESSED / "user_account_map_v2_6.csv",
              index=False, encoding="utf-8-sig")

    train_feature_df.to_csv(OUTPUT_PROCESSED / "train_dataset_hourly_v2_6.csv",
                            index=False, encoding="utf-8-sig")
    weather_df.to_csv(OUTPUT_PROCESSED / "hourly_weather_cleaned_v2_6.csv",
                      index=False, encoding="utf-8-sig")

    # 运行配置
    config_df = pd.DataFrame([{
        "PREDICT_START": str(PREDICT_START_TS),
        "PREDICT_END": str(PREDICT_END_TS),
        "TRAIN_START": str(TRAIN_START),
        "TRAIN_END": str(TRAIN_END),
        "TRAIN_MONTHS": TRAIN_MONTHS,
        "VAL_SPLIT_DATE": str(VAL_START),
        "VAL_SPLIT_DAYS": VAL_SPLIT_DAYS,
        "LOW_LOAD_THRESHOLD": LOW_LOAD_THRESHOLD,
        "LOW_LOAD_PROBA_THRESHOLD": LOW_LOAD_PROBA_THRESHOLD,
        "VERSION": "v2.6_upgraded"
    }])
    config_df.to_csv(OUTPUT_MODEL / "run_config_v2_6.csv", index=False, encoding="utf-8-sig")

    log(f"\n=== V2.6 训练完成 ===")
    log(f"分类样本数: {len(X_clf)} (低负荷: {y_clf.sum()})")
    log(f"低负荷回归样本数: {len(X_low) if X_low is not None else 0}")
    log(f"普通负荷样本数: {len(df_normal)}")
    log(f"24小时模型: {sum(1 for v in normal_regressors.values() if v is not None)} 个")


if __name__ == "__main__":
    main()
