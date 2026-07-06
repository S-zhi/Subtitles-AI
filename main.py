"""命令行入口：按 README 约定直接运行完整字幕流水线。"""

from __future__ import annotations

import argparse
import uuid
from typing import Sequence

from src.service.orchestrator import PipelineEvent, PipelineParams, run_pipeline


def _new_task_id() -> str:
    """生成默认任务 ID，用于决定 data/{task_id}/ 产物目录。"""
    return "task_" + uuid.uuid4().hex[:8]


def _build_parser() -> argparse.ArgumentParser:
    """构造 README 承诺的命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="下载视频、转写字幕、翻译字幕并输出成品视频。"
    )
    parser.add_argument("url", help="视频页面地址")
    parser.add_argument("-t", "--target", default="zh-CN", help="目标语言")
    parser.add_argument("-s", "--source", default="auto", help="源语言")
    parser.add_argument(
        "--mode",
        choices=("mono", "bilingual"),
        default="mono",
        help="字幕模式：mono 仅译文，bilingual 双语对照",
    )
    parser.add_argument(
        "--burn",
        choices=("hard", "soft"),
        default="hard",
        help="烧录方式：hard 硬烧录，soft 软字幕",
    )
    parser.add_argument("--model", default="small", help="Whisper 模型权重")
    parser.add_argument("--task-id", default=None, help="指定任务 ID")
    return parser


def _print_event(event: PipelineEvent) -> None:
    """把流水线事件输出为适合终端查看的一行进度。"""
    step = f" {event.current_step}" if event.current_step else ""
    print(f"[{event.progress:3d}%] {event.status}{step}")
    if event.error:
        print(f"error: {event.error}")
    if event.outputs:
        print(f"video: {event.outputs.get('video')}")
        print(f"subtitle: {event.outputs.get('subtitle')}")


def run_cli(argv: Sequence[str] | None = None) -> int:
    """解析命令行参数并执行完整字幕流水线。"""
    args = _build_parser().parse_args(argv)
    params = PipelineParams(
        task_id=args.task_id or _new_task_id(),
        url=args.url,
        source_lang=args.source,
        target_lang=args.target,
        mode=args.mode,
        burn=args.burn,
        model=args.model,
    )
    run_pipeline(params, _print_event)
    return 0


def main() -> None:
    """作为脚本入口运行 CLI。"""
    raise SystemExit(run_cli())


if __name__ == "__main__":
    main()
