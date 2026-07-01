# -*- coding: utf-8 -*-
import subprocess
import sys
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
RUNNER_SCRIPT = BASE_DIR / "run_forecast_v4_3_5.py"


def prompt_start_date() -> str:
    while True:
        value = input("请输入回测的起始日期 (YYYY-MM-DD): ").strip()
        try:
            return pd.Timestamp(value).strftime("%Y-%m-%d")
        except Exception:
            print("日期格式无效，请重新输入。")


def prompt_days() -> int:
    value = input("请输入连续天数，直接回车默认 1: ").strip()
    if not value:
        return 1
    try:
        return max(int(value), 1)
    except Exception:
        print("天数无效，已使用默认值 1。")
        return 1


def main():
    start_date = prompt_start_date()
    days = prompt_days()
    cmd = [
        sys.executable,
        str(RUNNER_SCRIPT),
        "--mode",
        "validate",
        "--start-date",
        start_date,
        "--days",
        str(days),
    ]
    print(f"起始日期: {start_date}")
    print(f"连续天数: {days}")
    raise SystemExit(subprocess.run(cmd, cwd=str(BASE_DIR)).returncode)


if __name__ == "__main__":
    main()
