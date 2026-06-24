import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse


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


def test_signup_view_links_to_login(client):
    response = client.get(reverse("accounts:signup"))

    assert response.status_code == 200
    assert f'href="{reverse("accounts:login")}"' in response.content.decode()


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
