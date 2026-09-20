"""Shared fixtures for ORACC MCP tests."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx
import pytest
import respx

from oracc_mcp.client import OraccClient

# Sample ORACC JSON fixtures


def make_projects_json(projects: list[str] | None = None) -> dict:
    if projects is None:
        projects = ["rimanum", "aemw/alalakh/idrimi", "dcclt"]
    return {"type": "projects", "public": projects}


def make_manifest(project: str = "rimanum", files: list[str] | None = None) -> dict:
    if files is None:
        files = ["corpus.json", "metadata.json"]
    return {"type": "manifest", "project": project, "files": files}


def make_metadata(project: str = "rimanum") -> dict:
    return {
        "type": "metadata",
        "config": {
            "pathname": project,
            "name": "The House of Prisoners",
            "abbrev": "Rīm-Anum",
        },
        "formats": {
            "atf": ["P295625"],
            "lem": ["P295625"],
            "tr-en": ["P295625"],
        },
    }


def make_catalogue(project: str = "rimanum") -> dict:
    return {
        "type": "catalogue",
        "project": project,
        "members": {
            "P295625": {
                "author": "Simmons, Stephen D.",
                "designation": "YOS 14, 341",
                "language": "Sumerian",
                "period": "Rim-Anum",
                "genre": "Administrative",
                "provenience": "Uruk",
            },
            "P296047": {
                "author": "Simmons, Stephen D.",
                "designation": "YOS 14, 342",
                "language": "Akkadian",
                "period": "Rim-Anum",
                "genre": "Administrative",
                "provenience": "Uruk",
            },
        },
    }


def make_corpus(project: str = "rimanum") -> dict:
    return {
        "type": "corpus",
        "project": project,
        "members": {
            "P295625": "corpusjson/P295625.json",
            "P296047": "corpusjson/P296047.json",
        },
    }


def make_text(project: str = "rimanum", text_id: str = "P295625") -> dict:
    return {
        "type": "cdl",
        "project": project,
        "textid": text_id,
        "cdl": [
            {
                "node": "c",
                "type": "text",
                "id": f"{text_id}.U0",
                "cdl": [
                    {
                        "node": "l",
                        "frag": "5(BAN₂)",
                        "f": {"lang": "akk-x-oldbab", "form": "5(BAN₂)", "pos": "n"},
                    },
                    {
                        "node": "l",
                        "frag": "še",
                        "f": {"lang": "akk-x-oldbab", "form": "še", "pos": "n"},
                    },
                    {
                        "node": "l",
                        "frag": "1",
                        "f": {"lang": "en", "form": "barley", "pos": "n"},
                    },
                ],
            }
        ],
    }


@pytest.fixture
def mock_http() -> AsyncIterator[respx.MockRouter]:
    with respx.mock(base_url="https://oracc.museum.upenn.edu") as router:
        yield router


@pytest.fixture
def client() -> OraccClient:
    return OraccClient(max_bytes=1024 * 1024)
