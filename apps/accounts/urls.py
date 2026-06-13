from django.urls import path

from apps.accounts.views import EmailLoginView, SessionLogoutView, signup

app_name = "accounts"

urlpatterns = [
    path("signup/", signup, name="signup"),
    path("login/", EmailLoginView.as_view(), name="login"),
    path("logout/", SessionLogoutView.as_view(), name="logout"),
]
