"""Fila persistente, executada por um processo separado da interface."""
from copy import deepcopy
import hashlib

from django.utils import timezone

from summarizer.contract import SYSTEM_PROMPT, validate_summary
from summarizer.service import summarize_text
from .models import SummaryVersion


def process_next():
    candidate = SummaryVersion.objects.filter(status=SummaryVersion.Status.QUEUED).order_by("created_at").first()
    if candidate is None:
        return False
    claimed = SummaryVersion.objects.filter(pk=candidate.pk, status=SummaryVersion.Status.QUEUED).update(
        status=SummaryVersion.Status.PROCESSING, started_at=timezone.now(),
    )
    if not claimed:
        return True
    try:
        # Nenhuma transação permanece aberta durante a chamada lenta ao modelo.
        result = summarize_text(
            candidate.article.original_text,
            provider=candidate.requested_provider,
            model=candidate.requested_model if candidate.requested_provider != "heuristic" else None,
        )
        cleaned = validate_summary(result)
        if not cleaned["titulo"] or not cleaned["resumo"]:
            raise ValueError("O modelo retornou título ou resumo vazio. Solicite uma nova geração.")
        if len(cleaned["titulo"]) > 500:
            raise ValueError("O título retornado excede 500 caracteres. Solicite uma nova geração.")
        meta = result.get("_meta", {})
        actual_provider = meta.get("provider", candidate.requested_provider)
        actual_prompt = "" if actual_provider == "heuristic" else SYSTEM_PROMPT
        SummaryVersion.objects.filter(pk=candidate.pk, status=SummaryVersion.Status.PROCESSING).update(
            status=SummaryVersion.Status.PENDING, generated_output=deepcopy(result),
            title=cleaned["titulo"], summary=cleaned["resumo"], points=cleaned["pontos_principais"],
            people=cleaned["pessoas"], places=cleaned["locais"], dates=cleaned["datas"],
            provider=actual_provider, prompt=actual_prompt,
            prompt_hash=hashlib.sha256(actual_prompt.encode()).hexdigest() if actual_prompt else "",
            model=meta.get("model", candidate.requested_model),
            duration_seconds=meta.get("duracao_segundos"), finished_at=timezone.now(), error_message="",
        )
    except Exception as exc:
        SummaryVersion.objects.filter(pk=candidate.pk, status=SummaryVersion.Status.PROCESSING).update(
            status=SummaryVersion.Status.FAILED, error_message=str(exc)[:2000], finished_at=timezone.now(),
        )
    return True
