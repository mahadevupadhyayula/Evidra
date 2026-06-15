from django.urls import path

from apps.stories import views

app_name = "stories"

urlpatterns = [
    path("", views.story_bank, name="story_bank"),
    path("generate/", views.story_generate, name="story_generate"),
    path("<int:story_id>/edit/", views.story_edit, name="story_edit"),
    path("<int:story_id>/regenerate/", views.story_regenerate, name="story_regenerate"),
]
