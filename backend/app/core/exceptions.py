"""Application custom exceptions."""

class ApplicationError(Exception):
    """Base exception class for the application."""

class ConfigurationError(ApplicationError):
    """Raised when an application setting is missing or invalid."""

class ExternalApiError(ApplicationError):
    """Raised when an integration with an external API fails."""

class TemporaryApiError(ExternalApiError):
    """Raised on temporary network timeouts or server errors."""

class DataNormalizationError(ApplicationError):
    """Raised when parsing/structuring external data fails."""

class CompanyNotFoundError(ApplicationError):
    """Raised when a requested company is not configured."""


class LlmUnavailableError(ApplicationError):
    """Raised when the language model provider is unreachable, misconfigured or rejects the credentials."""


class LlmResponseError(ApplicationError):
    """Raised when the language model returns output that cannot be validated."""
