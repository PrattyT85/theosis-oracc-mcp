"""Tests for the ORACC MCP server tools — provenance, truncation, errors."""

from __future__ import annotations

import json

import pytest
import respx

from conftest import make_catalogue, make_manifest, make_metadata, make_projects_json, make_text


class TestListProjects:
    @pytest.mark.asyncio
    async def test_returns_projects(self, mock_http: respx.MockRouter):
        from oracc_mcp.server import list_projects
        mock_http.get("/projects.json").respond(json=make_projects_json(["rimanum", "dcclt"]))
        result = await list_projects()
        parsed = json.loads(result)
        assert parsed["count"] == 2
        assert "rimanum" in parsed["projects"]

    @pytest.mark.asyncio
    async def test_filter_query(self, mock_http: respx.MockRouter):
        from oracc_mcp.server import list_projects
        # "rima" is a substring of "rimanum" but not "ri-ma" or "dcclt"
        mock_http.get("/projects.json").respond(json=make_projects_json(["rimanum", "dcclt", "ri-ma"]))
        result = await list_projects(query="rima")
        parsed = json.loads(result)
        assert parsed["count"] == 1
        assert parsed["projects"] == ["rimanum"]

    @pytest.mark.asyncio
    async def test_limit(self, mock_http: respx.MockRouter):
        from oracc_mcp.server import list_projects
        projects = [f"proj{i}" for i in range(100)]
        mock_http.get("/projects.json").respond(json=make_projects_json(projects))
        result = await list_projects(limit=10)
        parsed = json.loads(result)
        assert parsed["count"] == 10

    @pytest.mark.asyncio
    async def test_http_error_returns_error_json(self, mock_http: respx.MockRouter):
        from oracc_mcp.server import list_projects
        mock_http.get("/projects.json").respond(status_code=503)
        result = await list_projects()
        parsed = json.loads(result)
        assert "error" in parsed


class TestGetProjectMetadata:
    @pytest.mark.asyncio
    async def test_returns_metadata(self, mock_http: respx.MockRouter):
        from oracc_mcp.server import get_project_metadata
        mock_http.get("/rimanum/metadata.json").respond(json=make_metadata())
        result = await get_project_metadata("rimanum")
        parsed = json.loads(result)
        assert "config" in parsed

    @pytest.mark.asyncio
    async def test_invalid_project(self):
        from oracc_mcp.server import get_project_metadata
        result = await get_project_metadata("../etc/passwd")
        parsed = json.loads(result)
        assert "error" in parsed


class TestGetProjectManifest:
    @pytest.mark.asyncio
    async def test_returns_manifest(self, mock_http: respx.MockRouter):
        from oracc_mcp.server import get_project_manifest
        mock_http.get("/rimanum/manifest.json").respond(json=make_manifest())
        result = await get_project_manifest("rimanum")
        parsed = json.loads(result)
        assert parsed["type"] == "manifest"


class TestListProjectTexts:
    @pytest.mark.asyncio
    async def test_returns_texts(self, mock_http: respx.MockRouter):
        from oracc_mcp.server import list_project_texts
        mock_http.get("/rimanum/catalogue.json").respond(json=make_catalogue())
        result = await list_project_texts("rimanum")
        parsed = json.loads(result)
        assert parsed["count"] == 2
        assert any(t["id"] == "P295625" for t in parsed["texts"])

    @pytest.mark.asyncio
    async def test_filter_by_designation(self, mock_http: respx.MockRouter):
        from oracc_mcp.server import list_project_texts
        mock_http.get("/rimanum/catalogue.json").respond(json=make_catalogue())
        result = await list_project_texts("rimanum", query="YOS 14, 341")
        parsed = json.loads(result)
        assert parsed["count"] == 1
        assert parsed["texts"][0]["id"] == "P295625"


class TestGetText:
    @pytest.mark.asyncio
    async def test_returns_bounded_text_with_provenance(self, mock_http: respx.MockRouter):
        from oracc_mcp.server import get_text
        mock_http.get("/rimanum/corpusjson/P295625.json").respond(json=make_text())
        result = await get_text("rimanum", "P295625")
        parsed = json.loads(result)
        assert parsed["source_url"] == "https://oracc.museum.upenn.edu/rimanum/corpusjson/P295625.json"
        assert parsed["textid"] == "P295625"
        assert parsed["project"] == "rimanum"
        assert "transliteration" in parsed
        assert "5(BAN₂)" in parsed["transliteration"]

    @pytest.mark.asyncio
    async def test_translation_extracted(self, mock_http: respx.MockRouter):
        from oracc_mcp.server import get_text
        mock_http.get("/rimanum/corpusjson/P295625.json").respond(json=make_text())
        result = await get_text("rimanum", "P295625")
        parsed = json.loads(result)
        assert "translation" in parsed
        assert "barley" in parsed["translation"]


class TestSearchProject:
    @pytest.mark.asyncio
    async def test_search_by_designation(self, mock_http: respx.MockRouter):
        from oracc_mcp.server import search_project
        mock_http.get("/rimanum/catalogue.json").respond(json=make_catalogue())
        result = await search_project("rimanum", "YOS 14, 342")
        parsed = json.loads(result)
        assert parsed["count"] == 1
        assert parsed["results"][0]["id"] == "P296047"

    @pytest.mark.asyncio
    async def test_search_no_match(self, mock_http: respx.MockRouter):
        from oracc_mcp.server import search_project
        mock_http.get("/rimanum/catalogue.json").respond(json=make_catalogue())
        result = await search_project("rimanum", "nonexistent")
        parsed = json.loads(result)
        assert parsed["count"] == 0


# ---- Robustness tests ----

class TestLimitClamping:
    @pytest.mark.asyncio
    async def test_limit_zero_clamps_to_one(self, mock_http: respx.MockRouter):
        from oracc_mcp.server import list_projects
        mock_http.get("/projects.json").respond(json=make_projects_json(["a", "b", "c"]))
        result = await list_projects(limit=0)
        parsed = json.loads(result)
        assert parsed["count"] == 1

    @pytest.mark.asyncio
    async def test_limit_negative_clamps_to_one(self, mock_http: respx.MockRouter):
        from oracc_mcp.server import list_projects
        mock_http.get("/projects.json").respond(json=make_projects_json(["a"]))
        result = await list_projects(limit=-5)
        parsed = json.loads(result)
        assert parsed["count"] == 1

    @pytest.mark.asyncio
    async def test_limit_exceeds_max_clamps_to_200(self, mock_http: respx.MockRouter):
        from oracc_mcp.server import list_projects
        projects = [f"p{i}" for i in range(250)]
        mock_http.get("/projects.json").respond(json=make_projects_json(projects))
        result = await list_projects(limit=999)
        parsed = json.loads(result)
        assert parsed["count"] == 200


class TestMalformedCatalogueHandling:
    @pytest.mark.asyncio
    async def test_members_not_dict_returns_error(self, mock_http: respx.MockRouter):
        from oracc_mcp.server import list_project_texts
        bad_catalogue = {"type": "catalogue", "members": "not a dict"}
        mock_http.get("/rimanum/catalogue.json").respond(json=bad_catalogue)
        result = await list_project_texts("rimanum")
        parsed = json.loads(result)
        assert "error" in parsed

    @pytest.mark.asyncio
    async def test_non_dict_member_skipped(self, mock_http: respx.MockRouter):
        from oracc_mcp.server import list_project_texts
        cat = {
            "type": "catalogue",
            "members": {
                "P295625": {"designation": "YOS 14, 341"},
                "P_bad": "not a dict entry",
            },
        }
        mock_http.get("/rimanum/catalogue.json").respond(json=cat)
        result = await list_project_texts("rimanum")
        parsed = json.loads(result)
        assert parsed["count"] == 1
        assert parsed["texts"][0]["id"] == "P295625"


class TestEmptyCDL:
    @pytest.mark.asyncio
    async def test_empty_cdl_returns_empty_transliteration(self, mock_http: respx.MockRouter):
        from oracc_mcp.server import get_text
        text = {"type": "cdl", "project": "rimanum", "textid": "P295625", "cdl": []}
        mock_http.get("/rimanum/corpusjson/P295625.json").respond(json=text)
        result = await get_text("rimanum", "P295625")
        parsed = json.loads(result)
        assert parsed["transliteration"] == ""
        assert "translation" not in parsed


class TestClientClose:
    @pytest.mark.asyncio
    async def test_close_idempotent(self):
        from oracc_mcp.client import OraccClient
        client = OraccClient()
        await client.close()  # no error on first close
        await client.close()  # idempotent second close

    @pytest.mark.asyncio
    async def test_client_reconnects_after_close(self, mock_http: respx.MockRouter):
        from oracc_mcp.client import OraccClient
        client = OraccClient()
        mock_http.get("/projects.json").respond(json=make_projects_json(["rimanum"]))
        result = await client.get_projects_list()
        assert result == ["rimanum"]
        await client.close()
        # Should create a new connection
        mock_http.get("/projects.json").respond(json=make_projects_json(["dcclt"]))
        result = await client.get_projects_list()
        assert result == ["dcclt"]
        await client.close()
