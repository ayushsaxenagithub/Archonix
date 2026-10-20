"""Exception types with user-facing messages."""


class ArchonixError(Exception):
    """Base class for errors reported to the user without a traceback."""


class PolicyError(ArchonixError):
    """An operation was refused by the effective execution policy."""


class ValidationFailed(ArchonixError):
    """A document failed schema or semantic validation."""
