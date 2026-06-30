"""API 请求 / 响应模型。

字段用 camelCase，直接对齐前端契约（web/app.js 的 RealApi），
这样前端切真实后端时无需改字段。
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from src.store import TaskRecord


class TaskCreate(BaseModel):
    """POST /api/tasks 的请求体。"""

    url: str
    sourceLang: str = "auto"
    targetLang: str = "zh-CN"
    mode: str = "mono"        # mono | bilingual
    burn: str = "hard"        # hard | soft
    model: str = "small"
    engine: str = "deepseek"


class TaskOut(BaseModel):
    """任务对象的响应形态。"""

    id: str
    url: str
    title: Optional[str]
    sourceLang: str
    targetLang: str
    mode: str
    burn: str
    model: str
    engine: str
    status: str
    progress: int
    currentStep: Optional[str]
    error: Optional[str]
    outputs: Optional[dict]
    createdAt: int
    updatedAt: int


def to_out(rec: TaskRecord) -> TaskOut:
    """TaskRecord(snake_case) -> TaskOut(camelCase)。"""
    outputs = None
    if rec.status == "SUCCESS":
        outputs = {
            "video": f"/api/tasks/{rec.id}/download",
            "subtitle": f"/api/tasks/{rec.id}/subtitle",
        }
    return TaskOut(
        id=rec.id,
        url=rec.url,
        title=rec.title,
        sourceLang=rec.source_lang,
        targetLang=rec.target_lang,
        mode=rec.mode,
        burn=rec.burn,
        model=rec.model,
        engine=rec.engine,
        status=rec.status,
        progress=rec.progress,
        currentStep=rec.current_step,
        error=rec.error,
        outputs=outputs,
        createdAt=rec.created_at,
        updatedAt=rec.updated_at,
    )
