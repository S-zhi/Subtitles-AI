"""路由共享依赖。"""

from __future__ import annotations

from src.config import settings
from src.store import TaskStore

# 存储单例（懒加载，便于测试用依赖覆盖替换）
_store: TaskStore | None = None


def get_store() -> TaskStore:
    global _store
    if _store is None:
        _store = TaskStore(settings.db_path)
    return _store
