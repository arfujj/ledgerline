# Using Ledgerline from Claude (MCP)

Ledgerline ships an MCP server (`src/ledgerline/mcp_server/server.py`, official `mcp` SDK v2) with five tools:

| Tool | What it does |
|---|---|
| `run_engagement` | Runs the full five-stage engagement and returns the verified executive summary, top findings and opportunities. |
| `ask_dataroom(question)` | Answers a question through the adaptive router and the grounding verifier. You get a cited answer, or "insufficient evidence". |
| `gap_check(topic?, min_severity?)` | Returns compliance gaps from the knowledge-graph analysis. |
| `size_opportunity(opportunity_id?, scenario?)` | Runs the ROI model, with tornado sensitivity for a single opportunity. |
| `diff_regulation(lineage_id, as_of?)` | Diffs the proposed and final rule, and says which version governs on a given date. |

Before you connect, run `make demo` (or at least `make dataroom corpus ingest process-db graph`) so the indexes exist. The API key comes from `.env`.

## Claude Code

```bash
claude mcp add ledgerline -- uv run --directory /absolute/path/to/ledgerline python -m ledgerline.mcp_server.server
```

## Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "ledgerline": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/ledgerline", "python", "-m", "ledgerline.mcp_server.server"]
    }
  }
}
```

## Streamable HTTP

```bash
uv run python -m ledgerline.mcp_server.server --http   # serves on :8765
```

`scripts/mcp_smoke.py` starts the server over stdio and calls two of the tools, as a real client would.
