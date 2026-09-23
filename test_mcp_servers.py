"""
Automated Test Suite for Nexis AI Model Context Protocol (MCP) Layer.
Tests standalone MCP servers and the unified bundle:
- Tool listing across all 4 domains (Agri, Health, Edu, Civic)
- Zero-mock live execution of tools via FastMCP
- Strict privacy redaction guardrails for government IDs
"""

import asyncio
import json
import pytest
from fastmcp import FastMCP

from agri_mcp import mcp as agri_mcp
from health_mcp import mcp as health_mcp
from edu_mcp import mcp as edu_mcp
from civic_mcp import mcp as civic_mcp
from nexis_mcp_bundle import unified_mcp


def _extract_content_json(tool_result) -> dict:
    """Helper to extract parsed JSON dictionary from FastMCP ToolResult."""
    if hasattr(tool_result, "content") and tool_result.content:
        first_item = tool_result.content[0]
        text_val = getattr(first_item, "text", "")
        try:
            return json.loads(text_val)
        except Exception:
            return {"raw_text": text_val}
    if hasattr(tool_result, "structured_content") and tool_result.structured_content:
        return tool_result.structured_content
    return {}


@pytest.mark.asyncio
async def test_mcp_servers_tool_registry():
    """Verify that the unified MCP hub aggregates all 10 expected tools across domains."""
    tools = await unified_mcp.list_tools()
    tool_names = [t.name for t in tools]

    expected_tools = [
        "get_agri_mandi_prices",
        "get_agri_weather_and_advisories",
        "find_nearby_healthcare_facilities",
        "verify_medicine_safety_and_precautions",
        "search_academic_literature",
        "explain_concept_socratically",
        "search_youtube_tutorials",
        "search_web_citations",
        "assess_welfare_scheme_eligibility",
        "get_scheme_historical_summary"
    ]

    for tool in expected_tools:
        assert tool in tool_names, f"Expected tool '{tool}' not found in unified MCP catalog: {tool_names}"


@pytest.mark.asyncio
async def test_mcp_agri_weather_tool_live():
    """Verify live weather and agricultural advisory tool execution via MCP."""
    res = await agri_mcp.call_tool("get_agri_weather_and_advisories", {"lat": 12.9716, "lon": 77.5946})
    assert not res.is_error, "Agri weather tool returned an error"
    data = _extract_content_json(res)
    assert data.get("status") == "success"
    assert "agricultural_advisories" in data
    assert "irrigation" in data["agricultural_advisories"]
    assert "chemical_spraying_window" in data["agricultural_advisories"]


@pytest.mark.asyncio
async def test_mcp_agri_mandi_tool_live():
    """Verify live mandi commodity prices tool execution via MCP."""
    res = await agri_mcp.call_tool("get_agri_mandi_prices", {"commodity": "Tomato", "state": "Karnataka", "limit": 3})
    assert not res.is_error
    data = _extract_content_json(res)
    assert data.get("status") == "success"
    assert "statistics" in data
    assert "records" in data


@pytest.mark.asyncio
async def test_mcp_health_medicine_tool_live():
    """Verify live pharmacology and clinical monograph tool execution via MCP."""
    res = await health_mcp.call_tool("verify_medicine_safety_and_precautions", {"name": "Metformin"})
    assert not res.is_error
    data = _extract_content_json(res)
    assert data.get("status") == "success"
    assert "nih_rxnav" in data
    assert "emergency_notice" in data
    assert "Dial 108" in data["emergency_notice"]


@pytest.mark.asyncio
async def test_mcp_health_facility_tool_live():
    """Verify live OSM Overpass hospital discovery tool via MCP."""
    res = await health_mcp.call_tool("find_nearby_healthcare_facilities", {
        "lat": 12.9716,
        "lon": 77.5946,
        "radius": 1500,
        "facility_type": "pharmacy"
    })
    assert not res.is_error
    data = _extract_content_json(res)
    assert data.get("status") in ["success", "empty"]
    assert "emergency_notice" in data


@pytest.mark.asyncio
async def test_mcp_edu_academic_search_tool_live():
    """Verify live academic search across arXiv & OpenLibrary via MCP."""
    res = await edu_mcp.call_tool("search_academic_literature", {"topic": "graph algorithms", "limit": 2})
    assert not res.is_error
    data = _extract_content_json(res)
    assert data.get("status") in ["success", "empty"]
    assert "textbooks" in data
    assert "research_papers" in data


@pytest.mark.asyncio
async def test_mcp_edu_youtube_tool_live():
    """Verify live YouTube tutorial discovery via MCP."""
    res = await edu_mcp.call_tool("search_youtube_tutorials", {"query": "sorting algorithms tutorial", "max_results": 2})
    assert not res.is_error
    data = _extract_content_json(res)
    assert data.get("status") == "success"
    assert "videos" in data
    if data.get("videos"):
        first_video = data["videos"][0]
        assert first_video["url"].startswith("https://www.youtube.com/watch?v=")


@pytest.mark.asyncio
async def test_mcp_civic_welfare_eligibility_tool_live():
    """Verify civic welfare scheme assessment via MCP."""
    res = await civic_mcp.call_tool("assess_welfare_scheme_eligibility", {
        "occupation": "Farmer",
        "income": 120000.0,
        "category": "General"
    })
    assert not res.is_error
    data = _extract_content_json(res)
    assert data.get("status") == "success"
    assert "schemes" in data
    assert len(data["schemes"]) > 0


@pytest.mark.asyncio
async def test_mcp_civic_wiki_scheme_tool_live():
    """Verify MediaWiki historical scheme summary tool via MCP."""
    res = await civic_mcp.call_tool("get_scheme_historical_summary", {
        "scheme_name": "Pradhan Mantri Kisan Samman Nidhi"
    })
    assert not res.is_error
    data = _extract_content_json(res)
    assert data.get("status") == "success"
    assert "url" in data
    assert "https://en.wikipedia.org/wiki/" in data["url"]


@pytest.mark.asyncio
async def test_mcp_privacy_redaction_guardrails():
    """Ensure MCP tools redact sensitive 12-digit national IDs (Aadhaar/RRN)."""
    leaked_aadhaar = "9876 5432 1098"
    leaked_rrn = "990101-1234567"

    # Test in medicine query
    res = await health_mcp.call_tool("verify_medicine_safety_and_precautions", {
        "name": f"Aspirin for patient with ID {leaked_aadhaar}"
    })
    data = _extract_content_json(res)
    raw_str = json.dumps(data)
    assert leaked_aadhaar not in raw_str, "Raw Aadhaar digits leaked through health MCP tool"

    # Test in civic scheme eligibility assessment
    res_civic = await civic_mcp.call_tool("assess_welfare_scheme_eligibility", {
        "occupation": f"Worker with Aadhaar {leaked_aadhaar} and RRN {leaked_rrn}",
        "income": 90000.0,
        "category": "General"
    })
    data_civic = _extract_content_json(res_civic)
    raw_civic_str = json.dumps(data_civic)
    assert leaked_aadhaar not in raw_civic_str, "Raw Aadhaar leaked through civic MCP tool"
    assert leaked_rrn not in raw_civic_str, "Raw RRN leaked through civic MCP tool"
    assert "[Aadhaar Redacted]" in raw_civic_str or "[ID Redacted]" in raw_civic_str
