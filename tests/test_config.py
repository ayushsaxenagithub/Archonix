from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from archonix.config import load_settings
from archonix.errors import ArchonixError


def test_mode_defaults() -> None:
    assert load_settings(None, mode="discovery").permissions.as_dict() == {
        "source_writes": False,
        "artifact_writes": True,
        "repo_code": False,
        "external_tools": False,
        "network": False,
        "dependency_install": False,
        "shared_environment": False,
        "destructive": False,
    }
    audit = load_settings(None, mode="audit").permissions
    assert audit.external_tools and not audit.repo_code and not audit.network
    impl = load_settings(None, mode="implementation").permissions
    assert impl.source_writes and impl.repo_code and not impl.network


def test_precedence_user_repo_explicit_env_cli(
    make_repo: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = tmp_path / "user.toml"
    user.write_text("[execution]\ntimeout_seconds = 10\nmax_output_bytes = 5000\n")
    root = make_repo({"archonix.toml": "[execution]\ntimeout_seconds = 20\n"})
    explicit = tmp_path / "explicit.toml"
    explicit.write_text("[execution]\ntimeout_seconds = 30\n")
    monkeypatch.setenv("ARCHONIX_USER_CONFIG", str(user))

    s = load_settings(root)
    assert s.timeout_seconds == 20 and s.max_output_bytes == 5000
    assert s.sources["execution.timeout_seconds"] == "repository config (archonix.toml)"
    assert s.sources["execution.max_output_bytes"].startswith("user config")
    assert load_settings(root, explicit_config=explicit).timeout_seconds == 30
    monkeypatch.setenv("ARCHONIX_TIMEOUT_SECONDS", "40")
    assert load_settings(root, explicit_config=explicit).timeout_seconds == 40
    s = load_settings(root, explicit_config=explicit, cli_overrides={"timeout_seconds": 50})
    assert s.timeout_seconds == 50 and s.sources["execution.timeout_seconds"] == "command line"


def test_repo_config_is_restrict_only(make_repo: Callable[..., Path]) -> None:
    root = make_repo(
        {
            "archonix.toml": """
        [permissions]
        repo_code = true
        network = true
        external_tools = false
        [execution]
        env_passthrough = ["AWS_SECRET_ACCESS_KEY"]
        [checks.bandit]
        extra_args = ["--config", "evil.py"]
        enabled = false
    """
        }
    )
    s = load_settings(root, mode="audit")
    assert not s.permissions.repo_code and not s.permissions.network
    assert not s.permissions.external_tools  # restricting is honoured
    assert s.env_passthrough == []
    assert s.check("bandit").extra_args == [] and s.check("bandit").enabled is False
    assert len(s.ignored) == 4


def test_trusted_explicit_config_may_grant(tmp_path: Path) -> None:
    cfg = tmp_path / "trusted.toml"
    cfg.write_text('[permissions]\nnetwork = true\n[checks.ruff]\nextra_args = ["--select", "E"]\n')
    s = load_settings(None, explicit_config=cfg)
    assert s.permissions.network and s.check("ruff").extra_args == ["--select", "E"]


def test_cli_overrides_repo_restriction(make_repo: Callable[..., Path]) -> None:
    root = make_repo({"archonix.toml": "[permissions]\nexternal_tools = false\n"})
    s = load_settings(root, mode="audit", cli_permissions={"external_tools": True})
    assert (
        s.permissions.external_tools and s.sources["permissions.external_tools"] == "command line"
    )


@pytest.mark.parametrize(
    "content, message",
    [
        ("[execution]\ntimeout_seconds = -1\n", "invalid config"),
        ("[unknown]\nx = 1\n", "invalid config"),
        ("not toml = = =", "invalid TOML"),
    ],
)
def test_invalid_config(tmp_path: Path, content: str, message: str) -> None:
    cfg = tmp_path / "c.toml"
    cfg.write_text(content)
    with pytest.raises(ArchonixError, match=message):
        load_settings(None, explicit_config=cfg)


def test_example_repo_config_is_valid() -> None:
    from conftest import REPO_ROOT

    s = load_settings(None, explicit_config=REPO_ROOT / "examples" / "archonix.toml")
    assert s.check("vulture").enabled is False
