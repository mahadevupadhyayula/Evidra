from django.urls import path

from apps.profiles import views

app_name = "profiles"

urlpatterns = [
    path("review/", views.profile_review, name="profile_review"),
    path("generate/", views.profile_generate, name="profile_generate"),
    path("<int:profile_id>/save/", views.profile_save, name="profile_save"),
    path("<int:profile_id>/confirm/", views.profile_confirm, name="profile_confirm"),
]
