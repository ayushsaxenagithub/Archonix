from __future__ import annotations

import pytest

from archonix.redact import MASK, Redactor

# Synthetic credentials assembled at runtime so the repository never contains a
# string that looks like a real token.
GITHUB = "ghp_" + "A1b2C3d4" * 5
AWS = "AKIA" + "ABCDEFGHIJKLMNOP"
JWT = "eyJ" + "hbGciOiJIUzI1" + ".eyJ" + "zdWIiOiIxMjM0" + ".c2lnbmF0dXJlLXZhbHVl"
KEY_BLOCK = "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----"


@pytest.mark.parametrize("secret", [GITHUB, AWS, JWT, KEY_BLOCK])
def test_credential_patterns(secret: str) -> None:
    text, n = Redactor().redact(f"value={secret} end")
    assert secret not in text and n >= 1


def test_prefix_preserving_patterns() -> None:
    r = Redactor()
    assert r.redact("Authorization: Bearer abcdefghijklmnop1234")[0].endswith("Bearer " + MASK)
    assert r.redact("postgres://app:s3cretpass@db/x")[0] == f"postgres://app:{MASK}@db/x"
    assert r.redact("DB_PASSWORD=hunter22")[0] == f"DB_PASSWORD={MASK}"


def test_json_escaped_assignment() -> None:
    text = '{"code": "DB_PASSWORD = \\"hunter-two-22\\""}'
    redacted, n = Redactor().redact(text)
    assert "hunter-two-22" not in redacted and n == 1


def test_plain_words_after_secret_like_names_are_kept() -> None:
    text = "hardcoded_password_string: Possible hardcoded password"
    assert Redactor().redact(text) == (text, 0)


def test_environment_values_and_configured_names() -> None:
    env = {
        "SERVICE_TOKEN": "tok-value-123",
        "INTERNAL": "zzz-internal-zzz",
        "PLAIN": "visible-value",
    }
    r = Redactor.from_environment(env=env, sensitive_env_names=["INTERNAL"])
    text, n = r.redact("tok-value-123 zzz-internal-zzz visible-value")
    assert text == f"{MASK} {MASK} visible-value" and n == 2


def test_short_values_are_not_treated_as_secrets() -> None:
    r = Redactor.from_environment(env={"API_KEY": "abc"})
    assert r.redact("abc abc")[1] == 0


def test_extra_patterns() -> None:
    r = Redactor.from_environment(env={}, extra_patterns=[r"ACME-\d{6}"])
    assert r.redact("id ACME-123456")[0] == f"id {MASK}"
