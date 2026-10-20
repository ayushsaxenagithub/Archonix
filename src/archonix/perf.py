"""Bounded API smoke measurement and load-test scenario generation.

Smoke checks issue a small, capped number of GET/HEAD requests to endpoints the user
names explicitly. They are not load tests and produce no capacity claims. Even GET
requests can have side effects; the user must only target endpoints they know are safe
and are authorized to exercise. Non-loopback hosts require ``--authorized-host``.
"""

from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from ipaddress import ip_address
from pathlib import Path
from statistics import fmean
from typing import Any
from urllib.parse import urljoin, urlsplit

from . import SCHEMA_VERSION
from .errors import ArchonixError, PolicyError
from .timeutil import utc_now

MAX_REQUESTS = 500
MAX_CONCURRENCY = 10
MAX_WARMUP = 20
SAFE_METHODS = ("GET", "HEAD")
MIN_TAIL_SAMPLES = 5
HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def percentile(sorted_values: list[float], p: float) -> dict[str, Any]:
    """Nearest-rank percentile; reliable only with >= MIN_TAIL_SAMPLES samples above it."""
    n = len(sorted_values)
    if n == 0:
        return {"value": None, "reliable": False}
    rank = max(1, math.ceil(p * n))
    reliable = n * (1 - p) >= MIN_TAIL_SAMPLES
    return {"value": round(sorted_values[rank - 1], 3), "reliable": reliable}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None  # a 3xx is recorded as-is; never follow to another location


def _opener() -> urllib.request.OpenerDirector:
    # ProxyHandler({}) ignores *_PROXY environment variables so requests go only to the target.
    return urllib.request.build_opener(_NoRedirect, urllib.request.ProxyHandler({}))


def _one(
    opener: urllib.request.OpenerDirector,
    url: str,
    method: str,
    headers: dict[str, str],
    timeout: float,
) -> tuple[float, int | None, str | None]:
    req = urllib.request.Request(url, method=method, headers=headers)  # noqa: S310 - scheme checked
    t0 = time.perf_counter()
    try:
        with opener.open(req, timeout=timeout) as resp:
            resp.read(65536)
            code: int | None = resp.status
        err = None
    except urllib.error.HTTPError as exc:
        code, err = exc.code, None
    except TimeoutError:
        code, err = None, "timeout"
    except (urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        code, err = None, "timeout" if isinstance(reason, TimeoutError) else f"error: {reason}"
    return (time.perf_counter() - t0) * 1000.0, code, err


def smoke(
    *,
    base_url: str,
    paths: list[str],
    method: str = "GET",
    requests: int = 20,
    concurrency: int = 1,
    warmup: int = 2,
    timeout: float = 5.0,
    authorized_host: str | None = None,
    auth_header_env: str | None = None,
    p95_ms: float | None = None,
    max_error_rate: float | None = None,
    revision: str | None = None,
    environment: str | None = None,
) -> dict[str, Any]:
    method = method.upper()
    if method not in SAFE_METHODS:
        raise PolicyError(f"smoke checks only issue {'/'.join(SAFE_METHODS)}; {method} refused")
    if not 1 <= requests <= MAX_REQUESTS:
        raise PolicyError(f"--requests must be between 1 and {MAX_REQUESTS}")
    if not 1 <= concurrency <= MAX_CONCURRENCY:
        raise PolicyError(f"--concurrency must be between 1 and {MAX_CONCURRENCY}")
    if not 0 <= warmup <= MAX_WARMUP:
        raise PolicyError(f"--warmup must be between 0 and {MAX_WARMUP}")
    parts = urlsplit(base_url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ArchonixError("--base-url must be an http(s) URL with a host")
    loopback = is_loopback(parts.hostname)
    if not loopback and authorized_host != parts.hostname:
        raise PolicyError(
            f"{parts.hostname} is not a loopback host; pass --authorized-host "
            f"{parts.hostname} only if you are authorized to test it"
        )
    headers = {"User-Agent": "archonix-smoke/0.1"}
    if auth_header_env:
        token = os.environ.get(auth_header_env)
        if not token:
            raise ArchonixError(f"environment variable {auth_header_env} is not set")
        headers["Authorization"] = token  # value is never written to the report

    opener = _opener()
    endpoints = []
    for path in paths:
        if not path.startswith("/"):
            raise ArchonixError(f"path {path!r} must start with '/'")
        url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
        if urlsplit(url).hostname != parts.hostname:
            raise PolicyError(f"{path!r} resolves outside the target host")
        for _ in range(warmup):
            _one(opener, url, method, headers, timeout)
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            results = list(
                pool.map(
                    lambda _, u=url: _one(opener, u, method, headers, timeout), range(requests)
                )
            )
        wall = time.perf_counter() - t0
        codes: dict[str, int] = {}
        timeouts = errors = 0
        latencies = []
        for ms, code, err in results:
            if err == "timeout":
                timeouts += 1
                errors += 1
                continue
            if err:
                errors += 1
                continue
            codes[str(code)] = codes.get(str(code), 0) + 1
            if code is not None and code >= 500:
                errors += 1
            latencies.append(ms)
        latencies.sort()
        p95 = percentile(latencies, 0.95)
        threshold_result = "not-configured"
        if p95_ms is not None or max_error_rate is not None:
            checks = []
            if p95_ms is not None:
                checks.append(None if not p95["reliable"] else p95["value"] <= p95_ms)
            if max_error_rate is not None:
                checks.append(errors / requests <= max_error_rate)
            threshold_result = (
                "fail" if False in checks else "unknown" if None in checks else "pass"
            )
        endpoints.append(
            {
                "method": method,
                "path": path,
                "samples": len(latencies),
                "errors": errors,
                "timeouts": timeouts,
                "status_codes": codes,
                "duration_seconds": round(wall, 3),
                "throughput_rps": round(requests / wall, 2) if wall > 0 else None,
                "latency_ms": {
                    "min": round(latencies[0], 3) if latencies else None,
                    "mean": round(fmean(latencies), 3) if latencies else None,
                    "max": round(latencies[-1], 3) if latencies else None,
                    "p50": percentile(latencies, 0.50),
                    "p95": p95,
                    "p99": percentile(latencies, 0.99),
                },
                "threshold": {
                    "p95_ms": p95_ms,
                    "max_error_rate": max_error_rate,
                    "result": threshold_result,
                },
            }
        )
    return {
        "kind": "performance-report",
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "revision": revision,
        "environment": environment,
        "methodology": {
            "type": "smoke",
            "requests_per_endpoint": requests,
            "concurrency": concurrency,
            "warmup_requests": warmup,
            "timeout_seconds": timeout,
            "percentile_method": "nearest-rank over successful responses",
            "reliability_rule": f"a percentile p is reliable only when samples x (1 - p) >= "
            f"{MIN_TAIL_SAMPLES} (p95 needs >= 100, p99 >= 500)",
        },
        "target": {"base_url": base_url, "loopback": loopback},
        "endpoints": endpoints,
        "limitations": [
            "Smoke measurement only: small sample, single client host, no capacity or "
            "reliability claim. Use a load-testing tool for load evidence.",
            "Errors count transport failures, timeouts and 5xx responses; 4xx responses are "
            "listed under status codes.",
            "Throughput is bounded by the configured client concurrency, not server capacity.",
            "Redirects are recorded and not followed; proxies from the environment are ignored.",
        ],
    }


def openapi_endpoints(spec_path: Path) -> list[dict[str, Any]]:
    try:
        text = spec_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ArchonixError(f"cannot read {spec_path}: {exc}") from exc
    if spec_path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ArchonixError(
                "YAML OpenAPI files need PyYAML (pip install pyyaml); or convert the spec to JSON"
            ) from exc
        spec = yaml.safe_load(text)
    else:
        try:
            spec = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ArchonixError(f"{spec_path}: invalid JSON: {exc}") from exc
    if not isinstance(spec, dict) or not isinstance(spec.get("paths"), dict):
        raise ArchonixError(f"{spec_path}: not an OpenAPI document (no 'paths' object)")
    out = []
    for path, item in spec["paths"].items():
        if not isinstance(item, dict):
            continue
        shared = item.get("parameters", [])
        for method in HTTP_METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            params = [*shared, *op.get("parameters", [])]
            required = [p.get("name") for p in params if isinstance(p, dict) and p.get("required")]
            safe = method.upper() in SAFE_METHODS and not required and "{" not in path
            out.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "operation_id": op.get("operationId"),
                    "summary": op.get("summary"),
                    "requires_auth": bool(op.get("security", spec.get("security"))),
                    "required_parameters": required,
                    "smoke_candidate": safe,
                    "note": "candidate only: confirm the endpoint has no side effects"
                    if safe
                    else "not a smoke candidate (unsafe method or required parameters)",
                }
            )
    return out


def k6_script(
    base_url: str,
    paths: list[str],
    *,
    vus: int,
    duration: str,
    p95_ms: float | None,
    max_error_rate: float | None,
) -> str:
    """Generate a reviewable k6 scenario. Archonix does not run load tests itself."""
    thresholds = []
    if p95_ms is not None:
        thresholds.append(f"    http_req_duration: ['p(95)<{p95_ms}'],")
    if max_error_rate is not None:
        thresholds.append(f"    http_req_failed: ['rate<{max_error_rate}'],")
    targets = ",\n".join(f"  {json.dumps(p)}" for p in paths)
    return f"""// Generated by archonix perf k6-script. Review before running.
// Run only against targets you are authorized to load test, never production
// without explicit approval. GET requests only.
import http from 'k6/http';
import {{ check, sleep }} from 'k6';

export const options = {{
  vus: {vus},
  duration: '{duration}',
  thresholds: {{
{chr(10).join(thresholds)}
  }},
}};

const BASE = __ENV.BASE_URL || {json.dumps(base_url.rstrip("/"))};
const PATHS = [
{targets}
];

export default function () {{
  for (const p of PATHS) {{
    const res = http.get(`${{BASE}}${{p}}`, {{ redirects: 0 }});
    check(res, {{ 'status < 500': (r) => r.status < 500 }});
  }}
  sleep(1);
}}
"""
