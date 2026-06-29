"""实网集成测试：真实链接跑通 ①下载 → ②提取音频 全链路。

默认跳过（避免每次 `uv run pytest` 都碰网络、下载大文件）。
需显式开启：

    SUBTRANS_LIVE_TEST=1 uv run pytest tests/test_live_pipeline.py -v -s

为了快，这里用 `format_selector="worst"` 拉最小清晰度，只验证链路是否通，
不关心画质。换示例视频时改 EXAMPLE_URL 即可。
"""

from __future__ import annotations

import os
import shutil

import pytest

from src.core import audio_extractor, downloader
from src.core.audio_extractor import extract_audio
from src.core.downloader import download_video

LIVE = os.getenv("SUBTRANS_LIVE_TEST") == "1"
EXAMPLE_URL = "https://cn.pornhub.com/view_video.php?viewkey=66f5a091bf8ff"

_FFMPEG_OK = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


@pytest.mark.skipif(not LIVE, reason="需 SUBTRANS_LIVE_TEST=1 才跑真实下载")
@pytest.mark.skipif(not _FFMPEG_OK, reason="需要 ffmpeg / ffprobe")
def test_live_download_and_extract(tmp_path, monkeypatch):
    # 下载与提取共用同一个隔离目录（不污染项目 data/）
    work = tmp_path / "live"
    work.mkdir()
    monkeypatch.setattr(downloader, "ensure_task_dir", lambda task_id: work)
    monkeypatch.setattr(audio_extractor, "ensure_task_dir", lambda task_id: work)

    # ① 下载（worst 清晰度，尽量小）
    dl_progress = []
    res = download_video(
        EXAMPLE_URL,
        "live",
        on_progress=dl_progress.append,
        format_selector="worst",
    )
    assert res.video_path.exists()
    assert res.filesize and res.filesize > 0
    assert res.source_url == EXAMPLE_URL
    assert dl_progress, "应至少收到一次下载进度回调"

    # ② 提取音频
    audio_progress = []
    audio = extract_audio(res.video_path, "live", on_progress=audio_progress.append)
    assert audio.audio_path.exists()
    assert audio.audio_path.name == "audio.wav"
    assert audio.sample_rate == 16000
    assert audio.channels == 1
    assert audio.filesize and audio.filesize > 0
