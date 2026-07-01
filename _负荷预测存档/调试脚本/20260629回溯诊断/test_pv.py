import pandas as pd, glob, numpy as np, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from pathlib import Path

pv_files = glob.glob('1-1负荷预测输入/2.天气/fujian_pv_daily*.xlsx')
print(f'Found {len(pv_files)} files')
for fp in sorted(pv_files):
    xls = pd.ExcelFile(fp)
    for sn in xls.sheet_names:
        if '6月27日' in sn:
            print(f'  MATCH: {Path(fp).name} / {sn}')
            raw = pd.read_excel(xls, sheet_name=sn, header=None)
            h = str(raw.iloc[0,0])
            print(f'    shape={raw.shape}')
            print(f'    has_pipe={"|" in h}, has_kw={"kw" in h.lower()}')
            print(f'    header: {h[:80]}...')
            rows_with_data = 0
            for i in range(len(raw)):
                for j in range(1,25):
                    v = raw.iloc[i,j] if j<raw.shape[1] else None
                    if pd.notna(v) and str(v).strip() not in ('-','','nan'):
                        rows_with_data += 1
                        break
            print(f'    rows with data: {rows_with_data}/{len(raw)}')
