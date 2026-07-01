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
    text = fpath.read_text(encoding='utf-8')
    if text.startswith('---\n'):
        fm_end = text.find('\n---\n', 4)
        if fm_end > 0:
            body = text[fm_end+4:].lstrip('\n')
        else:
            body = text
    else:
        body = text
    tag_str = ', '.join(tags)
    fm = f'---\ntags: [{tag_str}]\n---\n'
    fpath.write_text(fm + body, encoding='utf-8')

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

print("Step 3: 建双链...")
tag_index = defaultdict(list)
for title, info in notes.items():
    for t in info['tags']:
        tag_index[t].append(title)

links_added = 0
for title, info in notes.items():
    if not info['tags']: continue
    fpath = VAULT / info['dir'] / info['file']
    if not fpath.exists(): continue  # 跳过不存在的路径
    text = fpath.read_text(encoding='utf-8')
    scores = defaultdict(int)
    for t in info['tags']:
        for other in tag_index[t]:
            if other == title: continue
            w = 3 if notes[other]['dir'] == info['dir'] else 1
            scores[other] += w
    top5 = sorted(scores.items(), key=lambda x: -x[1])[:5]
    if not top5: continue
    text = re.sub(r'\n\n---\n\n## 双链笔记\n\n.*$', '', text, flags=re.DOTALL)
    new_links = []
    for ot, sc in top5:
        od = notes[ot]['dir']
        new_links.append(f"- [[{ot}]]" if od == info['dir'] else f"- [[{od}/{ot}]]")
    text = text.rstrip() + '\n\n---\n\n## 双链笔记\n\n' + '\n'.join(new_links) + '\n'
    fpath.write_text(text, encoding='utf-8')
    links_added += 1
print(f"  已建双链 {links_added} 篇")

print("Step 4: 重建索引...")
for d in ['综合能源', 'AI知识库', '个人笔记', '售电业务', 'Insights']:
    dp = VAULT / d
    if not dp.exists() or d not in [n.get('dir','') for n in notes.values()]: continue
    entries = [(t, i['tags'], f) for t, i in notes.items() if i['dir'] == d]
    by_tag = defaultdict(list)
    for t, tags, f in entries:
        for tg in list(tags)[:3]: by_tag[tg].append((t, f))
    tc = Counter()
    for _, tags, _ in entries:
        for tg in tags: tc[tg] += 1
    top = tc.most_common(6)
    idx = f'# {d} · 索引\n\n> 共 {len(entries)} 篇\n\n## 热门标签\n\n'
    idx += ' '.join(f'`#{t}`({c})' for t,c in top) + '\n\n## 按标签浏览\n\n'
    for tag, items in sorted(by_tag.items(), key=lambda x: -len(x[1])):
        idx += f'### {tag}\n\n'
        for t, f in items[:8]: idx += f'- [[{t}]]\n'
        if len(items) > 8: idx += f'- ... 等 {len(items)} 篇\n'
        idx += '\n'
    (dp / 'index.md').write_text(idx, encoding='utf-8')
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
