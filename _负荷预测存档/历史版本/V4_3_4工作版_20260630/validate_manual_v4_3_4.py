# -*- coding: utf-8 -*-
import runpy
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
SCRIPT_PATH = BASE_DIR / "回测_v4_3_4.py"


if __name__ == "__main__":
    runpy.run_path(str(SCRIPT_PATH), run_name="__main__")
