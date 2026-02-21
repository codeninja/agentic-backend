"""Authentication error types."""


class AuthenticationError(Exception):
    """Raised when authentication fails (invalid credentials, CSRF mismatch, etc.)."""
