"""Base task class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Task(ABC):
    name: str
    description: str
    instruction: str
    category: str
    scenario: str = "default"
    points: float = 1.0
    tags: list[str] = field(default_factory=list)

    @abstractmethod
    def evaluate(
        self,
        final_state: dict,
        diff: dict,
        action_log: list[dict],
    ) -> tuple[float, bool]:
        ...

    def get_initial_setup(self) -> dict | None:
        return None
