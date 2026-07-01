# -*- coding: utf-8 -*-
"""诊断: 对比Codex和V2.6预测差异的根源"""
import pandas as pd, numpy as np, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 1. 读取Codex预测 (MWh)
codex = pd.read_csv('1-2负荷预测输出/7-2/prediction_2026-07-02_v3.csv', encoding='utf-8')
print("=== Codex预测 ===")
print(f"形状: {codex.shape}")
print(f"列: {codex.columns.tolist()[:28]}")
# 检查几个用户
for uname in ['泉州南岛新材料科技有限公司', '福建俊杰新材料科技股份有限公司', '福州信青源家具有限公司']:
    row = codex[codex['用户名称']==uname]
    if not row.empty:
        night = row[['1:00','2:00','3:00','4:00']].values[0]
        print(f"\n{uname[:15]} 夜间(1-4h): {[f'{v*1000:.0f}kW' for v in night]} → MWh")

# 2. 读取V2.6预测 (kW)
v26 = pd.read_csv('1-2负荷预测输出/prediction/predict_long_v2_6.csv')
v26['datetime'] = pd.to_datetime(v26['datetime'])
v26['dhour'] = np.where(v26['datetime'].dt.hour==0, 24, v26['datetime'].dt.hour)
print(f"\n\n=== V2.6预测 ===")
for uname in ['泉州南岛新材料科技有限公司', '福建俊杰新材料科技股份有限公司', '福州信青源家具有限公司']:
    udf = v26[v26['用户名称']==uname].sort_values('datetime')
    night = udf[udf['dhour'].isin([1,2,3,4])]
    if not night.empty:
        vals = night['final_pred_net_load'].values
        print(f"\n{uname[:15]} 夜间(1-4h): {[f'{v:.0f}kW' for v in vals]} → {(vals.sum()/1000):.3f}MWh")
        print(f"  是否PV: {udf['是否有光伏_flag'].iloc[0]}, 容量: {udf['光伏容量(MW)'].iloc[0]}MW")
        # 检查天气
        has_temp = night['temperature'].notna().any()
        has_rad = night['shortwave_radiation'].notna().any()
        print(f"  有温度: {has_temp}, 有辐射: {has_rad}")

# 3. 检查训练数据中的实际负荷
print(f"\n\n=== 训练数据验证 ===")
hist = pd.read_csv('1-2负荷预测输出/processed/history_load_for_predict_v2_6.csv')
hist['datetime'] = pd.to_datetime(hist['datetime'])
hist['dhour'] = np.where(hist['datetime'].dt.hour==0, 24, hist['datetime'].dt.hour)

for uname in ['福建俊杰新材料科技股份有限公司', '泉州南岛新材料科技有限公司']:
    udf = hist[hist['用户名称']==uname].sort_values('datetime')
    if udf.empty:
        print(f"\n{uname}: 无训练数据!")
        continue
    night = udf[(udf['dhour'].isin([1,2,3,4])) & (udf['datetime'].dt.date==pd.Timestamp('2026-06-01').date())]
    print(f"\n{uname[:15]} 6月1日夜间实际:")
    for _, r in night.iterrows():
        load = r.get('load', np.nan)
        tl = r.get('total_load', np.nan)
        print(f"  {r['dhour']}:00  gate={load:.0f}kW  total={tl:.0f}kW" if pd.notna(tl) else f"  {r['dhour']}:00  gate={load:.0f}kW")

# 4. 检查天气合并
print(f"\n\n=== 天气数据验证 ===")
w = pd.read_csv('1-2负荷预测输出/processed/hourly_weather_cleaned_v2_6.csv')
print(f"城市: {w['所在市_norm'].unique()}")
ningde = w[(w['所在市_norm']=='宁德') & (w['datetime'].str.contains('2026-06-01'))]
print(f"宁德6月1日: {len(ningde)}条, temp非空{ningde['temperature'].notna().sum()}, rad非空{ningde['shortwave_radiation'].notna().sum()}")
if not ningde.empty:
    print(f"  温度范围: {ningde['temperature'].min():.1f}~{ningde['temperature'].max():.1f}")
    print(f"  辐射范围: {ningde['shortwave_radiation'].min():.1f}~{ningde['shortwave_radiation'].max():.1f}")
