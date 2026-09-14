"""Domain-level exceptions. The API layer maps these to HTTP responses in one place."""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    code = "domain_error"
    status_code = 400

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(DomainError):
    code = "not_found"
    status_code = 404


class ValidationFailedError(DomainError):
    code = "validation_failed"
    status_code = 422


class BoundaryTooLargeError(DomainError):
    code = "boundary_too_large"
    status_code = 422


class UpstreamUnavailableError(DomainError):
    code = "upstream_unavailable"
    status_code = 503
