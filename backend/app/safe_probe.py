"""SSRF-resistant service probes that pin TCP connections to validated public IPs.

The request URL is intentionally kept unchanged so HTTP Host and TLS SNI/certificate
validation continue to use the requested hostname. Only the TCP destination is pinned.
"""
from __future__ import annotations

import ipaddress
import socket
import ssl
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpcore
import httpx


@dataclass(frozen=True)
class PublicProbeTarget:
    url: str
    hostname: str
    port: int
    pinned_ip: str


def _is_public_address(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_global
        and not ip.is_private
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_multicast
        and not ip.is_reserved
        and not ip.is_unspecified
    )


def resolve_public_probe_target(url: str) -> PublicProbeTarget:
    """Validate URL and resolve exactly once; reject the entire answer set if unsafe."""
    normalized_url = url.strip()
    parsed = urlsplit(normalized_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Разрешены только абсолютные URL http/https без учётных данных")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError("Указан некорректный порт") from exc

    hostname = parsed.hostname.rstrip(".")
    if not hostname:
        raise ValueError("Не задано имя узла")
    try:
        literal_ip = ipaddress.ip_address(hostname)
        addresses = [literal_ip]
        connect_hostname = str(literal_ip)
    except ValueError:
        try:
            connect_hostname = hostname.encode("idna").decode("ascii").lower()
            infos = socket.getaddrinfo(connect_hostname, port, type=socket.SOCK_STREAM)
        except (OSError, UnicodeError) as exc:
            raise ValueError("Не удалось безопасно разрешить DNS-имя проверяемого узла") from exc
        addresses = []
        for info in infos:
            sockaddr = info[4]
            if sockaddr and sockaddr[0]:
                try:
                    addresses.append(ipaddress.ip_address(sockaddr[0].split("%", 1)[0]))
                except ValueError:
                    continue

    if not addresses:
        raise ValueError("Не удалось определить IP-адрес узла")
    if any(not _is_public_address(address) for address in addresses):
        raise ValueError(
            "Проверка внутренних, локальных и зарезервированных сетевых адресов запрещена политикой безопасности"
        )

    # Choose one of the validated results, then pin the actual socket connect to it.
    selected_ip = str(addresses[0])
    return PublicProbeTarget(
        url=normalized_url,
        hostname=connect_hostname,
        port=port,
        pinned_ip=selected_ip,
    )


class _PinnedNetworkBackend(httpcore.NetworkBackend):
    """Delegate normal socket operations while pinning a hostname to one IP address."""

    def __init__(self, hostname: str, pinned_ip: str) -> None:
        self._hostname = hostname.rstrip(".").casefold()
        self._pinned_ip = pinned_ip
        self._delegate = httpcore.SyncBackend()

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if isinstance(host, bytes):
            host_text = host.decode("ascii", errors="ignore")
        else:
            host_text = str(host)
        dial_host = self._pinned_ip if host_text.rstrip(".").casefold() == self._hostname else host_text
        return self._delegate.connect_tcp(
            dial_host,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    def connect_unix_socket(self, path, timeout=None, socket_options=None):
        return self._delegate.connect_unix_socket(path, timeout=timeout, socket_options=socket_options)

    def sleep(self, seconds: float) -> None:
        self._delegate.sleep(seconds)


class PinnedProbeTransport(httpx.BaseTransport):
    """Small synchronous transport backed by public httpcore APIs and pinned DNS."""

    def __init__(self, hostname: str, pinned_ip: str) -> None:
        self._pool = httpcore.ConnectionPool(
            ssl_context=ssl.create_default_context(),
            network_backend=_PinnedNetworkBackend(hostname, pinned_ip),
            retries=0,
        )

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.read(),
            extensions=request.extensions,
        )
        try:
            core_response = self._pool.handle_request(core_request)
            try:
                # A health probe only needs status/headers; do not download arbitrary response bodies.
                return httpx.Response(
                    status_code=core_response.status,
                    headers=core_response.headers,
                    content=b"",
                    request=request,
                )
            finally:
                core_response.close()
        except httpcore.HTTPError as exc:
            raise httpx.TransportError(str(exc), request=request) from exc

    def close(self) -> None:
        self._pool.close()
