#!/usr/bin/env python3
"""修复 YAML frontmatter 乱码——用 yaml.dump 标准序列化"""
import os, re, yaml
from pathlib import Path

VAULT = Path("D:/opc-ai知识库")

def fix_one(fpath):
    text = fpath.read_text(encoding='utf-8')

    # 解析当前 frontmatter
    fm = {}
    body_start = 0
    if text.startswith('---\n'):
        end = text.find('\n---\n', 4)
        if end > 0:
            try:
                fm = yaml.safe_load(text[4:end]) or {}
            except:
                pass
            body_start = end + 4

    body = text[body_start:].lstrip('\n')
    if not fm:
        return

    # 清理字段值
    for k, v in list(fm.items()):
        if isinstance(v, str):
            # 解码可能被 YAML 转义破坏的中文
            # 移除多余的转义符
            v = v.replace('\\"', '"').replace('\\#', '#')
            v = v.replace('\\>', '>').replace('\\*', '*')
            v = v.replace('\\[', '[').replace('\\]', ']')
            v = v.replace('\\|', '|').replace('\\\\', '\\')
            # 清理零宽字符
            v = re.sub(r'[​‌‍﻿]', '', v)
            fm[k] = v

    # 标题去掉 markdown #
    if 'title' in fm and isinstance(fm['title'], str):
        fm['title'] = fm['title'].lstrip('#').strip()

    # summary 截取纯文本
    if 'summary' in fm and isinstance(fm['summary'], str):
        s = fm['summary']
        s = re.sub(r'[#\*\|>\\]', '', s)
        s = re.sub(r'\s+', ' ', s)
        fm['summary'] = s[:140].strip()

    # 用 yaml.dump 标准输出
    fm_text = '---\n'
    # 自定义顺序
    order = ['title','date','tags','type','status','summary','verified','importance','verifier_type']
    for k in order:
        if k in fm:
            v = fm[k]
            if k == 'tags' and isinstance(v, list):
                clean_tags = [str(t).strip() for t in v]
                fm_text += 'tags: [' + ', '.join(clean_tags) + ']\n'
            elif isinstance(v, str):
                # 确保单行输出
                clean = v.replace('\n', ' ').replace('\r', ' ')
                clean = re.sub(r'\s+', ' ', clean).strip()
                if any(c in clean for c in ':#{}[]&*!|>"\''):
                    # 用双引号包裹
                    clean = clean.replace('"', '\\"')
                    fm_text += f'{k}: "{clean}"\n'
                else:
                    fm_text += f'{k}: "{clean}"\n'
            else:
                fm_text += f'{k}: {v}\n'
    fm_text += '---\n'

    fpath.write_text(fm_text + body, encoding='utf-8')

def main():
    fixed = 0
    for root, dirs, files in os.walk(VAULT):
        if any(s in str(root) for s in ['.git','.obsidian','.claude','.claudian','TALOS','node_modules']):
            continue
        for f in files:
            if not f.endswith('.md'): continue
            fix_one(Path(root) / f)
            fixed += 1
    print(f'已修复 {fixed} 篇')

if __name__ == '__main__':
    main()
