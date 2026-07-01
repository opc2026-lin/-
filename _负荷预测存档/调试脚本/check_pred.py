import pandas as pd, numpy as np, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
df = pd.read_csv('1-2负荷预测输出/prediction/predict_long_v2_6.csv')

low_mask = df['is_low_load']==1
norm_mask = df['is_low_load']==0
print('=== 预测统计 ===')
print(f"总行数: {len(df)}")
print(f"低负荷模型: {low_mask.sum()} 条, 均值={df.loc[low_mask,'final_pred_net_load'].mean():.0f}kW")
print(f"正常模型: {norm_mask.sum()} 条, 均值={df.loc[norm_mask,'final_pred_net_load'].mean():.0f}kW")
print()

for uname in ['福建俊杰新材料科技股份有限公司', '福州信青源家具有限公司', '津太新能源科技（福建）有限公司']:
    print(f'=== {uname[:15]} ===')
    udf = df[df['用户名称']==uname][['datetime','final_pred_net_load','is_low_load','proba_low']]
    print(udf.to_string(index=False))
    print()
