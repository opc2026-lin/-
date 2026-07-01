#!/usr/bin/env python3
"""
统一格式化脚本 v2 — 将所有笔记改写为 Loop Engineering 笔记的模板格式
目标模板：来源信息表 → 一、核心观点与总结 → 二、思考题 → 三、原文/逐字稿
"""

import os, re
from pathlib import Path
from datetime import datetime

VAULT = Path("D:/opc-ai知识库")
TARGETS = ["收件箱", "综合能源", "AI知识库"]

def has_content(text):
    """正文 > 200 字符"""
    body = re.sub(r'^# .+', '', text).strip()
    body = re.sub(r'^>.*$', '', body, flags=re.M).strip()
    body = re.sub(r'^-\s*[📝📄🖼️📦💬🎙️🗺️🔗🆔📎].*$', '', body, flags=re.M).strip()
    return len(body.strip()) > 200

def extract_meta(text):
    """提取元数据"""
    meta = {}
    m = re.search(r'media_id[：:]?\s*`?([a-z]+_[^`\s\)]+)', text)
    if m: meta['media_id'] = m.group(1)
    m = re.search(r'来源[：:]\s*(.+?)(?:\n|$)', text)
    if m: meta['source'] = m.group(1).strip()
    m = re.search(r'作者[：:]\s*(.+?)(?:\n|$)', text)
    if m: meta['author'] = m.group(1).strip()
    m = re.search(r'平台[：:]\s*(.+?)(?:\n|$)', text)
    if m: meta['platform'] = m.group(1).strip()
    m = re.search(r'链接[：:]\s*[\[(]?(https?://[^\s\])]+)', text)
    if m: meta['link'] = m.group(1)
    m = re.search(r'https?://(?:www\.)?(?:v\.)?douyin\.\S+?video/(\d+)', text)
    if m: meta['douyin_id'] = m.group(1)
    m = re.search(r'iesdouyin\.com/share/video/(\d+)', text)
    if m: meta['douyin_id'] = m.group(1)
    return meta

def is_video(meta, fname):
    return bool(meta.get('douyin_id') or meta.get('platform') == 'douyin'
                or '视频' in fname or 'video' in fname.lower())

def extract_body(text):
    """提取正文：去掉标题、元数据行、已有格式化标记、相关笔记"""
    # 先去掉末尾的相关笔记
    text = re.sub(r'\n\n---\n\n## 相关笔记\n\n.*$', '', text, flags=re.DOTALL)
    # 去掉末尾的 footer
    text = re.sub(r'\n\n---\n\n\*笔记由 AI.*\*$', '', text, flags=re.DOTALL)

    lines = text.split('\n')
    body = []
    in_header = True  # 跳过已有的模板头部
    skip_count = 0

    for ln in lines:
        s = ln.strip()

        # 跳过标题
        if s.startswith('# ') and not s.startswith('## ') and skip_count == 0:
            skip_count += 1
            continue

        # 检测是否进入已有格式化模板
        if s in ['## 视频信息', '## 来源信息', '## 一、核心观点与总结',
                 '## 二、联系实际的思考题', '## 三、视频逐字稿', '## 三、原文']:
            in_header = True
            continue

        if in_header:
            # 跳过元数据表、iframe、分隔线
            if s.startswith('|') or s.startswith('<iframe') or s.startswith('---'):
                continue
            if re.match(r'^[📝📄🖼️📦💬🎙️🗺️🔗🆔📎📌]', s):
                continue
            if s.startswith('> 来源') or s.startswith('> Source') or s.startswith('> 以下逐字稿'):
                continue
            if s == '': continue
            in_header = False

        body.append(ln)

    return '\n'.join(body).strip()

def extract_questions(text):
    """提取已有的思考题"""
    qs = []
    # Try to find numbered questions
    for m in re.finditer(r'(?:###?\s*)?(?:💡\s*)?问题\s*\d[：:](.*?)(?=\n\n|\n(?:###?\s*)?(?:💡\s*)?问题\s*\d|\Z)', text, re.DOTALL):
        qs.append(m.group(0).strip())
    if qs: return '\n\n'.join(qs[:3])

    # Try ## 二 section
    m = re.search(r'## 二[、.]?\s*.*?\n(.*?)(?=\n## |\Z)', text, re.DOTALL)
    if m:
        qtext = m.group(1).strip()
        if len(qtext) > 50:
            return qtext[:2000]
    return ""

def extract_summary(text):
    """提取核心观点"""
    m = re.search(r'(?:核心[论观].*?|视频核心.*?|角度[一二三].*?)(.{100,600}?)(?=角度[二三四五六]|问题\s*\d|总结|二[、.]|三[、.]|\Z)', text, re.DOTALL)
    if m: return m.group(0).strip()[:500]
    # Fallback: first substantial paragraph
    paras = [p.strip() for p in text.split('\n\n') if len(p.strip()) > 50]
    return paras[0][:500] if paras else text[:300]

def reformat(fpath):
    """统一格式化一篇笔记"""
    text = Path(fpath).read_text(encoding='utf-8')
    if not has_content(text):
        return False

    # 跳过已格式化的（有三段式结构 + 信息表 + 音频/视频/原文）
    if ('## 来源信息' in text or '## 视频信息' in text) and '## 一、核心观点与总结' in text and '## 三、' in text:
        # 确认不是被我们自己的格式化弄坏的（检查无重复标题）
        title_count = len(re.findall(r'^## 视频信息$|^## 来源信息$', text, re.MULTILINE))
        if title_count == 1:
            return False  # already clean, skip

    fname = os.path.basename(fpath)
    meta = extract_meta(text)
    body = extract_body(text)
    video = is_video(meta, fname)
    # 从原文第一行提取真实标题
    title_m = re.match(r'^# (.+)', text)
    title = title_m.group(1).strip() if title_m else fname.replace('.md', '')

    # Build source info table
    now = datetime.now().strftime("%Y-%m-%d")
    source_table = "| 项目 | 内容 |\n|------|------|\n"
    if video:
        source_table += f"| **标题** | {title} |\n"
        if meta.get('author'): source_table += f"| **作者** | {meta['author']} |\n"
        if meta.get('douyin_id'): source_table += f"| **视频ID** | {meta['douyin_id']} |\n"
        if meta.get('platform'): source_table += f"| **平台** | {meta['platform']} |\n"
        if meta.get('link'): source_table += f"| **链接** | [{meta['link']}]({meta['link']}) |\n"
    else:
        source = meta.get('source', 'IMA 知识库')
        source_table += f"| **来源** | {source} |\n"
        if meta.get('media_id'): source_table += f"| **media_id** | `{meta['media_id']}` |\n"
        if meta.get('author'): source_table += f"| **作者** | {meta['author']} |\n"

    source_table += f"| **整理日期** | {now} |\n"

    # Iframe for douyin videos
    iframe = ""
    if meta.get('douyin_id'):
        iframe = f'<iframe src="https://open.douyin.com/player/video?vid={meta["douyin_id"]}&autoplay=0" width="100%" height="480" frameborder="0" referrerpolicy="unsafe-url" allowfullscreen style="border-radius:8px;margin-bottom:12px"></iframe>\n\n'

    # Sections
    summary = extract_summary(body)
    questions = extract_questions(text)

    # Build output
    md = f"# {title}\n\n"
    md += f"## {'视频信息' if video else '来源信息'}\n\n"
    if iframe: md += iframe
    md += source_table + "\n---\n\n"
    md += "## 一、核心观点与总结\n\n"
    md += f"### 核心论点\n\n{summary}\n\n"
    md += "### 核心要点\n\n"

    # Extract bullet points from body
    bullets = []
    for ln in body.split('\n'):
        s = ln.strip()
        if re.match(r'^(?:[一二三四五六七八九十\d]+[\.、．)）]|\*\*[^*]+\*\*[：:]|[-*]\s)', s):
            bullets.append(s[:120])
    if not bullets:
        for para in body.split('\n\n')[:5]:
            p = para.strip()
            if len(p) > 30:
                bullets.append(p[:120] + ('…' if len(p) > 120 else ''))
    md += '\n'.join(f"- {b}" for b in bullets[:8]) if bullets else "- 待整理"
    md += "\n\n---\n\n"

    if questions:
        md += f"## 二、联系实际的思考题\n\n{questions}\n\n---\n\n"
    else:
        md += f"## 二、联系实际的思考题\n\n1. 本文核心观点如何应用到你的实际工作？\n\n2. 执行本文方案会遇到哪些障碍？列出 3 个卡点。\n\n3. 文中结论是否存在反例？批判性思考。\n\n---\n\n"

    section3 = "视频逐字稿" if video else "原文"
    md += f"## 三、{section3}\n\n{body}\n\n---\n\n"
    md += f"*笔记由 AI 整理，内容基于{'视频转录' if video else '原文提取'}，仅供参考。*\n"

    Path(fpath).write_text(md, encoding='utf-8')
    return True

def main():
    total = 0
    for dir_name in TARGETS:
        d = VAULT / dir_name
        if not d.exists(): continue
        count = 0
        for f in sorted(os.listdir(d)):
            if not f.endswith('.md') or f == 'index.md': continue
            if reformat(d / f):
                count += 1
        print(f"{dir_name}: {count} 篇")
        total += count
    print(f"\n共 {total} 篇")

if __name__ == "__main__":
    main()
