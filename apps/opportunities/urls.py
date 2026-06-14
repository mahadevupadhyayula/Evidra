from django.urls import path

from apps.opportunities import views

app_name = "opportunities"

urlpatterns = [
    path("", views.opportunity_detail, name="opportunity_detail"),
    path("analyze/", views.opportunity_analyze, name="opportunity_analyze"),
    path("<int:opportunity_id>/confirm/", views.opportunity_confirm, name="opportunity_confirm"),
]
