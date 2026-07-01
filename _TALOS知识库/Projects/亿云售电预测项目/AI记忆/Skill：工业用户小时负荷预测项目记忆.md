---
title: Skill：工业用户小时负荷预测项目记忆
tags: [talos, yiyun, source]
---

## 原文

Skill����ҵ�û�Сʱ����Ԥ����Ŀ����
1. ��ĿĿ��
�� ��ҵ�û�Сʱ����Ԥ�⣬�����ǣ�

���룺�û����ɡ��û���������ÿСʱ����
�����ָ��Ԥ�������ڵ� ÿСʱ����Ԥ��
�����ʽ���ȱ���Ϊ ��������ԭʼ�û����ı����һ�£�
����������
����
1:00 ~ 24:00
�ϼ�
2. ���ݽṹ
2.1 �û���������
һ���û�һ�� Excel �ļ�
�ļ���ƥ�����������е� �û�����
һ���ļ���� sheet
sheet �����ϸ�ʹ�ã�
25.2
25.3
26.4
26.5
����ʽ
2.2 ���ɱ��ṹ
�У�
����������
����
1:00 ~ 24:00
�ϼ�
24:00 ������ 00:00 ����
2.3 �û���������
�ֶι̶���

�û����
�û�����
������
������
�û�����
�Ƿ��й��
2.4 ��������
ʹ�� ÿСʱ��������
�ؼ��ֶ����ٰ�����

����
ʱ��
����
�¶�
ʪ��
�̲�����
�����ֶ��罵ˮ�����١���ѹ�������ȿ�ѡ
����ϲ���ʽ��

�� ������/������ + datetime �ϲ�
������ȱʧ�����˻����м�ƥ��
��ĳ��Сʱ����������
ѵ��ʱ���ɺ��Ը���
Ԥ��ʱ���������첻Ԥ�������ֵ
3. ��ǰ��ģ����
3.1 �ѳ��Թ�
ͳһ LightGBM �ع�
V2�����60��ѵ�� + ���ڻ������� + �����������
V3���й��/�޹��������/�ǰ����ģ��
V2��Ȩ�棺��2������ + ʱ��˥��Ȩ�� + �����Ȩ�� + �ڼ��ո�Ȩ��
V2.5���͸���״̬ʶ��棨�͸�����ֵ <50��
V2.6���͸���״̬ʶ������ð棨��ֵ�ͷ�����ֵ�ɵ���
3.2 ��ǰ�ж�
������Ȩѵ����Ч���� MAE / RMSE
�� ���� MAPE �ܸ�
�������⼯���ڣ�
����͸���״̬ʶ����
<20��20~50��50~100 ��Щ��������
�߸��������� >=200���Ѿ���Կ���
4. ��ǰ���·��
��ǰ�Ƽ�����ʹ�� V2.6���͸���״̬ʶ��棬��ʹ�õ͸����޷�������

4.1 V2.6 ����˼·
���׶�ģ�ͣ�

��һ��������
Ԥ���Сʱ�Ƿ�Ϊ�͸���״̬��

l
o
a
d
<
L
O
W
_
L
O
A
D
_
T
H
R
E
S
H
O
L
D
load<LOW_LOAD_THRESHOLD
�ڶ�������ģ�ͻع�
������Ϊ�͸��� �� �ߵ͸��ɻع�ģ��
���� �� ����ͨ�ع�ģ��
5. ��ǰ V2.6 ���÷�ʽ
�ű�����ͳһ���ã�

Python

PREDICT_START = "2026-05-01 00:00:00"
PREDICT_END = "2026-06-01 00:00:00"   # ����ҿ�
TRAIN_MONTHS = 24

LOW_LOAD_THRESHOLD = 80
LOW_LOAD_PROBA_THRESHOLD = 0.40
����
Ԥ�����䣺��������ã���һ�������£������Ǽ���
ѵ�����䣺
TRAIN_END = PREDICT_START
TRAIN_START = PREDICT_START - TRAIN_MONTHS
Ԥ������ʹ�� ����ҿ�
����԰�������ʽ����
6. ��ǰ�ű���ϵ
6.1 ѵ��
01_train_v2_6.py
���ã�

�Զ����� PREDICT_START �� TRAIN_MONTHS ȷ��ѵ������
ѵ�� 3 ��ģ�ͣ�
low_load_classifier_v2_6.pkl
low_load_regressor_v2_6.pkl
normal_load_regressor_v2_6.pkl
����Ԫ���ݣ�
feature_meta_classifier_v2_6.pkl
feature_meta_low_reg_v2_6.pkl
feature_meta_normal_reg_v2_6.pkl
�����������ã�
run_config_v2_6.csv
6.2 Ԥ��
02_predict_v2_6.py
���ã�

��ȡ run_config_v2_6.csv
��Ԥ�����乹���Ǽ�
��Сʱ�����ϲ�
�ݹ鹹����ʷ����
�����͸��ɷ��࣬�ٷ�ģ�ͻع�
�����
������predict_long_v2_6.csv
�������û���_v2_6.xlsx
6.3 ��֤
03_validate_v2_6.py
���ã�

��ȡԤ������ʵ��ֵ
��ȡ predict_long_v2_6.csv
�����
����ָ��
����ר��ָ��
����ʵֵ�ֲ�ָ��
�͸���ʶ��ʹ�����
ÿ�û�����
�������ܿ���
7. ��ǰ������ϵ
7.1 ʱ������
month
day
hour
weekday
is_weekend
is_workday
is_daytime_8_19
is_workhour
is_morning_ramp
is_lunch_time
is_evening_peak
time_segment
hour_sin/hour_cos
weekday_sin/weekday_cos
7.2 �ڼ�������
is_holiday
holiday_name
is_adjust_workday
is_real_restday
is_month_start
is_month_end
is_before_holiday
is_after_holiday
7.3 ��������
temperature
rainfall
wind_speed
pressure
humidity
visibility
cloud
dew_point
shortwave_radiation
air_quality
cooling_degree
heating_degree
7.4 ���ڻ�������
load_lag_24
load_lag_48
load_lag_168
load_same_hour_mean_3d
load_same_hour_mean_7d
load_same_weekday_hour_mean_4
load_same_weekday_hour_mean_8
workday_same_hour_mean_5
restday_same_hour_mean_5
load_roll_mean_24
load_roll_std_24
load_roll_mean_168
recent_workhour_mean_3d
recent_workhour_mean_7d
7.5 �����������
��Ȼ��ǰ�ص��Ȳ������������������Ա�����

pv_radiation_effect
pv_temp_effect
pv_temp_radiation_effect
pv_daytime_radiation
pv_workhour_radiation
8. ��ǰ��֤�ص�
��ǰ���ע��

8.1 ����ָ��
MAE
RMSE
MAPE
8.2 ����ר��
���� 8:00~19:00 �� MAE/RMSE/MAPE
8.3 ����ʵֵ�ֲ�
�ص��ע��

<20
20~50
50~100
100~200
>=200
8.4 �͸���ʶ�����
�ص㿴��

tp
fp
tn
fn
pred_low_ratio
actual_low_ratio
9. ��ǰ�ѵõ�����Ҫ����
�߸�������>=200���Ѿ��ӽ�����
�е͸�������Ȼ����Ҫ�����Դ
�͸��ɷ�������ƫ���أ�����©��
V2.6 �ȼ��޷���ֵ�ü�����
�������ټ�����ͳһ�޷����������Ǽ����Ż���
LOW_LOAD_THRESHOLD
LOW_LOAD_PROBA_THRESHOLD
�͸��ɷ�������
�͸��ɻع�ģ��
10. �Ժ��������Ż������ȼ�����
���� LOW_LOAD_THRESHOLD���� 80 / 100��
���� LOW_LOAD_PROBA_THRESHOLD���� 0.40 / 0.35��
���͸����ٻ����Ƿ�����
�ٿ��͸����� MAPE �Ƿ��½�
����ٿ����Ƿ�Ҫ�������ʽ�Ĺ����ģ
11. ����ָ�������
�Ժ���������˵��Щ����Ӧ���Զ��ָ������Ŀ�����ģ�

��ҵ�û�Сʱ����Ԥ��
�û��������� + ÿСʱ���� + �������
V2.6 �͸���״̬ʶ���
Ԥ����������ҿ�
ѵ�������� = Ԥ�⿪ʼ��
ѵ���·���������
�����������
�ص��ע���� 8~19 ����ʵֵ�ֲ����