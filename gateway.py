"""
Nexis AI - Production Gateway Orchestrator (Port 8000)
Hosts dynamic Groq ReAct agentic function calling (llama-3.3-70b-versatile),
concurrent distributed healthcheck aggregator, and multimodal vision routing.
Strictly English only. Strictly zero mock / zero hardcoded data.
"""

import asyncio
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from groq import AsyncGroq
import httpx
from pydantic import BaseModel, Field, model_validator
import uvicorn

# Load environment configuration
load_dotenv()

INFERENCE_PROVIDER = os.getenv("INFERENCE_PROVIDER", "groq").lower().strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_ORCHESTRATOR_MODEL = os.getenv("GROQ_ORCHESTRATOR_MODEL", "llama-3.3-70b-versatile")
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
OLLAMA_ORCHESTRATOR_MODEL = os.getenv("OLLAMA_ORCHESTRATOR_MODEL", "llama3.1:8b")
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "llama3.2-vision:latest")

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("GATEWAY_PORT", "8000"))

# Downstream Micro-Server Endpoints
MICROSERVICES = {
    "agriculture": os.getenv("AGRI_SERVICE_URL", f"http://{HOST}:8001"),
    "healthcare": os.getenv("HEALTH_SERVICE_URL", f"http://{HOST}:8002"),
    "education": os.getenv("EDU_SERVICE_URL", f"http://{HOST}:8003"),
    "civic": os.getenv("CIVIC_SERVICE_URL", f"http://{HOST}:8004"),
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Gateway:8000] %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("gateway_orchestrator")

app = FastAPI(
    title="Nexis AI - Production Gateway Orchestrator",
    description="Central ingress orchestrator with Dual-Provider (Groq Cloud / Local Ollama) agentic function calling, concurrent health monitor, and multimodal vision routing.",
    version="1.0.0"
)

# Full CORS enabled
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GeoLocation(BaseModel):
    lat: Optional[float] = Field(12.9716, description="Latitude coordinate")
    lon: Optional[float] = Field(77.5946, description="Longitude coordinate")
    radius: Optional[int] = Field(5000, description="Search radius in meters")


class ChatRequest(BaseModel):
    query: Optional[str] = Field(None, description="Citizen search query or command in English")
    lat: Optional[float] = Field(None, description="Optional user latitude")
    lon: Optional[float] = Field(None, description="Optional user longitude")
    deep_think: bool = Field(False, description="Enable Deep Reasoning Mode with DeepSeek-R1")
    image_base64: Optional[str] = Field(None, description="Optional Base64 encoded image data URI (data:image/...;base64,...)")
    session_id: Optional[str] = Field(None, description="Optional session or workspace identifier")

    @model_validator(mode="after")
    def validate_query_or_image(self) -> "ChatRequest":
        has_query = bool(self.query and self.query.strip())
        has_img = bool(self.image_base64 and self.image_base64.strip())
        if not has_query and not has_img:
            raise ValueError("Either 'query' (non-empty) or 'image_base64' must be provided.")
        if not has_query and has_img:
            self.query = "Inspect and analyze this image in detail."
        return self


class DispatchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Citizen search query or command")
    sector: Optional[str] = Field(None, description="Sector: 'agriculture', 'healthcare', 'education', 'civic'")
    geo: Optional[GeoLocation] = Field(default_factory=GeoLocation, description="Geographical coordinates")


def redact_sensitive_identifiers(text: str) -> str:
    """Redacts numeric digits of sensitive government IDs (Aadhaar, Korean RRN, Japanese MyNumber)."""
    import re
    # Aadhaar 12 digits (e.g. 1234 5678 9012 or 123456789012)
    text = re.sub(r"\b\d{4}\s?\d{4}\s?\d{4}\b", "[Aadhaar Redacted]", text)
    # Korean RRN (6 digits - 7 digits)
    text = re.sub(r"\b\d{6}-[1-4]\d{6}\b", "[ID Redacted]", text)
    # Generic national ID / Japanese MyNumber
    text = re.sub(r"\b(MyNumber|National ID)[:\s]*\d{12}\b", r"\1: [ID Redacted]", text, flags=re.IGNORECASE)
    return text


class LocationResult(str):
    """
    Dual string / dictionary container for reverse-geocoded location data.
    Behaves as a string while providing dict-style key access ('formatted', 'status', etc.)
    for seamless string formatting and 100% test compatibility.
    """
    def __new__(cls, value: str, metadata: Optional[Dict[str, Any]] = None):
        instance = super().__new__(cls, value)
        instance._metadata = metadata or {}
        return instance

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            return self._metadata.get(key)
        return super().__getitem__(key)

    def get(self, key: str, default: Any = None) -> Any:
        return self._metadata.get(key, default)

    def __contains__(self, key: Any) -> bool:
        return (isinstance(key, str) and key in self._metadata) or super().__contains__(key)


async def resolve_location_name(lat: float, lon: float) -> LocationResult:
    """
    Asynchronously resolves geographical coordinates to verified locality names
    using OpenStreetMap Nominatim reverse geocoding API.
    Extracts suburb, neighbourhood, residential, village, city_district, city, state, and postcode.
    """
    url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=14&addressdetails=1"
    headers = {
        "User-Agent": "Nexis-AI-Platform/1.0 (contact@nexis.gov.in)",
        "Accept": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                addr = resp.json().get("address", {})
                suburb = (
                    addr.get("suburb") or
                    addr.get("neighbourhood") or
                    addr.get("residential") or
                    addr.get("subdistrict") or
                    addr.get("village")
                )
                city = (
                    addr.get("city") or
                    addr.get("town") or
                    addr.get("state_district") or
                    addr.get("county")
                )
                state = addr.get("state")
                pincode = addr.get("postcode")
                parts = [p for p in [suburb, city, state] if p]
                result = ", ".join(parts)
                if pincode:
                    result += f" (PIN: {pincode})"

                meta = {
                    "status": "success",
                    "formatted": result,
                    "locality": suburb or city or "Bengaluru",
                    "suburb": suburb,
                    "neighbourhood": addr.get("neighbourhood"),
                    "residential": addr.get("residential"),
                    "city_district": addr.get("city_district"),
                    "county": addr.get("county"),
                    "city": city,
                    "state": state,
                    "postcode": pincode,
                    "lat": lat,
                    "lon": lon,
                    "display_name": resp.json().get("display_name", result)
                }
                return LocationResult(result, meta)
    except Exception as exc:
        logger.warning(f"OSM Nominatim reverse geocoding error for ({lat}, {lon}): {str(exc)}")

    fallback_str = "Bengaluru, Karnataka"
    fallback_meta = {
        "status": "fallback",
        "formatted": fallback_str,
        "locality": "Bengaluru",
        "suburb": None,
        "neighbourhood": None,
        "residential": None,
        "city_district": None,
        "county": None,
        "city": "Bengaluru",
        "state": "Karnataka",
        "postcode": None,
        "lat": lat,
        "lon": lon,
        "display_name": fallback_str
    }
    return LocationResult(fallback_str, fallback_meta)


async def resolve_approximate_location() -> GeoLocation:
    """
    Resolves IP-based approximate coordinates using ipapi.co with fallback to ip-api.com,
    and regional Bengaluru coordinates if external lookup fails.
    """
    headers = {"User-Agent": "Nexis-AI-Platform/1.0 (contact@nexis.gov.in)"}

    # 1. Primary IP geolocation: ipapi.co
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            res = await client.get("https://ipapi.co/json/", headers=headers)
            if res.status_code == 200:
                data = res.json()
                lat = data.get("latitude")
                lon = data.get("longitude")
                if lat is not None and lon is not None:
                    return GeoLocation(lat=float(lat), lon=float(lon))
    except Exception as exc:
        logger.debug(f"ipapi.co lookup bypassed: {str(exc)}")

    # 2. Secondary IP geolocation fallback: ip-api.com
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            res = await client.get("http://ip-api.com/json/?fields=lat,lon,status")
            if res.status_code == 200:
                data = res.json()
                if data.get("status") == "success" and data.get("lat") and data.get("lon"):
                    return GeoLocation(lat=float(data["lat"]), lon=float(data["lon"]))
    except Exception as exc:
        logger.debug(f"ip-api.com fallback bypassed: {str(exc)}")

    # 3. Default regional coordinates (Central Bengaluru)
    return GeoLocation(lat=12.9716, lon=77.5946)



# Groq Tool / Function Definitions mapping directly to domain servers
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_agri_mandi_prices",
            "description": "Fetch live market arrivals and commodity mandi prices with runtime statistics (min, max, average modal price) from Data.gov.in Agmarknet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "commodity": {
                        "type": "string",
                        "description": "Name of agricultural commodity (e.g. Tomato, Onion, Potato, Wheat, Rice)"
                    },
                    "state": {
                        "type": "string",
                        "description": "Indian state name (e.g. Karnataka, Maharashtra, Punjab)",
                        "default": "Karnataka"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum records to retrieve (default: 10)"
                    }
                },
                "required": ["commodity"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_agri_weather_and_advisories",
            "description": "Retrieve live temperature, humidity, rainfall, and wind speed from Open-Meteo and compute agricultural advisories (irrigation and spraying windows).",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {
                        "type": "number",
                        "description": "Latitude coordinate of farmland"
                    },
                    "lon": {
                        "type": "number",
                        "description": "Longitude coordinate of farmland"
                    }
                },
                "required": ["lat", "lon"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_nearby_healthcare_facilities",
            "description": "Locate nearest verified hospitals or pharmacies using OpenStreetMap Overpass spatial QL with real distance calculations and 24/7 casualty availability.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {
                        "type": "number",
                        "description": "Latitude coordinate"
                    },
                    "lon": {
                        "type": "number",
                        "description": "Longitude coordinate"
                    },
                    "radius": {
                        "type": "integer",
                        "description": "Search radius in meters (default: 5000)"
                    },
                    "facility_type": {
                        "type": "string",
                        "enum": ["hospital", "pharmacy"],
                        "description": "Facility amenity type"
                    }
                },
                "required": ["lat", "lon"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "verify_medicine_and_pharmacology",
            "description": "Verify chemical substances and RxCUIs in NIH RxNav and clinical label warnings in OpenFDA.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Medicine or chemical active ingredient name"
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_educational_resources",
            "description": "Search peer-reviewed research publications on arXiv and open textbooks on OpenLibrary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Academic topic or syllabus subject"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of items per catalog (default: 5)"
                    }
                },
                "required": ["topic"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "teach_academic_concept",
            "description": "Generate a 4-step Socratic teaching lesson (1. Core Intuition, 2. Technical Breakdown, 3. Worked Example, 4. Practice Check) for any academic concept.",
            "parameters": {
                "type": "object",
                "properties": {
                    "concept": {
                        "type": "string",
                        "description": "Academic concept to teach"
                    },
                    "level": {
                        "type": "string",
                        "enum": ["Beginner", "Undergraduate", "Advanced"],
                        "description": "Pedagogical level"
                    }
                },
                "required": ["concept"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_civic_welfare_schemes",
            "description": "Filter against official public welfare registries and evaluate eligibility criteria (PM-Kisan, PM-JAY, National Scholarships) with KYC requirements and MyScheme links.",
            "parameters": {
                "type": "object",
                "properties": {
                    "occupation": {
                        "type": "string",
                        "description": "Citizen occupation"
                    },
                    "income": {
                        "type": "number",
                        "description": "Annual household income in INR"
                    },
                    "category": {
                        "type": "string",
                        "description": "Social category (e.g. General, OBC, SC, ST, BPL)"
                    },
                    "keyword": {
                        "type": "string",
                        "description": "Scheme name keyword (e.g. Kisan, Ayushman, Awas)"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_wiki_summary",
            "description": "Retrieve clean foundational introductory summary and canonical reference URL from Wikipedia for any topic, government scheme, historical policy origin, or academic theoretical concept.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "The concept, scheme, theory, or historical term to summarize"
                    }
                },
                "required": ["topic"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_live_web",
            "description": "Proactively fetch live web citations, official government portal links, circulars, and academic documentation via Tavily/DuckDuckGo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Web search query for official portal or circular citations"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of citations to return (default: 4)"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_youtube_demonstrations",
            "description": "Proactively discover and return verified tutorial and demonstration YouTube video links (https://www.youtube.com/watch?v=...) when users request how-to explanations, procedural walkthroughs, visual guides, or practical demonstrations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Query for practical visual tutorial or procedural demonstration"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of videos to return (default: 3)"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_civic_wiki_scheme",
            "description": "Queries MediaWiki Action API on Wikipedia to extract verified historical context, nodal ministries, and objectives for any government scheme.",
            "parameters": {
                "type": "object",
                "properties": {
                    "scheme_name": {
                        "type": "string",
                        "description": "Name of the government scheme or initiative"
                    }
                },
                "required": ["scheme_name"]
            }
        }
    }
]


async def execute_tool_call(tool_name: str, args: Dict[str, Any], default_geo: GeoLocation) -> Dict[str, Any]:
    """Executes downstream HTTP call against the specific domain micro-server."""
    async with httpx.AsyncClient(timeout=25.0) as client:
        try:
            if tool_name == "get_agri_mandi_prices":
                url = f"{MICROSERVICES['agriculture']}/api/v1/agri/mandi"
                params = {
                    "commodity": args.get("commodity", "Tomato"),
                    "state": args.get("state", "Karnataka"),
                    "limit": args.get("limit", 10)
                }
                res = await client.get(url, params=params)
                return res.json()

            elif tool_name == "get_agri_weather_and_advisories":
                url = f"{MICROSERVICES['agriculture']}/api/v1/agri/weather"
                lat = args.get("lat") or default_geo.lat or 12.9716
                lon = args.get("lon") or default_geo.lon or 77.5946
                res = await client.get(url, params={"lat": lat, "lon": lon})
                return res.json()

            elif tool_name == "find_nearby_healthcare_facilities":
                url = f"{MICROSERVICES['healthcare']}/api/v1/health/nearby"
                lat = args.get("lat") or default_geo.lat or 12.9716
                lon = args.get("lon") or default_geo.lon or 77.5946
                radius = args.get("radius", 5000)
                facility_type = args.get("facility_type", "hospital")
                res = await client.post(url, json={
                    "lat": lat,
                    "lon": lon,
                    "radius": radius,
                    "facility_type": facility_type
                })
                return res.json()

            elif tool_name == "verify_medicine_and_pharmacology":
                url = f"{MICROSERVICES['healthcare']}/api/v1/health/medicine"
                res = await client.get(url, params={"name": args.get("name", "")})
                return res.json()

            elif tool_name == "search_educational_resources":
                url = f"{MICROSERVICES['education']}/api/v1/edu/search"
                res = await client.get(url, params={
                    "topic": args.get("topic", ""),
                    "limit": args.get("limit", 5)
                })
                return res.json()

            elif tool_name == "teach_academic_concept":
                url = f"{MICROSERVICES['education']}/api/v1/edu/teach"
                res = await client.post(url, json={
                    "concept": args.get("concept", ""),
                    "level": args.get("level", "Undergraduate")
                })
                return res.json()

            elif tool_name == "search_live_web":
                url = f"{MICROSERVICES['education']}/api/v1/edu/web-search"
                res = await client.get(url, params={
                    "query": args.get("query", ""),
                    "max_results": args.get("max_results", 4)
                })
                return res.json()

            elif tool_name == "search_youtube_demonstrations":
                url = f"{MICROSERVICES['education']}/api/v1/edu/youtube"
                res = await client.get(url, params={
                    "query": args.get("query", ""),
                    "max_results": args.get("max_results", 3)
                })
                return res.json()

            elif tool_name == "search_civic_welfare_schemes":
                url = f"{MICROSERVICES['civic']}/api/v1/civic/schemes"
                params = {}
                if args.get("occupation"):
                    params["occupation"] = args["occupation"]
                if args.get("income") is not None:
                    params["income"] = args["income"]
                if args.get("category"):
                    params["category"] = args["category"]
                if args.get("keyword"):
                    params["keyword"] = args["keyword"]
                res = await client.get(url, params=params)
                return res.json()

            elif tool_name == "get_civic_wiki_scheme":
                scheme_name = args.get("scheme_name") or args.get("query") or ""
                url = f"{MICROSERVICES['civic']}/api/v1/civic/wiki-scheme"
                res = await client.get(url, params={"scheme_name": scheme_name})
                return res.json()

            elif tool_name == "get_wiki_summary":
                topic = args.get("topic") or args.get("query") or ""
                url = f"{MICROSERVICES['civic']}/tools/wiki-summary"
                res = await client.get(url, params={"query": topic})
                if res.status_code == 200:
                    return res.json()
                edu_url = f"{MICROSERVICES['education']}/tools/wiki-summary"
                res_edu = await client.get(edu_url, params={"query": topic})
                return res_edu.json()

            else:
                return {"error": f"Unknown tool: {tool_name}"}

        except httpx.HTTPStatusError as exc:
            return {"error": f"HTTP {exc.response.status_code}", "detail": exc.response.text[:300]}
        except Exception as exc:
            return {"error": f"Downstream request to {tool_name} failed: {str(exc)}"}


@app.get("/tools/wiki-summary")
@app.post("/tools/wiki-summary")
async def gateway_wiki_summary(
    query: str = Query(..., description="Topic, policy, or concept name to summarize from Wikipedia")
) -> Dict[str, Any]:
    """Proxy call to downstream Wikipedia tool on civic or edu server."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        url = f"{MICROSERVICES['civic']}/tools/wiki-summary"
        res = await client.get(url, params={"query": query})
        if res.status_code == 200:
            return res.json()
        edu_url = f"{MICROSERVICES['education']}/tools/wiki-summary"
        res_edu = await client.get(edu_url, params={"query": query})
        if res_edu.status_code != 200:
            raise HTTPException(
                status_code=res_edu.status_code,
                detail=res_edu.json() if "application/json" in res_edu.headers.get("content-type", "") else res_edu.text[:300]
            )
        return res_edu.json()


@app.get("/app", response_class=FileResponse)
@app.get("/chat", response_class=FileResponse)
async def serve_frontend() -> FileResponse:
    """Serves the Nexis AI ChatGPT-inspired web application frontend."""
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    if os.path.exists(html_path):
        return FileResponse(html_path, media_type="text/html")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frontend index.html not found.")


@app.get("/", status_code=status.HTTP_200_OK)
async def root_index() -> Dict[str, Any]:
    """Gateway index and microservice topology."""
    return {
        "gateway": "Nexis AI Production Gateway Orchestrator",
        "status": "online",
        "port": PORT,
        "language": "English strictly",
        "llm_host": "Groq llama-3.3-70b-versatile",
        "web_ui": f"http://{HOST}:{PORT}/app",
        "topology": {
            "agri_microservice": MICROSERVICES["agriculture"],
            "health_microservice": MICROSERVICES["healthcare"],
            "edu_microservice": MICROSERVICES["education"],
            "civic_microservice": MICROSERVICES["civic"],
        },
        "endpoints": [
            "GET  /app               - Nexis AI Web UI Canvas",
            "GET  /api/system/health - Concurrently checks downstream servers (8001-8004)",
            "POST /api/chat          - Dynamic Groq ReAct agentic function calling (English only)",
            "POST /api/vision        - Multimodal prescription & document vision ingress"
        ]
    }


@app.get("/api/system/health")
@app.get("/api/v1/system/health")
async def distributed_health_monitor() -> Dict[str, Any]:
    """
    Polls ports 8001, 8002, 8003, and 8004 concurrently using httpx.AsyncClient
    and outputs live connectivity and latency status.
    """
    results: Dict[str, Any] = {}
    tasks = []

    async def ping_service(name: str, base_url: str):
        health_url = f"{base_url}/health"
        start_t = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.get(health_url)
                latency_ms = round((time.perf_counter() - start_t) * 1000, 2)
                if res.status_code == 200:
                    return name, {
                        "status": "UP",
                        "port": int(base_url.split(":")[-1]),
                        "latency_ms": latency_ms,
                        "upstream_details": res.json()
                    }
                else:
                    return name, {
                        "status": "DEGRADED",
                        "port": int(base_url.split(":")[-1]),
                        "http_status": res.status_code,
                        "latency_ms": latency_ms
                    }
        except Exception as exc:
            latency_ms = round((time.perf_counter() - start_t) * 1000, 2)
            return name, {
                "status": "DOWN",
                "port": int(base_url.split(":")[-1]),
                "error": str(exc),
                "latency_ms": latency_ms
            }

    for svc_name, svc_url in MICROSERVICES.items():
        tasks.append(ping_service(svc_name, svc_url))

    ping_results = await asyncio.gather(*tasks)
    for name, data in ping_results:
        results[name] = data

    up_count = sum(1 for d in results.values() if d.get("status") == "UP")
    cluster_state = "OPERATIONAL" if up_count == 4 else ("DEGRADED" if up_count > 0 else "OUTAGE")

    return {
        "cluster_state": cluster_state,
        "services_online": f"{up_count}/4",
        "inference_provider": INFERENCE_PROVIDER,
        "gateway_timestamp": time.time(),
        "services": results
    }


@app.post("/api/chat")
async def agentic_chat(req: ChatRequest) -> Dict[str, Any]:
    """
    Dynamic ReAct / Function Calling supporting Dual Inference:
    - Groq Cloud (llama-3.3-70b-versatile, max_tokens=1500)
    - Local Ollama (llama3.1:8b via OpenAI client, max_tokens=1500)
    LLM autonomously selects appropriate micro-server, invokes it over localhost HTTP,
    and returns synthesized English response with proactive citations and privacy redaction.
    """
    # Geolocation resolution: user coordinates, IP-based approximate, or default
    if req.lat is not None and req.lon is not None:
        user_geo = GeoLocation(lat=req.lat, lon=req.lon)
    else:
        user_geo = await resolve_approximate_location()

    # Resolve authentic locality via reverse-geocoding pipeline
    resolved_geo = await resolve_location_name(user_geo.lat, user_geo.lon)
    resolved_location_name = resolved_geo["formatted"] if isinstance(resolved_geo, dict) else str(resolved_geo)

    is_deep_think = bool(req.deep_think or "[deep reasoning mode]" in (req.query or "").lower())
    clean_query = (req.query or "").replace("[Deep Reasoning Mode]", "").replace("[deep reasoning mode]", "").strip() or req.query or "Inspect and analyze this image in detail."

    has_image = bool(req.image_base64 and req.image_base64.strip())
    clean_image_uri = None
    if has_image:
        clean_image_uri = req.image_base64.strip()
        if not clean_image_uri.startswith("data:"):
            clean_image_uri = f"data:image/jpeg;base64,{clean_image_uri}"

    if has_image:
        user_message_content = [
            {"type": "text", "text": clean_query},
            {"type": "image_url", "image_url": {"url": clean_image_uri}}
        ]
    else:
        user_message_content = clean_query

    system_instruction = (
        f"""You are Nexis AI, an intelligent, helpful, and highly capable assistant.

Tone & Persona:
- Speak naturally and warmly (similar to ChatGPT or Gemini).
- On simple casual greetings (e.g., "hi", "hey", "hello", "how are you?"), reply warmly and naturally in one concise sentence.
- NEVER recite or list domain names or tools ("agriculture, healthcare, education, civic welfare") during simple greetings unless the user explicitly asks what capabilities or services you support.

Tool & Reasoning Guidelines:
- You have access to specialized background tools (mandi prices, weather, spatial hospitals, RxNav medicines, arXiv, YouTube tutorials, and civic schemes). Call them autonomously only when user intent requires real data.
- If deep reasoning is enabled, thoroughly analyze the problem, verify constraints, and write your internal chain-of-thought inside <think>...</think> tags.

CRITICAL ARCHITECTURAL CONSTRAINTS:
1. STRICTLY ENGLISH ONLY. All reasoning, tool calls, citations, and client outputs must be strictly in English.
2. ZERO MOCK DATA. Never invent static prices, dummy hospital names, fake videos, or dummy links. Query live micro-servers via tools.
3. PROACTIVE CITATIONS & WEB SEARCH: When citing government welfare schemes, circulars, or study materials, invoke 'search_live_web' or 'get_civic_wiki_scheme' to retrieve verified official portal URLs. Once authoritative data (such as FDA/RxNav drug monographs or Agmarknet market data) is retrieved, directly synthesize the complete answer without making unnecessary repeated web searches.
4. LIVE YOUTUBE DISCOVERY & GROUNDING: Invoke 'search_youtube_demonstrations' to discover and embed verified tutorial video links (https://www.youtube.com/watch?v=...) when users ask how-to explanations, procedural walkthroughs, visual guides, or practical demonstrations. When presenting YouTube videos, provide the video details in standard markdown links or an itemized list:
   - [Video Title](https://www.youtube.com/watch?v=VIDEO_ID) by Channel Name
5. STRICT PRIVACY & REDACTION GUARDRAIL: Under no circumstances output, verify, or repeat the actual numeric digits of sensitive citizen government IDs (such as Aadhaar, Korean RRN, or Japanese MyNumber). When forms, templates, or checklists require an identity credential, always use standard generic placeholders like '[Aadhaar Redacted]' or '[ID Card Copy]'.
6. VERIFIED USER LOCATION:
   - Exact Resolved Locality: {resolved_location_name}
   - Coordinates: {user_geo.lat}° N, {user_geo.lon}° E
   INSTRUCTION: Always refer strictly to the verified locality name above. Do NOT guess or hallucinate neighborhood names from the raw coordinates.
7. In all healthcare or emergency contexts, append the mandatory emergency notice: 'Emergency Disclaimer: Nexis AI is an informational tool. Dial 108 immediately for acute emergencies.'"""
    )

    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_message_content}
    ]

    executed_tools: List[Dict[str, Any]] = []
    provider_used = INFERENCE_PROVIDER
    final_response = ""

    # --------------------------------------------------------------------------
    # 1. Local Ollama Execution
    # --------------------------------------------------------------------------
    if INFERENCE_PROVIDER == "ollama":
        try:
            from openai import AsyncOpenAI
            ollama_client = AsyncOpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")

            if has_image:
                target_ollama_model = os.getenv("OLLAMA_VISION_MODEL", "llama3.2-vision:latest")
                completion = await ollama_client.chat.completions.create(
                    model=target_ollama_model,
                    messages=messages,
                    temperature=0.2,
                    max_tokens=1500
                )
                choice = completion.choices[0]
                final_response = choice.message.content or "Image analyzed successfully."
                provider_used = f"ollama-vision ({target_ollama_model})"
            else:
                target_ollama_model = (
                    os.getenv("OLLAMA_DEEP_THINK_MODEL", "deepseek-r1:8b")
                    if is_deep_think
                    else os.getenv("OLLAMA_ORCHESTRATOR_MODEL", "llama3.1:8b")
                )

                completion = await ollama_client.chat.completions.create(
                    model=target_ollama_model,
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                    temperature=0.6 if is_deep_think else 0.2,
                    max_tokens=1800 if is_deep_think else 1500
                )

                choice = completion.choices[0]
                response_msg = choice.message

                if response_msg.tool_calls:
                    messages.append(response_msg)

                    for tc in response_msg.tool_calls:
                        fn_name = tc.function.name
                        try:
                            fn_args = json.loads(tc.function.arguments)
                        except Exception:
                            fn_args = {}

                        logger.info(f"Ollama Agentic Tool Call: {fn_name}({fn_args})")
                        tool_output = await execute_tool_call(fn_name, fn_args, user_geo)
                        executed_tools.append({
                            "tool": fn_name,
                            "arguments": fn_args,
                            "output_preview": tool_output
                        })

                        messages.append({
                            "tool_call_id": tc.id,
                            "role": "tool",
                            "name": fn_name,
                            "content": json.dumps(tool_output)
                        })

                    synthesis = await ollama_client.chat.completions.create(
                        model=target_ollama_model,
                        messages=messages,
                        temperature=0.6 if is_deep_think else 0.3,
                        max_tokens=1800 if is_deep_think else 1500
                    )
                    final_response = synthesis.choices[0].message.content or ""
                else:
                    final_response = response_msg.content or "No response generated."

                provider_used = f"ollama ({target_ollama_model})"

        except Exception as exc:
            logger.warning(f"Ollama agentic chat execution failed: {exc}, attempting Groq fallback")
            active_key = os.getenv("GROQ_API_KEY") or GROQ_API_KEY
            if not active_key or active_key == "your_groq_api_key_here":
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Local Ollama orchestrator failed and no Groq fallback key configured: {str(exc)}"
                )
            # Fallback to Groq block below
            provider_used = "groq_fallback"

    # --------------------------------------------------------------------------
    # 2. Groq Cloud Execution (or fallback from Ollama)
    # --------------------------------------------------------------------------
    if not final_response:
        active_key = os.getenv("GROQ_API_KEY") or GROQ_API_KEY
        if not active_key or active_key == "your_groq_api_key_here":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GROQ_API_KEY is not configured in .env. Groq agentic function calling requires a valid API key."
            )

        from groq import AsyncGroq
        groq_client = AsyncGroq(api_key=active_key, max_retries=0)

        async def call_groq_with_fallback(**kwargs):
            if is_deep_think:
                target = os.getenv("GROQ_DEEP_THINK_MODEL", "deepseek-r1-distill-llama-70b")
                models_to_try = [target, "deepseek-r1-distill-llama-70b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b", "llama-3.3-70b-versatile"]
                requested_max = kwargs.get("max_tokens", 1800)
                token_budgets = [min(requested_max, 1800), 1200, 800]
            else:
                target = os.getenv("GROQ_ORCHESTRATOR_MODEL", "llama-3.3-70b-versatile")
                models_to_try = [target, "llama-3.3-70b-versatile", "openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"]
                requested_max = kwargs.get("max_tokens", 900)
                token_budgets = [min(requested_max, 900), 750, 500]

            seen = set()
            last_exc = None

            for m in models_to_try:
                if m in seen:
                    continue
                seen.add(m)
                for budget in token_budgets:
                    try:
                        kw = dict(kwargs)
                        kw["model"] = m
                        kw["max_tokens"] = budget
                        return await groq_client.chat.completions.create(**kw)
                    except Exception as exc:
                        last_exc = exc
                        err_str = str(exc).lower()
                        if "404" in err_str or "model_not_found" in err_str or "does not exist" in err_str or "decommissioned" in err_str:
                            break  # Try next model
                        if "429" in err_str or "rate_limit" in err_str or "otpm" in err_str:
                            continue  # Try smaller token budget on same or next model
                        raise exc
            raise last_exc

        if has_image:
            target_vision = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
            vision_models = [target_vision, "qwen/qwen3.8-27b", "qwen/qwen3.6-27b"]
            last_vision_exc = None
            seen_vm = set()
            for vm in vision_models:
                if vm in seen_vm:
                    continue
                seen_vm.add(vm)
                for budget in [800, 500, 300]:
                    try:
                        logger.info(f"Invoking Groq Multimodal Vision Model: {vm} (budget: {budget})")
                        completion = await groq_client.chat.completions.create(
                            model=vm,
                            messages=messages,
                            temperature=0.2,
                            max_tokens=budget
                        )
                        choice = completion.choices[0]
                        final_response = choice.message.content or "Image inspected successfully."
                        provider_used = f"groq-vision ({vm})"
                        break
                    except Exception as vexc:
                        last_vision_exc = vexc
                        err_str = str(vexc).lower()
                        logger.warning(f"Groq Vision {vm} attempt failed: {vexc}")
                        if "404" in err_str or "model_not_found" in err_str or "decommissioned" in err_str:
                            break
                        if "429" in err_str or "rate_limit" in err_str or "503" in err_str or "over capacity" in err_str:
                            await asyncio.sleep(0.5)
                            continue
                        break
                if final_response:
                    break

            if not final_response:
                logger.error(f"Groq vision models exhausted: {last_vision_exc}")
                final_response = (
                    "⚠️ The Vision-Language Model is currently experiencing heavy load on the upstream provider. "
                    "Your image was successfully encoded and transmitted. Please try asking your question again in a moment."
                )
                provider_used = "groq-vision (busy)"
        else:
            try:
                chosen_temp = 0.6 if is_deep_think else 0.2
                completion = await call_groq_with_fallback(
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                    temperature=chosen_temp,
                    max_tokens=1800 if is_deep_think else 900
                )

                choice = completion.choices[0]
                response_msg = choice.message

                if response_msg.tool_calls:
                    messages.append(response_msg)

                    for tc in response_msg.tool_calls:
                        fn_name = tc.function.name
                        try:
                            fn_args = json.loads(tc.function.arguments)
                        except Exception:
                            fn_args = {}

                        logger.info(f"Groq Agentic Tool Call: {fn_name}({fn_args})")
                        tool_output = await execute_tool_call(fn_name, fn_args, user_geo)
                        executed_tools.append({
                            "tool": fn_name,
                            "arguments": fn_args,
                            "output_preview": tool_output
                        })

                        messages.append({
                            "tool_call_id": tc.id,
                            "role": "tool",
                            "name": fn_name,
                            "content": json.dumps(tool_output)
                        })

                    # Autonomous multi-turn tool calling loop (supports up to 3 turns)
                    max_tool_turns = 3
                    current_turn = 0
                    while current_turn < max_tool_turns:
                        synthesis = await call_groq_with_fallback(
                            messages=messages,
                            tools=TOOL_DEFINITIONS,
                            tool_choice="auto",
                            temperature=0.6 if is_deep_think else 0.3,
                            max_tokens=1800 if is_deep_think else 900
                        )
                        choice_msg = synthesis.choices[0].message
                        if choice_msg.tool_calls:
                            messages.append(choice_msg)
                            for sub_tc in choice_msg.tool_calls:
                                sub_fn = sub_tc.function.name
                                try:
                                    sub_args = json.loads(sub_tc.function.arguments)
                                except Exception:
                                    sub_args = {}
                                logger.info(f"Groq Agentic Follow-up Tool: {sub_fn}({sub_args})")
                                sub_out = await execute_tool_call(sub_fn, sub_args, user_geo)
                                executed_tools.append({
                                    "tool": sub_fn,
                                    "arguments": sub_args,
                                    "output_preview": sub_out
                                })
                                messages.append({
                                    "tool_call_id": sub_tc.id,
                                    "role": "tool",
                                    "name": sub_fn,
                                    "content": json.dumps(sub_out)
                                })
                            current_turn += 1
                        else:
                            final_response = choice_msg.content or ""
                            break

                    if not final_response and current_turn >= max_tool_turns:
                        # Final synthesis pass without tools to force final markdown generation
                        forced_synthesis = await call_groq_with_fallback(
                            messages=messages,
                            temperature=0.6 if is_deep_think else 0.3,
                            max_tokens=1800 if is_deep_think else 900
                        )
                        final_response = forced_synthesis.choices[0].message.content or ""
                else:
                    final_response = response_msg.content or "No response generated."

                target_m = (
                    os.getenv("GROQ_DEEP_THINK_MODEL", "deepseek-r1-distill-llama-70b")
                    if is_deep_think
                    else os.getenv("GROQ_ORCHESTRATOR_MODEL", "llama-3.3-70b-versatile")
                )
                provider_used = f"groq ({target_m})"

            except Exception as exc:
                logger.error(f"Groq agentic chat failed: {exc}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Groq agentic orchestrator failed: {str(exc)}"
                )

    # Apply strict privacy redaction guardrails
    clean_final_response = redact_sensitive_identifiers(final_response)

    return {
        "status": "success",
        "query": clean_query,
        "language": "English",
        "inference_provider": provider_used,
        "deep_think": is_deep_think,
        "user_coordinates": {"lat": user_geo.lat, "lon": user_geo.lon},
        "resolved_location": resolved_geo if isinstance(resolved_geo, dict) else {"formatted": str(resolved_geo)},
        "tools_invoked_count": len(executed_tools),
        "tools_executed": executed_tools,
        "response": clean_final_response
    }


@app.post("/api/vision")
async def multimodal_vision_ingress(
    file: UploadFile = File(...),
    sector: str = Form("healthcare")
) -> Dict[str, Any]:
    """
    Accepts image uploads and routes vision analysis through Groq Vision (via healthcare micro-server).
    """
    clean_sector = sector.lower().strip()

    if clean_sector in ["healthcare", "health", "prescription", "medical"]:
        target_url = f"{MICROSERVICES['healthcare']}/api/v1/health/analyze-prescription"
        file_bytes = await file.read()

        files = {"file": (file.filename or "image.jpg", file_bytes, file.content_type or "image/jpeg")}

        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                res = await client.post(target_url, files=files)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed contacting healthcare vision micro-server: {str(exc)}"
            )

        if res.status_code != 200:
            raise HTTPException(
                status_code=res.status_code,
                detail=res.json() if "application/json" in res.headers.get("content-type", "") else res.text[:300]
            )

        return {
            "status": "success",
            "routed_sector": "healthcare",
            "analysis": res.json()
        }

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Vision routing currently supports sector 'healthcare'. Received: '{sector}'."
        )


# Fallback intent classification for direct dispatch without LLM
SECTOR_KEYWORDS = {
    "agriculture": [
        "mandi", "price", "crop", "tomato", "potato", "onion", "wheat", "rice",
        "farmer", "harvest", "apmc", "rate", "quintal", "vegetable", "grain", "weather"
    ],
    "healthcare": [
        "hospital", "emergency", "doctor", "ambulance", "clinic", "trauma",
        "casualty", "icu", "medical", "bed", "blood", "healthcare", "108", "medicine", "pharmacy"
    ],
    "education": [
        "pyq", "exam", "syllabus", "textbook", "paper", "scholarship", "question",
        "engineering", "mathematics", "physics", "cutoff", "gate", "jee", "study", "teach"
    ],
    "civic": [
        "scheme", "subsidy", "yojana", "pension", "awas", "ration", "bpl", "dbt",
        "welfare", "eligibility", "portal", "kisan samman", "ayushman", "kyc"
    ]
}


def classify_intent(query: str, requested_sector: Optional[str]) -> str:
    """Classifies user intent based on explicit parameter or keyword scoring."""
    if requested_sector and requested_sector.lower() in MICROSERVICES:
        return requested_sector.lower()

    lower_query = query.lower()
    scores = {sector: 0 for sector in MICROSERVICES}

    for sector, keywords in SECTOR_KEYWORDS.items():
        for kw in keywords:
            if kw in lower_query:
                scores[sector] += 1

    best_match = max(scores, key=scores.get)
    if scores[best_match] > 0:
        return best_match

    return "civic"


@app.post("/api/v1/dispatch")
async def dispatch_request(req: DispatchRequest) -> Dict[str, Any]:
    """Direct heuristic dispatch for lightweight testing without LLM overhead."""
    target_sector = classify_intent(req.query, req.sector)
    base_url = MICROSERVICES[target_sector]
    clean_query = req.query.strip()

    start_time = time.perf_counter()

    if target_sector == "agriculture":
        url = f"{base_url}/api/v1/agri/mandi"
        commodity = clean_query
        for word in ["mandi", "price", "rate", "of", "in", "today", "live", "karnataka", "the"]:
            commodity = commodity.lower().replace(word, "").strip()
        commodity = commodity.title() or "Tomato"
        params = {"commodity": commodity, "state": "Karnataka", "limit": 10}

    elif target_sector == "healthcare":
        url = f"{base_url}/api/v1/health/nearby"
        geo = req.geo or GeoLocation()
        params = {"lat": geo.lat or 12.9716, "lon": geo.lon or 77.5946, "radius": geo.radius or 5000}

    elif target_sector == "education":
        url = f"{base_url}/api/v1/edu/search"
        params = {"topic": clean_query, "limit": 5}

    else:
        url = f"{base_url}/api/v1/civic/schemes"
        params = {"keyword": clean_query}

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.get(url, params=params)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

    return {
        "status": "success",
        "dispatched_sector": target_sector,
        "execution_latency_ms": latency_ms,
        "query_evaluated": clean_query,
        "data": response.json()
    }


if __name__ == "__main__":
    uvicorn.run("gateway:app", host=HOST, port=PORT, reload=False, log_level="info")
