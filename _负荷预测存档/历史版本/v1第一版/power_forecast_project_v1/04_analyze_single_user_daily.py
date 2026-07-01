# -*- coding: utf-8 -*-

import re
import glob
import warnings
import numpy as np
import pandas as pd

from pathlib import Path

warnings.filterwarnings("ignore")


# =========================================================
# 1. 参数配置
# =========================================================
TARGET_USER_NAME = "福建俊杰新材料科技股份有限公司"

ANALYZE_START = "2026-03-01 00:00:00"
ANALYZE_END = "2026-05-31 23:59:59"


# =========================================================
# 2. 路径配置
# =========================================================
BASE_DIR = Path(__file__).resolve().parent

USER_MASTER_PATH = BASE_DIR / "input" / "user_master" / "01_用户主档案表.csv"
WEATHER_DIR = BASE_DIR / "input" / "weather"
LOAD_DIR = BASE_DIR / "input" / "load"

OUTPUT_ANALYSIS = BASE_DIR / "output" / "analysis"
OUTPUT_LOGS = BASE_DIR / "output" / "logs"

for p in [OUTPUT_ANALYSIS, OUTPUT_LOGS]:
    p.mkdir(parents=True, exist_ok=True)


# =========================================================
# 3. 日志
# =========================================================
SAFE_USER_NAME = TARGET_USER_NAME.replace("/", "_").replace("\\", "_")
LOG_FILE = OUTPUT_LOGS / f"analyze_single_user_daily_{SAFE_USER_NAME}.log"


def log(msg):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")


with open(LOG_FILE, "w", encoding="utf-8") as f:
    f.write("=== 单用户日级分析日志 ===\n")


# =========================================================
# 4. 时间范围
# =========================================================
ANALYZE_START_TS = pd.Timestamp(ANALYZE_START)
ANALYZE_END_TS = pd.Timestamp(ANALYZE_END)


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
# 7. 主档案读取
# =========================================================
def load_user_master():
    log("读取用户主档案表...")
    df = safe_read_table(USER_MASTER_PATH)
    df.columns = [str(c).strip() for c in df.columns]
    df["用户名称_norm"] = df["用户名称"].apply(normalize_text)
    df["所在市_norm"] = df["所在市"].apply(normalize_text)
    df["所在区_norm"] = df["所在区"].apply(normalize_region_name)
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
            raise ValueError("未识别到负荷表头")

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

    return long_df[["用户编号", "用户名称", "户号", "datetime", "load", "所在市", "所在区"]].dropna(subset=["datetime"])


def load_single_user_hourly(user_master_df):
    log(f"读取目标用户负荷：{TARGET_USER_NAME}")

    target_norm = normalize_text(TARGET_USER_NAME)
    matched = user_master_df[user_master_df["用户名称_norm"] == target_norm]
    if matched.empty:
        raise ValueError(f"主档案表中未找到目标用户：{TARGET_USER_NAME}")

    user_info = matched.iloc[0]

    files = list(Path(LOAD_DIR).glob("*.xlsx")) + list(Path(LOAD_DIR).glob("*.xls"))
    target_file = None
    for fp in files:
        if normalize_text(fp.stem) == target_norm:
            target_file = fp
            break

    if target_file is None:
        raise FileNotFoundError(f"未找到该用户负荷文件：{TARGET_USER_NAME}")

    xls = pd.ExcelFile(target_file)
    all_list = []

    for s in xls.sheet_names:
        try:
            one = parse_one_load_sheet(target_file, s, user_info)
            if one is not None and not one.empty:
                all_list.append(one)
                log(f"已读取负荷：{target_file.name} - {s}")
        except Exception as e:
            log(f"[错误] 读取失败：{target_file.name} - {s} -> {e}")

    if not all_list:
        raise ValueError(f"未读取到任何负荷数据：{TARGET_USER_NAME}")

    df = pd.concat(all_list, ignore_index=True)
    df = df.sort_values("datetime").reset_index(drop=True)

    # 只保留分析时间范围
    df = df[(df["datetime"] >= ANALYZE_START_TS) & (df["datetime"] <= ANALYZE_END_TS)].copy()

    log(f"单用户小时负荷记录数：{len(df)}")
    return df, user_info


# =========================================================
# 9. 天气读取
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

    weather_files = [fp for fp in weather_files if not Path(fp).name.startswith("~$")]

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
# 10. 合并单用户负荷与天气
# =========================================================
def merge_user_weather(load_df, weather_df, user_info):
    log("合并单用户负荷与天气...")

    df = load_df.copy()
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce").dt.floor("h")
    df["所在市_norm"] = df["所在市"].apply(normalize_text)
    df["所在区_norm"] = df["所在区"].apply(normalize_region_name)

    w = weather_df.copy()
    w["datetime"] = pd.to_datetime(w["datetime"], errors="coerce").dt.floor("h")

    merged = df.merge(
        w,
        on=["所在市_norm", "所在区_norm", "datetime"],
        how="left",
        suffixes=("", "_w")
    )

    if "temperature" in merged.columns:
        miss_mask = merged["temperature"].isna()
    else:
        miss_mask = pd.Series(False, index=merged.index)

    if miss_mask.any():
        city_numeric_cols = [
            c for c in [
                "temperature", "rainfall", "wind_level", "wind_speed", "wind_angle",
                "pressure", "humidity", "air_quality", "visibility", "cloud",
                "dew_point", "shortwave_radiation"
            ] if c in w.columns
        ]

        city_numeric = (
            w.groupby(["所在市_norm", "datetime"], as_index=False)[city_numeric_cols]
            .mean()
        )

        retry_base = merged.loc[miss_mask, ["所在市_norm", "datetime"]].reset_index(drop=True)
        retry = retry_base.merge(city_numeric, on=["所在市_norm", "datetime"], how="left")

        for c in city_numeric_cols:
            if c in retry.columns:
                merged.loc[miss_mask, c] = retry[c].values

        merged.loc[miss_mask, "weather_match_level"] = "city_agg"

    if "weather_match_level" not in merged.columns:
        merged["weather_match_level"] = "district_exact"
    else:
        merged["weather_match_level"] = merged["weather_match_level"].fillna("district_exact")

    # 补节假日 / 时间特征
    merged = add_holiday_features(merged)
    merged = add_time_behavior_features(merged)

    # 构造按天统计基础
    merged["date_day"] = merged["datetime"].dt.normalize()
    merged["day_key"] = merged["datetime"].dt.date

    log("天气匹配层级统计：")
    log(merged["weather_match_level"].value_counts(dropna=False).to_dict())

    return merged

# =========================================================
# 11. 构造单用户日级分析表
# =========================================================
def build_daily_profile(merged_df):
    log("构造单用户日级画像...")

    df = merged_df.copy()
    df["hour"] = df["datetime"].dt.hour

    df["is_daytime_8_19"] = df["hour"].between(8, 19).astype(int)
    df["is_night"] = (1 - df["is_daytime_8_19"]).astype(int)

    df["daytime_load"] = np.where(df["is_daytime_8_19"] == 1, df["load"], 0)
    df["night_load"] = np.where(df["is_night"] == 1, df["load"], 0)

    agg_dict = {
        "load": ["sum", "mean", "max", "min", "std"],
        "daytime_load": ["sum", "mean"],
        "night_load": ["sum", "mean"],
        "temperature": ["mean", "max", "min"],
        "humidity": ["mean", "max", "min"],
        "rainfall": ["sum", "mean"],
        "shortwave_radiation": ["sum", "mean", "max"],
        "pressure": ["mean"],
        "cloud": ["mean"],
        "dew_point": ["mean"],
        "is_workday": ["max"],
        "is_holiday": ["max"],
        "is_before_holiday": ["max"],
        "is_after_holiday": ["max"],
        "is_month_start": ["max"],
        "is_month_end": ["max"],
        "weather_match_level": [lambda x: x.mode().iloc[0] if not x.mode().empty else np.nan]
    }

    daily = df.groupby("date_day").agg(agg_dict)

    # 扁平化列名
    daily.columns = [
        "_".join([str(i) for i in col if str(i) != ""])
        .replace("<lambda>", "mode")
        for col in daily.columns
    ]
    daily = daily.reset_index()

    # 重命名更直观
    rename_map = {
        "date_day": "date",
        "load_sum": "daily_total_load",
        "load_mean": "day_mean_load",
        "load_max": "day_peak_load",
        "load_min": "day_valley_load",
        "load_std": "day_std_load",

        "daytime_load_sum": "daytime_total_load",
        "daytime_load_mean": "daytime_mean_load",
        "night_load_sum": "night_total_load",
        "night_load_mean": "night_mean_load",

        "temperature_mean": "temp_mean",
        "temperature_max": "temp_max",
        "temperature_min": "temp_min",

        "humidity_mean": "humidity_mean",
        "humidity_max": "humidity_max",
        "humidity_min": "humidity_min",

        "rainfall_sum": "rainfall_total",
        "rainfall_mean": "rainfall_mean",

        "shortwave_radiation_sum": "radiation_total",
        "shortwave_radiation_mean": "radiation_mean",
        "shortwave_radiation_max": "radiation_max",

        "pressure_mean": "pressure_mean",
        "cloud_mean": "cloud_mean",
        "dew_point_mean": "dew_point_mean",

        "is_workday_max": "is_workday",
        "is_holiday_max": "is_holiday",
        "is_before_holiday_max": "is_before_holiday",
        "is_after_holiday_max": "is_after_holiday",
        "is_month_start_max": "is_month_start",
        "is_month_end_max": "is_month_end",

        "weather_match_level_mode": "weather_match_level_mode",
    }
    daily = daily.rename(columns=rename_map)

    # 日级滚动特征
    daily = daily.sort_values("date").reset_index(drop=True)
    daily["daily_total_load_lag_1"] = daily["daily_total_load"].shift(1)
    daily["daily_total_load_roll_mean_3"] = daily["daily_total_load"].shift(1).rolling(3, min_periods=1).mean()
    daily["daily_total_load_roll_mean_7"] = daily["daily_total_load"].shift(1).rolling(7, min_periods=1).mean()

    daily["daytime_total_load_lag_1"] = daily["daytime_total_load"].shift(1)
    daily["daytime_total_load_roll_mean_3"] = daily["daytime_total_load"].shift(1).rolling(3, min_periods=1).mean()
    daily["daytime_total_load_roll_mean_7"] = daily["daytime_total_load"].shift(1).rolling(7, min_periods=1).mean()

    # 分位数标签（辅助看日类型）
    q30 = daily["daytime_total_load"].quantile(0.3)
    q70 = daily["daytime_total_load"].quantile(0.7)

    def get_day_type(x):
        if pd.isna(x):
            return "unknown"
        elif x <= q30:
            return "low_day"
        elif x <= q70:
            return "mid_day"
        else:
            return "high_day"

    daily["day_type_by_daytime_load"] = daily["daytime_total_load"].apply(get_day_type)

    return daily


# =========================================================
# 12. 导出分析结果
# =========================================================
def export_analysis_outputs(daily_df):
    log("导出日级分析结果...")

    # 日级长表
    daily_path = OUTPUT_ANALYSIS / f"single_user_daily_profile_{SAFE_USER_NAME}.csv"
    daily_df.to_csv(daily_path, index=False, encoding="utf-8-sig")
    log(f"已导出：{daily_path.name}")

    # 描述统计
    desc_cols = [c for c in daily_df.columns if daily_df[c].dtype != "object" and c != "date"]
    summary = daily_df[desc_cols].describe().T
    summary_path = OUTPUT_ANALYSIS / f"single_user_daily_summary_{SAFE_USER_NAME}.csv"
    summary.to_csv(summary_path, encoding="utf-8-sig")
    log(f"已导出：{summary_path.name}")

    # 日类型数量统计
    daytype_count = daily_df["day_type_by_daytime_load"].value_counts(dropna=False).reset_index()
    daytype_count.columns = ["day_type_by_daytime_load", "count"]
    daytype_path = OUTPUT_ANALYSIS / f"single_user_day_type_count_{SAFE_USER_NAME}.csv"
    daytype_count.to_csv(daytype_path, index=False, encoding="utf-8-sig")
    log(f"已导出：{daytype_path.name}")
 
 # =========================================================
# 13. 主流程
# =========================================================
def main():
    log("=== 开始单用户日级工况分析 ===")
    log(f"目标用户 = {TARGET_USER_NAME}")
    log(f"ANALYZE_START = {ANALYZE_START_TS}")
    log(f"ANALYZE_END   = {ANALYZE_END_TS}")

    user_master_df = load_user_master()
    load_df, user_info = load_single_user_hourly(user_master_df)
    weather_df = load_hourly_weather()

    merged_df = merge_user_weather(load_df, weather_df, user_info)
    daily_df = build_daily_profile(merged_df)

    export_analysis_outputs(daily_df)

    log(f"分析天数: {len(daily_df)}")
    log("=== 单用户日级工况分析完成 ===")


if __name__ == "__main__":
    main()

