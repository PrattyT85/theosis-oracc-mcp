"""FastMCP stdio server exposing ORACC read-only tools."""

from __future__ import annotations

import json
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import OraccClient, archive_url, validate_project, validate_text_id
from .errors import InvalidProjectError, InvalidTextIdError, MalformedJSONError, OraccError, ResponseTooLargeError, UpstreamHTTPError

mcp = FastMCP("oracc-mcp", instructions=(
    "Read-only MCP server for the Open Richly Annotated Cuneiform Corpus (ORACC). "
    "Project tools query the current https://oracc.museum.upenn.edu/json/ archives. "
    "No data is stored or modified; this server is for research reference only."
))

_client: OraccClient | None = None


def _get_client() -> OraccClient:
    global _client
    if _client is None:
        _client = OraccClient()
    return _client


def _error_response(msg: str) -> dict[str, Any]:
    return {"error": True, "message": msg}


def _truncate(text: str, limit: int = 8000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated, {len(text)} total chars]"


# ---------- tools ----------


@mcp.tool()
async def list_projects(query: str | None = None, limit: int = 50) -> str:
    """List ORACC public projects, optionally filtered by name substring.

    Args:
        query: Optional case-insensitive substring filter.
        limit: Max projects to return (default 50).
    """
    try:
        projects = await _get_client().get_projects_list()
        if query:
            q = query.lower()
            projects = [p for p in projects if q in p.lower()]
        limit = max(1, min(limit, 200))
        projects = projects[:limit]
        return _truncate(json.dumps({"count": len(projects), "projects": projects}, indent=2))
    except OraccError as e:
        return json.dumps(_error_response(str(e)))


@mcp.tool()
async def get_project_metadata(project: str) -> str:
    """Get metadata for an ORACC project (config, formats, witnesses).

    Args:
        project: ORACC project identifier (e.g. 'rimanum' or 'aemw/alalakh/idrimi').
    """
    try:
        data = await _get_client().get_project_metadata(project)
        return _truncate(json.dumps(data, indent=2, default=str))
    except OraccError as e:
        return json.dumps(_error_response(str(e)))


@mcp.tool()
async def get_project_manifest(project: str) -> str:
    """Get the JSON manifest listing available files for a project.

    Args:
        project: ORACC project identifier.
    """
    try:
        data = await _get_client().get_project_manifest(project)
        return _truncate(json.dumps(data, indent=2))
    except OraccError as e:
        return json.dumps(_error_response(str(e)))


@mcp.tool()
async def list_project_texts(project: str, query: str | None = None, limit: int = 50) -> str:
    """List texts in a project's catalogue with key metadata (designation, language, period, genre).

    Args:
        project: ORACC project identifier.
        query: Optional case-insensitive substring filter on designation.
        limit: Max texts to return (default 50).
    """
    try:
        cat = await _get_client().get_project_catalogue(project)
        members = cat.get("members", {})
        if not isinstance(members, dict):
            return json.dumps(_error_response(f"Unexpected catalogue structure for {project}"))

        items: list[dict] = []
        for tid, info in members.items():
            if not isinstance(info, dict):
                continue
            designation = info.get("designation", "")
            if query and query.lower() not in designation.lower():
                continue
            items.append({
                "id": tid,
                "designation": designation,
                "language": info.get("language", ""),
                "period": info.get("period", ""),
                "genre": info.get("genre", ""),
                "provenience": info.get("provenience", ""),
            })
        limit = max(1, min(limit, 200))
        items = items[:limit]
        return _truncate(json.dumps({"project": project, "count": len(items), "texts": items}, indent=2))
    except OraccError as e:
        return json.dumps(_error_response(str(e)))


@mcp.tool()
async def get_text(project: str, text_id: str) -> str:
    """Get a bounded excerpt of an ORACC text edition (CDL structure).

    Returns source URL, text ID, project, and transliteration/translation text where available.
    The response is capped to keep output manageable.

    Args:
        project: ORACC project identifier.
        text_id: ORACC text ID (e.g. 'P295625').
    """
    try:
        data = await _get_client().get_text(project, text_id)
        source_url = f"{archive_url(project)}#{project}/corpusjson/{text_id}.json"

        result: dict[str, Any] = {
            "source_url": source_url,
            "project": data.get("project", project),
            "textid": data.get("textid", text_id),
            "type": data.get("type", ""),
        }

        # Extract a bounded transliteration from the CDL tree
        cdl = data.get("cdl", [])
        fragments: list[str] = []
        _extract_fragments(cdl, fragments, max_fragments=200)
        transliteration = " ".join(fragments)
        result["transliteration"] = _truncate(transliteration, 8000)

        # Collect English translations if present in the "l" nodes' f objects
        en_frags: list[str] = []
        _extract_translations(cdl, en_frags, max_fragments=100)
        if en_frags:
            result["translation"] = _truncate(" ".join(en_frags), 4000)

        return _truncate(json.dumps(result, indent=2, default=str))
    except OraccError as e:
        return json.dumps(_error_response(str(e)))


@mcp.tool()
async def search_project(project: str, query: str, limit: int = 20) -> str:
    """Search a project's catalogue for texts matching a query (designation, author, or title).

    Args:
        project: ORACC project identifier.
        query: Case-insensitive search term.
        limit: Max results (default 20).
    """
    try:
        cat = await _get_client().get_project_catalogue(project)
        members = cat.get("members", {})
        if not isinstance(members, dict):
            return json.dumps(_error_response(f"Unexpected catalogue structure for {project}"))

        q = query.lower()
        matches: list[dict] = []
        for tid, info in members.items():
            if not isinstance(info, dict):
                continue
            # Search across designation, author, title
            designation = info.get("designation", "")
            author = info.get("author", "")
            title = info.get("title", "")
            if q in designation.lower() or q in author.lower() or q in title.lower():
                matches.append({
                    "id": tid,
                    "designation": designation,
                    "author": author,
                    "language": info.get("language", ""),
                    "period": info.get("period", ""),
                })
            if len(matches) >= limit:
                break

        return _truncate(json.dumps({
            "project": project,
            "query": query,
            "count": len(matches),
            "results": matches,
        }, indent=2))
    except OraccError as e:
        return json.dumps(_error_response(str(e)))


# ---------- CDL helpers ----------


def _extract_fragments(cdl: list, out: list[str], max_fragments: int) -> None:
    """Walk the CDL tree and collect transliteration fragments from lemma 'frag' fields."""
    if len(out) >= max_fragments:
        return
    for node in cdl:
        if len(out) >= max_fragments:
            return
        if node.get("node") == "l":
            frag = node.get("frag")
            if frag:
                out.append(frag)
        children = node.get("cdl")
        if children and isinstance(children, list):
            _extract_fragments(children, out, max_fragments)


def _extract_translations(cdl: list, out: list[str], max_fragments: int) -> None:
    """Walk the CDL tree and collect English translation fragments."""
    if len(out) >= max_fragments:
        return
    for node in cdl:
        if len(out) >= max_fragments:
            return
        if node.get("node") == "l":
            f = node.get("f")
            if isinstance(f, dict) and f.get("lang", "").startswith("en") and f.get("form"):
                out.append(f["form"])
        children = node.get("cdl")
        if children and isinstance(children, list):
            _extract_translations(children, out, max_fragments)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
