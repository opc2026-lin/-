#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IMA 知识库迁移脚本 — 将 IMA 云端知识库内容拉取到本地 Obsidian vault。
用法：python3 migrate_ima.py
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

# ==================== 配置 ====================
VAULT = Path(__file__).resolve().parent
SKILL_DIR = (VAULT / ".claudian" / "skills" / "ima-skill").resolve()
IMA_API = SKILL_DIR / "ima_api.cjs"

HOME_DIR = Path.home()
CLIENT_ID_FILE = HOME_DIR / ".config" / "ima" / "client_id"
API_KEY_FILE = HOME_DIR / ".config" / "ima" / "api_key"

# 要迁移的知识库：{kb_id: (目录名, 显示名)}
KB_TARGETS = {
    "bWX5XRIu91BivluHfKTfoYwxY9MLjFsI5C0-AnxWd84=": ("AIGC", "AIGC"),
}

# 每页条数
PAGE_SIZE = 50
# API 调用间隔（秒），避免触发限频
API_DELAY = 0.6

# ==================== 辅助函数 ====================

def get_opts():
    """读取凭证构造 opts JSON"""
    cid = CLIENT_ID_FILE.read_text().strip()
    api_key = API_KEY_FILE.read_text().strip()
    return json.dumps({"clientId": cid, "apiKey": api_key}, ensure_ascii=False)


def call_ima(api_path, body_dict):
    """调用 ima_api.cjs，返回 (success, data_or_error)"""
    opts = get_opts()
    body = json.dumps(body_dict, ensure_ascii=False)
    try:
        result = subprocess.run(
            ["node", str(IMA_API.resolve()), api_path, body, opts],
            capture_output=True, text=True, timeout=60,
            encoding="utf-8",
        )
        if result.returncode != 0:
            try:
                err = json.loads(result.stderr)
                return False, f"脚本错误 code={err.get('code')}: {err.get('msg')}"
            except:
                return False, f"脚本错误: {result.stderr[:200]}"
        data = json.loads(result.stdout)
        if data.get("code") != 0:
            return False, f"API 错误 code={data.get('code')}: {data.get('msg')}"
        return True, data.get("data", {})
    except subprocess.TimeoutExpired:
        return False, "超时"
    except Exception as e:
        return False, str(e)


def list_all_knowledge(kb_id):
    """分页拉取知识库全部条目，返回 [{media_id, title, media_type_hint}, ...]"""
    items = []
    cursor = ""
    page = 0
    while True:
        page += 1
        ok, data = call_ima("openapi/wiki/v1/get_knowledge_list", {
            "cursor": cursor,
            "limit": PAGE_SIZE,
            "knowledge_base_id": kb_id,
        })
        if not ok:
            print(f"  ❌ 分页失败: {data}", flush=True)
            break
        kl = data.get("knowledge_list", [])
        for it in kl:
            # 从 media_id 前缀推测类型
            mid = it.get("media_id", "")
            hint = "unknown"
            for prefix in ["note_", "pdf_", "word_", "ppt_", "excel_", "web_", "img_",
                           "md_", "txt_", "session_", "audio_", "xmind_"]:
                if mid.startswith(prefix):
                    hint = prefix.rstrip("_")
                    break
            items.append({
                "media_id": mid,
                "title": it.get("title", "未命名"),
                "type_hint": hint,
                "folder_id": it.get("parent_folder_id", ""),
            })
        is_end = data.get("is_end", True)
        cursor = data.get("next_cursor", "")
        print(f"  第 {page} 页: {len(kl)} 条, 累计 {len(items)} 条, is_end={is_end}", flush=True)
        if is_end or not cursor:
            break
        time.sleep(API_DELAY)
    return items


def get_media_info(media_id):
    """获取媒体详情，返回 {media_type, url, note_id, ...}"""
    ok, data = call_ima("openapi/wiki/v1/get_media_info", {"media_id": media_id})
    if not ok:
        return None
    info = {"media_type": data.get("media_type", 0)}
    ui = data.get("url_info", {})
    if ui and ui.get("url"):
        info["url"] = ui["url"]
        info["headers"] = ui.get("headers", {})
    ne = data.get("notebook_ext_info", {})
    if ne and ne.get("notebook_id"):
        info["note_id"] = ne["notebook_id"]
    return info


def get_note_content(note_id):
    """获取 IMA 笔记正文（纯文本）"""
    ok, data = call_ima("openapi/note/v1/get_doc_content", {
        "note_id": note_id,
        "target_content_format": 0,  # 纯文本
    })
    if not ok:
        return None
    return data.get("content", "")


def sanitize_filename(title, max_len=80):
    """将标题转为安全的文件名"""
    name = title.strip()
    # 移除 Windows 非法字符
    name = re.sub(r'[<>:"/\\|?*]', '-', name)
    # 压缩空白
    name = re.sub(r'\s+', ' ', name)
    if len(name) > max_len:
        name = name[:max_len].rstrip() + "…"
    return name


# ==================== 主流程 ====================

def migrate_kb(kb_id, dir_name, display_name):
    """迁移单个知识库"""
    out_dir = VAULT / dir_name
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"📚 迁移知识库: {display_name}")
    print(f"   目标目录: {dir_name}/")
    print(f"{'='*60}")

    # Step 1: 列出全部条目
    print("🔍 拉取知识库条目列表...")
    items = list_all_knowledge(kb_id)
    print(f"   共 {len(items)} 条")

    if not items:
        print("   ⚠️ 该知识库无内容，跳过")
        return

    # 统计类型分布
    type_counts = {}
    for it in items:
        h = it["type_hint"]
        type_counts[h] = type_counts.get(h, 0) + 1
    print(f"   类型分布: {type_counts}")

    # Step 2: 逐个处理
    success = 0
    skipped = 0
    failed = 0

    for i, item in enumerate(items):
        mid = item["media_id"]
        title = item["title"]
        hint = item["type_hint"]
        fname = sanitize_filename(title)
        out_path = out_dir / f"{fname}.md"

        # 处理重名：自动追加序号
        if out_path.exists():
            base = out_path.stem
            counter = 2
            orig_path = out_path
            while out_path.exists():
                out_path = out_dir / f"{base}_{counter}.md"
                counter += 1
                if counter > 100:  # 安全上限
                    break

        content = None
        meta_note = ""

        try:
            if hint == "note":
                # IMA 笔记：尝试获取正文，失败则创建引用笔记
                info = get_media_info(mid)
                if info and info.get("note_id"):
                    content = get_note_content(info["note_id"])
                    if content:
                        content = f"# {title}\n\n> 来源: IMA 笔记 ({mid})\n\n{content}"
                if not content:
                    # 无权限或获取失败 → 创建引用笔记
                    meta_note = f"# {title}\n\n- 📝 类型: IMA 笔记\n- 🆔 media_id: `{mid}`\n- 🔗 [在 IMA 中打开](https://ima.qq.com/wiki/?media_id={mid})"
            elif hint in ("web",):
                # 网页：获取 URL 并尝试抓取
                info = get_media_info(mid)
                if info and info.get("url"):
                    meta_note = f"# {title}\n\n> 📎 原文链接: {info['url']}\n> 来源: IMA 知识库 ({mid})\n> 类型: 网页\n\n> ⚠️ 网页内容需手动打开原文链接查看"

            elif hint in ("pdf", "word", "ppt", "excel"):
                # 文件类型：创建引用笔记
                info = get_media_info(mid)
                url = info.get("url", "") if info else ""
                type_names = {"pdf": "PDF", "word": "Word", "ppt": "PPT", "excel": "Excel"}
                type_cn = type_names.get(hint, hint.upper())
                meta_note = f"# {title}\n\n- 📄 类型: {type_cn}\n- 🆔 media_id: `{mid}`\n- 🔗 [在 IMA 中打开](https://ima.qq.com/wiki/?media_id={mid})"
                if url:
                    meta_note += f"\n- 📎 下载链接: {url}"

            elif hint in ("img",):
                info = get_media_info(mid)
                url = info.get("url", "") if info else ""
                meta_note = f"# {title}\n\n- 🖼️ 类型: 图片\n- 🆔 media_id: `{mid}`\n- 🔗 [在 IMA 中打开](https://ima.qq.com/wiki/?media_id={mid})"

            elif hint in ("session",):
                meta_note = f"# {title}\n\n- 💬 类型: AI 会话\n- 🆔 media_id: `{mid}`\n- 🔗 [在 IMA 中打开](https://ima.qq.com/wiki/?media_id={mid})"

            elif hint in ("audio",):
                meta_note = f"# {title}\n\n- 🎙️ 类型: 录音\n- 🆔 media_id: `{mid}`\n- 🔗 [在 IMA 中打开](https://ima.qq.com/wiki/?media_id={mid})"

            elif hint in ("xmind",):
                meta_note = f"# {title}\n\n- 🗺️ 类型: 思维导图\n- 🆔 media_id: `{mid}`\n- 🔗 [在 IMA 中打开](https://ima.qq.com/wiki/?media_id={mid})"

            else:
                # 未知类型，尝试获取 media_info
                info = get_media_info(mid)
                mt = info.get("media_type", "?") if info else "?"
                url = info.get("url", "") if info else ""
                meta_note = f"# {title}\n\n- 📦 类型: media_type={mt}\n- 🆔 media_id: `{mid}`\n- 🔗 [在 IMA 中打开](https://ima.qq.com/wiki/?media_id={mid})"

            # 写入文件
            final_content = content if content else meta_note
            if final_content:
                out_path.write_text(final_content, encoding="utf-8")
                success += 1
            else:
                failed += 1

        except Exception as e:
            failed += 1
            print(f"  ⚠️ [{i+1}] 错误: {title[:40]}... → {e}")

        if (i + 1) % 20 == 0:
            print(f"  进度: {i+1}/{len(items)} (成功 {success}, 跳过 {skipped}, 失败 {failed})", flush=True)

        time.sleep(API_DELAY)

    print(f"\n✅ {display_name} 迁移完成: 成功 {success}, 跳过 {skipped}, 失败 {failed}")
    return success, skipped, failed


def main():
    print("🚀 IMA 知识库迁移开始")
    print(f"   Vault: {VAULT}")
    print(f"   目标知识库: {len(KB_TARGETS)} 个")

    total_success = 0
    for kb_id, (dir_name, display_name) in KB_TARGETS.items():
        s, sk, f = migrate_kb(kb_id, dir_name, display_name)
        total_success += s

    print(f"\n{'='*60}")
    print(f"🏁 全部迁移完成! 共创建 {total_success} 个 .md 文件")
    print(f"   接下来运行: python3 refresh-dashboard.py --vault \"{VAULT}\"")


if __name__ == "__main__":
    main()
