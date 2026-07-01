# -*- coding: utf-8 -*-
"""
V3 验证脚本

用途：
1. 从 1-2负荷预测输出 读取 prediction_result_v3_long.csv
2. 从 1-1负荷预测输入 读取真实负荷与真实天气
3. 逐用户逐小时对齐，输出真实误差报告
"""

import glob
import re
from pathlib import Path

import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parents[1]

INPUT_ROOT = PROJECT_DIR / "1-1负荷预测输入"
OUTPUT_ROOT = PROJECT_DIR / "1-2负荷预测输出"

USER_MASTER_PATH = INPUT_ROOT / "用户主档案表.xlsx"
LOAD_DIR = INPUT_ROOT / "1.分时段历史用电信息"
WEATHER_DIR = INPUT_ROOT / "3.真实天气"

OUTPUT_PREDICTION = OUTPUT_ROOT / "prediction"
OUTPUT_MODEL = OUTPUT_ROOT / "model"
OUTPUT_VALIDATION = OUTPUT_ROOT / "validation"

for path in [OUTPUT_VALIDATION]:
    path.mkdir(parents=True, exist_ok=True)


PV_EFFICIENCY = 0.75
PV_TEMP_COEFF = -0.004


def normalize_text(value):
    if pd.isna(value):
        return None
    return str(value).strip().replace("\u3000", "").replace(" ", "")


def convert_yes_no(value):
    text = normalize_text(value)
    return 1 if text in {"是", "有", "1", "true", "True", "Y", "y"} else 0


def compute_metrics(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mae = np.mean(np.abs(y_true - y_pred))
    rmse = np.sqrt(np.mean((y_true - y_pred) ** 2))
    mape = np.mean(np.abs(y_true - y_pred) / np.maximum(np.abs(y_true), 1e-6)) * 100
    return mae, rmse, mape


def load_run_config():
    config_path = OUTPUT_MODEL / "run_config_v3.csv"
    if not config_path.exists():
        raise FileNotFoundError(f"未找到运行配置: {config_path}")
    cfg = pd.read_csv(config_path, encoding="utf-8-sig").iloc[0]
    predict_start = pd.Timestamp(cfg["PREDICT_START"])
    predict_end = pd.Timestamp(cfg["PREDICT_END"])
    low_load_threshold = float(cfg["LOW_LOAD_THRESHOLD"])
    return predict_start, predict_end, low_load_threshold


def load_user_master():
    df = pd.read_excel(USER_MASTER_PATH)
    df.columns = [str(col).strip() for col in df.columns]

    if "所在区" not in df.columns:
        df["所在区"] = df["所在市"].astype(str) + "区"
    if "是否有光伏" not in df.columns:
        df["是否有光伏"] = "否"
    if "光伏容量(MW)" not in df.columns:
        df["光伏容量(MW)"] = 0.0

    df["用户名称_norm"] = df["用户名称"].apply(normalize_text)
    df["是否有光伏_flag"] = df["是否有光伏"].apply(convert_yes_no)
    df["光伏容量(MW)"] = pd.to_numeric(df["光伏容量(MW)"], errors="coerce").fillna(0.0)
    df["所在市_norm"] = df["所在市"].apply(normalize_text)
    return df


def load_prediction_long():
    pred_path = OUTPUT_PREDICTION / "prediction_result_v3_long.csv"
    if not pred_path.exists():
        raise FileNotFoundError(f"未找到预测结果: {pred_path}")

    df = pd.read_csv(pred_path, encoding="utf-8-sig")
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    df = df.dropna(subset=["datetime"]).copy()
    return df


def _find_header_row(raw_df):
    for idx in range(min(len(raw_df), 6)):
        row_text = " ".join([str(x) for x in raw_df.iloc[idx].tolist() if pd.notna(x)])
        if "电量年月日" in row_text or "电力用户名称" in row_text:
            return idx
    return None


def _build_user_lookup(user_master_df):
    lookup = {}
    for _, row in user_master_df.iterrows():
        name_norm = row["用户名称_norm"]
        if not name_norm:
            continue
        lookup[name_norm] = row
        if "(" in name_norm:
            lookup[name_norm.split("(")[0]] = row
        if "（" in name_norm:
            lookup[name_norm.split("（")[0]] = row
    return lookup


def load_actual_load(user_master_df, predict_start, predict_end):
    files = sorted(glob.glob(str(LOAD_DIR / "*.xlsx"))) + sorted(glob.glob(str(LOAD_DIR / "*.xls")))
    if not files:
        raise FileNotFoundError(f"未找到真实负荷文件: {LOAD_DIR}")

    user_lookup = _build_user_lookup(user_master_df)
    records = []
    available_days = set()
    valid_dates = {
        dt.normalize()
        for dt in pd.date_range(predict_start - pd.Timedelta(days=1), predict_end, freq="D")
    }

    for fp in files:
        try:
            raw = pd.read_excel(fp, sheet_name=0, header=None)
        except Exception:
            continue

        header_row = _find_header_row(raw)
        if header_row is None:
            continue

        df = pd.read_excel(fp, sheet_name=0, header=header_row)
        df.columns = [str(col).strip() for col in df.columns]

        if "电量年月日" not in df.columns:
            continue
        if "电力用户名称" not in df.columns:
            continue

        df["电量年月日"] = df["电量年月日"].astype(str).str.strip()
        df = df[df["电量年月日"].str.fullmatch(r"\d{8}", na=False)].copy()
        if df.empty:
            continue

        df["date"] = pd.to_datetime(df["电量年月日"], format="%Y%m%d", errors="coerce")
        available_days.update(df["date"].dropna().dt.strftime("%Y-%m-%d").tolist())
        df = df[df["date"].isin(valid_dates)].copy()
        if df.empty:
            continue

        hour_cols = sorted(
            [str(col).strip() for col in df.columns if re.fullmatch(r"(1?\d|2[0-4]):00", str(col).strip())],
            key=lambda x: int(x.split(":")[0]),
        )
        if len(hour_cols) < 20:
            continue

        df["电力用户名称_norm"] = df["电力用户名称"].apply(normalize_text)
        for user_name_norm, user_rows in df.groupby("电力用户名称_norm"):
            matched_user = user_lookup.get(user_name_norm)
            if matched_user is None and user_name_norm:
                for key, value in user_lookup.items():
                    if key and (key in user_name_norm or user_name_norm in key):
                        matched_user = value
                        break
            if matched_user is None:
                continue

            melted = user_rows.melt(
                id_vars=["date"],
                value_vars=hour_cols,
                var_name="hour_str",
                value_name="actual_load",
            )
            melted["actual_load"] = pd.to_numeric(melted["actual_load"], errors="coerce")

            def build_datetime(row):
                hour = int(str(row["hour_str"]).split(":")[0])
                base_date = row["date"]
                if pd.isna(base_date):
                    return pd.NaT
                if hour == 24:
                    return base_date + pd.Timedelta(days=1)
                return base_date + pd.Timedelta(hours=hour)

            melted["datetime"] = melted.apply(build_datetime, axis=1)
            melted = melted[
                (melted["datetime"] >= predict_start) & (melted["datetime"] < predict_end)
            ].copy()
            if melted.empty:
                continue

            melted["用户编号"] = matched_user["用户编号"]
            melted["用户名称"] = matched_user["用户名称"]
            melted["所在市_norm"] = matched_user["所在市_norm"]
            melted["是否有光伏_flag"] = matched_user["是否有光伏_flag"]
            melted["光伏容量(MW)"] = matched_user["光伏容量(MW)"]

            records.append(
                melted[["用户编号", "用户名称", "所在市_norm", "datetime", "actual_load", "是否有光伏_flag", "光伏容量(MW)"]]
            )

    if not records:
        latest_day = max(available_days) if available_days else "无可用日期"
        raise ValueError(f"未读取到预测区间内的真实负荷数据，当前真实负荷最新日期: {latest_day}")

    actual_df = pd.concat(records, ignore_index=True)
    actual_df = actual_df.dropna(subset=["datetime", "actual_load"]).copy()
    actual_df = (
        actual_df.groupby(["用户编号", "用户名称", "所在市_norm", "datetime", "是否有光伏_flag", "光伏容量(MW)"], as_index=False)
        ["actual_load"]
        .mean()
    )
    return actual_df.sort_values(["用户编号", "datetime"]).reset_index(drop=True)


def load_actual_weather():
    weather_files = sorted(glob.glob(str(WEATHER_DIR / "*.xlsx"))) + sorted(glob.glob(str(WEATHER_DIR / "*.xls")))
    city_sheet_map = {
        "宁德": "宁德",
        "莆田": "莆田",
        "福州": "福州",
        "泉州": "泉州",
    }
    records = []

    for fp in weather_files:
        try:
            xls = pd.ExcelFile(fp)
        except Exception:
            continue

        for sheet_name in xls.sheet_names:
            city_name = None
            for key, value in city_sheet_map.items():
                if key in str(sheet_name):
                    city_name = value
                    break
            if city_name is None:
                continue

            try:
                raw = pd.read_excel(fp, sheet_name=sheet_name, header=None)
            except Exception:
                continue

            row_idx = 0
            while row_idx < len(raw):
                header_text = str(raw.iloc[row_idx, 0]) if pd.notna(raw.iloc[row_idx, 0]) else ""
                date_match = re.search(r"(\d+)月(\d+)日", header_text)
                if not date_match:
                    row_idx += 1
                    continue

                month = int(date_match.group(1))
                day = int(date_match.group(2))
                date_base = pd.Timestamp(year=2026, month=month, day=day)

                for hour in range(24):
                    col = hour + 1
                    temperature = pd.to_numeric(raw.iloc[row_idx + 2, col], errors="coerce") if row_idx + 2 < len(raw) and col < raw.shape[1] else np.nan
                    radiation = pd.to_numeric(raw.iloc[row_idx + 3, col], errors="coerce") if row_idx + 3 < len(raw) and col < raw.shape[1] else np.nan
                    records.append(
                        {
                            "所在市_norm": city_name,
                            "datetime": date_base + pd.Timedelta(hours=hour),
                            "temperature": temperature,
                            "shortwave_radiation": radiation,
                        }
                    )

                row_idx += 8

    if not records:
        return pd.DataFrame(columns=["所在市_norm", "datetime", "temperature", "shortwave_radiation"])

    weather_df = pd.DataFrame(records)
    weather_df["datetime"] = pd.to_datetime(weather_df["datetime"]).dt.floor("h")
    weather_df = weather_df.drop_duplicates(subset=["所在市_norm", "datetime"], keep="last")
    return weather_df.sort_values(["所在市_norm", "datetime"]).reset_index(drop=True)


def estimate_actual_pv(actual_df, weather_df):
    df = actual_df.merge(weather_df, on=["所在市_norm", "datetime"], how="left")
    df["temperature"] = pd.to_numeric(df["temperature"], errors="coerce")
    df["shortwave_radiation"] = pd.to_numeric(df["shortwave_radiation"], errors="coerce")

    for col in ["temperature", "shortwave_radiation"]:
        city_median = df.groupby("所在市_norm")[col].transform("median")
        global_median = df[col].median()
        if pd.isna(global_median):
            global_median = 0.0
        df[col] = df[col].fillna(city_median).fillna(global_median)

    df["actual_pv_est"] = 0.0
    pv_mask = (df["是否有光伏_flag"] == 1) & (df["光伏容量(MW)"] > 0)
    df.loc[pv_mask, "actual_pv_est"] = (
        df.loc[pv_mask, "光伏容量(MW)"] * 1000 * PV_EFFICIENCY *
        (df.loc[pv_mask, "shortwave_radiation"] / 1000.0) *
        (1 + PV_TEMP_COEFF * (df.loc[pv_mask, "temperature"] - 25.0))
    )
    df["actual_pv_est"] = df["actual_pv_est"].clip(lower=0.0)
    df["actual_total_load"] = df["actual_load"] + df["actual_pv_est"]
    return df


def build_validation(actual_df, pred_df, low_load_threshold):
    keep_cols = [
        "用户编号",
        "用户名称",
        "datetime",
        "pv_capacity",
        "pv_est",
        "proba_low",
        "is_low_load_pred",
        "pred_total_load",
        "pred_net_load",
    ]
    pred_df = pred_df[[col for col in keep_cols if col in pred_df.columns]].copy()

    merged = actual_df.merge(pred_df, on=["用户编号", "用户名称", "datetime"], how="left")
    merged["hour"] = merged["datetime"].dt.hour
    merged["pred_net_load"] = pd.to_numeric(merged["pred_net_load"], errors="coerce")
    merged["pred_total_load"] = pd.to_numeric(merged["pred_total_load"], errors="coerce")
    merged["pv_est"] = pd.to_numeric(merged.get("pv_est", 0.0), errors="coerce").fillna(0.0)
    merged["actual_load"] = pd.to_numeric(merged["actual_load"], errors="coerce")

    merged["net_error"] = merged["pred_net_load"] - merged["actual_load"]
    merged["net_abs_error"] = merged["net_error"].abs()

    merged["total_error"] = merged["pred_total_load"] - merged["actual_total_load"]
    merged["total_abs_error"] = merged["total_error"].abs()

    merged["is_low_load_actual"] = (merged["actual_load"] < low_load_threshold).astype(int)
    merged["is_daytime_8_19"] = merged["hour"].between(8, 19).astype(int)
    merged["has_prediction"] = merged["pred_net_load"].notna().astype(int)
    return merged


def save_reports(validation_df, predict_start):
    validation_path = OUTPUT_VALIDATION / "validation_result_v3_long.csv"
    validation_df.to_csv(validation_path, index=False, encoding="utf-8-sig")

    valid_net = validation_df.dropna(subset=["actual_load", "pred_net_load"]).copy()
    valid_total = validation_df.dropna(subset=["actual_total_load", "pred_total_load"]).copy()

    net_mae, net_rmse, net_mape = compute_metrics(valid_net["actual_load"], valid_net["pred_net_load"])
    total_mae, total_rmse, total_mape = compute_metrics(valid_total["actual_total_load"], valid_total["pred_total_load"])

    summary = pd.DataFrame(
        [
            {
                "date": predict_start.strftime("%Y-%m-%d"),
                "sample_count": len(validation_df),
                "matched_prediction_count": int(validation_df["has_prediction"].sum()),
                "user_count": validation_df["用户编号"].nunique(),
                "net_mae_kw": net_mae,
                "net_rmse_kw": net_rmse,
                "net_mape_pct": net_mape,
                "total_mae_kw": total_mae,
                "total_rmse_kw": total_rmse,
                "total_mape_pct": total_mape,
                "actual_net_mwh": valid_net["actual_load"].sum() / 1000.0,
                "pred_net_mwh": valid_net["pred_net_load"].sum() / 1000.0,
                "actual_total_mwh": valid_total["actual_total_load"].sum() / 1000.0,
                "pred_total_mwh": valid_total["pred_total_load"].sum() / 1000.0,
            }
        ]
    )
    summary_path = OUTPUT_VALIDATION / "validation_summary_v3.csv"
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")

    user_summary = (
        validation_df.dropna(subset=["actual_load", "pred_net_load"])
        .groupby(["用户编号", "用户名称"], as_index=False)
        .agg(
            actual_net_mwh=("actual_load", lambda s: s.sum() / 1000.0),
            pred_net_mwh=("pred_net_load", lambda s: s.sum() / 1000.0),
            net_mae_kw=("net_abs_error", "mean"),
            max_abs_error_kw=("net_abs_error", "max"),
        )
        .sort_values("net_mae_kw", ascending=False)
    )
    user_summary_path = OUTPUT_VALIDATION / "validation_user_summary_v3.csv"
    user_summary.to_csv(user_summary_path, index=False, encoding="utf-8-sig")

    print("=" * 60)
    print("V3 真实回测结果")
    print("=" * 60)
    print(f"预测日期: {predict_start:%Y-%m-%d}")
    print(f"样本数: {len(validation_df)}")
    print(f"成功对齐预测样本: {int(validation_df['has_prediction'].sum())}")
    print(f"净负荷 MAE: {net_mae:.2f} kW")
    print(f"净负荷 RMSE: {net_rmse:.2f} kW")
    print(f"净负荷 MAPE: {net_mape:.2f}%")
    print(f"总需求 MAE: {total_mae:.2f} kW")
    print(f"总需求 RMSE: {total_rmse:.2f} kW")
    print(f"总需求 MAPE: {total_mape:.2f}%")
    print(f"明细输出: {validation_path}")
    print(f"汇总输出: {summary_path}")
    print(f"用户汇总: {user_summary_path}")


def main():
    predict_start, predict_end, low_load_threshold = load_run_config()
    user_master_df = load_user_master()
    pred_df = load_prediction_long()
    try:
        actual_df = load_actual_load(user_master_df, predict_start, predict_end)
    except ValueError as exc:
        print(f"无法执行真实回测: {exc}")
        print(f"当前预测区间: {predict_start:%Y-%m-%d %H:%M:%S} 至 {predict_end:%Y-%m-%d %H:%M:%S}")
        print("请把对应日期的真实负荷文件放入 1-1负荷预测输入/1.分时段历史用电信息 后再运行。")
        return
    weather_df = load_actual_weather()
    actual_df = estimate_actual_pv(actual_df, weather_df)
    validation_df = build_validation(actual_df, pred_df, low_load_threshold)
    save_reports(validation_df, predict_start)


if __name__ == "__main__":
    main()
