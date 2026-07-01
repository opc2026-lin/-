#!/usr/bin/env python3
"""全库索引重建：为所有含 3+ 篇笔记的目录生成 index.md。
修复标签计数渲染 Bug：`#tag`(N) → `#tag` (N)"""
import os, re, yaml
from pathlib import Path
from collections import defaultdict, Counter

VAULT = Path("D:/opc-ai知识库")
SKIP_DIRS = {'.git', '.obsidian', '.claude', '.claudian', 'TALOS', 'node_modules', '__pycache__'}
MIN_NOTES = 3  # 目录至少包含几篇笔记才生成索引

# 格式伪标签（不应出现在标签云中）
FORMAT_PSEUDO_TAGS = {'PDF', 'Word', 'PPT', 'PPTX', 'XLS', 'XLSX', 'DOC', 'DOCX', '文件'}

def build_index(dir_path: Path, entries: list[tuple[str, set[str], str, str]]) -> str:
    """
    为目录生成 index.md 内容。
    entries: [(title, tags_set, filename, note_type), ...]
    """
    dir_name = dir_path.name if dir_path != VAULT else '根目录'
    total = len(entries)

    # 标签计数（排除伪标签）
    tag_counter = Counter()
    for _, tags, _, _ in entries:
        for t in tags:
            if t not in FORMAT_PSEUDO_TAGS:
                tag_counter[t] += 1

    # 按标签分组
    by_tag = defaultdict(list)
    for title, tags, fname, ntype in entries:
        clean_tags = [t for t in tags if t not in FORMAT_PSEUDO_TAGS]
        for t in clean_tags[:3]:  # 每篇最多归入 3 个标签
            by_tag[t].append((title, fname, ntype))

    # 热门标签
    top_tags = tag_counter.most_common(8)

    # 构建内容
    lines = [
        f'# {dir_name} · 索引',
        '',
        f'> 共 {total} 篇',
        '',
    ]

    if top_tags:
        lines.append('## 热门标签')
        lines.append('')
        # 修复：`#tag`(N) → `#tag` (N)（加空格才能正确渲染）
        tag_cloud = ' '.join(f'`#{t}` ({c})' for t, c in top_tags)
        lines.append(tag_cloud)
        lines.append('')

    if by_tag:
        lines.append('## 按标签浏览')
        lines.append('')
        for tag, items in sorted(by_tag.items(), key=lambda x: -len(x[1])):
            lines.append(f'### {tag}')
            lines.append('')
            for title, fname, ntype in items[:10]:
                # 如果是 file 类型，加标记
                marker = ' 📄' if ntype == 'file' else ''
                lines.append(f'- [[{title}]]{marker}')
            if len(items) > 10:
                lines.append(f'- ... 等 {len(items)} 篇')
            lines.append('')

    # 补充分类统计
    type_counts = Counter(nt for _, _, _, nt in entries)
    if len(type_counts) > 1:
        lines.append('## 类型分布')
        lines.append('')
        for t, c in type_counts.most_common():
            lines.append(f'- {t}: {c} 篇')
        lines.append('')

    return '\n'.join(lines) + '\n'

def main():
    # ====== 收集所有笔记按目录分组 ======
    print("收集笔记...")
    dir_entries: dict[str, list[tuple[str, set[str], str, str]]] = defaultdict(list)

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

            # 解析 frontmatter
            tags = set()
            ntype = 'note'
            if text.startswith('---\n'):
                fm_end = text.find('\n---\n', 4)
                if fm_end > 0:
                    try:
                        fm = yaml.safe_load(text[4:fm_end]) or {}
                        t = fm.get('tags', [])
                        if isinstance(t, str):
                            t = [t]
                        tags = set(t)
                        ntype = fm.get('type', 'note')
                    except:
                        pass

            title = f.replace('.md', '')
            rel_dir = str(Path(root).relative_to(VAULT))
            dir_entries[rel_dir].append((title, tags, f, ntype))

    # ====== 为每个目录生成 index.md ======
    print("生成索引...")
    generated = 0

    for rel_dir, entries in sorted(dir_entries.items()):
        if len(entries) < MIN_NOTES:
            continue

        dir_path = VAULT / rel_dir
        if not dir_path.exists():
            continue

        content = build_index(dir_path, entries)
        index_path = dir_path / 'index.md'
        index_path.write_text(content, encoding='utf-8')
        print(f'  [OK] {rel_dir}/index.md ({len(entries)} notes)')
        generated += 1

    print(f'\n共生成 {generated} 个索引')

    # ====== 统计 ======
    print("\n=== 目录统计 ===")
    for rel_dir, entries in sorted(dir_entries.items(), key=lambda x: -len(x[1])):
        md_files = sum(1 for t, _, _, _ in entries
                       if any(t.endswith(e.replace('.md', '')) for e in
                              ('.pdf.md', '.docx.md', '.pptx.md', '.xls.md', '.xlsx.md', '.doc.md')))
        tag_total = sum(len(tags) for _, tags, _, _ in entries)
        print(f'  {rel_dir}: {len(entries)} 篇 (MarkItDown: {md_files}, 标签: {tag_total})')

if __name__ == '__main__':
    main()
