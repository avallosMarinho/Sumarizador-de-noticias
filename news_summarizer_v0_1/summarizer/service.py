from __future__ import annotations

from pathlib import Path

from .heuristic import summarize_heuristic
from .ollama_provider import summarize_with_ollama
from .reader import read_txt


def summarize_text(text: str, provider: str = "auto", model: str = "qwen3:4b") -> dict:
    provider = provider.lower().strip()

    if provider == "heuristic":
        return summarize_heuristic(text)

    if provider == "ollama":
        return summarize_with_ollama(text, model=model)

    if provider == "auto":
        try:
            return summarize_with_ollama(text, model=model)
        except Exception as exc:
            result = summarize_heuristic(text)
            result["_meta"]["observacao"] = (
                "O Ollama não pôde ser usado; o programa caiu automaticamente "
                f"para o modo heurístico. Motivo: {exc}"
            )
            return result

    raise ValueError("Provider inválido. Use auto, ollama ou heuristic.")


def summarize_file(path: Path, provider: str = "auto", model: str = "qwen3:4b") -> dict:
    text = read_txt(path)

    # Limite simples de segurança para a v0.1.
    if len(text) > 120_000:
        text = text[:120_000]

    return summarize_text(text, provider=provider, model=model)
