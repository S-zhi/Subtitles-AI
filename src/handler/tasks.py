"""任务相关路由（业务域：tasks）。

新增其它业务时，仿照本文件建一个 APIRouter，再在 app.py 里 include 即可。
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from src.config import OUTPUT_VIDEO, TRANSLATED_SRT, task_dir
from src.handler.deps import get_store
from src.handler.schemas import TaskCreate, TaskOut, to_out
from src.service.runner import enqueue_pipeline
from src.store import TaskStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

_TERMINAL = {"SUCCESS", "FAILED"}


def _require(store: TaskStore, task_id: str):
    rec = store.get(task_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return rec


# ---------- CRUD ----------

@router.post("", response_model=TaskOut, status_code=201)
def create_task(body: TaskCreate, store: TaskStore = Depends(get_store)) -> TaskOut:
    rec = store.create(
        url=body.url,
        source_lang=body.sourceLang,
        target_lang=body.targetLang,
        mode=body.mode,
        burn=body.burn,
        model=body.model,
        engine=body.engine,
    )
    enqueue_pipeline(rec.id)  # 第 2 步接入真正执行
    return to_out(rec)


@router.get("", response_model=List[TaskOut])
def list_tasks(store: TaskStore = Depends(get_store)) -> List[TaskOut]:
    return [to_out(r) for r in store.list()]


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: str, store: TaskStore = Depends(get_store)) -> TaskOut:
    return to_out(_require(store, task_id))


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: str, store: TaskStore = Depends(get_store)) -> None:
    _require(store, task_id)
    store.delete(task_id)
    shutil.rmtree(task_dir(task_id), ignore_errors=True)  # 连产物目录一起清


@router.post("/{task_id}/retry", response_model=TaskOut)
def retry_task(task_id: str, store: TaskStore = Depends(get_store)) -> TaskOut:
    _require(store, task_id)
    store.update(task_id, status="PENDING", progress=0, current_step=None, error=None)
    enqueue_pipeline(task_id)
    return to_out(store.get(task_id))


# ---------- 文件下载 ----------

@router.get("/{task_id}/download")
def download_video(task_id: str, store: TaskStore = Depends(get_store)):
    _require(store, task_id)
    path = task_dir(task_id) / OUTPUT_VIDEO
    if not path.exists():
        raise HTTPException(status_code=409, detail="成品视频尚未生成")
    return FileResponse(path, media_type="video/mp4", filename=f"{task_id}.mp4")


@router.get("/{task_id}/subtitle")
def download_subtitle(task_id: str, store: TaskStore = Depends(get_store)):
    _require(store, task_id)
    path = task_dir(task_id) / TRANSLATED_SRT
    if not path.exists():
        raise HTTPException(status_code=409, detail="译文字幕尚未生成")
    return FileResponse(path, media_type="application/x-subrip", filename=f"{task_id}.srt")


# ---------- SSE 进度 ----------

def _sse_payload(rec) -> str:
    data = {
        "id": rec.id,
        "status": rec.status,
        "progress": rec.progress,
        "currentStep": rec.current_step,
        "title": rec.title,
        "error": rec.error,
        "outputs": to_out(rec).outputs,
    }
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/{task_id}/stream")
def stream_progress(task_id: str, store: TaskStore = Depends(get_store)):
    """轮询库表并以 SSE 推送进度（方案 A 足够；将来可换事件驱动）。"""
    _require(store, task_id)

    def gen():
        last = None
        for _ in range(3600):  # 上限 ~1 小时
            rec = store.get(task_id)
            if rec is None:
                yield 'data: {"error":"任务不存在"}\n\n'
                return
            snapshot = (rec.status, rec.progress)
            if snapshot != last:
                yield _sse_payload(rec)
                last = snapshot
            if rec.status in _TERMINAL:
                return
            time.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream")
