"""Reusable async client for the ORACC JSON archive API."""

from __future__ import annotations

import io
import json
import re
import zipfile
from typing import Any

import httpx

from .errors import (
    ArchiveMemberError,
    InvalidProjectError,
    InvalidTextIdError,
    MalformedJSONError,
    ResponseTooLargeError,
    UpstreamHTTPError,
)

# Project archives are the current ORACC JSON delivery format. Keep both the
# archive and individual member bounded; no archive is persisted to disk.
DEFAULT_MAX_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_MEMBER_BYTES = 2 * 1024 * 1024
BASE_URL = "https://oracc.museum.upenn.edu"

_PROJECT_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_\-]*(/[a-zA-Z0-9][a-zA-Z0-9_\-]*)*$")
_TEXTID_RE = re.compile(r"^P\d+$")


def validate_project(project: str) -> None:
    """Validate a project identifier and reject traversal/path tricks."""
    if not project or not _PROJECT_RE.match(project):
        raise InvalidProjectError(project)
    if ".." in project or project.startswith("/") or project.endswith("/"):
        raise InvalidProjectError(project)


def validate_text_id(text_id: str) -> None:
    """Validate an ORACC text ID such as ``P295625``."""
    if not text_id or not _TEXTID_RE.match(text_id):
        raise InvalidTextIdError(text_id)


def archive_name(project: str) -> str:
    """Map a validated project path to the current ORACC archive filename."""
    validate_project(project)
    return f"{project.replace('/', '-')}.zip"


def archive_url(project: str) -> str:
    """Return the canonical public archive URL for a project."""
    return f"{BASE_URL}/json/{archive_name(project)}"


class OraccClient:
    """Async HTTP client for ORACC's public JSON archives."""

    def __init__(
        self,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_member_bytes: int = DEFAULT_MAX_MEMBER_BYTES,
    ) -> None:
        self._max_bytes = max_bytes
        self._max_member_bytes = max_member_bytes
        self._http: httpx.AsyncClient | None = None
        self._archive_cache: dict[str, bytes] = {}

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                base_url=BASE_URL,
                timeout=httpx.Timeout(45.0, connect=10.0),
                follow_redirects=True,
                headers={"User-Agent": "theosis-oracc-mcp/0.2"},
            )
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()
        self._archive_cache.clear()

    async def fetch_bytes(self, path: str, *, max_bytes: int | None = None) -> bytes:
        """Fetch a bounded response body from ORACC."""
        client = await self._get_client()
        url = path.lstrip("/") if not path.startswith("http") else path
        limit = max_bytes or self._max_bytes
        async with client.stream("GET", url) as resp:
            if resp.status_code != 200:
                await resp.aread()
                raise UpstreamHTTPError(str(resp.url), resp.status_code)
            chunks: list[bytes] = []
            total = 0
            async for chunk in resp.aiter_bytes(64 * 1024):
                total += len(chunk)
                if total > limit:
                    raise ResponseTooLargeError(str(resp.url), total, limit)
                chunks.append(chunk)
            raw = b"".join(chunks)
        if not raw:
            raise MalformedJSONError(str(url))
        return raw

    async def fetch_json(self, path: str) -> Any:
        """Fetch and decode a JSON resource."""
        url = path.lstrip("/") if not path.startswith("http") else path
        raw = await self.fetch_bytes(path)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MalformedJSONError(str(url)) from exc

    async def _get_archive(self, project: str) -> bytes:
        validate_project(project)
        name = archive_name(project)
        if name not in self._archive_cache:
            self._archive_cache[name] = await self.fetch_bytes(f"/json/{name}")
        return self._archive_cache[name]

    def _member_bytes(self, project: str, archive: bytes, member: str) -> bytes:
        """Extract one safe, bounded member from a project archive."""
        validate_project(project)
        expected_prefix = f"{project}/"
        if not member or member.startswith("/") or ".." in member:
            raise ArchiveMemberError(project, member)
        member_path = f"{expected_prefix}{member}"
        try:
            with zipfile.ZipFile(io.BytesIO(archive)) as zf:
                try:
                    info = zf.getinfo(member_path)
                except KeyError as exc:
                    raise ArchiveMemberError(project, member) from exc
                if info.is_dir() or info.file_size > self._max_member_bytes:
                    raise ArchiveMemberError(project, member)
                return zf.read(info)
        except zipfile.BadZipFile as exc:
            raise ArchiveMemberError(project, member) from exc

    def _archive_members(self, project: str, archive: bytes) -> list[str]:
        validate_project(project)
        prefix = f"{project}/"
        try:
            with zipfile.ZipFile(io.BytesIO(archive)) as zf:
                members: list[str] = []
                for info in zf.infolist():
                    if info.is_dir() or not info.filename.startswith(prefix):
                        continue
                    relative = info.filename[len(prefix):]
                    if relative and ".." not in relative and not relative.startswith("/"):
                        members.append(relative)
                return sorted(members)
        except zipfile.BadZipFile as exc:
            raise ArchiveMemberError(project, "<archive>") from exc

    async def _archive_json(self, project: str, member: str) -> dict:
        archive = await self._get_archive(project)
        raw = self._member_bytes(project, archive, member)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MalformedJSONError(f"{archive_url(project)}#{project}/{member}") from exc
        if not isinstance(data, dict):
            raise MalformedJSONError(f"{archive_url(project)}#{project}/{member}")
        return data

    async def get_projects_list(self) -> list[str]:
        data = await self.fetch_json("/projects.json")
        if not isinstance(data, dict) or not isinstance(data.get("public"), list):
            raise MalformedJSONError("/projects.json")
        return [p for p in data["public"] if isinstance(p, str)]

    async def get_project_manifest(self, project: str) -> dict:
        archive = await self._get_archive(project)
        files = self._archive_members(project, archive)
        return {
            "type": "archive_manifest",
            "project": project,
            "archive": archive_name(project),
            "archive_url": archive_url(project),
            "files": files,
        }

    async def get_project_metadata(self, project: str) -> dict:
        return await self._archive_json(project, "metadata.json")

    async def get_project_catalogue(self, project: str) -> dict:
        return await self._archive_json(project, "catalogue.json")

    async def get_project_corpus(self, project: str) -> dict:
        return await self._archive_json(project, "corpus.json")

    async def get_text(self, project: str, text_id: str) -> dict:
        validate_project(project)
        validate_text_id(text_id)
        return await self._archive_json(project, f"corpusjson/{text_id}.json")
