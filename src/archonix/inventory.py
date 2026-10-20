"""Static repository inventory and stack detection.

The scanner walks the tree without following directory symlinks, skips configured
exclusions, reads only known manifest/config files (bounded by size), and never
imports or executes repository code. Results describe *declared* and *configured*
technology, which is evidence of intent, not proof of runtime behaviour.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import tomllib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from . import SCHEMA_VERSION, __version__
from .config import Settings
from .gitinfo import repository_info
from .timeutil import utc_now

LANGUAGE_BY_EXT = {
    ".py": "Python",
    ".pyi": "Python",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".swift": "Swift",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".hpp": "C++",
    ".scala": "Scala",
    ".sh": "Shell",
    ".sql": "SQL",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "CSS",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".tf": "HCL",
    ".dart": "Dart",
    ".ex": "Elixir",
    ".exs": "Elixir",
}

MANIFESTS = {
    "pyproject.toml": ("pyproject", "python"),
    "setup.py": ("setup.py", "python"),
    "setup.cfg": ("setup.cfg", "python"),
    "Pipfile": ("pipfile", "python"),
    "package.json": ("package.json", "javascript"),
    "go.mod": ("go.mod", "go"),
    "Cargo.toml": ("cargo", "rust"),
    "pom.xml": ("maven", "java"),
    "build.gradle": ("gradle", "java"),
    "build.gradle.kts": ("gradle", "java"),
    "Gemfile": ("gemfile", "ruby"),
    "composer.json": ("composer", "php"),
}
REQUIREMENTS_FILE = re.compile(r"^requirements([-_.][\w.-]*)?\.(txt|in)$")

LOCKFILES = {
    "poetry.lock": "poetry",
    "uv.lock": "uv",
    "Pipfile.lock": "pipenv",
    "pdm.lock": "pdm",
    "package-lock.json": "npm",
    "npm-shrinkwrap.json": "npm",
    "yarn.lock": "yarn",
    "pnpm-lock.yaml": "pnpm",
    "bun.lockb": "bun",
    "bun.lock": "bun",
    "go.sum": "go modules",
    "Cargo.lock": "cargo",
    "Gemfile.lock": "bundler",
    "composer.lock": "composer",
}

# (category, display name) keyed by normalised dependency name.
PY_DEPENDENCIES: dict[str, tuple[str, str]] = {
    "django": ("framework", "Django"),
    "flask": ("framework", "Flask"),
    "fastapi": ("framework", "FastAPI"),
    "starlette": ("framework", "Starlette"),
    "tornado": ("framework", "Tornado"),
    "aiohttp": ("framework", "aiohttp"),
    "pyramid": ("framework", "Pyramid"),
    "streamlit": ("framework", "Streamlit"),
    "djangorestframework": ("api", "Django REST framework"),
    "graphene": ("api", "GraphQL (graphene)"),
    "strawberry-graphql": ("api", "GraphQL (strawberry)"),
    "grpcio": ("api", "gRPC"),
    "psycopg": ("database", "PostgreSQL client"),
    "psycopg2": ("database", "PostgreSQL client"),
    "psycopg2-binary": ("database", "PostgreSQL client"),
    "asyncpg": ("database", "PostgreSQL client"),
    "pymysql": ("database", "MySQL client"),
    "mysqlclient": ("database", "MySQL client"),
    "pymongo": ("database", "MongoDB client"),
    "motor": ("database", "MongoDB client"),
    "sqlalchemy": ("database", "SQLAlchemy ORM"),
    "alembic": ("database", "Alembic migrations"),
    "redis": ("cache", "Redis client"),
    "pymemcache": ("cache", "Memcached client"),
    "celery": ("queue", "Celery"),
    "rq": ("queue", "RQ"),
    "dramatiq": ("queue", "Dramatiq"),
    "pika": ("queue", "RabbitMQ client"),
    "kafka-python": ("queue", "Kafka client"),
    "confluent-kafka": ("queue", "Kafka client"),
    "pyjwt": ("auth", "JWT (PyJWT)"),
    "python-jose": ("auth", "JWT (python-jose)"),
    "authlib": ("auth", "Authlib"),
    "django-allauth": ("auth", "django-allauth"),
    "passlib": ("auth", "passlib"),
    "flask-login": ("auth", "Flask-Login"),
    "djangorestframework-simplejwt": ("auth", "Simple JWT"),
    "pytest": ("test", "pytest"),
    "hypothesis": ("test", "Hypothesis (property-based)"),
    "playwright": ("test", "Playwright"),
    "pytest-playwright": ("test", "Playwright"),
    "locust": ("performance", "Locust"),
    "coverage": ("test", "coverage.py"),
    "pytest-cov": ("test", "coverage.py"),
    "mutmut": ("test", "mutmut (mutation)"),
    "ruff": ("lint", "Ruff"),
    "flake8": ("lint", "flake8"),
    "pylint": ("lint", "Pylint"),
    "black": ("format", "Black"),
    "mypy": ("typecheck", "mypy"),
    "pyright": ("typecheck", "Pyright"),
    "bandit": ("security", "Bandit"),
    "vulture": ("dead-code", "Vulture"),
    "deptry": ("dead-code", "deptry"),
    "boto3": ("integration", "AWS SDK"),
    "stripe": ("integration", "Stripe SDK"),
    "requests": ("integration", "HTTP client (requests)"),
    "httpx": ("integration", "HTTP client (httpx)"),
}
JS_DEPENDENCIES: dict[str, tuple[str, str]] = {
    "react": ("framework", "React"),
    "next": ("framework", "Next.js"),
    "vue": ("framework", "Vue"),
    "nuxt": ("framework", "Nuxt"),
    "svelte": ("framework", "Svelte"),
    "@sveltejs/kit": ("framework", "SvelteKit"),
    "@angular/core": ("framework", "Angular"),
    "express": ("framework", "Express"),
    "fastify": ("framework", "Fastify"),
    "koa": ("framework", "Koa"),
    "@nestjs/core": ("framework", "NestJS"),
    "hono": ("framework", "Hono"),
    "@remix-run/react": ("framework", "Remix"),
    "astro": ("framework", "Astro"),
    "solid-js": ("framework", "Solid"),
    "graphql": ("api", "GraphQL"),
    "@apollo/server": ("api", "Apollo Server"),
    "@trpc/server": ("api", "tRPC"),
    "pg": ("database", "PostgreSQL client"),
    "mysql2": ("database", "MySQL client"),
    "mongodb": ("database", "MongoDB client"),
    "mongoose": ("database", "MongoDB (Mongoose)"),
    "@prisma/client": ("database", "Prisma ORM"),
    "prisma": ("database", "Prisma ORM"),
    "typeorm": ("database", "TypeORM"),
    "sequelize": ("database", "Sequelize"),
    "drizzle-orm": ("database", "Drizzle ORM"),
    "knex": ("database", "Knex"),
    "better-sqlite3": ("database", "SQLite client"),
    "redis": ("cache", "Redis client"),
    "ioredis": ("cache", "Redis client"),
    "bullmq": ("queue", "BullMQ"),
    "bull": ("queue", "Bull"),
    "amqplib": ("queue", "RabbitMQ client"),
    "kafkajs": ("queue", "Kafka client"),
    "next-auth": ("auth", "NextAuth.js"),
    "@auth/core": ("auth", "Auth.js"),
    "passport": ("auth", "Passport"),
    "jsonwebtoken": ("auth", "JWT (jsonwebtoken)"),
    "jose": ("auth", "JOSE"),
    "bcrypt": ("auth", "bcrypt"),
    "argon2": ("auth", "argon2"),
    "jest": ("test", "Jest"),
    "vitest": ("test", "Vitest"),
    "mocha": ("test", "Mocha"),
    "@playwright/test": ("test", "Playwright"),
    "cypress": ("test", "Cypress"),
    "@testing-library/react": ("test", "Testing Library"),
    "fast-check": ("test", "fast-check (property-based)"),
    "@axe-core/playwright": ("test", "axe accessibility"),
    "supertest": ("test", "supertest"),
    "eslint": ("lint", "ESLint"),
    "@biomejs/biome": ("lint", "Biome"),
    "prettier": ("format", "Prettier"),
    "typescript": ("typecheck", "TypeScript compiler"),
    "knip": ("dead-code", "Knip"),
    "stripe": ("integration", "Stripe SDK"),
    "@aws-sdk/client-s3": ("integration", "AWS SDK"),
    "axios": ("integration", "HTTP client (axios)"),
}

# (glob on file name, category, name) — basis: config-file.
CONFIG_FILES: list[tuple[str, str, str]] = [
    ("pytest.ini", "test", "pytest"),
    ("conftest.py", "test", "pytest"),
    ("tox.ini", "test", "tox"),
    ("noxfile.py", "test", "nox"),
    ("ruff.toml", "lint", "Ruff"),
    (".ruff.toml", "lint", "Ruff"),
    (".flake8", "lint", "flake8"),
    (".pylintrc", "lint", "Pylint"),
    ("mypy.ini", "typecheck", "mypy"),
    (".mypy.ini", "typecheck", "mypy"),
    ("pyrightconfig.json", "typecheck", "Pyright"),
    (".eslintrc", "lint", "ESLint"),
    (".eslintrc.*", "lint", "ESLint"),
    ("eslint.config.*", "lint", "ESLint"),
    (".prettierrc", "format", "Prettier"),
    (".prettierrc.*", "format", "Prettier"),
    ("prettier.config.*", "format", "Prettier"),
    ("biome.json", "lint", "Biome"),
    ("biome.jsonc", "lint", "Biome"),
    ("tsconfig.json", "typecheck", "TypeScript compiler"),
    ("jest.config.*", "test", "Jest"),
    ("vitest.config.*", "test", "Vitest"),
    ("playwright.config.*", "test", "Playwright"),
    ("cypress.config.*", "test", "Cypress"),
    (".mocharc*", "test", "Mocha"),
    ("stryker.conf.*", "test", "Stryker (mutation)"),
    ("Dockerfile", "container", "Docker"),
    ("Dockerfile.*", "container", "Docker"),
    ("*.Dockerfile", "container", "Docker"),
    ("docker-compose*.yml", "container", "Docker Compose"),
    ("docker-compose*.yaml", "container", "Docker Compose"),
    ("compose.yml", "container", "Docker Compose"),
    ("compose.yaml", "container", "Docker Compose"),
    ("*.tf", "infrastructure", "Terraform"),
    ("Chart.yaml", "infrastructure", "Helm"),
    ("kustomization.yaml", "infrastructure", "Kustomize"),
    ("serverless.yml", "infrastructure", "Serverless Framework"),
    ("Pulumi.yaml", "infrastructure", "Pulumi"),
    ("cdk.json", "infrastructure", "AWS CDK"),
    ("fly.toml", "deployment", "Fly.io"),
    ("vercel.json", "deployment", "Vercel"),
    ("netlify.toml", "deployment", "Netlify"),
    ("Procfile", "deployment", "Procfile (Heroku-style)"),
    ("render.yaml", "deployment", "Render"),
    (".gitlab-ci.yml", "ci", "GitLab CI"),
    ("Jenkinsfile", "ci", "Jenkins"),
    ("azure-pipelines.yml", "ci", "Azure Pipelines"),
    ("bitbucket-pipelines.yml", "ci", "Bitbucket Pipelines"),
    (".releaserc", "release", "semantic-release"),
    (".releaserc.*", "release", "semantic-release"),
    ("release-please-config.json", "release", "release-please"),
    (".goreleaser.y*ml", "release", "GoReleaser"),
    ("CHANGELOG.md", "release", "Changelog"),
    ("openapi.json", "api-spec", "OpenAPI"),
    ("openapi.y*ml", "api-spec", "OpenAPI"),
    ("swagger.json", "api-spec", "OpenAPI (Swagger)"),
    ("swagger.y*ml", "api-spec", "OpenAPI (Swagger)"),
    ("*.graphql", "api-spec", "GraphQL schema"),
    ("*.proto", "api-spec", "Protocol Buffers"),
    ("alembic.ini", "database", "Alembic migrations"),
    ("schema.prisma", "database", "Prisma schema"),
    ("pnpm-workspace.yaml", "monorepo", "pnpm workspaces"),
    ("lerna.json", "monorepo", "Lerna"),
    ("nx.json", "monorepo", "Nx"),
    ("turbo.json", "monorepo", "Turborepo"),
    ("k6*.js", "performance", "k6"),
    ("locustfile.py", "performance", "Locust"),
]
# (posix path glob relative to root, category, name)
PATH_PATTERNS: list[tuple[str, str, str]] = [
    (".github/workflows/*.yml", "ci", "GitHub Actions"),
    (".github/workflows/*.yaml", "ci", "GitHub Actions"),
    (".circleci/config.yml", "ci", "CircleCI"),
    (".changeset/*.md", "release", "Changesets"),
    ("*/migrations/*.py", "database", "Django/Alembic migrations"),
]
PYPROJECT_TOOLS = {
    "pytest": ("test", "pytest"),
    "ruff": ("lint", "Ruff"),
    "mypy": ("typecheck", "mypy"),
    "black": ("format", "Black"),
    "coverage": ("test", "coverage.py"),
    "pyright": ("typecheck", "Pyright"),
    "bandit": ("security", "Bandit"),
    "vulture": ("dead-code", "Vulture"),
    "poetry": ("package-manager", "poetry"),
    "hatch": ("package-manager", "hatch"),
    "pdm": ("package-manager", "pdm"),
    "uv": ("package-manager", "uv"),
}
HIGH_CONFIDENCE_DEP_CATEGORIES = {
    "framework",
    "test",
    "lint",
    "format",
    "typecheck",
    "security",
    "dead-code",
    "api",
    "performance",
}

_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def normalise_py(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _py_dep_names(specs: list[Any]) -> list[str]:
    out = []
    for spec in specs:
        if isinstance(spec, str):
            m = _REQ_NAME.match(spec)
            if m:
                out.append(normalise_py(m.group(1)))
    return out


def parse_requirements_txt(text: str) -> list[str]:
    names = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith(("-", "git+", "http:", "https:")):
            continue
        m = _REQ_NAME.match(line)
        if m:
            names.append(normalise_py(m.group(1)))
    return names


@dataclass
class _State:
    root: Path
    settings: Settings
    files: list[str] = field(default_factory=list)
    lang_files: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    lang_bytes: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    excluded: list[str] = field(default_factory=list)
    symlinks: list[str] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)
    large: list[str] = field(default_factory=list)
    truncated: bool = False
    detections: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)

    def detect(self, category: str, name: str, basis: str, evidence: str, confidence: str) -> None:
        key = (category, name)
        entry = self.detections.get(key)
        if entry is None:
            self.detections[key] = {
                "category": category,
                "name": name,
                "confidence": confidence,
                "basis": basis,
                "evidence": [evidence],
            }
            return
        if evidence not in entry["evidence"] and len(entry["evidence"]) < 20:
            entry["evidence"].append(evidence)
        rank = {"low": 0, "medium": 1, "high": 2}
        if rank[confidence] > rank[entry["confidence"]]:
            entry["confidence"], entry["basis"] = confidence, basis


def _excluded(rel: str, name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(rel, p) for p in patterns)


def _walk(state: _State) -> None:
    patterns = state.settings.exclude
    stack = [state.root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError:
            state.unreadable.append(_rel(state.root, Path(current)) or ".")
            continue
        for entry in entries:
            path = Path(entry.path)
            rel = _rel(state.root, path)
            try:
                if entry.is_symlink():
                    state.symlinks.append(rel)
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if _excluded(rel, entry.name, patterns):
                        state.excluded.append(rel + "/")
                    else:
                        stack.append(path)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                if _excluded(rel, entry.name, patterns):
                    continue
                if len(state.files) >= state.settings.max_files:
                    state.truncated = True
                    return
                size = entry.stat(follow_symlinks=False).st_size
            except OSError:
                state.unreadable.append(rel)
                continue
            state.files.append(rel)
            lang = LANGUAGE_BY_EXT.get(path.suffix.lower())
            if lang:
                state.lang_files[lang] += 1
                state.lang_bytes[lang] += size


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix() if path != root else ""


def _read(state: _State, rel: str) -> str | None:
    path = state.root / rel
    try:
        if path.stat().st_size > state.settings.max_file_bytes:
            state.large.append(rel)
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        state.unreadable.append(rel)
        return None


def _record_deps(
    state: _State, rel: str, names: list[str], table: dict[str, tuple[str, str]]
) -> None:
    for dep in names:
        hit = table.get(dep)
        if hit:
            category, display = hit
            conf = "high" if category in HIGH_CONFIDENCE_DEP_CATEGORIES else "medium"
            state.detect(
                category, display, "declared-dependency", f"{rel}: dependency {dep!r}", conf
            )


def _parse_pyproject(
    state: _State, rel: str, text: str
) -> tuple[list[str], str | None, str | None]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return [], None, f"invalid TOML: {exc}"
    project = data.get("project", {})
    deps = _py_dep_names(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        deps += _py_dep_names(group)
    for group in data.get("dependency-groups", {}).values():
        deps += _py_dep_names(group)
    poetry = data.get("tool", {}).get("poetry", {})
    deps += [normalise_py(k) for k in poetry.get("dependencies", {}) if k != "python"]
    for group in poetry.get("group", {}).values():
        deps += [normalise_py(k) for k in group.get("dependencies", {})]
    for tool, (category, display) in PYPROJECT_TOOLS.items():
        if tool in data.get("tool", {}):
            state.detect(category, display, "manifest-field", f"{rel}: [tool.{tool}]", "high")
    name = project.get("name") or poetry.get("name")
    return sorted(set(deps)), name if isinstance(name, str) else None, None


def _parse_package_json(
    state: _State, rel: str, text: str
) -> tuple[list[str], str | None, str | None]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [], None, f"invalid JSON: {exc}"
    if not isinstance(data, dict):
        return [], None, "package.json is not an object"
    deps: list[str] = []
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        value = data.get(section)
        if isinstance(value, dict):
            deps += list(value)
    if data.get("workspaces"):
        state.detect(
            "monorepo", "npm/yarn workspaces", "manifest-field", f"{rel}: workspaces", "high"
        )
    pm = data.get("packageManager")
    if isinstance(pm, str) and pm:
        state.detect(
            "package-manager", pm.split("@")[0], "manifest-field", f"{rel}: packageManager", "high"
        )
    name = data.get("name")
    return sorted(set(deps)), name if isinstance(name, str) else None, None


def build_inventory(root: Path, settings: Settings) -> dict[str, Any]:
    root = root.resolve()
    state = _State(root=root, settings=settings)
    _walk(state)

    manifests: list[dict[str, Any]] = []
    projects: dict[str, dict[str, Any]] = {}
    for rel in state.files:
        name = PurePosixPath(rel).name
        parent = str(PurePosixPath(rel).parent)
        project_dir = "." if parent == "." else parent
        manifest = MANIFESTS.get(name)
        if manifest is None and REQUIREMENTS_FILE.match(name):
            manifest = ("requirements.txt", "python")
        if manifest is not None:
            mtype, ecosystem = manifest
            deps: list[str] = []
            pname: str | None = None
            error: str | None = None
            if mtype in {"pyproject", "package.json", "requirements.txt", "pipfile"}:
                text = _read(state, rel)
                if text is None:
                    error = "not parsed (unreadable or larger than max_file_bytes)"
                elif mtype == "pyproject":
                    deps, pname, error = _parse_pyproject(state, rel, text)
                elif mtype == "package.json":
                    deps, pname, error = _parse_package_json(state, rel, text)
                elif mtype == "pipfile":
                    try:
                        pip = tomllib.loads(text)
                        deps = sorted(
                            {
                                normalise_py(k)
                                for sec in ("packages", "dev-packages")
                                for k in pip.get(sec, {})
                            }
                        )
                    except tomllib.TOMLDecodeError as exc:
                        error = f"invalid TOML: {exc}"
                else:
                    deps = parse_requirements_txt(text)
            table = JS_DEPENDENCIES if ecosystem == "javascript" else PY_DEPENDENCIES
            _record_deps(state, rel, deps, table)
            manifests.append(
                {"path": rel, "type": mtype, "ecosystem": ecosystem, "parse_error": error}
            )
            proj = projects.setdefault(
                project_dir,
                {
                    "path": project_dir,
                    "name": None,
                    "ecosystems": [],
                    "manifests": [],
                    "dependencies": [],
                },
            )
            if ecosystem not in proj["ecosystems"]:
                proj["ecosystems"].append(ecosystem)
            proj["manifests"].append(rel)
            proj["name"] = proj["name"] or pname
            proj["dependencies"] = sorted(set(proj["dependencies"]) | set(deps))
        if name in LOCKFILES:
            state.detect(
                "package-manager", LOCKFILES[name], "config-file", f"{rel}: lockfile", "high"
            )
        if REQUIREMENTS_FILE.match(name):
            state.detect(
                "package-manager", "pip", "config-file", f"{rel}: requirements file", "medium"
            )
        for pattern, category, display in CONFIG_FILES:
            if fnmatch.fnmatch(name, pattern):
                state.detect(category, display, "config-file", rel, "high")
        for pattern, category, display in PATH_PATTERNS:
            if fnmatch.fnmatch(rel, pattern):
                state.detect(category, display, "file-pattern", rel, "medium")

    for proj in projects.values():
        proj["ecosystems"].sort()
    if len(projects) > 1:
        state.detect(
            "monorepo",
            "multiple projects",
            "file-pattern",
            f"{len(projects)} directories contain package manifests",
            "medium",
        )
    if "TypeScript" in state.lang_files:
        state.detect(
            "language",
            "TypeScript",
            "file-pattern",
            f"{state.lang_files['TypeScript']} .ts/.tsx files",
            "high",
        )

    repo = repository_info(
        root,
        allow_git_process=settings.permissions.external_tools,
        timeout=min(settings.timeout_seconds, 30),
    )
    limitations = [
        "Static inspection of manifests and configuration files only; repository code was "
        "not imported or executed.",
        "Declared dependencies show intent, not runtime use; services configured outside "
        "the repository (environment variables, platform settings) are not visible.",
    ]
    if state.truncated:
        limitations.append(f"Scan stopped at max_files={settings.max_files}; results are partial.")
    if state.symlinks:
        limitations.append(f"{len(state.symlinks)} symlink(s) were not followed.")
    if state.large:
        limitations.append(
            f"{len(state.large)} manifest(s) exceeded max_file_bytes and were not parsed."
        )
    if state.unreadable:
        limitations.append(f"{len(state.unreadable)} path(s) could not be read.")

    order = {"high": 0, "medium": 1, "low": 2}
    return {
        "kind": "inventory",
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "generator": {"name": "archonix", "version": __version__},
        "root": str(root),
        "repository": repo,
        "scan": {
            "files_scanned": len(state.files),
            "truncated": state.truncated,
            "max_files": settings.max_files,
            "excluded_dirs": sorted(state.excluded),
            "symlinks_skipped": sorted(state.symlinks),
            "unreadable": sorted(set(state.unreadable)),
            "large_files": sorted(state.large),
        },
        "languages": sorted(
            (
                {"name": k, "files": v, "bytes": state.lang_bytes[k]}
                for k, v in state.lang_files.items()
            ),
            key=lambda x: (-x["files"], x["name"]),
        ),
        "manifests": manifests,
        "projects": sorted(projects.values(), key=lambda p: p["path"]),
        "detections": sorted(
            state.detections.values(),
            key=lambda d: (d["category"], order[d["confidence"]], d["name"]),
        ),
        "limitations": limitations,
    }


def ecosystems(inventory: dict[str, Any]) -> set[str]:
    return {e for p in inventory["projects"] for e in p["ecosystems"]}


def summary(inventory: dict[str, Any]) -> dict[str, Any]:
    return {
        "languages": [lang["name"] for lang in inventory["languages"]],
        "ecosystems": sorted(ecosystems(inventory)),
        "detections": [f"{d['category']}: {d['name']}" for d in inventory["detections"]],
    }


def render_markdown(inv: dict[str, Any]) -> str:
    repo = inv["repository"]
    lines = [
        "# Repository inventory",
        "",
        f"- Root: `{inv['root']}`",
        f"- Generated: {inv['generated_at']} by archonix {inv['generator']['version']}",
        f"- VCS: {repo['vcs']}; revision: {repo['revision'] or 'n/a'}; branch: "
        f"{repo['branch'] or 'n/a'}; dirty: {_tri(repo['dirty'])}",
        f"- Files scanned: {inv['scan']['files_scanned']}"
        + (" (truncated)" if inv["scan"]["truncated"] else ""),
        "",
        "## Languages",
        "",
    ]
    lines += [f"- {lang['name']}: {lang['files']} files" for lang in inv["languages"]] or [
        "- none detected"
    ]
    lines += ["", "## Projects", ""]
    for p in inv["projects"]:
        lines.append(
            f"- `{p['path']}` ({', '.join(p['ecosystems'])})"
            + (f" — {p['name']}" if p.get("name") else "")
            + f": {', '.join(p['manifests'])}"
        )
    if not inv["projects"]:
        lines.append("- no package manifests found")
    lines += [
        "",
        "## Detected technology",
        "",
        "| Category | Name | Confidence | Basis | Evidence |",
        "|---|---|---|---|---|",
    ]
    for d in inv["detections"]:
        ev = "; ".join(d["evidence"][:3]) + (" …" if len(d["evidence"]) > 3 else "")
        lines.append(f"| {d['category']} | {d['name']} | {d['confidence']} | {d['basis']} | {ev} |")
    errors = [m for m in inv["manifests"] if m.get("parse_error")]
    if errors:
        lines += ["", "## Manifest problems", ""]
        lines += [f"- `{m['path']}`: {m['parse_error']}" for m in errors]
    lines += ["", "## Limitations", ""] + [
        f"- {x}" for x in inv["limitations"] + repo.get("notes", [])
    ]
    return "\n".join(lines) + "\n"


def _tri(value: bool | None) -> str:
    return "unknown" if value is None else ("yes" if value else "no")
