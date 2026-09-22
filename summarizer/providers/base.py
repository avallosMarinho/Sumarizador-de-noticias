from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SummarizerProvider(ABC):
    """Contrato comum para qualquer mecanismo de sumarização."""

    name: str
    model: str

    @abstractmethod
    def summarize(self, text: str) -> dict[str, Any]:
        """Recebe uma notícia em texto e devolve o resumo padronizado."""
        raise NotImplementedError
