# debug_pv.py
import pandas as pd
from pathlib import Path

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ts = pd.Timestamp('2026-07-02')
s1 = ts.strftime('%#m月%#d日')
s2 = ts.strftime('%m月%d日')
print(f'Format strings: s1={s1}, s2={s2}')

BASE_DIR = Path('D:/亿云能源科技售电交易数据库')
WEATHER_DIR = BASE_DIR / '1-1负荷预测输入' / '2.天气'

import glob
pv_files = glob.glob(str(WEATHER_DIR / 'fujian_pv_daily*.xlsx'))
print(f'PV files found: {len(pv_files)}')

for fp in pv_files:
    print(f'\n=== {Path(fp).name} ===')
    xls = pd.ExcelFile(fp)
    for sn in xls.sheet_names:
        match1 = s1 in sn
        match2 = s2 in sn
        print(f'  Sheet: "{sn}" -> match1={match1}, match2={match2}')
        if match1 or match2:
            raw = pd.read_excel(xls, sheet_name=sn, header=None)
            print(f'  Shape: {raw.shape}')
            # Show first few rows
            for i in range(min(12, len(raw))):
                vals = []
                for j in range(min(5, raw.shape[1])):
                    v = raw.iloc[i, j]
                    if pd.notna(v):
                        vals.append(str(v)[:40])
                    else:
                        vals.append('NaN')
                print(f'    Row{i}: {vals}')
