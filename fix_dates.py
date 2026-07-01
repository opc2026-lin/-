#!/usr/bin/env python3
"""智能日期修复：对批量日期 "2026-07-01" 的笔记，用 git 首次提交日期替换。
回退：非 git 追踪文件用文件修改时间。不触碰已有个性化日期的笔记。"""
import os, re, subprocess, yaml
from pathlib import Path
from datetime import datetime

VAULT = Path("D:/opc-ai知识库")
BULK_DATE = "2026-07-01"
SKIP_DIRS = {'.git', '.obsidian', '.claude', '.claudian', 'TALOS', 'node_modules', '__pycache__'}

# 缓存 git 文件日期，避免重复调用 git
_git_date_cache: dict[str, str | None] = {}

def _get_git_first_date(fpath: Path) -> str | None:
    """获取文件的首次 git 提交日期 (YYYY-MM-DD)"""
    rel = str(fpath.relative_to(VAULT)).replace('\\', '/')
    if rel in _git_date_cache:
        return _git_date_cache[rel]

    try:
        # --diff-filter=A: 文件首次添加的提交
        result = subprocess.run(
            ['git', 'log', '--diff-filter=A', '--format=%aI', '--', rel],
            cwd=str(VAULT), capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            # 取最后一行（最早的提交）
            date_str = result.stdout.strip().split('\n')[-1][:10]
            _git_date_cache[rel] = date_str
            return date_str
    except Exception:
        pass

    # 如果 --diff-filter=A 没结果，尝试 --reverse（处理初始提交未标记为 A 的情况）
    try:
        result = subprocess.run(
            ['git', 'log', '--reverse', '--format=%aI', '--', rel],
            cwd=str(VAULT), capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            date_str = result.stdout.strip().split('\n')[0][:10]
            _git_date_cache[rel] = date_str
            return date_str
    except Exception:
        pass

    _git_date_cache[rel] = None
    return None

def _get_mtime_date(fpath: Path) -> str:
    """回退：用文件修改时间"""
    ts = os.path.getmtime(fpath)
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d')

def fix_date(fpath: Path) -> tuple[str, str] | None:
    """修复单个文件的日期。返回 (旧日期, 新日期) 若修改，否则 None。"""
    text = fpath.read_text(encoding='utf-8')

    # 提取 frontmatter
    if not text.startswith('---\n'):
        return None
    fm_end = text.find('\n---\n', 4)
    if fm_end < 0:
        return None

    fm_text = text[4:fm_end]
    try:
        fm = yaml.safe_load(fm_text) or {}
    except:
        return None

    old_date = fm.get('date', '')
    if not old_date or old_date != BULK_DATE:
        return None  # 不是批量日期，跳过

    # 获取真实日期
    new_date = _get_git_first_date(fpath)
    if not new_date:
        new_date = _get_mtime_date(fpath)

    if new_date == BULK_DATE:
        return None  # 没有更好的日期

    # 替换 frontmatter 中的 date 行
    new_fm_text = re.sub(
        r'^date:\s*".*?"\s*$',
        f'date: "{new_date}"',
        fm_text,
        flags=re.MULTILINE
    )

    new_text = '---\n' + new_fm_text + '\n---' + text[fm_end + 4:]
    fpath.write_text(new_text, encoding='utf-8')

    return (old_date, new_date)

def main():
    fixed = 0
    skipped_personal = 0
    unchanged = 0

    for root, dirs, files in os.walk(VAULT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
        for f in files:
            if not f.endswith('.md'):
                continue
            fpath = Path(root) / f
            result = fix_date(fpath)
            if result:
                old, new = result
                rel = str(fpath.relative_to(VAULT))
                print(f'  ✓ {rel}: {old} → {new}')
                fixed += 1

    # 统计跳过的情况
    for root, dirs, files in os.walk(VAULT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
        for f in files:
            if not f.endswith('.md'):
                continue
            fpath = Path(root) / f
            text = fpath.read_text(encoding='utf-8')
            if text.startswith('---\n'):
                fm_end = text.find('\n---\n', 4)
                if fm_end > 0:
                    try:
                        fm = yaml.safe_load(text[4:fm_end]) or {}
                        d = fm.get('date', '')
                        if d and d != BULK_DATE:
                            skipped_personal += 1
                        elif d == BULK_DATE:
                            unchanged += 1
                    except:
                        pass

    print(f'\n修复: {fixed} 篇')
    print(f'保留个性化日期: {skipped_personal} 篇')
    print(f'未能修复（批量日期无 git 历史）: {unchanged} 篇')

if __name__ == '__main__':
    main()
