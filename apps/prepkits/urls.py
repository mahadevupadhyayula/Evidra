from django.urls import path

from apps.prepkits import views

app_name = "prepkits"

urlpatterns = [
    path("", views.prepkit_detail, name="detail"),
    path("generate/", views.prepkit_generate, name="generate"),
    path("status/", views.prepkit_status, name="status"),
    path("retry/", views.prepkit_retry, name="retry"),
    path("print/", views.prepkit_print, name="print"),
]
