from django.urls import include, path
from news.admin import editorial_site

urlpatterns = [
    path("admin/", editorial_site.urls),
    path("", include("news.urls")),
]
