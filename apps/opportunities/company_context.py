from __future__ import annotations

import ipaddress
import socket
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

MAX_REDIRECTS = 3
MAX_RESPONSE_BYTES = 512_000
MAX_EXTRACTED_TEXT_CHARS = 20_000
TIMEOUT_SECONDS = 5.0
ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_CONTENT_TYPES = ("text/html", "text/plain", "application/xhtml+xml")


class CompanyContextFetchError(RuntimeError):
    """Raised when a company context page cannot be fetched safely."""


class UnsafeCompanyContextURLError(CompanyContextFetchError):
    """Raised when a company context URL is unsafe to fetch."""


@dataclass(frozen=True)
class CompanyContextFetchResult:
    final_url: str
    visible_text: str
    content_type: str


class _VisibleTextParser(HTMLParser):
    hidden_tags = {"script", "style", "noscript", "head", "title", "meta", "link", "svg"}

    def __init__(self) -> None:
        super().__init__()
        self._hidden_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() in self.hidden_tags:
            self._hidden_depth += 1

    def handle_endtag(self, tag: str):
        if tag.lower() in self.hidden_tags and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str):
        if self._hidden_depth == 0:
            text = data.strip()
            if text:
                self.parts.append(text)

    def text(self) -> str:
        return normalize_visible_text(" ".join(self.parts))


def normalize_visible_text(value: str) -> str:
    return " ".join(value.split())[:MAX_EXTRACTED_TEXT_CHARS]


def extract_visible_text(content: bytes, content_type: str) -> str:
    text = content.decode("utf-8", errors="replace")
    if "html" not in content_type.casefold():
        return normalize_visible_text(text)
    parser = _VisibleTextParser()
    parser.feed(text)
    return parser.text()


def validate_safe_public_url(url: str) -> str:
    candidate = url.strip()
    parsed = urlparse(candidate)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UnsafeCompanyContextURLError("Enter a public http or https URL.")
    if not parsed.hostname:
        raise UnsafeCompanyContextURLError("Enter a URL with a valid hostname.")
    if parsed.username or parsed.password:
        raise UnsafeCompanyContextURLError("URL credentials are not allowed.")
    hostname = parsed.hostname.rstrip(".").casefold()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise UnsafeCompanyContextURLError("Localhost URLs are not allowed.")
    _validate_hostname_addresses(hostname)
    return candidate


def _validate_hostname_addresses(hostname: str) -> None:
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        addresses = _resolve_hostname(hostname)
    else:
        addresses = [ip]
    for address in addresses:
        if _is_unsafe_address(address):
            raise UnsafeCompanyContextURLError("Private or internal network URLs are not allowed.")


# DNS resolution is intentionally synchronous in the MBP fetcher; it is performed
# before the bounded HTTP request so unsafe resolved addresses are rejected early.
def _resolve_hostname(hostname: str) -> Iterable[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise CompanyContextFetchError("Could not resolve the company URL.") from exc
    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        sockaddr = info[4]
        addresses.append(ipaddress.ip_address(sockaddr[0]))
    if not addresses:
        raise CompanyContextFetchError("Could not resolve the company URL.")
    return addresses


def _is_unsafe_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(
        [
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        ]
    )


@dataclass(frozen=True)
class CompanyContextFetcher:
    client: httpx.Client | None = None
    timeout_seconds: float = TIMEOUT_SECONDS
    max_redirects: int = MAX_REDIRECTS
    max_response_bytes: int = MAX_RESPONSE_BYTES

    def fetch(self, url: str) -> CompanyContextFetchResult:
        current_url = validate_safe_public_url(url)
        redirects = 0
        close_client = self.client is None
        client = self.client or httpx.Client(timeout=self.timeout_seconds, follow_redirects=False)
        try:
            while True:
                with self._stream(client, current_url) as response:
                    if response.is_redirect:
                        redirects += 1
                        if redirects > self.max_redirects:
                            raise CompanyContextFetchError("Company URL redirected too many times.")
                        location = response.headers.get("location")
                        if not location:
                            raise CompanyContextFetchError(
                                "Company URL redirect did not include a location."
                            )
                        current_url = validate_safe_public_url(str(response.url.join(location)))
                        continue
                    if response.status_code < 200 or response.status_code >= 300:
                        raise CompanyContextFetchError(
                            "Company URL returned an unsuccessful response."
                        )
                    content_type = (
                        response.headers.get("content-type", "text/plain").split(";")[0].strip()
                    )
                    if content_type not in ALLOWED_CONTENT_TYPES:
                        raise CompanyContextFetchError("Company URL returned unsupported content.")
                    content = self._bounded_content(response)
                    visible_text = extract_visible_text(content, content_type)
                    if not visible_text:
                        raise CompanyContextFetchError("No visible company text was found.")
                    return CompanyContextFetchResult(
                        final_url=str(response.url),
                        visible_text=visible_text,
                        content_type=content_type,
                    )
        finally:
            if close_client:
                client.close()

    @contextmanager
    def _stream(self, client: httpx.Client, url: str):
        try:
            with client.stream("GET", url, timeout=self.timeout_seconds) as response:
                yield response
        except httpx.TimeoutException as exc:
            raise CompanyContextFetchError("Company URL timed out.") from exc
        except httpx.HTTPError as exc:
            raise CompanyContextFetchError("Company URL could not be fetched.") from exc

    def _bounded_content(self, response: httpx.Response) -> bytes:
        content_length = response.headers.get("content-length")
        if content_length:
            try:
                declared_length = int(content_length)
            except ValueError as exc:
                raise CompanyContextFetchError(
                    "Company URL returned invalid response metadata."
                ) from exc
            if declared_length > self.max_response_bytes:
                raise CompanyContextFetchError("Company URL response is too large.")
        chunks: list[bytes] = []
        total = 0
        try:
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > self.max_response_bytes:
                    raise CompanyContextFetchError("Company URL response is too large.")
                chunks.append(chunk)
        except httpx.TimeoutException as exc:
            raise CompanyContextFetchError("Company URL timed out.") from exc
        except httpx.HTTPError as exc:
            raise CompanyContextFetchError("Company URL could not be fetched.") from exc
        return b"".join(chunks)
