from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit, urlunsplit

from app.core.config import Settings


class UnsafeUrlError(ValueError):
    """Raised before network access when a URL may reach a protected address."""


BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain", "metadata.google.internal"}
BLOCKED_METADATA_IPS = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("100.100.100.200"),
}


@dataclass(frozen=True)
class ValidatedUrl:
    normalized: str
    hostname: str
    addresses: tuple[str, ...]


def _is_forbidden_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        address in BLOCKED_METADATA_IPS
        or address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def validate_ip(address_text: str) -> str:
    try:
        address = ipaddress.ip_address(address_text.split("%", 1)[0])
    except ValueError as exc:
        raise UnsafeUrlError("URL resolved to an invalid IP address") from exc
    if _is_forbidden_address(address):
        raise UnsafeUrlError("URL resolves to a local, private, reserved, or metadata address")
    return address.compressed


def normalize_url(raw_url: str, *, allow_http: bool = False) -> tuple[str, SplitResult]:
    if any(ord(char) < 32 for char in raw_url):
        raise UnsafeUrlError("URL contains control characters")
    try:
        parsed = urlsplit(raw_url.strip())
        port = parsed.port
    except ValueError as exc:
        raise UnsafeUrlError("URL is malformed") from exc
    allowed_schemes = {"https"} | ({"http"} if allow_http else set())
    if parsed.scheme.lower() not in allowed_schemes:
        raise UnsafeUrlError("Only HTTPS URLs are allowed")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeUrlError("Embedded URL credentials are not allowed")
    if not parsed.hostname:
        raise UnsafeUrlError("URL must contain a hostname")
    try:
        hostname = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise UnsafeUrlError("URL hostname is invalid") from exc
    if hostname in BLOCKED_HOSTNAMES or hostname.endswith(".localhost"):
        raise UnsafeUrlError("Localhost URLs are not allowed")
    if port is not None and not 1 <= port <= 65535:
        raise UnsafeUrlError("URL port is invalid")
    default_port = 443 if parsed.scheme.lower() == "https" else 80
    display_host = f"[{hostname}]" if ":" in hostname else hostname
    netloc = display_host if port in (None, default_port) else f"{display_host}:{port}"
    path = parsed.path or "/"
    normalized = urlunsplit((parsed.scheme.lower(), netloc, path, parsed.query, ""))
    return normalized, urlsplit(normalized)


async def resolve_public_addresses(hostname: str, port: int) -> tuple[str, ...]:
    try:
        literal = ipaddress.ip_address(hostname.split("%", 1)[0])
    except ValueError:
        loop = asyncio.get_running_loop()
        try:
            results = await loop.getaddrinfo(
                hostname,
                port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
                proto=socket.IPPROTO_TCP,
            )
        except socket.gaierror as exc:
            raise UnsafeUrlError("URL hostname could not be resolved") from exc
        addresses = tuple(sorted({validate_ip(item[4][0]) for item in results}))
    else:
        addresses = (validate_ip(literal.compressed),)
    if not addresses:
        raise UnsafeUrlError("URL hostname did not resolve to an address")
    return addresses


async def validate_url(raw_url: str, settings: Settings) -> ValidatedUrl:
    normalized, parsed = normalize_url(raw_url, allow_http=settings.allow_http_urls)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = await resolve_public_addresses(parsed.hostname or "", port)
    return ValidatedUrl(normalized, parsed.hostname or "", addresses)
