# -*- coding: utf-8 -*-
"""
【V2.6 适配版】负荷预测预测脚本 - 适配新目录结构
P0: 并行预测 + P1: 光伏逆向扣减 + P2: 24小时独立模型路由
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
BASE_DIR    = Path(__file__).resolve().parent
INPUT_DIR   = BASE_DIR / "1-1负荷预测输入"
OUTPUT_DIR  = BASE_DIR / "1-2负荷预测输出"

USER_MASTER_PATH = INPUT_DIR / "用户主档案表.xlsx"
WEATHER_DIR      = INPUT_DIR / "2.预测天气"  # PV预测天气
WEATHER_HIST_DIR  = INPUT_DIR / "3.真实天气"  # 历史实际天气
LOAD_DIR         = INPUT_DIR / "1.分时段历史用电信息"

OUTPUT_PROCESSED  = OUTPUT_DIR / "processed"
OUTPUT_MODEL      = OUTPUT_DIR / "model"
OUTPUT_PREDICTION = OUTPUT_DIR / "prediction"

for p in [OUTPUT_PROCESSED, OUTPUT_MODEL, OUTPUT_PREDICTION]:
    p.mkdir(parents=True, exist_ok=True)

# =========================================================
# 2. 日志
# =========================================================
LOG_FILE = OUTPUT_DIR / "02_predict_v2_6_new_log.txt"
def log(msg):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")
with open(LOG_FILE, "w", encoding="utf-8") as f:
    f.write("=== V2.6_Adapted 预测日志 ===\n")

# =========================================================
# 3. 读取运行配置
# =========================================================
CONFIG_PATH = OUTPUT_MODEL / "run_config_v2_6.csv"
if not CONFIG_PATH.exists():
    raise FileNotFoundError("未找到 run_config_v2_6.csv，请先运行 01_train_v2.py")

RUN_CONFIG = pd.read_csv(CONFIG_PATH, encoding="utf-8-sig").iloc[0]
PREDICT_START_TS         = pd.Timestamp(RUN_CONFIG["PREDICT_START"])
PREDICT_END_TS           = pd.Timestamp(RUN_CONFIG["PREDICT_END"])
LOW_LOAD_THRESHOLD       = float(RUN_CONFIG["LOW_LOAD_THRESHOLD"])
LOW_LOAD_PROBA_THRESHOLD = float(RUN_CONFIG["LOW_LOAD_PROBA_THRESHOLD"])
# V2: 预测时提高阈值，确保分类器不把正常负荷错判为低负荷
# 低于此阈值的才走低负荷模型，否则走24小时独立模型
# =========================================================
# 4. 节假日配置
# =========================================================
HOLIDAY_MAP = {
    "2024-01-01": "元旦",
    "2024-02-10": "春节","2024-02-11": "春节","2024-02-12": "春节","2024-02-13": "春节",
    "2024-02-14": "春节","2024-02-15": "春节","2024-02-16": "春节","2024-02-17": "春节",
    "2024-04-04": "清明节","2024-04-05": "清明节","2024-04-06": "清明节",
    "2024-05-01": "劳动节","2024-05-02": "劳动节","2024-05-03": "劳动节","2024-05-04": "劳动节","2024-05-05": "劳动节",
    "2024-06-08": "端午节","2024-06-09": "端午节","2024-06-10": "端午节",
    "2024-09-15": "中秋节","2024-09-16": "中秋节","2024-09-17": "中秋节",
    "2024-10-01": "国庆节","2024-10-02": "国庆节","2024-10-03": "国庆节","2024-10-04": "国庆节",
    "2024-10-05": "国庆节","2024-10-06": "国庆节","2024-10-07": "国庆节",
    "2025-01-01": "元旦",
    "2025-01-28": "春节","2025-01-29": "春节","2025-01-30": "春节","2025-01-31": "春节",
    "2025-02-01": "春节","2025-02-02": "春节","2025-02-03": "春节","2025-02-04": "春节",
    "2025-04-04": "清明节","2025-04-05": "清明节","2025-04-06": "清明节",
    "2025-05-01": "劳动节","2025-05-02": "劳动节","2025-05-03": "劳动节","2025-05-04": "劳动节","2025-05-05": "劳动节",
    "2025-05-31": "端午节","2025-06-01": "端午节","2025-06-02": "端午节",
    "2025-10-01": "国庆节","2025-10-02": "国庆节","2025-10-03": "国庆节","2025-10-04": "国庆节",
    "2025-10-05": "国庆节","2025-10-06": "国庆节","2025-10-07": "国庆节","2025-10-08": "中秋节",
    "2026-01-01": "元旦",
    "2026-02-17": "春节","2026-02-18": "春节","2026-02-19": "春节","2026-02-20": "春节",
    "2026-02-21": "春节","2026-02-22": "春节","2026-02-23": "春节",
    "2026-04-04": "清明节","2026-04-05": "清明节","2026-04-06": "清明节",
    "2026-05-01": "劳动节","2026-05-02": "劳动节","2026-05-03": "劳动节",
    "2026-06-19": "端午节","2026-06-20": "端午节","2026-06-21": "端午节",
    "2026-09-25": "中秋节","2026-09-26": "中秋节","2026-09-27": "中秋节",
    "2026-10-01": "国庆节","2026-10-02": "国庆节","2026-10-03": "国庆节","2026-10-04": "国庆节",
    "2026-10-05": "国庆节","2026-10-06": "国庆节","2026-10-07": "国庆节",
}
ADJUST_WORKDAYS = set([
    "2024-02-04","2024-02-18","2024-04-07","2024-04-28","2024-05-11","2024-09-14","2024-09-29","2024-10-12",
    "2025-01-26","2025-02-08","2025-04-27","2025-09-28","2025-10-11",
    "2026-02-15","2026-02-28","2026-04-26","2026-05-09","2026-09-27","2026-10-10",
])

# =========================================================
# 5. 通用函数
# =========================================================
def normalize_text(x):
    if pd.isna(x): return None
    return str(x).strip().replace("\u3000","").replace(" ","")

def convert_yes_no(x):
    x = normalize_text(x)
    return 1 if x in ["是","有","1","true","True","Y","y"] else 0

def extract_city(s):
    if pd.isna(s): return None
    s = str(s).strip()
    for city in ["福州","泉州","莆田","宁德","厦门","漳州","龙岩","三明","南平"]:
        if city in s: return city
    return s

def estimate_pv_generation(radiation, temp, capacity):
    if pd.isna(radiation) or pd.isna(temp) or pd.isna(capacity): return 0.0
    if radiation <= 0 or capacity <= 0: return 0.0
    temp_coeff = 1 + (-0.004)*(temp-25)
    pv = capacity*1000*0.75*(radiation/1000)*temp_coeff
    return max(0.0, pv)

# =========================================================
# 6. 节假日和时间特征
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
        (df["is_holiday"]==1)|((weekend==1)&(df["is_adjust_workday"]==0)),1,0)
    df["is_month_start"] = df["datetime"].dt.day.isin([1,2,3]).astype(int)
    month_end_days = df["datetime"].dt.days_in_month
    df["is_month_end"] = ((month_end_days - df["datetime"].dt.day).isin([0,1,2])).astype(int)
    holiday_dates = sorted(pd.to_datetime(list(HOLIDAY_MAP.keys())))
    before_set = set([(d-pd.Timedelta(days=1)).normalize() for d in holiday_dates])
    after_set  = set([(d+pd.Timedelta(days=1)).normalize() for d in holiday_dates])
    df["is_before_holiday"] = date_only.isin(before_set).astype(int)
    df["is_after_holiday"]  = date_only.isin(after_set).astype(int)
    return df

def add_time_behavior_features(df):
    df = df.copy()
    df["month"]   = df["datetime"].dt.month
    df["day"]     = df["datetime"].dt.day
    df["hour"]    = df["datetime"].dt.hour
    df["weekday"] = df["datetime"].dt.weekday + 1
    df["is_weekend"] = (df["datetime"].dt.weekday >= 5).astype(int)
    df["is_workday"]  = np.where((df["is_real_restday"]==0)|(df["is_adjust_workday"]==1),1,0)
    df["is_active_hour"] = ((df["hour"]>=8)&(df["hour"]<=22)).astype(int)
    df["is_workhour"]    = ((df["hour"]>=8)&(df["hour"]<=19)).astype(int)
    df["is_daytime_8_19"] = ((df["hour"]>=8)&(df["hour"]<=19)).astype(int)

    def get_bias_segment(h):
        if 8<=h<=10: return "seg_8_10"
        elif 11<=h<=13: return "seg_11_13"
        elif 14<=h<=17: return "seg_14_17"
        elif 18<=h<=19: return "seg_18_19"
        else: return "seg_other"
    df["bias_segment"] = df["hour"].apply(get_bias_segment)
    df["is_morning_ramp"] = ((df["hour"]>=8)&(df["hour"]<=10)).astype(int)
    df["is_lunch_time"]   = ((df["hour"]>=11)&(df["hour"]<=13)).astype(int)
    df["is_evening_peak"] = ((df["hour"]>=18)&(df["hour"]<=22)).astype(int)

    def get_time_segment(h):
        if 0<=h<=6: return "night"
        elif 7<=h<=10: return "morning_start"
        elif 11<=h<=13: return "lunch"
        elif 14<=h<=17: return "afternoon"
        elif 18<=h<=22: return "evening_peak"
        else: return "late_night"
    df["time_segment"] = df["hour"].apply(get_time_segment)
    df["hour_sin"] = np.sin(2*np.pi*df["hour"]/24.0)
    df["hour_cos"] = np.cos(2*np.pi*df["hour"]/24.0)
    weekday0 = df["weekday"] - 1
    df["weekday_sin"] = np.sin(2*np.pi*weekday0/7.0)
    df["weekday_cos"] = np.cos(2*np.pi*weekday0/7.0)
    return df

# =========================================================
# 7. 读取PV每日预测气象 (用于预测日天气)
# =========================================================
def load_pv_daily_weather():
    """从 fujian_pv_daily.xlsx 读取预测日的小时气象数据（已验证版）"""
    pv_files = glob.glob(str(WEATHER_DIR / "fujian_pv_daily*.xlsx"))
    if not pv_files:
        log("[警告] 未找到 PV daily 气象文件")
        return pd.DataFrame()

    # 构造多种日期格式以确保匹配
    pred_m = PREDICT_START_TS.month
    pred_d = PREDICT_START_TS.day
    date_patterns = [f"{pred_m}月{pred_d}日"]  # 6月27日
    all_rows = []

    for fp in pv_files:
        try:
            xls = pd.ExcelFile(fp)
        except Exception:
            continue

        for sheet_name in xls.sheet_names:
            # 用多种日期格式匹配
            if not any(p in sheet_name for p in date_patterns):
                continue

            log(f"  读取预测天气: {Path(fp).name} / {sheet_name}")
            try:
                raw = pd.read_excel(fp, sheet_name=sheet_name, header=None)
            except Exception as e:
                log(f"  [错误] {e}")
                continue

            if raw.empty:
                continue

            i = 0
            while i < len(raw):
                if pd.isna(raw.iloc[i, 0]) or i+4 >= len(raw):
                    i += 1
                    continue

                header = str(raw.iloc[i, 0])
                if "|" not in header or "kw" not in header.lower():
                    i += 1
                    continue

                parts = header.split("|")
                user_name_raw = parts[0].strip() if len(parts) > 0 else ""
                city_raw = parts[1].strip() if len(parts) > 1 else ""
                city = normalize_text(city_raw)

                temp_row = i + 2
                rad_row  = i + 3

                for h in range(1, 25):
                    if h >= raw.shape[1]:
                        break

                    try:
                        tv, rv = raw.iloc[temp_row, h], raw.iloc[rad_row, h]
                    except:
                        continue

                    stv = str(tv).strip()
                    srv = str(rv).strip()

                    temp_val = np.nan
                    if stv not in ("-", "nan", ""):
                        try:
                            temp_val = float(tv)
                        except:
                            pass

                    rad_val = np.nan
                    if srv not in ("-", "nan", ""):
                        try:
                            rad_val = float(rv)
                        except:
                            pass

                    dt = PREDICT_START_TS.normalize() + pd.Timedelta(hours=h)  # h=1→01:00, h=24→次日00:00

                    all_rows.append({
                        "user_name_raw": user_name_raw,
                        "city": city,
                        "datetime": dt,
                        "temperature": temp_val,
                        "shortwave_radiation": rad_val,
                    })

                i += 5

    if not all_rows:
        log("[警告] PV daily中未找到预测日天气数据")
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    df["datetime"] = pd.to_datetime(df["datetime"])
    log(f"PV daily 预测天气: {len(df)} 条, 有效温度 {df['temperature'].notna().sum()} 条, 城市 {df['city'].nunique()} 个")
    return df

# =========================================================
# 8. 读取历史天气 (用于特征补全)
# =========================================================
def load_historical_weather():
    """读取历史天气文件用于构建特征"""
    weather_files = sorted(glob.glob(str(WEATHER_DIR / "福建四地区历史天气数据_*.xlsx")))
    if not weather_files:
        return pd.DataFrame()

    SHEET_CITY_MAP = {"宁德":"宁德","莆田":"莆田","福州":"福州","泉州":"泉州"}
    all_rows = []

    for fp in weather_files:
        try:
            xls = pd.ExcelFile(fp)
        except: continue

        for sheet_name in xls.sheet_names:
            city = None
            for k,v in SHEET_CITY_MAP.items():
                if k in sheet_name:
                    city = v; break
            if city is None:
                city = extract_city(sheet_name) or sheet_name

            try:
                raw = pd.read_excel(fp, sheet_name=sheet_name, header=None)
            except: continue

            ncols = raw.shape[1]
            for col_idx in range(0, ncols, 3):
                if col_idx >= ncols: break
                header_val = str(raw.iloc[0,col_idx]) if col_idx<ncols and pd.notna(raw.iloc[0,col_idx]) else ""
                date_match = re.search(r"(\d+)月(\d+)日", header_val)
                if not date_match: continue
                month = int(date_match.group(1)); day = int(date_match.group(2))
                year = 2026
                d = pd.Timestamp(year=year, month=month, day=day)
                for h in range(24):
                    col = col_idx + 1 + h
                    dt = d + pd.Timedelta(hours=h)
                    temp = np.nan; rad = np.nan
                    if 1 < len(raw) and col < raw.shape[1]:
                        temp = pd.to_numeric(raw.iloc[1,col], errors="coerce")
                    if 2 < len(raw) and col < raw.shape[1]:
                        rad  = pd.to_numeric(raw.iloc[2,col], errors="coerce")
                    all_rows.append({"city":city,"datetime":dt,"temperature":temp,"shortwave_radiation":rad})

    if not all_rows:
        return pd.DataFrame()
    return pd.DataFrame(all_rows)

# =========================================================
# 9. 读取用户主档案
# =========================================================
def load_user_master():
    df = pd.read_excel(USER_MASTER_PATH)
    df.columns = [str(c).strip() for c in df.columns]
    if "所在区" not in df.columns:
        df["所在区"] = "未知"
    if "用户类型" not in df.columns:
        df["用户类型"] = df.get("用户类型标签","未知")
    if "光伏容量(MW)" not in df.columns:
        df["光伏容量(MW)"] = 0.0

    df["用户名称_norm"]   = df["用户名称"].apply(normalize_text)
    df["是否有光伏_flag"]  = df["是否有光伏"].apply(convert_yes_no)
    df["光伏容量(MW)"]     = pd.to_numeric(df["光伏容量(MW)"], errors="coerce").fillna(0)
    df["用户类型"]         = df["用户类型"].fillna("未知").astype(str)
    return df

# =========================================================
# 10. 构建预测骨架
# =========================================================
def build_predict_skeleton(user_master_df):
    log("构建预测骨架...")
    time_range = pd.date_range(start=PREDICT_START_TS, end=PREDICT_END_TS, freq="h", inclusive="left")

    rows = []
    for _, u in user_master_df.iterrows():
        if pd.isna(u["用户编号"]): continue
        tmp = pd.DataFrame({"datetime": time_range})
        tmp["用户编号"]       = u["用户编号"]
        tmp["用户名称"]       = u["用户名称"]
        tmp["户号"]           = u["用户编号"]
        tmp["所在市"]         = u["所在市"]
        tmp["所在区"]         = u.get("所在区","未知")
        tmp["用户类型"]       = u.get("用户类型","未知")
        tmp["是否有光伏"]      = u["是否有光伏"]
        tmp["是否有光伏_flag"] = u["是否有光伏_flag"]
        tmp["光伏容量(MW)"]    = u["光伏容量(MW)"]
        rows.append(tmp)

    if not rows: raise ValueError("未生成预测骨架")

    df = pd.concat(rows, ignore_index=True)
    df["所在市_norm"] = df["所在市"].apply(normalize_text)
    df["所在区_norm"] = df["所在区"].apply(normalize_text)
    df["day_key"]     = df["datetime"].dt.date
    df = df.dropna(subset=["用户编号","datetime"]).copy()
    log(f"预测骨架: {len(df)} 条记录")
    return df

# =========================================================
# 11. 匹配预测气象
# =========================================================
def merge_predict_weather(predict_df, pv_weather_df):
    """将预测日气象数据匹配到预测骨架"""
    log("匹配预测气象...")

    df = predict_df.copy()
    df["datetime"] = pd.to_datetime(df["datetime"]).dt.floor("h")

    # 补充基础气象列
    for c in ["temperature","shortwave_radiation","rainfall","wind_speed",
              "pressure","humidity","visibility","cloud","dew_point","air_quality"]:
        if c not in df.columns:
            df[c] = np.nan

    if pv_weather_df.empty:
        log("[警告] 无预测天气数据，使用nan填充")
        df["weather_match_level"] = "no_forecast"
    else:
        w = pv_weather_df.copy()
        w["datetime"] = pd.to_datetime(w["datetime"]).dt.floor("h")

        # 按城市匹配
        df["city_norm"] = df["所在市"].apply(extract_city)
        for idx, row in df.iterrows():
            city = row.get("city_norm", "")
            dt   = row["datetime"]
            match = w[(w["city"]==city) & (w["datetime"]==dt)]
            if not match.empty:
                df.at[idx, "temperature"]         = match["temperature"].iloc[0]
                df.at[idx, "shortwave_radiation"] = match["shortwave_radiation"].iloc[0]
                df.at[idx, "weather_match_level"] = "pv_forecast"
            else:
                df.at[idx, "weather_match_level"] = "no_match"

    # 补节假日和时间特征
    df = add_holiday_features(df)
    df = add_time_behavior_features(df)

    # 补派生气象特征
    df["cooling_degree"] = np.maximum(df.get("temperature",25).fillna(25) - 24, 0)
    df["heating_degree"] = np.maximum(18 - df.get("temperature",25).fillna(25), 0)

    # 天气完整标记: 放宽限制，有城市匹配即可预测（夜间无辐射但lag特征仍然有效）
    df["weather_day_complete"] = df["weather_match_level"].isin(["pv_forecast", "city_match"])

    # 字符列清洗
    for c in ["用户类型","所在市","所在区","weather","time_segment",
              "wind_direction","holiday_name","bias_segment"]:
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip()

    if "weather" not in df.columns:
        df["weather"] = "未知"
    if "wind_direction" not in df.columns:
        df["wind_direction"] = "未知"

    log(f"匹配后有效温度记录: {df['temperature'].notna().sum()}/{len(df)}")
    return df

# =========================================================
# 12. 构建预测特征 (历史lag)
# =========================================================
def build_predict_features(predict_df, history_df):
    """并行模式：从历史数据一次性构造lag特征"""
    log("构造预测lag特征...")
    pred = predict_df.copy()
    pred["datetime"] = pd.to_datetime(pred["datetime"])
    pred = pred.sort_values(["用户编号","datetime"]).reset_index(drop=True)

    hist = history_df.copy()
    hist["datetime"] = pd.to_datetime(hist["datetime"])
    hist = hist.dropna(subset=["datetime","用户编号"]).copy()
    hist = hist.sort_values(["用户编号","datetime"]).reset_index(drop=True)

    # 历史负荷：优先使用total_load（与训练lag一致），否则用原始load
    if "total_load" in hist.columns:
        hist["load_for_lag"] = hist["total_load"]
        log("  使用 total_load 构建lag特征（与训练一致）")
    elif "load" in hist.columns:
        hist["load_for_lag"] = hist["load"]
    else:
        hist["load_for_lag"] = 0

    result_rows = []
    # 预初始化lag列（确保列存在，防止pd赋值静默丢失）
    lag_cols = ["load_lag_24","load_lag_48","load_lag_168",
                "load_same_hour_mean_3d","load_same_hour_mean_7d",
                "load_same_weekday_hour_mean_4","load_same_weekday_hour_mean_8",
                "workday_same_hour_mean_5","restday_same_hour_mean_5",
                "load_roll_mean_24","load_roll_std_24","load_roll_mean_168",
                "recent_workhour_mean_3d","recent_workhour_mean_7d"]
    for c in lag_cols:
        if c not in pred.columns:
            pred[c] = np.nan

    for uid in pred["用户编号"].unique():
        if pd.isna(uid): continue
        user_hist = hist[hist["用户编号"]==uid].sort_values("datetime").reset_index(drop=True)
        user_pred = pred[pred["用户编号"]==uid].sort_values("datetime").reset_index(drop=True)

        if user_hist.empty:
            for c in ["load_lag_24","load_lag_48","load_lag_168",
                      "load_same_hour_mean_3d","load_same_hour_mean_7d",
                      "load_same_weekday_hour_mean_4","load_same_weekday_hour_mean_8",
                      "workday_same_hour_mean_5","restday_same_hour_mean_5",
                      "load_roll_mean_24","load_roll_std_24","load_roll_mean_168",
                      "recent_workhour_mean_3d","recent_workhour_mean_7d"]:
                user_pred[c] = np.nan
            result_rows.append(user_pred)
            continue

        hist_dt_map = dict(zip(user_hist["datetime"], user_hist["load_for_lag"]))
        hist_dts_arr = user_hist["datetime"].values
        hist_vals_arr = user_hist["load_for_lag"].values

        # 预计算：历史末尾最近N条->用于lag（历史截止到6月22，预测7月2有10天gap）
        hist_tail_vals = hist_vals_arr  # 全部历史
        hist_tail_dts  = hist_dts_arr

        for idx, row in user_pred.iterrows():
            ct = row["datetime"]

            # lag特征: 全部用历史末尾近似（因预测日远超历史范围）
            def get_lag_tail(hours_back):
                offset = max(1, hours_back)
                idx_back = min(offset, len(hist_tail_vals))
                if idx_back > 0:
                    return float(hist_tail_vals[-idx_back])
                return np.nan

            row["load_lag_24"]  = get_lag_tail(24)
            row["load_lag_48"]  = get_lag_tail(48)
            row["load_lag_168"] = get_lag_tail(168)

            # 滚动统计: 用历史末尾
            row["load_roll_mean_24"]  = np.mean(hist_tail_vals[-24:]) if len(hist_tail_vals)>=1 else np.nan
            row["load_roll_std_24"]   = np.std(hist_tail_vals[-24:]) if len(hist_tail_vals)>=2 else 0.0
            row["load_roll_mean_168"] = np.mean(hist_tail_vals[-168:]) if len(hist_tail_vals)>=1 else np.nan

            ch = ct.hour
            # 同小时: 从全部历史中取
            same_h_mask = pd.to_datetime(hist_tail_dts).hour == ch
            sh_vals = hist_tail_vals[same_h_mask]
            row["load_same_hour_mean_3d"] = np.mean(sh_vals[-3:]) if len(sh_vals)>=1 else np.nan
            row["load_same_hour_mean_7d"] = np.mean(sh_vals[-7:]) if len(sh_vals)>=1 else np.nan

            # 同星期几同小时
            cw = ct.weekday()
            swh_mask = (pd.to_datetime(hist_tail_dts).weekday==cw) & same_h_mask
            swh_vals = hist_tail_vals[swh_mask]
            row["load_same_weekday_hour_mean_4"] = np.mean(swh_vals[-4:]) if len(swh_vals)>=1 else np.nan
            row["load_same_weekday_hour_mean_8"] = np.mean(swh_vals[-8:]) if len(swh_vals)>=1 else np.nan

            # 工作日/休息日同小时
            iw = row.get("is_workday",1)
            bf_dates = pd.to_datetime(hist_tail_dts)
            bf_wend = (bf_dates.weekday>=5).astype(int)
            dt_mask = (bf_wend==0) if iw==1 else (bf_wend==1)
            shdt_mask = same_h_mask & dt_mask
            dt_vals = hist_tail_vals[shdt_mask]
            m = np.mean(dt_vals[-5:]) if len(dt_vals)>=1 else np.nan
            row["workday_same_hour_mean_5"] = m if iw==1 else np.nan
            row["restday_same_hour_mean_5"] = m if iw==0 else np.nan

            # 工作时段
            wh_mask = (bf_dates.hour>=8) & (bf_dates.hour<=19)
            wh_vals = hist_tail_vals[wh_mask]
            row["recent_workhour_mean_3d"] = np.mean(wh_vals[-36:]) if len(wh_vals)>=1 else np.nan
            row["recent_workhour_mean_7d"] = np.mean(wh_vals[-84:]) if len(wh_vals)>=1 else np.nan

            user_pred.loc[idx] = row

        result_rows.append(user_pred)

    result = pd.concat(result_rows, ignore_index=True)
    has_lag = "load_lag_24" in result.columns
    nn = result["load_lag_24"].notna().sum() if has_lag else 0
    log(f"预测特征完成: {len(result)}条, lag_24={'非空'+str(nn) if has_lag else 'MISSING'}")
    if not has_lag:
        log("  WARNING: lag列完全缺失! 正在调试...")
        # dump first user_pred columns to debug
        if result_rows:
            log(f"  user_pred cols: {result_rows[0].columns.tolist()[-10:]}")
    return result

# =========================================================
# 13. 单步特征准备
# =========================================================
def prepare_single_step_features(step_df, feature_meta):
    df = step_df.copy()
    use_features  = feature_meta["use_features"]
    cat_cols      = feature_meta["cat_cols"]
    num_cols      = feature_meta["num_cols"]
    train_columns = feature_meta["train_columns"]
    num_fill_vals = feature_meta["num_fill_values"]

    for col in cat_cols:
        if col not in df.columns:
            df[col] = "未知"
        df[col] = df[col].fillna("未知").astype(str)

    for col in num_cols:
        if col not in df.columns:
            df[col] = num_fill_vals.get(col,0)
        df[col] = df[col].fillna(num_fill_vals.get(col,0))

    X = df[use_features].copy()
    X = pd.get_dummies(X, columns=cat_cols, dummy_na=False)

    for c in train_columns:
        if c not in X.columns:
            X[c] = 0
    extra = [c for c in X.columns if c not in train_columns]
    if extra:
        X = X.drop(columns=extra)
    X = X[train_columns].copy()
    return X

# =========================================================
# 14. 加载模型
# =========================================================
def load_models():
    log("加载V2.6模型...")
    with open(OUTPUT_MODEL / "low_load_classifier_v2_6.pkl","rb") as f:
        clf = pickle.load(f)
    with open(OUTPUT_MODEL / "low_load_regressor_v2_6.pkl","rb") as f:
        low_reg = pickle.load(f)
    with open(OUTPUT_MODEL / "normal_load_regressors_v2_6_dict.pkl","rb") as f:
        normal_regs = pickle.load(f)
    with open(OUTPUT_MODEL / "feature_meta_classifier_v2_6.pkl","rb") as f:
        clf_meta = pickle.load(f)
    with open(OUTPUT_MODEL / "feature_meta_low_reg_v2_6.pkl","rb") as f:
        low_meta = pickle.load(f)
    with open(OUTPUT_MODEL / "feature_meta_normal_reg_v2_6.pkl","rb") as f:
        normal_meta = pickle.load(f)
    log(f"模型加载完成: {sum(1 for v in normal_regs.values() if v is not None)} 个有效小时模型")
    return clf, low_reg, normal_regs, clf_meta, low_meta, normal_meta

# =========================================================
# 15. V2并行预测
# =========================================================
def parallel_predict(clf_model, low_reg_model, normal_regressors,
                     clf_meta, low_reg_meta, normal_reg_meta, predict_df):
    log("开始V2并行预测...")
    pred = predict_df.copy()
    pred["pred_total_load"]     = np.nan
    pred["final_pred_net_load"] = np.nan
    pred["is_low_load"]         = 0
    pred["proba_low"]           = np.nan

    weather_ok = pred["weather_day_complete"].astype(bool)
    pdf_ok  = pred[weather_ok].copy()
    pdf_skip = pred[~weather_ok].copy()
    log(f"天气完整: {len(pdf_ok)}, 缺失: {len(pdf_skip)}")

    if pdf_ok.empty:
        log("[警告] 无天气完整记录")
        return pred

    # 填充数值特征
    num_cols   = clf_meta["num_cols"]
    num_fills  = clf_meta["num_fill_values"]
    for col in num_cols:
        if col in pdf_ok.columns:
            pdf_ok[col] = pdf_ok[col].fillna(num_fills.get(col,0))

    # 阶段1: 低负荷分类
    log("阶段1: 低负荷状态判定...")
    X_pred = prepare_single_step_features(pdf_ok, clf_meta)
    if hasattr(clf_model,"predict_proba"):
        proba = clf_model.predict_proba(X_pred)[:,1]
        is_low = (proba >= LOW_LOAD_PROBA_THRESHOLD).astype(int)
        pdf_ok["proba_low"] = proba
    else:
        is_low = clf_model.predict(X_pred)
        pdf_ok["proba_low"] = np.nan
    pdf_ok["is_low_load"] = is_low
    log(f"判定低负荷: {is_low.sum()}/{len(is_low)}")

    # 阶段2: 低负荷回归 (仅白天小时走分类器，夜间强制用24h独立模型)
    # 夜间小时(19-6)温度/辐射全NaN，分类器会误判为低负荷，因此强制路由到小时模型
    night_hours = [0,1,2,3,4,5,6,19,20,21,22,23]  # datetime hour
    pdf_ok["is_low_load"] = is_low
    # 夜间覆盖：强制为正常负荷(走小时模型)
    night_mask = pdf_ok["hour"].isin(night_hours)
    pdf_ok.loc[night_mask, "is_low_load"] = 0
    log(f"夜间强制路由: {night_mask.sum()}条 → 24h独立模型")
    log(f"低负荷判定(仅白天): {pdf_ok[~night_mask]['is_low_load'].sum()}/{len(pdf_ok[~night_mask])}")

    pdf_ok["is_low_load"] = is_low
    mask_low = pdf_ok["is_low_load"]==1
    if mask_low.any() and low_reg_model is not None:
        log(f"低负荷回归 ({mask_low.sum()}条)...")
        X_low = prepare_single_step_features(pdf_ok[mask_low], low_reg_meta)
        pred_low = np.clip(low_reg_model.predict(X_low), 0, None)
        pdf_ok.loc[mask_low,"pred_total_load"] = pred_low

    # 阶段3: 24小时独立回归 (dt_hour: 0=24:00, 1=1:00, ..., 23=23:00)
    log("阶段3: 24小时独立回归路由...")
    for h in range(0, 24):
        hm = (pdf_ok["hour"]==h) & (pdf_ok["is_low_load"]==0)
        if not hm.any(): continue
        model = normal_regressors.get(f"hour_{h}")
        if model is None:
            dh = 24 if h==0 else h
            log(f"  Hour{dh}:00 (dt={h}) 无模型，跳过 {hm.sum()} 条")
            continue
        X_h = prepare_single_step_features(pdf_ok[hm], clf_meta)
        pred_h = np.clip(model.predict(X_h), 0, None)
        pdf_ok.loc[hm,"pred_total_load"] = pred_h

    # 合并回主表
    for c in ["pred_total_load","is_low_load","proba_low"]:
        if c in pdf_ok.columns:
            pred.loc[weather_ok, c] = pdf_ok[c].values

    # P0: 光伏逆向扣减
    log("光伏逆向扣减...")
    pred["pred_pv"] = 0.0
    pred["final_pred_net_load"] = pred["pred_total_load"]
    mask_pv = pred["是否有光伏_flag"]==1
    if mask_pv.any():
        pred.loc[mask_pv,"pred_pv"] = pred[mask_pv].apply(
            lambda r: estimate_pv_generation(
                r["shortwave_radiation"], r["temperature"], r["光伏容量(MW)"]), axis=1)
        pred.loc[mask_pv,"final_pred_net_load"] = (
            pred.loc[mask_pv,"pred_total_load"] - pred.loc[mask_pv,"pred_pv"])
    pred["final_pred_net_load"] = pred["final_pred_net_load"].clip(lower=0)

    pred["predict_status"] = np.where(weather_ok, "已预测", "天气缺失未预测")
    log(f"预测完成! 有效:{weather_ok.sum()}, 天气缺失:{(~weather_ok).sum()}")
    return pred

# =========================================================
# 16. 导出结果
# =========================================================
def build_output_sheet(one_user_df, account_value):
    pred_start = PREDICT_START_TS.normalize()
    pred_end   = PREDICT_END_TS.normalize()
    day_range_end = pred_end if PREDICT_END_TS!=pred_end else pred_end-pd.Timedelta(days=1)
    day_range = pd.date_range(start=pred_start, end=day_range_end, freq="D")

    day_rows = []
    for day in day_range:
        row = {"电量年月日": day.strftime("%Y%m%d"), "户号": account_value}
        day_slice = one_user_df.copy()
        day_slice["base_date"] = np.where(
            day_slice["datetime"].dt.hour==0,
            (day_slice["datetime"]-pd.Timedelta(days=1)).dt.normalize(),
            day_slice["datetime"].dt.normalize())
        day_slice["base_date"] = pd.to_datetime(day_slice["base_date"])
        one_day = day_slice[day_slice["base_date"]==day]

        all_empty = True; total_val = 0.0
        for h in range(1,25):
            target_dt = day+pd.Timedelta(days=1) if h==24 else day+pd.Timedelta(hours=h)
            hit = one_day[one_day["datetime"]==target_dt]
            if not (PREDICT_START_TS<=target_dt<PREDICT_END_TS):
                v = np.nan
            elif hit.empty or pd.isna(hit["final_pred_net_load"].iloc[0]):
                v = np.nan
            else:
                v = float(hit["final_pred_net_load"].iloc[0]) / 1000.0  # kW → MWh
                all_empty = False; total_val += v
            row[f"{h}:00"] = v
        row["合计"] = np.nan if all_empty else total_val
        day_rows.append(row)

    cols = ["电量年月日","户号"]+[f"{h}:00" for h in range(1,25)]+["合计"]
    return pd.DataFrame(day_rows)[cols]

def export_prediction_excels(final_pred):
    log("导出预测Excel...")
    grouped = final_pred.dropna(subset=["用户编号"]).groupby(["用户编号","用户名称"])
    sheet_name = f"{str(PREDICT_START_TS.year)[2:]}.{PREDICT_START_TS.month}"

    for (uid, uname), g in grouped:
        g = g.copy().sort_values("datetime")
        acc = str(g["户号"].dropna().iloc[0]) if g["户号"].notna().any() else str(uname)
        out_sheet = build_output_sheet(g, acc)
        safe_name = str(uname).replace("/","_").replace("\\","_")
        out_path = OUTPUT_PREDICTION / f"{safe_name}_v2_6.xlsx"
        with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
            out_sheet.to_excel(writer, sheet_name=sheet_name[:31], index=False)
        log(f"已导出: {out_path.name}")

# =========================================================
# 17. 汇总表导出（18用户 × 24时段）
# =========================================================
def export_summary_wide_table(final_pred, user_master_df):
    """生成类似6月27-29日负荷预测表格式的汇总Excel"""
    log("生成24时段汇总表...")

    pred_date = PREDICT_START_TS.normalize()
    # 日期标签: "7月2日_周四"
    weekday_names = ["周一","周二","周三","周四","周五","周六","周日"]
    weekday_cn = weekday_names[pred_date.weekday()]
    date_label = pred_date.strftime(f"%#m月%#d日_{weekday_cn}")  # Windows

    # 天气描述
    weather_desc = f"天气: 7月2日预测温度/辐照(来自PVdaily)"

    # 构建汇总sheet数据
    user_data = []
    for _, u in user_master_df.iterrows():
        uid = u["用户编号"]
        uname = u["用户名称"]
        city = u["所在市"]
        utype = u.get("用户类型","未知")
        has_pv = "是" if u["是否有光伏_flag"] == 1 else "否"

        user_pred = final_pred[final_pred["用户编号"]==uid].sort_values("datetime")
        daily_mwh = user_pred["final_pred_net_load"].sum() / 1000.0 if user_pred["final_pred_net_load"].notna().any() else 0

        user_data.append({
            "用户编号": uid,
            "用户名称": uname,
            "所在市": city,
            "用户类型": utype,
            "是否有光伏": has_pv,
            f"{date_label}\n预测(MWh)": round(daily_mwh, 3),
        })

    summary_df = pd.DataFrame(user_data)

    # 构建24时段明细sheet
    detail_rows = []
    for idx, u in user_master_df.iterrows():
        uid = u["用户编号"]
        uname = u["用户名称"]
        utype = u.get("用户类型","未知")
        has_pv = "是" if u["是否有光伏_flag"] == 1 else "否"

        user_pred = final_pred[final_pred["用户编号"]==uid].sort_values("datetime")
        user_pred = user_pred.copy()
        user_pred["base_date"] = np.where(
            user_pred["datetime"].dt.hour == 0,
            (user_pred["datetime"] - pd.Timedelta(days=1)).dt.normalize(),
            user_pred["datetime"].dt.normalize()
        )
        user_pred["base_date"] = pd.to_datetime(user_pred["base_date"])
        one_day = user_pred[user_pred["base_date"] == pred_date].copy()

        row = {
            "序号": idx + 1,
            "用户编号": uid,
            "用户名称": uname,
            "用户类型": utype,
            "是否有光伏": has_pv,
        }

        daily_total = 0.0
        all_empty = True
        for h in range(1, 25):
            target_dt = pred_date + pd.Timedelta(days=1) if h == 24 else pred_date + pd.Timedelta(hours=h)
            hit = one_day[one_day["datetime"] == target_dt]
            if hit.empty or pd.isna(hit["final_pred_net_load"].iloc[0]):
                v = np.nan
            else:
                v = float(hit["final_pred_net_load"].iloc[0]) / 1000.0  # kW → MWh
                daily_total += v
                all_empty = False
            row[f"{h}:00"] = round(v, 4) if pd.notna(v) else v

        row["合计"] = round(daily_total, 4) if not all_empty else np.nan
        detail_rows.append(row)

    detail_cols = ["序号","用户编号","用户名称","用户类型","是否有光伏"] + [f"{h}:00" for h in range(1,25)] + ["合计"]
    detail_df = pd.DataFrame(detail_rows)[detail_cols]

    # 添加"总计"行
    total_row = {"序号": "", "用户编号": "", "用户名称": "总计", "用户类型": "", "是否有光伏": ""}
    for h in range(1, 25):
        total_row[f"{h}:00"] = round(detail_df[f"{h}:00"].sum(), 3)
    total_row["合计"] = round(detail_df["合计"].sum(), 3)
    detail_df = pd.concat([detail_df, pd.DataFrame([total_row])], ignore_index=True)

    # 光伏预测sheet
    pv_users = user_master_df[user_master_df["是否有光伏_flag"]==1]
    pv_rows = []
    for _, u in pv_users.iterrows():
        uid = u["用户编号"]
        uname = u["用户名称"]
        user_pred = final_pred[final_pred["用户编号"]==uid].sort_values("datetime")
        row = {"用户名称": uname, "光伏容量(MW)": u.get("光伏容量(MW)", 0)}
        daily_pv = 0.0
        for h in range(1, 25):
            target_dt = pred_date + pd.Timedelta(days=1) if h == 24 else pred_date + pd.Timedelta(hours=h)
            hit = user_pred[user_pred["datetime"] == target_dt]
            if not hit.empty and "pred_pv" in hit.columns:
                pv_val = float(hit["pred_pv"].iloc[0]) if pd.notna(hit["pred_pv"].iloc[0]) else 0
            else:
                pv_val = 0
            row[f"{h}:00"] = round(pv_val, 3)
            daily_pv += pv_val
        row["日发电量(MWh)"] = round(daily_pv / 1000, 3)
        pv_rows.append(row)

    pv_cols = ["用户名称","光伏容量(MW)"] + [f"{h}:00" for h in range(1,25)] + ["日发电量(MWh)"]
    pv_df = pd.DataFrame(pv_rows)[pv_cols] if pv_rows else pd.DataFrame()

    # 写入Excel
    summary_path = OUTPUT_PREDICTION / f"7月2日_负荷预测汇总表_V2.6.xlsx"
    with pd.ExcelWriter(summary_path, engine="openpyxl") as writer:
        # 预测汇总sheet
        summary_df.to_excel(writer, sheet_name="预测汇总", index=False)

        # 24时段明细sheet
        detail_df.to_excel(writer, sheet_name=f"{pred_date.strftime('%#m月%#d日')}_{weekday_cn}"[:31], index=False)

        # PV sheet
        if not pv_df.empty:
            pv_df.to_excel(writer, sheet_name="光伏发电量预测", index=False)

    log(f"汇总表已导出: {summary_path.name}")
    return summary_path

# =========================================================
# 18. 主流程
# =========================================================
def main():
    log("=== 开始 V2.6_Adapted 预测 ===")
    log(f"PREDICT_START = {PREDICT_START_TS}")
    log(f"PREDICT_END   = {PREDICT_END_TS}")

    # 加载模型
    clf, low_reg, normal_regs, clf_meta, low_meta, normal_meta = load_models()

    # 加载历史负荷
    hist_path = OUTPUT_PROCESSED / "history_load_for_predict_v2_6.csv"
    if not hist_path.exists():
        raise FileNotFoundError(f"未找到历史负荷: {hist_path}")
    history_df = pd.read_csv(hist_path, encoding="utf-8-sig")
    history_df["datetime"] = pd.to_datetime(history_df["datetime"], errors="coerce")
    log(f"历史负荷: {len(history_df)} 条")

    # 加载用户和天气
    user_master_df = load_user_master()
    pv_weather_df  = load_pv_daily_weather()

    # 构建骨架 + 匹配天气
    skeleton = build_predict_skeleton(user_master_df)
    pred_base = merge_predict_weather(skeleton, pv_weather_df)

    # 构造lag特征
    pred_feat = build_predict_features_fixed2(pred_base, history_df)

    # 并行预测
    final_pred = parallel_predict(clf, low_reg, normal_regs,
                                  clf_meta, low_meta, normal_meta, pred_feat)

    # 保存
    final_pred.to_csv(OUTPUT_PREDICTION / "predict_long_v2_6.csv", index=False, encoding="utf-8-sig")
    export_prediction_excels(final_pred)

    # 导出24时段汇总表
    export_summary_wide_table(final_pred, user_master_df)

    log("=== V2.6_Adapted 预测完成 ===")

def build_predict_features_fixed(predict_df, history_df):
    """按每个目标时点重算lag，避免整天复用同一组历史尾值。"""
    log("重建预测特征（fixed）...")
    pred = predict_df.copy()
    pred["datetime"] = pd.to_datetime(pred["datetime"])
    pred = pred.sort_values(["鐢ㄦ埛缂栧彿", "datetime"]).reset_index(drop=True)

    hist = history_df.copy()
    hist["datetime"] = pd.to_datetime(hist["datetime"])
    hist = hist.dropna(subset=["datetime", "鐢ㄦ埛缂栧彿"]).copy()
    hist = hist.sort_values(["鐢ㄦ埛缂栧彿", "datetime"]).reset_index(drop=True)

    if "total_load" in hist.columns:
        hist["load_for_lag"] = hist["total_load"]
    elif "load" in hist.columns:
        hist["load_for_lag"] = hist["load"]
    else:
        hist["load_for_lag"] = 0

    lag_cols = [
        "load_lag_24", "load_lag_48", "load_lag_168",
        "load_same_hour_mean_3d", "load_same_hour_mean_7d",
        "load_same_weekday_hour_mean_4", "load_same_weekday_hour_mean_8",
        "workday_same_hour_mean_5", "restday_same_hour_mean_5",
        "load_roll_mean_24", "load_roll_std_24", "load_roll_mean_168",
        "recent_workhour_mean_3d", "recent_workhour_mean_7d",
    ]
    for c in lag_cols:
        if c not in pred.columns:
            pred[c] = np.nan

    rows = []
    for uid in pred["鐢ㄦ埛缂栧彿"].unique():
        if pd.isna(uid):
            continue
        user_hist = hist[hist["鐢ㄦ埛缂栧彿"] == uid].sort_values("datetime").reset_index(drop=True)
        user_pred = pred[pred["鐢ㄦ埛缂栧彿"] == uid].sort_values("datetime").reset_index(drop=True)
        if user_hist.empty:
            rows.append(user_pred)
            continue

        hist_dt_map = dict(zip(user_hist["datetime"], user_hist["load_for_lag"]))
        for idx, row in user_pred.iterrows():
            ct = row["datetime"]
            hist_before = user_hist[user_hist["datetime"] < ct].copy()

            row["load_lag_24"]  = hist_dt_map.get(ct - pd.Timedelta(hours=24), np.nan)
            row["load_lag_48"]  = hist_dt_map.get(ct - pd.Timedelta(hours=48), np.nan)
            row["load_lag_168"] = hist_dt_map.get(ct - pd.Timedelta(hours=168), np.nan)

            tail_24 = hist_before["load_for_lag"].tail(24)
            tail_168 = hist_before["load_for_lag"].tail(168)
            row["load_roll_mean_24"]  = tail_24.mean() if len(tail_24) else np.nan
            row["load_roll_std_24"]   = tail_24.std(ddof=0) if len(tail_24) >= 2 else 0.0
            row["load_roll_mean_168"] = tail_168.mean() if len(tail_168) else np.nan

            ch = ct.hour
            same_h = hist_before[hist_before["datetime"].dt.hour == ch]["load_for_lag"]
            row["load_same_hour_mean_3d"] = same_h.tail(3).mean() if len(same_h) else np.nan
            row["load_same_hour_mean_7d"] = same_h.tail(7).mean() if len(same_h) else np.nan

            cw = ct.weekday()
            same_wh = hist_before[
                (hist_before["datetime"].dt.weekday == cw) &
                (hist_before["datetime"].dt.hour == ch)
            ]["load_for_lag"]
            row["load_same_weekday_hour_mean_4"] = same_wh.tail(4).mean() if len(same_wh) else np.nan
            row["load_same_weekday_hour_mean_8"] = same_wh.tail(8).mean() if len(same_wh) else np.nan

            iw = row.get("is_workday", 1)
            rest_flag = (hist_before["datetime"].dt.weekday >= 5).astype(int)
            daytype_mask = (rest_flag == 0) if iw == 1 else (rest_flag == 1)
            same_daytype_hour = hist_before[daytype_mask & (hist_before["datetime"].dt.hour == ch)]["load_for_lag"]
            mean_daytype = same_daytype_hour.tail(5).mean() if len(same_daytype_hour) else np.nan
            row["workday_same_hour_mean_5"] = mean_daytype if iw == 1 else np.nan
            row["restday_same_hour_mean_5"] = mean_daytype if iw == 0 else np.nan

            wh_vals = hist_before[
                (hist_before["datetime"].dt.hour >= 8) &
                (hist_before["datetime"].dt.hour <= 19)
            ]["load_for_lag"]
            row["recent_workhour_mean_3d"] = wh_vals.tail(36).mean() if len(wh_vals) else np.nan
            row["recent_workhour_mean_7d"] = wh_vals.tail(84).mean() if len(wh_vals) else np.nan

            user_pred.loc[idx] = row

        rows.append(user_pred)

    result = pd.concat(rows, ignore_index=True)
    log(f"棰勬祴鐗瑰緛瀹屾垚(fixed): {len(result)}鏉?")
    return result
def build_predict_features_fixed2(predict_df, history_df):
    """Use dynamic column detection so lag features stay aligned with the actual data schema."""
    pred = predict_df.copy()
    pred["datetime"] = pd.to_datetime(pred["datetime"])

    hist = history_df.copy()
    hist["datetime"] = pd.to_datetime(hist["datetime"])
    hist = hist.dropna(subset=["datetime"]).copy()

    def find_uid_col(df):
        skip = {
            "datetime", "date", "load", "total_load", "actual_load", "pred_total_load",
            "final_pred_net_load", "pred_pv", "hour", "month", "day", "weekday"
        }
        for c in df.columns:
            if c not in skip and not str(c).startswith("Unnamed"):
                return c
        raise KeyError("uid column not found")

    uid_col = find_uid_col(hist)
    if uid_col not in pred.columns:
        uid_col = find_uid_col(pred)

    hist = hist.dropna(subset=[uid_col]).copy()
    pred = pred.dropna(subset=[uid_col]).copy()
    hist = hist.sort_values([uid_col, "datetime"]).reset_index(drop=True)
    pred = pred.sort_values([uid_col, "datetime"]).reset_index(drop=True)

    if "total_load" in hist.columns:
        hist["load_for_lag"] = hist["total_load"]
    elif "load" in hist.columns:
        hist["load_for_lag"] = hist["load"]
    else:
        hist["load_for_lag"] = 0.0

    lag_cols = [
        "load_lag_24", "load_lag_48", "load_lag_168",
        "load_same_hour_mean_3d", "load_same_hour_mean_7d",
        "load_same_weekday_hour_mean_4", "load_same_weekday_hour_mean_8",
        "workday_same_hour_mean_5", "restday_same_hour_mean_5",
        "load_roll_mean_24", "load_roll_std_24", "load_roll_mean_168",
        "recent_workhour_mean_3d", "recent_workhour_mean_7d",
    ]
    for c in lag_cols:
        if c not in pred.columns:
            pred[c] = np.nan

    out_parts = []
    for uid, user_pred in pred.groupby(uid_col, sort=False):
        user_pred = user_pred.sort_values("datetime").copy()
        user_hist = hist[hist[uid_col] == uid].sort_values("datetime").copy()
        if user_hist.empty:
            out_parts.append(user_pred)
            continue

        hist_map = dict(zip(user_hist["datetime"], user_hist["load_for_lag"]))

        for idx, row in user_pred.iterrows():
            current_dt = row["datetime"]
            hist_before = user_hist[user_hist["datetime"] < current_dt]

            user_pred.at[idx, "load_lag_24"] = hist_map.get(current_dt - pd.Timedelta(hours=24), np.nan)
            user_pred.at[idx, "load_lag_48"] = hist_map.get(current_dt - pd.Timedelta(hours=48), np.nan)
            user_pred.at[idx, "load_lag_168"] = hist_map.get(current_dt - pd.Timedelta(hours=168), np.nan)

            tail_24 = hist_before["load_for_lag"].tail(24)
            tail_168 = hist_before["load_for_lag"].tail(168)
            user_pred.at[idx, "load_roll_mean_24"] = tail_24.mean() if not tail_24.empty else np.nan
            user_pred.at[idx, "load_roll_std_24"] = tail_24.std(ddof=0) if len(tail_24) >= 2 else 0.0
            user_pred.at[idx, "load_roll_mean_168"] = tail_168.mean() if not tail_168.empty else np.nan

            hour = current_dt.hour
            same_hour = hist_before[hist_before["datetime"].dt.hour == hour]["load_for_lag"]
            user_pred.at[idx, "load_same_hour_mean_3d"] = same_hour.tail(3).mean() if not same_hour.empty else np.nan
            user_pred.at[idx, "load_same_hour_mean_7d"] = same_hour.tail(7).mean() if not same_hour.empty else np.nan

            weekday = current_dt.weekday()
            same_weekday_hour = hist_before[
                (hist_before["datetime"].dt.weekday == weekday) &
                (hist_before["datetime"].dt.hour == hour)
            ]["load_for_lag"]
            user_pred.at[idx, "load_same_weekday_hour_mean_4"] = same_weekday_hour.tail(4).mean() if not same_weekday_hour.empty else np.nan
            user_pred.at[idx, "load_same_weekday_hour_mean_8"] = same_weekday_hour.tail(8).mean() if not same_weekday_hour.empty else np.nan

            is_workday = row.get("is_workday", 1)
            hist_is_workday = (hist_before["datetime"].dt.weekday < 5).astype(int)
            same_daytype_hour = hist_before[
                (hist_is_workday == is_workday) &
                (hist_before["datetime"].dt.hour == hour)
            ]["load_for_lag"]
            mean_daytype = same_daytype_hour.tail(5).mean() if not same_daytype_hour.empty else np.nan
            user_pred.at[idx, "workday_same_hour_mean_5"] = mean_daytype if is_workday == 1 else np.nan
            user_pred.at[idx, "restday_same_hour_mean_5"] = mean_daytype if is_workday == 0 else np.nan

            workhour_vals = hist_before[
                (hist_before["datetime"].dt.hour >= 8) &
                (hist_before["datetime"].dt.hour <= 19)
            ]["load_for_lag"]
            user_pred.at[idx, "recent_workhour_mean_3d"] = workhour_vals.tail(36).mean() if not workhour_vals.empty else np.nan
            user_pred.at[idx, "recent_workhour_mean_7d"] = workhour_vals.tail(84).mean() if not workhour_vals.empty else np.nan

        out_parts.append(user_pred)

    result = pd.concat(out_parts, ignore_index=True)
    log(f"fixed2 lag features built: {len(result)}")
    return result

if __name__ == "__main__":
    main()
