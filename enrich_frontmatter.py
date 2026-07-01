#!/usr/bin/env python3
"""统一补充所有笔记的 YAML frontmatter 字段"""
import os, re, yaml
from pathlib import Path
from datetime import datetime

VAULT = Path("D:/opc-ai知识库")

def get_existing_fm(text):
    """提取已有 frontmatter"""
    if not text.startswith('---\n'):
        return {}, 0
    end = text.find('\n---\n', 4)
    if end < 0:
        return {}, 0
    try:
        fm = yaml.safe_load(text[4:end]) or {}
    except:
        fm = {}
    return fm, end + 4

def detect_type(fpath, text, has_iframe):
    """自动检测类型"""
    rel = str(fpath.relative_to(VAULT))
    fname = fpath.name
    if fname == 'index.md':
        return 'index'
    if has_iframe:
        return 'video'
    if rel.startswith('System'):
        return 'rules'
    if fname.endswith('.pdf.md') or fname.endswith('.docx.md') or \
       fname.endswith('.pptx.md') or fname.endswith('.xls.md') or \
       fname.endswith('.xlsx.md') or fname.endswith('.doc.md'):
        return 'file'
    if len(text) > 500:
        return 'note'
    return 'stub'

def detect_summary(text):
    """提取摘要：标题后的第一段有意义文本"""
    # 跳过 frontmatter, 标题, 元数据表, iframe
    body = re.sub(r'^---.*?---\n', '', text, flags=re.DOTALL)
    body = re.sub(r'^# .+\n', '', body)
    body = re.sub(r'<iframe.*?</iframe>\n?', '', body, flags=re.DOTALL)
    body = re.sub(r'\|.*?\|.*?\|.*?\n', '', body)
    body = re.sub(r'^>.*\n', '', body)
    body = re.sub(r'^-\s*(📝|📄|📎|🔗|🆔).*\n', '', body, flags=re.MULTILINE)
    body = body.strip()
    # 取前 150 字符
    summary = body[:150].replace('\n', ' ').strip()
    if len(summary) > 140:
        summary = summary[:140] + '…'
    return summary if summary else '待整理'

def detect_importance(fpath, ftype, text, tags):
    """自动评估重要性 1-5"""
    if fpath.name.startswith('CLAUDE') or 'tasks.md' in fpath.name:
        return 5
    if ftype == 'rules':
        return 5
    if ftype == 'note' and len(text) > 3000:
        return 4
    if ftype == 'note' and len(text) > 1000:
        return 3
    if ftype == 'video':
        return 4
    if ftype == 'file':
        return 2
    if ftype == 'index':
        return 3
    return 2

def enrich(fpath):
    """为单篇笔记补充完整 frontmatter"""
    text = fpath.read_text(encoding='utf-8')
    fm, body_start = get_existing_fm(text)
    body = text[body_start:] if body_start > 0 else text

    # 提取标题
    title_m = re.match(r'^# (.+)', body)
    title = title_m.group(1).strip() if title_m else fpath.stem

    # 已有字段
    tags = fm.get('tags', [])
    if isinstance(tags, str): tags = [tags]

    has_iframe = '<iframe' in text

    # 自动检测
    ftype = fm.get('type') or detect_type(fpath, text, has_iframe)
    status = fm.get('status', 'draft')
    summary = fm.get('summary') or detect_summary(body)
    verified = fm.get('verified', 'unverified')
    importance = fm.get('importance') or detect_importance(fpath, ftype, text, tags)
    verifier_type = fm.get('verifier_type', 'auto')
    date = fm.get('date') or datetime.fromtimestamp(
        os.path.getmtime(fpath)).strftime('%Y-%m-%d')

    # 构建新 frontmatter
    new_fm = {
        'title': title,
        'date': date,
        'tags': tags,
        'type': ftype,
        'status': status,
        'summary': summary,
        'verified': verified,
        'importance': importance,
        'verifier_type': verifier_type,
    }

    # 写入
    fm_text = '---\n'
    for k, v in new_fm.items():
        if k == 'tags':
            fm_text += f'tags: [{", ".join(v)}]\n'
        elif isinstance(v, str):
            # 转义标题中的特殊字符
            safe = v.replace('"', '\\"').replace('\n', ' ')
            fm_text += f'{k}: "{safe}"\n'
        else:
            fm_text += f'{k}: {v}\n'
    fm_text += '---\n'

    fpath.write_text(fm_text + body.lstrip(), encoding='utf-8')
    return new_fm

def main():
    enriched = 0
    for root, dirs, files in os.walk(VAULT):
        if any(s in str(root) for s in ['.git','.obsidian','.claude','.claudian','TALOS','node_modules']):
            continue
        for f in files:
            if not f.endswith('.md'): continue
            # skip non-vault files
            if f in ('refresh-dashboard.py',): continue
            enrich(Path(root) / f)
            enriched += 1

    print(f"已处理 {enriched} 篇笔记")

    # 统计
    types = {}
    for root, dirs, files in os.walk(VAULT):
        if any(s in str(root) for s in ['.git','.obsidian','.claude','.claudian','TALOS','node_modules']):
            continue
        for f in files:
            if not f.endswith('.md'): continue
            text = (Path(root) / f).read_text(encoding='utf-8')
            m = re.search(r'type:\s*"?(.+?)"?\n', text)
            if m:
                t = m.group(1)
                types[t] = types.get(t, 0) + 1
    for t, c in sorted(types.items()):
        print(f"  {t}: {c}")

if __name__ == '__main__':
    main()
