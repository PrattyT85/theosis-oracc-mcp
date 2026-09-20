"""Tests for the ORACC HTTP client — URL safety, limits, validation, and malformed payloads."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from oracc_mcp.client import OraccClient, archive_name, validate_project, validate_text_id
from oracc_mcp.errors import ArchiveMemberError, InvalidProjectError, InvalidTextIdError, MalformedJSONError, ResponseTooLargeError, UpstreamHTTPError

from conftest import make_archive, make_catalogue, make_manifest, make_metadata, make_projects_json, make_text


# ---- URL / path safety ----

class TestProjectValidation:
    def test_valid_simple(self):
        validate_project("rimanum")

    def test_valid_nested(self):
        validate_project("aemw/alalakh/idrimi")

    def test_empty_rejected(self):
        with pytest.raises(InvalidProjectError):
            validate_project("")

    def test_traversal_rejected(self):
        with pytest.raises(InvalidProjectError):
            validate_project("../etc/passwd")

    def test_leading_slash_rejected(self):
        with pytest.raises(InvalidProjectError):
            validate_project("/rimanum")

    def test_trailing_slash_rejected(self):
        with pytest.raises(InvalidProjectError):
            validate_project("rimanum/")

    def test_dots_rejected(self):
        with pytest.raises(InvalidProjectError):
            validate_project("rima..num")

    def test_special_chars_rejected(self):
        with pytest.raises(InvalidProjectError):
            validate_project("rimanum;rm -rf /")


class TestArchiveMapping:
    def test_nested_project_archive_name(self):
        assert archive_name("aemw/alalakh/idrimi") == "aemw-alalakh-idrimi.zip"

    def test_archive_member_rejects_traversal(self, client: OraccClient):
        with pytest.raises(ArchiveMemberError):
            client._member_bytes("rimanum", make_archive(), "../metadata.json")

    @pytest.mark.asyncio
    async def test_nested_project_archive_lookup(self, mock_http: respx.MockRouter):
        project = "aemw/alalakh/idrimi"
        mock_http.get("/json/aemw-alalakh-idrimi.zip").respond(
            content=make_archive(project)
        )
        client = OraccClient()
        result = await client.get_project_metadata(project)
        assert result["config"]["pathname"] == project
        await client.close()


class TestTextIdValidation:
    def test_valid(self):
        validate_text_id("P295625")

    def test_empty_rejected(self):
        with pytest.raises(InvalidTextIdError):
            validate_text_id("")

    def test_non_numeric_rejected(self):
        with pytest.raises(InvalidTextIdError):
            validate_text_id("Pabc")

    def test_missing_p_rejected(self):
        with pytest.raises(InvalidTextIdError):
            validate_text_id("295625")


# ---- HTTP client ----

class TestOraccClient:
    @pytest.mark.asyncio
    async def test_get_projects_list(self, client: OraccClient, mock_http: respx.MockRouter):
        mock_http.get("/projects.json").respond(json=make_projects_json(["rimanum", "dcclt"]))
        result = await client.get_projects_list()
        assert result == ["rimanum", "dcclt"]

    @pytest.mark.asyncio
    async def test_http_error_raises(self, client: OraccClient, mock_http: respx.MockRouter):
        mock_http.get("/projects.json").respond(status_code=500)
        with pytest.raises(UpstreamHTTPError) as exc_info:
            await client.get_projects_list()
        assert exc_info.value.status == 500

    @pytest.mark.asyncio
    async def test_malformed_json_raises(self, client: OraccClient, mock_http: respx.MockRouter):
        mock_http.get("/projects.json").respond(content=b"not json {{{")
        with pytest.raises(MalformedJSONError):
            await client.get_projects_list()

    @pytest.mark.asyncio
    async def test_response_too_large(self):
        big_client = OraccClient(max_bytes=100)
        # Create a mock httpx response that exceeds the limit
        large_data = json.dumps({"public": ["x"] * 1000})
        # Test via a direct mock
        with respx.mock(base_url="https://oracc.museum.upenn.edu") as router:
            router.get("/projects.json").respond(content=large_data.encode())
            with pytest.raises(ResponseTooLargeError):
                await big_client.fetch_json("/projects.json")

    @pytest.mark.asyncio
    async def test_get_project_manifest(self, client: OraccClient, mock_http: respx.MockRouter):
        mock_http.get("/json/rimanum.zip").respond(content=make_archive())
        result = await client.get_project_manifest("rimanum")
        assert result["type"] == "archive_manifest"
        assert result["project"] == "rimanum"
        assert "catalogue.json" in result["files"]

    @pytest.mark.asyncio
    async def test_get_project_metadata(self, client: OraccClient, mock_http: respx.MockRouter):
        mock_http.get("/json/rimanum.zip").respond(content=make_archive())
        result = await client.get_project_metadata("rimanum")
        assert result["config"]["pathname"] == "rimanum"

    @pytest.mark.asyncio
    async def test_get_text(self, client: OraccClient, mock_http: respx.MockRouter):
        mock_http.get("/json/rimanum.zip").respond(content=make_archive())
        result = await client.get_text("rimanum", "P295625")
        assert result["textid"] == "P295625"
        assert result["type"] == "cdl"

    @pytest.mark.asyncio
    async def test_get_project_catalogue(self, client: OraccClient, mock_http: respx.MockRouter):
        mock_http.get("/json/rimanum.zip").respond(content=make_archive())
        result = await client.get_project_catalogue("rimanum")
        assert "P295625" in result["members"]

    @pytest.mark.asyncio
    async def test_traversal_blocked(self, client: OraccClient, mock_http: respx.MockRouter):
        with pytest.raises(InvalidProjectError):
            await client.get_project_manifest("../../../etc")
