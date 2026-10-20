"""Registry of built-in check adapters."""

from __future__ import annotations

from .base import Adapter, Context, ParseOutcome
from .python_tools import BanditAdapter, PytestAdapter, RuffAdapter, VultureAdapter
from .security_tools import (
    GitleaksAdapter,
    NpmAuditAdapter,
    SemgrepLocalAdapter,
    SemgrepRegistryAdapter,
)

ADAPTERS: dict[str, Adapter] = {
    a.id: a
    for a in (
        RuffAdapter(),
        BanditAdapter(),
        VultureAdapter(),
        PytestAdapter(),
        GitleaksAdapter(),
        SemgrepLocalAdapter(),
        SemgrepRegistryAdapter(),
        NpmAuditAdapter(),
    )
}

__all__ = ["ADAPTERS", "Adapter", "Context", "ParseOutcome"]
