from __future__ import annotations

import socket

import pytest

from app import safe_probe


def _info(ip: str):
    return (socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443, 0, 0) if ":" in ip else (ip, 443))


def test_probe_rejects_non_http_schemes_and_url_credentials():
    with pytest.raises(ValueError):
        safe_probe.resolve_public_probe_target("file:///etc/passwd")
    with pytest.raises(ValueError):
        safe_probe.resolve_public_probe_target("https://user:secret@example.com/")


def test_probe_rejects_private_or_mixed_dns_answers(monkeypatch):
    monkeypatch.setattr(safe_probe.socket, "getaddrinfo", lambda *a, **kw: [_info("93.184.216.34"), _info("127.0.0.1")])
    with pytest.raises(ValueError, match="внутренних"):
        safe_probe.resolve_public_probe_target("https://example.com/health")


def test_probe_resolves_public_hostname_once_and_returns_pinned_address(monkeypatch):
    calls = []

    def fake_getaddrinfo(host, port, type=None):
        calls.append((host, port))
        return [_info("93.184.216.34")]

    monkeypatch.setattr(safe_probe.socket, "getaddrinfo", fake_getaddrinfo)
    target = safe_probe.resolve_public_probe_target("https://example.com/health")
    assert target.url == "https://example.com/health"
    assert target.hostname == "example.com"
    assert target.port == 443
    assert target.pinned_ip == "93.184.216.34"
    assert calls == [("example.com", 443)]


def test_pinned_backend_dials_the_validated_ip_and_leaves_other_hosts_unchanged(monkeypatch):
    backend = safe_probe._PinnedNetworkBackend("example.com", "93.184.216.34")
    calls = []

    class FakeStream:
        pass

    def fake_connect_tcp(host, port, **kwargs):
        calls.append((host, port, kwargs))
        return FakeStream()

    monkeypatch.setattr(backend._delegate, "connect_tcp", fake_connect_tcp)
    backend.connect_tcp("example.com", 443, timeout=3.0)
    backend.connect_tcp("other.example", 443, timeout=3.0)
    assert calls[0][0:2] == ("93.184.216.34", 443)
    assert calls[1][0:2] == ("other.example", 443)


def test_pinned_transport_keeps_original_https_host_for_tls_and_host_header(monkeypatch):
    seen = {}

    class FakeResponse:
        status = 204
        headers = [(b"content-type", b"text/plain")]
        stream = []

        def close(self):
            seen["closed"] = True

    class FakePool:
        def __init__(self, **kwargs):
            seen["backend"] = kwargs["network_backend"]

        def handle_request(self, request):
            seen["request_host"] = request.url.host
            seen["request_scheme"] = request.url.scheme
            seen["request_target"] = request.url.target
            return FakeResponse()

        def close(self):
            pass

    monkeypatch.setattr(safe_probe.httpcore, "ConnectionPool", FakePool)
    transport = safe_probe.PinnedProbeTransport("example.com", "93.184.216.34")
    import httpx
    response = transport.handle_request(httpx.Request("GET", "https://example.com/health"))
    assert response.status_code == 204
    assert seen["request_host"] == b"example.com"
    assert seen["request_scheme"] == b"https"
    assert seen["request_target"] == b"/health"
    assert seen["closed"] is True


def test_transport_connects_to_pinned_socket_while_sending_original_host_header():
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import httpx

    received = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            received["path"] = self.path
            received["host"] = self.headers.get("Host")
            self.send_response(204)
            self.end_headers()

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        transport = safe_probe.PinnedProbeTransport("probe.example", "127.0.0.1")
        request = httpx.Request("GET", f"http://probe.example:{port}/health")
        response = transport.handle_request(request)
        transport.close()
        assert response.status_code == 204
        assert received["path"] == "/health"
        assert received["host"] == f"probe.example:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
