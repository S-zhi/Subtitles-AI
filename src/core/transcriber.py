"""流水线第③步：语音识别（faster-whisper）。

输入：audio.wav（提取阶段产物） + 任务 ID
输出：TranscribeResult（其中 srt_path 指向 data/{task_id}/original.srt）

用 faster-whisper（基于 CTranslate2）把音频转成带时间戳的原文字幕。
在 Apple Silicon 上走 CPU + int8，速度与精度的折中。

进度通过 on_progress 回调透传：faster-whisper 的 transcribe 返回一个段落生成器，
按 segment.end / 总时长 估算百分比。

依赖：faster-whisper（懒加载，未安装时本模块仍可 import，便于单测 mock）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from src.config import settings, ensure_task_dir, ORIGINAL_SRT
from src.core.srt_utils import Subtitle, write_srt

logger = logging.getLogger(__name__)


class TranscribeError(RuntimeError):
    """语音识别阶段失败。"""


@dataclass
class TranscribeProgress:
    percent: Optional[float]
    processed_seconds: float
    total_seconds: Optional[float]


@dataclass
class TranscribeResult:
    srt_path: Path
    language: str
    language_probability: Optional[float]
    segment_count: int
    duration: Optional[float]


ProgressHook = Callable[[TranscribeProgress], None]


def _load_model(model_size: str, device: str, compute_type: str, download_root: Optional[str]):
    """懒加载 WhisperModel。单独抽出便于单测 monkeypatch。"""
    from faster_whisper import WhisperModel

    return WhisperModel(
        model_size,
        device=device,
        compute_type=compute_type,
        download_root=download_root,
    )


def transcribe(
    audio_path: Path | str,
    task_id: str,
    on_progress: Optional[ProgressHook] = None,
    *,
    language: Optional[str] = None,
    model_size: Optional[str] = None,
    device: Optional[str] = None,
    compute_type: Optional[str] = None,
) -> TranscribeResult:
    """把音频识别为原文字幕 data/{task_id}/original.srt。

    Args:
        audio_path: 输入音频（通常是 audio.wav）。
        task_id: 任务 ID，决定输出目录。
        on_progress: 可选进度回调。
        language: 源语言代码；None / "" / "auto" 表示自动检测。
        model_size / device / compute_type: 覆盖配置默认值。

    Raises:
        TranscribeError: 输入不存在、模型加载或识别失败。
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise TranscribeError(f"输入音频不存在: {audio_path}")

    model_size = model_size or settings.whisper_model
    device = device or settings.whisper_device
    compute_type = compute_type or settings.whisper_compute_type
    lang = None if language in (None, "", "auto") else language

    out_dir = ensure_task_dir(task_id)
    srt_path = out_dir / ORIGINAL_SRT

    download_root = (
        str(settings.whisper_download_root) if settings.whisper_download_root else None
    )

    logger.info("开始识别: task=%s model=%s device=%s", task_id, model_size, device)
    try:
        model = _load_model(model_size, device, compute_type, download_root)
        segments_iter, info = model.transcribe(str(audio_path), language=lang)
    except Exception as e:
        raise TranscribeError(f"语音识别失败: {e}") from e

    total = getattr(info, "duration", None)
    subs: List[Subtitle] = []
    try:
        for seg in segments_iter:
            text = (getattr(seg, "text", "") or "").strip()
            if text:
                subs.append(
                    Subtitle(
                        index=len(subs) + 1,
                        start=float(getattr(seg, "start", 0.0)),
                        end=float(getattr(seg, "end", 0.0)),
                        text=text,
                    )
                )
            if on_progress is not None:
                _emit(on_progress, float(getattr(seg, "end", 0.0)), total)
    except Exception as e:
        raise TranscribeError(f"语音识别过程中出错: {e}") from e

    write_srt(subs, srt_path)
    if on_progress is not None:
        last = total if total else (subs[-1].end if subs else 0.0)
        _emit(on_progress, last, total, force_full=True)

    detected = getattr(info, "language", None) or lang or "unknown"
    result = TranscribeResult(
        srt_path=srt_path,
        language=detected,
        language_probability=getattr(info, "language_probability", None),
        segment_count=len(subs),
        duration=total,
    )
    logger.info(
        "识别完成: task=%s lang=%s segments=%d", task_id, detected, len(subs)
    )
    return result


def _emit(
    hook: ProgressHook,
    processed: float,
    total: Optional[float],
    *,
    force_full: bool = False,
) -> None:
    pct: Optional[float]
    if force_full:
        pct = 100.0 if total else None
    elif total and total > 0:
        pct = max(0.0, min(100.0, processed / total * 100.0))
    else:
        pct = None
    try:
        hook(TranscribeProgress(
            percent=round(pct, 1) if pct is not None else None,
            processed_seconds=processed,
            total_seconds=total,
        ))
    except Exception:
        logger.exception("进度回调异常，已忽略")


if __name__ == "__main__":
    # 独立测试入口：python -m src.core.transcriber <audio.wav> [task_id] [language]
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if len(sys.argv) < 2:
        print("用法: python -m src.core.transcriber <audio_path> [task_id] [language]")
        raise SystemExit(1)

    audio = sys.argv[1]
    task = sys.argv[2] if len(sys.argv) > 2 else "manual_test"
    lang = sys.argv[3] if len(sys.argv) > 3 else None

    def _p(p: TranscribeProgress) -> None:
        if p.percent is not None:
            print(f"\r识别中 {p.percent:5.1f}%", end="", flush=True)

    res = transcribe(audio, task, on_progress=_p, language=lang)
    print("\n识别结果:")
    print(f"  字幕: {res.srt_path}")
    print(f"  语言: {res.language} (p={res.language_probability})")
    print(f"  段数: {res.segment_count}")
    print(f"  时长: {res.duration}")
