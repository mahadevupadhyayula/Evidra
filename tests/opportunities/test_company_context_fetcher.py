import socket

import httpx
import pytest

from apps.opportunities.company_context import (
    CompanyContextFetcher,
    CompanyContextFetchError,
    UnsafeCompanyContextURLError,
    extract_visible_text,
    validate_safe_public_url,
)


def test_validate_safe_public_url_rejects_file_scheme():
    with pytest.raises(UnsafeCompanyContextURLError):
        validate_safe_public_url("file:///etc/passwd")


def test_validate_safe_public_url_rejects_localhost():
    with pytest.raises(UnsafeCompanyContextURLError):
        validate_safe_public_url("https://localhost/about")


def test_validate_safe_public_url_rejects_private_ip():
    with pytest.raises(UnsafeCompanyContextURLError):
        validate_safe_public_url("http://10.0.0.5/")


def test_validate_safe_public_url_rejects_hostname_resolving_to_private_ip(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 443))],
    )

    with pytest.raises(UnsafeCompanyContextURLError):
        validate_safe_public_url("https://example.com")


def test_fetcher_extracts_visible_text_and_does_not_fetch_links(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443))
        ],
    )
    requests = []

    def handler(request):
        requests.append(request.url)
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=(
                b"<html><head><title>Hidden</title><script>bad()</script></head>"
                b"<body><h1>Acme Product</h1>"
                b"<a href='https://example.com/next'>Next</a></body></html>"
            ),
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    result = CompanyContextFetcher(client=client).fetch("https://example.com")

    assert "Acme Product" in result.visible_text
    assert "bad()" not in result.visible_text
    assert len(requests) == 1


def test_fetcher_rejects_redirect_to_private_url(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, *args, **kwargs: (
            [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443))]
            if host == "example.com"
            else [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 80))]
        ),
    )

    def handler(request):
        return httpx.Response(302, headers={"location": "http://127.0.0.1/"}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)

    with pytest.raises(UnsafeCompanyContextURLError):
        CompanyContextFetcher(client=client).fetch("https://example.com")


def test_fetcher_enforces_response_size(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443))
        ],
    )

    def handler(request):
        return httpx.Response(
            200,
            headers={"content-type": "text/plain", "content-length": "20"},
            content=b"too large",
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)

    with pytest.raises(CompanyContextFetchError):
        CompanyContextFetcher(client=client, max_response_bytes=5).fetch("https://example.com")


def test_extract_visible_text_strips_script_and_style():
    text = extract_visible_text(
        b"<html><style>.x{}</style><body>Hello <script>bad()</script>World</body></html>",
        "text/html",
    )

    assert text == "Hello World"


def test_fetcher_enforces_streamed_response_size_without_content_length(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443))
        ],
    )

    def handler(request):
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            content=b"too large",
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)

    with pytest.raises(CompanyContextFetchError):
        CompanyContextFetcher(client=client, max_response_bytes=5).fetch("https://example.com")


def test_fetcher_rejects_invalid_content_length(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443))
        ],
    )

    def handler(request):
        return httpx.Response(
            200,
            headers={"content-type": "text/plain", "content-length": "not-a-number"},
            content=b"Example builds collaboration software.",
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)

    with pytest.raises(CompanyContextFetchError):
        CompanyContextFetcher(client=client).fetch("https://example.com")
