from django.urls import path

from apps.evidence import views

app_name = "evidence"

urlpatterns = [
    path("", views.evidence_review, name="evidence_review"),
    path("extract/", views.evidence_extract, name="evidence_extract"),
    path("continue/", views.evidence_continue, name="evidence_continue"),
    path("highlights/add/", views.highlight_add, name="highlight_add"),
    path("highlights/<int:highlight_id>/edit/", views.highlight_edit, name="highlight_edit"),
    path(
        "highlights/<int:highlight_id>/archive/",
        views.highlight_archive,
        name="highlight_archive",
    ),
    path("cards/<int:card_id>/save/", views.card_save, name="card_save"),
    path("cards/<int:card_id>/approve/", views.card_approve, name="card_approve"),
    path("cards/<int:card_id>/reject/", views.card_reject, name="card_reject"),
]
