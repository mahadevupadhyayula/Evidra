from django.urls import path

from apps.documents import views

app_name = "documents"

urlpatterns = [
    path("upload/", views.resume_upload, name="resume_upload"),
    path("paste/", views.resume_paste, name="resume_paste"),
    path("<int:document_id>/review/", views.resume_review, name="resume_review"),
    path("<int:document_id>/confirm/", views.resume_confirm, name="resume_confirm"),
    path("replace/", views.resume_replace, name="resume_replace"),
]
