"""
Nexis AI - Education MCP Server (nexis-edu-mcp)
Exposes authentic, zero-mock educational and research tools over Model Context Protocol (MCP).
Covers arXiv, OpenLibrary, Socratic tutoring, YouTube tutorial discovery, and Tavily live web citations.
"""

import logging
import os
import sys
from typing import Any, Dict
from fastmcp import FastMCP

# Ensure root workspace is on sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from edu_server import (
    academic_search as _fetch_academic_search,
    teach_concept as _fetch_teach_concept,
    search_youtube_videos as _fetch_youtube_videos,
    live_web_search as _fetch_web_search,
    TeachRequest
)

# Initialize FastMCP server
mcp = FastMCP(
    name="nexis-edu-mcp",
    instructions="Provides live academic paper/textbook search via arXiv/OpenLibrary, 4-step Socratic teaching, authentic YouTube demonstration discovery, and live web citations via Tavily."
)


@mcp.tool()
async def search_academic_literature(
    topic: str,
    limit: int = 5
) -> Dict[str, Any]:
    """
    Search authentic academic literature concurrently across arXiv and OpenLibrary.
    Retrieves peer-reviewed papers, open-access preprints, academic textbooks, and verified author information.

    Args:
        topic: Academic topic, scientific concept, or algorithm name (e.g. 'Dijkstra algorithm', 'Quantum Computing')
        limit: Maximum results per catalog to retrieve (default: 5)
    """
    try:
        data = await _fetch_academic_search(topic=topic, limit=limit)
        return data
    except Exception as exc:
        return {
            "status": "error",
            "service": "nexis-edu-mcp",
            "topic": topic,
            "error": str(exc)
        }


@mcp.tool()
async def explain_concept_socratically(
    concept: str,
    level: str = "Undergraduate"
) -> Dict[str, Any]:
    """
    Generate a rigorous 4-step Socratic teaching module:
    1. Core Intuition
    2. Technical Breakdown
    3. Worked Example
    4. Practice Check with verified solutions.

    Args:
        concept: Educational topic or concept to explain
        level: Target pedagogical level ('Beginner', 'Undergraduate', 'Advanced')
    """
    valid_levels = ["Beginner", "Undergraduate", "Advanced"]
    clean_level = level if level in valid_levels else "Undergraduate"
    req = TeachRequest(concept=concept, level=clean_level)
    try:
        data = await _fetch_teach_concept(req=req)
        return data
    except Exception as exc:
        return {
            "status": "error",
            "service": "nexis-edu-mcp",
            "concept": concept,
            "level": clean_level,
            "error": str(exc)
        }


@mcp.tool()
async def search_youtube_tutorials(
    query: str,
    max_results: int = 3
) -> Dict[str, Any]:
    """
    Discover authentic, verified YouTube tutorial and demonstration video links.
    Returns direct watch links (https://www.youtube.com/watch?v=...), channel names, and video descriptions.
    Strictly zero dummy or mock video IDs.

    Args:
        query: Search term for visual tutorial or procedure (e.g. 'Dijkstra shortest path demonstration')
        max_results: Maximum videos to return (default: 3)
    """
    try:
        data = await _fetch_youtube_videos(query=query, max_results=max_results)
        return data
    except Exception as exc:
        return {
            "status": "error",
            "service": "nexis-edu-mcp",
            "query": query,
            "error": str(exc)
        }


@mcp.tool()
async def search_web_citations(
    query: str,
    max_results: int = 4
) -> Dict[str, Any]:
    """
    Execute live web search for verified citations, official portal links, and documentation via Tavily.
    Returns clean extracts and direct source URLs.

    Args:
        query: Search query for factual documentation, portal links, or news
        max_results: Maximum citations to return (default: 4)
    """
    try:
        data = await _fetch_web_search(query=query, max_results=max_results)
        return data
    except Exception as exc:
        return {
            "status": "error",
            "service": "nexis-edu-mcp",
            "query": query,
            "error": str(exc)
        }


if __name__ == "__main__":
    transport = "stdio"
    if "--transport" in sys.argv:
        idx = sys.argv.index("--transport")
        if idx + 1 < len(sys.argv):
            transport = sys.argv[idx + 1]
    mcp.run(transport=transport)
