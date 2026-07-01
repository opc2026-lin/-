import pandas as pd, numpy as np, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
vdf = pd.read_csv('1-2负荷预测输出/validation/validation_hourly_long_v2_6.csv')
vdf['mape'] = np.where((vdf['actual_load']!=0)&vdf['actual_load'].notna()&vdf['final_pred_net_load'].notna(),
                        abs(vdf['final_pred_net_load']-vdf['actual_load'])/vdf['actual_load'], np.nan)

print('=== 逐用户 1:00-4:00 夜间对比 ===')
for (uid,uname), grp in vdf.groupby(['用户编号','用户名称']):
    night = grp[grp['hour'].isin([1,2,3,4])]
    a = night['actual_load'].mean(); p = night['final_pred_net_load'].mean()
    err = abs(p-a); m = np.nanmean(night['mape'])
    print(f'  {uname[:18]:<18} 实际{a:>6.0f}kW 预测{p:>6.0f}kW 误差{err:>6.0f}kW MAPE{m:>7.1%}')

print()
print('=== 日合计对比 ===')
ds = vdf.groupby(['用户编号','用户名称']).agg(act=('actual_load','sum'), pred=('final_pred_net_load','sum')).reset_index()
ds['err%'] = abs((ds['pred']-ds['act'])/ds['act'])
ds = ds.sort_values('err%')
for _, r in ds.iterrows():
    print(f'  {r["用户名称"][:18]:<18} act={r.act:>7.0f}kW pred={r.pred:>7.0f}kW err={r["err%"]:>6.1%}')

print()
# Overall daily
print(f'\n18用户日合计: 实际 {ds["act"].sum():.0f}kW, 预测 {ds["pred"].sum():.0f}kW, 误差 {abs(ds["pred"].sum()-ds["act"].sum())/ds["act"].sum():.1%}')
