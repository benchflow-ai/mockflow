"""Task registry."""

from __future__ import annotations

from .base import Task

_REGISTRY: dict[str, Task] = {}


def register_task(task: Task):
    _REGISTRY[task.name] = task


def get_task(name: str) -> Task | None:
    return _REGISTRY.get(name)


def list_tasks() -> list[str]:
    return list(_REGISTRY.keys())
