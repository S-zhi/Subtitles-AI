"""全局配置。

支持通过环境变量覆盖，方便在不同机器 / 部署环境调整，
本机开发直接用默认值即可。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# backend/ 目录（本文件位于 backend/app/config/config.py，向上三级）
_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _env_path(key: str, default: Path) -> Path:
    val = os.getenv(key)
    return Path(val).expanduser() if val else default


def _opt_env_path(key: str) -> Optional[Path]:
    val = os.getenv(key)
    return Path(val).expanduser() if val else None


@dataclass(frozen=True)
class Settings:
    # 后端根目录
    backend_dir: Path = _BACKEND_DIR

    # 所有任务产物的根目录，按 data/{task_id}/ 组织
    data_dir: Path = _env_path("SUBTRANS_DATA_DIR", _BACKEND_DIR / "data")

    # yt-dlp 格式选择：优先最佳视频+音频，回退到单一最佳流
    download_format: str = os.getenv("SUBTRANS_DL_FORMAT", "bv*+ba/b")

    # 合并后的容器格式
    merge_output_format: str = os.getenv("SUBTRANS_DL_CONTAINER", "mp4")

    # 部分站点需要 cookies 通过年龄校验 / 登录，可选
    cookies_file: Optional[Path] = _opt_env_path("SUBTRANS_COOKIES")

    # 下载失败重试次数
    download_retries: int = int(os.getenv("SUBTRANS_DL_RETRIES", "3"))

    # ffmpeg / ffprobe 可执行文件（默认走 PATH）
    ffmpeg_bin: str = os.getenv("SUBTRANS_FFMPEG", "ffmpeg")
    ffprobe_bin: str = os.getenv("SUBTRANS_FFPROBE", "ffprobe")

    # 提取音频的采样率与声道：16kHz 单声道是 Whisper 的标准输入
    audio_sample_rate: int = int(os.getenv("SUBTRANS_AUDIO_SR", "16000"))
    audio_channels: int = int(os.getenv("SUBTRANS_AUDIO_CH", "1"))

    # --- ③ 语音识别（faster-whisper）---
    whisper_model: str = os.getenv("SUBTRANS_WHISPER_MODEL", "small")
    # device: auto / cpu（Apple Silicon 下 CTranslate2 走 CPU）
    whisper_device: str = os.getenv("SUBTRANS_WHISPER_DEVICE", "auto")
    # compute_type: int8 体积小速度快；float32 更准更慢
    whisper_compute_type: str = os.getenv("SUBTRANS_WHISPER_COMPUTE", "int8")
    # 模型缓存目录（None = faster-whisper 默认 ~/.cache）
    whisper_download_root: Optional[Path] = _opt_env_path("SUBTRANS_WHISPER_DIR")

    # --- ④ 翻译（DeepSeek，OpenAI 兼容接口）---
    deepseek_api_key: Optional[str] = (
        os.getenv("SUBTRANS_DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    )
    deepseek_base_url: str = os.getenv("SUBTRANS_DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_model: str = os.getenv("SUBTRANS_DEEPSEEK_MODEL", "deepseek-chat")
    # 每批翻译多少条字幕
    translate_batch_size: int = int(os.getenv("SUBTRANS_TRANSLATE_BATCH", "20"))
    translate_timeout: int = int(os.getenv("SUBTRANS_TRANSLATE_TIMEOUT", "60"))


settings = Settings()
