from django.core.paginator import Paginator
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from .models import Article, SummaryVersion


def published_articles():
    return Article.objects.filter(
        public_version__isnull=False, published_at__isnull=False,
        public_version__status=SummaryVersion.Status.APPROVED,
        public_version__article_id=F("pk"),
    ).select_related("public_version").order_by("-published_at", "-pk")


@require_safe
@never_cache
def index(request):
    query = request.GET.get("q", "").strip()[:150]
    articles = published_articles()
    if query:
        articles = articles.filter(
            Q(public_version__title__icontains=query) |
            Q(public_version__summary__icontains=query) | Q(source_name__icontains=query)
        )
    page = Paginator(articles, 9).get_page(request.GET.get("page"))
    return render(request, "news/index.html", {"page_obj": page, "query": query})


@require_safe
@never_cache
def detail(request, pk):
    article = get_object_or_404(published_articles(), pk=pk)
    return render(request, "news/detail.html", {"article": article, "summary": article.public_version})
