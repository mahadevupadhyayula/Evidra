from django.urls import path

from apps.plans import views

app_name = "plans"

urlpatterns = [
    path("", views.plan_detail, name="detail"),
    path("generate/", views.plan_generate, name="generate"),
    path("tasks/<int:task_id>/status/", views.task_status, name="task_status"),
    path("complete/", views.plan_complete, name="complete"),
]
