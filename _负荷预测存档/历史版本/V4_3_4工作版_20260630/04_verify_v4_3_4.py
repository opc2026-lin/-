# -*- coding: utf-8 -*-
import argparse
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parents[1]
PREDICTION_ROOT = PROJECT_DIR / "1-2负荷预测输出"
EVAL_ROOT = PROJECT_DIR / "1-3负荷回测效验"

OUTPUT_MODEL = PREDICTION_ROOT / "model"
OUTPUT_PREDICTION = PREDICTION_ROOT / "prediction"
VERIFY_DIR = EVAL_ROOT / "校验结果"
VERIFY_DIR.mkdir(parents=True, exist_ok=True)

REQUIRED_MODEL_FILES = [
    "low_load_classifier_v3.pkl",
    "feature_meta_classifier_v3.pkl",
    "low_load_regressor_v3.pkl",
    "feature_meta_low_reg_v3.pkl",
    "normal_load_regressors_v3_dict.pkl",
    "normal_reg_metas_v3_dict.pkl",
    "available_features_v3.pkl",
]


def parse_args():
    parser = argparse.ArgumentParser(description="负荷预测结果校验 v4.3.4")
    parser.add_argument("--start-date", required=True, help="目标日期 YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=1, help="连续天数")
    return parser.parse_args()


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def build_summary(day_df: pd.DataFrame):
    rows = []
    for keyword, expected_group, expected_prefix in [
        ("安捷", "property", "property_hour_"),
        ("元兴", "property", "property_hour_"),
        ("象园", "property", "property_hour_"),
        ("津太", "energy", "energy_hour_"),
        ("津泰", "energy", "energy_hour_"),
    ]:
        sub = day_df[day_df["用户名称"].astype(str).str.contains(keyword, na=False)]
        if sub.empty:
            continue
        non_low = sub[sub["model_route"] != "low_load_regressor"]
        if not non_low.empty:
            assert_true((non_low["user_type_group"] == expected_group).all(), f"{keyword} 分组错误")
            assert_true(non_low["model_route"].astype(str).str.startswith(expected_prefix).all(), f"{keyword} 路由错误")
        rows.append({
            "用户关键字": keyword,
            "总时段数": len(sub),
            "低负荷时段数": int((sub["model_route"] == "low_load_regressor").sum()),
            "日预测kWh": round(float(sub["pred_net_load"].sum()), 3),
        })

    sanqing = day_df[day_df["用户名称"].astype(str).str.contains("三清", na=False)]
    if not sanqing.empty:
        low_count = int((sanqing["model_route"] == "low_load_regressor").sum())
        assert_true(low_count <= 18, f"三清低负荷时段仍过多: {low_count}")
        rows.append({
            "用户关键字": "三清",
            "总时段数": len(sanqing),
            "低负荷时段数": low_count,
            "日预测kWh": round(float(sanqing["pred_net_load"].sum()), 3),
        })

    for keyword in ["至和", "天泽"]:
        sub = day_df[day_df["用户名称"].astype(str).str.contains(keyword, na=False)]
        if sub.empty:
            continue
        assert_true((sub["pred_total_load"] > 0).all(), f"{keyword} 仍存在 0 负荷预测")
        rows.append({
            "用户关键字": keyword,
            "总时段数": len(sub),
            "低负荷时段数": int((sub["model_route"] == "low_load_regressor").sum()),
            "日预测kWh": round(float(sub["pred_net_load"].sum()), 3),
        })
    return pd.DataFrame(rows)


def main():
    args = parse_args()
    pred_date = pd.Timestamp(args.start_date).strftime("%Y-%m-%d")

    for file_name in REQUIRED_MODEL_FILES:
        assert_true((OUTPUT_MODEL / file_name).exists(), f"缺少模型文件: {file_name}")

    long_path = OUTPUT_PREDICTION / "prediction_result_v3_long.csv"
    wide_path = OUTPUT_PREDICTION / f"prediction_{pred_date}_v3.csv"
    assert_true(long_path.exists(), f"缺少预测长表文件: {long_path.name}")
    assert_true(wide_path.exists(), f"缺少预测宽表文件: {wide_path.name}")

    long_df = pd.read_csv(long_path, encoding="utf-8-sig")
    long_df["datetime"] = pd.to_datetime(long_df["datetime"])
    for col in ["pred_total_load", "pred_net_load", "proba_low"]:
        if col in long_df.columns:
            long_df[col] = pd.to_numeric(long_df[col], errors="coerce")
    day_df = long_df[long_df["datetime"].dt.strftime("%Y-%m-%d") == pred_date].copy()

    assert_true(not day_df.empty, f"{pred_date} 预测长表为空")
    assert_true((day_df["pred_net_load"] >= 0).all(), "存在负的净负荷预测")
    assert_true((day_df["pred_total_load"] >= 0).all(), "存在负的总负荷预测")
    assert_true(day_df["hour"].nunique() == 24, "预测小时不完整")
    assert_true("model_route" in day_df.columns, "预测结果缺少 model_route")
    assert_true("user_type_group" in day_df.columns, "预测结果缺少 user_type_group")
    assert_true((day_df["model_route"] != "unassigned").all(), "存在未分配模型路由的记录")

    verify_df = build_summary(day_df)
    verify_path = VERIFY_DIR / f"校验结果_{pred_date}_v4_3_4.csv"
    verify_df.to_csv(verify_path, index=False, encoding="utf-8-sig")

    print(f"校验通过: {pred_date}")
    print(f"校验结果: {verify_path}")
    if not verify_df.empty:
        print(verify_df.to_string(index=False))


if __name__ == "__main__":
    main()
