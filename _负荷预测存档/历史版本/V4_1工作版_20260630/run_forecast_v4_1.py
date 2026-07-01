# -*- coding: utf-8 -*-
import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent

TRAIN_SCRIPT = BASE_DIR / "01_train_v4_1.py"
PREDICT_SCRIPT = BASE_DIR / "02_predict_v4_1.py"
VALIDATE_SCRIPT = BASE_DIR / "03_validate_v4_1.py"
VERIFY_SCRIPT = BASE_DIR / "04_verify_v4_1.py"


def parse_args():
    parser = argparse.ArgumentParser(description="本地负荷预测运行器 v4.1")
    parser.add_argument(
        "--mode",
        choices=["train", "predict", "validate", "verify", "all"],
        default="all",
        help="运行模式",
    )
    parser.add_argument(
        "--start-date",
        required=True,
        help="起始日期，格式 YYYY-MM-DD",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="连续运行天数，至少 1",
    )
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

    print("本地负荷预测运行器 v4.1")
    print(f"模式: {args.mode}")
    print(f"日期: {date_list[0]} -> {date_list[-1]}")
    print(f"天数: {day_count}")

    for one_date in date_list:
        if args.mode in {"train", "all"}:
            run_script(TRAIN_SCRIPT, one_date)
        if args.mode in {"predict", "all"}:
            run_script(PREDICT_SCRIPT, one_date)
        if args.mode in {"validate", "all"}:
            run_script(VALIDATE_SCRIPT, one_date)
        if args.mode in {"verify", "all"}:
            run_script(VERIFY_SCRIPT, one_date)

    print("\n全部任务执行完成。")


if __name__ == "__main__":
    main()
