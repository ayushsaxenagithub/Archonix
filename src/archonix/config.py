"""Layered configuration with recorded provenance.

Precedence (lowest to highest):

1. built-in defaults (and the selected mode's permission defaults)
2. user config: ``$ARCHONIX_USER_CONFIG`` or ``$XDG_CONFIG_HOME/archonix/config.toml``
   (falls back to ``~/.config/archonix/config.toml``)
3. repository config: ``<root>/archonix.toml`` or ``<root>/.archonix.toml``
4. explicit ``--config FILE`` given on the command line
5. environment: ``ARCHONIX_TIMEOUT_SECONDS``, ``ARCHONIX_MAX_OUTPUT_BYTES``
6. command-line flags

Repository config is controlled by whoever controls the repository, so it is
*restrict-only* for trust-sensitive settings: it may turn permissions off but never
on, and it may not set ``execution.env_passthrough`` or ``checks.*.extra_args``.
Ignored settings are recorded and surfaced in reports.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import ArchonixError
from .policy import MODES, PERMISSION_NAMES, Permissions
from .schemas import errors_for

DEFAULT_EXCLUDES = (
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".cache",
    "dist",
    "build",
    ".next",
    ".nuxt",
    ".turbo",
    "coverage",
    "htmlcov",
    ".idea",
    ".vscode",
    "target",
    "vendor",
    ".gradle",
    ".terraform",
    ".archonix",
    "*.egg-info",
)
REPO_CONFIG_NAMES = ("archonix.toml", ".archonix.toml")


@dataclass
class CheckSettings:
    enabled: bool = True
    timeout_seconds: float | None = None
    extra_args: list[str] = field(default_factory=list)


@dataclass
class Settings:
    mode: str = "discovery"
    permissions: Permissions = field(default_factory=Permissions)
    exclude: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDES))
    max_files: int = 20000
    max_file_bytes: int = 1_000_000
    timeout_seconds: float = 300.0
    max_output_bytes: int = 2_000_000
    env_passthrough: list[str] = field(default_factory=list)
    sensitive_env_names: list[str] = field(default_factory=list)
    extra_redaction_patterns: list[str] = field(default_factory=list)
    checks: dict[str, CheckSettings] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    ignored: list[str] = field(default_factory=list)
    # Exclusions contributed by repository config; they also hide files from scanners,
    # so reports list them.
    repo_excludes: list[str] = field(default_factory=list)
    files_loaded: list[str] = field(default_factory=list)

    def check(self, check_id: str) -> CheckSettings:
        return self.checks.get(check_id, CheckSettings())


def user_config_path(env: Mapping[str, str]) -> Path | None:
    explicit = env.get("ARCHONIX_USER_CONFIG")
    if explicit is not None:
        return None if explicit in {"", "none"} else Path(explicit)
    base = env.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "archonix" / "config.toml"


def find_repo_config(root: Path) -> Path | None:
    for name in REPO_CONFIG_NAMES:
        candidate = root / name
        if candidate.is_file() and not candidate.is_symlink():
            return candidate
    return None


def read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except OSError as exc:
        raise ArchonixError(f"cannot read config {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ArchonixError(f"invalid TOML in {path}: {exc}") from exc
    errs = errors_for(data, "config")
    if errs:
        raise ArchonixError(f"invalid config {path}:\n  " + "\n  ".join(errs))
    return data


def _apply_layer(s: Settings, data: Mapping[str, Any], label: str, trusted: bool) -> None:
    inv = data.get("inventory", {})
    if "exclude" in inv:
        added = [x for x in inv["exclude"] if x not in s.exclude]
        s.exclude.extend(added)
        s.sources["inventory.exclude"] = f"defaults + {label}"
        if not trusted:
            s.repo_excludes.extend(added)
    for key, attr in (("max_files", "max_files"), ("max_file_bytes", "max_file_bytes")):
        if key in inv:
            setattr(s, attr, inv[key])
            s.sources[f"inventory.{key}"] = label

    ex = data.get("execution", {})
    for key in ("timeout_seconds", "max_output_bytes"):
        if key in ex:
            setattr(s, key, ex[key])
            s.sources[f"execution.{key}"] = label
    if "env_passthrough" in ex:
        if trusted:
            s.env_passthrough = list(ex["env_passthrough"])
            s.sources["execution.env_passthrough"] = label
        else:
            s.ignored.append(
                f"{label}: execution.env_passthrough (repository config may not "
                "pass environment variables to tools)"
            )

    for name, value in data.get("permissions", {}).items():
        if not trusted and value:
            s.ignored.append(
                f"{label}: permissions.{name}=true (repository config may only "
                "restrict permissions)"
            )
            continue
        setattr(s.permissions, name, bool(value))
        s.sources[f"permissions.{name}"] = label

    red = data.get("redaction", {})
    s.sensitive_env_names.extend(red.get("sensitive_env_names", []))
    if trusted:
        s.extra_redaction_patterns.extend(red.get("extra_patterns", []))
    elif red.get("extra_patterns"):
        s.ignored.append(
            f"{label}: redaction.extra_patterns (repository config may not supply regular "
            "expressions; a crafted pattern could stall redaction)"
        )

    for check_id, cfg in data.get("checks", {}).items():
        cs = s.checks.setdefault(check_id, CheckSettings())
        if "enabled" in cfg:
            cs.enabled = bool(cfg["enabled"])
            s.sources[f"checks.{check_id}.enabled"] = label
        if "timeout_seconds" in cfg:
            cs.timeout_seconds = float(cfg["timeout_seconds"])
            s.sources[f"checks.{check_id}.timeout_seconds"] = label
        if "extra_args" in cfg:
            if trusted:
                cs.extra_args = list(cfg["extra_args"])
                s.sources[f"checks.{check_id}.extra_args"] = label
            else:
                s.ignored.append(
                    f"{label}: checks.{check_id}.extra_args (repository config may "
                    "not add tool arguments)"
                )


def load_settings(
    root: Path | None,
    *,
    mode: str = "discovery",
    explicit_config: Path | None = None,
    cli_permissions: Mapping[str, bool] | None = None,
    cli_overrides: Mapping[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
    use_repo_config: bool = True,
) -> Settings:
    if mode not in MODES:
        raise ArchonixError(f"unknown mode {mode!r}; expected one of {', '.join(MODES)}")
    env = os.environ if env is None else env
    s = Settings(mode=mode, permissions=Permissions.for_mode(mode))
    for name in PERMISSION_NAMES:
        s.sources[f"permissions.{name}"] = f"mode:{mode}"

    user_path = user_config_path(env)
    if user_path is not None and user_path.is_file():
        _apply_layer(s, read_toml(user_path), f"user config ({user_path})", trusted=True)
        s.files_loaded.append(str(user_path))

    if root is not None and use_repo_config:
        repo_path = find_repo_config(root)
        if repo_path is not None:
            _apply_layer(
                s, read_toml(repo_path), f"repository config ({repo_path.name})", trusted=False
            )
            s.files_loaded.append(str(repo_path))

    if explicit_config is not None:
        _apply_layer(s, read_toml(explicit_config), f"--config ({explicit_config})", trusted=True)
        s.files_loaded.append(str(explicit_config))

    for var, attr, cast in (
        ("ARCHONIX_TIMEOUT_SECONDS", "timeout_seconds", float),
        ("ARCHONIX_MAX_OUTPUT_BYTES", "max_output_bytes", int),
    ):
        if var in env:
            try:
                setattr(s, attr, cast(env[var]))
            except ValueError as exc:
                raise ArchonixError(f"{var} must be a number, got {env[var]!r}") from exc
            s.sources[f"execution.{attr}"] = f"env:{var}"

    for key, value in (cli_overrides or {}).items():
        if value is not None:
            setattr(s, key, value)
            s.sources[f"execution.{key}"] = "command line"

    for name, value in (cli_permissions or {}).items():
        setattr(s.permissions, name, value)
        s.sources[f"permissions.{name}"] = "command line"

    if s.timeout_seconds <= 0 or s.max_output_bytes < 1024:
        raise ArchonixError("timeout_seconds must be > 0 and max_output_bytes >= 1024")
    return s
