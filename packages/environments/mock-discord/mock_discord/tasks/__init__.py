"""Task and evaluation framework (stub)."""

from __future__ import annotations

from .base import Task
from .registry import get_task, list_tasks, register_task

__all__ = ["Task", "get_task", "list_tasks", "register_task"]
