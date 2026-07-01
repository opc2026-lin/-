#!/usr/bin/env python3
"""Extended MarkItDown bridge for the Obsidian plugin."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import warnings
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from xml.etree import ElementTree


SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".xlsm",
    ".csv",
    ".json",
    ".xml",
    ".html",
    ".htm",
    ".txt",
    ".md",
    ".rtf",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
    ".gif",
    ".webp",
    ".wav",
    ".mp3",
    ".m4a",
    ".flac",
    ".ogg",
    ".aac",
    ".zip",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
ZIP_EXTENSIONS = {".zip"}


def configure_bundled_ffmpeg() -> str | None:
    warnings.filterwarnings(
        "ignore",
        message="Couldn't find ffmpeg or avconv.*",
        category=RuntimeWarning,
    )
    try:
        import imageio_ffmpeg
    except Exception:
        return None

    try:
        ffmpeg_path = Path(imageio_ffmpeg.get_ffmpeg_exe()).resolve()
    except Exception:
        return None

    if not ffmpeg_path.exists():
        return None

    os.environ["PATH"] = f"{ffmpeg_path.parent}{os.pathsep}{os.environ.get('PATH', '')}"
    os.environ.setdefault("IMAGEIO_FFMPEG_EXE", str(ffmpeg_path))
    try:
        from pydub import AudioSegment

        AudioSegment.converter = str(ffmpeg_path)
        AudioSegment.ffmpeg = str(ffmpeg_path)
    except Exception:
        pass

    return str(ffmpeg_path)


def safe_note_name(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "-", name).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "Untitled"


def unique_output_path(directory: Path, stem: str, overwrite: bool) -> Path:
    output = directory / f"{stem}.md"
    if overwrite or not output.exists():
        return output
    index = 2
    while True:
        candidate = directory / f"{stem}-{index}.md"
        if not candidate.exists():
            return candidate
        index += 1


def assert_inside_vault(path: Path, vault: Path) -> None:
    try:
        path.relative_to(vault)
    except ValueError as exc:
        raise ValueError(f"Output directory must be inside the vault: {vault}") from exc


def is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def note_stem_for_source(source: str | Path) -> str:
    raw = str(source)
    if is_url(raw):
        parsed = urlparse(raw)
        tail = parsed.path.rstrip("/").split("/")[-1] or parsed.netloc
        return safe_note_name(tail)
    return safe_note_name(Path(raw).stem)


def youtube_video_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]

    video_id = None
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0] or None
    elif host.endswith("youtube.com"):
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]
        elif parsed.path.startswith(("/shorts/", "/embed/", "/live/")):
            parts = parsed.path.strip("/").split("/")
            video_id = parts[1] if len(parts) > 1 else None

    if video_id and re.fullmatch(r"[A-Za-z0-9_-]{6,}", video_id):
        return video_id
    return None


def is_youtube_url(value: str) -> bool:
    return bool(is_url(value) and youtube_video_id(value))


def is_bilibili_url(value: str) -> bool:
    if not is_url(value):
        return False
    host = urlparse(value).netloc.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host.endswith("bilibili.com") or host in {"b23.tv", "bili2233.cn"}


def bilibili_video_identifiers(url: str) -> tuple[str | None, str | None]:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    bvid = (query.get("bvid") or [None])[0]
    aid = (query.get("aid") or [None])[0]

    match = re.search(r"/video/(BV[A-Za-z0-9]+)", parsed.path, re.IGNORECASE)
    if match:
        bvid = match.group(1)
    match = re.search(r"/video/av(\d+)", parsed.path, re.IGNORECASE)
    if match:
        aid = match.group(1)

    if bvid and not re.fullmatch(r"BV[A-Za-z0-9]+", bvid, re.IGNORECASE):
        bvid = None
    if aid and not re.fullmatch(r"\d+", str(aid)):
        aid = None
    return bvid, aid


def frontmatter_for(source: str | Path, converter: str) -> str:
    converted_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    lines = [
        "---",
        "tags:",
        "  - imported",
        "  - markitdown",
        f"source_file: {json.dumps(str(source), ensure_ascii=False)}",
        f"converted_at: {json.dumps(converted_at, ensure_ascii=False)}",
        f"converter: {json.dumps(converter, ensure_ascii=False)}",
        "---",
        "",
    ]
    return "\n".join(lines)


def markitdown() -> object:
    warnings.filterwarnings(
        "ignore",
        message="Couldn't find ffmpeg or avconv.*",
        category=RuntimeWarning,
    )
    configure_bundled_ffmpeg()
    from markitdown import MarkItDown

    try:
        return MarkItDown(enable_plugins=False)
    except TypeError:
        return MarkItDown()


def convert_with_markitdown(source: Path | str) -> str:
    md = markitdown()
    if isinstance(source, str) and is_url(source):
        result = md.convert_url(source)
    else:
        result = md.convert(str(source))
    return result.text_content.strip()


def fetch_youtube_oembed(url: str) -> dict[str, str]:
    try:
        import requests

        response = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": url, "format": "json"},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        return {
            "title": str(data.get("title") or "").strip(),
            "author_name": str(data.get("author_name") or "").strip(),
            "author_url": str(data.get("author_url") or "").strip(),
        }
    except Exception:
        return {}


def fetch_bilibili_json(url: str, params: dict[str, object] | None = None) -> dict[str, object]:
    try:
        import requests

        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
                "Referer": "https://www.bilibili.com/",
            }
        )
        response = session.get(url, params=params or {}, timeout=20)
        response.raise_for_status()
        return response.json()
    except Exception:
        return {}


def fetch_bilibili_video_info(url: str) -> dict[str, object]:
    bvid, aid = bilibili_video_identifiers(url)
    if not bvid and not aid:
        return {}
    params: dict[str, object] = {}
    if bvid:
        params["bvid"] = bvid
    if aid:
        params["aid"] = aid
    data = fetch_bilibili_json("https://api.bilibili.com/x/web-interface/view", params=params)
    if data.get("code") != 0:
        return {}
    return data.get("data") or {}


def fetch_bilibili_subtitle_info(bvid: str, cid: object) -> dict[str, object]:
    if not bvid or not cid:
        return {}
    data = fetch_bilibili_json("https://api.bilibili.com/x/player/v2", params={"bvid": bvid, "cid": cid})
    if data.get("code") != 0:
        data = fetch_bilibili_json("https://api.bilibili.com/x/player/wbi/v2", params={"bvid": bvid, "cid": cid})
    if data.get("code") != 0:
        return {}
    payload = data.get("data") or {}
    subtitle = payload.get("subtitle") or {}
    if not isinstance(subtitle, dict):
        return {}
    return subtitle


def fetch_youtube_ytdlp(url: str) -> dict[str, object]:
    try:
        from yt_dlp import YoutubeDL
    except Exception:
        return {"_error": "yt-dlp is not installed."}

    class QuietLogger:
        def debug(self, message: str) -> None:
            pass

        def warning(self, message: str) -> None:
            pass

        def error(self, message: str) -> None:
            pass

    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "extract_flat": False,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "logger": QuietLogger(),
    }
    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        return {"_error": str(sys.exc_info()[1])}
    return info or {}


def pick_subtitle_track(info: dict[str, object]) -> tuple[dict[str, object] | None, str]:
    preferred = ("zh-Hans", "zh-Hant", "zh-CN", "zh-TW", "zh", "en")
    for group_name, auto_label in (("subtitles", "manual"), ("automatic_captions", "generated")):
        group = info.get(group_name)
        if not isinstance(group, dict):
            continue
        languages = list(group.keys())
        ordered_languages = [lang for lang in preferred if lang in group]
        ordered_languages.extend(lang for lang in languages if lang not in ordered_languages)
        for language in ordered_languages:
            tracks = group.get(language)
            if not isinstance(tracks, list):
                continue
            ordered_tracks = sorted(
                (track for track in tracks if isinstance(track, dict) and track.get("url")),
                key=lambda track: 0 if str(track.get("ext") or "").lower() in {"json3", "vtt", "srv3", "srv2", "srv1"} else 1,
            )
            if ordered_tracks:
                return ordered_tracks[0], f"{language} ({auto_label}, yt-dlp)"
    return None, ""


def strip_markup(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'")
    return clean_extracted_text(text)


def transcript_from_json3(text: str) -> list[dict[str, object]]:
    data = json.loads(text)
    items: list[dict[str, object]] = []
    for event in data.get("events", []):
        if not isinstance(event, dict) or "segs" not in event:
            continue
        caption = "".join(str(seg.get("utf8") or "") for seg in event.get("segs", []) if isinstance(seg, dict))
        caption = clean_extracted_text(caption)
        if caption:
            items.append({"start": float(event.get("tStartMs", 0)) / 1000, "text": caption})
    return items


def transcript_from_vtt(text: str) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    current_start = 0.0
    current_lines: list[str] = []

    def seconds(value: str) -> float:
        match = re.match(r"(?:(\d+):)?(\d{2}):(\d{2})[.,](\d{3})", value)
        if not match:
            return 0.0
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2))
        secs = int(match.group(3))
        millis = int(match.group(4))
        return hours * 3600 + minutes * 60 + secs + millis / 1000

    def flush() -> None:
        nonlocal current_lines
        text_value = clean_extracted_text(" ".join(current_lines))
        if text_value:
            items.append({"start": current_start, "text": strip_markup(text_value)})
        current_lines = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line == "WEBVTT" or line.startswith(("Kind:", "Language:", "NOTE")):
            if current_lines:
                flush()
            continue
        if "-->" in line:
            if current_lines:
                flush()
            current_start = seconds(line.split("-->", 1)[0].strip())
            continue
        if re.fullmatch(r"\d+", line):
            continue
        current_lines.append(line)
    if current_lines:
        flush()
    return items


def transcript_from_xml(text: str) -> list[dict[str, object]]:
    root = ElementTree.fromstring(text)
    items: list[dict[str, object]] = []
    for node in root.iter():
        if node.tag.split("}")[-1] not in {"text", "p"}:
            continue
        caption = strip_markup("".join(node.itertext()))
        if caption:
            items.append({"start": float(node.attrib.get("start") or node.attrib.get("t") or 0) / (1000 if "t" in node.attrib else 1), "text": caption})
    return items


def fetch_ytdlp_transcript(info: dict[str, object]) -> tuple[list[dict[str, object]], str]:
    track, label = pick_subtitle_track(info)
    if not track:
        raise RuntimeError("No subtitle tracks found in yt-dlp metadata.")

    import requests

    response = requests.get(str(track["url"]), timeout=30)
    response.raise_for_status()
    text = response.text
    ext = str(track.get("ext") or "").lower()
    if ext == "json3" or text.lstrip().startswith("{"):
        items = transcript_from_json3(text)
    elif ext.startswith("srv") or text.lstrip().startswith("<"):
        items = transcript_from_xml(text)
    else:
        items = transcript_from_vtt(text)
    if not items:
        raise RuntimeError("Subtitle track was found but contained no readable text.")
    return items, label


def raw_transcript_items(transcript: object) -> list[dict[str, object]]:
    if hasattr(transcript, "to_raw_data"):
        return list(transcript.to_raw_data())
    return list(transcript)


def fetch_youtube_transcript(video_id: str) -> tuple[list[dict[str, object]], str]:
    from youtube_transcript_api import YouTubeTranscriptApi

    languages = ("zh-Hans", "zh-Hant", "zh-CN", "zh-TW", "zh", "en")
    api = YouTubeTranscriptApi()

    try:
        transcript_list = api.list(video_id)
        try:
            transcript = transcript_list.find_manually_created_transcript(languages)
            return raw_transcript_items(transcript.fetch(preserve_formatting=True)), (
                f"{transcript.language} ({transcript.language_code}, manual)"
            )
        except Exception:
            pass

        try:
            transcript = transcript_list.find_generated_transcript(languages)
            return raw_transcript_items(transcript.fetch(preserve_formatting=True)), (
                f"{transcript.language} ({transcript.language_code}, generated)"
            )
        except Exception:
            pass

        transcript = transcript_list.find_transcript(languages)
        return raw_transcript_items(transcript.fetch(preserve_formatting=True)), (
            f"{transcript.language} ({transcript.language_code})"
        )
    except Exception:
        transcript = api.fetch(video_id, languages=languages, preserve_formatting=True)
        return raw_transcript_items(transcript), "preferred transcript"


def format_timestamp(seconds: object) -> str:
    try:
        total = int(float(seconds))
    except Exception:
        total = 0
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def markdown_for_youtube_transcript(items: list[dict[str, object]]) -> str:
    lines: list[str] = []
    for item in items:
        text = clean_extracted_text(str(item.get("text") or ""))
        if not text:
            continue
        timestamp = format_timestamp(item.get("start", 0))
        lines.append(f"- `{timestamp}` {text}")
    return "\n".join(lines).strip()


def normalize_bilibili_bvid(bvid: str | None) -> str | None:
    if not bvid:
        return None
    match = re.fullmatch(r"(BV[A-Za-z0-9]+)", bvid, re.IGNORECASE)
    return match.group(1) if match else None


def iter_bilibili_pages(info: dict[str, object]) -> list[dict[str, object]]:
    pages = info.get("pages")
    if not isinstance(pages, list):
        return []
    return [page for page in pages if isinstance(page, dict)]


def format_bilibili_page_title(index: int, page: dict[str, object], total: int) -> str:
    part = clean_extracted_text(str(page.get("part") or ""))
    if total <= 1:
        return part or "P1"
    prefix = f"P{index + 1}"
    return f"{prefix} {part}".strip()


def bilibili_subtitle_items(subtitle_entry: dict[str, object]) -> list[dict[str, object]]:
    import requests

    url = str(subtitle_entry.get("subtitle_url") or subtitle_entry.get("url") or "")
    if url.startswith("//"):
        url = "https:" + url
    if not url:
        raise RuntimeError("Subtitle entry did not include a usable URL.")
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    data = response.json()
    items: list[dict[str, object]] = []
    for entry in data.get("body", []):
        if not isinstance(entry, dict):
            continue
        text = clean_extracted_text(str(entry.get("content") or ""))
        if not text:
            continue
        start = float(entry.get("from") or 0)
        items.append({"start": start, "text": text})
    return items


def select_bilibili_subtitle(subtitles: list[dict[str, object]]) -> tuple[dict[str, object] | None, str]:
    preferred = ("ai-zh", "ai-zh-Hans", "zh-Hans", "zh-Hant", "zh-CN", "zh-TW", "zh", "en")
    ordered = list(subtitles)
    ordered.sort(key=lambda item: 0 if str(item.get("lan") or "") in preferred else 1)
    if not ordered:
        return None, ""
    best = ordered[0]
    label = str(best.get("lan_doc") or best.get("lan") or "subtitle")
    return best, label


def convert_bilibili_url(url: str) -> tuple[str, str, str]:
    info = fetch_bilibili_video_info(url)
    if not info:
        raise RuntimeError("Could not retrieve Bilibili video metadata.")

    title = clean_extracted_text(str(info.get("title") or ""))
    owner = info.get("owner") if isinstance(info.get("owner"), dict) else {}
    uploader = clean_extracted_text(str((owner or {}).get("name") or ""))
    desc = clean_extracted_text(str(info.get("desc") or ""))
    bvid = normalize_bilibili_bvid(str(info.get("bvid") or bilibili_video_identifiers(url)[0] or ""))
    pages = iter_bilibili_pages(info)
    if not title:
        title = f"Bilibili {bvid or 'video'}"

    header_lines = [f"Source: {url}"]
    if bvid:
        header_lines.append(f"BV: `{bvid}`")
    if uploader:
        header_lines.append(f"UP 主: {uploader}")
    if desc:
        header_lines.append(f"简介: {desc[:4000]}")

    sections: list[str] = []
    if pages:
        total = len(pages)
        for idx, page in enumerate(pages):
            cid = page.get("cid")
            page_title = format_bilibili_page_title(idx, page, total)
            subtitle_meta = fetch_bilibili_subtitle_info(bvid or "", cid)
            subtitles = subtitle_meta.get("subtitles") if isinstance(subtitle_meta, dict) else []
            if not isinstance(subtitles, list) or not subtitles:
                sections.append(f"## {page_title}\n\n> No public subtitle / AI subtitle was available. Conversion stopped.")
                continue
            subtitle_entry, subtitle_label = select_bilibili_subtitle(subtitles)
            if not subtitle_entry:
                sections.append(f"## {page_title}\n\n> No usable subtitle track was found. Conversion stopped.")
                continue
            try:
                items = bilibili_subtitle_items(subtitle_entry)
                if not items:
                    raise RuntimeError("Subtitle track was empty.")
                subtitle_markdown = markdown_for_youtube_transcript(items)
                sections.append(f"## {page_title}\n\nSubtitle: {subtitle_label}\n\n{subtitle_markdown}")
            except Exception as exc:
                sections.append(f"## {page_title}\n\n> No public subtitle / AI subtitle was available: {exc}")
    else:
        sections.append("> No page metadata found.")

    body = "\n".join(header_lines)
    if sections:
        body += "\n\n" + "\n\n---\n\n".join(sections)
    return body, "bilibili subtitle bridge", safe_note_name(title)


def convert_youtube_url(url: str) -> tuple[str, str, str]:
    video_id = youtube_video_id(url)
    if not video_id:
        raise RuntimeError("Could not parse YouTube video ID from URL.")

    metadata = fetch_youtube_oembed(url)
    ytdlp_info = fetch_youtube_ytdlp(url)
    title = metadata.get("title") or f"YouTube {video_id}"
    if ytdlp_info.get("title"):
        title = str(ytdlp_info["title"]).strip()
    author = metadata.get("author_name") or ""
    if ytdlp_info.get("channel") or ytdlp_info.get("uploader"):
        author = str(ytdlp_info.get("channel") or ytdlp_info.get("uploader") or "").strip()
    author_url = metadata.get("author_url") or ""
    if ytdlp_info.get("channel_url") or ytdlp_info.get("uploader_url"):
        author_url = str(ytdlp_info.get("channel_url") or ytdlp_info.get("uploader_url") or "").strip()

    header_lines = [
        f"Source: {url}",
        f"Video ID: `{video_id}`",
    ]
    if author:
        header_lines.append(f"Channel: [{author}]({author_url})" if author_url else f"Channel: {author}")

    transcript_errors: list[str] = []
    try:
        if ytdlp_info and not ytdlp_info.get("_error"):
            transcript_items, transcript_label = fetch_ytdlp_transcript(ytdlp_info)
        else:
            raise RuntimeError(str(ytdlp_info.get("_error") or "yt-dlp could not read this video."))
    except Exception as ytdlp_error:
        transcript_errors.append(f"yt-dlp: {ytdlp_error}")
        try:
            transcript_items, transcript_label = fetch_youtube_transcript(video_id)
        except Exception as api_error:
            transcript_errors.append(f"youtube-transcript-api: {api_error}")
            transcript_items = []
            transcript_label = ""

    try:
        transcript_markdown = markdown_for_youtube_transcript(transcript_items)
        if not transcript_markdown:
            raise RuntimeError("Transcript was found but contained no text.")
        body = "\n".join(header_lines)
        body += f"\nTranscript: {transcript_label}\n\n## Transcript\n\n{transcript_markdown}"
        return body, "youtube transcript", safe_note_name(title)
    except Exception as transcript_error:
        if str(transcript_error):
            transcript_errors.append(str(transcript_error))

        body = "\n".join(header_lines)
        description = clean_extracted_text(str(ytdlp_info.get("description") or ""))
        if description:
            body += f"\n\n## Description\n\n{description[:4000]}"
        body += (
            "\n\n## Transcript unavailable\n\n"
            f"> Could not retrieve YouTube captions/transcript: {'; '.join(transcript_errors)}\n\n"
            "This can happen when the video has no public captions, YouTube blocks the transcript endpoint, "
            "or the current network cannot access YouTube transcript data."
        )
        subtitle_languages = sorted(
            set((ytdlp_info.get("subtitles") or {}).keys()) | set((ytdlp_info.get("automatic_captions") or {}).keys())
        ) if ytdlp_info else []
        if subtitle_languages:
            body += "\n\nAvailable subtitle languages reported by yt-dlp: " + ", ".join(subtitle_languages[:80])
        return body, "youtube metadata + transcript error", safe_note_name(title)


def extract_legacy_ppt(source: Path, tools_dir: Path | None) -> str | None:
    if not tools_dir:
        return extract_legacy_ppt_text(source)
    sys.path.insert(0, str(tools_dir))
    try:
        from markitdown_to_obsidian import convert_file

        return convert_file(source)
    except Exception:
        return extract_legacy_ppt_text(source)
    finally:
        try:
            sys.path.remove(str(tools_dir))
        except ValueError:
            pass


def extract_legacy_doc(source: Path) -> tuple[str, str] | None:
    text = extract_legacy_doc_with_textutil(source)
    if text:
        return text, "markitdown + textutil doc fallback"

    text = extract_legacy_doc_with_command(source, "antiword", [str(source)])
    if text:
        return text, "markitdown + antiword doc fallback"

    text = extract_legacy_doc_with_command(source, "catdoc", [str(source)])
    if text:
        return text, "markitdown + catdoc doc fallback"

    text = extract_legacy_doc_with_libreoffice(source)
    if text:
        return text, "markitdown + libreoffice doc fallback"

    text = extract_legacy_doc_text(source)
    if text:
        return text, "markitdown + legacy doc fallback"

    return None


def extract_legacy_doc_with_textutil(source: Path) -> str | None:
    if not shutil.which("textutil"):
        return None
    try:
        result = subprocess.run(
            ["textutil", "-convert", "txt", "-stdout", str(source)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    text = clean_extracted_text(result.stdout)
    return text or None


def extract_legacy_doc_with_command(source: Path, command: str, args: list[str]) -> str | None:
    if not shutil.which(command):
        return None
    try:
        result = subprocess.run(
            [command, *args],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    text = clean_extracted_text(result.stdout)
    return text or None


def extract_legacy_doc_with_libreoffice(source: Path) -> str | None:
    command = shutil.which("soffice") or shutil.which("libreoffice")
    if not command:
        return None
    with tempfile.TemporaryDirectory(prefix="markitdown-doc-") as temp_dir:
        try:
            result = subprocess.run(
                [
                    command,
                    "--headless",
                    "--convert-to",
                    "txt:Text",
                    "--outdir",
                    temp_dir,
                    str(source),
                ],
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
        except Exception:
            return None
        if result.returncode != 0:
            return None
        output = Path(temp_dir) / f"{source.stem}.txt"
        if not output.exists():
            candidates = sorted(Path(temp_dir).glob("*.txt"))
            output = candidates[0] if candidates else output
        if not output.exists():
            return None
        text = clean_extracted_text(output.read_text(encoding="utf-8", errors="ignore"))
        return text or None


def extract_legacy_doc_text(source: Path) -> str | None:
    try:
        import olefile
    except Exception:
        return None

    try:
        with olefile.OleFileIO(str(source)) as ole:
            stream_name = next(
                (
                    entry
                    for entry in ole.listdir(streams=True, storages=False)
                    if entry and entry[-1] == "WordDocument"
                ),
                None,
            )
            if stream_name is None:
                return None
            data = ole.openstream(stream_name).read()
    except Exception:
        return None

    chunks: list[str] = []
    seen: set[str] = set()

    def add_candidate(text: str) -> None:
        cleaned = clean_extracted_text(text)
        if not cleaned or cleaned in seen:
            return
        if len(re.sub(r"\s+", "", cleaned)) < 8:
            return
        seen.add(cleaned)
        chunks.append(cleaned)

    for match in re.finditer(rb"(?:[\x20-\x7e]\x00|[\x00-\xff][\x4e-\x9f]){8,}", data):
        add_candidate(match.group(0).decode("utf-16le", errors="ignore"))

    for match in re.finditer(rb"[\x20-\x7e\x80-\xff]{16,}", data):
        raw = match.group(0)
        try:
            add_candidate(raw.decode("gb18030", errors="ignore"))
        except Exception:
            pass

    if not chunks:
        return None
    return (
        "> Legacy .doc fallback extraction was used because MarkItDown could not convert this file directly.\n\n"
        + "\n\n".join(chunks)
    )


def clean_extracted_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x0b", "\n")
    text = re.sub(r"[\x00-\x08\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def looks_like_slide_text(text: str) -> bool:
    if len(text) < 2:
        return False
    if text.startswith(("C:\\", "__", "___")):
        return False
    if "单击此处编辑母版" in text:
        return False
    if re.fullmatch(r"[\W_]+", text):
        return False
    return True


def extract_legacy_ppt_text(source: Path) -> str | None:
    try:
        import olefile
    except Exception:
        return None

    try:
        with olefile.OleFileIO(str(source)) as ole:
            stream_name = next(
                (
                    entry
                    for entry in ole.listdir(streams=True, storages=False)
                    if entry and entry[-1] == "PowerPoint Document"
                ),
                None,
            )
            if stream_name is None:
                return None
            data = ole.openstream(stream_name).read()
    except Exception:
        return None

    chunks: list[str] = []
    seen: set[str] = set()

    def add_text(text: str) -> None:
        cleaned = clean_extracted_text(text)
        if not cleaned or not looks_like_slide_text(cleaned) or cleaned in seen:
            return
        seen.add(cleaned)
        chunks.append(cleaned)

    def walk_records(start: int, end: int) -> None:
        position = start
        while position + 8 <= end:
            record_version = data[position] & 0x0F
            record_type = int.from_bytes(data[position + 2 : position + 4], "little")
            record_len = int.from_bytes(data[position + 4 : position + 8], "little")
            payload_start = position + 8
            payload_end = payload_start + record_len

            if payload_end > end:
                return

            payload = data[payload_start:payload_end]
            if record_type == 4000:
                add_text(payload.decode("utf-16le", errors="ignore"))
            elif record_type == 4008:
                add_text(payload.decode("gbk", errors="ignore"))

            if record_version == 0x0F and record_len:
                walk_records(payload_start, payload_end)

            position = payload_end if record_len else position + 8

    walk_records(0, len(data))
    if not chunks:
        return None

    body = "\n\n---\n\n".join(chunks)
    return (
        "> Legacy .ppt fallback extraction was used because MarkItDown could not convert this file directly.\n\n"
        f"{body}"
    )


def run_macos_ocr(image: Path, ocr_script: Path) -> str | None:
    if not ocr_script.exists() or not shutil.which("swift"):
        return None
    result = subprocess.run(
        ["swift", str(ocr_script), str(image)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    text = result.stdout.strip()
    if result.returncode == 0 and text:
        return text
    return None


def run_tesseract_ocr(image: Path) -> str | None:
    try:
        import pytesseract
        from PIL import Image
    except Exception:
        return None

    try:
        text = pytesseract.image_to_string(Image.open(image), lang="chi_sim+chi_tra+eng")
    except Exception:
        try:
            text = pytesseract.image_to_string(Image.open(image))
        except Exception:
            return None

    text = text.strip()
    return text or None


def convert_image(source: Path, ocr_script: Path) -> tuple[str, str]:
    ocr_text = run_macos_ocr(source, ocr_script)
    if ocr_text:
        return ocr_text, "macOS Vision OCR"
    ocr_text = run_tesseract_ocr(source)
    if ocr_text:
        return ocr_text, "Tesseract OCR"
    return convert_with_markitdown(source), "markitdown"


def convert_content(source: Path | str, tools_dir: Path | None, ocr_script: Path) -> tuple[str, str]:
    if isinstance(source, str) and is_url(source):
        return convert_with_markitdown(source), "markitdown"

    path = Path(source)
    suffix = path.suffix.lower()
    if suffix == ".ppt":
        legacy_text = extract_legacy_ppt(path, tools_dir)
        if legacy_text:
            return legacy_text, "markitdown + legacy ppt fallback"
    if suffix == ".doc":
        legacy_doc = extract_legacy_doc(path)
        if legacy_doc:
            return legacy_doc
    if suffix in IMAGE_EXTENSIONS:
        return convert_image(path, ocr_script)
    return convert_with_markitdown(path), "markitdown"


def write_note(
    source: str | Path,
    markdown: str,
    output_dir: Path,
    overwrite: bool,
    converter: str,
    stem_override: str | None = None,
) -> Path:
    stem = safe_note_name(stem_override or note_stem_for_source(source))
    output = unique_output_path(output_dir, stem, overwrite)
    output.write_text(
        frontmatter_for(source, converter) + f"# {stem}\n\n" + markdown.strip() + "\n",
        encoding="utf-8",
    )
    return output


def convert_zip(source: Path, tools_dir: Path | None, ocr_script: Path) -> tuple[str, str]:
    sections: list[str] = []
    with tempfile.TemporaryDirectory(prefix="markitdown-zip-") as temp_dir:
        temp_root = Path(temp_dir)
        with zipfile.ZipFile(source) as archive:
            archive.extractall(temp_root)
        for child in sorted(temp_root.rglob("*")):
            if not child.is_file() or child.suffix.lower() not in SUPPORTED_EXTENSIONS - ZIP_EXTENSIONS:
                continue
            try:
                markdown, converter = convert_content(child, tools_dir, ocr_script)
                relative = child.relative_to(temp_root).as_posix()
                sections.append(f"## {relative}\n\n{markdown}\n\n<!-- converter: {converter} -->")
            except Exception as exc:
                relative = child.relative_to(temp_root).as_posix()
                sections.append(f"## {relative}\n\n> Conversion failed: {exc}")
    if not sections:
        raise RuntimeError("No supported files were found inside the ZIP archive.")
    return "\n\n---\n\n".join(sections), "zip recursive bridge"


def iter_directory_files(directory: Path, recursive: bool) -> list[Path]:
    iterator = directory.rglob("*") if recursive else directory.glob("*")
    return sorted(
        path
        for path in iterator
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def convert_one(
    source: str,
    output_dir: Path,
    overwrite: bool,
    recursive: bool,
    tools_dir: Path | None,
    ocr_script: Path,
) -> list[dict[str, object]]:
    if is_url(source):
        if is_youtube_url(source):
            markdown, converter, stem = convert_youtube_url(source)
            output = write_note(source, markdown, output_dir, overwrite, converter, stem)
        elif is_bilibili_url(source):
            markdown, converter, stem = convert_bilibili_url(source)
            output = write_note(source, markdown, output_dir, overwrite, converter, stem)
        else:
            markdown, converter = convert_content(source, tools_dir, ocr_script)
            output = write_note(source, markdown, output_dir, overwrite, converter)
        return [{"ok": True, "source": source, "output": str(output)}]

    path = Path(source).expanduser().resolve()
    if path.is_dir():
        results: list[dict[str, object]] = []
        files = iter_directory_files(path, recursive)
        if not files:
            return [{"ok": False, "source": str(path), "error": "No supported files found in this folder."}]
        for child in files:
            results.extend(convert_one(str(child), output_dir, overwrite, recursive, tools_dir, ocr_script))
        return results

    if not path.is_file():
        return [{"ok": False, "source": source, "error": "Source does not exist."}]

    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return [{"ok": False, "source": str(path), "error": f"Unsupported file type: {path.suffix or 'none'}"}]

    if path.suffix.lower() in ZIP_EXTENSIONS:
        markdown, converter = convert_zip(path, tools_dir, ocr_script)
    else:
        markdown, converter = convert_content(path, tools_dir, ocr_script)
    output = write_note(path, markdown, output_dir, overwrite, converter)
    return [{"ok": True, "source": str(path), "output": str(output)}]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extended MarkItDown bridge for Obsidian.")
    parser.add_argument("--vault", required=True, type=Path)
    parser.add_argument("--dest", required=True)
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--tools-dir", type=Path, default=None)
    parser.add_argument("--ocr-script", type=Path, required=True)
    parser.add_argument("--result-file", type=Path, default=None)
    return parser.parse_args()


def emit_result(payload: dict[str, object], result_file: Path | None) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    if result_file:
        result_file.parent.mkdir(parents=True, exist_ok=True)
        result_file.write_text(text, encoding="utf-8")
    else:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
        print(text)


def main() -> int:
    args = parse_args()
    vault = args.vault.expanduser().resolve()
    output_dir = (vault / args.dest).resolve()
    results: list[dict[str, object]] = []

    try:
        assert_inside_vault(output_dir, vault)
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        emit_result({"results": [{"ok": False, "source": args.dest, "error": str(exc)}]}, args.result_file)
        return 1

    for source in args.source:
        try:
            results.extend(
                convert_one(
                    source,
                    output_dir,
                    args.overwrite,
                    args.recursive,
                    args.tools_dir.expanduser().resolve() if args.tools_dir else None,
                    args.ocr_script.expanduser().resolve(),
                )
            )
        except Exception as exc:
            results.append({"ok": False, "source": source, "error": str(exc)})

    emit_result({"results": results}, args.result_file)
    return 0 if all(result.get("ok") for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
