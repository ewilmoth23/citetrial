from __future__ import annotations

import asyncio

import httpx
import pytest

from app.core.config import Settings
from app.ingestion.url_safety import UnsafeUrlError, normalize_url, validate_ip, validate_url
from app.ingestion.web import (
    ResponseTooLargeError,
    RetrievalError,
    UnsupportedMimeTypeError,
    retrieve_webpage,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "ftp://example.com/file",
        "file:///etc/passwd",
        "https://user:secret@example.com/",
        "https://localhost/",
        "https://localhost.localdomain/",
        "https://example.com:99999/",
        "javascript:alert(1)",
    ],
)
def test_rejects_unsafe_url_shapes(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        normalize_url(url)


def test_hostname_is_normalized_to_ascii_idna() -> None:
    normalized, parsed = normalize_url("https://b\u00fccher.example/report")
    assert normalized == "https://xn--bcher-kva.example/report"
    assert parsed.hostname == "xn--bcher-kva.example"


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "::1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.2",
        "169.254.169.254",
        "100.100.100.200",
        "224.0.0.1",
        "0.0.0.0",
    ],
)
def test_rejects_protected_ip_ranges(address: str) -> None:
    with pytest.raises(UnsafeUrlError):
        validate_ip(address)


@pytest.mark.asyncio
async def test_accepts_public_https_literal() -> None:
    value = await validate_url("https://93.184.216.34/a#fragment", Settings())
    assert value.normalized == "https://93.184.216.34/a"


@pytest.mark.asyncio
async def test_redirect_to_private_address_is_rejected() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://127.0.0.1/admin"})

    with pytest.raises(UnsafeUrlError):
        await retrieve_webpage(
            "https://93.184.216.34/",
            Settings(),
            transport=httpx.MockTransport(handler),
        )


@pytest.mark.asyncio
async def test_mime_type_is_enforced() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200, headers={"content-type": "application/octet-stream"}, content=b"x"
        )
    )
    with pytest.raises(UnsupportedMimeTypeError):
        await retrieve_webpage("https://93.184.216.34/", Settings(), transport=transport)


@pytest.mark.asyncio
async def test_valid_mocked_webpage_retrieval() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=b"<html><main><p>Stored evidence.</p></main></html>",
        )
    )
    result = await retrieve_webpage("https://93.184.216.34/report", Settings(), transport=transport)
    assert result.status_code == 200
    assert result.final_url.endswith("/report")
    assert b"Stored evidence" in result.content


@pytest.mark.asyncio
async def test_request_connects_to_validated_ip_with_original_host_and_sni(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def resolve(_hostname: str, _port: int) -> tuple[str, ...]:
        return ("93.184.216.34",)

    monkeypatch.setattr("app.ingestion.url_safety.resolve_public_addresses", resolve)

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://93.184.216.34:444/report?q=evidence"
        assert request.headers["host"] == "research.example:444"
        assert request.extensions["sni_hostname"] == "research.example"
        return httpx.Response(200, headers={"content-type": "text/plain"}, content=b"ok")

    result = await retrieve_webpage(
        "https://research.example:444/report?q=evidence",
        Settings(),
        transport=httpx.MockTransport(handler),
    )
    assert result.final_url == "https://research.example:444/report?q=evidence"


@pytest.mark.asyncio
async def test_each_redirect_uses_its_own_validated_address_and_tls_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    addresses = {
        "first.example": ("93.184.216.34",),
        "second.example": ("93.184.216.35",),
    }

    async def resolve(hostname: str, _port: int) -> tuple[str, ...]:
        return addresses[hostname]

    monkeypatch.setattr("app.ingestion.url_safety.resolve_public_addresses", resolve)
    observed: list[tuple[str, str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(
            (
                request.url.host,
                request.headers["host"],
                str(request.extensions["sni_hostname"]),
            )
        )
        if len(observed) == 1:
            return httpx.Response(302, headers={"location": "https://second.example/final"})
        return httpx.Response(200, headers={"content-type": "text/plain"}, content=b"ok")

    result = await retrieve_webpage(
        "https://first.example/start", Settings(), transport=httpx.MockTransport(handler)
    )
    assert observed == [
        ("93.184.216.34", "first.example", "first.example"),
        ("93.184.216.35", "second.example", "second.example"),
    ]
    assert result.final_url == "https://second.example/final"


@pytest.mark.asyncio
async def test_next_validated_address_is_tried_after_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def resolve(_hostname: str, _port: int) -> tuple[str, ...]:
        return ("93.184.216.34", "93.184.216.35")

    monkeypatch.setattr("app.ingestion.url_safety.resolve_public_addresses", resolve)
    observed: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request.url.host)
        if len(observed) == 1:
            raise httpx.ConnectError("first address unavailable", request=request)
        return httpx.Response(200, headers={"content-type": "text/plain"}, content=b"ok")

    await retrieve_webpage(
        "https://research.example/", Settings(), transport=httpx.MockTransport(handler)
    )
    assert observed == ["93.184.216.34", "93.184.216.35"]


@pytest.mark.asyncio
async def test_address_retries_share_one_configured_hop_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def resolve(_hostname: str, _port: int) -> tuple[str, ...]:
        return ("93.184.216.34", "93.184.216.35")

    monkeypatch.setattr("app.ingestion.url_safety.resolve_public_addresses", resolve)
    observed: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request.url.host)
        await asyncio.sleep(0.05)
        raise httpx.ConnectTimeout("unavailable", request=request)

    with pytest.raises(RetrievalError, match="timed out"):
        await retrieve_webpage(
            "https://research.example/",
            Settings(request_timeout_seconds=0.01),
            transport=httpx.MockTransport(handler),
        )
    assert observed == ["93.184.216.34"]


@pytest.mark.asyncio
async def test_redirect_cookie_is_not_replayed() -> None:
    observed_cookies: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_cookies.append(request.headers.get("cookie"))
        if len(observed_cookies) == 1:
            return httpx.Response(
                302,
                headers={
                    "location": "https://93.184.216.34/final",
                    "set-cookie": "tracking=secret; Path=/; Secure",
                },
            )
        return httpx.Response(200, headers={"content-type": "text/plain"}, content=b"ok")

    await retrieve_webpage(
        "https://93.184.216.34/start", Settings(), transport=httpx.MockTransport(handler)
    )
    assert observed_cookies == [None, None]


@pytest.mark.asyncio
async def test_redirect_limit_is_enforced() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(302, headers={"location": "/again"})
    )
    with pytest.raises(RetrievalError, match="redirect limit"):
        await retrieve_webpage(
            "https://93.184.216.34/", Settings(max_redirects=1), transport=transport
        )


@pytest.mark.asyncio
async def test_timeout_is_normalized() -> None:
    def timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    with pytest.raises(RetrievalError, match="timed out"):
        await retrieve_webpage(
            "https://93.184.216.34/", Settings(), transport=httpx.MockTransport(timeout)
        )


@pytest.mark.asyncio
async def test_declared_response_size_is_enforced() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            headers={"content-type": "text/html", "content-length": "1000"},
            content=b"small",
        )
    )
    with pytest.raises(ResponseTooLargeError):
        await retrieve_webpage(
            "https://93.184.216.34/",
            Settings(max_download_bytes=100),
            transport=transport,
        )


@pytest.mark.asyncio
async def test_streamed_response_size_is_enforced() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200, headers={"content-type": "text/html"}, content=b"x" * 101
        )
    )
    with pytest.raises(ResponseTooLargeError):
        await retrieve_webpage(
            "https://93.184.216.34/",
            Settings(max_download_bytes=100),
            transport=transport,
        )
