"""
Nexis AI - Unified MCP Hub (nexis-unified-mcp)
Merges all sector-specific tools (Agri, Health, Edu, Civic) into a single unified Model Context Protocol server.
Compatible with stdio transport (Claude Desktop, Cursor, Cline) and Streamable HTTP.
"""

import logging
import os
import sys
from fastmcp import FastMCP

# Ensure root workspace is on sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Import individual MCP servers
from agri_mcp import mcp as agri_mcp
from health_mcp import mcp as health_mcp
from edu_mcp import mcp as edu_mcp
from civic_mcp import mcp as civic_mcp

# Initialize Unified FastMCP Hub
unified_mcp = FastMCP(
    name="nexis-unified-mcp",
    instructions=(
        "Nexis AI Unified Intelligence Runtime. Provides authentic, zero-mock tools across "
        "Agriculture (Agmarknet mandi prices & weather), Healthcare (OSM facility locator & pharmacology safety), "
        "Education (arXiv/OpenLibrary academic search, Socratic tutoring, YouTube tutorials, Tavily live web citations), "
        "and Civic Welfare (Welfare entitlement assessment & MediaWiki policy summaries)."
    )
)

# Mount all child sector MCP servers without namespace so tools keep clean names
unified_mcp.mount(agri_mcp)
unified_mcp.mount(health_mcp)
unified_mcp.mount(edu_mcp)
unified_mcp.mount(civic_mcp)


if __name__ == "__main__":
    transport = "stdio"
    if "--transport" in sys.argv:
        idx = sys.argv.index("--transport")
        if idx + 1 < len(sys.argv):
            transport = sys.argv[idx + 1]
    unified_mcp.run(transport=transport)
