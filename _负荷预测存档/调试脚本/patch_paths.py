import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

files = ['01_train_v3.py', '02_predict_v3.py', '03_validate_v3.py']

for fn in files:
    with open(fn, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replace old paths with new
    content = content.replace(
        'BASE_DIR / "input" / "user_master" / "01_用户主档案表.csv"',
        'BASE_DIR / "1-1负荷预测输入" / "用户主档案表.xlsx"')
    content = content.replace(
        'BASE_DIR / "input" / "weather"',
        'BASE_DIR / "1-1负荷预测输入" / "2.预测天气"')
    content = content.replace(
        'BASE_DIR / "input" / "load"',
        'BASE_DIR / "1-1负荷预测输入" / "1.分时段历史用电信息"')
    content = content.replace(
        'BASE_DIR / "output"',
        'BASE_DIR / "1-2负荷预测输出"')

    # Also fix WEATHER_DIR reference for historical weather in train script
    if fn == '01_train_v3.py':
        content = content.replace(
            'BASE_DIR / "1-1负荷预测输入" / "2.预测天气"',
            'BASE_DIR / "1-1负荷预测输入" / "3.真实天气"')
    if fn == '03_validate_v3.py':
        content = content.replace(
            'BASE_DIR / "1-1负荷预测输入" / "2.预测天气"',
            'BASE_DIR / "1-1负荷预测输入" / "3.真实天气"')

    with open(fn, 'w', encoding='utf-8') as f:
        f.write(content)

    # Verify
    with open(fn, 'r', encoding='utf-8') as f:
        new = f.read()
    checks = {
        'old input': 'BASE_DIR / "input"' in new,
        'old output': 'BASE_DIR / "output"' in new,
        'has 1-1输入': '1-1负荷预测输入' in new,
        'has 1-2输出': '1-2负荷预测输出' in new,
        'has xlsx': '用户主档案表.xlsx' in new,
    }
    print(f'{fn}: {checks}')
