"""Shared application exceptions for authorization decisions.

HTTP-free: presentation maps these to the contract's 403 bodies via the
app-level exception handlers in app/main.py (and _handle_domain_errors for
exceptions raised inside use cases).
"""


class AccessDenied(PermissionError):
    """The caller may not access the requested resource."""


class InsufficientGroup(PermissionError):
    """The caller's group does not allow the attempted action."""
