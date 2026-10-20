"""The Caddy reverse proxy (compose.tls.yaml, roadmap item 14).

Runs only in TLS mode (`E2E_TLS=1 e2e/run.sh`); in the plain stack there is
no proxy to test. Each test pins something the load balancer does at go-live.
"""

import socket
import uuid

import httpx
import pytest

from e2e.helpers import TLS_CA, compose, tls_verify

pytestmark = pytest.mark.skipif(not TLS_CA, reason="TLS mode only: E2E_TLS=1 e2e/run.sh")

APP_HOST = "app.localhost"
API_HOST = "api.localhost"
CADDY_IP = "10.250.0.10"  # compose.tls.yaml
SPOOFED_IP = "203.0.113.9"  # TEST-NET-3: documentation range, never a real client
UNPUBLISHED_PORTS = (3000, 5000)
CONNECT_TIMEOUT_SECONDS = 2
HSTS_ONE_YEAR = "max-age=31536000"


def test_api_certificate_verifies_against_the_local_ca(api: httpx.Client) -> None:
    """A fixture client with verify=<CA root>: a wrong or self-signed certificate would raise here."""
    assert api.get("/health").status_code == 200


def test_app_is_served_over_https() -> None:
    response = httpx.get(f"https://{APP_HOST}/api/health", verify=tls_verify(), timeout=15)
    assert response.status_code == 200


@pytest.mark.parametrize("host", [APP_HOST, API_HOST])
def test_plain_http_redirects_to_https(host: str) -> None:
    response = httpx.get(f"http://{host}/some/path", follow_redirects=False, timeout=15)
    assert response.status_code == 308
    assert response.headers["location"] == f"https://{host}/some/path"


@pytest.mark.parametrize("host", [APP_HOST, API_HOST])
def test_security_headers_are_set_and_the_server_is_not_named(host: str) -> None:
    response = httpx.get(f"https://{host}/", verify=tls_verify(), timeout=15)
    assert response.headers["strict-transport-security"] == HSTS_ONE_YEAR
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "server" not in response.headers


@pytest.mark.parametrize("port", UNPUBLISHED_PORTS)
def test_the_app_is_only_reachable_through_the_proxy(port: int) -> None:
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=CONNECT_TIMEOUT_SECONDS).close()


def test_backend_sees_the_real_client_and_ignores_a_spoofed_one(api: httpx.Client) -> None:
    """uvicorn trusts X-Forwarded-For from Caddy only, and Caddy discards the client's own.

    Without FORWARDED_ALLOW_IPS the access log shows Caddy's address for every
    request; if Caddy passed the header through, it would show the spoofed one.
    """
    marker = uuid.uuid4().hex
    api.get("/health", params={"probe": marker}, headers={"X-Forwarded-For": SPOOFED_IP})

    logs = compose("logs", "--no-color", "backend").stdout
    line = next(line for line in logs.splitlines() if marker in line)
    assert CADDY_IP not in line, line
    assert SPOOFED_IP not in line, line


@pytest.mark.parametrize(
    "path",
    ["/metrics", "/metrics/", "/%6Detrics"],
    ids=["plain", "trailing-slash", "percent-encoded"],
)
def test_metrics_endpoint_is_not_reachable_through_the_proxy(api: httpx.Client, path: str) -> None:
    """Prometheus scrapes on the compose network only (item 15). uvicorn
    decodes %6D to "m", so the encoded form would reach the route if Caddy
    matched the raw path. Caddy's own 404 has an empty body; the API's would
    be JSON."""
    response = api.get(path)
    assert response.status_code == 404
    assert response.text == ""
