import pandas as pd, numpy as np, sys, io, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Check prediction CSV
df = pd.read_csv('1-2负荷预测输出/prediction/predict_long_v2_6.csv')
print(f'=== 预测CSV: {len(df)} 行 ===')
print(f"final_pred_net_load: min={df.final_pred_net_load.min():.0f} max={df.final_pred_net_load.max():.0f} mean={df.final_pred_net_load.mean():.0f}")
print(f"已预测: {df.predict_status.value_counts().to_dict()}")
print()

# Check summary excel
summary_path = '1-2负荷预测输出/prediction/7月2日_负荷预测汇总表_V2.6.xlsx'
xls = pd.ExcelFile(summary_path)
print(f'=== 汇总表 Sheets: {xls.sheet_names} ===')
for sn in xls.sheet_names:
    sdf = pd.read_excel(xls, sheet_name=sn)
    print(f'\n--- {sn} (shape={sdf.shape}) ---')
    print(sdf.columns.tolist())
    print(sdf.head(3).to_string())

# Check a user to verify 24 hours
print('\n=== 验证: 福建俊杰新材料 24时段 ===')
p1 = df[df['用户名称']=='福建俊杰新材料科技股份有限公司']
p1_sorted = p1.sort_values('datetime')
for _, r in p1_sorted.iterrows():
    h = r['datetime'].hour if isinstance(r['datetime'], pd.Timestamp) else pd.Timestamp(r['datetime']).hour
    dh = 24 if h==0 else h
    print(f"  {dh}:00  net={r['final_pred_net_load']:.1f}kW  low={r['is_low_load']}")
