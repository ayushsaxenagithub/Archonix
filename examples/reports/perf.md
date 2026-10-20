> **EXAMPLE REPORT** — synthetic target, for documentation.

# API smoke measurement

- Target: http://127.0.0.1:53059 (loopback: True)
- Revision: not recorded; environment: local example server
- Method: smoke; 120 requests/endpoint, concurrency 2, warm-up 2, timeout 5.0s
- Percentiles: nearest-rank over successful responses; a percentile p is reliable only when samples x (1 - p) >= 5 (p95 needs >= 100, p99 >= 500)

| Endpoint | Samples | Errors | Timeouts | Status codes | p50 ms | p95 ms | p99 ms | RPS | Threshold |
|---|---|---|---|---|---|---|---|---|---|
| GET /health | 120 | 0 | 0 | 200x120 | 0.6 | 0.7 | 1.2 (insufficient samples) | 3480.1 | pass |

## Limitations

- Smoke measurement only: small sample, single client host, no capacity or reliability claim. Use a load-testing tool for load evidence.
- Errors count transport failures, timeouts and 5xx responses; 4xx responses are listed under status codes.
- Throughput is bounded by the configured client concurrency, not server capacity.
- Redirects are recorded and not followed; proxies from the environment are ignored.
