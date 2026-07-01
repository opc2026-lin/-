import pandas as pd, numpy as np, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
df = pd.read_csv('1-2负荷预测输出/prediction/predict_long_v2_6.csv')

# Check specific users
for uid in ['ND-GY-F-001', 'FZ-SY-001']:
    user = df[df['用户编号']==uid]
    name = user['用户名称'].iloc[0]
    night = user[user['datetime'].str.contains('T01:')].sort_values('datetime')
    if not night.empty:
        r = night.iloc[0]
        print(f'{name[:15]}: net={r["final_pred_net_load"]:.0f}kW low={r["is_low_load"]} hour={r["hour"]}')
        print(f'  lag_24={r["load_lag_24"]:.0f} lag_48={r["load_lag_48"]:.0f} roll_mean={r["load_roll_mean_24"]:.0f}')
        print(f'  same_h_3d={r["load_same_hour_mean_3d"]:.0f} same_wh_4={r.get("load_same_weekday_hour_mean_4",np.nan):.0f}')

# Check distribution
print(f'\nTotal: {len(df)}, predicted nonzero: {(df["final_pred_net_load"]>0).sum()}')
print(f'final_pred_net_load: min={df.final_pred_net_load.min():.0f} max={df.final_pred_net_load.max():.0f}')
print(f'Unique night(1h) values: {df[df["hour"]==1]["final_pred_net_load"].nunique()}')
