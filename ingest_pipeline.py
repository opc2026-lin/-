#!/usr/bin/env python3
"""Ingest 管线：收件箱整理 → 打标签 → 建双链 → 重建索引 → 刷新 STATS"""
import os, re, subprocess, sys
from pathlib import Path
from collections import defaultdict, Counter

VAULT = Path("D:/opc-ai知识库")
INBOX = VAULT / "收件箱"
DIRS = set()
for root, dirs, files in os.walk(VAULT):
    if any(s in str(root) for s in ['.git','.obsidian','.claude','.claudian','TALOS','node_modules']):
        continue
    for f in files:
        if f.endswith('.md') and f != 'index.md':
            DIRS.add(str(Path(root).relative_to(VAULT)))

# ========== Step 1: 路由表 ==========
ROUTES = {
    '能源托管': '综合能源', '合同能源': '综合能源', '节能': '综合能源',
    '光伏': '综合能源', '储能': '综合能源', '充电桩': '综合能源', '换电': '综合能源',
    '碳': '综合能源', '售电': '售电业务', '电力': '综合能源', '电价': '综合能源',
    '电网': '综合能源', '发改': '综合能源', '国办': '综合能源', '能源局': '综合能源',
    '托管': '综合能源', '电费': '综合能源', '现货': '综合能源',
    'AI': 'AI知识库', 'Claude': 'AI知识库', 'Codex': 'AI知识库', 'Agent': 'AI知识库',
    'Skill': 'AI知识库', 'Vibe': 'AI知识库', 'Obsidian': 'AI知识库', 'LLM': 'AI知识库',
    '创业': '个人笔记', '赚钱': '个人笔记', '周报': '个人笔记', '销售': '个人笔记',
    '方法论': 'Insights', '原则': 'Insights', '框架': 'Insights',
    '视频笔记': 'AI知识库', '月度整理': '收件箱',
}

TAG_MAP = {
    '能源托管': '能源托管', '合同能源': '合同能源管理', '节能': '节能改造',
    '光伏': '光伏', '储能': '储能', '充电桩': '充换电', '换电站': '充换电',
    '碳': '双碳', '碳普惠': '碳交易', '碳交易': '碳交易', 'CCER': '碳交易',
    '售电': '售电', '电力交易': '电力交易', '电力市场': '电力交易', '电价': '电力交易',
    '虚拟电厂': '虚拟电厂', '综合能源': '综合能源',
    '医院': '公共机构', '学校': '公共机构', '空调': '暖通节能',
    '发改': '政策文件', '招标': '招投标', '投标': '招投标',
    'AI': 'AI', 'LLM': 'AI', 'Claude': 'Claude', 'Agent': 'AI Agent',
    'Skill': 'AI Skill', 'Vibe Coding': 'VibeCoding', 'Codex': 'Codex',
    'Obsidian': 'Obsidian', 'Loop': 'Loop Engineering', 'Prompt': 'Prompt',
    '创业': '创业', '商业模式': '商业模式', '销售': '销售', '投资': '投资',
}

def classify(title):
    for kw, dest in ROUTES.items():
        if kw.lower() in title.lower():
            return dest
    return '个人笔记'

def get_tags(title, content):
    text = (title + ' ' + (content or '')[:500]).lower()
    tags = set()
    for kw, tag in TAG_MAP.items():
        if kw.lower() in text: tags.add(tag)
    return sorted(tags)[:6]

def add_frontmatter(fpath, tags):
    """保留所有已有 frontmatter 字段，仅更新 tags（修复覆盖 bug）"""
    import yaml
    text = fpath.read_text(encoding='utf-8')
    existing = {}
    fm_end = 0
    if text.startswith('---\n'):
        fm_end = text.find('\n---\n', 4)
        if fm_end > 0:
            try:
                existing = yaml.safe_load(text[4:fm_end]) or {}
            except:
                pass
            fm_end += 4
        else:
            existing = {}
    else:
        existing = {}

    # 合并标签
    old_tags = existing.get('tags', [])
    if isinstance(old_tags, str):
        old_tags = [old_tags]
    existing['tags'] = sorted(set(list(old_tags) + list(tags)))

    # 重建 frontmatter
    fm = '---\n'
    for k, v in existing.items():
        if k == 'tags':
            fm += f'tags: [{", ".join(v)}]\n'
        elif isinstance(v, str):
            fm += f'{k}: "{v}"\n'
        elif isinstance(v, list):
            fm += f'{k}: [{", ".join(str(x) for x in v)}]\n'
        else:
            fm += f'{k}: {v}\n'
    fm += '---\n'

    body = text[fm_end:] if fm_end > 0 else text
    fpath.write_text(fm + body.lstrip('\n'), encoding='utf-8')

# ========== Run ==========
print("Step 1: 收件箱整理...")
moved = 0
for f in sorted(os.listdir(INBOX)):
    if f in ('index.md',) or f.startswith('月度整理_'): continue
    src = INBOX / f
    dest_dir = classify(f)
    dest = VAULT / dest_dir / f
    if dest.exists():
        src.unlink(); moved += 1; continue
    import shutil
    shutil.move(str(src), str(dest))
    moved += 1
print(f"  已处理 {moved} 个文件")

print("Step 2: 打标签...")
tagged = 0
notes = {}
# 递归收集所有笔记
for root, dirs, files in os.walk(VAULT):
    if any(s in str(root) for s in ['.git','.obsidian','.claude','.claudian','TALOS','node_modules']):
        continue
    rd = str(Path(root).relative_to(VAULT))
    for f in files:
        if not f.endswith('.md') or f == 'index.md': continue
        fpath = Path(root) / f
        text = fpath.read_text(encoding='utf-8')
        if len(text) < 100: continue
        title = f.replace('.md', '')
        if 'tags:' not in text[:100]:
            tags = get_tags(title, text)
            if tags:
                add_frontmatter(fpath, tags)
                tagged += 1
        tags_m = re.search(r'tags:\s*\[(.+?)\]', text)
        tset = set()
        if tags_m: tset = set(t.strip() for t in tags_m.group(1).split(','))
        notes[title] = {'dir': rd, 'tags': tset, 'file': f}
print(f"  已打标签 {tagged} 篇")

print("Step 3: 建双链（link_builder.py）...")
subprocess.run([sys.executable, 'link_builder.py'], cwd=str(VAULT))
print("  双链已更新")

print("Step 4: 重建索引（index_rebuilder.py）...")
subprocess.run([sys.executable, 'index_rebuilder.py'], cwd=str(VAULT))
print("  索引已更新")

print("Step 5: 刷新仪表盘...")
subprocess.run([sys.executable, 'refresh-dashboard.py', '--vault', str(VAULT)],
               cwd=str(VAULT), capture_output=True)

print("\n管线完成。运行 git commit 和 push...")
subprocess.run(['git', 'add', '-A'], cwd=str(VAULT))
subprocess.run(['git', 'commit', '-m', f'Ingest pipeline: {moved} files processed'],
               cwd=str(VAULT))
subprocess.run(['git', 'push'], cwd=str(VAULT))
print("Done!")
