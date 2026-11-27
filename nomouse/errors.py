"""Exceptions that carry a user-friendly message instead of a traceback."""


class StartupError(RuntimeError):
    """Raised when NoMouse cannot start (camera unavailable, missing dependency, ...)."""
