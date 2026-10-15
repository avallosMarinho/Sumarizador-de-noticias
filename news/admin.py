import json
from urllib.parse import urlencode

from django.contrib import admin, messages
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import OuterRef, Subquery
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from .forms import ArticleForm, DecisionForm, EditSummaryForm, GenerationForm, WithdrawalForm
from .models import Article, Review, SummaryVersion
from .services import create_article, decide_version, edit_version, enqueue_generation, require_reviewer, withdraw_article


class EditorialSite(admin.AdminSite):
    site_header = "Redação · Notícias em resumo"
    site_title = "Redação"
    index_title = "Painel de revisão"
    site_url = "/"

    def get_urls(self):
        urls = [
            path("noticias/nova/", self.admin_view(self.create), name="news_create"),
            path("noticias/<uuid:pk>/", self.admin_view(self.article), name="news_review"),
            path("noticias/<uuid:pk>/gerar/", self.admin_view(self.generate), name="news_generate"),
            path("noticias/<uuid:pk>/retirar/", self.admin_view(self.withdraw), name="news_withdraw"),
            path("resumos/<int:pk>/editar/", self.admin_view(self.edit), name="news_edit"),
            path("resumos/<int:pk>/avaliar/", self.admin_view(self.decide), name="news_decide"),
        ]
        return urls + super().get_urls()

    def page(self, request, template, title, **context):
        require_reviewer(request.user)
        return TemplateResponse(request, template, {
            **self.each_context(request), "title": title, **context,
        })

    def index(self, request, extra_context=None):
        require_reviewer(request.user)
        latest = SummaryVersion.objects.filter(article_id=OuterRef("pk")).order_by("-number")
        base = Article.objects.select_related("public_version").annotate(
            latest_status=Subquery(latest.values("status")[:1]),
            latest_number=Subquery(latest.values("number")[:1]),
        )
        counts = {value: base.filter(latest_status=value).count() for value in ["pending", "queued", "processing", "failed"]}
        query = request.GET.get("q", "").strip()[:150]
        state = request.GET.get("state", "")
        articles = base
        if query:
            articles = articles.filter(original_title__icontains=query)
        if state == "published":
            articles = articles.filter(public_version__isnull=False)
        elif state in SummaryVersion.Status.values:
            articles = articles.filter(latest_status=state)
        page = Paginator(articles, 12).get_page(request.GET.get("page"))
        return self.page(request, "news/editorial/dashboard.html", "Painel de revisão",
                         page_obj=page, query=query, state=state, counts=counts,
                         status_labels=dict(SummaryVersion.Status.choices))

    def create(self, request):
        require_reviewer(request.user)
        if request.method not in {"GET", "POST"}:
            return HttpResponseNotAllowed(["GET", "POST"])
        form = ArticleForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and form.is_valid():
            try:
                article = create_article(form.cleaned_data, request.user)
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, "Notícia salva. O resumo entrou na fila de geração.")
                return redirect("admin:news_review", article.pk)
        return self.page(request, "news/editorial/create.html", "Nova notícia", form=form)

    def review_context(self, article, version=None, decision_form=None, withdrawal_form=None):
        versions = list(article.versions.select_related("created_by").order_by("-number"))
        selected = version or (versions[0] if versions else None)
        generation_form = GenerationForm(initial={
            "provider": selected.requested_provider if selected else "ollama",
            "model": selected.requested_model if selected and selected.requested_provider != "heuristic" else "",
        })
        return {
            "article": article, "version": selected, "versions": versions,
            "latest_version": versions[0] if versions else None,
            "is_processing": selected and selected.status in {"queued", "processing"},
            "has_active_generation": any(item.status in {"queued", "processing"} for item in versions),
            "decision_form": decision_form or DecisionForm(),
            "generation_form": generation_form,
            "withdrawal_form": withdrawal_form or WithdrawalForm(prefix="withdrawal", initial={"public_version": article.public_version_id}),
            "reviews": Review.objects.filter(version__article=article).select_related("version", "reviewer"),
            "generated_json": json.dumps(selected.generated_output, ensure_ascii=False, indent=2) if selected and selected.generated_output else "",
            "generation_note": selected.generated_output.get("_meta", {}).get("observacao", "") if selected else "",
        }

    def article(self, request, pk):
        require_reviewer(request.user)
        if request.method != "GET":
            return HttpResponseNotAllowed(["GET"])
        article = get_object_or_404(Article.objects.select_related("public_version"), pk=pk)
        version = None
        if request.GET.get("versao"):
            if not request.GET["versao"].isdigit():
                raise Http404("Versão inválida.")
            version = get_object_or_404(article.versions, pk=request.GET["versao"])
        return self.page(request, "news/editorial/review.html", article.original_title,
                         **self.review_context(article, version))

    def generate(self, request, pk):
        require_reviewer(request.user)
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        article = get_object_or_404(Article, pk=pk)
        form = GenerationForm(request.POST)
        if form.is_valid():
            try:
                enqueue_generation(article, request.user, form.cleaned_data["provider"], form.cleaned_data["model"])
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                messages.success(request, "Nova geração solicitada. Ela precisará de revisão antes de ser publicada.")
        else:
            messages.error(request, "Confira o provedor e o nome do modelo.")
        return redirect("admin:news_review", article.pk)

    def decide(self, request, pk):
        require_reviewer(request.user)
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        version = get_object_or_404(SummaryVersion.objects.select_related("article"), pk=pk)
        form = DecisionForm(request.POST)
        if form.is_valid():
            try:
                data = form.cleaned_data
                criteria = {key: data[key] for key in ("fidelity", "coverage", "conciseness", "coherence", "redundancy")}
                decide_version(version, request.user, data["action"], data["notes"], criteria)
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, "Resumo aprovado e publicado." if data["action"] == "approve" else "Resumo rejeitado. Motivo registrado no histórico.")
                return redirect("admin:news_review", version.article_id)
        return self.page(request, "news/editorial/review.html", version.article.original_title,
                         **self.review_context(version.article, version, decision_form=form))

    def edit(self, request, pk):
        require_reviewer(request.user)
        if request.method not in {"GET", "POST"}:
            return HttpResponseNotAllowed(["GET", "POST"])
        source = get_object_or_404(SummaryVersion.objects.select_related("article"), pk=pk)
        if not source.ready:
            messages.error(request, "Aguarde a geração antes de editar.")
            return redirect("admin:news_review", source.article_id)
        initial = {"title": source.title, "summary": source.summary}
        initial.update({key: "\n".join(getattr(source, key)) for key in ("points", "people", "places", "dates")})
        form = EditSummaryForm(request.POST or None, initial=initial)
        if request.method == "POST" and form.is_valid():
            version = edit_version(source, form.cleaned_data, request.user)
            messages.success(request, "Edição salva como nova versão pendente. Confira o texto e aprove para publicar.")
            url = reverse("admin:news_review", args=[source.article_id])
            return redirect(url + "?" + urlencode({"versao": version.pk}))
        return self.page(request, "news/editorial/edit.html", f"Editar versão {source.number}",
                         form=form, version=source, article=source.article)

    def withdraw(self, request, pk):
        require_reviewer(request.user)
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        article = get_object_or_404(Article.objects.select_related("public_version"), pk=pk)
        form = WithdrawalForm(request.POST, prefix="withdrawal")
        if form.is_valid():
            try:
                if article.public_version_id != form.cleaned_data["public_version"]:
                    raise ValidationError("A versão publicada mudou. Atualize a página antes de retirar.")
                withdraw_article(article, request.user, form.cleaned_data["notes"])
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, "Notícia retirada da página pública. O histórico foi preservado.")
                return redirect("admin:news_review", article.pk)
        return self.page(request, "news/editorial/review.html", article.original_title,
                         **self.review_context(article, withdrawal_form=form))


editorial_site = EditorialSite(name="admin")
editorial_site.register(User, UserAdmin)
editorial_site.register(Group, GroupAdmin)


class ReadOnlyEditorialAdmin(admin.ModelAdmin):
    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("news.review_summary")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]


@admin.register(Article, site=editorial_site)
class ArticleAdmin(ReadOnlyEditorialAdmin):
    list_display = ["original_title", "source_name", "created_at", "published_at"]
    search_fields = ["original_title", "source_name"]
    view_on_site = False


@admin.register(SummaryVersion, site=editorial_site)
class SummaryVersionAdmin(ReadOnlyEditorialAdmin):
    list_display = ["article", "number", "status", "origin", "provider", "model"]
    list_filter = ["status", "origin", "provider"]


@admin.register(Review, site=editorial_site)
class ReviewAdmin(ReadOnlyEditorialAdmin):
    list_display = ["version", "action", "reviewer", "created_at"]
    list_filter = ["action"]
