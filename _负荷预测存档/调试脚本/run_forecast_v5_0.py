# -*- coding: utf-8 -*-
import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent

TRAIN_SCRIPT = BASE_DIR / "01_train_v5_0.py"
PREDICT_SCRIPT = BASE_DIR / "02_predict_v5_0.py"
VALIDATE_SCRIPT = BASE_DIR / "03_validate_v5_0.py"
VERIFY_SCRIPT = BASE_DIR / "04_verify_v5_0.py"


def parse_args():
    parser = argparse.ArgumentParser(description="负荷预测本地运行器 v5.0")
    parser.add_argument(
        "--mode",
        choices=["train", "predict", "train_predict", "validate", "verify"],
        default="train_predict",
        help="运行模式",
    )
    parser.add_argument("--start-date", required=True, help="起始日期，格式 YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=1, help="连续运行天数，默认 1")
    return parser.parse_args()


def run_script(script_path: Path, start_date: str):
    cmd = [sys.executable, str(script_path), "--start-date", start_date, "--days", "1"]
    print(f"\n=== 运行 {script_path.name} | 目标日期 {start_date} ===")
    result = subprocess.run(cmd, cwd=str(BASE_DIR))
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main():
    args = parse_args()
    day_count = max(int(args.days), 1)
    start_ts = pd.Timestamp(args.start_date).normalize()
    date_list = [
        (start_ts + pd.Timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in range(day_count)
    ]

    print("负荷预测本地运行器 v5.0")
    print(f"模式: {args.mode}")
    print(f"起始日: {date_list[0]}")
    print(f"结束日: {date_list[-1]}")
    print(f"天数: {day_count}")

    for one_date in date_list:
        if args.mode == "train":
            run_script(TRAIN_SCRIPT, one_date)
        elif args.mode == "predict":
            run_script(PREDICT_SCRIPT, one_date)
        elif args.mode == "train_predict":
            run_script(TRAIN_SCRIPT, one_date)
            run_script(PREDICT_SCRIPT, one_date)
        elif args.mode == "validate":
            run_script(VALIDATE_SCRIPT, one_date)
        elif args.mode == "verify":
            run_script(VERIFY_SCRIPT, one_date)

    print("\n全部任务执行完成。")


if __name__ == "__main__":
    main()
