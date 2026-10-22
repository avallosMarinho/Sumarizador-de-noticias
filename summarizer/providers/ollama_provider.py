from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
from typing import Any

from .base import SummarizerProvider
from ..contract import SYSTEM_PROMPT, SUMMARY_JSON_SCHEMA, validate_summary


OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
DEFAULT_OLLAMA_MODEL = "qwen3.5:4b"
DEFAULT_OLLAMA_TIMEOUT_SECONDS = 900


def _generation_timeout(value: float | str) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("OLLAMA_TIMEOUT_SECONDS deve ser um número positivo de segundos.") from exc
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("OLLAMA_TIMEOUT_SECONDS deve ser um número positivo de segundos.")
    return seconds


def _extract_json(content: str) -> dict[str, Any]:
    content = content.strip()

    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("O modelo do Ollama não retornou um JSON válido.")

    return json.loads(content[start : end + 1])


class OllamaProvider(SummarizerProvider):
    name = "ollama"

    def __init__(self, model: str | None = None, url: str = OLLAMA_URL, *, timeout: float | None = None) -> None:
        self.model = model or DEFAULT_OLLAMA_MODEL
        self.url = url
        self.timeout = _generation_timeout(
            timeout if timeout is not None else os.environ.get("OLLAMA_TIMEOUT_SECONDS", str(DEFAULT_OLLAMA_TIMEOUT_SECONDS))
        )

    def _timeout_error(self) -> TimeoutError:
        return TimeoutError(
            f'O modelo "{self.model}" no Ollama não respondeu dentro do limite de espera '
            f"de {self.timeout:g} segundos. Isso pode ocorrer quando o carregamento ou a geração "
            "demoram no computador. Você pode solicitar outra geração e, se necessário, "
            "configurar OLLAMA_TIMEOUT_SECONDS antes de iniciar a aplicação. "
            "Aumentar esse limite amplia a espera, mas não acelera o modelo."
        )

    def summarize(self, text: str) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "stream": False,
            "format": SUMMARY_JSON_SCHEMA,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Produza o resumo estruturado da notícia abaixo.\n\n"
                        "ESQUEMA JSON ESPERADO:\n"
                        + json.dumps(SUMMARY_JSON_SCHEMA, ensure_ascii=False)
                        + "\n\nNOTÍCIA:\n"
                        + text
                    ),
                },
            ],
            "options": {"temperature": 0},
        }

        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except TimeoutError as exc:
            raise self._timeout_error() from exc
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"O Ollama retornou HTTP {exc.code}. Detalhes: {details[:500]}"
            ) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise self._timeout_error() from exc
            raise ConnectionError(
                "Não foi possível conectar ao Ollama em http://127.0.0.1:11434. "
                "Confirme se o Ollama está instalado e em execução."
            ) from exc

        content = body.get("message", {}).get("content", "")
        return validate_summary(_extract_json(content))
