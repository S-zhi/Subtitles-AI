"""API 层单测。用 FastAPI TestClient + 隔离的临时 DB（依赖覆盖）。

执行（pipeline）在第 1 步是占位，所以这里只验证 CRUD / 文件下载 / 校验，
不涉及真实跑流水线。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.handler import tasks as tasks_routes
from src.handler.app import app
from src.handler.deps import get_store
from src.store import TaskStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    store = TaskStore(tmp_path / "test.db")
    # 覆盖 store 依赖 -> 临时库
    app.dependency_overrides[get_store] = lambda: store
    # 下载端点用 task_dir 定位文件 -> 指向临时目录
    monkeypatch.setattr(tasks_routes, "task_dir", lambda tid: tmp_path / tid)
    # 不在 API 测试里真跑流水线（执行器单独测）
    monkeypatch.setattr(tasks_routes, "enqueue_pipeline", lambda task_id: None)
    with TestClient(app) as c:
        c._store = store
        c._tmp = tmp_path
        yield c
    app.dependency_overrides.clear()


def _payload(**over):
    body = {
        "url": "https://example.com/v",
        "sourceLang": "auto",
        "targetLang": "zh-CN",
        "mode": "mono",
        "burn": "hard",
        "model": "small",
        "engine": "deepseek",
    }
    body.update(over)
    return body


# ---------- 创建 ----------

def test_create_task(client):
    r = client.post("/api/tasks", json=_payload())
    assert r.status_code == 201
    data = r.json()
    assert data["id"].startswith("task_")
    assert data["status"] == "PENDING"
    assert data["progress"] == 0
    # camelCase 字段对齐前端
    assert data["sourceLang"] == "auto"
    assert data["targetLang"] == "zh-CN"
    assert data["outputs"] is None
    assert data["createdAt"] > 0


def test_create_defaults_when_minimal(client):
    r = client.post("/api/tasks", json={"url": "https://x/y"})
    assert r.status_code == 201
    data = r.json()
    assert data["targetLang"] == "zh-CN" and data["mode"] == "mono"


def test_create_missing_url_422(client):
    r = client.post("/api/tasks", json={"targetLang": "zh-CN"})
    assert r.status_code == 422


def test_create_rejects_invalid_enum_params(client, monkeypatch):
    """非法枚举参数应在创建前返回 422，且不能入队。"""
    enqueued = []
    monkeypatch.setattr(tasks_routes, "enqueue_pipeline", enqueued.append)

    assert client.post("/api/tasks", json=_payload(mode="mixed")).status_code == 422
    assert client.post("/api/tasks", json=_payload(burn="weird")).status_code == 422
    assert client.post("/api/tasks", json=_payload(engine="other")).status_code == 422
    assert enqueued == []


def test_create_rejects_empty_model_and_languages(client, monkeypatch):
    """模型和语言字段为空时应在创建前返回 422，且不能入队。"""
    enqueued = []
    monkeypatch.setattr(tasks_routes, "enqueue_pipeline", enqueued.append)

    assert client.post("/api/tasks", json=_payload(model="")).status_code == 422
    assert client.post("/api/tasks", json=_payload(sourceLang="")).status_code == 422
    assert client.post("/api/tasks", json=_payload(targetLang="")).status_code == 422
    assert enqueued == []


# ---------- 查询 ----------

def test_list_tasks(client):
    client.post("/api/tasks", json=_payload())
    client.post("/api/tasks", json=_payload(url="https://x/2"))
    r = client.get("/api/tasks")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_get_task(client):
    cid = client.post("/api/tasks", json=_payload()).json()["id"]
    r = client.get(f"/api/tasks/{cid}")
    assert r.status_code == 200 and r.json()["id"] == cid


def test_get_missing_404(client):
    assert client.get("/api/tasks/nope").status_code == 404


# ---------- 删除 ----------

def test_delete_task(client):
    cid = client.post("/api/tasks", json=_payload()).json()["id"]
    # 造个产物目录，验证会被清理
    d = client._tmp / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "output.mp4").write_bytes(b"x")

    assert client.delete(f"/api/tasks/{cid}").status_code == 204
    assert client.get(f"/api/tasks/{cid}").status_code == 404
    assert not d.exists()


def test_delete_missing_404(client):
    assert client.delete("/api/tasks/nope").status_code == 404


# ---------- 重试 ----------

def test_retry_resets_status(client, monkeypatch):
    """失败任务重试时应重置状态并重新入队。"""
    cid = client.post("/api/tasks", json=_payload()).json()["id"]
    client._store.update(cid, status="FAILED", progress=40, error="boom")
    enqueued = []
    monkeypatch.setattr(tasks_routes, "enqueue_pipeline", enqueued.append)

    r = client.post(f"/api/tasks/{cid}/retry")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "PENDING"
    assert data["progress"] == 0
    assert data["error"] is None
    assert enqueued == [cid]


def test_retry_running_task_returns_409(client, monkeypatch):
    """运行中任务重试应返回 409 且不能重复入队。"""
    cid = client.post("/api/tasks", json=_payload()).json()["id"]
    client._store.update(cid, status="DOWNLOADING", progress=10, current_step="DOWNLOADING")
    enqueued = []
    monkeypatch.setattr(tasks_routes, "enqueue_pipeline", enqueued.append)

    r = client.post(f"/api/tasks/{cid}/retry")

    assert r.status_code == 409
    assert enqueued == []
    rec = client._store.get(cid)
    assert rec.status == "DOWNLOADING"
    assert rec.progress == 10


# ---------- 文件下载 ----------

def test_download_409_when_not_ready(client):
    cid = client.post("/api/tasks", json=_payload()).json()["id"]
    assert client.get(f"/api/tasks/{cid}/download").status_code == 409
    assert client.get(f"/api/tasks/{cid}/subtitle").status_code == 409


def test_download_serves_file(client):
    cid = client.post("/api/tasks", json=_payload()).json()["id"]
    d = client._tmp / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "output.mp4").write_bytes(b"VIDEO")
    (d / "translated.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")

    r = client.get(f"/api/tasks/{cid}/download")
    assert r.status_code == 200 and r.content == b"VIDEO"
    r2 = client.get(f"/api/tasks/{cid}/subtitle")
    assert r2.status_code == 200 and "hi" in r2.text


def test_success_task_exposes_outputs(client):
    cid = client.post("/api/tasks", json=_payload()).json()["id"]
    client._store.update(cid, status="SUCCESS", progress=100)
    data = client.get(f"/api/tasks/{cid}").json()
    assert data["outputs"]["video"] == f"/api/tasks/{cid}/download"
    assert data["outputs"]["subtitle"] == f"/api/tasks/{cid}/subtitle"


def test_health(client):
    assert client.get("/api/health").json() == {"ok": True}


# ---------- CORS ----------

def test_cors_allows_local_workbench_origin(client):
    r = client.options(
        "/api/tasks",
        headers={
            "Origin": "http://localhost:5273",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5273"


def test_cors_rejects_untrusted_origin(client):
    r = client.options(
        "/api/tasks",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.status_code == 400
    assert "access-control-allow-origin" not in r.headers
