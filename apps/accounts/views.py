from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_http_methods

from apps.accounts.forms import EmailSignupForm


@require_http_methods(["GET", "POST"])
def signup(request):
    if request.user.is_authenticated:
        return redirect("workspace:index")

    if request.method == "POST":
        form = EmailSignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("workspace:index")
    else:
        form = EmailSignupForm()

    return render(request, "accounts/signup.html", {"form": form})


class EmailLoginView(LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True


class SessionLogoutView(LogoutView):
    http_method_names = ["post", "options"]
    next_page = reverse_lazy("home")
