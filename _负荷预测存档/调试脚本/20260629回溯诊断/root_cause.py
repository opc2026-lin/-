import pandas as pd, numpy as np, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 1. 预测长表
pred = pd.read_csv('1-2负荷预测输出/prediction/predict_long_v2_6.csv')
pred['dt'] = pd.to_datetime(pred['datetime'])

# 2. 验证表
val = pd.read_csv('1-2负荷预测输出/validation/validation_hourly_long_v2_6.csv')

print("=" * 70)
print("【根因1】夜间预测完全没有用户区分度")
print("=" * 70)
night = val[val['hour'].isin([1,2,3,4])]
print(f"夜间(1-4h) 预测值分布: min={night['final_pred_net_load'].min():.0f}kW max={night['final_pred_net_load'].max():.0f}kW std={night['final_pred_net_load'].std():.0f}kW")
print(f"夜间(1-4h) 实际值分布: min={night['actual_load'].min():.0f}kW max={night['actual_load'].max():.0f}kW std={night['actual_load'].std():.0f}kW")
print(f"→ 预测std/实际std = {night['final_pred_net_load'].std()/night['actual_load'].std():.1%} (模型只捕捉了这么少的差异)")

print()
print("=" * 70)
print("【根因2】按小时看：预测值标准差vs实际标准差")
print("=" * 70)
print(f"{'小时':<6} {'预测std':>8} {'实际std':>8} {'比值':>8}")
for h in range(0,24):
    hv = val[val['hour']==h]
    ps = hv['final_pred_net_load'].std()
    as_ = hv['actual_load'].std()
    ratio = ps/as_ if as_>0 else 0
    print(f"  {h:>2}:00  {ps:>8.0f}  {as_:>8.0f}  {ratio:>7.1%}")

print()
print("=" * 70)
print("【根因3】lag特征是否真的区分了用户？")
print("=" * 70)
# 检查预测长表中每个用户1:00的lag特征
for uid in ['ND-GY-F-001','QZ-JG-001','FZ-SY-F-001','PT-QK-Z-001']:
    u = pred[pred['用户编号']==uid]
    if u.empty: continue
    name = u['用户名称'].iloc[0]
    h1 = u[u['dt'].dt.hour==1]
    if h1.empty: continue
    r = h1.iloc[0]
    is_pv = r.get('是否有光伏_flag',0)
    cap   = r.get('光伏容量(MW)',0)
    print(f"\n  {name[:15]} PV={is_pv} 容量={cap}MW:")
    for f in ['load_lag_24','load_lag_48','load_lag_168','load_roll_mean_24','load_same_hour_mean_3d']:
        v = r.get(f, np.nan)
        print(f"    {f}: {v:.0f}" if pd.notna(v) else f"    {f}: NaN")

print()
print("=" * 70)
print("【根因4】训练数据中用户差异有多大？")
print("=" * 70)
train = pd.read_csv('1-2负荷预测输出/processed/train_dataset_hourly_v2_6.csv')
train['dt'] = pd.to_datetime(train['datetime'])
recent = train[train['dt']>='2026-06-01']
for uid in ['ND-GY-F-001','QZ-JG-001']:
    u = recent[recent['用户编号']==uid]
    if u.empty: continue
    name = u['用户名称'].iloc[0]
    night = u[u['dt'].dt.hour.isin([1,2,3,4])]
    print(f"\n  {name[:15]} 6月夜间 load(total_load) 实际:")
    print(f"    mean={night['load'].mean():.0f}kW std={night['load'].std():.0f}kW min={night['load'].min():.0f}kW max={night['load'].max():.0f}kW")

print()
print("=" * 70)
print("【结论】")
print("=" * 70)
print("问题: 训练时用户特征差异巨大(1~1200kW)，但预测时所有用户得到接近的lag值")
print("原因: 历史total_load中PV用户夜间也有700+KW，但预测lag回退机制取到的是最近几个点")
print("      这些点恰好都是低值，导致lag特征不能反映用户真实模式")
print("修复方向: lag应使用'同星期几同小时'的历史中位数，而非简单的offset回退")
