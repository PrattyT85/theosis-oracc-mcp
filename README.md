# theosis-oracc-mcp

Read-only MCP server wrapper for the [ORACC](https://oracc.museum.upenn.edu/) (Open Richly Annotated Cuneiform Corpus) JSON archive API, built for integration with the [Theosis](https://github.com/PrattyT85/theosis-mcp) theological research stack.

## Features

- **`list_projects`** — List public ORACC projects with optional filtering
- **`get_project_metadata`** — Project config, formats, and witnesses
- **`get_project_manifest`** — Available JSON files for a project
- **`list_project_texts`** — Catalogue entries with designation, language, period, genre
- **`get_text`** — Bounded CDL excerpt with transliteration and translation
- **`search_project`** — Search catalogue by designation, author, or title

## Setup

```bash
uv sync
uv run python -m oracc_mcp.server  # stdio transport
```

Or add to your Hermes config:

```yaml
mcp:
  servers:
    oracc-mcp:
      transport: stdio
      command: uv
      args: ["--directory", "/path/to/theosis-oracc-mcp", "run", "python", "-m", "oracc_mcp.server"]
```

## Testing

```bash
uv run pytest -v                    # offline tests only
uv run pytest -m live -v           # live tests (ORACC_LIVE=1 required)
ORACC_LIVE=1 uv run pytest -m live -v
```

## ORACC Attribution

This server is a read-only client for the [ORACC JSON archive API](https://oracc.museum.upenn.edu/json/). `projects.json` is used for discovery; project metadata, catalogues, corpora, and text editions are read from the current `/json/<project-archive>.zip` downloads. Archives are bounded and cached only in memory for the lifetime of one client; they are not persisted or redistributed. Results include the archive URL and member path as provenance. ORACC data is provided by the University of Pennsylvania and its project contributors; follow the licence and attribution for the specific source.

**Citation**: Steve Tinney & Eleanor Robson, 'Oracc JSON Data: A brief introduction for programmers', *Oracc: The Open Richly Annotated Cuneiform Corpus*, Oracc, 2019 [http://oracc.museum.upenn.edu/doc/opendata/json/]

## License

MIT — see [LICENSE](LICENSE).
