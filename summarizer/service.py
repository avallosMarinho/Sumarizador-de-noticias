from __future__ import annotations

from pathlib import Path
from time import perf_counter

from .providers import (
    GeminiProvider,
    HeuristicProvider,
    OllamaProvider,
    SummarizerProvider,
)
from .reader import read_txt


def build_provider(provider: str, model: str | None = None) -> SummarizerProvider:
    provider = provider.lower().strip()

    if provider == "heuristic":
        return HeuristicProvider()

    if provider == "ollama":
        return OllamaProvider(model=model)

    if provider == "gemini":
        return GeminiProvider(model=model)

    raise ValueError("Provider inválido. Use auto, ollama, gemini ou heuristic.")


def _run_provider(text: str, engine: SummarizerProvider) -> dict:
    start = perf_counter()
    result = engine.summarize(text)
    elapsed = perf_counter() - start

    result["_meta"] = {
        "provider": engine.name,
        "model": engine.model,
        "duracao_segundos": round(elapsed, 3),
        "caracteres_entrada": len(text),
    }
    return result


def summarize_text(
    text: str,
    provider: str = "auto",
    model: str | None = None,
) -> dict:
    provider = provider.lower().strip()

    if provider != "auto":
        return _run_provider(text, build_provider(provider, model=model))

    # O modo auto permanece totalmente local: tenta Ollama e, se ele não estiver
    # disponível, usa o mecanismo heurístico. Gemini só é chamado explicitamente,
    # evitando envio involuntário da notícia para um serviço externo.
    try:
        return _run_provider(text, OllamaProvider(model=model))
    except Exception as exc:
        result = _run_provider(text, HeuristicProvider())
        result["_meta"]["observacao"] = (
            "O Ollama não pôde ser usado; foi aplicado o fallback heurístico. "
            f"Motivo: {exc}"
        )
        return result


def summarize_file(
    path: Path,
    provider: str = "auto",
    model: str | None = None,
) -> dict:
    text = read_txt(path)

    # Limite simples de proteção da v0.1.1. Notícias normais ficam muito abaixo.
    if len(text) > 120_000:
        text = text[:120_000]

    return summarize_text(text, provider=provider, model=model)
