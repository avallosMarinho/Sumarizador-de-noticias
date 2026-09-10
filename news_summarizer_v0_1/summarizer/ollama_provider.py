from __future__ import annotations

import json
import urllib.error
import urllib.request


OLLAMA_URL = "http://127.0.0.1:11434/api/chat"


def _extract_json(content: str) -> dict:
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
        raise ValueError("O modelo não retornou um JSON válido.")

    return json.loads(content[start:end + 1])


def summarize_with_ollama(text: str, model: str) -> dict:
    system_prompt = """
Você é um sumarizador de notícias em português do Brasil.
Use SOMENTE informações presentes no texto fornecido.
Não invente fatos, pessoas, locais ou datas.
Retorne APENAS JSON válido, sem Markdown e sem comentários extras.

Formato obrigatório:
{
  "titulo": "string",
  "resumo": "string com 1 a 3 parágrafos curtos",
  "pontos_principais": ["string", "string"],
  "pessoas": ["string"],
  "locais": ["string"],
  "datas": ["string"]
}

Regras:
- titulo: use o título do texto, se houver; caso contrário, crie um título factual.
- resumo: preserve números, nomes e fatos importantes.
- pontos_principais: entre 3 e 6 itens quando houver conteúdo suficiente.
- pessoas: somente pessoas explicitamente citadas.
- locais: cidades, estados, países ou locais explicitamente citados.
- datas: somente datas ou períodos explicitamente citados.
- se uma categoria não tiver informação, use uma lista vazia.
""".strip()

    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "NOTÍCIA:\n\n" + text},
        ],
        "options": {
            "temperature": 0.1
        }
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise ConnectionError(
            "Não foi possível conectar ao Ollama em http://127.0.0.1:11434."
        ) from exc

    content = body.get("message", {}).get("content", "")
    result = _extract_json(content)

    required = [
        "titulo",
        "resumo",
        "pontos_principais",
        "pessoas",
        "locais",
        "datas",
    ]
    for key in required:
        if key not in result:
            raise ValueError(f"Resposta do modelo sem o campo obrigatório: {key}")

    for key in ("pontos_principais", "pessoas", "locais", "datas"):
        if not isinstance(result[key], list):
            result[key] = []

    result["_meta"] = {
        "provider": f"ollama:{model}",
        "observacao": "Resumo gerado por modelo local via Ollama.",
    }
    return result
