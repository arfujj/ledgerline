"""Spawn the Ledgerline MCP server over stdio and call two tools as a real MCP client would."""

from __future__ import annotations

import asyncio
import json
import os
import sys

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def main() -> int:
    params = StdioServerParameters(command=sys.executable,
                                   args=["-m", "ledgerline.mcp_server.server"],
                                   env={**os.environ})
    async with stdio_client(params) as (read, write), ClientSession(read, write) as s:
        await s.initialize()
        tools = await s.list_tools()
        print("tools:", sorted(t.name for t in tools.tools))
        r = await s.call_tool("gap_check", {"min_severity": "critical"})
        print("gap_check:", json.dumps(r.structured_content or {}, default=str)[:300])
        r = await s.call_tool("size_opportunity", {"opportunity_id": "OPP-RECON-MATCH"})
        print("size_opportunity:", (r.content[0].text if r.content else "")[:300])
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
