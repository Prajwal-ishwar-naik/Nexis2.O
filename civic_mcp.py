"""
Nexis AI - Civic Welfare MCP Server (nexis-civic-mcp)
Exposes authentic, zero-mock welfare entitlement and policy intelligence tools over Model Context Protocol (MCP).
Includes strict privacy redaction guardrails against exposing Aadhaar/RRN numbers.
"""

import logging
import os
import re
import sys
from typing import Any, Dict
from fastmcp import FastMCP

# Ensure root workspace is on sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from civic_server import (
    get_civic_schemes as _fetch_civic_schemes,
    get_wiki_scheme as _fetch_wiki_scheme
)
from health_server import redact_sensitive_identifiers

# Initialize FastMCP server
mcp = FastMCP(
    name="nexis-civic-mcp",
    instructions="Provides live citizen welfare scheme evaluation against public eligibility criteria and verified policy context via MediaWiki API. Enforces strict privacy redaction."
)


def _sanitize_response(data: Any) -> Any:
    """Recursively redacts sensitive identifiers from nested dictionary/list data structures."""
    if isinstance(data, str):
        return redact_sensitive_identifiers(data)
    if isinstance(data, dict):
        return {k: _sanitize_response(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_sanitize_response(item) for item in data]
    return data


@mcp.tool()
async def assess_welfare_scheme_eligibility(
    occupation: str,
    income: float,
    category: str = "General"
) -> Dict[str, Any]:
    """
    Assess citizen parameters against public welfare scheme criteria (e.g. PM-Kisan, Ayushman Bharat PM-JAY, National Scholarships).
    Returns verified entitlement benefits, required KYC checklist with privacy redaction, and official myscheme.gov.in links.

    Args:
        occupation: Citizen's occupation (e.g. 'Farmer', 'Student', 'Artisan', 'Vendor')
        income: Annual household income in INR (e.g. 150000.0)
        category: Socio-economic category (e.g. 'General', 'OBC', 'SC', 'ST', 'BPL')
    """
    safe_occupation = redact_sensitive_identifiers(occupation)
    safe_category = redact_sensitive_identifiers(category)
    try:
        data = await _fetch_civic_schemes(
            occupation=safe_occupation,
            income=income,
            category=safe_category,
            keyword=safe_occupation
        )
        return _sanitize_response(data)
    except Exception as exc:
        return {
            "status": "error",
            "service": "nexis-civic-mcp",
            "occupation": safe_occupation,
            "income": income,
            "category": safe_category,
            "error": str(exc)
        }


@mcp.tool()
async def get_scheme_historical_summary(
    scheme_name: str
) -> Dict[str, Any]:
    """
    Retrieve verified historical context, nodal ministry, and policy objectives for government initiatives from Wikipedia MediaWiki API.
    Returns canonical page URLs and structured summaries.

    Args:
        scheme_name: Name of the government scheme or initiative (e.g. 'PM-KISAN', 'Ayushman Bharat', 'Pradhan Mantri Awas Yojana')
    """
    safe_scheme = redact_sensitive_identifiers(scheme_name)
    try:
        data = await _fetch_wiki_scheme(scheme_name=safe_scheme)
        return _sanitize_response(data)
    except Exception as exc:
        return {
            "status": "error",
            "service": "nexis-civic-mcp",
            "scheme_name": safe_scheme,
            "error": str(exc)
        }


if __name__ == "__main__":
    transport = "stdio"
    if "--transport" in sys.argv:
        idx = sys.argv.index("--transport")
        if idx + 1 < len(sys.argv):
            transport = sys.argv[idx + 1]
    mcp.run(transport=transport)
