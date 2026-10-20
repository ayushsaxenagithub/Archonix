"""Layered, best-effort secret redaction for persisted or displayed output.

Layer 1 replaces exact values that are known to be sensitive (explicitly configured
values and the values of environment variables whose names look sensitive).
Layer 2 replaces substrings matching recognisable credential formats.

Pattern matching cannot detect every secret. Redaction reduces accidental exposure;
it is not a guarantee, and raw output should still be treated as sensitive.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

MASK = "[REDACTED]"
MIN_VALUE_LENGTH = 6

DEFAULT_SENSITIVE_NAME = re.compile(
    r"(SECRET|TOKEN|PASSWORD|PASSWD|PASSPHRASE|API_?KEY|PRIVATE_?KEY|CREDENTIAL|AUTH|SESSION|COOKIE|DSN)",
    re.IGNORECASE,
)

# (label, pattern). Patterns are deliberately specific to keep false positives low.
CREDENTIAL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "private-key",
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
    ),
    ("aws-access-key-id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    (
        "github-token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b"),
    ),
    ("gitlab-token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}\b")),
    ("stripe-key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("openai-style-key", re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{32,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("bearer", re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=-]{16,}")),
    ("url-credentials", re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://[^\s:/@]+:)[^\s@/]+(@)")),
    (
        "assignment",
        re.compile(
            r"(?i)(\b[\w.-]*(?:password|passwd|secret|token|api[_-]?key|access[_-]?key)[\w.-]*[\"']?"
            r"\s*[:=]\s*(?:\\?[\"'])?)(?!\[REDACTED\])([^\s\"',;\\]{6,})"
        ),
    ),
]


@dataclass
class Redactor:
    values: set[str] = field(default_factory=set)
    extra_patterns: list[re.Pattern[str]] = field(default_factory=list)

    @classmethod
    def from_environment(
        cls,
        env: Mapping[str, str] | None = None,
        sensitive_env_names: Iterable[str] = (),
        values: Iterable[str] = (),
        extra_patterns: Iterable[str] = (),
    ) -> Redactor:
        env = os.environ if env is None else env
        names = set(sensitive_env_names)
        found = {
            v
            for k, v in env.items()
            if (k in names or DEFAULT_SENSITIVE_NAME.search(k)) and len(v) >= MIN_VALUE_LENGTH
        }
        found.update(v for v in values if len(v) >= MIN_VALUE_LENGTH)
        return cls(values=found, extra_patterns=[re.compile(p) for p in extra_patterns])

    def redact(self, text: str) -> tuple[str, int]:
        """Return (redacted_text, number_of_replacements)."""
        count = 0
        # Longest first so that a value containing another value is masked whole.
        for value in sorted(self.values, key=len, reverse=True):
            if value in text:
                count += text.count(value)
                text = text.replace(value, MASK)
        for label, pattern in CREDENTIAL_PATTERNS:
            if label == "assignment":
                text, n = _redact_assignments(pattern, text)
            else:
                text, n = pattern.subn(_replacement(label), text)
            count += n
        for pattern in self.extra_patterns:
            text, n = pattern.subn(MASK, text)
            count += n
        return text, count


def _looks_secret(value: str) -> bool:
    """Heuristic for `name = value` matches: plain words ("Possible") are not masked."""
    return len(value) >= 16 or any(not c.isalpha() for c in value)


def _redact_assignments(pattern: re.Pattern[str], text: str) -> tuple[str, int]:
    count = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal count
        if not _looks_secret(m.group(2)):
            return m.group(0)
        count += 1
        return m.group(1) + MASK

    return pattern.sub(repl, text), count


def _replacement(label: str) -> str:
    # Patterns with a captured prefix keep it so the output stays readable.
    if label == "bearer":
        return r"\1" + MASK
    if label == "url-credentials":
        return r"\1" + MASK + r"\2"
    return MASK
