from __future__ import annotations

from typing import Any

from .base import SummarizerProvider
from ..heuristic import summarize_heuristic
from ..contract import validate_summary


class HeuristicProvider(SummarizerProvider):
    name = "heuristic"
    model = "heuristic-v0.1"

    def summarize(self, text: str) -> dict[str, Any]:
        result = summarize_heuristic(text)
        result.pop("_meta", None)
        return validate_summary(result)
