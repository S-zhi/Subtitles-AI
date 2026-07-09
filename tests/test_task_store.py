"""任务存储（SQLite）单测。"""

from __future__ import annotations

import time

import pytest

from src.store import TaskRecord, TaskStore


@pytest.fixture
def store(tmp_path):
    return TaskStore(tmp_path / "app.db")


def _create(store, **over):
    fields = dict(
        url="http://x/v",
        source_lang="auto",
        target_lang="zh-CN",
        mode="mono",
        burn="hard",
        model="small",
        engine="deepseek",
    )
    fields.update(over)
    return store.create(**fields)


def test_create_defaults(store):
    rec = _create(store)
    assert rec.id.startswith("task_")
    assert rec.status == "PENDING"
    assert rec.progress == 0
    assert rec.created_at > 0
    assert rec.created_at == rec.updated_at


def test_get_roundtrip(store):
    rec = _create(store)
    got = store.get(rec.id)
    assert got is not None
    assert got == rec  # dataclass 相等


def test_create_defaults_source_type_url(store):
    rec = _create(store)
    assert rec.source_type == "url"


def test_create_upload_persists_source_type_and_title(store):
    rec = _create(store, source_type="upload", title="my clip")
    got = store.get(rec.id)
    assert got.source_type == "upload"
    assert got.title == "my clip"


def test_get_missing(store):
    assert store.get("nope") is None


def test_list_newest_first(store):
    a = _create(store)
    time.sleep(0.002)
    b = _create(store)
    ids = [r.id for r in store.list()]
    assert ids[0] == b.id and ids[1] == a.id


def test_update_partial(store):
    rec = _create(store)
    before = rec.updated_at
    time.sleep(0.002)
    updated = store.update(rec.id, status="TRANSCRIBING", progress=42, current_step="TRANSCRIBING")
    assert updated.status == "TRANSCRIBING"
    assert updated.progress == 42
    assert updated.current_step == "TRANSCRIBING"
    assert updated.updated_at > before
    # url 等未传字段保持不变
    assert updated.url == rec.url


def test_update_outputs_and_title(store):
    rec = _create(store)
    updated = store.update(
        rec.id, status="SUCCESS", progress=100,
        title="My Video", output_video="/d/output.mp4", output_subtitle="/d/translated.srt",
    )
    assert updated.title == "My Video"
    assert updated.output_video == "/d/output.mp4"
    assert updated.output_subtitle == "/d/translated.srt"


def test_update_ignores_unknown_field(store):
    rec = _create(store)
    updated = store.update(rec.id, bogus="x", progress=5)
    assert updated.progress == 5
    assert not hasattr(updated, "bogus")


def test_update_missing_returns_none(store):
    assert store.update("nope", progress=1) is None


def test_delete(store):
    rec = _create(store)
    assert store.delete(rec.id) is True
    assert store.get(rec.id) is None
    assert store.delete(rec.id) is False


def test_persistence_across_instances(tmp_path):
    path = tmp_path / "app.db"
    s1 = TaskStore(path)
    rec = _create(s1)
    s2 = TaskStore(path)  # 新实例读同一文件
    assert s2.get(rec.id) == rec
