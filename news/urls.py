from django.urls import path
from . import views

app_name = "news"
urlpatterns = [
    path("", views.index, name="index"),
    path("noticias/<uuid:pk>/", views.detail, name="detail"),
]
