#!/usr/bin/env python3
"""
政策采集自动化主脚本 v3 - Windows本地版
- 输出直接写入 D:\亿云能源科技售电交易数据库\相关政策文件
- 每周一自动执行 / 手动运行强制采集
- 采集 → 下载PDF → 生成汇编
"""

import sys, os, json, logging
from pathlib import Path
from datetime import datetime

# 目标输出路径（用户本地D盘）
TARGET_DIR = Path(r"D:\亿云能源科技售电交易数据库\相关政策文件")
TARGET_DIR.mkdir(parents=True, exist_ok=True)

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from scrapers.collector import PolicyScraper
from scrapers.assembler import generate_assembly, generate_assembly_markdown

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(PROJECT_ROOT / 'logs' / 'main.log', encoding='utf-8'),
    ]
)
logger = logging.getLogger(__name__)

STATE_FILE = PROJECT_ROOT / "output" / "data" / "schedule_state.json"


def load_schedule_state():
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'last_run': None, 'runs': []}


def save_schedule_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def should_run_today():
    state = load_schedule_state()
    today = datetime.now()
    weekday = today.weekday()

    if weekday == 0:
        return True, state

    if state.get('last_run'):
        last = datetime.fromisoformat(state['last_run'])
        if (today - last).days >= 7:
            logger.info("检测到遗漏采集（超过7天未运行），执行补采")
            return True, state

    if 'FORCE_RUN' in os.environ:
        return True, state

    return False, state


def copy_to_target(xlsx_path, md_path):
    """将生成的汇编文件复制到用户D盘目标路径"""
    import shutil
    try:
        shutil.copy2(xlsx_path, TARGET_DIR / "政策汇编_最新.xlsx")
        shutil.copy2(md_path, TARGET_DIR / "政策汇编_最新.md")
        logger.info(f"✅ 已复制到: {TARGET_DIR}")
        return True
    except Exception as e:
        logger.warning(f"⚠ 复制到目标路径失败: {e}")
        return False


def run_collection():
    logger.info("=" * 60)
    logger.info(f"政策采集任务启动 - {datetime.now():%Y-%m-%d %H:%M:%S}")
    logger.info(f"目标输出: {TARGET_DIR}")
    logger.info("=" * 60)

    try:
        logger.info("【1/3】采集政策...")
        scraper = PolicyScraper()
        scraper.scrape_all()

        logger.info("【2/3】下载PDF附件...")
        scraper.download_pdfs()

        logger.info("【3/3】生成政策汇编...")
        xlsx_path = generate_assembly(scraper.results)
        md_path = generate_assembly_markdown(scraper.results)

        # 复制到D盘目标路径
        copy_to_target(xlsx_path, md_path)

        # 更新状态
        state = load_schedule_state()
        state['last_run'] = datetime.now().isoformat()
        state['runs'].append({
            'time': state['last_run'],
            'count': len(scraper.results),
        })
        state['runs'] = state['runs'][-50:]
        save_schedule_state(state)

        logger.info("=" * 60)
        logger.info(f"✅ 任务完成: 采集 {len(scraper.results)} 条政策")
        logger.info(f"📊 Excel: {TARGET_DIR / '政策汇编_最新.xlsx'}")
        logger.info(f"📝 Markdown: {TARGET_DIR / '政策汇编_最新.md'}")
        logger.info("=" * 60)

        return {'count': len(scraper.results)}

    except Exception as e:
        logger.error(f"任务失败: {e}", exc_info=True)
        raise


if __name__ == '__main__':
    run_now, state = should_run_today()

    if run_now:
        logger.info(f"上次运行: {state.get('last_run', '从未')}")
        result = run_collection()
        print(f"\n✅ 完成: {result['count']} 条 → {TARGET_DIR}")
    else:
        today = datetime.now()
        logger.info(f"今天不是采集日（周一），跳过。上次运行: {state.get('last_run', '从未')}")
        print(f"跳过 - 今天周{today.weekday()+1}，非采集日")
