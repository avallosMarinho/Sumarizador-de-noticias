"""Operações editoriais. A geração nunca publica conteúdo."""
from copy import deepcopy
import hashlib
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from summarizer.contract import SYSTEM_PROMPT
from summarizer.providers import DEFAULT_GEMINI_MODEL, DEFAULT_OLLAMA_MODEL
from .models import Article, Review, SummaryVersion

CRITERION_KEYS = ("fidelity", "coverage", "conciseness", "coherence", "redundancy")


def require_reviewer(user):
    if not (user.is_active and user.is_staff and user.has_perm("news.review_summary")):
        raise PermissionDenied("Você precisa de permissão para revisar notícias.")


def content_fingerprint(text):
    normalized = unicodedata.normalize("NFC", " ".join(text.split())).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def normalize_url(url):
    if not url:
        return ""
    parts = urlsplit(url.strip())
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), ""))


def _next_version(article_id):
    # A primeira operação da transação é uma escrita: serializa a numeração no SQLite.
    Article.objects.filter(pk=article_id).update(version_counter=F("version_counter") + 1)
    return Article.objects.values_list("version_counter", flat=True).get(pk=article_id)


def enqueue_generation(article, user, provider="ollama", model=""):
    require_reviewer(user)
    if provider not in {"ollama", "gemini", "heuristic", "auto"}:
        raise ValidationError("Provedor inválido.")
    if len(model) > 200 or any(char.isspace() for char in model):
        raise ValidationError("Nome de modelo inválido.")
    default = DEFAULT_GEMINI_MODEL if provider == "gemini" else DEFAULT_OLLAMA_MODEL
    requested_model = "heuristic" if provider == "heuristic" else (model or default)
    try:
        with transaction.atomic():
            number = _next_version(article.pk)
            return SummaryVersion.objects.create(
                article=article, number=number, created_by=user,
                requested_provider=provider, requested_model=requested_model,
                prompt=SYSTEM_PROMPT if provider != "heuristic" else "",
                prompt_hash=hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest() if provider != "heuristic" else "",
            )
    except IntegrityError as exc:
        raise ValidationError("Esta notícia já tem uma geração na fila ou em andamento.") from exc


def create_article(data, user):
    require_reviewer(user)
    try:
        with transaction.atomic():
            article = Article.objects.create(
                original_title=data["original_title"], source_name=data.get("source_name", ""),
                source_url=normalize_url(data.get("source_url", "")), source_date=data.get("source_date"),
                original_text=data["original_text"], fingerprint=content_fingerprint(data["original_text"]),
                created_by=user,
            )
            enqueue_generation(article, user, data["provider"], data.get("model", ""))
            return article
    except IntegrityError as exc:
        raise ValidationError("O texto ou link já está cadastrado. Use a notícia existente no painel.") from exc


def edit_version(source, data, user):
    require_reviewer(user)
    if not source.ready:
        raise ValidationError("Aguarde a geração antes de editar o resumo.")
    with transaction.atomic():
        number = _next_version(source.article_id)
        return SummaryVersion.objects.create(
            article=source.article, number=number, status=SummaryVersion.Status.PENDING,
            parent=source, origin="human", created_by=user,
            requested_provider=source.requested_provider, requested_model=source.requested_model,
            provider=source.provider, model=source.model, prompt=source.prompt, prompt_hash=source.prompt_hash,
            generated_output=deepcopy(source.generated_output), duration_seconds=source.duration_seconds,
            title=data["title"], summary=data["summary"], points=data["points"],
            people=data["people"], places=data["places"], dates=data["dates"], finished_at=timezone.now(),
        )


def decide_version(version, user, action, notes="", criteria=None):
    require_reviewer(user)
    criteria = criteria or {}
    if action not in {Review.Action.APPROVE, Review.Action.REJECT}:
        raise ValidationError("Decisão inválida.")
    if action == Review.Action.APPROVE:
        if not all(criteria.get(key) is True for key in CRITERION_KEYS):
            raise ValidationError("Confirme os cinco critérios de revisão antes de aprovar.")
        if not version.title.strip() or not version.summary.strip():
            raise ValidationError("O título e o resumo precisam estar preenchidos.")
    elif not notes.strip():
        raise ValidationError("Informe o motivo da rejeição.")
    with transaction.atomic():
        status = SummaryVersion.Status.APPROVED if action == Review.Action.APPROVE else SummaryVersion.Status.REJECTED
        changed = SummaryVersion.objects.filter(pk=version.pk, status=SummaryVersion.Status.PENDING).update(status=status)
        if not changed:
            raise ValidationError("Esta versão não está pendente ou já foi avaliada. Atualize a página.")
        Review.objects.create(version=version, reviewer=user, action=action, notes=notes, criteria=criteria)
        if action == Review.Action.APPROVE:
            Article.objects.filter(pk=version.article_id).update(public_version=version, published_at=timezone.now())


def withdraw_article(article, user, notes):
    require_reviewer(user)
    if not notes.strip():
        raise ValidationError("Informe o motivo da retirada.")
    public_id = article.public_version_id
    if not public_id:
        raise ValidationError("Esta notícia não está publicada.")
    with transaction.atomic():
        changed = Article.objects.filter(pk=article.pk, public_version_id=public_id).update(
            public_version=None, published_at=None,
        )
        if not changed:
            raise ValidationError("A publicação foi alterada. Atualize a página antes de retirar.")
        Review.objects.create(version_id=public_id, reviewer=user, action=Review.Action.WITHDRAW, notes=notes)
