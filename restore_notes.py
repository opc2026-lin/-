#!/usr/bin/env python3
"""从 IMA 重新拉取所有笔记原文，干净还原。"""
import os, re, json, subprocess, time
from pathlib import Path

VAULT = Path("D:/opc-ai知识库")
IMA_API = (VAULT / ".claudian/skills/ima-skill/ima_api.cjs").resolve()
HOME_DIR = Path.home()
OPTS = json.dumps({
    "clientId": (HOME_DIR / ".config/ima/client_id").read_text().strip(),
    "apiKey": (HOME_DIR / ".config/ima/api_key").read_text().strip()
}, ensure_ascii=False)

def call_ima(path, body):
    r = subprocess.run(["node", str(IMA_API), path, json.dumps(body, ensure_ascii=False), OPTS],
        capture_output=True, text=True, timeout=30, encoding='utf-8')
    return json.loads(r.stdout)

def get_note_content(media_id):
    """获取笔记原文"""
    # get_media_info -> note_id
    info = call_ima("openapi/wiki/v1/get_media_info", {"media_id": media_id})
    if info.get("code") != 0:
        return None
    note_id = info["data"].get("notebook_ext_info", {}).get("notebook_id", "")
    if not note_id:
        return None
    # get_doc_content
    doc = call_ima("openapi/note/v1/get_doc_content", {"note_id": note_id, "target_content_format": 0})
    if doc.get("code") != 0:
        return None
    return doc["data"].get("content", "")

def restore_note(fpath):
    """还原一篇笔记"""
    text = fpath.read_text(encoding='utf-8')

    # 提取 media_id
    m = re.search(r"media_id[：:]?\s*`?([a-z]+_[^`\s\)]+)", text)
    if not m:
        return False  # 没有 media_id，跳过
    media_id = m.group(1)

    # 提取原标题（第一个 # 行）
    title_m = re.match(r'^# (.+)', text)
    title = title_m.group(1).strip() if title_m else fpath.stem

    # 提取相关笔记
    related = ""
    rm = re.search(r'(\n\n## 相关笔记\n\n.*)$', text, re.DOTALL)
    if rm:
        related = rm.group(1)

    content = None

    if media_id.startswith('note_'):
        content = get_note_content(media_id)

    if content:
        result = f"# {title}\n\n> 来源: IMA 笔记 ({media_id})\n\n{content}{related}\n"
    else:
        # 无法获取内容，保留元数据引用
        type_names = {'pdf': 'PDF', 'word': 'Word', 'ppt': 'PPT', 'excel': 'Excel',
                      'img': '图片', 'web': '网页'}
        hint = media_id.split('_')[0]
        type_cn = type_names.get(hint, hint.upper())
        result = f"# {title}\n\n- 📄 类型: {type_cn}\n- 🆔 media_id: `{media_id}`\n- 🔗 [在 IMA 中查看](https://ima.qq.com/wiki/?media_id={media_id}){related}\n"

    fpath.write_text(result, encoding='utf-8')
    return True

def main():
    restored = 0
    for dir_name in ["综合能源", "AI知识库"]:
        d = VAULT / dir_name
        for f in sorted(os.listdir(d)):
            if not f.endswith('.md') or f == 'index.md': continue
            fpath = d / f
            if '<iframe' in fpath.read_text(encoding='utf-8')[:200]:
                continue  # skip video notes
            if restore_note(fpath):
                restored += 1
                print(f"  {dir_name}/{f[:50]}")
            time.sleep(0.5)  # 避免 API 限频

    print(f"\n还原 {restored} 篇")

if __name__ == "__main__":
    main()
