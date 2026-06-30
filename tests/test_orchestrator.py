"""流水线编排单测。mock 五步函数，验证事件序列、进度映射与失败处理。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.service import orchestrator
from src.service.orchestrator import PipelineParams, run_pipeline


def _params():
    return PipelineParams(
        task_id="t1",
        url="http://x/v",
        source_lang="auto",
        target_lang="zh-CN",
        mode="mono",
        burn="hard",
        model="small",
    )


def _install_fakes(monkeypatch, *, calls, fail_at=None, percent=100):
    """装上五步假实现：各自调用 on_progress 并返回带必要属性的结果。"""

    def make(name, result):
        def fn(*args, **kwargs):
            calls.append(name)
            if fail_at == name:
                raise RuntimeError(f"{name} boom")
            cb = kwargs.get("on_progress")
            if cb:
                cb(SimpleNamespace(percent=percent))
            return result
        return fn

    monkeypatch.setattr(orchestrator, "download_video",
                        make("download", SimpleNamespace(video_path=Path("/d/source.mp4"), title="My Video")))
    monkeypatch.setattr(orchestrator, "extract_audio",
                        make("extract", SimpleNamespace(audio_path=Path("/d/audio.wav"))))
    monkeypatch.setattr(orchestrator, "transcribe",
                        make("transcribe", SimpleNamespace(srt_path=Path("/d/original.srt"))))
    monkeypatch.setattr(orchestrator, "translate_srt",
                        make("translate", SimpleNamespace(srt_path=Path("/d/translated.srt"))))
    monkeypatch.setattr(orchestrator, "burn_subtitles",
                        make("burn", SimpleNamespace(output_path=Path("/d/output.mp4"))))


def test_pipeline_success_event_sequence(monkeypatch):
    calls = []
    _install_fakes(monkeypatch, calls=calls)
    events = []

    result = run_pipeline(_params(), events.append)

    # 五步都按序调用
    assert calls == ["download", "extract", "transcribe", "translate", "burn"]

    # 状态顺序覆盖五个阶段，最后 SUCCESS
    statuses = [e.status for e in events]
    for s in ["DOWNLOADING", "EXTRACTING", "TRANSCRIBING", "TRANSLATING", "BURNING"]:
        assert s in statuses
    assert statuses[-1] == "SUCCESS"

    # 进度单调不减，结束 100
    progs = [e.progress for e in events]
    assert progs == sorted(progs)
    assert events[-1].progress == 100

    # 成功事件带标题与产物
    assert result.status == "SUCCESS"
    assert result.title == "My Video"
    assert result.outputs == {"video": "/d/output.mp4", "subtitle": "/d/translated.srt"}


def test_pipeline_progress_mapping(monkeypatch):
    # 每步内部 50% -> 应落在该阶段的 band 内
    calls = []
    _install_fakes(monkeypatch, calls=calls, percent=50)
    events = []
    run_pipeline(_params(), events.append)

    by_status = {}
    for e in events:
        by_status.setdefault(e.status, []).append(e.progress)

    # 下载内部 50% -> 0 + 0.5*(20-0) = 10
    assert 10 in by_status["DOWNLOADING"]
    # 识别内部 50% -> 35 + 0.5*(65-35) = 50
    assert 50 in by_status["TRANSCRIBING"]
    # 烧录内部 50% -> 85 + 0.5*(100-85) = 92
    assert 92 in by_status["BURNING"]


def test_pipeline_failure(monkeypatch):
    calls = []
    _install_fakes(monkeypatch, calls=calls, fail_at="transcribe")
    events = []

    with pytest.raises(RuntimeError):
        run_pipeline(_params(), events.append)

    # 识别后续步骤不应执行
    assert "translate" not in calls and "burn" not in calls

    last = events[-1]
    assert last.status == "FAILED"
    assert last.current_step == "TRANSCRIBING"
    assert "boom" in last.error


def test_pipeline_passes_options(monkeypatch):
    """目标语言 / 模式 / 模型 / 烧录方式应透传给对应步骤。"""
    seen = {}

    def fake_transcribe(audio, tid, **kw):
        seen["model"] = kw.get("model_name")
        seen["language"] = kw.get("language")
        return SimpleNamespace(srt_path=Path("/d/original.srt"))

    def fake_translate(srt, tid, src, tgt, **kw):
        seen["target"] = tgt
        seen["mode"] = kw.get("mode")
        return SimpleNamespace(srt_path=Path("/d/translated.srt"))

    def fake_burn(video, srt, tid, **kw):
        seen["burn"] = kw.get("mode")
        return SimpleNamespace(output_path=Path("/d/output.mp4"))

    monkeypatch.setattr(orchestrator, "download_video",
                        lambda *a, **k: SimpleNamespace(video_path=Path("/d/source.mp4"), title="T"))
    monkeypatch.setattr(orchestrator, "extract_audio",
                        lambda *a, **k: SimpleNamespace(audio_path=Path("/d/audio.wav")))
    monkeypatch.setattr(orchestrator, "transcribe", fake_transcribe)
    monkeypatch.setattr(orchestrator, "translate_srt", fake_translate)
    monkeypatch.setattr(orchestrator, "burn_subtitles", fake_burn)

    params = PipelineParams(
        task_id="t1", url="http://x", source_lang="en", target_lang="ja",
        mode="bilingual", burn="soft", model="medium",
    )
    run_pipeline(params, lambda e: None)

    assert seen == {
        "model": "medium", "language": "en",
        "target": "ja", "mode": "bilingual", "burn": "soft",
    }
