# -*- coding: utf-8 -*-
from pathlib import Path
import runpy


SCRIPT_PATH = Path(__file__).resolve().parent / "预测_v4_3_1.py"


if __name__ == "__main__":
    runpy.run_path(str(SCRIPT_PATH), run_name="__main__")
