import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


def assert_no_active_social_login(response):
    html = response.content.decode().lower()
    forbidden_fragments = [
        "continue with google",
        "accounts/google",
        "google/login",
        "oauth",
        "social",
        "provider_login_url",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in html, fragment


def test_signup_view_has_no_active_social_login(client):
    response = client.get(reverse("accounts:signup"))

    assert response.status_code == 200
    assert_no_active_social_login(response)


def test_login_view_has_no_active_social_login(client):
    response = client.get(reverse("accounts:login"))

    assert response.status_code == 200
    assert_no_active_social_login(response)


@pytest.mark.django_db
def test_signup_view_creates_user_and_logs_in(client):
    response = client.post(
        reverse("accounts:signup"),
        {
            "full_name": "New User",
            "email": "new@example.com",
            "password1": "A-strong-test-password-123",
            "password2": "A-strong-test-password-123",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("workspace:index")
    user = get_user_model().objects.get(email="new@example.com")
    assert user.first_name == "New User"


def test_signup_view_omits_terms_privacy_links_without_approved_legal_pages(client):
    response = client.get(reverse("accounts:signup"))

    html = response.content.decode().lower()
    assert response.status_code == 200
    assert "terms" not in html
    assert "privacy" not in html


def test_signup_view_links_to_login(client):
    response = client.get(reverse("accounts:signup"))

    html = response.content.decode()
    assert response.status_code == 200
    assert 'class="auth-login-strip"' in html
    assert "Already have an account?" in html
    assert f'href="{reverse("accounts:login")}"' in html


def test_login_view_omits_secondary_login_strip(client):
    response = client.get(reverse("accounts:login"))

    html = response.content.decode()
    assert response.status_code == 200
    assert 'class="auth-login-strip"' not in html
    assert "Already have an account?" not in html


@pytest.mark.django_db
def test_authenticated_user_is_redirected_from_signup(client):
    user = get_user_model().objects.create_user(
        username="user@example.com",
        email="user@example.com",
        password="A-strong-test-password-123",
    )
    client.force_login(user)

    response = client.get(reverse("accounts:signup"))

    assert response.status_code == 302
    assert response.url == reverse("workspace:index")


def test_login_view_links_to_signup(client):
    response = client.get(reverse("accounts:login"))

    assert response.status_code == 200
    assert f'href="{reverse("accounts:signup")}"' in response.content.decode()


def test_login_view_uses_email_presentation_with_username_field_name(client):
    response = client.get(reverse("accounts:login"))

    html = response.content.decode()
    assert response.status_code == 200
    assert '<label for="id_username">Email:</label>' in html
    assert 'name="username"' in html
    assert 'placeholder="name@company.com"' in html
    assert 'placeholder="Enter your password"' in html


@pytest.mark.django_db
def test_login_and_logout_flow(client):
    get_user_model().objects.create_user(
        username="user@example.com",
        email="user@example.com",
        password="A-strong-test-password-123",
    )

    login_response = client.post(
        reverse("accounts:login"),
        {"username": "user@example.com", "password": "A-strong-test-password-123"},
    )
    assert login_response.status_code == 302
    assert login_response.url == reverse("workspace:index")

    logout_response = client.post(reverse("accounts:logout"))
    assert logout_response.status_code == 302
    assert logout_response.url == reverse("home")

    workspace_response = client.get(reverse("workspace:index"))
    assert workspace_response.status_code == 302
    assert reverse("accounts:login") in workspace_response.url


def test_signup_password_toggles_are_non_submitting_buttons(client):
    response = client.get(reverse("accounts:signup"))

    html = response.content.decode()
    assert response.status_code == 200
    assert html.count('class="auth-password-toggle"') == 2
    assert html.count('type="button" class="auth-password-toggle"') == 2
    assert 'data-password-toggle="id_password1"' in html
    assert 'data-password-toggle="id_password2"' in html
    assert 'aria-label="Show password"' in html


def test_login_password_toggle_is_non_submitting_button(client):
    response = client.get(reverse("accounts:login"))

    html = response.content.decode()
    assert response.status_code == 200
    assert html.count('class="auth-password-toggle"') == 1
    assert html.count('type="button" class="auth-password-toggle"') == 1
    assert 'data-password-toggle="id_password"' in html
    assert 'aria-label="Show password"' in html

@pytest.mark.django_db
def test_login_view_links_to_password_reset_after_routes_exist(client):
    response = client.get(reverse("accounts:login"))

    html = response.content.decode()
    assert response.status_code == 200
    assert "Forgot password?" in html
    assert f'href="{reverse("accounts:password_reset")}"' in html


@pytest.mark.django_db
def test_password_reset_request_sends_email_for_existing_user(client, mailoutbox):
    get_user_model().objects.create_user(
        username="reset@example.com",
        email="reset@example.com",
        password="A-strong-test-password-123",
    )

    response = client.post(
        reverse("accounts:password_reset"),
        {"email": "reset@example.com"},
    )

    assert response.status_code == 302
    assert response.url == reverse("accounts:password_reset_done")
    assert len(mailoutbox) == 1
    assert "Reset your Evidra password" in mailoutbox[0].subject
    assert "/accounts/password-reset/" in mailoutbox[0].body


def test_password_reset_request_view_renders(client):
    response = client.get(reverse("accounts:password_reset"))

    html = response.content.decode()
    assert response.status_code == 200
    assert "Reset your password" in html
    assert "Send reset link" in html


def test_password_reset_sent_view_renders(client):
    response = client.get(reverse("accounts:password_reset_done"))

    html = response.content.decode()
    assert response.status_code == 200
    assert "Password reset email sent" in html


@pytest.mark.django_db
def test_password_reset_confirm_view_renders_for_valid_token(client):
    user = get_user_model().objects.create_user(
        username="reset-form@example.com",
        email="reset-form@example.com",
        password="A-strong-test-password-123",
    )
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)

    response = client.get(
        reverse("accounts:password_reset_confirm", kwargs={"uidb64": uidb64, "token": token}),
        follow=True,
    )

    html = response.content.decode()
    assert response.status_code == 200
    assert "Choose a new password" in html
    assert "Reset password" in html


def test_password_reset_complete_view_renders(client):
    response = client.get(reverse("accounts:password_reset_complete"))

    html = response.content.decode()
    assert response.status_code == 200
    assert "Password reset complete" in html
