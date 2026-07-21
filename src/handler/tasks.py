"""任务相关路由（业务域：tasks）。

新增其它业务时，仿照本文件建一个 APIRouter，再在 app.py 里 include 即可。
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from src.config import OUTPUT_VIDEO, SOURCE_VIDEO_STEM, TRANSLATED_SRT, task_dir
from src.core.downloader import probe_video
from src.handler.deps import get_store
from src.handler.schemas import TaskCreate, TaskOut, TaskProbeIn, TaskProbeOut, to_out
from src.service.runner import enqueue_pipeline
from src.store import TaskStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

_TERMINAL = {"SUCCESS", "FAILED"}

# 允许上传的本地视频扩展名（小写，含点）
_UPLOAD_VIDEO_EXTS = {
    ".mp4", ".mov", ".mkv", ".webm", ".avi",
    ".m4v", ".flv", ".ts", ".mpeg", ".mpg", ".wmv",
}


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
        need_subtitle=body.needSubtitle,
    )
    enqueue_pipeline(rec.id)  # 第 2 步接入真正执行
    return to_out(rec)


@router.post("/upload", response_model=TaskOut, status_code=201)
def create_upload_task(
    file: UploadFile = File(..., description="本地视频文件"),
    sourceLang: str = Form("auto", min_length=1),
    targetLang: str = Form("zh-CN", min_length=1),
    mode: Literal["mono", "bilingual"] = Form("mono"),
    burn: Literal["hard", "soft"] = Form("hard"),
    model: str = Form("small", min_length=1),
    engine: Literal["deepseek"] = Form("deepseek"),
    needSubtitle: bool = Form(True),
    store: TaskStore = Depends(get_store),
) -> TaskOut:
    """上传本地视频并创建任务：源文件直接落盘，跳过下载，走后续识别 / 翻译 / 烧录。

    字幕模式（mode）与烧录方式（burn）与链接任务同样透传到下层流水线。
    """
    filename = (file.filename or "").strip()
    ext = Path(filename).suffix.lower()
    if ext not in _UPLOAD_VIDEO_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的视频格式：{ext or '未知'}（支持 {', '.join(sorted(_UPLOAD_VIDEO_EXTS))}）",
        )

    # 先建记录拿到 task_id，再把源文件落盘到该任务目录
    rec = store.create(
        url=filename,
        source_lang=sourceLang,
        target_lang=targetLang,
        mode=mode,
        burn=burn,
        model=model,
        engine=engine,
        source_type="upload",
        need_subtitle=needSubtitle,
        title=Path(filename).stem or "上传的视频",
    )

    d = task_dir(rec.id)
    d.mkdir(parents=True, exist_ok=True)
    dest = d / f"{SOURCE_VIDEO_STEM}{ext}"
    try:
        with dest.open("wb") as out:
            shutil.copyfileobj(file.file, out)  # 流式写盘，避免整文件入内存
    except Exception as e:
        store.delete(rec.id)
        shutil.rmtree(d, ignore_errors=True)
        raise HTTPException(status_code=500, detail="保存上传文件失败") from e
    finally:
        file.file.close()

    if not dest.exists() or dest.stat().st_size == 0:
        store.delete(rec.id)
        shutil.rmtree(d, ignore_errors=True)
        raise HTTPException(status_code=400, detail="上传的视频文件为空")

    enqueue_pipeline(rec.id)
    return to_out(store.get(rec.id) or rec)


@router.get("", response_model=List[TaskOut])
def list_tasks(store: TaskStore = Depends(get_store)) -> List[TaskOut]:
    return [to_out(r) for r in store.list()]


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: str, store: TaskStore = Depends(get_store)) -> TaskOut:
    return to_out(_require(store, task_id))


@router.post("/probe", response_model=TaskProbeOut)
def probe_task(body: TaskProbeIn) -> TaskProbeOut:
    """探测视频链接是否能被 yt-dlp 解析并找到可下载格式。"""
    result = probe_video(body.url)
    return TaskProbeOut(
        ok=result.ok,
        title=result.title,
        extractor=result.extractor,
        duration=result.duration,
        formatsCount=result.formats_count,
        webpageUrl=result.webpage_url,
        reason=result.reason,
        detail=result.detail,
    )


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: str, store: TaskStore = Depends(get_store)) -> None:
    """仅允许删除终态任务，避免运行中流水线继续写回孤儿产物。"""
    rec = _require(store, task_id)
    if rec.status not in _TERMINAL:
        raise HTTPException(status_code=409, detail="运行中任务不能删除")
    store.delete(task_id)
    shutil.rmtree(task_dir(task_id), ignore_errors=True)  # 连产物目录一起清


@router.post("/{task_id}/retry", response_model=TaskOut)
def retry_task(task_id: str, store: TaskStore = Depends(get_store)) -> TaskOut:
    """仅允许失败任务重新入队，避免运行中任务重复执行。"""
    rec = _require(store, task_id)
    if rec.status != "FAILED":
        raise HTTPException(status_code=409, detail="只有失败任务可以重试")
    updated = store.update(
        task_id,
        status="PENDING",
        progress=0,
        current_step=None,
        error=None,
    )
    enqueue_pipeline(task_id)
    return to_out(updated)


# ---------- 文件下载 ----------

@router.get("/{task_id}/download")
def download_video(task_id: str, store: TaskStore = Depends(get_store)):
    _require(store, task_id)
    path = _resolve_video(task_id)
    if path is None:
        raise HTTPException(status_code=409, detail="成品视频尚未生成")
    return FileResponse(path, media_type="video/mp4", filename=f"{task_id}.mp4")


def _resolve_video(task_id: str):
    """定位可下载的视频：优先烧录成品 output.mp4，仅下载模式回退到 source.*。"""
    d = task_dir(task_id)
    out = d / OUTPUT_VIDEO
    if out.exists():
        return out
    for p in sorted(d.glob(f"{SOURCE_VIDEO_STEM}.*")):
        return p
    return None


@router.get("/{task_id}/subtitle")
def download_subtitle(task_id: str, store: TaskStore = Depends(get_store)):
    _require(store, task_id)
    path = task_dir(task_id) / TRANSLATED_SRT
    if not path.exists():
        raise HTTPException(status_code=409, detail="译文字幕尚未生成")
    return FileResponse(path, media_type="application/x-subrip", filename=f"{task_id}.srt")


@router.post("/{task_id}/folder", summary="打开任务文件夹")
def open_task_folder(task_id: str, store: TaskStore = Depends(get_store)) -> dict:
    """用系统文件管理器打开任务产物目录。"""
    _require(store, task_id)
    path = task_dir(task_id)
    if not path.exists():
        raise HTTPException(status_code=409, detail="任务目录尚未生成")
    _open_folder(path)
    return {"ok": True}


def _open_folder(path) -> None:
    """按当前系统选择文件管理器打开目录。"""
    if sys.platform == "darwin":
        cmd = ["open", str(path)]
    elif sys.platform.startswith("win"):
        cmd = ["explorer", str(path)]
    else:
        cmd = ["xdg-open", str(path)]
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail="当前系统不支持打开文件夹") from e


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
