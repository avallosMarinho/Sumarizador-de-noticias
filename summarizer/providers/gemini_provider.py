from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .base import SummarizerProvider
from ..contract import SYSTEM_PROMPT, SUMMARY_JSON_SCHEMA, validate_summary


DEFAULT_GEMINI_MODEL = "gemini-3.7-flash"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(SummarizerProvider):
    name = "gemini"

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self.model = model or DEFAULT_GEMINI_MODEL
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "A variável de ambiente GEMINI_API_KEY não foi definida. "
                "Defina a chave antes de usar --provider gemini."
            )

    def summarize(self, text: str) -> dict[str, Any]:
        model = urllib.parse.quote(self.model, safe="-._")
        url = f"{GEMINI_API_BASE}/{model}:generateContent"

        payload = {
            "systemInstruction": {
                "parts": [{"text": SYSTEM_PROMPT}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                "Produza o resumo estruturado desta notícia.\n\n"
                                "NOTÍCIA:\n" + text
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": SUMMARY_JSON_SCHEMA,
            },
        }

        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=240) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"A API Gemini retornou HTTP {exc.code}. Detalhes: {details[:500]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ConnectionError(
                "Não foi possível conectar à API Gemini. Verifique sua internet."
            ) from exc

        try:
            parts = body["candidates"][0]["content"]["parts"]
            content = "".join(part.get("text", "") for part in parts)
            result = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError(
                "A API Gemini respondeu, mas o conteúdo não pôde ser interpretado "
                "como o JSON esperado."
            ) from exc

        return validate_summary(result)
