"""流水线第①步：下载视频。

输入：视频页面 URL + 任务 ID
输出：DownloadResult（其中 video_path 指向 data/{task_id}/source.mp4）

基于 yt-dlp，合并最佳音视频流为单个 mp4。通过 on_progress 回调把下载进度
往外透传，供编排层（orchestrator）转成 SSE 推给前端。

依赖：yt-dlp（Python 包）、ffmpeg（合并音视频流，需在 PATH 中）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError as YtDlpDownloadError

from src.config import settings, ensure_task_dir, SOURCE_VIDEO_STEM

logger = logging.getLogger(__name__)


class DownloadError(RuntimeError):
    """下载阶段失败。包装底层异常，向上层提供统一的错误类型。"""


@dataclass
class DownloadProgress:
    """单次进度回调的数据。percent 为 0-100；总大小未知时 total_bytes 为 None。"""

    status: str  # "downloading" | "finished"
    percent: float
    downloaded_bytes: int
    total_bytes: Optional[int]
    speed: Optional[float]  # 字节/秒
    eta: Optional[int]      # 预计剩余秒数


@dataclass
class DownloadResult:
    """下载结果。"""

    video_path: Path
    title: str
    duration: Optional[float]   # 秒
    ext: str
    filesize: Optional[int]     # 字节
    width: Optional[int]
    height: Optional[int]
    source_url: str

# 视频下载回调函数 回调函数逻辑 提供修改进度的展示函数 -> 放入执行流程中的hook内
ProgressHook = Callable[[DownloadProgress], None]

# 对钩子函数进行封装
def _make_progress_adapter(on_progress: ProgressHook):
    """把 yt-dlp 的 hook 字典转换成统一的 DownloadProgress 回调。"""

    def hook(d: dict) -> None:
        status = d.get("status")
        if status not in ("downloading", "finished"):
            return

        downloaded = d.get("downloaded_bytes") or 0
        total = d.get("total_bytes") or d.get("total_bytes_estimate")

        if status == "finished":
            percent = 100.0
        elif total:
            percent = max(0.0, min(100.0, downloaded / total * 100.0))
        else:
            percent = 0.0

        try:
            on_progress(
                DownloadProgress(
                    status=status,
                    percent=round(percent, 1),
                    downloaded_bytes=downloaded,
                    total_bytes=total,
                    speed=d.get("speed"),
                    eta=d.get("eta"),
                )
            )
        except Exception:  # 回调里的异常不应中断下载
            logger.exception("下载进度回调异常，已忽略")

    return hook


def download_video(
    url: str,
    task_id: str,
    on_progress: Optional[ProgressHook] = None,
    *,
    cookies_file: Optional[Path] = None,
    format_selector: Optional[str] = None,
) -> DownloadResult:
    """下载单个视频到 data/{task_id}/source.mp4。

    Args:
        url: 视频页面地址。
        task_id: 任务 ID，决定输出目录。
        on_progress: 可选进度回调。
        cookies_file: 可选 cookies 文件（部分站点需年龄校验 / 登录）。
        format_selector: 可选覆盖 yt-dlp 的 format 选择串。

    Returns:
        DownloadResult

    Raises:
        DownloadError: 下载或解析失败、或找不到产物文件。
    """
    out_dir = ensure_task_dir(task_id)
    # 固定基名，扩展名交给 yt-dlp / 合并器决定，最终合并为 mp4
    outtmpl = str(out_dir / f"{SOURCE_VIDEO_STEM}.%(ext)s")

    ydl_opts: dict = {
        "format": format_selector or settings.download_format,
        "merge_output_format": settings.merge_output_format,
        "outtmpl": outtmpl,
        "noplaylist": True,          # 只下单个视频，忽略播放列表
        "retries": settings.download_retries,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,          # 关闭 yt-dlp 自带进度条，进度走我们的 hook
        "overwrites": True,          # 重跑时覆盖旧文件
    }

    cookies = cookies_file or settings.cookies_file
    if cookies:
        ydl_opts["cookiefile"] = str(cookies)

    if on_progress is not None:
        ydl_opts["progress_hooks"] = [_make_progress_adapter(on_progress)]

    logger.info("开始下载: task=%s url=%s", task_id, url)

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except YtDlpDownloadError as e:
        raise DownloadError(f"视频下载失败: {e}") from e
    except Exception as e:  # 解析 / 网络等其它错误
        raise DownloadError(f"下载过程中出错: {e}") from e

    video_path = _resolve_output_path(info, out_dir)
    if video_path is None or not video_path.exists():
        raise DownloadError("下载完成但未找到产物文件")

    result = DownloadResult(
        video_path=video_path,
        title=info.get("title") or video_path.stem,
        duration=info.get("duration"),
        ext=video_path.suffix.lstrip("."),
        filesize=_safe_filesize(video_path),
        width=info.get("width"),
        height=info.get("height"),
        source_url=url,
    )
    logger.info(
        "下载完成: task=%s file=%s (%.1f MB)",
        task_id,
        video_path.name,
        (result.filesize or 0) / 1024 / 1024,
    )
    return result


def _resolve_output_path(info: dict, out_dir: Path) -> Optional[Path]:
    """从 yt-dlp 的 info 中解析最终产物路径，带多重回退。"""
    # 1) 最可靠：合并后的 requested_downloads[].filepath
    downloads = info.get("requested_downloads")
    if downloads:
        fp = downloads[0].get("filepath")
        if fp:
            return Path(fp)

    # 2) info 顶层可能直接带 filepath
    fp = info.get("filepath")
    if fp:
        return Path(fp)

    # 3) 兜底：按固定基名在目录里找
    candidates = sorted(out_dir.glob(f"{SOURCE_VIDEO_STEM}.*"))
    # 优先合并目标容器
    target = out_dir / f"{SOURCE_VIDEO_STEM}.{settings.merge_output_format}"
    if target.exists():
        return target
    return candidates[0] if candidates else None


def _safe_filesize(path: Path) -> Optional[int]:
    try:
        return path.stat().st_size
    except OSError:
        return None

