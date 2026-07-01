#!/usr/bin/env python3
"""
视频逐字稿转录工具 v3
-- 抖音：解析 share 页 _ROUTER_DATA → 下载视频 → Whisper 转录
-- B站/YouTube：yt-dlp 直接下载 → Whisper 转录
用法: python3 transcribe.py <视频URL> [--model small|medium]
"""

import sys, os, tempfile, subprocess, re, json
import requests

def transcribe_douyin(url, model_size="small"):
    """抖音专用：解析 share 页 JSON 获取视频地址"""
    headers = {'User-Agent': 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36'}
    r = requests.get(url, headers=headers, allow_redirects=True, timeout=15)
    html = r.text

    idx = html.find('_ROUTER_DATA')
    if idx < 0:
        raise RuntimeError("未找到视频数据，可能需要更新 share URL")

    eq = html.find('=', idx)
    start = html.find('{', eq)
    depth = 0
    end = start
    for i in range(start, len(html)):
        if html[i] == '{': depth += 1
        elif html[i] == '}':
            depth -= 1
            if depth == 0: end = i + 1; break

    data = json.loads(html[start:end])
    item = data['loaderData']['video_(id)/page']['videoInfoRes']['item_list'][0]
    video_url = item['video']['play_addr']['url_list'][0].replace('playwm', 'play')

    return download_and_transcribe(video_url, model_size,
        {'User-Agent': 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36',
         'Referer': 'https://www.douyin.com/'})

def transcribe_other(url, model_size="small"):
    """B站/YouTube：只下载音频流，不下载视频"""
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, 'audio.%(ext)s')
        subprocess.run([
            'yt-dlp', '-f', 'bestaudio', '--audio-format', 'wav', '-o', out,
            '--no-playlist', '--socket-timeout', '30', '--retries', '3', url
        ], check=True, capture_output=True)
        for f in os.listdir(tmp):
            if f.endswith('.wav'):
                return transcribe_audio(os.path.join(tmp, f), model_size)
    raise FileNotFoundError("下载失败")

def download_and_transcribe(video_url, model_size, headers):
    """流式下载 → 管道提取音频 → Whisper 转录（不存视频文件）"""
    download_cmd = [
        'curl', '-sL',
        '-H', f'User-Agent: {headers["User-Agent"]}',
        '-H', f'Referer: {headers["Referer"]}',
        video_url
    ]
    ffmpeg_cmd = [
        'ffmpeg', '-y', '-i', 'pipe:0', '-vn',
        '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', '-f', 'wav', 'pipe:1'
    ]

    dl = subprocess.Popen(download_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    ff = subprocess.Popen(ffmpeg_cmd, stdin=dl.stdout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    dl.stdout.close()

    audio_data, _ = ff.communicate(timeout=120)
    if ff.returncode != 0 or len(audio_data) < 1000:
        raise RuntimeError(f"音频提取失败，大小: {len(audio_data)} bytes")

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as af:
        af.write(audio_data)
        apath = af.name

    try:
        return transcribe_audio(apath, model_size)
    finally:
        os.unlink(apath)

def transcribe_audio(audio_path, model_size):
    """faster-whisper 转录"""
    from faster_whisper import WhisperModel
    print(f"转录中 (模型: {model_size})...", file=sys.stderr)
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(audio_path, beam_size=5, language="zh")
    return "\n\n".join(seg.text.strip() for seg in segments)

def main():
    if len(sys.argv) < 2:
        print("用法: python3 transcribe.py <视频URL>", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]
    model_size = sys.argv[2] if len(sys.argv) > 2 else "small"

    if 'douyin.com' in url or 'iesdouyin.com' in url:
        text = transcribe_douyin(url, model_size)
    else:
        text = transcribe_other(url, model_size)

    print(text)

if __name__ == "__main__":
    main()
