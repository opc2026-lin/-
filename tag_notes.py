#!/usr/bin/env python3
"""为所有笔记自动打标签（基于内容关键词），并更新 YAML frontmatter。"""
import os, re, yaml
from pathlib import Path
from collections import Counter

VAULT = Path("D:/opc-ai知识库")

# 关键词 → 标签映射
TAG_MAP = {
    # 能源领域
    '能源托管': '能源托管', '能源费用': '能源托管', '合同能源': '合同能源管理',
    'EMC': '合同能源管理', '节能': '节能改造', '节能率': '节能改造',
    '光伏': '光伏', '太阳能': '光伏', '分布式光伏': '光伏',
    '储能': '储能', '电池': '储能', '充电桩': '充换电', '换电站': '充换电',
    '碳': '双碳', '碳普惠': '碳交易', '碳交易': '碳交易', 'CCER': '碳交易', 'CEA': '碳交易',
    '售电': '售电', '电力交易': '电力交易', '电力市场': '电力交易', '电价': '电力交易',
    '现货': '电力交易', '负荷预测': '电力交易', '电网': '电网',
    '虚拟电厂': '虚拟电厂', 'VPP': '虚拟电厂',
    '综合能源': '综合能源', '多能互补': '综合能源',
    '空调': '暖通节能', '照明': '照明节能', '锅炉': '暖通节能',
    '医院': '公共机构', '学校': '公共机构', '公共机构': '公共机构',
    '发改': '政策文件', '国办': '政策文件', '能源局': '政策文件',
    '招标': '招投标', '投标': '招投标', '采购': '招投标',

    # AI/Tech
    'AI': 'AI', 'LLM': 'AI', '大模型': 'AI', 'Claude': 'Claude', 'GPT': 'AI',
    'Agent': 'AI Agent', 'Skill': 'AI Skill', 'MCP': 'AI',
    'Vibe Coding': 'VibeCoding', 'Codex': 'Codex', 'Cursor': 'AI工具',
    'Obsidian': 'Obsidian', 'Notion': '知识管理', '知识库': '知识管理',
    'Prompt': 'Prompt', 'Loop': 'Loop Engineering',
    '开源': '开源', 'github': '开源',

    # 商业
    '创业': '创业', '商业模式': '商业模式', '销售': '销售', '客户': '销售',
    '营销': '营销', '赚钱': '商业思维', '投资': '投资', '交易': '投资',
}

def extract_keywords(text):
    """从文本提取关键词"""
    words = re.findall(r'[\w一-鿿]{2,6}', text)
    stop = {'一个','这个','可以','没有','不是','已经','还是','但是','我们',
            '他们','这些','那些','什么','怎么','为什么','因为','所以','如果',
            '虽然','不过','而且','然后','就是','只是','进行','通过','需要',
            '使用','问题','情况','方式','方面','作为','对于','关于','全部',
            '大家','视频','链接','作者','平台','来源','笔记','内容','整理',
            '打开','查看','关注','谢谢','时间','生成','时长','创建'}
    return [w for w in words if w not in stop]

def get_tags(title, content):
    """根据标题和内容打标签"""
    text = title + ' ' + content[:1000]
    keywords = set()
    for kw, tag in TAG_MAP.items():
        if kw.lower() in text.lower():
            keywords.add(tag)
    return sorted(keywords)[:6]

def add_frontmatter(fpath, tags):
    """为 markdown 文件添加/更新 YAML frontmatter"""
    text = fpath.read_text(encoding='utf-8')

    # 提取已有 frontmatter
    existing = {}
    fm_end = 0
    if text.startswith('---\n'):
        fm_end = text.find('\n---\n', 4)
        if fm_end > 0:
            fm_text = text[4:fm_end]
            try:
                existing = yaml.safe_load(fm_text) or {}
            except:
                pass
            fm_end += 4  # past the closing ---

    # 合并标签
    old_tags = existing.get('tags', [])
    if isinstance(old_tags, str):
        old_tags = [old_tags]
    new_tags = sorted(set(list(old_tags) + list(tags)))

    existing['tags'] = new_tags

    # 重建 frontmatter
    fm = '---\n'
    for k, v in existing.items():
        if k == 'tags':
            fm += f'tags: [{", ".join(v)}]\n'
        elif isinstance(v, str):
            fm += f'{k}: "{v}"\n'
        else:
            fm += f'{k}: {v}\n'
    fm += '---\n'

    body = text[fm_end:] if fm_end > 0 else '\n' + text
    fpath.write_text(fm + body.lstrip('\n'), encoding='utf-8')

def main():
    total = 0
    for dir_name in ['综合能源', 'AI知识库', '个人笔记', '收件箱']:
        d = VAULT / dir_name
        if not d.exists(): continue
        count = 0
        for f in sorted(os.listdir(d)):
            if not f.endswith('.md') or f in ('index.md',): continue
            fpath = d / f
            text = fpath.read_text(encoding='utf-8')
            if len(text) < 100: continue

            title = f.replace('.md', '')
            tags = get_tags(title, text)
            if not tags: continue

            add_frontmatter(fpath, tags)
            count += 1
        print(f'{dir_name}: {count} 篇')
        total += count
    print(f'共 {total} 篇')

if __name__ == '__main__':
    main()
