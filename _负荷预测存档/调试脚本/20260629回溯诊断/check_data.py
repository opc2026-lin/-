import pandas as pd, numpy as np, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 1. 历史CSV
hist = pd.read_csv('1-2负荷预测输出/processed/history_load_for_predict_v2_6.csv')
hist['dt'] = pd.to_datetime(hist['datetime'])
print('=== 历史CSV ===')
print(f'total: {len(hist)}, total_load非空: {hist.total_load.notna().sum()}, load非空: {hist.load.notna().sum()}')
recent = hist[hist['dt'] >= '2026-06-23']
print(f'6/23-6/26: {len(recent)}条, {recent["用户编号"].nunique()}用户')

# 俊杰 6/26
jj = recent[(recent['用户编号'].str.contains('ND-GY')) & (recent['dt'].dt.date==pd.Timestamp('2026-06-26').date())]
if not jj.empty:
    print(f'俊杰6/26: {len(jj)}条, load={jj.iloc[0].load}, total_load={jj.iloc[0].total_load}')
    print(f'  6/26 1h: loads={jj[jj["dt"].dt.hour==1][["dt","load","total_load"]].to_string(index=False)}')

# 2. 预测CSV lag列
pred = pd.read_csv('1-2负荷预测输出/prediction/predict_long_v2_6.csv')
for c in ['load_lag_24','load_lag_48','load_lag_168','load_roll_mean_24','load_same_hour_mean_3d']:
    if c in pred.columns:
        nn = pred[c].notna().sum()
        vals = pred[c].dropna()
        if len(vals)>0:
            print(f'{c}: {nn}/{len(pred)}非空, range={vals.min():.0f}~{vals.max():.0f}')
        else:
            print(f'{c}: 全NaN ({nn}/{len(pred)})')
    else:
        print(f'{c}: 列不存在')
