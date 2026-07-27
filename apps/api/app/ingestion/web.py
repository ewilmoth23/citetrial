from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from app.core.config import Settings
from app.ingestion.url_safety import UnsafeUrlError, ValidatedUrl, validate_url


class RetrievalError(RuntimeError):
    pass


class ResponseTooLargeError(RetrievalError):
    pass


class UnsupportedMimeTypeError(RetrievalError):
    pass


ALLOWED_WEB_MIME_TYPES = {"text/html", "application/xhtml+xml", "text/plain"}


@dataclass(frozen=True)
class RetrievedWebpage:
    original_url: str
    final_url: str
    redirect_count: int
    status_code: int
    mime_type: str
    content: bytes
    encoding: str | None


@dataclass(frozen=True)
class _FetchedHop:
    redirect_location: str | None
    status_code: int
    mime_type: str | None = None
    content: bytes = b""
    encoding: str | None = None


def _pinned_request_url(validated: ValidatedUrl, address: str) -> str:
    parsed = urlsplit(validated.normalized)
    display_address = f"[{address}]" if ":" in address else address
    default_port = 443 if parsed.scheme == "https" else 80
    netloc = (
        display_address
        if parsed.port in (None, default_port)
        else f"{display_address}:{parsed.port}"
    )
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, ""))


async def _bounded_body(response: httpx.Response, maximum: int) -> bytes:
    declared = response.headers.get("content-length")
    if declared:
        try:
            if int(declared) > maximum:
                raise ResponseTooLargeError("Remote response exceeds the configured size limit")
        except ValueError:
            pass
    parts: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > maximum:
            raise ResponseTooLargeError("Remote response exceeds the configured size limit")
        parts.append(chunk)
    return b"".join(parts)


async def _fetch_hop(
    validated: ValidatedUrl,
    address: str,
    settings: Settings,
    headers: dict[str, str],
    transport: httpx.AsyncBaseTransport | None,
) -> _FetchedHop:
    parsed = urlsplit(validated.normalized)
    request_headers = {**headers, "Host": parsed.netloc}
    timeout = httpx.Timeout(settings.request_timeout_seconds)
    # A new client for every IP attempt and redirect hop prevents a connection authenticated for
    # one hostname from being reused for another hostname that resolves to the same address.
    async with httpx.AsyncClient(
        follow_redirects=False,
        timeout=timeout,
        cookies=None,
        transport=transport,
        trust_env=False,
    ) as client:
        client.cookies.clear()
        async with client.stream(
            "GET",
            _pinned_request_url(validated, address),
            headers=request_headers,
            extensions={"sni_hostname": validated.hostname},
        ) as response:
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise RetrievalError("Redirect response did not include a Location header")
                return _FetchedHop(
                    redirect_location=location,
                    status_code=response.status_code,
                )
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if content_type not in ALLOWED_WEB_MIME_TYPES:
                raise UnsupportedMimeTypeError(
                    f"Unsupported webpage MIME type: {content_type or 'missing'}"
                )
            body = await _bounded_body(response, settings.max_download_bytes)
            return _FetchedHop(
                redirect_location=None,
                status_code=response.status_code,
                mime_type=content_type,
                content=body,
                encoding=response.encoding,
            )


async def _fetch_validated_hop(
    validated: ValidatedUrl,
    settings: Settings,
    headers: dict[str, str],
    transport: httpx.AsyncBaseTransport | None,
) -> _FetchedHop:
    last_request_error: tuple[str, httpx.RequestError] | None = None
    try:
        # DNS may return many addresses. Keep all connection attempts within one configured hop timeout
        # so an attacker cannot multiply the timeout by publishing a long address list.
        async with asyncio.timeout(settings.request_timeout_seconds):
            for address in validated.addresses:
                try:
                    return await _fetch_hop(validated, address, settings, headers, transport)
                except UnsafeUrlError:
                    raise
                except httpx.TimeoutException as exc:
                    last_request_error = ("Webpage retrieval timed out", exc)
                except httpx.HTTPStatusError as exc:
                    raise RetrievalError(
                        f"Webpage returned HTTP {exc.response.status_code}"
                    ) from exc
                except httpx.RequestError as exc:
                    last_request_error = ("Webpage could not be retrieved", exc)
    except TimeoutError as exc:
        raise RetrievalError("Webpage retrieval timed out") from exc
    if last_request_error is not None:
        message, cause = last_request_error
        raise RetrievalError(message) from cause
    raise RetrievalError("Webpage hostname did not provide a usable address")


async def retrieve_webpage(
    raw_url: str,
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> RetrievedWebpage:
    validated = await validate_url(raw_url, settings)
    current = validated.normalized
    original = current
    headers = {
        "User-Agent": "CiteTrail/0.1 (+local research source importer)",
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8",
        "Accept-Encoding": "identity",
    }
    for redirect_count in range(settings.max_redirects + 1):
        hop = await _fetch_validated_hop(validated, settings, headers, transport)
        if hop.redirect_location is not None:
            if redirect_count >= settings.max_redirects:
                raise RetrievalError("Remote response exceeded the redirect limit")
            current = urljoin(current, hop.redirect_location)
            validated = await validate_url(current, settings)
            current = validated.normalized
            continue
        return RetrievedWebpage(
            original_url=original,
            final_url=current,
            redirect_count=redirect_count,
            status_code=hop.status_code,
            mime_type=hop.mime_type or "",
            content=hop.content,
            encoding=hop.encoding,
        )
    raise RetrievalError("Remote response exceeded the redirect limit")
