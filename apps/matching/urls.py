from django.urls import path

from apps.matching import views

app_name = "matching"

urlpatterns = [
    path("", views.matching_index, name="index"),
    path("generate/", views.matching_generate, name="generate"),
    path("<int:match_id>/override/", views.matching_override, name="override"),
]
