from django.urls import path

from apps.workspace import views

app_name = "workspace"

urlpatterns = [
    path("", views.index, name="index"),
    path("sprints/current/", views.current_sprint, name="current_sprint"),
]
