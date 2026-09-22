from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from summarizer.providers import DEFAULT_GEMINI_MODEL, DEFAULT_OLLAMA_MODEL
from summarizer.service import summarize_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "News Summarizer v0.1.1 - resume uma notícia .txt usando "
            "Ollama, Gemini ou modo heurístico"
        )
    )
    parser.add_argument("arquivo", help="Caminho para o arquivo .txt da notícia")
    parser.add_argument(
        "--provider",
        choices=["auto", "ollama", "gemini", "heuristic"],
        default="auto",
        help=(
            "auto: tenta Ollama e usa heurístico se falhar; "
            "ollama: modelo local; gemini: API Google; "
            "heuristic: somente Python"
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Modelo a utilizar. Se omitido: "
            f"Ollama={DEFAULT_OLLAMA_MODEL}; Gemini={DEFAULT_GEMINI_MODEL}."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Exibe somente o JSON final",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        result = summarize_file(
            Path(args.arquivo),
            provider=args.provider,
            model=args.model,
        )
    except Exception as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print("\n=== NEWS SUMMARIZER v0.1.1 ===\n")
    print(f"Título: {result['titulo']}\n")
    print("Resumo:")
    print(result["resumo"])

    print("\nPontos principais:")
    for item in result["pontos_principais"]:
        print(f"- {item}")

    print("\nPessoas:")
    print(", ".join(result["pessoas"]) if result["pessoas"] else "Nenhuma identificada")

    print("\nLocais:")
    print(", ".join(result["locais"]) if result["locais"] else "Nenhum identificado")

    print("\nDatas:")
    print(", ".join(result["datas"]) if result["datas"] else "Nenhuma identificada")

    meta = result["_meta"]
    print(f"\nProvider: {meta['provider']}")
    print(f"Modelo: {meta['model']}")
    print(f"Tempo: {meta['duracao_segundos']} s")
    if meta.get("observacao"):
        print(f"Observação: {meta['observacao']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
