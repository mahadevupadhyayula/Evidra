from django.urls import path

from apps.opportunities import views

app_name = "opportunities"

urlpatterns = [
    path("", views.opportunity_detail, name="opportunity_detail"),
    path("analyze/", views.opportunity_analyze, name="opportunity_analyze"),
    path(
        "<int:opportunity_id>/company-context/",
        views.company_context_submit,
        name="company_context_submit",
    ),
    path(
        "<int:opportunity_id>/company-context/review/",
        views.company_context_review,
        name="company_context_review",
    ),
    path(
        "<int:opportunity_id>/company-context/confirm/",
        views.company_context_confirm,
        name="company_context_confirm",
    ),
    path(
        "<int:opportunity_id>/company-context/skip/",
        views.company_context_skip,
        name="company_context_skip",
    ),
    path("<int:opportunity_id>/confirm/", views.opportunity_confirm, name="opportunity_confirm"),
]
