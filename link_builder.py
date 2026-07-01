#!/usr/bin/env python3
"""智能双链构建器：多因子打分 + MarkItDown 配对检测 + 最少 2 条双链保证。
公式：标签重叠×3 + 关键词Jaccard×2 + 同目录×1 + note↔file互推×2"""
import os, re, yaml
from pathlib import Path
from collections import defaultdict, Counter

VAULT = Path("D:/opc-ai知识库")
SKIP_DIRS = {'.git', '.obsidian', '.claude', '.claudian', 'TALOS', 'node_modules', '__pycache__'}
MIN_LINKS = 2           # 每篇至少推荐几条双链
MAX_LINKS = 8           # 每篇最多几条

# MarkItDown 文件后缀
MD_EXTENSIONS = ('.pdf.md', '.docx.md', '.pptx.md', '.xls.md', '.xlsx.md', '.doc.md')

def extract_keywords(text: str, max_len: int = 2000) -> set[str]:
    """提取内容关键词集合（用于 Jaccard 计算）"""
    t = text[:max_len]
    words = set(re.findall(r'[\w一-鿿]{2,8}', t.lower()))
    stop = {'一个','这个','可以','没有','不是','已经','还是','但是','我们',
            '他们','这些','那些','什么','怎么','为什么','因为','所以','如果',
            '虽然','不过','而且','然后','就是','只是','进行','通过','需要',
            '使用','问题','情况','方式','方面','作为','对于','关于','全部',
            '大家','视频','链接','作者','平台','来源','笔记','内容','整理',
            '打开','查看','关注','谢谢','时间','生成','时长','创建',
            'with','the','and','for','that','this','from','have','are','was',
            'will','can','not','but','all','has','been','they','their','more',
            'its','also','into','new','only','other','used','some','such','than',
            'when','your','which','each','may','any','one','two','like','very'}
    return words - stop

def get_core_name(filename: str) -> str:
    """获取文件核心名（去除 MarkItDown 后缀）"""
    for ext in MD_EXTENSIONS:
        if filename.endswith(ext):
            return filename[:-len(ext)]
    return filename.replace('.md', '')

def is_markitdown(title: str) -> bool:
    """判断是否为 MarkItDown 转换文档"""
    return any(title.endswith(ext.replace('.md', '')) for ext in MD_EXTENSIONS)

def is_interpretation(title: str) -> bool:
    """判断是否为解读笔记"""
    return title.startswith('解读') or title.startswith('解析')

def detect_pair(title: str, other_title: str) -> bool:
    """检测 MarkItDown 原文档 ↔ 解读笔记配对"""
    core_a = get_core_name(title)
    core_b = get_core_name(other_title)

    # 去掉"解读"/"解析"前缀后再比较
    clean_a = re.sub(r'^(解读|解析)\s*', '', core_a)
    clean_b = re.sub(r'^(解读|解析)\s*', '', core_b)

    # 一个必须是 MarkItDown 文档，另一个必须是解读笔记
    a_is_md = is_markitdown(title)
    b_is_md = is_markitdown(other_title)
    a_is_int = is_interpretation(title)
    b_is_int = is_interpretation(other_title)

    if (a_is_md and b_is_int) or (a_is_int and b_is_md):
        # 核心名必须匹配
        if clean_a == clean_b:
            return True
        # 也尝试子串匹配（解读标题可能包含完整原文件名）
        if len(clean_a) > 8 and len(clean_b) > 8:
            if clean_a in clean_b or clean_b in clean_a:
                return True

    return False

def jaccard(set_a: set, set_b: set) -> float:
    """计算 Jaccard 相似度"""
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)

def parse_fm(text: str) -> tuple[dict, str]:
    """解析 YAML frontmatter，返回 (fm_dict, body)"""
    if not text.startswith('---\n'):
        return {}, text
    end = text.find('\n---\n', 4)
    if end < 0:
        return {}, text
    try:
        fm = yaml.safe_load(text[4:end]) or {}
    except:
        fm = {}
    return fm, text[end + 4:]

def main():
    # ====== Phase 1: 收集所有笔记元数据 ======
    print("Phase 1: 收集笔记元数据...")
    notes: dict[str, dict] = {}  # title → {dir, tags, type, keywords, file}

    for root, dirs, files in os.walk(VAULT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
        for f in files:
            if not f.endswith('.md') or f == 'index.md':
                continue
            fpath = Path(root) / f
            try:
                text = fpath.read_text(encoding='utf-8')
            except:
                continue
            if len(text) < 50:
                continue

            title = f.replace('.md', '')
            fm, body = parse_fm(text)
            tags = fm.get('tags', [])
            if isinstance(tags, str):
                tags = [tags]
            tags = set(tags)
            ntype = fm.get('type', 'note')
            keywords = extract_keywords(title + ' ' + body[:2000])
            rel_dir = str(Path(root).relative_to(VAULT))

            notes[title] = {
                'dir': rel_dir,
                'file': f,
                'tags': tags,
                'type': ntype,
                'keywords': keywords,
            }

    print(f"  共 {len(notes)} 篇笔记")

    # ====== Phase 2: 构建索引 ======
    print("Phase 2: 构建索引...")
    tag_index: dict[str, set[str]] = defaultdict(set)
    for title, info in notes.items():
        for t in info['tags']:
            tag_index[t].add(title)

    # ====== Phase 3: 为每篇笔记计算双链推荐 ======
    print("Phase 3: 计算双链推荐...")
    links_added = 0
    links_total = 0

    for title, info in notes.items():
        scores: dict[str, float] = defaultdict(float)

        for other_title, other_info in notes.items():
            if other_title == title:
                continue

            # 1. 标签重叠分 (×3)
            tag_overlap = len(info['tags'] & other_info['tags'])
            if tag_overlap > 0:
                scores[other_title] += tag_overlap * 3

            # 2. 关键词 Jaccard 分 (×2)
            jac = jaccard(info['keywords'], other_info['keywords'])
            if jac > 0.05:  # 阈值过滤噪音
                scores[other_title] += jac * 2

            # 3. 同目录加分 (×1)
            if info['dir'] == other_info['dir']:
                scores[other_title] += 1

            # 4. note↔file 互推 (×2)
            if detect_pair(title, other_title):
                scores[other_title] += 2

        # 取 Top N
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        top = ranked[:MAX_LINKS]

        # 确保最少 MIN_LINKS 条
        if len(top) < MIN_LINKS:
            # 补充同目录笔记
            already = {t for t, _ in top}
            same_dir = [
                (ot, 0) for ot, oi in notes.items()
                if ot != title and oi['dir'] == info['dir'] and ot not in already
            ]
            # 去重后取需要的数量
            needed = MIN_LINKS - len(top)
            top.extend(same_dir[:needed])

        if not top:
            continue

        # ====== 写入文件 ======
        fpath = VAULT / info['dir'] / info['file']
        if not fpath.exists():
            continue

        text = fpath.read_text(encoding='utf-8')

        # 清理已有双链段落（去重）
        text = re.sub(r'\n*---\n\n## 双链笔记\n\n.*$', '', text, flags=re.DOTALL)
        text = re.sub(r'\n*## 双链笔记\n\n.*$', '', text, flags=re.DOTALL)

        # 构建新链接
        new_links = []
        seen = set()
        for ot, sc in top:
            if ot in seen:
                continue
            seen.add(ot)
            od = notes[ot]['dir']
            if od == info['dir'] or info['dir'] == '.':
                link = f'- [[{ot}]]'
            else:
                link = f'- [[{od}/{ot}]]'
            new_links.append(link)

        # 追加
        text = text.rstrip() + '\n\n---\n\n## 双链笔记\n\n' + '\n'.join(new_links) + '\n'
        fpath.write_text(text, encoding='utf-8')
        links_added += 1
        links_total += len(new_links)

    print(f"  已为 {links_added} 篇笔记添加双链（共 {links_total} 条链接）")

    # ====== Phase 4: 统计报告 ======
    print("\n=== 统计报告 ===")
    md_count = sum(1 for t in notes if is_markitdown(t))
    int_count = sum(1 for t in notes if is_interpretation(t))
    pairs_found = 0
    for t, i in notes.items():
        for ot in notes:
            if t < ot and detect_pair(t, ot):
                pairs_found += 1
    print(f"  MarkItDown 文档: {md_count} 篇")
    print(f"  解读笔记: {int_count} 篇")
    print(f"  检测到文档<->解读配对: {pairs_found} 对")

if __name__ == '__main__':
    main()
