import pytest
from django.contrib.auth import get_user_model

from apps.accounts.forms import EmailSignupForm


@pytest.mark.django_db
def test_signup_form_field_order_matches_mockup():
    form = EmailSignupForm()

    assert list(form.fields) == ["full_name", "email", "password1", "password2"]


@pytest.mark.django_db
def test_signup_form_normalizes_email_and_creates_user():
    form = EmailSignupForm(
        data={
            "full_name": "Example User",
            "email": "USER@Example.COM",
            "password1": "A-strong-test-password-123",
            "password2": "A-strong-test-password-123",
        }
    )

    assert form.is_valid(), form.errors
    user = form.save()

    assert user.email == "user@example.com"
    assert user.username == "user@example.com"
    assert user.first_name == "Example User"


@pytest.mark.django_db
def test_signup_form_rejects_duplicate_email_case_insensitively():
    User = get_user_model()
    User.objects.create_user(
        username="user@example.com",
        email="user@example.com",
        password="A-strong-test-password-123",
    )

    form = EmailSignupForm(
        data={
            "full_name": "Example User",
            "email": "USER@example.com",
            "password1": "Another-strong-test-password-123",
            "password2": "Another-strong-test-password-123",
        }
    )

    assert not form.is_valid()
    assert "email" in form.errors
