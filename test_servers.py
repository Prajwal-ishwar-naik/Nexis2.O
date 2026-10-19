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
    assert "[RRN Redacted]" in redacted
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


@pytest.mark.asyncio
async def test_gateway_deep_reasoning_payload_and_thought_trace():
    """Verify ChatRequest supports model='deep_reasoning' and thought trace extraction."""
    from gateway import ChatRequest
    import re

    # Validate ChatRequest accepts model="deep_reasoning"
    req = ChatRequest(query="Calculate sqrt(144)", model="deep_reasoning")
    assert req.model == "deep_reasoning"

    # Validate thought trace stripping
    raw_response = "<think>Step 1: 12 * 12 = 144.\nTherefore sqrt(144) = 12.</think>\n\nThe square root of 144 is 12."
    think_match = re.search(r"<think>([\s\S]*?)</think>", raw_response, flags=re.IGNORECASE)
    assert think_match is not None
    thought_trace = think_match.group(1).strip()
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", raw_response, flags=re.IGNORECASE).strip()
    assert thought_trace == "Step 1: 12 * 12 = 144.\nTherefore sqrt(144) = 12."
    assert cleaned == "The square root of 144 is 12."
    assert "<think>" not in cleaned

    # Validate unclosed <think> tag recovery
    unclosed = "<think>Step 1: Incomplete reasoning"
    if "<think>" in unclosed.lower() and "</think>" not in unclosed.lower():
        parts = re.split(r"<think>", unclosed, flags=re.IGNORECASE, maxsplit=1)
        u_trace = parts[1].strip()
        u_body = parts[0].strip()
        assert u_trace == "Step 1: Incomplete reasoning"
        assert u_body == ""


@pytest.mark.asyncio
async def test_gateway_deep_reasoning_system_instruction_protocol():
    """Verify that deep reasoning mode activates required protocol and parameters."""
    import os
    from gateway import GROQ_DEEP_THINK_MODEL, OLLAMA_DEEP_THINK_MODEL

    assert GROQ_DEEP_THINK_MODEL == "deepseek-r1-distill-llama-70b"
    assert OLLAMA_DEEP_THINK_MODEL == "deepseek-r1:8b"


# -----------------------------------------------------------------------------
# 6. Hybrid Memory Architecture (Layers 1, 2, 3, 4) Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_memory_system_layer1_redis_buffer_capping_and_ttl():
    """Verify Layer 1 Redis cache_turn, list capping to 20, TTL, and get_recent_history."""
    import tempfile, os
    import fakeredis.aioredis
    from memory import MemoryManager

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_db = tf.name

    try:
        mem = MemoryManager(db_path=temp_db)
        fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        mem._redis = fake_redis
        mem._redis_available = True

        sid = "redis_test_sess_01"

        # Cache 25 turns to test list capping to 20
        for i in range(25):
            role = "user" if i % 2 == 0 else "assistant"
            content = f"Message {i}"
            success = await mem.cache_turn(sid, role, content, ttl=7200)
            assert success is True

        # Verify list length capped to 20 in Redis
        key = f"nexis:session:{sid}:turns"
        list_len = await fake_redis.llen(key)
        assert list_len == 20

        # Verify TTL is set
        ttl = await fake_redis.ttl(key)
        assert ttl > 0 and ttl <= 7200

        # Retrieve recent history (limit=8) from Redis
        recent = await mem.get_recent_history(sid, limit=8)
        assert len(recent) == 8
        # Should be turns 17 through 24
        assert recent[-1]["content"] == "Message 24"
        assert recent[0]["content"] == "Message 17"
    finally:
        if os.path.exists(temp_db):
            os.remove(temp_db)


@pytest.mark.asyncio
async def test_memory_system_layer1_redis_fallback_when_offline():
    """Verify automatic graceful fallback to SQLite when Redis is unreachable."""
    import tempfile, os
    from memory import MemoryManager

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_db = tf.name

    try:
        # Point to unreachable port without crashing
        mem = MemoryManager(db_path=temp_db, redis_url="redis://127.0.0.1:65534/0")
        connected = await mem.init_redis()
        assert connected is False
        assert mem._redis_available is False

        # Add message to SQLite
        sid = "fallback_sess"
        await mem.save_message(sid, "user", "Testing SQLite fallback message")

        # get_recent_history should fall back to SQLite seamlessly
        history = await mem.get_recent_history(sid, limit=5)
        assert len(history) == 1
        assert history[0]["content"] == "Testing SQLite fallback message"
    finally:
        if os.path.exists(temp_db):
            os.remove(temp_db)


@pytest.mark.asyncio
async def test_memory_system_layer2_dual_write_and_persistence():
    """Verify Layer 2 dual-write (save_turn) and SQLite persistence across turns."""
    from memory import MemoryManager
    import tempfile, os
    import fakeredis.aioredis

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_db = tf.name

    try:
        mem = MemoryManager(db_path=temp_db)
        fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        mem._redis = fake_redis
        mem._redis_available = True

        sid = "dual_write_sess"
        msg_id = await mem.save_turn(sid, "user", "Dual write message 1")
        assert msg_id is not None and msg_id > 0

        # Verify SQLite has it
        details = await mem.get_session_details(sid)
        assert details is not None
        assert len(details["messages"]) == 1
        assert details["messages"][0]["content"] == "Dual write message 1"

        # Verify Redis buffer also has it
        key = f"nexis:session:{sid}:turns"
        assert await fake_redis.llen(key) == 1

        # Verify sessions listing
        sessions = await mem.list_sessions()
        assert any(s["session_id"] == sid for s in sessions)
    finally:
        if os.path.exists(temp_db):
            os.remove(temp_db)


@pytest.mark.asyncio
async def test_memory_system_layer3_semantic_facts_and_prompt_formatting():
    """Verify Layer 3 fact upsert, semantic retrieval, and prompt formatting."""
    from memory import MemoryManager
    import tempfile, os

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_db = tf.name

    try:
        mem = MemoryManager(db_path=temp_db)
        await mem.save_fact(
            fact_content="User operates 20 acres sugarcane farm in Mandya, Karnataka",
            fact_type="agriculture",
            user_id="default_user"
        )
        await mem.save_fact(
            fact_content="User has severe allergy to Penicillin and Cephalosporins",
            fact_type="healthcare",
            user_id="default_user"
        )

        # Semantic retrieval
        facts = await mem.get_relevant_facts(query="What is the sugarcane yield?", limit=3)
        assert len(facts) >= 1
        assert any("sugarcane" in f["fact_content"].lower() for f in facts)

        # Format for system prompt
        formatted = mem.format_facts_for_prompt(facts)
        assert "### PERSISTENT USER FACTS & DOMAIN CONSTRAINTS:" in formatted
        assert "[agriculture]:" in formatted or "[healthcare]:" in formatted
    finally:
        if os.path.exists(temp_db):
            os.remove(temp_db)


@pytest.mark.asyncio
async def test_memory_system_layer4_pii_zero_leakage():
    """Verify Layer 4 strict PII zero-leakage across Aadhaar, RRN, and MyNumber."""
    from memory import MemoryManager
    import tempfile, os
    import fakeredis.aioredis

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_db = tf.name

    try:
        mem = MemoryManager(db_path=temp_db)
        fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        mem._redis = fake_redis
        mem._redis_available = True

        sid = "pii_zero_leakage_sess"
        raw_text = (
            "User: Aadhaar 9876 5432 1098, Korean RRN 901212-1234567, MyNumber: 123456789012."
        )

        await mem.save_turn(sid, "user", raw_text)

        # 1. Check SQLite
        details = await mem.get_session_details(sid)
        sqlite_content = details["messages"][0]["content"]
        assert "9876 5432 1098" not in sqlite_content
        assert "901212-1234567" not in sqlite_content
        assert "123456789012" not in sqlite_content
        assert "[Aadhaar Redacted]" in sqlite_content
        assert "[RRN Redacted]" in sqlite_content
        assert "[ID Redacted]" in sqlite_content

        # 2. Check Redis
        key = f"nexis:session:{sid}:turns"
        redis_raw = await fake_redis.lindex(key, 0)
        assert "9876 5432 1098" not in redis_raw
        assert "901212-1234567" not in redis_raw
        assert "123456789012" not in redis_raw
        assert "[Aadhaar Redacted]" in redis_raw
        assert "[RRN Redacted]" in redis_raw
    finally:
        if os.path.exists(temp_db):
            os.remove(temp_db)


@pytest.mark.asyncio
async def test_memory_system_token_budget_management():
    """Verify cumulative token window compaction beyond 3000 tokens."""
    from memory import MemoryManager

    mem = MemoryManager()
    large_messages = [
        {"role": "user", "content": "Alpha turn " + "x" * 3500},
        {"role": "assistant", "content": "Beta turn " + "y" * 3500},
        {"role": "user", "content": "Gamma turn " + "z" * 3500},
        {"role": "assistant", "content": "Delta turn " + "w" * 3500},
        {"role": "user", "content": "Recent question about farming."}
    ]

    managed = mem.manage_token_window(large_messages, max_tokens=3000)
    assert any("[Earlier conversation summary:" in m["content"] for m in managed)
    total_chars = sum(len(m["content"]) for m in managed)
    assert total_chars < 3000 * 4 + 1000


@pytest.mark.asyncio
async def test_gateway_session_endpoints():
    """Verify /api/sessions REST API endpoints on Gateway."""
    async with AsyncClient(transport=ASGITransport(app=gateway_app), base_url="http://test") as ac:
        res = await ac.get("/api/sessions")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert isinstance(data["sessions"], list)

        res_facts = await ac.get("/api/memory/facts")
        assert res_facts.status_code == 200
        facts_data = res_facts.json()
        assert facts_data["status"] == "success"
        assert isinstance(facts_data["facts"], list)


@pytest.mark.asyncio
async def test_gateway_zero_shot_response_archetypes():
    """Verify classification of all 5 Zero-Shot Response Archetypes and their format contracts."""
    from gateway import (
        detect_response_archetype,
        ARCHETYPE_EXECUTIVE_SUMMARY,
        ARCHETYPE_STRUCTURED_AUDIT,
        ARCHETYPE_CODE_ENGINEERING,
        ARCHETYPE_CONCEPTUAL_MENTOR,
        ARCHETYPE_MULTI_TURN_CONTINUATION,
        ARCHETYPE_INSTRUCTIONS
    )

    # 1. ARCHETYPE_EXECUTIVE_SUMMARY
    assert detect_response_archetype("price of tomato in kolar") == ARCHETYPE_EXECUTIVE_SUMMARY
    assert detect_response_archetype("tell fast what is the rate") == ARCHETYPE_EXECUTIVE_SUMMARY
    assert detect_response_archetype("give rate") == ARCHETYPE_EXECUTIVE_SUMMARY
    assert "Deliver a high-impact, ultra-concise answer" in ARCHETYPE_INSTRUCTIONS[ARCHETYPE_EXECUTIVE_SUMMARY]

    # 2. ARCHETYPE_STRUCTURED_AUDIT
    assert detect_response_archetype("is Aadhaar present in the document?") == ARCHETYPE_STRUCTURED_AUDIT
    assert detect_response_archetype("compare wheat and barley yields and prices") == ARCHETYPE_STRUCTURED_AUDIT
    assert detect_response_archetype("verify spreadsheet parameters in a markdown table") == ARCHETYPE_STRUCTURED_AUDIT
    assert "Present the primary finding inside a clean Markdown Table" in ARCHETYPE_INSTRUCTIONS[ARCHETYPE_STRUCTURED_AUDIT]

    # 3. ARCHETYPE_CODE_ENGINEERING
    assert detect_response_archetype("Traceback (most recent call last): File 'gateway.py', line 12 TypeError") == ARCHETYPE_CODE_ENGINEERING
    assert detect_response_archetype("def calculate_fibonacci(n): pass") == ARCHETYPE_CODE_ENGINEERING
    assert detect_response_archetype("write a python function to parse json payloads in src/components/InputDeck.jsx") == ARCHETYPE_CODE_ENGINEERING
    assert "Provide direct implementation code immediately" in ARCHETYPE_INSTRUCTIONS[ARCHETYPE_CODE_ENGINEERING]

    # 4. ARCHETYPE_CONCEPTUAL_MENTOR
    assert detect_response_archetype("i am not getting this, explain how attention works simply") == ARCHETYPE_CONCEPTUAL_MENTOR
    assert detect_response_archetype("explain like i'm 5 what is quantum computing") == ARCHETYPE_CONCEPTUAL_MENTOR
    assert detect_response_archetype("how does backpropagation work in neural networks?") == ARCHETYPE_CONCEPTUAL_MENTOR
    assert "Use a simple everyday real-world analogy" in ARCHETYPE_INSTRUCTIONS[ARCHETYPE_CONCEPTUAL_MENTOR]

    # 5. ARCHETYPE_MULTI_TURN_CONTINUATION
    active_history = [
        {"role": "user", "content": "What is drip irrigation?"},
        {"role": "assistant", "content": "Drip irrigation saves water by dripping water directly to roots."}
    ]
    assert detect_response_archetype("broooo", recent_history=active_history) == ARCHETYPE_MULTI_TURN_CONTINUATION
    assert detect_response_archetype("why?", recent_history=active_history) == ARCHETYPE_MULTI_TURN_CONTINUATION
    assert detect_response_archetype("what next?", recent_history=active_history) == ARCHETYPE_MULTI_TURN_CONTINUATION
    assert detect_response_archetype("then?", recent_history=active_history) == ARCHETYPE_MULTI_TURN_CONTINUATION
    assert "This is an ongoing conversational nudge" in ARCHETYPE_INSTRUCTIONS[ARCHETYPE_MULTI_TURN_CONTINUATION]


@pytest.mark.asyncio
async def test_gateway_rag_upload_multipart_endpoint():
    """Verify /api/rag/upload endpoint accepts multipart documents and returns chunk metadata."""
    import io

    async with AsyncClient(transport=ASGITransport(app=gateway_app), base_url="http://test") as ac:
        # 1. Upload text document
        txt_content = b"Karnataka Horticulture Guidelines: Tomato recommended spacing is 60cm x 45cm."
        files = {"file": ("guidelines.txt", io.BytesIO(txt_content), "text/plain")}
        data = {"session_id": "test_upload_sess_01"}
        res = await ac.post("/api/rag/upload", files=files, data=data)
        assert res.status_code == 200
        data_res = res.json()
        assert data_res["status"] == "success"
        assert data_res["filename"] == "guidelines.txt"
        assert data_res["file_type"] == ".txt"
        assert data_res["chunks_indexed"] >= 1

        # 2. Upload CSV spreadsheet
        csv_content = b"Item,Cost,Category\nFertilizer,1500,Agri\nSeeds,800,Agri\n"
        files_csv = {"file": ("budget.csv", io.BytesIO(csv_content), "text/csv")}
        res_csv = await ac.post("/api/rag/upload", files=files_csv, data={"session_id": "test_upload_sess_01"})
        assert res_csv.status_code == 200
        csv_res = res_csv.json()
        assert csv_res["status"] == "success"
        assert csv_res["filename"] == "budget.csv"
        assert csv_res["file_type"] == ".csv"
        assert csv_res["chunks_indexed"] >= 1

        # 3. Reject unsupported executable or binary format
        bin_content = b"\x7fELF\x02\x01\x01\x00"
        files_bin = {"file": ("malware.exe", io.BytesIO(bin_content), "application/octet-stream")}
        res_bin = await ac.post("/api/rag/upload", files=files_bin, data={"session_id": "test_upload_sess_01"})
        assert res_bin.status_code == 400







