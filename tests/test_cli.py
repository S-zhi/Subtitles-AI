"""命令行入口单测。"""

from __future__ import annotations

import main as cli
from src.service.orchestrator import PipelineEvent


def test_cli_passes_readme_options(monkeypatch):
    """README 中声明的 CLI 参数应透传为 PipelineParams。"""
    seen = {}

    def fake_run_pipeline(params, on_event):
        seen["params"] = params
        on_event(PipelineEvent("SUCCESS", 100, None))

    monkeypatch.setattr(cli, "run_pipeline", fake_run_pipeline)

    code = cli.run_cli([
        "https://example.com/video",
        "--target", "ja",
        "--source", "en",
        "--mode", "bilingual",
        "--burn", "soft",
        "--model", "medium",
        "--task-id", "task_custom",
    ])

    params = seen["params"]
    assert code == 0
    assert params.task_id == "task_custom"
    assert params.url == "https://example.com/video"
    assert params.source_lang == "en"
    assert params.target_lang == "ja"
    assert params.mode == "bilingual"
    assert params.burn == "soft"
    assert params.model == "medium"


def test_cli_generates_default_task_id(monkeypatch):
    """未显式传入 --task-id 时 CLI 应自动生成 task_ 前缀任务 ID。"""
    seen = {}
    monkeypatch.setattr(cli, "_new_task_id", lambda: "task_auto")

    def fake_run_pipeline(params, on_event):
        seen["params"] = params
        on_event(PipelineEvent("SUCCESS", 100, None))

    monkeypatch.setattr(cli, "run_pipeline", fake_run_pipeline)

    cli.run_cli(["https://example.com/video"])

    params = seen["params"]
    assert params.task_id == "task_auto"
    assert params.source_lang == "auto"
    assert params.target_lang == "zh-CN"
    assert params.mode == "mono"
    assert params.burn == "hard"
    assert params.model == "small"
