"""Error types for ORACC MCP operations."""

from __future__ import annotations


class OraccError(Exception):
    """Base error for ORACC operations."""


class InvalidProjectError(OraccError):
    """Raised when a project identifier is invalid or contains traversal."""

    def __init__(self, project: str) -> None:
        super().__init__(f"Invalid project identifier: {project!r}")
        self.project = project


class InvalidTextIdError(OraccError):
    """Raised when a text ID is invalid."""

    def __init__(self, text_id: str) -> None:
        super().__init__(f"Invalid text ID: {text_id!r}")
        self.text_id = text_id


class UpstreamHTTPError(OraccError):
    """Raised when ORACC returns a non-2xx HTTP response."""

    def __init__(self, url: str, status: int) -> None:
        super().__init__(f"ORACC HTTP {status} for {url}")
        self.url = url
        self.status = status


class MalformedJSONError(OraccError):
    """Raised when ORACC returns invalid JSON."""

    def __init__(self, url: str) -> None:
        super().__init__(f"Malformed JSON from {url}")
        self.url = url


class ResponseTooLargeError(OraccError):
    """Raised when a response exceeds the byte limit."""

    def __init__(self, url: str, size: int, limit: int) -> None:
        super().__init__(f"Response from {url} ({size} bytes) exceeds limit ({limit} bytes)")
        self.url = url
        self.size = size
        self.limit = limit
