"""
Defines custom exceptions for the application to allow for more specific
error handling.
"""


class AuthenticationError(Exception):
    """Raised when user login fails due to invalid credentials."""

    pass


class IneligibleError(Exception):
    """Raised when the user's account is not eligible for streaming (e.g., free tier)."""

    pass


class InvalidAppIdError(Exception):
    """Raised when the provided App ID is rejected by the Qobuz API."""

    pass


class InvalidAppSecretError(Exception):
    """Raised when the derived app secrets are invalid."""

    pass


class InvalidQuality(Exception):
    """Raised when an invalid quality ID is requested."""

    pass


class NonStreamable(Exception):
    """Raised when attempting to download an item that is not available for streaming."""

    pass
