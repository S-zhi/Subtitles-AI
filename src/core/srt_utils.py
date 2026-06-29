"""SRT 字幕读写工具。

被 ③识别（写 original.srt）和 ④翻译（读 original.srt、写 translated.srt）共用。
自己实现一份轻量解析/生成，避免引入额外依赖，也方便单测。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class Subtitle:
    """一条字幕。start / end 为秒；text 可含换行（双语时原文/译文两行）。"""

    index: int
    start: float
    end: float
    text: str


def format_timestamp(seconds: float) -> str:
    """秒 -> SRT 时间戳 HH:MM:SS,mmm。"""
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    hours, total_ms = divmod(total_ms, 3_600_000)
    minutes, total_ms = divmod(total_ms, 60_000)
    secs, millis = divmod(total_ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def parse_timestamp(ts: str) -> float:
    """SRT 时间戳 -> 秒。兼容逗号或点作为毫秒分隔符。"""
    ts = ts.strip().replace(".", ",")
    hms, _, millis = ts.partition(",")
    hours, minutes, secs = hms.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + int(secs) + int(millis or 0) / 1000


def write_srt(subs: List[Subtitle], path: Path) -> None:
    """把字幕列表写成 SRT 文件（UTF-8）。序号按顺序重排。"""
    path = Path(path)
    blocks: List[str] = []
    for i, sub in enumerate(subs, start=1):
        blocks.append(
            f"{i}\n"
            f"{format_timestamp(sub.start)} --> {format_timestamp(sub.end)}\n"
            f"{sub.text}".rstrip()
        )
    content = "\n\n".join(blocks)
    if content:
        content += "\n"
    path.write_text(content, encoding="utf-8")


def parse_srt(path: Path) -> List[Subtitle]:
    """解析 SRT 文件为字幕列表。容忍缺序号、多行文本、点/逗号毫秒。"""
    path = Path(path)
    raw = path.read_text(encoding="utf-8-sig")
    subs: List[Subtitle] = []
    for block in re.split(r"\n\s*\n", raw.strip()):
        lines = [ln for ln in block.splitlines()]
        if not lines:
            continue
        # 找到包含 --> 的时间行
        time_idx = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if time_idx is None:
            continue
        start_s, _, end_s = lines[time_idx].partition("-->")
        try:
            start = parse_timestamp(start_s)
            end = parse_timestamp(end_s)
        except (ValueError, IndexError):
            continue
        text = "\n".join(lines[time_idx + 1:]).strip()
        index = len(subs) + 1
        if time_idx == 1:  # 时间行前一行通常是序号
            try:
                index = int(lines[0].strip())
            except ValueError:
                pass
        subs.append(Subtitle(index=index, start=start, end=end, text=text))
    return subs
