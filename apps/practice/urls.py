from django.urls import path

from apps.practice import views

app_name = "practice"

urlpatterns = [
    path("", views.practice_index, name="index"),
    path("attempts/", views.practice_submit, name="submit"),
    path("history/", views.practice_history, name="history"),
]
