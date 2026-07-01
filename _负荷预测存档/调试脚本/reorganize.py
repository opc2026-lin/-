# -*- coding: utf-8 -*-
"""
文件夹整理脚本 - 按业务逻辑重新组织目录结构
保留当前工作流水线(01_train_v2.py, 02_predict_v2.py, 1-1输入, 1-2输出)在根目录
"""
import shutil, os, sys, io
from pathlib import Path

# Fix Windows encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = Path(__file__).resolve().parent

def safe_move(src, dst_dir, dst_name=None):
    """安全移动文件/文件夹"""
    if not src.exists():
        print(f"  [跳过] 不存在: {src.name}")
        return False
    dst = dst_dir / (dst_name or src.name)
    if dst.exists():
        print(f"  [跳过] 已存在: {dst.name}")
        return False
    try:
        shutil.move(str(src), str(dst))
        print(f"  [OK] {src.name} → {dst_dir.name}/")
        return True
    except Exception as e:
        print(f"  [错误] {src.name}: {e}")
        return False

def ensure_dir(path):
    path.mkdir(parents=True, exist_ok=True)

# ========================================
# 1. 创建新目录结构
# ========================================
print("=" * 60)
print("创建新目录结构")
print("=" * 60)

dirs = [
    "_负荷预测存档/历史版本/v1第一版",
    "_负荷预测存档/历史版本/v2.5副本",
    "_负荷预测存档/调试脚本",
    "_价格预测/输入数据",
    "_价格预测/参考",
    "_交易运营/交易记录",
    "_交易运营/日滚搓申报",
    "_交易运营/复盘报告",
    "_交易运营/BUG记录",
    "_运营数据/日清分",
    "_运营数据/检验",
    "_运营数据/交易时序",
    "_运营数据/临时文件",
    "_TALOS知识库",
    "_仪表盘/talos-dashboard",
    "_政策与资料/政策汇编",
    "_政策与资料/AI参考",
    "_归档/旧负荷预测项目",
    "_归档/杂项",
]

for d in dirs:
    ensure_dir(BASE / d)
    print(f"  ✓ {d}")

# ========================================
# 2. 移动文件
# ========================================
print()
print("=" * 60)
print("移动文件到分类目录")
print("=" * 60)

# --- 负荷预测存档 ---
print("\n[负荷预测存档]")
# 原始 V2.6 脚本
for f in ["01.py", "02.py", "03.py"]:
    safe_move(BASE / f, BASE / "_负荷预测存档/历史版本", f"v2.6_{f}")

# 旧项目
safe_move(BASE / "power_forecast_project（第1次）", BASE / "_负荷预测存档/历史版本/v1第一版", "power_forecast_project_v1")
safe_move(BASE / "power_forecast_project（第1次） - 副本", BASE / "_负荷预测存档/历史版本/v2.5副本", "power_forecast_project_v2.5")

# 调试/验证脚本
for f in ["check_pred.py", "debug_pv.py", "debug_pv2.py", "verify_v2.py"]:
    safe_move(BASE / f, BASE / "_负荷预测存档/调试脚本")

# --- 价格预测 ---
print("\n[价格预测]")
safe_move(BASE / "2-1价格预测输入", BASE / "_价格预测/输入数据", "2-1价格预测输入")
safe_move(BASE / "2-2价格预测输出", BASE / "_价格预测", "输出数据")
for f in ["【第五课】电价预测.xlsx", "【第五课】电价预测_6月真实数据.xlsx"]:
    safe_move(BASE / f, BASE / "_价格预测/参考")

# --- 交易运营 ---
print("\n[交易运营]")
safe_move(BASE / "3-1交易记录", BASE / "_交易运营/交易记录", "挂牌与竞价申报数据")
safe_move(BASE / "4-1日滚搓申报", BASE / "_交易运营/日滚搓申报", "日滚撮申报数据")
safe_move(BASE / "5-1复盘报告", BASE / "_交易运营/复盘报告")

# 空目录合并
if (BASE / "4-1BUG记录").exists():
    try:
        (BASE / "4-1BUG记录").rmdir()
        print("  [OK] 删除空目录 4-1BUG记录")
    except:
        pass

# --- 运营数据 ---
print("\n[运营数据]")
safe_move(BASE / "日清分", BASE / "_运营数据/日清分", "日清分数据")
safe_move(BASE / "检验", BASE / "_运营数据/检验")
safe_move(BASE / "交易时序", BASE / "_运营数据/交易时序")
safe_move(BASE / "6.24", BASE / "_运营数据/临时文件", "系统预测_6.24")
safe_move(BASE / "目标日7-1复盘.xlsx", BASE / "_运营数据/临时文件")
safe_move(BASE / "7TGDPHXX_20260623092420_y_2026_m_06_d_23.pdf", BASE / "_运营数据/临时文件")

# 删除空txt
if (BASE / "新建文本文档.txt").exists():
    (BASE / "新建文本文档.txt").unlink()
    print("  [OK] 删除 新建文本文档.txt")

# --- TALOS知识库 ---
print("\n[TALOS知识库]")
for d in ["Identity", "System", "Projects", "Insights", "Materials", "Experience", "Workflows", "Taste-Samples", "example"]:
    safe_move(BASE / d, BASE / "_TALOS知识库")

for f in ["外脑总览.md", "Home.md", "homepage.md"]:
    safe_move(BASE / f, BASE / "_TALOS知识库")

# 嵌套同名目录
nested = BASE / "亿云能源科技售电交易数据库"
if nested.exists():
    safe_move(BASE / "亿云能源科技售电交易数据库", BASE / "_TALOS知识库", "Obsidian配置")

# --- 仪表盘 ---
print("\n[仪表盘]")
safe_move(BASE / "talos-dashboard", BASE / "_仪表盘/talos-dashboard", "主仪表盘")
safe_move(BASE / "talos-dashboard-backup-20260626-150811", BASE / "_仪表盘", "仪表盘备份")
safe_move(BASE / "dashboard.html", BASE / "_仪表盘")
safe_move(BASE / "refresh-dashboard.py", BASE / "_仪表盘")
safe_move(BASE / "TALOS部署说明.md", BASE / "_仪表盘")

# --- 政策与资料 ---
print("\n[政策与资料]")
safe_move(BASE / "相关政策文件", BASE / "_政策与资料/政策汇编", "政策汇编文件")
safe_move(BASE / "AI用", BASE / "_政策与资料/AI参考", "AI辅助文件")

# --- 归档 ---
print("\n[归档]")
safe_move(BASE / "Archive", BASE / "_归档", "系统归档")
safe_move(BASE / "杂", BASE / "_归档/杂项", "杂项文件")

# 移动可能残留的空目录
for d in ["4-1BUG记录", "__pycache__"]:
    p = BASE / d
    if p.exists():
        try: shutil.rmtree(str(p)); print(f"  [OK] 清理 {d}")
        except: pass

# ========================================
# 3. 创建导航文档
# ========================================
print()
print("=" * 60)
print("创建目录导航")
print("=" * 60)

navigation = """# 亿云能源科技售电交易数据库 - 目录导航

> 最后整理: 2026-06-29

---

## 📂 根目录（工作入口）
- `01_train_v2.py` — 负荷预测训练脚本 (V2.6)
- `02_predict_v2.py` — 负荷预测预测脚本 (V2.6)
- `1-1负荷预测输入/` — 负荷预测数据输入
- `1-2负荷预测输出/` — 负荷预测结果输出

## 📂 _负荷预测存档/
历史版本代码和调试工具
- `历史版本/v1第一版/` — 最初版本 (power_forecast_project)
- `历史版本/v2.5副本/` — V2.5 weatherfix 版本
- `历史版本/v2.6_*.py` — V2.6 原始版 (01/02/03.py)
- `调试脚本/` — 临时调试和验证脚本

## 📂 _价格预测/
电价预测相关数据和参考
- `输入数据/` — 价格预测输入 (2-1)
- `输出数据/` — 价格预测输出 (2-2)
- `参考/` — 电价预测课程参考文件

## 📂 _交易运营/
电力市场交易执行和管理
- `交易记录/` — 月度挂牌/竞价申报数据
- `日滚搓申报/` — 日滚撮申报操作数据
- `复盘报告/` — 交易复盘分析 (待填充)

## 📂 _运营数据/
日常运营相关数据
- `日清分/` — 日清分结算结果
- `交易时序/` — 中长期交易时序安排
- `临时文件/` — 系统预测、复盘等临时数据

## 📂 _TALOS知识库/
Obsidian 知识管理系统
- `Identity/` — 系统身份定义
- `System/` — 运行规则和权限
- `Projects/` — 项目管理
- `Insights/` — 业务洞察
- `Materials/` — 原始资料索引
- `Experience/` — 经验沉淀
- `Workflows/` — 工作流定义
- `外脑总览.md` — 知识库总入口
- `homepage.md` — 首页配置

## 📂 _仪表盘/
TALOS 可视化仪表盘
- `talos-dashboard/` — 仪表盘项目主目录
- `仪表盘备份/` — 上一版本备份
- `dashboard.html` — 仪表盘页面
- `refresh-dashboard.py` — 数据刷新脚本
- `TALOS部署说明.md` — 部署文档

## 📂 _政策与资料/
外部参考资料
- `政策汇编/` — 电力交易相关政策文件
- `AI参考/` — AI 辅助工作资料

## 📂 _归档/
历史归档文件
- `系统归档/` — 原始文件索引
- `杂项/` — 杂项 Excel 文件
"""

with open(BASE / "README.md", "w", encoding="utf-8") as f:
    f.write(navigation)
print("  ✓ 已创建 README.md 导航文档")

print()
print("=" * 60)
print("✅ 整理完成!")
print("=" * 60)
print(f"根目录保留: 2 个脚本 + 2 个数据目录")
print(f"新增分类目录: 8 个 (_负荷预测存档, _价格预测, _交易运营, _运营数据, _TALOS知识库, _仪表盘, _政策与资料, _归档)")
print(f"导航文档: README.md")
