"""Application-level errors mapped to HTTP responses by the API layer."""


class CoreNotConfiguredError(RuntimeError):
    """Raised when a deliberately empty infrastructure adapter is called."""


class FilingNotFoundError(LookupError):
    """Raised when a requested filing cannot be found in the configured store."""
