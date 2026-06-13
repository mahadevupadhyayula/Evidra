import pytest
from django.core.exceptions import ImproperlyConfigured

from config.settings import LOCAL_DEVELOPMENT_SECRET_KEY, get_secret_key


def test_secret_key_allows_local_development_fallback(monkeypatch):
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)

    assert get_secret_key(debug=True) == LOCAL_DEVELOPMENT_SECRET_KEY


def test_secret_key_requires_real_value_when_debug_is_false(monkeypatch):
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)

    with pytest.raises(ImproperlyConfigured):
        get_secret_key(debug=False)


def test_secret_key_rejects_placeholder_when_debug_is_false(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", LOCAL_DEVELOPMENT_SECRET_KEY)

    with pytest.raises(ImproperlyConfigured):
        get_secret_key(debug=False)


def test_secret_key_accepts_real_value_when_debug_is_false(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "real-secret-for-test-only")

    assert get_secret_key(debug=False) == "real-secret-for-test-only"
