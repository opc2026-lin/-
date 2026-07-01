# -*- coding: utf-8 -*-
import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
RUNNER_SCRIPT = BASE_DIR / "run_forecast_v4_3.py"


def parse_args():
    parser = argparse.ArgumentParser(description="手动日期运行器 v4.3")
    parser.add_argument(
        "--mode",
        choices=["train", "predict", "validate", "verify", "all"],
        default="all",
        help="运行模式",
    )
    parser.add_argument("--start-date", help="手动指定开始日期 YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=1, help="连续天数，默认 1")
    return parser.parse_args()


def prompt_start_date() -> str:
    while True:
        value = input("请输入目标日期 (YYYY-MM-DD): ").strip()
        try:
            return pd.Timestamp(value).strftime("%Y-%m-%d")
        except Exception:
            print("日期格式无效，请重新输入。")


def prompt_days(default_days: int) -> int:
    value = input(f"请输入连续天数，直接回车默认 {default_days}: ").strip()
    if not value:
        return default_days
    try:
        return max(int(value), 1)
    except Exception:
        print("天数无效，已使用默认值 1。")
        return 1


def run_pipeline(mode: str, start_date: str, days: int):
    cmd = [
        sys.executable,
        str(RUNNER_SCRIPT),
        "--mode",
        mode,
        "--start-date",
        start_date,
        "--days",
        str(days),
    ]
    print(f"目标日期: {start_date}")
    print(f"模式: {mode}")
    print(f"天数: {days}")
    result = subprocess.run(cmd, cwd=str(BASE_DIR))
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main():
    args = parse_args()
    start_date = args.start_date or prompt_start_date()
    days = max(int(args.days), 1)
    if not args.start_date:
        days = prompt_days(days)
    run_pipeline(args.mode, pd.Timestamp(start_date).strftime("%Y-%m-%d"), days)


if __name__ == "__main__":
    main()
