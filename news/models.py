import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse


class Article(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    original_title = models.CharField("título original", max_length=300)
    source_name = models.CharField("fonte", max_length=200, blank=True)
    source_url = models.URLField("link original", max_length=1000, blank=True)
    source_date = models.DateField("data da notícia original", blank=True, null=True)
    original_text = models.TextField("texto original")
    fingerprint = models.CharField(max_length=64, unique=True, editable=False)
    version_counter = models.PositiveIntegerField(default=0, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField("cadastrada em", auto_now_add=True)
    public_version = models.ForeignKey(
        "SummaryVersion", on_delete=models.PROTECT, null=True, blank=True,
        related_name="+", verbose_name="versão publicada",
    )
    published_at = models.DateTimeField("publicada em", null=True, blank=True)

    class Meta:
        verbose_name = "notícia"
        verbose_name_plural = "notícias"
        ordering = ["-created_at"]
        permissions = [("review_summary", "Pode gerar, revisar e publicar resumos")]
        constraints = [models.UniqueConstraint(
            fields=["source_url"], condition=~models.Q(source_url=""),
            name="unique_nonempty_source_url",
        )]

    def __str__(self):
        return self.original_title

    def get_absolute_url(self):
        return reverse("news:detail", args=[self.pk])


class SummaryVersion(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Na fila"
        PROCESSING = "processing", "Gerando resumo"
        PENDING = "pending", "Pendente de revisão"
        APPROVED = "approved", "Aprovada"
        REJECTED = "rejected", "Rejeitada"
        FAILED = "failed", "Falha na geração"

    article = models.ForeignKey(Article, related_name="versions", on_delete=models.PROTECT)
    number = models.PositiveIntegerField("versão")
    status = models.CharField("situação", max_length=16, choices=Status.choices, default=Status.QUEUED)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)
    origin = models.CharField("origem", max_length=10, default="model", choices=[
        ("model", "Geração automática"), ("human", "Edição humana"),
    ])
    requested_provider = models.CharField(max_length=16)
    requested_model = models.CharField(max_length=200, blank=True)
    provider = models.CharField("provedor utilizado", max_length=16, blank=True)
    model = models.CharField("modelo utilizado", max_length=200, blank=True)
    prompt = models.TextField("prompt utilizado", blank=True)
    prompt_hash = models.CharField(max_length=64, blank=True)
    generated_output = models.JSONField("resultado original do modelo", default=dict, blank=True)
    title = models.CharField("título do resumo", max_length=500, blank=True)
    summary = models.TextField("resumo", blank=True)
    points = models.JSONField("pontos principais", default=list, blank=True)
    people = models.JSONField("pessoas", default=list, blank=True)
    places = models.JSONField("locais", default=list, blank=True)
    dates = models.JSONField("datas", default=list, blank=True)
    duration_seconds = models.FloatField("tempo de geração (s)", null=True, blank=True)
    error_message = models.TextField("erro", blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField("criada em", auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "versão do resumo"
        verbose_name_plural = "versões dos resumos"
        ordering = ["-number"]
        constraints = [
            models.UniqueConstraint(fields=["article", "number"], name="unique_article_version"),
            models.UniqueConstraint(
                fields=["article"], condition=models.Q(status__in=["queued", "processing"]),
                name="one_active_generation_per_article",
            ),
        ]
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self):
        return f"{self.article} · v{self.number}"

    @property
    def ready(self):
        return self.status in {self.Status.PENDING, self.Status.APPROVED, self.Status.REJECTED}


class Review(models.Model):
    class Action(models.TextChoices):
        APPROVE = "approve", "Aprovação e publicação"
        REJECT = "reject", "Rejeição"
        WITHDRAW = "withdraw", "Retirada da página pública"

    version = models.ForeignKey(SummaryVersion, related_name="reviews", on_delete=models.PROTECT)
    action = models.CharField("decisão", max_length=12, choices=Action.choices)
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    notes = models.TextField("observação", blank=True)
    criteria = models.JSONField("critérios confirmados", default=dict, blank=True)
    created_at = models.DateTimeField("registrada em", auto_now_add=True)

    class Meta:
        verbose_name = "registro de revisão"
        verbose_name_plural = "registros de revisão"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_action_display()} · v{self.version.number}"
