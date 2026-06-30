"""流水线编排：把 ①~⑤ 串成一条任务，逐步上报进度。

设计为纯逻辑：不碰数据库 / Redis，只通过 on_event 回调把状态与进度往外抛。
Worker 层把 on_event 接到「写 SQLite + 发 SSE」即可。

各步的内部百分比按权重映射到整体 0-100：
  下载 0-20 · 提取 20-35 · 识别 35-65 · 翻译 65-85 · 烧录 85-100
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional

from src.core.audio_extractor import extract_audio
from src.core.downloader import download_video
from src.core.subtitle_burner import burn_subtitles
from src.core.transcriber import transcribe
from src.core.translator import translate_srt

logger = logging.getLogger(__name__)


@dataclass
class PipelineParams:
    task_id: str
    url: str
    source_lang: str
    target_lang: str
    mode: str = "mono"     # mono | bilingual
    burn: str = "hard"     # hard | soft
    model: str = "small"
    engine: str = "deepseek"


@dataclass
class PipelineEvent:
    status: str
    progress: int
    current_step: Optional[str]
    title: Optional[str] = None
    error: Optional[str] = None
    outputs: Optional[dict] = None


EventHook = Callable[[PipelineEvent], None]

# (status, 整体进度下界, 上界)
_BANDS = {
    "DOWNLOADING": (0, 20),
    "EXTRACTING": (20, 35),
    "TRANSCRIBING": (35, 65),
    "TRANSLATING": (65, 85),
    "BURNING": (85, 100),
}


def _scale(lo: int, hi: int, pct: Optional[float]) -> int:
    if pct is None:
        return lo
    return int(lo + max(0.0, min(100.0, pct)) / 100.0 * (hi - lo))


def run_pipeline(
    params: PipelineParams,
    on_event: EventHook,
    *,
    api_key: Optional[str] = None,
) -> PipelineEvent:
    """顺序执行五步。成功返回最终 SUCCESS 事件；失败发 FAILED 事件并抛出。"""
    tid = params.task_id
    state = {"progress": 0, "step": None}

    def emit(status: str, progress: int, **extra) -> None:
        state["progress"] = max(state["progress"], progress)
        state["step"] = status if status in _BANDS else None
        on_event(PipelineEvent(
            status=status,
            progress=state["progress"],
            current_step=state["step"],
            **extra,
        ))

    def step_cb(status: str):
        lo, hi = _BANDS[status]

        def cb(p) -> None:
            prog = _scale(lo, hi, getattr(p, "percent", None))
            emit(status, prog)

        return cb

    try:
        emit("DOWNLOADING", 0)
        dl = download_video(params.url, tid, on_progress=step_cb("DOWNLOADING"))

        emit("EXTRACTING", 20)
        au = extract_audio(dl.video_path, tid, on_progress=step_cb("EXTRACTING"))

        emit("TRANSCRIBING", 35)
        tr = transcribe(
            au.audio_path, tid,
            language=params.source_lang,
            model_name=params.model,
            on_progress=step_cb("TRANSCRIBING"),
        )

        emit("TRANSLATING", 65)
        tl = translate_srt(
            tr.srt_path, tid,
            params.source_lang, params.target_lang,
            mode=params.mode,
            on_progress=step_cb("TRANSLATING"),
            api_key=api_key,
        )

        emit("BURNING", 85)
        bn = burn_subtitles(
            dl.video_path, tl.srt_path, tid,
            mode=params.burn,
            on_progress=step_cb("BURNING"),
        )

        outputs = {"video": str(bn.output_path), "subtitle": str(tl.srt_path)}
        final = PipelineEvent("SUCCESS", 100, None, title=dl.title, outputs=outputs)
        on_event(final)
        logger.info("流水线完成: task=%s", tid)
        return final

    except Exception as e:
        logger.exception("流水线失败: task=%s step=%s", tid, state["step"])
        on_event(PipelineEvent(
            status="FAILED",
            progress=state["progress"],
            current_step=state["step"],
            error=str(e),
        ))
        raise
