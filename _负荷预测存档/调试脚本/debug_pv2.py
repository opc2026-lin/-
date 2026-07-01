# debug_pv2.py - Test PV daily parsing
import pandas as pd, re, numpy as np
from pathlib import Path
import sys, io, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_DIR = Path('D:/亿云能源科技售电交易数据库')
WEATHER_DIR = BASE_DIR / '1-1负荷预测输入' / '2.天气'

def normalize_text(x):
    if pd.isna(x): return None
    return str(x).strip().replace('\u3000','').replace(' ','')

PREDICT_START_TS = pd.Timestamp('2026-07-02 00:00:00')

pv_files = glob.glob(str(WEATHER_DIR / 'fujian_pv_daily*.xlsx'))
all_rows = []

for fp in pv_files:
    try:
        xls = pd.ExcelFile(fp)
    except: continue
    
    for sheet_name in xls.sheet_names:
        ts_str = PREDICT_START_TS.strftime('%#m月%#d日')
        if ts_str not in sheet_name:
            continue
        
        print(f'Processing: {Path(fp).name} / {sheet_name}')
        raw = pd.read_excel(fp, sheet_name=sheet_name, header=None)
        print(f'  Shape: {raw.shape}')
        
        i = 0
        while i < len(raw):
            if pd.isna(raw.iloc[i, 0]) or i+4 >= len(raw):
                i += 1
                continue
            
            header = str(raw.iloc[i, 0])
            has_pipe = '|' in header
            has_kw = 'kw' in header.lower()
            
            if not has_pipe or not has_kw:
                i += 1
                continue
            
            parts = header.split('|')
            user_name_raw = parts[0].strip()
            city_raw = parts[1].strip() if len(parts)>1 else ''
            city = normalize_text(city_raw)
            
            print(f'  Found user: {user_name_raw[:30]}... city={city}')
            
            temp_row_idx = i + 2
            rad_row_idx = i + 3
            
            added = 0
            for h in range(1, 25):
                if h >= raw.shape[1]:
                    break
                
                try:
                    tv = raw.iloc[temp_row_idx, h]
                    rv = raw.iloc[rad_row_idx, h]
                except:
                    continue
                
                str_tv = str(tv).strip()
                str_rv = str(rv).strip()
                
                temp_val = np.nan
                if str_tv != '-' and str_tv != 'nan':
                    try: temp_val = pd.to_numeric(tv, errors='coerce')
                    except: pass
                
                rad_val = np.nan
                if str_rv != '-' and str_rv != 'nan':
                    try: rad_val = pd.to_numeric(rv, errors='coerce')
                    except: pass
                
                dt = PREDICT_START_TS.normalize() + pd.Timedelta(hours=h-1)
                if h == 24:
                    dt = PREDICT_START_TS.normalize() + pd.Timedelta(days=1)
                
                all_rows.append({
                    'user_name_raw': user_name_raw,
                    'city': city,
                    'datetime': dt,
                    'temperature': temp_val,
                    'shortwave_radiation': rad_val,
                })
                added += 1
            
            print(f'  Added {added} rows')
            i += 5  # Skip user block

print(f'\nTotal rows collected: {len(all_rows)}')
if all_rows:
    df = pd.DataFrame(all_rows)
    print(f'\nCity counts: {df["city"].value_counts().to_dict()}')
    print(f'Temp non-null: {df["temperature"].notna().sum()}')
    print(f'Rad non-null: {df["shortwave_radiation"].notna().sum()}')
    print(f'\nSample:')
    print(df.head(10).to_string())
