# System context (inventory-derived)

```mermaid
flowchart LR
  subgraph repo["Repository"]
    proj_["example-monorepo<br/><small>javascript</small>"]
    proj_apps_web["web<br/><small>javascript · React</small>"]
    proj_services_api["example-api<br/><small>python · FastAPI</small>"]
  end
  svc_HTTP_client__axios{{"HTTP client (axios)"}}
  svc_Redis_client[("Redis client")]
  svc_SQLAlchemy_ORM[("SQLAlchemy ORM")]
  proj_apps_web -. "axios (inferred)" .-> svc_HTTP_client__axios
  proj_services_api -. "redis (inferred)" .-> svc_Redis_client
  proj_services_api -. "sqlalchemy (inferred)" .-> svc_SQLAlchemy_ORM
  ctx_containerDocker_Compose["Docker Compose<br/><small>container</small>"]
  ctx_containerDocker_Compose --- repo
  classDef inferred stroke-dasharray: 4 3;
  class svc_HTTP_client__axios inferred;
  class svc_Redis_client inferred;
  class svc_SQLAlchemy_ORM inferred;
```

Legend: solid edges are verified from files; dashed edges are inferred from declared dependencies; items marked unknown could not be resolved statically.

## Evidence

| Element | Relationship | Status | Evidence |
|---|---|---|---|
| example-monorepo | project | verified | package.json |
| web | project | verified | apps/web/package.json |
| example-api | project | verified | services/api/pyproject.toml |
| apps/web -> HTTP client (axios) | uses | inferred | declared dependency 'axios' in apps/web/package.json |
| services/api -> Redis client | uses | inferred | declared dependency 'redis' in services/api/pyproject.toml |
| services/api -> SQLAlchemy ORM | uses | inferred | declared dependency 'sqlalchemy' in services/api/pyproject.toml |
| Docker Compose | container configuration | verified (file present) | docker-compose.yml |

## Limitations

- Static inspection of manifests and configuration files only; repository code was not imported or executed.
- Declared dependencies show intent, not runtime use; services configured outside the repository (environment variables, platform settings) are not visible.
