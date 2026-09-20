"""Reusable async HTTP client for ORACC JSON API requests."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .errors import (
    InvalidProjectError,
    InvalidTextIdError,
    MalformedJSONError,
    ResponseTooLargeError,
    UpstreamHTTPError,
)

# Default byte limit for response bodies (4 MB)
DEFAULT_MAX_BYTES = 4 * 1024 * 1024

BASE_URL = "https://oracc.museum.upenn.edu"

# Project identifiers may contain letters, digits, hyphens, underscores, and slashes.
# Each path segment is validated individually; no leading/trailing slashes.
_PROJECT_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_\-]*(/[a-zA-Z0-9][a-zA-Z0-9_\-]*)*$")

# Text IDs are always P followed by digits, e.g. P295625
_TEXTID_RE = re.compile(r"^P\d+$")


def validate_project(project: str) -> None:
    """Validate a project identifier. Raises InvalidProjectError on failure."""
    if not project or not _PROJECT_RE.match(project):
        raise InvalidProjectError(project)
    # Block traversal attempts explicitly
    if ".." in project or project.startswith("/") or project.endswith("/"):
        raise InvalidProjectError(project)


def validate_text_id(text_id: str) -> None:
    """Validate a text ID format. Raises InvalidTextIdError on failure."""
    if not text_id or not _TEXTID_RE.match(text_id):
        raise InvalidTextIdError(text_id)


class OraccClient:
    """Async HTTP client for ORACC JSON endpoints."""

    def __init__(self, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
        self._max_bytes = max_bytes
        self._http: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                base_url=BASE_URL,
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
                headers={"User-Agent": "theosis-oracc-mcp/0.1"},
            )
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()

    async def fetch_json(self, path: str) -> Any:
        """Fetch a JSON resource from ORACC. Returns parsed JSON.

        Raises UpstreamHTTPError, MalformedJSONError, or ResponseTooLargeError.
        """
        client = await self._get_client()
        url = path.lstrip("/") if not path.startswith("http") else path

        # Stream to enforce byte limit
        async with client.stream("GET", url) as resp:
            if resp.status_code != 200:
                await resp.aread()
                raise UpstreamHTTPError(str(resp.url), resp.status_code)
            chunks: list[bytes] = []
            total = 0
            async for chunk in resp.aiter_bytes(64 * 1024):
                total += len(chunk)
                if total > self._max_bytes:
                    raise ResponseTooLargeError(str(resp.url), total, self._max_bytes)
                chunks.append(chunk)
            raw = b"".join(chunks)

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise MalformedJSONError(str(url))

    # -- Convenience methods --

    async def get_projects_list(self) -> list[str]:
        """Return the list of public project identifiers."""
        data = await self.fetch_json("/projects.json")
        if not isinstance(data, dict) or "public" not in data:
            raise MalformedJSONError("/projects.json")
        return list(data["public"])

    async def get_project_manifest(self, project: str) -> dict:
        validate_project(project)
        data = await self.fetch_json(f"/{project}/manifest.json")
        if not isinstance(data, dict):
            raise MalformedJSONError(f"/{project}/manifest.json")
        return data

    async def get_project_metadata(self, project: str) -> dict:
        validate_project(project)
        data = await self.fetch_json(f"/{project}/metadata.json")
        if not isinstance(data, dict):
            raise MalformedJSONError(f"/{project}/metadata.json")
        return data

    async def get_project_catalogue(self, project: str) -> dict:
        validate_project(project)
        data = await self.fetch_json(f"/{project}/catalogue.json")
        if not isinstance(data, dict):
            raise MalformedJSONError(f"/{project}/catalogue.json")
        return data

    async def get_project_corpus(self, project: str) -> dict:
        validate_project(project)
        data = await self.fetch_json(f"/{project}/corpus.json")
        if not isinstance(data, dict):
            raise MalformedJSONError(f"/{project}/corpus.json")
        return data

    async def get_text(self, project: str, text_id: str) -> dict:
        validate_project(project)
        validate_text_id(text_id)
        data = await self.fetch_json(f"/{project}/corpusjson/{text_id}.json")
        if not isinstance(data, dict):
            raise MalformedJSONError(f"/{project}/corpusjson/{text_id}.json")
        return data
