# Repository inventory

- Root: `examples/mixed-monorepo`
- Generated: 2026-10-20T21:29:46Z by archonix 0.1.0
- VCS: git; revision: n/a; branch: main; dirty: unknown
- Files scanned: 8

## Languages

- Python: 3 files
- TypeScript: 1 files

## Projects

- `.` (javascript) — example-monorepo: package.json
- `apps/web` (javascript) — web: apps/web/package.json
- `services/api` (python) — example-api: services/api/pyproject.toml

## Detected technology

| Category | Name | Confidence | Basis | Evidence |
|---|---|---|---|---|
| cache | Redis client | medium | declared-dependency | services/api/pyproject.toml: dependency 'redis' |
| container | Docker Compose | high | config-file | docker-compose.yml |
| database | SQLAlchemy ORM | medium | declared-dependency | services/api/pyproject.toml: dependency 'sqlalchemy' |
| framework | FastAPI | high | declared-dependency | services/api/pyproject.toml: dependency 'fastapi' |
| framework | React | high | declared-dependency | apps/web/package.json: dependency 'react' |
| integration | HTTP client (axios) | medium | declared-dependency | apps/web/package.json: dependency 'axios' |
| language | TypeScript | high | file-pattern | 1 .ts/.tsx files |
| monorepo | npm/yarn workspaces | high | manifest-field | package.json: workspaces |
| monorepo | multiple projects | medium | file-pattern | 3 directories contain package manifests |
| test | Vitest | high | declared-dependency | apps/web/package.json: dependency 'vitest' |
| test | pytest | high | manifest-field | services/api/pyproject.toml: [tool.pytest] |

## Limitations

- Static inspection of manifests and configuration files only; repository code was not imported or executed.
- Declared dependencies show intent, not runtime use; services configured outside the repository (environment variables, platform settings) are not visible.
- branch 'main' has no commits yet
- working-tree status unknown: running git requires external tool permission
