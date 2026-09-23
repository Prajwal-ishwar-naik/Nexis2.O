"""
Nexis AI - Healthcare MCP Server (nexis-health-mcp)
Exposes authentic, zero-mock healthcare intelligence tools over Model Context Protocol (MCP).
Includes strict privacy redaction and mandatory emergency triage notice.
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

from health_server import (
    locate_nearby_facilities as _fetch_nearby_facilities,
    verify_medicine as _fetch_verify_medicine,
    EMERGENCY_DISCLAIMER
)

# Initialize FastMCP server
mcp = FastMCP(
    name="nexis-health-mcp",
    instructions="Provides live geospatial healthcare facility discovery via OpenStreetMap Overpass and pharmacology safety validation via NIH RxNav & OpenFDA."
)


def redact_sensitive_identifiers(text: str) -> str:
    """Redacts 12-digit Aadhaar, Korean RRN, and Japanese MyNumber patterns."""
    text = re.sub(r"\b\d{4}\s?\d{4}\s?\d{4}\b", "[Aadhaar Redacted]", text)
    text = re.sub(r"\b\d{6}-[1-4]\d{6}\b", "[ID Redacted]", text)
    text = re.sub(r"\b(MyNumber|National ID)[:\s]*\d{12}\b", r"\1: [ID Redacted]", text, flags=re.IGNORECASE)
    return text


@mcp.tool()
async def find_nearby_healthcare_facilities(
    lat: float,
    lon: float,
    radius: int = 5000,
    facility_type: str = "hospital"
) -> Dict[str, Any]:
    """
    Locate nearest authentic hospitals or pharmacies using OpenStreetMap Overpass API.
    Calculates geodesic Haversine distance, checks 24/7 casualty availability, and returns verified facility records.

    Args:
        lat: Search latitude coordinate (e.g. 12.9716)
        lon: Search longitude coordinate (e.g. 77.5946)
        radius: Search radius in meters (min 200, max 50000, default: 5000)
        facility_type: 'hospital' or 'pharmacy' (default: 'hospital')
    """
    clean_type = "pharmacy" if str(facility_type).lower() == "pharmacy" else "hospital"
    try:
        data = await _fetch_nearby_facilities(
            lat=lat,
            lon=lon,
            radius=radius,
            facility_type=clean_type
        )
        if "emergency_notice" not in data:
            data["emergency_notice"] = EMERGENCY_DISCLAIMER
        return data
    except Exception as exc:
        return {
            "status": "error",
            "service": "nexis-health-mcp",
            "search_origin": {"lat": lat, "lon": lon},
            "facility_type": clean_type,
            "error": str(exc),
            "emergency_notice": EMERGENCY_DISCLAIMER
        }


@mcp.tool()
async def verify_medicine_safety_and_precautions(
    name: str
) -> Dict[str, Any]:
    """
    Verify pharmaceutical ingredients and clinical warnings for medications.
    Queries NIH RxNav for active molecular concepts and OpenFDA for official warnings, contraindications, and indications.

    Args:
        name: Chemical or brand name of medication in English (e.g., 'Paracetamol', 'Metformin', 'Amoxicillin')
    """
    redacted_name = redact_sensitive_identifiers(name)
    try:
        data = await _fetch_verify_medicine(name=redacted_name)
        if "emergency_notice" not in data:
            data["emergency_notice"] = EMERGENCY_DISCLAIMER
        return data
    except Exception as exc:
        return {
            "status": "error",
            "service": "nexis-health-mcp",
            "medicine_query": redacted_name,
            "error": str(exc),
            "emergency_notice": EMERGENCY_DISCLAIMER
        }


if __name__ == "__main__":
    transport = "stdio"
    if "--transport" in sys.argv:
        idx = sys.argv.index("--transport")
        if idx + 1 < len(sys.argv):
            transport = sys.argv[idx + 1]
    mcp.run(transport=transport)
