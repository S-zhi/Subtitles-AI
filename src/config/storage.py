"""存储路径策略。

每个任务一个目录：data/{task_id}/，所有中间产物与成品都落在里面。
好处：断点续跑只需检查文件是否存在；清理任务只需删一个目录；
DB 只存相对信息，不依赖绝对路径历史。
"""

from __future__ import annotations

from pathlib import Path

from .config import settings

# 流水线各阶段的标准产物文件名（stem，不含扩展名的固定基名）
SOURCE_VIDEO_STEM = "source"      # 下载的原始视频 source.mp4
AUDIO_FILENAME = "audio.wav"      # 提取的音频
ORIGINAL_SRT = "original.srt"     # 识别出的原文字幕
TRANSLATED_SRT = "translated.srt"  # 翻译后的字幕
OUTPUT_VIDEO = "output.mp4"       # 烧录后的成品


def task_dir(task_id: str) -> Path:
    """返回任务目录路径（不保证存在）。"""
    return settings.data_dir / task_id


def ensure_task_dir(task_id: str) -> Path:
    """返回任务目录路径，并确保已创建。"""
    d = task_dir(task_id)
    d.mkdir(parents=True, exist_ok=True)
    return d
