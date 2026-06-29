"""① 下载视频 的单元测试。

全程 mock yt_dlp，不依赖网络：验证产物路径解析、结果构造、错误包装、
进度回调适配等纯逻辑。
"""

from __future__ import annotations

import pytest
from yt_dlp.utils import DownloadError as YtDlpDownloadError

from src.core import downloader
from src.core.downloader import (
    DownloadError,
    DownloadProgress,
    download_video,
    _make_progress_adapter,
    _resolve_output_path,
)


def make_fake_ydl(on_extract):
    """构造一个可作为上下文管理器使用的假 YoutubeDL，extract_info 行为由回调决定。"""

    class _FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=False):
            return on_extract(url, download, self.opts)

    return _FakeYDL


@pytest.fixture
def task_path(tmp_path, monkeypatch):
    """隔离任务目录：patch downloader.ensure_task_dir 指向临时目录。"""
    d = tmp_path / "task1"
    d.mkdir()
    monkeypatch.setattr(downloader, "ensure_task_dir", lambda task_id: d)
    return d


# ---------- download_video 主流程 ----------

def test_download_success(task_path, monkeypatch):
    src = task_path / "source.mp4"

    def on_extract(url, download, opts):
        assert download is True
        src.write_bytes(b"fake video data")
        return {
            "title": "My Video",
            "duration": 12.5,
            "width": 640,
            "height": 360,
            "requested_downloads": [{"filepath": str(src)}],
        }

    monkeypatch.setattr(downloader, "YoutubeDL", make_fake_ydl(on_extract))

    res = download_video("http://example.com/v", "task1")

    assert res.video_path == src
    assert res.title == "My Video"
    assert res.duration == 12.5
    assert res.ext == "mp4"
    assert res.width == 640 and res.height == 360
    assert res.filesize == len(b"fake video data")
    assert res.source_url == "http://example.com/v"


def test_download_title_falls_back_to_stem(task_path, monkeypatch):
    src = task_path / "source.mp4"

    def on_extract(url, download, opts):
        src.write_bytes(b"x")
        return {"requested_downloads": [{"filepath": str(src)}]}  # 无 title

    monkeypatch.setattr(downloader, "YoutubeDL", make_fake_ydl(on_extract))

    res = download_video("http://x", "task1")
    assert res.title == "source"


def test_download_wraps_ytdlp_error(task_path, monkeypatch):
    def on_extract(url, download, opts):
        raise YtDlpDownloadError("boom")

    monkeypatch.setattr(downloader, "YoutubeDL", make_fake_ydl(on_extract))

    with pytest.raises(DownloadError, match="下载失败"):
        download_video("http://x", "task1")


def test_download_wraps_generic_error(task_path, monkeypatch):
    def on_extract(url, download, opts):
        raise ValueError("unexpected")

    monkeypatch.setattr(downloader, "YoutubeDL", make_fake_ydl(on_extract))

    with pytest.raises(DownloadError, match="出错"):
        download_video("http://x", "task1")


def test_download_missing_output_file(task_path, monkeypatch):
    def on_extract(url, download, opts):
        # 返回一个不存在的路径，模拟"下载完成但产物缺失"
        return {"requested_downloads": [{"filepath": str(task_path / "nope.mp4")}]}

    monkeypatch.setattr(downloader, "YoutubeDL", make_fake_ydl(on_extract))

    with pytest.raises(DownloadError, match="未找到产物"):
        download_video("http://x", "task1")


def test_download_passes_progress_hook(task_path, monkeypatch):
    """传入 on_progress 时，opts 里应注册 progress_hooks。"""
    src = task_path / "source.mp4"
    captured = {}

    def on_extract(url, download, opts):
        captured["opts"] = opts
        src.write_bytes(b"x")
        return {"requested_downloads": [{"filepath": str(src)}]}

    monkeypatch.setattr(downloader, "YoutubeDL", make_fake_ydl(on_extract))

    download_video("http://x", "task1", on_progress=lambda p: None)
    assert "progress_hooks" in captured["opts"]
    assert len(captured["opts"]["progress_hooks"]) == 1


# ---------- _resolve_output_path 回退逻辑 ----------

def test_resolve_uses_requested_downloads(tmp_path):
    target = tmp_path / "a.mp4"
    info = {"requested_downloads": [{"filepath": str(target)}]}
    assert _resolve_output_path(info, tmp_path) == target


def test_resolve_uses_top_level_filepath(tmp_path):
    target = tmp_path / "b.mp4"
    info = {"filepath": str(target)}
    assert _resolve_output_path(info, tmp_path) == target


def test_resolve_glob_prefers_merge_container(tmp_path):
    (tmp_path / "source.mp4").write_bytes(b"x")
    assert _resolve_output_path({}, tmp_path) == tmp_path / "source.mp4"


def test_resolve_glob_other_ext(tmp_path):
    (tmp_path / "source.mkv").write_bytes(b"x")
    assert _resolve_output_path({}, tmp_path) == tmp_path / "source.mkv"


def test_resolve_returns_none_when_nothing(tmp_path):
    assert _resolve_output_path({}, tmp_path) is None


# ---------- _make_progress_adapter 进度映射 ----------

def test_progress_downloading_with_total():
    seen = []
    hook = _make_progress_adapter(seen.append)
    hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 200})
    assert len(seen) == 1
    p = seen[0]
    assert isinstance(p, DownloadProgress)
    assert p.percent == 25.0
    assert p.total_bytes == 200
    assert p.downloaded_bytes == 50


def test_progress_uses_estimate_when_no_total():
    seen = []
    hook = _make_progress_adapter(seen.append)
    hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes_estimate": 100})
    assert seen[0].percent == 50.0


def test_progress_finished_is_100():
    seen = []
    hook = _make_progress_adapter(seen.append)
    hook({"status": "finished", "downloaded_bytes": 200, "total_bytes": 200})
    assert seen[0].percent == 100.0
    assert seen[0].status == "finished"


def test_progress_ignores_unknown_status():
    seen = []
    hook = _make_progress_adapter(seen.append)
    hook({"status": "error"})
    assert seen == []


def test_progress_swallows_callback_exception():
    def bad(_p):
        raise RuntimeError("callback blew up")

    hook = _make_progress_adapter(bad)
    # 不应抛出
    hook({"status": "finished"})
