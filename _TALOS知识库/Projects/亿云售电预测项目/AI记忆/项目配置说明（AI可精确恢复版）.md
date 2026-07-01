---
title: 项目配置说明（AI可精确恢复版）
tags: [talos, yiyun, source]
---

## 原文

��Ŀ����˵����AI�ɾ�ȷ�ָ��棩
0. ��Ŀ����
��Ŀ����ҵ�û�Сʱ����Ԥ��
��ǰ�ص㷽�򣺵��û�ר�ģ
��ǰ�ص���󣺸��������²��ϿƼ��ɷ����޹�˾
Ԥ��Ŀ�꣺δ��ĳʱ�������Сʱ����
�����ʽ����������
����������
����
1:00 ~ 24:00
�ϼ�
1. ����Ŀ¼�ṹ
Python

BASE_DIR/
��
���� input/
��  ���� user_master/
��  ��  ���� 01_�û���������.csv
��  ���� weather/
��  ��  ���� ���·�Сʱ�����ļ�.xlsx/csv
��  ��  ���� ע�ⲻҪ�� ~$.xlsx ��ʱ�ļ�
��  ���� load/
��     ���� �û�A.xlsx
��     ���� �û�B.xlsx
��     ���� ...
��
���� output/
��  ���� processed/
��  ���� model/
��  ���� prediction/
��  ���� validation/
��  ���� analysis/
��  ���� logs/
��
���� ���ű�.py
2. �������ݹ淶
2.1 ��������
�ļ�·����

Python

input/user_master/01_�û���������.csv
�����ֶΣ�

�û����
�û�����
������
������
�û�����
�Ƿ��й��
˵����

�û����� ����ƥ�为���ļ��ļ���
������/������ ����ƥ������
2.2 �û������ļ�
Ŀ¼��

Python

input/load/
����

һ���û�һ�� Excel �ļ�
�ļ���������ƥ���������е� �û�����
һ���ļ���� sheet
sheet �����ϸ�Ϊ��
25.2
25.3
26.4
26.5
�ȸ�ʽ
��ͷ���������У�

����������
����
1:00 ~ 24:00
�ϼ�
˵����

24:00 �������� 00:00
���ݵ�λ��1 = 1000��
2.3 Сʱ�����ļ�
Ŀ¼��

Python

input/weather/
����

�����Ƕ���ļ������£�
֧�� xlsx/xls/csv
������ԣ�
Python

~$.xlsx
���� Excel ��ʱ���ļ�

�����ֶΣ�

����
ʱ��
����
�¶�
ʪ��
�̲�����
��ѡ����ˮ�����١���ѹ��������¶�㡢����������
3. ����ƥ���߼�������ʹ�������棩
3.1 ����ԭ��
��������ѵ�� / Ԥ�� / ��֤�汾��Ĭ�϶������������棬���ܻ��˵��ɰ档

3.2 ������׼������
���������ر�׼��
ʹ�ã�

Python

normalize_region_name()
���ã�

ȥ�ո�
ȥ��ĩβ������׺��
��
��
��
���磺

��¥�� �� ��¥
������ �� ����
����������׼��
������ region �Ȳ�ɣ�

��
����
Ȼ������Ҳ�ߣ�

Python

normalize_region_name()
3.3 ƥ�����ȼ�
��һ�����ϸ�ƥ��
����

Python

["������_norm", "������_norm", "datetime"]
�ڶ��������м��ۺϻز�
�������Сʱƥ�䲻����

��ֵ�У���ͬ��ͬСʱ���ֵ
����У���ͬ��ͬСʱȡ����
�������ã�

Python

groupby(...).first()
��Ϊ���������������Ⱦ��

3.4 ����ƥ��㼶�ֶ�
���뱣���ֶΣ�

Python

weather_match_level
����ֵ��

district_exact
city_agg
��;��

ѵ�����������ƥ������
��֤ʱ�ɰ�����ƥ��㼶��������
3.5 ѵ��ʱ����������
ѵ���׶Σ�

��ĳ����һСʱ�ؼ�����ȱʧ
�������޳�
�ؼ��ֶ����٣�

Python

temperature
ͨ�������ɣ�

Python

weather_day_complete
4. ���ýű����
4.1 ���û�ѵ���ű�
�Ƽ�������

Python

01_train_single_user.py
���ã�

��ȡĿ���û�����
�ϲ�����
����Сʱ��ѵ������
ѵ�����û�ģ��
����ģ�͡�����Ԫ���ݡ���ʷ���ݡ�����
�ű������ؼ����ã�

Python

TARGET_USER_NAME
PREDICT_START
PREDICT_END
TRAIN_MONTHS
BIAS_LOOKBACK_DAYS
ѵ���������

Python

output/model/
output/processed/
output/prediction/
4.2 ���û�Ԥ��ű�
�Ƽ�������

Python

02_predict_single_user.py
���ã�

��ȡ���û�ģ��
��ȡ��ʷ����
��ȡ����
����Ԥ��Ǽ�
�ݹ�Ԥ��Сʱֵ
������� / ����
��Ҫ��ȡ��

Python

output/model/single_user_model_*.pkl
output/model/single_user_feature_meta_*.pkl
output/model/single_user_run_config_*.csv
output/processed/single_user_history_*.csv
4.3 ���û���֤�ű�
�Ƽ�������

Python

03_validate_single_user.py
���ã�

��ȡԤ����
��ȡʵ��ֵ
�������ָ��
��������Ա�
����ֲ����
4.4 ���û��ռ������ű�
�Ƽ�������

Python

04_analyze_single_user_daily.py
���ã�

�����û�Сʱ���ɾۺϳ��ռ�����
�۲죺
���ܸ���
�����ܸ���
ҹ���ܸ���
��ֵ
�վ�ֵ
�ڼ���
������ͳ��
�����ж��Ƿ�������� low_day / mid_day / high_day
���Ŀ¼��

Python

output/analysis/
5. ���û��ű�����߱��ĺ����嵥
5.1 ѵ���ű� 01_train_single_user.py ���躯��
����
log
normalize_text
normalize_region_name
safe_read_table
convert_yes_no
clean_col_name
extract_city_district
parse_sheet_yy_m
in_train_sheet_range
�������븺��
load_user_master
normalize_load_sheet
parse_one_load_sheet
load_single_user_load
�ڼ�����ʱ������
add_holiday_features
add_time_behavior_features
����Ȩ��
add_recency_weight
add_time_segment_weight
add_special_day_weight
����
hourly_weather_column_mapper
looks_like_hourly_weather_columns
smart_read_hourly_weather_file
load_hourly_weather
merge_load_weather_hourly
����������ѵ��
create_train_features
get_feature_list
prepare_matrix
train_regressor
export_feature_importance
export_train_metrics
main
5.2 �����ű� 04_analyze_single_user_daily.py ���躯��
log
normalize_text
normalize_region_name
safe_read_table
clean_col_name
extract_city_district
load_user_master
normalize_load_sheet
parse_one_load_sheet
load_single_user_hourly
add_holiday_features
add_time_behavior_features
hourly_weather_column_mapper
looks_like_hourly_weather_columns
smart_read_hourly_weather_file
load_hourly_weather
merge_user_weather
build_daily_profile
export_analysis_outputs
main
6. ��ǰҵ���жϣ�����Ҫ��
6.1 ���ݵ�λ
Python

1 = 1000��
���ԣ�

load = 100 ���� 100,000 ��
��������ֵ�����ʱ��Ҫ��������⡣

6.2 ��ǰ�ص����
Python

���������²��ϿƼ��ɷ����޹�˾
���ǵ�ǰר���������

6.3 ��ǰ��Ҫ����
������������ռ��������֣�

daytime_total_load �ֲ�ǳ�����
�������Եģ�
low_day
mid_day
high_day
˵����

����û��ʺ��� ���������ͣ�����СʱԤ�⡣

6.4 ��ǰ�Ƽ�·��
�����������ȼ�����

ͳһȫ��ģ��
ֱ��Сʱ�ع�
ǿ�й���ֽ�
�������ߣ�

���û� V5��������ʶ�� + СʱԤ��
7. ����������ԭ��
�����������أ�

7.1 �̶��ļ���
��Ҫÿ�ΰ汾����������֤����ļ�����
���ֶ����ݶԱȼ��ɡ�

7.2 ���û��������
�Ƽ�ͳһ����

Python

single_user_xxx_{SAFE_USER_NAME}.csv
single_user_xxx_{SAFE_USER_NAME}.xlsx
8. ��δ��ֻҪ�����ҵĹؼ���
�������淢��Щ����Ӧ���ָ̻������ģ�

��ҵ�û�Сʱ����Ԥ��
����������
���м��ۺϻز�
���ر�׼��
���û���ģ
���������²��ϿƼ��ɷ����޹�˾
���û��ռ�����
low_day / mid_day / high_day
V5��������ʶ�� + СʱԤ��
9. ��ǰ���ùؼ�������
��Щ�Ǻ����ű�������޸ĵģ�

Python

TARGET_USER_NAME
PREDICT_START
PREDICT_END
TRAIN_MONTHS
BIAS_LOOKBACK_DAYS
���δ���������Թ����ط����������У�

Python

PV_RADIATION_ZERO_THRESHOLD
PV_EFFECT_CAP_RATIO
����ǰ���û�������ʱ�������á�

�����Ը�⣬��һ���ҿ���ֱ�Ӽ����������ߣ�

01_train_single_user_v5.py
Ҳ������ʽ��ʼ����

���û������ͷ���
СʱԤ��ģ�͡�