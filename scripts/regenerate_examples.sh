#!/usr/bin/env bash
# Regenerate examples/reports/ by running Archonix on a temporary copy of
# examples/python-service with real tools (ruff, bandit, vulture, pytest must be on PATH).
#
# The copy is not a Git repository, so reports honestly record no revision. Absolute
# temporary paths are replaced with "examples/python-service" so the committed examples
# do not contain machine-specific paths; nothing else is edited.
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
out="$repo/examples/reports"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "$work"; [[ -n "${server_pid:-}" ]] && kill "$server_pid" 2>/dev/null || true' EXIT

cp -R "$repo/examples/python-service" "$work/python-service"
rm -rf "$out" && mkdir -p "$out"

archonix check run "$work/python-service" --mode audit --allow-repo-code \
  --checks ruff,bandit,vulture,pytest --workflow audit --label-example \
  --format json > "$work/report.json"

archonix readiness assess --policy "$repo/examples/readiness-policy.toml" \
  --report "$work/report.json" --ledger "$repo/examples/requirements/ledger.json" \
  --label-example --format json > "$work/readiness.json" || true

# Local loopback target for the smoke example.
mkdir -p "$work/site" && echo ok > "$work/site/health"
port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
python3 -m http.server "$port" --bind 127.0.0.1 --directory "$work/site" >/dev/null 2>&1 &
server_pid=$!
sleep 1
archonix perf smoke --base-url "http://127.0.0.1:$port" --path /health --requests 120 \
  --concurrency 2 --p95-ms 250 --allow-network --environment "local example server" \
  --label-example --format json > "$work/perf.json"

python3 - "$work" "$out" "$repo" <<'PY'
import json, sys
from pathlib import Path
work, out, repo = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
for name in ("report.json", "readiness.json", "perf.json"):
    text = (work / name).read_text()
    text = text.replace(str(work / "report.json"), "examples/reports/report.json")
    text = text.replace(str(work / "python-service"), "examples/python-service")
    text = text.replace(str(work), "<tmp>").replace(str(repo) + "/", "")
    (out / name).write_text(text)
    json.loads(text)
PY

for name in report readiness perf; do
  archonix validate "$out/$name.json"
  archonix render "$out/$name.json" --out "$out/$name.md"
done
archonix inventory "$repo/examples/mixed-monorepo" --format md \
  | sed "s#$repo/##" > "$out/inventory-mixed-monorepo.md"
archonix architecture diagram "$repo/examples/mixed-monorepo" > "$out/architecture-mixed-monorepo.md"
archonix requirements matrix "$repo/examples/requirements/ledger.json" --report "$out/report.json" \
  > "$out/traceability.md"
echo "regenerated $out"
