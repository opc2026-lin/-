# -*- coding: utf-8 -*-

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
    from lightgbm import LGBMRegressor, LGBMClassifier
    MODEL_NAME = "lightgbm"
except Exception:
    from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
    MODEL_NAME = "random_forest"


# =========================================================
# 1. 参数配置（核心改这里）
# =========================================================
PREDICT_START = "2026-06-28 00:00:00"   # 左闭
PREDICT_END = "2026-07-01 00:00:00"     # 右开
TRAIN_MONTHS = 24

LOW_LOAD_THRESHOLD = 50
LOW_LOAD_PROBA_THRESHOLD = 0.40   # 训练脚本仅保存配置，预测脚本使用


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
LOG_FILE = OUTPUT_LOGS / "01_train_v2_5_weatherfix_log.txt"


def log(msg):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")


with open(LOG_FILE, "w", encoding="utf-8") as f:
    f.write("=== V2.5_WeatherFix训练日志 ===\n")


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
# 6. 通用函数
# =========================================================
def normalize_text(x):
    if pd.isna(x):
        return None
    x = str(x).strip()
    x = x.replace("　", "").replace(" ", "")
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
# 7. 节假日特征
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
# 8. 时间行为特征
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
# 9. 样本权重
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
# 10. 小时气象：城市级聚合回补版
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
# 11. 读取主档案
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

    log(f"用户主档案表读取完成，共 {len(df)} 条")
    return df


# =========================================================
# 12. 读取负荷
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

    long_df["用户编号"] = user_info["用户编号"]
    long_df["用户名称"] = user_info["用户名称"]
    long_df["所在市"] = user_info["所在市"]
    long_df["所在区"] = user_info["所在区"]
    long_df["用户类型"] = user_info["用户类型"]
    long_df["是否有光伏"] = user_info["是否有光伏"]
    long_df["是否有光伏_flag"] = user_info["是否有光伏_flag"]

    out_cols = [
        "用户编号", "用户名称", "户号", "所在市", "所在区", "用户类型",
        "是否有光伏", "是否有光伏_flag", "date", "datetime", "load"
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
# 13. 读取小时气象
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
# 14. 合并训练负荷与气象（天气修正版）
# =========================================================
def merge_load_weather_hourly(load_df, weather_df):
    log("合并训练负荷与小时气象（天气修正版）...")

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

    # 2）城市级聚合天气（数值均值）
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
# 15. 特征工程
# =========================================================
def create_train_features(df):
    log("生成V2.5_WeatherFix训练特征...")
    df = df.copy()
    df = df.sort_values(["用户编号", "datetime"]).reset_index(drop=True)

    for c in ["rainfall", "wind_speed", "pressure", "visibility", "cloud", "dew_point", "shortwave_radiation", "air_quality"]:
        if c not in df.columns:
            df[c] = np.nan

    df = add_holiday_features(df)
    df = add_time_behavior_features(df)

    df["cooling_degree"] = np.maximum(df["temperature"] - 24, 0)
    df["heating_degree"] = np.maximum(18 - df["temperature"], 0)

    # 不用 lag_1
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

    # 光伏交互特征（保留）
    df["pv_radiation_effect"] = df["是否有光伏_flag"] * df["shortwave_radiation"]
    df["pv_temp_effect"] = df["是否有光伏_flag"] * df["temperature"]
    df["pv_temp_radiation_effect"] = df["是否有光伏_flag"] * df["shortwave_radiation"] * df["temperature"]
    df["pv_daytime_radiation"] = df["是否有光伏_flag"] * df["shortwave_radiation"] * df["is_active_hour"]
    df["pv_workhour_radiation"] = df["是否有光伏_flag"] * df["shortwave_radiation"] * df["is_workhour"]

    # 低负荷标签
    df["is_low_load"] = (df["load"] < LOW_LOAD_THRESHOLD).astype(int)

    for c in ["用户类型", "所在市", "所在区", "weather", "time_segment", "wind_direction", "holiday_name", "bias_segment"]:
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip()

    log("V2.5_WeatherFix训练特征生成完成")
    return df


# =========================================================
# 16. 特征列表
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

        "pv_radiation_effect", "pv_temp_effect", "pv_temp_radiation_effect",
        "pv_daytime_radiation", "pv_workhour_radiation",
    ]
    use_features = [c for c in use_features if c in train_df.columns]
    return use_features


# =========================================================
# 17. 训练矩阵准备
# =========================================================
def prepare_matrix(df, target_col, use_features):
    data = df.copy()
    data = data.dropna(subset=[target_col]).copy()

    lag_cols = [c for c in ["load_lag_24", "load_lag_48", "load_lag_168"] if c in data.columns]
    if lag_cols:
        data = data.dropna(subset=lag_cols)

    if data.empty:
        return None, None, None, None, None

    cat_cols = [c for c in ["用户类型", "所在市", "所在区", "weather", "time_segment", "wind_direction", "holiday_name", "bias_segment"] if c in use_features]
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
# 18. 训练模型
# =========================================================
def train_classifier(X_train, y_train, sample_weight=None):
    log(f"开始训练低负荷分类模型：{MODEL_NAME}")

    if MODEL_NAME == "lightgbm":
        model = LGBMClassifier(
            n_estimators=800,
            learning_rate=0.03,
            num_leaves=31,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=42
        )
    else:
        model = RandomForestClassifier(
            n_estimators=300,
            random_state=42,
            n_jobs=-1
        )

    if sample_weight is not None:
        model.fit(X_train, y_train, sample_weight=sample_weight)
    else:
        model.fit(X_train, y_train)

    return model


def train_regressor(X_train, y_train, sample_weight=None, model_name="regressor"):
    log(f"开始训练回归模型 {model_name}：{MODEL_NAME}")

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
# 19. 导出结果
# =========================================================
def export_feature_importance(model, X_train, file_name):
    if hasattr(model, "feature_importances_"):
        fi = pd.DataFrame({
            "feature": X_train.columns,
            "importance": model.feature_importances_
        }).sort_values("importance", ascending=False)
        fi.to_csv(OUTPUT_PREDICTION / file_name, index=False, encoding="utf-8-sig")


def export_train_metrics_classifier(model, X_train, y_train):
    pred_cls = model.predict(X_train)
    acc = accuracy_score(y_train, pred_cls)
    f1 = f1_score(y_train, pred_cls)

    out = pd.DataFrame([
        {"metric": "low_load_classifier_accuracy", "value": acc},
        {"metric": "low_load_classifier_f1", "value": f1},
    ])
    out.to_csv(OUTPUT_PREDICTION / "train_metrics_v2_5_weatherfix_classifier.csv", index=False, encoding="utf-8-sig")

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
    log("=== 开始V2.5_WeatherFix训练：修正天气匹配逻辑版 ===")
    log(f"PREDICT_START = {PREDICT_START_TS}")
    log(f"PREDICT_END   = {PREDICT_END_TS}")
    log(f"TRAIN_START   = {TRAIN_START}")
    log(f"TRAIN_END     = {TRAIN_END}")
    log(f"TRAIN_MONTHS  = {TRAIN_MONTHS}")
    log(f"LOW_LOAD_THRESHOLD = {LOW_LOAD_THRESHOLD}")
    log(f"LOW_LOAD_PROBA_THRESHOLD = {LOW_LOAD_PROBA_THRESHOLD}")

    user_master_df = load_user_master()
    load_df, user_account_map = load_all_user_loads(user_master_df)
    weather_df = load_hourly_weather()

    train_raw_df = merge_load_weather_hourly(load_df, weather_df)
    train_feature_df = create_train_features(train_raw_df)

    train_feature_df = train_feature_df[
        (train_feature_df["datetime"] >= TRAIN_START) &
        (train_feature_df["datetime"] < TRAIN_END)
    ].copy()

    if train_feature_df.empty:
        raise ValueError("V2.5_WeatherFix训练数据为空，请检查负荷与气象数据")

    train_feature_df = add_recency_weight(train_feature_df, TRAIN_END)
    train_feature_df = add_time_segment_weight(train_feature_df)
    train_feature_df = add_special_day_weight(train_feature_df)

    train_feature_df["sample_weight"] = (
        train_feature_df["recency_weight"] *
        train_feature_df["time_weight"] *
        train_feature_df["special_day_weight"]
    ).clip(lower=0.05, upper=3.0)

    log(
        "样本权重统计："
        f" min={train_feature_df['sample_weight'].min():.4f},"
        f" max={train_feature_df['sample_weight'].max():.4f},"
        f" mean={train_feature_df['sample_weight'].mean():.4f}"
    )

    use_features = get_feature_list(train_feature_df)

    # 1）低负荷分类模型
    clf_df, X_clf, y_clf, w_clf, clf_meta = prepare_matrix(
        train_feature_df, "is_low_load", use_features
    )
    if X_clf is None or X_clf.empty:
        raise ValueError("V2.5_WeatherFix分类训练矩阵为空")

    clf_model = train_classifier(X_clf, y_clf, sample_weight=w_clf)

    with open(OUTPUT_MODEL / "low_load_classifier_v2_5_weatherfix.pkl", "wb") as f:
        pickle.dump(clf_model, f)

    with open(OUTPUT_MODEL / "feature_meta_classifier_v2_5_weatherfix.pkl", "wb") as f:
        pickle.dump(clf_meta, f)

    export_feature_importance(clf_model, X_clf, "feature_importance_classifier_v2_5_weatherfix.csv")
    export_train_metrics_classifier(clf_model, X_clf, y_clf)

    # 2）低负荷回归模型
    low_df_raw = train_feature_df[train_feature_df["is_low_load"] == 1].copy()
    low_df, X_low, y_low, w_low, low_meta = prepare_matrix(
        low_df_raw, "load", use_features
    )

    if X_low is None or X_low.empty:
        raise ValueError("V2.5_WeatherFix低负荷回归训练矩阵为空")

    low_model = train_regressor(X_low, y_low, sample_weight=w_low, model_name="low_load_regressor")

    with open(OUTPUT_MODEL / "low_load_regressor_v2_5_weatherfix.pkl", "wb") as f:
        pickle.dump(low_model, f)

    with open(OUTPUT_MODEL / "feature_meta_low_reg_v2_5_weatherfix.pkl", "wb") as f:
        pickle.dump(low_meta, f)

    export_feature_importance(low_model, X_low, "feature_importance_low_regressor_v2_5_weatherfix.csv")
    export_train_metrics_regressor(low_model, X_low, y_low, "train_metrics_low_regressor_v2_5_weatherfix.csv")

    # 3）普通回归模型
    normal_df_raw = train_feature_df[train_feature_df["is_low_load"] == 0].copy()
    normal_df, X_normal, y_normal, w_normal, normal_meta = prepare_matrix(
        normal_df_raw, "load", use_features
    )

    if X_normal is None or X_normal.empty:
        raise ValueError("V2.5_WeatherFix普通回归训练矩阵为空")

    normal_model = train_regressor(X_normal, y_normal, sample_weight=w_normal, model_name="normal_load_regressor")

    with open(OUTPUT_MODEL / "normal_load_regressor_v2_5_weatherfix.pkl", "wb") as f:
        pickle.dump(normal_model, f)

    with open(OUTPUT_MODEL / "feature_meta_normal_reg_v2_5_weatherfix.pkl", "wb") as f:
        pickle.dump(normal_meta, f)

    export_feature_importance(normal_model, X_normal, "feature_importance_normal_regressor_v2_5_weatherfix.csv")
    export_train_metrics_regressor(normal_model, X_normal, y_normal, "train_metrics_normal_regressor_v2_5_weatherfix.csv")

    # 历史负荷输出
    history_df = load_df[
        (load_df["datetime"] >= pd.Timestamp("2024-01-01 00:00:00")) &
        (load_df["datetime"] < PREDICT_START_TS)
    ].copy()
    history_df.to_csv(OUTPUT_PROCESSED / "history_load_for_predict_v2_5_weatherfix.csv", index=False, encoding="utf-8-sig")

    pd.DataFrame([
        {"用户编号": k, "户号": v} for k, v in user_account_map.items()
    ]).to_csv(OUTPUT_PROCESSED / "user_account_map_v2_5_weatherfix.csv", index=False, encoding="utf-8-sig")

    train_feature_df.to_csv(OUTPUT_PROCESSED / "train_dataset_hourly_v2_5_weatherfix.csv", index=False, encoding="utf-8-sig")
    weather_df.to_csv(OUTPUT_PROCESSED / "hourly_weather_cleaned_v2_5_weatherfix.csv", index=False, encoding="utf-8-sig")

    config_df = pd.DataFrame([{
        "PREDICT_START": str(PREDICT_START_TS),
        "PREDICT_END": str(PREDICT_END_TS),
        "TRAIN_START": str(TRAIN_START),
        "TRAIN_END": str(TRAIN_END),
        "TRAIN_MONTHS": TRAIN_MONTHS,
        "LOW_LOAD_THRESHOLD": LOW_LOAD_THRESHOLD,
        "LOW_LOAD_PROBA_THRESHOLD": LOW_LOAD_PROBA_THRESHOLD
    }])
    config_df.to_csv(OUTPUT_MODEL / "run_config_v2_5_weatherfix.csv", index=False, encoding="utf-8-sig")

    log(f"分类样本数: {len(X_clf)}")
    log(f"低负荷样本数: {len(X_low)}")
    log(f"普通样本数: {len(X_normal)}")

    log("=== V2.5_WeatherFix训练完成 ===")


if __name__ == "__main__":
    main()
