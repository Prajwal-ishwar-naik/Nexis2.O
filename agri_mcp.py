"""
Nexis AI - Agriculture MCP Server (nexis-agri-mcp)
Exposes authentic, zero-mock agricultural intelligence tools over Model Context Protocol (MCP).
Supports stdio and Streamable HTTP transports.
"""

import logging
import os
import sys
from typing import Any, Dict, Optional
from fastmcp import FastMCP

# Ensure root workspace is on sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from agri_server import get_mandi_prices as _fetch_mandi_prices
from agri_server import get_agri_weather as _fetch_agri_weather

# Initialize FastMCP server
mcp = FastMCP(
    name="nexis-agri-mcp",
    instructions="Provides live commodity mandi prices via Agmarknet and real-time agricultural weather and spray/irrigation advisories via Open-Meteo."
)


@mcp.tool()
async def get_agri_mandi_prices(
    commodity: str,
    state: str = "Karnataka",
    limit: int = 10
) -> Dict[str, Any]:
    """
    Retrieve live wholesale commodity mandi prices from official Data.gov.in Agmarknet API.
    Computes authentic distribution statistics including min, max, average modal price, and active markets.

    Args:
        commodity: Name of crop/commodity (e.g. Tomato, Onion, Potato, Rice, Wheat, Cotton)
        state: Indian state name (default: 'Karnataka')
        limit: Maximum number of market records to return (default: 10)
    """
    try:
        data = await _fetch_mandi_prices(commodity=commodity, state=state, limit=limit)
        return data
    except Exception as exc:
        return {
            "status": "error",
            "service": "nexis-agri-mcp",
            "commodity": commodity,
            "state": state,
            "error": str(exc)
        }


@mcp.tool()
async def get_agri_weather_and_advisories(
    lat: float,
    lon: float
) -> Dict[str, Any]:
    """
    Retrieve live agricultural weather metrics from Open-Meteo and compute operational farming advisories.
    Calculates operational windows for irrigation, chemical/fertilizer spraying, and precipitation alerts.

    Args:
        lat: Farmland latitude coordinate (e.g. 12.9716)
        lon: Farmland longitude coordinate (e.g. 77.5946)
    """
    try:
        data = await _fetch_agri_weather(lat=lat, lon=lon)
        return data
    except Exception as exc:
        return {
            "status": "error",
            "service": "nexis-agri-mcp",
            "coordinates": {"lat": lat, "lon": lon},
            "error": str(exc)
        }


if __name__ == "__main__":
    # Support both stdio (default) and streamable-http if transport flag is passed
    transport = "stdio"
    if "--transport" in sys.argv:
        idx = sys.argv.index("--transport")
        if idx + 1 < len(sys.argv):
            transport = sys.argv[idx + 1]
    mcp.run(transport=transport)
