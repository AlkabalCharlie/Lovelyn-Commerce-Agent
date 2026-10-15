"""Custom exceptions for the Lovelyn application."""

class SSRFError(Exception):
    """Raised when a URL attempts to access internal or restricted networks."""
    pass

class ExtractionError(Exception):
    """Raised when product data cannot be extracted from a URL."""
    pass