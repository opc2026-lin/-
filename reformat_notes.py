#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量格式化脚本：将综合能源和 AI知识库的笔记统一改写为收件箱视频笔记模板格式。
只处理有正文的 .md 文件，仅元数据的文件引用不动。
"""

import os, re, sys
from pathlib import Path
from datetime import datetime

VAULT = Path("D:/opc-ai知识库")
TARGET_DIRS = ["综合能源", "AI知识库"]

def extract_media_id(content):
    m = re.search(r"media_id: `([^`]+)`", content)
    return m.group(1) if m else ""

def extract_source(content):
    m = re.search(r"来源: (.+)", content)
    return m.group(1).strip() if m else "IMA 知识库"

def has_content(content):
    """判断是否有正文（非仅元数据）"""
    body = re.sub(r'^# .+', '', content).strip()
    body = re.sub(r'^>.*$', '', body, flags=re.M).strip()
    body = re.sub(r'^-\s*(📝|📄|🖼️|📦|💬|🎙️|🗺️|🔗|🆔|📎).*$', '', body, flags=re.M).strip()
    body = re.sub(r'^\[.+\]\(.+\)$', '', body, flags=re.M).strip()
    body = body.strip()
    return len(body) > 200

def reformat(content, filename):
    """将笔记内容改写为统一模板"""
    lines = content.split('\n')

    # 提取标题（第一行 # 开头）
    title = ""
    body_start = 0
    for i, ln in enumerate(lines):
        if ln.startswith('# ') and not ln.startswith('## '):
            title = ln[2:].strip()
            body_start = i + 1
            break
    if not title:
        title = filename.replace('.md', '')

    # 提取元数据
    mid = extract_media_id(content)
    source = extract_source(content)

    # 提取正文（去掉元数据行）
    body_lines = []
    for ln in lines[body_start:]:
        s = ln.strip()
        if s.startswith('> 来源:') or s.startswith('> Source:'):
            continue
        if re.match(r'^-\s*(📝|📄|🖼️|📦|💬|🎙️|🗺️|🔗|🆔|📎)', s):
            continue
        if re.match(r'^\[.+\]\(.+\)$', s) and '在 IMA' in s:
            continue
        body_lines.append(ln)

    body = '\n'.join(body_lines).strip()

    # 尝试识别已有的结构分段
    # 查找"核心论点"、"角度"、"总结"等关键词
    summary = ""
    questions = ""
    transcript = body  # 默认全部作为原文

    # 尝试拆分：找"思考问题"或"问题1"等标记
    q_match = re.search(r'(二[、.][\s\S]*?思考[\s\S]*?(问题|题)[\s\S]*?\n)', body)
    if not q_match:
        q_match = re.search(r'(问题\s*\d[：:][\s\S]*?)(?=三[、.]|四[、.]|\Z)', body)

    if q_match:
        q_start = q_match.start()
        main_body = body[:q_start].strip()
        questions = body[q_start:].strip()
    else:
        main_body = body

    # 尝试从正文提取核心观点部分
    summary = main_body[:500] if len(main_body) > 500 else main_body

    # 构建统一模板
    now = datetime.now().strftime("%Y-%m-%d")

    md = f"""# {title}

## 来源信息

| 项目 | 内容 |
|------|------|
| **来源** | {source} |
| **media_id** | `{mid}` |
| **整理日期** | {now} |

---

## 一、核心观点与总结

### 核心论点

{summary[:300]}…

> 📌 完整总结待 AI 深度整理。以下为原文关键要点。

### 核心要点

{_extract_key_points(body)}

---

## 二、联系实际的思考题

{_extract_questions(questions) if questions else _default_questions(title)}

---

## 三、原文

{transcript}

---

*笔记由 AI 从 IMA 知识库迁移并整理，内容基于原文提取，仅供参考。*
"""
    return md

def _extract_key_points(body):
    """从正文提取关键要点行"""
    points = []
    for ln in body.split('\n'):
        s = ln.strip()
        # 匹配 "角度一"、"角度二"、"第X点" 等
        if re.match(r'^(角度[一二三四五六七八九十]|第[一二三四五六七八九十\d]+[点步]|核心|关键)', s):
            points.append(f"- **{s[:60]}**")
        # 匹配 "1." "2." 开头
        elif re.match(r'^\d+[\.、）)]\s*\*\*', s):
            points.append(f"- {s[:80]}")
    if not points:
        # 取前 5 段非空行
        paras = [p.strip() for p in body.split('\n\n') if p.strip() and len(p.strip()) > 20]
        for p in paras[:5]:
            points.append(f"- {p[:100]}…")
    return '\n'.join(points[:8]) if points else "- 待整理"

def _extract_questions(questions_text):
    """清理已有的思考题"""
    lines = questions_text.strip().split('\n')
    cleaned = []
    for ln in lines:
        s = ln.strip()
        if s and len(s) > 10:
            cleaned.append(s)
    return '\n\n'.join(cleaned[:10]) if cleaned else _default_questions("")

def _default_questions(title):
    return f"""1. **{title[:30]}中的核心观点如何应用到你的实际工作？**请结合具体场景分析。

2. **如果你来执行文中的方案，会遇到哪些障碍？**列出 3 个最可能的卡点及应对策略。

3. **文中的结论是否存在反例或边界条件？**批判性地思考哪些场景下这些经验可能不适用。"""

def main():
    total = 0
    for dir_name in TARGET_DIRS:
        d = VAULT / dir_name
        if not d.exists():
            print(f"  ⚠️ 目录不存在: {dir_name}")
            continue

        count = 0
        for f in sorted(os.listdir(d)):
            if not f.endswith('.md') or f == 'index.md':
                continue
            fpath = d / f
            content = fpath.read_text(encoding='utf-8')

            if not has_content(content):
                continue

            try:
                new_content = reformat(content, f)
                fpath.write_text(new_content, encoding='utf-8')
                count += 1
            except Exception as e:
                print(f"  ❌ {f}: {e}")

        print(f"✅ {dir_name}: 格式化 {count} 篇")
        total += count

    print(f"\n🏁 共处理 {total} 篇笔记")

if __name__ == "__main__":
    main()
