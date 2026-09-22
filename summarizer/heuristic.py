from __future__ import annotations

import re
import unicodedata
from collections import Counter


STOPWORDS = {
    "a", "à", "ao", "aos", "as", "às", "o", "os", "um", "uma", "uns", "umas",
    "de", "da", "das", "do", "dos", "em", "na", "nas", "no", "nos", "por",
    "para", "com", "sem", "sob", "sobre", "entre", "e", "ou", "mas", "que",
    "se", "como", "mais", "menos", "muito", "muita", "muitos", "muitas",
    "foi", "foram", "ser", "são", "é", "era", "eram", "tem", "têm", "ter",
    "teve", "também", "já", "ainda", "após", "antes", "durante", "nesta",
    "neste", "nessa", "nesse", "esta", "este", "isso", "isto", "ele", "ela",
    "eles", "elas", "sua", "seu", "suas", "seus", "pelo", "pela", "pelos",
    "pelas", "desde", "até", "quando", "onde", "porque", "segundo"
}

MONTHS = (
    "janeiro|fevereiro|março|abril|maio|junho|julho|agosto|"
    "setembro|outubro|novembro|dezembro"
)


def _normalize_word(word: str) -> str:
    value = unicodedata.normalize("NFKD", word.lower())
    return "".join(c for c in value if not unicodedata.combining(c))


def _sentences(text: str) -> list[str]:
    compact = re.sub(r"[ \t]+", " ", text.replace("\r", "\n"))
    compact = re.sub(r"\n+", " ", compact).strip()
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9])", compact)
    return [p.strip() for p in parts if len(p.strip()) >= 20]


def _title(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return "Sem título"

    first = lines[0]
    if len(first) <= 180:
        return first

    sentences = _sentences(text)
    return (sentences[0][:177] + "...") if sentences else first[:177] + "..."


def _score_sentences(sentences: list[str]) -> list[tuple[float, int, str]]:
    tokens = re.findall(r"[A-Za-zÀ-ÿ0-9'-]+", " ".join(sentences))
    normalized = [_normalize_word(t) for t in tokens]
    words = [w for w in normalized if len(w) > 2 and w not in STOPWORDS and not w.isdigit()]
    freq = Counter(words)

    if not freq:
        return [(1.0, i, sentence) for i, sentence in enumerate(sentences)]

    max_freq = max(freq.values())
    weights = {word: count / max_freq for word, count in freq.items()}

    scored = []
    for idx, sentence in enumerate(sentences):
        sentence_tokens = [
            _normalize_word(t)
            for t in re.findall(r"[A-Za-zÀ-ÿ0-9'-]+", sentence)
        ]
        useful = [t for t in sentence_tokens if t in weights]
        if not useful:
            score = 0.0
        else:
            score = sum(weights[t] for t in useful) / (len(sentence_tokens) ** 0.55)

        if idx < 3:
            score *= 1.15

        scored.append((score, idx, sentence))
    return scored


def _best_sentences(text: str, limit: int) -> list[str]:
    sentences = _sentences(text)
    if not sentences:
        return [text[:500].strip()] if text.strip() else []

    scored = _score_sentences(sentences)
    selected = sorted(scored, reverse=True)[: min(limit, len(scored))]
    selected.sort(key=lambda item: item[1])
    return [item[2] for item in selected]


def _extract_dates(text: str) -> list[str]:
    patterns = [
        rf"\b\d{{1,2}}\s+de\s+(?:{MONTHS})(?:\s+de\s+\d{{4}})?\b",
        rf"\b(?:{MONTHS})\s+de\s+\d{{4}}\b",
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
        r"\b\d{4}-\d{2}-\d{2}\b",
    ]

    found = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = match.group(0).strip()
            if value not in found:
                found.append(value)
    return found[:10]


def _extract_people(text: str) -> list[str]:
    candidates = re.findall(
        r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+"
        r"(?:\s+(?:da|de|do|dos|das|e)\s+)?"
        r"(?:\s*[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+){1,3})\b",
        text,
    )

    excluded = {
        "Estados Unidos", "União Europeia", "América Latina", "São Paulo",
        "Rio de Janeiro", "Minas Gerais", "Distrito Federal", "Linux Mint",
        "Inteligência Artificial"
    }

    unique = []
    for candidate in candidates:
        candidate = re.sub(r"\s+", " ", candidate).strip(" ,.;:")
        if candidate in excluded:
            continue
        if candidate not in unique:
            unique.append(candidate)
    return unique[:12]


def _extract_locations(text: str) -> list[str]:
    patterns = [
        r"\b(?:em|no|na|nos|nas|de|do|da)\s+"
        r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ.-]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ.-]+){0,3})",
    ]

    reject = {
        "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo",
        "Governo", "Presidente", "Ministério", "Congresso"
    }

    results = []
    for pattern in patterns:
        for value in re.findall(pattern, text):
            value = value.strip(" ,.;:")
            if len(value) < 3 or value in reject:
                continue
            if value not in results:
                results.append(value)
    return results[:12]


def summarize_heuristic(text: str) -> dict:
    title = _title(text)
    summary_sentences = _best_sentences(text, 3)
    points = _best_sentences(text, 5)

    return {
        "titulo": title,
        "resumo": " ".join(summary_sentences),
        "pontos_principais": points,
        "pessoas": _extract_people(text),
        "locais": _extract_locations(text),
        "datas": _extract_dates(text),
        "_meta": {
            "provider": "heuristic",
            "observacao": (
                "Modo local sem IA. Funciona sem dependências externas, "
                "mas a identificação de pessoas e locais é aproximada."
            ),
        },
    }
