"""Load and validate documents against the versioned Archonix schemas."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from .errors import ValidationFailed
from .resources import schemas_dir

# Document ``kind`` -> schema name. Findings and execution records have no
# ``kind`` field and are validated by explicit schema name.
KIND_TO_SCHEMA = {
    "inventory": "inventory",
    "requirements-ledger": "requirements",
    "workflow-report": "workflow-report",
    "release-readiness": "release-readiness",
    "performance-report": "performance-report",
}


def schema_names() -> list[str]:
    return sorted(p.name.removesuffix(".schema.json") for p in schemas_dir().glob("*.schema.json"))


@cache
def _load(name: str) -> dict[str, Any]:
    path = schemas_dir() / f"{name}.schema.json"
    if not path.is_file():
        raise ValidationFailed(f"unknown schema {name!r}; known: {', '.join(schema_names())}")
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


@cache
def _registry() -> Registry:
    resources = [(_load(n)["$id"], Resource.from_contents(_load(n))) for n in schema_names()]
    return Registry().with_resources(resources)


def validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(_load(name), registry=_registry(), format_checker=FormatChecker())


def errors_for(document: Any, name: str) -> list[str]:
    """Return human-readable schema errors (empty when valid)."""
    out = []
    for err in sorted(validator(name).iter_errors(document), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "<root>"
        out.append(f"{where}: {err.message}")
    return out


def schema_for_document(document: Any) -> str:
    if isinstance(document, dict):
        kind = document.get("kind")
        if isinstance(kind, str) and kind in KIND_TO_SCHEMA:
            return KIND_TO_SCHEMA[kind]
    raise ValidationFailed(
        "cannot infer schema: document has no recognised 'kind'; pass --schema explicitly"
    )


def validate(document: Any, name: str | None = None) -> str:
    """Validate ``document``; return the schema name used or raise ValidationFailed."""
    name = name or schema_for_document(document)
    errs = errors_for(document, name)
    if errs:
        raise ValidationFailed(f"{name} schema validation failed:\n  " + "\n  ".join(errs))
    return name


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationFailed(f"{path}: file not found") from exc
    except json.JSONDecodeError as exc:
        raise ValidationFailed(f"{path}: invalid JSON: {exc}") from exc
