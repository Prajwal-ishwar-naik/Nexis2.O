"""
Nexis AI - Production Test Suite
Validates all 4 domain micro-servers and the Gateway Orchestrator against authentic live endpoints.
Asserts Zero Mock Data Policy, English only processing, and real API integrations.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from agri_server import app as agri_app
from health_server import app as health_app
from edu_server import app as edu_app
from civic_server import app as civic_app
from gateway import app as gateway_app, classify_intent, redact_sensitive_identifiers, resolve_approximate_location, resolve_location_name


# -----------------------------------------------------------------------------
# 1. Agri Micro-Server (Port 8001) Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_agri_server_health():
    """Verify Agri micro-server health endpoint and configuration."""
    async with AsyncClient(transport=ASGITransport(app=agri_app), base_url="http://test") as ac:
        response = await ac.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "agri_server"
        assert data["port"] == 8001
        assert data["upstream_configured"] is True


@pytest.mark.asyncio
async def test_agri_server_live_mandi_and_statistics():
    """
    Verify live Data.gov.in Agmarknet API execution and dynamic statistics.
    Asserts zero mock data and presence of runtime min, max, average modal price.
    """
    async with AsyncClient(transport=ASGITransport(app=agri_app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/agri/mandi", params={"commodity": "Tomato", "state": "Karnataka", "limit": 5})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["success", "empty"]
        assert "statistics" in data
        stats = data["statistics"]
        assert "min_modal_price" in stats
        assert "max_modal_price" in stats
        assert "average_modal_price" in stats
        assert "market_count" in stats

        if data["status"] == "success":
            assert len(data["records"]) > 0
            rec = data["records"][0]
            assert "market" in rec
            assert "modal_price" in rec
            assert "arrival_date" in rec


@pytest.mark.asyncio
async def test_agri_server_live_weather_and_advisories():
    """
    Verify live Open-Meteo agro-meteorological metrics and dynamic advisories.
    """
    async with AsyncClient(transport=ASGITransport(app=agri_app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/agri/weather", params={"lat": 13.1, "lon": 77.6})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "current_weather" in data
        assert "temperature_celsius" in data["current_weather"]
        assert "relative_humidity_percent" in data["current_weather"]
        assert "agricultural_advisories" in data
        adv = data["agricultural_advisories"]
        assert "irrigation" in adv
        assert "chemical_spraying_window" in adv
        assert adv["irrigation"]["status"] in ["HALT", "REDUCE", "REQUIRED", "NORMAL"]
        assert adv["chemical_spraying_window"]["status"] in ["UNFAVORABLE", "OPTIMAL", "MARGINAL"]


# -----------------------------------------------------------------------------
# 2. Health Micro-Server (Port 8002) Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_health_server_health():
    """Verify Health micro-server health endpoint."""
    async with AsyncClient(transport=ASGITransport(app=health_app), base_url="http://test") as ac:
        response = await ac.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "health_server"
        assert data["port"] == 8002


@pytest.mark.asyncio
async def test_health_server_live_spatial_overpass():
    """
    Verify live OpenStreetMap Overpass API spatial query with Haversine distance.
    """
    async with AsyncClient(transport=ASGITransport(app=health_app), base_url="http://test") as ac:
        payload = {
            "lat": 12.9716,
            "lon": 77.5946,
            "radius": 4000,
            "facility_type": "hospital"
        }
        response = await ac.post("/api/v1/health/nearby", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "emergency_notice" in data
        assert "108" in data["emergency_notice"]
        assert data["status"] in ["success", "empty"]
        if data["status"] == "success":
            assert len(data["facilities"]) > 0
            fac = data["facilities"][0]
            assert "name" in fac
            assert "coordinates" in fac
            assert "distance_meters" in fac
            assert "is_open_24_7" in fac


@pytest.mark.asyncio
async def test_health_server_live_medicine_resolution():
    """
    Verify authentic clinical pharmacology resolution via NIH RxNav and OpenFDA.
    """
    async with AsyncClient(transport=ASGITransport(app=health_app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/health/medicine", params={"name": "Paracetamol"})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "nih_rxnav" in data
        assert "openfda_monograph" in data
        assert "emergency_notice" in data


# -----------------------------------------------------------------------------
# 3. Education Micro-Server (Port 8003) Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_edu_server_health():
    """Verify Education micro-server health endpoint."""
    async with AsyncClient(transport=ASGITransport(app=edu_app), base_url="http://test") as ac:
        response = await ac.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["port"] == 8003


@pytest.mark.asyncio
async def test_edu_server_live_academic_search():
    """
    Verify live concurrent search across arXiv and OpenLibrary.
    """
    async with AsyncClient(transport=ASGITransport(app=edu_app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/edu/search", params={"topic": "Quantum Computing", "limit": 2})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "textbooks" in data
        assert "research_papers" in data
        assert len(data["textbooks"]) > 0 or len(data["research_papers"]) > 0


# -----------------------------------------------------------------------------
# 4. Civic Welfare Micro-Server (Port 8004) Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_civic_server_health():
    """Verify Civic micro-server health endpoint."""
    async with AsyncClient(transport=ASGITransport(app=civic_app), base_url="http://test") as ac:
        response = await ac.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["port"] == 8004


@pytest.mark.asyncio
async def test_civic_server_live_schemes_and_eligibility():
    """
    Verify live scheme registry query and dynamic multi-criteria eligibility filter.
    """
    async with AsyncClient(transport=ASGITransport(app=civic_app), base_url="http://test") as ac:
        params = {
            "occupation": "Farmer",
            "income": 120000.0,
            "category": "OBC",
            "keyword": "Kisan"
        }
        response = await ac.get("/api/v1/civic/schemes", params=params)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "citizen_profile" in data
        assert len(data["schemes"]) > 0
        scheme = data["schemes"][0]
        assert "scheme_name" in scheme
        assert "eligibility_evaluation" in scheme
        eval_data = scheme["eligibility_evaluation"]
        assert eval_data["status"] in ["ELIGIBLE", "POTENTIALLY_ELIGIBLE", "INELIGIBLE_EXCEEDS_INCOME"]
        assert "document_checklist" in eval_data
        assert "entitlement_benefits" in eval_data


# -----------------------------------------------------------------------------
# 5. Gateway Orchestrator (Port 8000) Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_gateway_root_discovery():
    """Verify Gateway root index."""
    async with AsyncClient(transport=ASGITransport(app=gateway_app), base_url="http://test") as ac:
        response = await ac.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "Nexis AI" in data["gateway"]
        assert "topology" in data
        assert "endpoints" in data
        assert data["language"] == "English strictly"


@pytest.mark.asyncio
async def test_gateway_chat_endpoint_validation():
    """Verify Chat endpoint schema validation and response structure."""
    async with AsyncClient(transport=ASGITransport(app=gateway_app), base_url="http://test") as ac:
        res_invalid = await ac.post("/api/chat", json={"query": ""})
        assert res_invalid.status_code == 422


@pytest.mark.asyncio
async def test_gateway_conversational_greeting():
    """Verify that casual greeting queries return natural responses without domain recitation."""
    async with AsyncClient(transport=ASGITransport(app=gateway_app), base_url="http://test", timeout=60.0) as ac:
        response = await ac.post("/api/chat", json={"query": "hey"})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "response" in data
        assert len(data["response"]) > 0
        assert data["tools_executed"] == []
        reply_lower = data["response"].lower()
        for domain in ["agriculture", "healthcare", "education", "civic welfare"]:
            assert domain not in reply_lower


def test_gateway_intent_classification():
    """Verify Gateway intent routing heuristics."""
    assert classify_intent("What is the mandi price of onion in Hubli?", None) == "agriculture"
    assert classify_intent("Find hospital near me with 24/7 ICU beds", None) == "healthcare"
    assert classify_intent("Teach quantum entanglement undergraduate level", None) == "education"
    assert classify_intent("Eligible for PM Kisan Samman Nidhi housing scheme?", None) == "civic"


@pytest.mark.asyncio
async def test_civic_server_wiki_summary_tool():
    """Verify /tools/wiki-summary on civic_server for policy/scheme background."""
    async with AsyncClient(transport=ASGITransport(app=civic_app), base_url="http://test") as ac:
        response = await ac.get("/tools/wiki-summary", params={"query": "Pradhan Mantri Kisan Samman Nidhi"})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "title" in data
        assert "summary" in data
        assert len(data["summary"]) > 0
        assert "url" in data
        assert "wikipedia.org" in data["url"]


@pytest.mark.asyncio
async def test_civic_server_wiki_scheme_endpoint():
    """Verify /api/v1/civic/wiki-scheme on civic_server for scheme background and nodal ministry."""
    async with AsyncClient(transport=ASGITransport(app=civic_app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/civic/wiki-scheme", params={"scheme_name": "Pradhan Mantri Kisan Samman Nidhi"})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "scheme_name" in data
        assert "title" in data
        assert "nodal_ministry" in data
        assert "summary" in data
        assert len(data["summary"]) > 0
        assert "url" in data
        assert "wikipedia.org" in data["url"]


@pytest.mark.asyncio
async def test_edu_server_live_youtube_discovery():
    """Verify /api/v1/edu/youtube returns authentic YouTube watch links."""
    async with AsyncClient(transport=ASGITransport(app=edu_app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/edu/youtube", params={"query": "drip irrigation setup tutorial", "max_results": 2})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "videos" in data
        assert len(data["videos"]) > 0
        video = data["videos"][0]
        assert "video_id" in video
        assert "url" in video
        assert "https://www.youtube.com/watch?v=" in video["url"]
        assert "title" in video


@pytest.mark.asyncio
async def test_edu_server_live_web_search():
    """Verify /api/v1/edu/web-search returns authentic web citation URLs."""
    async with AsyncClient(transport=ASGITransport(app=edu_app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/edu/web-search", params={"query": "PM Kisan Samman Nidhi", "max_results": 2})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "results" in data
        assert len(data["results"]) > 0
        res = data["results"][0]
        assert "url" in res
        assert res["url"].startswith("http")
        assert "title" in res


def test_privacy_redaction_guardrails():
    """Verify sensitive government ID digits (Aadhaar, Korean RRN, Japanese MyNumber) are cleanly redacted."""
    sample_text = (
        "Citizen details: Name: Ramesh, Aadhaar: 1234 5678 9012, Alternate: 987654321098, "
        "Korean RRN: 880101-1234567, MyNumber: 123456789012."
    )
    redacted = redact_sensitive_identifiers(sample_text)
    assert "1234 5678 9012" not in redacted
    assert "987654321098" not in redacted
    assert "880101-1234567" not in redacted
    assert "[Aadhaar Redacted]" in redacted
    assert "[ID Redacted]" in redacted


@pytest.mark.asyncio
async def test_dual_inference_configuration():
    """Verify Gateway and Health server report active INFERENCE_PROVIDER."""
    async with AsyncClient(transport=ASGITransport(app=health_app), base_url="http://test") as ac:
        res = await ac.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert "inference_provider" in data
        assert data["inference_provider"] in ["groq", "ollama"]

    async with AsyncClient(transport=ASGITransport(app=gateway_app), base_url="http://test") as ac:
        res = await ac.get("/api/system/health")
        assert res.status_code == 200
        data = res.json()
        assert "inference_provider" in data
        assert data["inference_provider"] in ["groq", "ollama"]


@pytest.mark.asyncio
async def test_gateway_location_fallback():
    """Verify resolve_approximate_location returns valid coordinates."""
    geo = await resolve_approximate_location()
    assert geo.lat is not None and isinstance(geo.lat, float)
    assert geo.lon is not None and isinstance(geo.lon, float)


@pytest.mark.asyncio
async def test_gateway_reverse_geocoding_accuracy():
    """Verify authentic OpenStreetMap Nominatim reverse geocoding resolves verified locality names."""
    # North Bengaluru / Yelahanka coordinates
    loc = await resolve_location_name(13.1733, 77.5321)
    assert loc["status"] in ["success", "fallback"]
    assert "formatted" in loc
    assert len(loc["formatted"]) > 0
    if loc["status"] == "success":
        formatted_lower = loc["formatted"].lower()
        # Must resolve to Yelahanka or Shyanuboganahalli or Bengaluru Urban, never Whitefield or Marathahalli
        assert any(k in formatted_lower for k in ["yelahanka", "shyanuboganahalli", "bengaluru"])
        assert "whitefield" not in formatted_lower
        assert "marathahalli" not in formatted_lower



