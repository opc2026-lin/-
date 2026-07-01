# -*- coding: utf-8 -*-
"""
【V2.6 适配版】负荷预测训练脚本 - 适配新目录结构
路径: 输入 1-1负荷预测输入/, 输出 1-2负荷预测输出/
核心: P0光伏显式分解 + P1_24小时独立模型 + P2_EarlyStopping
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
    from lightgbm import LGBMRegressor, LGBMClassifier
    MODEL_NAME = "lightgbm"
except Exception:
    from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
    MODEL_NAME = "random_forest"

# =========================================================
# 1. 参数配置
# =========================================================
PREDICT_START = "2026-07-02 01:00:00"   # 7月2日1:00（含24:00=次日0:00）
PREDICT_END   = "2026-07-03 01:00:00"   # 右开 → 预测7月2日完整24时段(1:00~24:00)
TRAIN_MONTHS  = 24
TARGET_LOAD_MODE = "total_load"

LOW_LOAD_THRESHOLD        = 80       # V2: 从50提升到80
LOW_LOAD_PROBA_THRESHOLD  = 0.40

# =========================================================
# 2. 路径配置 (适配新目录)
# =========================================================
BASE_DIR    = Path(__file__).resolve().parent
INPUT_DIR   = BASE_DIR / "1-1负荷预测输入"
OUTPUT_DIR  = BASE_DIR / "1-2负荷预测输出"

USER_MASTER_PATH = INPUT_DIR / "用户主档案表.xlsx"
LOAD_DIR         = INPUT_DIR / "1.分时段历史用电信息"
WEATHER_DIR      = INPUT_DIR / "3.真实天气"  # 历史天气数据

OUTPUT_PROCESSED  = OUTPUT_DIR / "processed"
OUTPUT_MODEL      = OUTPUT_DIR / "model"
OUTPUT_PREDICTION = OUTPUT_DIR / "prediction"

for p in [OUTPUT_PROCESSED, OUTPUT_MODEL, OUTPUT_PREDICTION]:
    p.mkdir(parents=True, exist_ok=True)

# =========================================================
# 3. 日志
# =========================================================
LOG_FILE = OUTPUT_DIR / "01_train_v2_6_new_log.txt"
def log(msg):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")
with open(LOG_FILE, "w", encoding="utf-8") as f:
    f.write("=== V2.6_Adapted 训练日志 ===\n")

# =========================================================
# 4. 时间范围
# =========================================================
PREDICT_START_TS = pd.Timestamp(PREDICT_START)
PREDICT_END_TS   = pd.Timestamp(PREDICT_END)
TRAIN_END        = PREDICT_START_TS
TRAIN_START      = PREDICT_START_TS - pd.DateOffset(months=TRAIN_MONTHS)
VAL_SPLIT_DAYS   = 30
VAL_START        = PREDICT_START_TS - pd.Timedelta(days=VAL_SPLIT_DAYS)

# =========================================================
# 5. 节假日配置
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
# 6. 通用函数
# =========================================================
def normalize_text(x):
    if pd.isna(x): return None
    x = str(x).strip().replace("\u3000","").replace(" ","")
    return x

def convert_yes_no(x):
    x = normalize_text(x)
    return 1 if x in ["是","有","1","true","True","Y","y"] else 0

def extract_city(s):
    """从用户名称或所在市中提取城市名"""
    if pd.isna(s): return None
    s = str(s).strip()
    for city in ["福州","泉州","莆田","宁德","厦门","漳州","龙岩","三明","南平"]:
        if city in s:
            return city
    return s

# =========================================================
# 7. V2核心: 光伏物理估算
# =========================================================
def estimate_pv_generation(radiation, temp, capacity):
    if pd.isna(radiation) or pd.isna(temp) or pd.isna(capacity): return 0.0
    if radiation <= 0 or capacity <= 0: return 0.0
    temp_coeff = 1 + (-0.004) * (temp - 25)
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
        (df["is_holiday"]==1) | ((weekend==1) & (df["is_adjust_workday"]==0)), 1, 0)
    df["is_month_start"] = df["datetime"].dt.day.isin([1,2,3]).astype(int)
    month_end_days = df["datetime"].dt.days_in_month
    df["is_month_end"] = ((month_end_days - df["datetime"].dt.day).isin([0,1,2])).astype(int)
    holiday_dates = sorted(pd.to_datetime(list(HOLIDAY_MAP.keys())))
    before_set = set([(d-pd.Timedelta(days=1)).normalize() for d in holiday_dates])
    after_set  = set([(d+pd.Timedelta(days=1)).normalize() for d in holiday_dates])
    df["is_before_holiday"] = date_only.isin(before_set).astype(int)
    df["is_after_holiday"]  = date_only.isin(after_set).astype(int)
    return df

# =========================================================
# 9. 时间行为特征
# =========================================================
def add_time_behavior_features(df):
    df = df.copy()
    df["month"]   = df["datetime"].dt.month
    df["day"]     = df["datetime"].dt.day
    df["hour"]    = df["datetime"].dt.hour
    df["weekday"] = df["datetime"].dt.weekday + 1
    df["is_weekend"] = (df["datetime"].dt.weekday >= 5).astype(int)
    df["is_workday"] = np.where(
        (df["is_real_restday"]==0) | (df["is_adjust_workday"]==1), 1, 0)
    df["is_active_hour"] = ((df["hour"]>=8) & (df["hour"]<=22)).astype(int)
    df["is_workhour"]    = ((df["hour"]>=8) & (df["hour"]<=19)).astype(int)
    df["is_daytime_8_19"] = ((df["hour"]>=8) & (df["hour"]<=19)).astype(int)

    def get_bias_segment(h):
        if 8<=h<=10: return "seg_8_10"
        elif 11<=h<=13: return "seg_11_13"
        elif 14<=h<=17: return "seg_14_17"
        elif 18<=h<=19: return "seg_18_19"
        else: return "seg_other"
    df["bias_segment"] = df["hour"].apply(get_bias_segment)
    df["is_morning_ramp"] = ((df["hour"]>=8) & (df["hour"]<=10)).astype(int)
    df["is_lunch_time"]   = ((df["hour"]>=11) & (df["hour"]<=13)).astype(int)
    df["is_evening_peak"] = ((df["hour"]>=18) & (df["hour"]<=22)).astype(int)

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
# 10. 样本权重
# =========================================================
def add_recency_weight(df, train_end):
    df = df.copy()
    days_diff = (train_end.normalize() - df["datetime"].dt.normalize()).dt.days
    def get_weight(d):
        if d<=31: return 1.00
        elif d<=92: return 0.42
        elif d<=183: return 0.22
        elif d<=365: return 0.12
        else: return 0.06
    df["recency_weight"] = days_diff.apply(get_weight)
    return df

def add_time_segment_weight(df):
    df = df.copy()
    def get_time_weight(h):
        if 8<=h<=10: return 1.50
        elif 11<=h<=13: return 1.40
        elif 14<=h<=17: return 1.40
        elif 18<=h<=19: return 1.50
        elif 0<=h<=7: return 0.90
        else: return 1.00
    df["time_weight"] = df["hour"].apply(get_time_weight)
    return df

def add_special_day_weight(df):
    df = df.copy()
    df["special_day_weight"] = 1.0
    df.loc[(df["is_month_start"]==1)|(df["is_month_end"]==1),"special_day_weight"] = 1.15
    df.loc[(df["is_before_holiday"]==1)|(df["is_after_holiday"]==1),"special_day_weight"] = 1.20
    df.loc[df["is_holiday"]==1,"special_day_weight"] = 1.30
    return df

# =========================================================
# 11. 读取主档案 (适配版)
# =========================================================
def load_user_master():
    log("读取用户主档案表...")
    df = pd.read_excel(USER_MASTER_PATH)
    df.columns = [str(c).strip() for c in df.columns]

    # 检查必要字段
    required = ["用户编号","用户名称","所在市","是否有光伏"]
    for c in required:
        if c not in df.columns:
            raise ValueError(f"用户主档案表缺少字段: {c}")

    # 补充缺失字段
    if "所在区" not in df.columns:
        df["所在区"] = "未知"
    if "用户类型" not in df.columns:
        df["用户类型"] = df.get("用户类型标签", "未知")
    if "光伏容量(MW)" not in df.columns:
        df["光伏容量(MW)"] = 0.0

    df["用户名称_norm"] = df["用户名称"].apply(normalize_text)
    df["所在市_norm"]   = df["所在市"].apply(normalize_text)
    df["所在区_norm"]   = df["所在区"].apply(normalize_text)
    df["是否有光伏_flag"] = df["是否有光伏"].apply(convert_yes_no)
    df["光伏容量(MW)"]   = pd.to_numeric(df["光伏容量(MW)"], errors="coerce").fillna(0)
    df["用户类型"]       = df["用户类型"].fillna("未知").astype(str)

    log(f"用户主档案读取完成，共 {len(df)} 条，光伏用户 {df['是否有光伏_flag'].sum()} 家")
    return df

# =========================================================
# 12. 读取月度负荷文件 (适配版 - 新格式)
# =========================================================
def load_all_user_loads(user_master_df):
    """读取月度负荷文件: 电量年月日 | 电力用户名称 | 1:00~24:00"""
    log("读取所有月度负荷文件...")
    files = sorted(glob.glob(str(LOAD_DIR / "*.xlsx")))
    if not files:
        raise FileNotFoundError("未找到负荷文件")

    # 建立用户名称 → 用户档案映射
    # 负荷文件中的名称可能带"(套餐用户)"后缀
    user_name_map = {}
    for _, u in user_master_df.iterrows():
        name = normalize_text(u["用户名称"])
        user_name_map[name] = u
        # 也尝试去掉常见后缀
        short_name = name.replace("(套餐用户)","").replace("套餐用户","").strip()
        user_name_map[short_name] = u

    all_rows = []
    user_account_map = {}

    for fp in files:
        fname = Path(fp).name
        log(f"  读取: {fname}")
        try:
            raw = pd.read_excel(fp, sheet_name=0)
            # 查找表头行 (包含"电量年月日"或"电力用户名称")
            header_idx = None
            for i in range(min(len(raw), 5)):
                row_str = " ".join([str(x) for x in raw.iloc[i].tolist() if pd.notna(x)])
                if "电量年月日" in row_str or "电力用户名称" in row_str:
                    header_idx = i
                    break
            if header_idx is not None and header_idx > 0:
                raw.columns = [str(x).strip() for x in raw.iloc[header_idx].tolist()]
                raw = raw.iloc[header_idx+1:].reset_index(drop=True)

            raw.columns = [str(c).strip() for c in raw.columns]
            if "电量年月日" not in raw.columns or "电力用户名称" not in raw.columns:
                log(f"  [跳过] {fname} 未找到电量年月日/电力用户名称列")
                continue

        except Exception as e:
            log(f"  [错误] {fname}: {e}")
            continue

        # 过滤: 只保留有效日期行
        raw["电量年月日"] = raw["电量年月日"].astype(str).str.strip()
        raw = raw[raw["电量年月日"].str.fullmatch(r"\d{8}", na=False)].copy()

        # 识别小时列
        hour_cols = []
        for c in raw.columns:
            if re.fullmatch(r"(1?\d|2[0-4]):00", str(c).strip()):
                hour_cols.append(str(c).strip())
        hour_cols = sorted(hour_cols, key=lambda x: int(x.split(":")[0]))
        if len(hour_cols) != 24:
            log(f"  [警告] {fname} 小时列不完整: {len(hour_cols)}/24")
            # 尝试继续

        # melt成long格式
        id_vars = ["电量年月日","电力用户名称"]
        melt_df = raw.melt(id_vars=id_vars, value_vars=hour_cols,
                           var_name="hour_str", value_name="load")

        melt_df["date"] = pd.to_datetime(melt_df["电量年月日"], format="%Y%m%d", errors="coerce")
        melt_df["load"] = pd.to_numeric(melt_df["load"], errors="coerce")

        def build_datetime(row):
            d = row["date"]
            h = int(str(row["hour_str"]).split(":")[0])
            if pd.isna(d): return pd.NaT
            if h == 24: return d + pd.Timedelta(days=1)
            return d + pd.Timedelta(hours=h)
        melt_df["datetime"] = melt_df.apply(build_datetime, axis=1)

        # 匹配用户
        melt_df["电力用户名称_norm"] = melt_df["电力用户名称"].apply(normalize_text)
        melt_df["用户编号"] = None
        melt_df["用户名称"] = None
        melt_df["所在市"]   = None
        melt_df["所在区"]   = None
        melt_df["用户类型"] = None
        melt_df["是否有光伏"]       = None
        melt_df["是否有光伏_flag"]  = 0
        melt_df["光伏容量(MW)"]     = 0.0

        for name_norm, group in melt_df.groupby("电力用户名称_norm"):
            # 尝试匹配
            matched_u = None
            if name_norm in user_name_map:
                matched_u = user_name_map[name_norm]
            else:
                # 模糊匹配: 去掉"(套餐用户)"等
                for k, v in user_name_map.items():
                    if k and name_norm and (k in name_norm or name_norm in k):
                        matched_u = v
                        break

            if matched_u is None:
                continue  # 跳过"汇总电量""平均电量"等非用户行

            idx = group.index
            melt_df.loc[idx, "用户编号"]    = matched_u["用户编号"]
            melt_df.loc[idx, "用户名称"]    = matched_u["用户名称"]
            melt_df.loc[idx, "所在市"]      = matched_u["所在市"]
            melt_df.loc[idx, "所在区"]      = matched_u.get("所在区","未知")
            melt_df.loc[idx, "用户类型"]    = matched_u.get("用户类型","未知")
            melt_df.loc[idx, "是否有光伏"]   = matched_u["是否有光伏"]
            melt_df.loc[idx, "是否有光伏_flag"] = matched_u["是否有光伏_flag"]
            melt_df.loc[idx, "光伏容量(MW)"]    = matched_u["光伏容量(MW)"]

            # 记录户号映射
            uid = matched_u["用户编号"]
            if uid not in user_account_map and pd.notna(uid):
                user_account_map[uid] = str(uid)

        # 只保留匹配成功的行
        melt_df = melt_df.dropna(subset=["用户编号"]).copy()
        melt_df["户号"] = melt_df["用户编号"].astype(str)

        out_cols = ["用户编号","用户名称","户号","所在市","所在区","用户类型",
                    "是否有光伏","是否有光伏_flag","光伏容量(MW)","date","datetime","load"]
        out_cols = [c for c in out_cols if c in melt_df.columns]
        all_rows.append(melt_df[out_cols])

    if not all_rows:
        raise ValueError("未读取到任何有效负荷数据")

    df = pd.concat(all_rows, ignore_index=True)
    df = df.dropna(subset=["datetime","用户编号"]).sort_values(["用户编号","datetime"]).reset_index(drop=True)
    log(f"训练负荷合并完成，共 {len(df)} 条，{df['用户编号'].nunique()} 个用户")
    return df, user_account_map

# =========================================================
# 13. 读取小时气象 (适配版 - 新格式)
# =========================================================
def load_hourly_weather():
    """读取气象数据: 福建四地区历史天气数据，每sheet一个城市点位"""
    log("读取小时气象数据...")
    weather_files = sorted(glob.glob(str(WEATHER_DIR / "福建四地区历史天气数据_*.xlsx")))
    if not weather_files:
        log("[警告] 未找到历史天气文件")
        return pd.DataFrame()

    # City name mapping from sheet names
    SHEET_CITY_MAP = {
        "宁德": "宁德", "莆田": "莆田", "福州": "福州", "泉州": "泉州",
        "宁德_俊杰": "宁德", "莆田_新兴达": "莆田",
        "福州_超库鲜生": "福州", "泉州_德化圣光": "泉州",
    }

    all_rows = []
    for fp in weather_files:
        log(f"  读取: {Path(fp).name}")
        try:
            xls = pd.ExcelFile(fp)
        except Exception as e:
            log(f"  [错误] {e}")
            continue

        for sheet_name in xls.sheet_names:
            # Determine city
            city = None
            for k, v in SHEET_CITY_MAP.items():
                if k in sheet_name:
                    city = v
                    break
            if city is None:
                city = extract_city(sheet_name) or sheet_name

            try:
                raw = pd.read_excel(fp, sheet_name=sheet_name, header=None)
            except Exception:
                continue

            if raw.empty:
                continue

            # Vertical format: each day = block of rows (7 rows + optional blank)
            # Row i+0: day header (e.g. "6月1日 | ...")
            # Row i+1: 变量 / 1, 2, 3, ..., 24 (hour labels)
            # Row i+2: 温度(°C)    [cols 1-24]
            # Row i+3: 短波辐射(W/m²) [cols 1-24]
            # Row i+4: 云量(%)     [cols 1-24]
            # Row i+5: 湿度(%)     [cols 1-24]
            # Row i+6: 降雨(mm)    [cols 1-24]
            # Row i+7: blank (optional separator)

            row_idx = 0
            nrows = len(raw)
            while row_idx < nrows:
                # Find day header (contains "月" and "日")
                header_val = str(raw.iloc[row_idx, 0]) if pd.notna(raw.iloc[row_idx, 0]) else ""
                date_match = re.search(r"(\d+)月(\d+)日", header_val)
                if not date_match:
                    row_idx += 1
                    continue

                month = int(date_match.group(1))
                day   = int(date_match.group(2))
                year  = 2026  # All data context

                d = pd.Timestamp(year=year, month=month, day=day)

                # Ensure we have enough rows
                if row_idx + 3 >= nrows:
                    row_idx += 1
                    continue

                # Parse temperature (row_idx+2), radiation (row_idx+3),
                # cloud (row_idx+4), humidity (row_idx+5), rainfall (row_idx+6)
                for h in range(24):
                    col = h + 1  # Column 1 = first hour
                    if col >= raw.shape[1]:
                        break
                    dt = d + pd.Timedelta(hours=h)

                    def safe_num(r, c):
                        try:
                            v = raw.iloc[r, c] if r < nrows else np.nan
                            return pd.to_numeric(v, errors="coerce")
                        except:
                            return np.nan

                    temp   = safe_num(row_idx+2, col)
                    rad    = safe_num(row_idx+3, col)
                    cloud  = safe_num(row_idx+4, col) if row_idx+4 < nrows else np.nan
                    humid  = safe_num(row_idx+5, col) if row_idx+5 < nrows else np.nan
                    rain   = safe_num(row_idx+6, col) if row_idx+6 < nrows else np.nan

                    all_rows.append({
                        "所在市_norm": city,
                        "datetime": dt,
                        "temperature": temp,
                        "shortwave_radiation": rad,
                        "humidity": humid,
                        "cloud": cloud,
                        "rainfall": rain,
                        "weather": "未知",
                    })

                # Skip this day block (8 rows)
                row_idx += 8

    if not all_rows:
        log("[警告] 未解析到有效气象数据")
        return pd.DataFrame()

    weather_df = pd.DataFrame(all_rows)
    weather_df = weather_df.dropna(subset=["datetime"]).copy()
    weather_df["datetime"] = pd.to_datetime(weather_df["datetime"]).dt.floor("h")
    weather_df = (weather_df.sort_values("datetime")
                  .drop_duplicates(subset=["所在市_norm","datetime"], keep="last")
                  .reset_index(drop=True))

    # Fill missing weather columns
    for c in ["rainfall","wind_speed","pressure","visibility","cloud","dew_point","air_quality","wind_direction"]:
        if c not in weather_df.columns:
            weather_df[c] = np.nan

    log(f"气象数据解析完成，共 {len(weather_df)} 条，覆盖 {weather_df['所在市_norm'].nunique()} 个城市")
    return weather_df

# =========================================================
# 14. 合并训练负荷与气象
# =========================================================
def merge_load_weather_hourly(load_df, weather_df):
    log("合并训练负荷与小时气象...")

    df = load_df.copy()
    df["datetime"] = pd.to_datetime(df["datetime"]).dt.floor("h")
    df["所在市_norm"] = df["所在市"].apply(normalize_text)

    if weather_df.empty:
        log("[警告] 气象数据为空，使用默认值")
        # Still need to add weather columns
        for c in ["temperature","rainfall","wind_speed","pressure","humidity",
                  "visibility","cloud","dew_point","shortwave_radiation","air_quality",
                  "weather","wind_direction"]:
            if c not in df.columns:
                df[c] = np.nan
        df["weather_match_level"] = "no_weather_data"
        df["day_key"] = df["datetime"].dt.date
        df["weather_day_complete"] = False
        return df

    w = weather_df.copy()
    w["datetime"] = pd.to_datetime(w["datetime"]).dt.floor("h")
    w["所在区_norm"] = "未知"

    # 按城市匹配
    merged = df.merge(w, on=["所在市_norm","datetime"], how="left", suffixes=("","_w"))

    # 补缺失数值列
    numeric_cols = ["temperature","shortwave_radiation","humidity","rainfall",
                    "wind_speed","pressure","visibility","cloud","dew_point","air_quality"]
    for c in numeric_cols:
        if c in merged.columns:
            merged[c] = merged[c].fillna(merged[c].median() if merged[c].notna().any() else 0)

    # Weather match level
    merged["weather_match_level"] = np.where(
        merged.get("temperature_w", pd.Series(np.nan, index=merged.index)).isna(),
        "city_agg", "city_match"
    )
    if "temperature_w" in merged.columns:
        merged = merged.drop(columns=[c for c in merged.columns if c.endswith("_w")])

    # 按天判断天气是否完整
    merged["day_key"] = merged["datetime"].dt.date
    if "temperature" in merged.columns:
        day_ok = (merged.groupby("用户编号")["temperature"]
                  .apply(lambda x: x.notna().all())
                  .reset_index(name="weather_day_complete"))
        merged = merged.merge(day_ok, on="用户编号", how="left")
    else:
        merged["weather_day_complete"] = False

    # 天级别: 若任一小时缺temperature则放弃整天
    # (简化版：检查temperature notna)
    merged = merged[merged["temperature"].notna() | (merged["weather_day_complete"] == True)].copy()

    log(f"训练数据合并完成，共 {len(merged)} 条")
    return merged

# =========================================================
# 15. 特征工程 (V2光伏解耦版)
# =========================================================
def create_train_features(df):
    log("生成V2.6训练特征（光伏解耦版）...")
    df = df.copy()
    df = df.sort_values(["用户编号","datetime"]).reset_index(drop=True)

    # 补缺失气象列
    for c in ["rainfall","wind_speed","pressure","visibility","cloud",
              "dew_point","shortwave_radiation","air_quality"]:
        if c not in df.columns:
            df[c] = np.nan

    df = add_holiday_features(df)
    df = add_time_behavior_features(df)
    df["cooling_degree"] = np.maximum(df["temperature"] - 24, 0)
    df["heating_degree"] = np.maximum(18 - df["temperature"], 0)

    # P0: 光伏物理估算 + 总负荷还原
    log("正在进行光伏净负荷解耦...")
    df["pv_est"] = 0.0
    mask_pv = df["是否有光伏_flag"] == 1
    if mask_pv.any():
        df.loc[mask_pv, "pv_est"] = df[mask_pv].apply(
            lambda r: estimate_pv_generation(
                r["shortwave_radiation"], r["temperature"], r["光伏容量(MW)"]), axis=1)

    df["total_load"]  = df["load"] + df["pv_est"]
    df["actual_load"] = df["load"]
    df["model_target_load"] = df["total_load"]
    df["load"]        = df["total_load"]  # 后续lag基于total_load

    # Lag特征
    df["load_lag_24"]  = df.groupby("用户编号")["load"].shift(24)
    df["load_lag_48"]  = df.groupby("用户编号")["load"].shift(48)
    df["load_lag_168"] = df.groupby("用户编号")["load"].shift(168)

    same_hour_series = df.groupby(["用户编号","hour"])["load"]
    df["load_same_hour_mean_3d"] = (same_hour_series.shift(1)
        .groupby([df["用户编号"],df["hour"]]).rolling(3,min_periods=1).mean()
        .reset_index(level=[0,1],drop=True))
    df["load_same_hour_mean_7d"] = (same_hour_series.shift(1)
        .groupby([df["用户编号"],df["hour"]]).rolling(7,min_periods=1).mean()
        .reset_index(level=[0,1],drop=True))

    df["weekday_hour_key"] = df["weekday"].astype(str)+"_"+df["hour"].astype(str)
    wh_series = df.groupby(["用户编号","weekday_hour_key"])["load"]
    df["load_same_weekday_hour_mean_4"] = (wh_series.shift(1)
        .groupby([df["用户编号"],df["weekday_hour_key"]]).rolling(4,min_periods=1).mean()
        .reset_index(level=[0,1],drop=True))
    df["load_same_weekday_hour_mean_8"] = (wh_series.shift(1)
        .groupby([df["用户编号"],df["weekday_hour_key"]]).rolling(8,min_periods=1).mean()
        .reset_index(level=[0,1],drop=True))

    df["day_type"] = np.where(df["is_workday"]==1,"workday","restday")
    df["daytype_hour_key"] = df["day_type"].astype(str)+"_"+df["hour"].astype(str)
    dt_series = df.groupby(["用户编号","daytype_hour_key"])["load"]
    df["daytype_same_hour_mean_5"] = (dt_series.shift(1)
        .groupby([df["用户编号"],df["daytype_hour_key"]]).rolling(5,min_periods=1).mean()
        .reset_index(level=[0,1],drop=True))
    df["workday_same_hour_mean_5"] = np.where(df["is_workday"]==1, df["daytype_same_hour_mean_5"], np.nan)
    df["restday_same_hour_mean_5"] = np.where(df["is_workday"]==0, df["daytype_same_hour_mean_5"], np.nan)

    df["load_roll_mean_24"] = (df.groupby("用户编号")["load"].shift(1)
        .rolling(24,min_periods=1).mean().reset_index(level=0,drop=True))
    df["load_roll_std_24"]  = (df.groupby("用户编号")["load"].shift(1)
        .rolling(24,min_periods=1).std().reset_index(level=0,drop=True))
    df["load_roll_mean_168"] = (df.groupby("用户编号")["load"].shift(1)
        .rolling(168,min_periods=1).mean().reset_index(level=0,drop=True))

    df["load_workhour_only"] = np.where(df["is_workhour"]==1, df["load"], np.nan)
    df["recent_workhour_mean_3d"] = (df.groupby("用户编号")["load_workhour_only"]
        .shift(1).rolling(72,min_periods=1).mean().reset_index(level=0,drop=True))
    df["recent_workhour_mean_7d"] = (df.groupby("用户编号")["load_workhour_only"]
        .shift(1).rolling(168,min_periods=1).mean().reset_index(level=0,drop=True))

    # 低负荷标签 (基于total_load, 阈值80kW)
    df["is_low_load"] = (df["model_target_load"] < LOW_LOAD_THRESHOLD).astype(int)

    # 字符列清洗
    for c in ["用户类型","所在市","所在区","weather","time_segment",
              "wind_direction","holiday_name","bias_segment"]:
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip()

    log("V2.6训练特征生成完成")
    return df

# =========================================================
# 16. 特征列表
# =========================================================
def get_feature_list(train_df):
    use_features = [
        "用户类型","是否有光伏_flag","所在市","所在区",
        "month","day","hour","weekday",
        "is_weekend","is_workday","is_active_hour","is_workhour","is_daytime_8_19",
        "is_morning_ramp","is_lunch_time","is_evening_peak",
        "time_segment","bias_segment",
        "hour_sin","hour_cos","weekday_sin","weekday_cos",
        "is_holiday","is_adjust_workday","is_real_restday","holiday_name",
        "is_month_start","is_month_end","is_before_holiday","is_after_holiday",
        "weather","wind_direction",
        "temperature","rainfall","wind_speed","pressure","humidity",
        "visibility","cloud","dew_point","shortwave_radiation","air_quality",
        "cooling_degree","heating_degree",
        "load_lag_24","load_lag_48","load_lag_168",
        "load_same_hour_mean_3d","load_same_hour_mean_7d",
        "load_same_weekday_hour_mean_4","load_same_weekday_hour_mean_8",
        "workday_same_hour_mean_5","restday_same_hour_mean_5",
        "load_roll_mean_24","load_roll_std_24","load_roll_mean_168",
        "recent_workhour_mean_3d","recent_workhour_mean_7d",
    ]
    return [c for c in use_features if c in train_df.columns]

# =========================================================
# 17. 训练矩阵准备
# =========================================================
def prepare_matrix(df, target_col, use_features):
    data = df.copy()
    data = data.dropna(subset=[target_col]).copy()
    lag_cols = [c for c in ["load_lag_24","load_lag_48","load_lag_168"] if c in data.columns]
    if lag_cols:
        data = data.dropna(subset=lag_cols)
    if data.empty:
        return None,None,None,None,None

    cat_cols = [c for c in ["用户类型","所在市","所在区","weather","time_segment",
                             "wind_direction","holiday_name","bias_segment"] if c in use_features]
    num_cols = [c for c in use_features if c not in cat_cols]

    for col in cat_cols:
        data[col] = data[col].fillna("未知").astype(str)
    for col in num_cols:
        med = data[col].median() if col in data.columns else 0
        data[col] = data[col].fillna(med)

    X = data[use_features].copy()
    y = data[target_col].copy()
    w = data["sample_weight"].copy() if "sample_weight" in data.columns else None
    X = pd.get_dummies(X, columns=cat_cols, dummy_na=False)

    meta = {
        "use_features": use_features,
        "cat_cols": cat_cols,
        "num_cols": num_cols,
        "train_columns": X.columns.tolist(),
        "num_fill_values": {c: data[c].median() if c in data.columns else 0 for c in num_cols},
    }
    return data, X, y, w, meta

# =========================================================
# 18. 导出函数
# =========================================================
def export_feature_importance(model, X_train, file_name):
    if hasattr(model, "feature_importances_"):
        fi = pd.DataFrame({"feature":X_train.columns,"importance":model.feature_importances_}
                         ).sort_values("importance", ascending=False)
        fi.to_csv(OUTPUT_PREDICTION / file_name, index=False, encoding="utf-8-sig")

def export_train_metrics_classifier(model, X_train, y_train, file_name):
    pred = model.predict(X_train)
    acc = accuracy_score(y_train, pred)
    f1  = f1_score(y_train, pred)
    pd.DataFrame([{"metric":"accuracy","value":acc},{"metric":"f1","value":f1}]
                ).to_csv(OUTPUT_PREDICTION / file_name, index=False, encoding="utf-8-sig")
    log(f"分类模型 Accuracy: {acc:.4f}, F1: {f1:.4f}")

def export_train_metrics_regressor(model, X_train, y_train, file_name):
    pred = model.predict(X_train)
    ev = pd.DataFrame({"y_true":pd.to_numeric(y_train,errors="coerce"),
                       "y_pred":pd.to_numeric(pred,errors="coerce")}).dropna()
    if ev.empty:
        log(f"[警告] {file_name} 无有效评估样本")
        return
    mae  = mean_absolute_error(ev["y_true"], ev["y_pred"])
    rmse = np.sqrt(mean_squared_error(ev["y_true"], ev["y_pred"]))
    pd.DataFrame([{"metric":"mae","value":mae},{"metric":"rmse","value":rmse}]
                ).to_csv(OUTPUT_PREDICTION / file_name, index=False, encoding="utf-8-sig")
    log(f"{file_name} -> MAE:{mae:.2f}, RMSE:{rmse:.2f}")

# =========================================================
# 19. 主流程
# =========================================================
def main():
    log("=== 开始 V2.6_Adapted 训练 ===")
    log(f"PREDICT_START = {PREDICT_START_TS}")
    log(f"PREDICT_END   = {PREDICT_END_TS}")
    log(f"TRAIN_START   = {TRAIN_START}")
    log(f"TRAIN_END     = {TRAIN_END}")
    log(f"LOW_LOAD_THRESHOLD = {LOW_LOAD_THRESHOLD}")
    log(f"VAL_SPLIT_DATE     = {VAL_START}")

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
        raise ValueError("训练数据为空，请检查数据")

    # 样本权重
    train_feature_df = add_recency_weight(train_feature_df, TRAIN_END)
    train_feature_df = add_time_segment_weight(train_feature_df)
    train_feature_df = add_special_day_weight(train_feature_df)
    train_feature_df["sample_weight"] = (
        train_feature_df["recency_weight"] *
        train_feature_df["time_weight"] *
        train_feature_df["special_day_weight"]
    ).clip(lower=0.05, upper=3.0)

    log(f"样本权重: min={train_feature_df['sample_weight'].min():.3f}, "
        f"max={train_feature_df['sample_weight'].max():.3f}, "
        f"mean={train_feature_df['sample_weight'].mean():.3f}")

    use_features = get_feature_list(train_feature_df)
    log(f"使用特征数: {len(use_features)}")

    # ======== 1) 低负荷分类器 ========
    log("\n[阶段1] 训练低负荷分类器...")
    clf_df, X_clf, y_clf, w_clf, clf_meta = prepare_matrix(train_feature_df, "is_low_load", use_features)
    if X_clf is None or X_clf.empty:
        raise ValueError("分类训练矩阵为空")

    clf_model = LGBMClassifier(n_estimators=800, learning_rate=0.03, num_leaves=31,
                               subsample=0.9, colsample_bytree=0.9, random_state=42)
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
    log(f"分类样本: {len(X_clf)}, 低负荷: {y_clf.sum()}")

    # ======== 2) 低负荷回归器 ========
    log("\n[阶段2] 训练低负荷回归器...")
    low_df_raw = train_feature_df[train_feature_df["is_low_load"]==1].copy()
    low_df, X_low, y_low, w_low, low_meta = prepare_matrix(low_df_raw, "model_target_load", use_features)
    if X_low is None or X_low.empty:
        log("[警告] 低负荷回归训练矩阵为空，使用零模型")
        low_model = None
        low_meta = {"use_features":use_features,"cat_cols":[],"num_cols":[],"train_columns":[],"num_fill_values":{}}
    else:
        low_model = LGBMRegressor(n_estimators=500, objective='regression_l1', random_state=42, n_jobs=-1)
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

    # ======== 3) 24个独立小时普通负荷回归器 ========
    log("\n[阶段3] 训练24个独立小时回归器...")
    df_normal = train_feature_df[train_feature_df["is_low_load"]==0].copy()
    log(f"普通负荷样本(全局): {len(df_normal)}")

    # 统一特征空间: 所有24小时模型共享clf_meta的列，确保预测时特征一致
    unified_columns = clf_meta["train_columns"]
    normal_regressors = {}
    val_results = []

    for h in range(0, 24):  # datetime hour 0=24:00, 1=1:00, ..., 23=23:00
        df_h = df_normal[df_normal["hour"]==h].copy()
        display_h = 24 if h == 0 else h  # display: 0→24:00
        if df_h.empty:
            log(f"Hour {display_h}:00 (dt_hour={h}) 无训练数据，跳过")
            normal_regressors[f"hour_{h}"] = None
            continue

        # 划分训练/验证集
        df_h_train = df_h[df_h["datetime"] < VAL_START].copy()
        df_h_val   = df_h[df_h["datetime"] >= VAL_START].copy()

        _, X_h_train_raw, y_h_train, _, _ = prepare_matrix(df_h_train, "model_target_load", use_features)
        _, X_h_val_raw,   y_h_val,   _, _ = prepare_matrix(df_h_val, "model_target_load", use_features) if len(df_h_val)>0 else (None,None,None,None,None)

        if X_h_train_raw is None or X_h_train_raw.empty:
            normal_regressors[f"hour_{h}"] = None
            continue

        # === 统一特征空间: 对齐到clf_meta的列 ===
        X_h_train = pd.DataFrame(0, index=range(len(X_h_train_raw)), columns=unified_columns)
        for c in unified_columns:
            if c in X_h_train_raw.columns:
                X_h_train[c] = X_h_train_raw[c].values
        X_h_train = X_h_train.astype(float)

        if X_h_val_raw is not None and not X_h_val_raw.empty:
            X_h_val = pd.DataFrame(0, index=range(len(X_h_val_raw)), columns=unified_columns)
            for c in unified_columns:
                if c in X_h_val_raw.columns:
                    X_h_val[c] = X_h_val_raw[c].values
            X_h_val = X_h_val.astype(float)
        else:
            X_h_val = None

        model = LGBMRegressor(n_estimators=1500, learning_rate=0.03, num_leaves=63,
                              max_depth=8, min_child_samples=50, subsample=0.8,
                              colsample_bytree=0.8, reg_alpha=0.5,
                              random_state=42, n_jobs=-1, verbose=-1)

        if X_h_val is not None and len(X_h_val)>0 and len(y_h_val)>0:
            model.fit(X_h_train, y_h_train,
                      eval_set=[(X_h_val, y_h_val)],
                      callbacks=[lgb.early_stopping(stopping_rounds=50, verbose=False)])
            val_pred = model.predict(X_h_val)
            val_mae  = mean_absolute_error(y_h_val, val_pred)
            val_rmse = np.sqrt(mean_squared_error(y_h_val, val_pred))
            val_results.append({"display_hour":display_h,"dt_hour":h,"train_samples":len(X_h_train),"val_samples":len(X_h_val),
                                "val_mae":val_mae,"val_rmse":val_rmse,"best_iter":model.best_iteration_})
            log(f"Hour {display_h}:00 (dt={h}) best_iter={model.best_iteration_}, val_mae={val_mae:.2f}")
        else:
            model.fit(X_h_train, y_h_train)
            val_results.append({"display_hour":display_h,"dt_hour":h,"train_samples":len(X_h_train),"val_samples":0,
                                "val_mae":np.nan,"val_rmse":np.nan,"best_iter":model.n_estimators})
            log(f"Hour {display_h}:00 (dt={h}) 全量训练 (n={len(X_h_train)})")

        normal_regressors[f"hour_{h}"] = model

    with open(OUTPUT_MODEL / "normal_load_regressors_v2_6_dict.pkl", "wb") as f:
        pickle.dump(normal_regressors, f)

    pd.DataFrame(val_results).to_csv(OUTPUT_PREDICTION / "validation_hour_model_results_v2_6.csv",
                                     index=False, encoding="utf-8-sig")

    # 保存特征元信息（用分类器的meta兼容）
    normal_meta = clf_meta
    with open(OUTPUT_MODEL / "feature_meta_normal_reg_v2_6.pkl", "wb") as f:
        pickle.dump(normal_meta, f)

    # ======== 导出数据文件 ========
    # 导出历史负荷（含total_load用于预测时lag特征一致性）
    history_df = load_df[
        (load_df["datetime"] >= pd.Timestamp("2024-01-01")) &
        (load_df["datetime"] < PREDICT_START_TS)
    ].copy()

    # 从train_feature_df中提取total_load列（用于预测时lag一致性）
    # train_feature_df.load 已经 = total_load
    tf_tl = train_feature_df[["用户编号","datetime","model_target_load","actual_load"]].copy()
    tf_tl = tf_tl.rename(columns={"model_target_load":"total_load"})
    history_df = history_df.merge(tf_tl, on=["用户编号","datetime"], how="left")
    # 对于未匹配到的（可能因为天气缺失被过滤），用原始load作为total_load
    history_df["total_load"] = history_df["total_load"].fillna(history_df["load"])
    history_df["actual_load"] = history_df["actual_load"].fillna(history_df["load"])

    history_df.to_csv(OUTPUT_PROCESSED / "history_load_for_predict_v2_6.csv", index=False, encoding="utf-8-sig")
    log(f"历史负荷已导出: {len(history_df)} 条（含total_load列）")

    pd.DataFrame([{"用户编号":k,"户号":v} for k,v in user_account_map.items()]
                ).to_csv(OUTPUT_PROCESSED / "user_account_map_v2_6.csv", index=False, encoding="utf-8-sig")

    train_feature_df.to_csv(OUTPUT_PROCESSED / "train_dataset_hourly_v2_6.csv", index=False, encoding="utf-8-sig")
    weather_df.to_csv(OUTPUT_PROCESSED / "hourly_weather_cleaned_v2_6.csv", index=False, encoding="utf-8-sig")

    config_df = pd.DataFrame([{
        "PREDICT_START": str(PREDICT_START_TS),
        "PREDICT_END": str(PREDICT_END_TS),
        "TRAIN_START": str(TRAIN_START),
        "TRAIN_END": str(TRAIN_END),
        "TRAIN_MONTHS": TRAIN_MONTHS,
        "VAL_SPLIT_DATE": str(VAL_START),
        "TARGET_LOAD_MODE": TARGET_LOAD_MODE,
        "LOW_LOAD_THRESHOLD": LOW_LOAD_THRESHOLD,
        "LOW_LOAD_PROBA_THRESHOLD": LOW_LOAD_PROBA_THRESHOLD,
        "VERSION": "v2.6_adapted"
    }])
    config_df.to_csv(OUTPUT_MODEL / "run_config_v2_6.csv", index=False, encoding="utf-8-sig")

    log(f"\n=== V2.6 训练完成 ===")
    log(f"分类样本: {len(X_clf)} (低负荷:{y_clf.sum()})")
    log(f"低负荷回归样本: {len(X_low) if X_low is not None else 0}")
    log(f"24小时模型数: {sum(1 for v in normal_regressors.values() if v is not None)}")

if __name__ == "__main__":
    main()
