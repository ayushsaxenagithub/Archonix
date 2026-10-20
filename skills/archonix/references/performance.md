# API reliability and performance

Distinguish **smoke checks** (a few requests: is it up, roughly how fast), **load tests**
(sustained concurrency with a tool such as k6 or Locust) and **reliability evidence**
(error budgets over time from production monitoring). Do not present one as another.

## Scope and authorization

- Endpoints come from an OpenAPI document (`archonix perf endpoints openapi.json`) or an
  explicit route list. Choose targets explicitly.
- Only GET/HEAD are exercised automatically, and even those can have side effects.
  Never infer authorization from the HTTP method. Write endpoints are never exercised
  automatically.
- Load tests require explicit target scope, authentication handling, request and duration
  limits, and authorization. Production requires specific authorization.

## Smoke measurement (CLI)

```bash
archonix perf smoke --base-url http://127.0.0.1:8000 --path /health --requests 100 \
  --concurrency 2 --p95-ms 200 --allow-network --revision "$(git rev-parse HEAD)"
```

Caps: ≤500 requests per endpoint, ≤10 concurrency, ≤20 warm-up. Non-loopback hosts need
`--authorized-host HOST`. Redirects are not followed; environment proxies are ignored;
credentials come from `--auth-header-env VAR` and are never written to reports.

Percentiles use nearest rank over successful responses and are flagged unreliable unless
at least 5 samples lie above them (p95 needs ≥100 samples, p99 ≥500). A threshold that
depends on an unreliable percentile evaluates to `unknown`, not pass.

## Load tests

`archonix perf k6-script --base-url … --path … --vus 10 --duration 1m --p95-ms 300`
generates a reviewable k6 script; run it yourself only when authorized. Record
environment, revision, concurrency, duration, warm-up, sample count and configuration.

## Comparing revisions

Compare only under comparable conditions (same environment, data volume, concurrency,
warm-up and client location); report both sample sizes and treat small differences as
noise unless repeated runs agree.
