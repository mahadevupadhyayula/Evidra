from django.contrib import admin
from django.shortcuts import redirect, render
from django.urls import include, path


def home(request):
    if request.user.is_authenticated:
        return redirect("workspace:index")
    return render(request, "home.html")


urlpatterns = [
    path("", home, name="home"),
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("workspace/evidence/", include("apps.evidence.urls")),
    path("workspace/matching/", include("apps.matching.urls")),
    path("workspace/opportunity/", include("apps.opportunities.urls")),
    path("workspace/profile/", include("apps.profiles.urls")),
    path("workspace/preview/", include("apps.previews.urls")),
    path("workspace/payment/", include("apps.payments.urls")),
    path("workspace/prepkit/", include("apps.prepkits.urls")),
    path("workspace/practice/", include("apps.practice.urls")),
    path("workspace/resume/", include("apps.documents.urls")),
    path("workspace/stories/", include("apps.stories.urls")),
    path("workspace/", include("apps.workspace.urls")),
]
