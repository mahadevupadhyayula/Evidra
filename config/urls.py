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
    path("workspace/", include("apps.workspace.urls")),
]
