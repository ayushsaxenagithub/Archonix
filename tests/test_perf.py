from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import pytest
from conftest import REPO_ROOT

from archonix.cli import main
from archonix.errors import PolicyError
from archonix.perf import k6_script, openapi_endpoints, percentile, smoke
from archonix.schemas import validate


class Handler(BaseHTTPRequestHandler):
    hits: ClassVar[list[str]] = []

    def do_GET(self) -> None:
        Handler.hits.append(self.path)
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "http://example.invalid/elsewhere")
            self.end_headers()
            return
        status = 500 if self.path == "/boom" else 200
        self.send_response(status)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def server() -> Iterator[str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_percentile_reliability_rule() -> None:
    values = sorted(float(i) for i in range(1, 101))
    assert percentile(values, 0.95) == {"value": 95.0, "reliable": True}
    assert percentile(values, 0.99)["reliable"] is False
    assert percentile(values[:10], 0.5) == {"value": 5.0, "reliable": True}
    assert percentile([], 0.5) == {"value": None, "reliable": False}


def test_smoke_against_loopback(server: str) -> None:
    report = smoke(base_url=server, paths=["/health", "/boom"], requests=20, warmup=1, p95_ms=1000)
    validate(report, "performance-report")
    health, boom = report["endpoints"]
    assert (
        health["samples"] == 20 and health["errors"] == 0 and health["status_codes"] == {"200": 20}
    )
    assert health["latency_ms"]["p95"]["reliable"] is False  # 20 samples is too few for p95
    assert health["threshold"]["result"] == "unknown"
    assert boom["errors"] == 20
    assert report["target"]["loopback"] is True


def test_redirects_are_not_followed(server: str) -> None:
    Handler.hits.clear()
    report = smoke(base_url=server, paths=["/redirect"], requests=3, warmup=0)
    assert report["endpoints"][0]["status_codes"] == {"302": 3}


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"method": "POST"}, "only issue GET/HEAD"),
        ({"requests": 501}, "between 1 and 500"),
        ({"concurrency": 11}, "between 1 and 10"),
        ({"base_url": "http://203.0.113.10"}, "not a loopback host"),
    ],
)
def test_safety_limits(kwargs: dict, message: str) -> None:
    args = {"base_url": "http://127.0.0.1:9", "paths": ["/x"], **kwargs}
    with pytest.raises(PolicyError, match=message):
        smoke(**args)


def test_remote_requires_matching_authorized_host() -> None:
    with pytest.raises(PolicyError):
        smoke(base_url="http://203.0.113.10", paths=["/x"], authorized_host="198.51.100.1")


def test_cli_requires_allow_network(server: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["perf", "smoke", "--base-url", server, "--path", "/health"]) == 3
    assert (
        main(
            [
                "perf",
                "smoke",
                "--base-url",
                server,
                "--path",
                "/health",
                "--requests",
                "5",
                "--allow-network",
                "--format",
                "json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["endpoints"][0]["samples"] == 5


def test_auth_header_value_never_reported(server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMOKE_AUTH", "Bearer synthetic-token-value-123")
    report = smoke(base_url=server, paths=["/health"], requests=2, auth_header_env="SMOKE_AUTH")
    assert "synthetic-token-value-123" not in json.dumps(report)


def test_openapi_endpoints() -> None:
    rows = openapi_endpoints(REPO_ROOT / "examples/python-service/openapi.json")
    by = {(r["method"], r["path"]): r for r in rows}
    assert by[("GET", "/health")]["smoke_candidate"] is True
    assert by[("GET", "/prices/{sku}")]["smoke_candidate"] is False
    assert by[("GET", "/prices/{sku}")]["requires_auth"] is True
    assert by[("POST", "/orders")]["smoke_candidate"] is False


def test_k6_script(tmp_path: Path) -> None:
    script = k6_script(
        "http://127.0.0.1:8000/",
        ["/health"],
        vus=3,
        duration="10s",
        p95_ms=200,
        max_error_rate=0.01,
    )
    assert "vus: 3" in script and "p(95)<200" in script and "rate<0.01" in script
    assert "http.get" in script and "http.post" not in script
