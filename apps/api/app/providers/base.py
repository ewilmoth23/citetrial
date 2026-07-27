from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderResult:
    content: str
    usage: dict[str, Any] = field(default_factory=dict)


class ModelProvider(ABC):
    @property
    @abstractmethod
    def leaves_device(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> tuple[bool, str]:
        raise NotImplementedError

    @abstractmethod
    async def complete(
        self, system: str, user: str, *, temperature: float | None = None
    ) -> ProviderResult:
        raise NotImplementedError
