from __future__ import annotations

from typing import Any


REQUIRED_FIELDS = (
    "titulo",
    "resumo",
    "pontos_principais",
    "pessoas",
    "locais",
    "datas",
)

LIST_FIELDS = (
    "pontos_principais",
    "pessoas",
    "locais",
    "datas",
)

SUMMARY_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "titulo": {
            "type": "string",
            "description": "Título factual da notícia, preferindo o título original quando disponível.",
        },
        "resumo": {
            "type": "string",
            "description": "Resumo curto e fiel contendo somente informações presentes na notícia.",
        },
        "pontos_principais": {
            "type": "array",
            "items": {"type": "string"},
            "description": "De 3 a 6 fatos principais, quando houver conteúdo suficiente.",
        },
        "pessoas": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Pessoas explicitamente citadas na notícia.",
        },
        "locais": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Locais explicitamente citados na notícia.",
        },
        "datas": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Datas ou períodos explicitamente citados na notícia.",
        },
    },
    "required": list(REQUIRED_FIELDS),
    "additionalProperties": False,
}

SYSTEM_PROMPT = """
Você é um sumarizador de notícias em português do Brasil.

Objetivo: condensar a notícia preservando as informações factuais mais importantes.

Regras obrigatórias:
1. Use SOMENTE informações presentes no texto fornecido.
2. Não invente fatos, pessoas, locais, datas, números, causas ou consequências.
3. Preserve nomes próprios, números, datas e relações factuais relevantes.
4. Dê prioridade ao acontecimento central: o que ocorreu, quem participou, onde,
   quando e quais números ou consequências são essenciais para compreender a notícia.
5. Remova repetições, detalhes acessórios, publicidade e comentários que não sejam
   necessários para compreender o fato principal.
6. Não inclua opiniões próprias nem conhecimentos externos.
7. Se uma categoria não tiver informação explícita, retorne uma lista vazia.
8. Retorne somente um objeto JSON válido seguindo exatamente o esquema solicitado.
""".strip()


def validate_summary(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError("A resposta do provedor não é um objeto JSON.")

    missing = [field for field in REQUIRED_FIELDS if field not in result]
    if missing:
        raise ValueError(
            "Resposta sem campos obrigatórios: " + ", ".join(missing)
        )

    if not isinstance(result["titulo"], str) or not isinstance(result["resumo"], str):
        raise ValueError("Os campos 'titulo' e 'resumo' devem ser texto.")

    clean: dict[str, Any] = {
        "titulo": result["titulo"].strip(),
        "resumo": result["resumo"].strip(),
    }

    for field in LIST_FIELDS:
        value = result.get(field, [])
        if not isinstance(value, list):
            raise ValueError(f"O campo '{field}' deve ser uma lista.")
        clean[field] = [str(item).strip() for item in value if str(item).strip()]

    return clean
