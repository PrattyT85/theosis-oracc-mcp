"""Live smoke test for ORACC MCP.

Skipped unless ORACC_LIVE=1 is set. When run, it fetches projects.json,
chooses a stable small project (or uses ORACC_PROJECT), and fetches
metadata/manifest/catalogue/text data, printing only bounded results.

Usage:
    ORACC_LIVE=1 uv run python scripts/smoke_live.py
    # or via pytest:
    ORACC_LIVE=1 uv run pytest -m live -v
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

from oracc_mcp.client import OraccClient
from oracc_mcp.errors import OraccError


def _pick_project(projects: list[str]) -> str:
    """Pick a stable small project for testing."""
    env = os.environ.get("ORACC_PROJECT")
    if env:
        return env
    # Prefer rimanum (small, stable, well-known)
    for candidate in ["rimanum", "dcclt", "ribo"]:
        if candidate in projects:
            return candidate
    # Fallback to first project
    return projects[0] if projects else "rimanum"


async def run_smoke() -> dict:
    client = OraccClient()
    results: dict = {}

    try:
        # 1. Fetch projects
        print("=== Fetching projects.json ===")
        projects = await client.get_projects_list()
        print(f"Found {len(projects)} projects (first 10: {projects[:10]})")
        results["project_count"] = len(projects)
        results["sample_projects"] = projects[:10]

        project = _pick_project(projects)
        print(f"\n=== Using project: {project} ===")

        # 2. Fetch metadata
        print(f"Fetching {project}/metadata.json ...")
        metadata = await client.get_project_metadata(project)
        config = metadata.get("config", {})
        print(f"  name: {config.get('name', 'N/A')}")
        print(f"  abbrev: {config.get('abbrev', 'N/A')}")
        results["metadata_name"] = config.get("name", "N/A")

        # 3. Fetch manifest
        print(f"Fetching {project}/manifest.json ...")
        manifest = await client.get_project_manifest(project)
        files = manifest.get("files", [])
        print(f"  Available JSON files: {files[:10]}")
        results["manifest_files"] = files[:10]

        # 4. Fetch catalogue
        print(f"Fetching {project}/catalogue.json ...")
        catalogue = await client.get_project_catalogue(project)
        members = catalogue.get("members", {})
        text_ids = list(members.keys())
        print(f"  Catalogue has {len(text_ids)} texts (first 5: {text_ids[:5]})")
        results["catalogue_count"] = len(text_ids)

        # 5. Fetch the first non-empty text edition. ORACC catalogues can
        # include zero-byte members for unpublished or damaged witnesses.
        selected_id = None
        text_data = None
        for candidate_id in text_ids:
            try:
                text_data = await client.get_text(project, candidate_id)
                selected_id = candidate_id
                break
            except OraccError:
                continue

        if selected_id and text_data is not None:
            print(f"\nFetching first non-empty text: {selected_id} ...")
            cdl = text_data.get("cdl", [])
            frag_count = 0

            def _count(nodes):
                nonlocal frag_count
                for n in nodes:
                    if n.get("node") == "l" and n.get("frag"):
                        frag_count += 1
                    children = n.get("cdl")
                    if children and isinstance(children, list):
                        _count(children)

            _count(cdl)
            print(f"  CDL nodes: {len(cdl)}, lemma fragments: {frag_count}")
            print(f"  source: https://oracc.museum.upenn.edu/json/{project.replace('/', '-')}.zip#{project}/corpusjson/{selected_id}.json")
            results["first_text_id"] = selected_id
            results["lemma_fragments"] = frag_count
        else:
            raise RuntimeError("No non-empty corpus text found in the selected project")

        print("\n=== Smoke test passed ===")
        results["status"] = "passed"

    finally:
        await client.close()

    return results


@pytest.mark.live
def test_live_smoke():
    """Live smoke test — requires ORACC_LIVE=1."""
    if os.environ.get("ORACC_LIVE") != "1":
        pytest.skip("Set ORACC_LIVE=1 to run live smoke test")
    results = asyncio.get_event_loop().run_until_complete(run_smoke())
    assert results["status"] == "passed"


if __name__ == "__main__":
    # Allow direct invocation for manual testing
    asyncio.run(run_smoke())
