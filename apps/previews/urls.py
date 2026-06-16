from django.urls import path

from apps.previews import views

app_name = "previews"

urlpatterns = [
    path("", views.preview_detail, name="detail"),
    path("generate/", views.preview_generate, name="generate"),
    path(
        "generation/status/poll/",
        views.preview_generation_status_poll,
        name="generation_status_poll",
    ),
]
