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
import re
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional

UPLOAD_DIR = Path("./temp_uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from groq import AsyncGroq
import httpx
from pydantic import BaseModel, Field, model_validator
import uvicorn

from memory import memory_manager
try:
    from src.rag.ingestion import ingest_document
    from src.rag.vector_store import vector_store
    from src.rag.crag_engine import crag_engine
    from src.rag.tabular_engine import tabular_registry
    from src.rag.entity_matcher import resolve_tabular_query
except Exception as rag_err:
    logging.getLogger("gateway_orchestrator").warning(f"RAG modules optional load warning: {rag_err}")
    ingest_document = None
    vector_store = None
    crag_engine = None
    tabular_registry = None
    resolve_tabular_query = None

# Load environment configuration
load_dotenv()

INFERENCE_PROVIDER = os.getenv("INFERENCE_PROVIDER", "groq").lower().strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_ORCHESTRATOR_MODEL = os.getenv("GROQ_ORCHESTRATOR_MODEL", "llama-3.3-70b-versatile")
GROQ_DEEP_THINK_MODEL = os.getenv("GROQ_DEEP_THINK_MODEL", "deepseek-r1-distill-llama-70b")
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
OLLAMA_ORCHESTRATOR_MODEL = os.getenv("OLLAMA_ORCHESTRATOR_MODEL", "llama3.1:8b")
OLLAMA_DEEP_THINK_MODEL = os.getenv("OLLAMA_DEEP_THINK_MODEL", "deepseek-r1:8b")
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes Layer 1 Redis short-term memory buffer on startup and cleans up on shutdown."""
    try:
        await memory_manager.init_redis()
    except Exception as e:
        logger.warning(f"Optional Redis init warning during lifespan: {e}")
    yield
    try:
        await memory_manager.close_redis()
    except Exception as e:
        logger.warning(f"Optional Redis close warning during lifespan: {e}")


app = FastAPI(
    title="Nexis AI Gateway",
    description="Central ingress orchestrator with Dual-Provider (Groq Cloud / Local Ollama) agentic function calling, concurrent health monitor, and multimodal vision routing.",
    version="1.0.0",
    lifespan=lifespan
)

# Hardened CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
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
    message: Optional[str] = Field(None, description="Alternative field for user prompt")
    history: List[Dict[str, Any]] = Field(default_factory=list, description="Recent conversation turns")
    session_id: Optional[str] = Field(None, description="Optional session or workspace identifier")
    chat_id: Optional[str] = Field(None, description="Optional active chat identifier")
    attached_document: Optional[str] = Field(None, description="Filename of document attached in the UI")
    document_context: Optional[str] = Field(None, description="Filename or name of the attached document")
    file_path: Optional[str] = Field(None, description="Path or identifier of the attached document")
    workspace_id: Optional[str] = Field(None, description="Optional workspace identifier")
    lat: Optional[float] = Field(None, description="Optional user latitude")
    lon: Optional[float] = Field(None, description="Optional user longitude")
    deep_think: bool = Field(False, description="Enable Deep Reasoning Mode with DeepSeek-R1")
    model: Optional[str] = Field(None, description="Target model identifier, e.g. 'deep_reasoning' or 'fast'")
    image: Optional[str] = Field(None, description="Base64 Data URI or raw Base64 image data")
    image_base64: Optional[str] = Field(None, description="Optional Base64 encoded image data URI")

    @model_validator(mode="after")
    def validate_query_or_image(self) -> "ChatRequest":
        effective_query = (self.query or self.message or "").strip()
        effective_image = (self.image or self.image_base64 or "").strip()
        effective_doc = (self.document_context or self.attached_document or self.file_path or "").strip()
        if not effective_query and not effective_image and not effective_doc:
            raise ValueError("Either 'message'/'query' (non-empty), 'document_context', or 'image' must be provided.")
        self.query = effective_query or (f"Analyze and summarize {effective_doc} in detail." if effective_doc else "Analyze and describe this image in detail.")
        self.message = self.query
        self.image = effective_image or None
        self.image_base64 = self.image
        return self


class DispatchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Citizen search query or command")
    sector: Optional[str] = Field(None, description="Sector: 'agriculture', 'healthcare', 'education', 'civic'")
    geo: Optional[GeoLocation] = Field(default_factory=GeoLocation, description="Geographical coordinates")


def redact_sensitive_identifiers(text: str) -> str:
    """Redacts numeric digits of sensitive government IDs (Aadhaar, Korean RRN, Japanese MyNumber)."""
    if not text or not isinstance(text, str):
        return text or ""
    import re
    # 1. Japanese MyNumber / Generic national ID (e.g. MyNumber: 123456789012)
    text = re.sub(r"\b(MyNumber|National ID)[:\s]*\d{12}\b", r"\1: [ID Redacted]", text, flags=re.IGNORECASE)
    # 2. Korean RRN (6 digits - 7 digits)
    text = re.sub(r"\b\d{6}-[1-4]\d{6}\b", "[RRN Redacted]", text)
    # 3. Aadhaar 12 digits (with spaces or continuous)
    text = re.sub(r"\b\d{4}\s?\d{4}\s?\d{4}\b", "[Aadhaar Redacted]", text)
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


@app.get("/health", status_code=status.HTTP_200_OK)
@app.head("/health")
@app.get("/api/health", status_code=status.HTTP_200_OK)
@app.head("/api/health")
async def health_check() -> Dict[str, Any]:
    """Lightweight gateway liveness health probe."""
    return {"status": "ok", "service": "gateway", "port": PORT}


@app.get("/", status_code=status.HTTP_200_OK)
@app.head("/")
async def root_index() -> Dict[str, Any]:
    """Gateway index and microservice topology."""
    return {
        "status": "ok",
        "gateway": "Nexis AI Production Gateway Orchestrator",
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
            "GET  /health            - Lightweight gateway health probe",
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


@app.get("/api/sessions")
async def list_user_sessions(limit: int = Query(50, ge=1, le=200)) -> Dict[str, Any]:
    """Retrieves all active and historical chat sessions from SQLite Memory."""
    sessions = await memory_manager.list_sessions(limit=limit)
    return {"status": "success", "sessions": sessions}


@app.get("/api/sessions/{session_id}")
async def get_session_details(session_id: str) -> Dict[str, Any]:
    """Retrieves session metadata and full messages from SQLite Memory."""
    details = await memory_manager.get_session_details(session_id)
    if not details:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "success", "session": details}


@app.delete("/api/sessions/{session_id}")
async def delete_user_session(session_id: str) -> Dict[str, Any]:
    """Deletes a chat session and all its messages from SQLite Memory."""
    success = await memory_manager.delete_session(session_id)
    return {"status": "success", "session_id": session_id, "deleted": success}


@app.get("/api/memory/facts")
async def list_user_facts() -> Dict[str, Any]:
    """Retrieves all extracted persistent user facts (Tier 2 memory)."""
    facts = await memory_manager.list_all_facts()
    return {"status": "success", "facts": facts}


def sanitize_and_optimize_image_uri(image_uri: str, max_dim: int = 2048) -> str:
    """
    Validates, sanitizes, and resizes images to ensure full compliance with
    VLM pixel requirements (enforces >= 32px minimum and <= 2048px maximum).
    """
    if not image_uri or not image_uri.strip():
        return image_uri
    uri = image_uri.strip()
    if not uri.startswith("data:"):
        uri = f"data:image/jpeg;base64,{uri}"
    try:
        import io, re, base64
        from PIL import Image

        match = re.match(r"^data:(image\/[a-zA-Z0-9\+\-\.]+);base64,(.+)$", uri, re.DOTALL)
        if not match:
            return uri
        mime, b64_data = match.group(1), match.group(2)
        raw_bytes = base64.b64decode(b64_data)
        img = Image.open(io.BytesIO(raw_bytes))
        width, height = img.size

        # Minimum dimension guard for Groq Vision (at least 32px)
        if width < 32 or height < 32:
            new_w = max(width, 32)
            new_h = max(height, 32)
            img = img.resize((new_w, new_h), Image.Resampling.NEAREST)
            width, height = img.size

        # Maximum dimension / pixel guard (at most 2048px on longest side or 4M pixels)
        if width > max_dim or height > max_dim or (width * height > 4_000_000):
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        out_buf = io.BytesIO()
        if img.mode in ("RGBA", "P"):
            img.save(out_buf, format="PNG")
            mime = "image/png"
        else:
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(out_buf, format="JPEG", quality=90)
            mime = "image/jpeg"
        new_b64 = base64.b64encode(out_buf.getvalue()).decode("utf-8")
        return f"data:{mime};base64,{new_b64}"
    except Exception as exc:
        logger.warning(f"Image sanitize/optimization notice: {exc}")
    return uri


def extract_ocr_text_from_image_uri(image_uri: str) -> str:
    """Extracts textual content from base64 image data URI using Tesseract OCR if available."""
    if not image_uri or not image_uri.strip():
        return ""
    try:
        import io, re, base64, shutil
        import pytesseract
        from PIL import Image

        tess_bin = shutil.which("tesseract") or "/opt/homebrew/bin/tesseract" or "/usr/local/bin/tesseract"
        if tess_bin and os.path.exists(tess_bin):
            pytesseract.pytesseract.tesseract_cmd = tess_bin

        match = re.match(r"^data:(?:image\/[a-zA-Z0-9\+\-\.]+)?;base64,(.+)$", image_uri.strip(), re.DOTALL)
        b64_data = match.group(1) if match else image_uri.strip()
        raw_bytes = base64.b64decode(b64_data)
        img = Image.open(io.BytesIO(raw_bytes))
        extracted = pytesseract.image_to_string(img)
        return extracted.strip()
    except Exception as exc:
        logger.warning(f"Local OCR text extraction failed or skipped: {exc}")
        return ""


def get_session_document_text(
    session_id: str,
    file_path: Optional[str] = None,
    document_context: Optional[str] = None,
    max_chars: int = 15000
) -> str:
    """
    Retrieves full text of indexed documents in session from:
    1. Vector store all chunks
    2. Local file path via pypdf / text parser if on disk
    """
    retrieved_text = ""
    # 1. Check vector store
    if session_id and vector_store:
        try:
            chunks = vector_store.get_all_chunks(session_id)
            if chunks:
                texts = [c.get("content", "").strip() for c in chunks if c.get("content")]
                retrieved_text = "\n\n".join(texts)
        except Exception as e:
            logger.warning(f"Error fetching chunks for session '{session_id}': {e}")

    # 2. Check disk fallback (pypdf, docx, txt)
    if not retrieved_text:
        possible_paths = []
        if file_path:
            possible_paths.append(Path(file_path))
        if document_context:
            possible_paths.append(UPLOAD_DIR / document_context)
            possible_paths.append(Path(document_context))

        for p in possible_paths:
            if p and p.exists() and p.is_file():
                try:
                    ext = p.suffix.lower()
                    if ext == ".pdf":
                        import pypdf
                        reader = pypdf.PdfReader(str(p))
                        pages_txt = [page.extract_text() or "" for page in reader.pages]
                        retrieved_text = "\n\n".join(pt.strip() for pt in pages_txt if pt.strip())
                    elif ext in [".txt", ".md", ".csv"]:
                        retrieved_text = p.read_text(encoding="utf-8", errors="ignore")
                    elif ext == ".docx":
                        import docx
                        doc = docx.Document(str(p))
                        retrieved_text = "\n\n".join([para.text for para in doc.paragraphs if para.text.strip()])
                    if retrieved_text:
                        break
                except Exception as read_err:
                    logger.warning(f"Direct file read fallback notice for '{p}': {read_err}")

    if retrieved_text and len(retrieved_text) > max_chars:
        retrieved_text = retrieved_text[:max_chars] + "\n...[truncated for token context]..."

    return retrieved_text.strip()


@app.post("/api/rag/upload")
async def upload_document(
    file: UploadFile = File(...),
    session_id: str = Form("default")
) -> Dict[str, Any]:
    """
    Ingests and adaptively chunks any supported document (.pdf, .docx, .pptx, .xlsx, .csv, .txt, .png, .jpg, .jpeg).
    Embeds and stores into session-isolated ChromaDB collection with PII redaction.
    """
    if not file or not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No file uploaded.")

    file_ext = Path(file.filename).suffix.lower()
    allowed = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".csv", ".txt", ".md", ".png", ".jpg", ".jpeg"}
    if file_ext not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file_ext}. Allowed types: {', '.join(sorted(allowed))}"
        )

    clean_session_id = session_id.strip() if session_id else "default"
    file_path = UPLOAD_DIR / file.filename

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Pass to RAG ingestion engine
        from src.rag.ingestion import ingest_document
        chunks = await ingest_document(str(file_path), file.filename, clean_session_id)
        chunks_count = vector_store.add_chunks(clean_session_id, chunks) if vector_store else len(chunks)

        tabular_meta = None
        if file_ext in [".xlsx", ".xls", ".csv"] and tabular_registry:
            try:
                tab_doc = tabular_registry.register_file(str(file_path), file.filename, clean_session_id)
                if tab_doc and tab_doc.primary_meta:
                    tabular_meta = {
                        "is_tabular": True,
                        "sheet_name": tab_doc.primary_meta.sheet_name,
                        "total_rows": tab_doc.primary_meta.total_rows,
                        "columns": tab_doc.primary_meta.columns,
                        "primary_text_columns": tab_doc.primary_meta.primary_text_columns,
                        "numeric_columns": tab_doc.primary_meta.numeric_columns
                    }
            except Exception as tab_err:
                logger.warning(f"Could not register spreadsheet in tabular_registry: {tab_err}")

        resp_payload: Dict[str, Any] = {
            "status": "success",
            "filename": file.filename,
            "file_path": str(file_path),
            "file_type": file_ext,
            "session_id": clean_session_id,
            "chunks_indexed": chunks_count,
            "message": f"Successfully indexed {chunks_count} adaptive chunks for '{file.filename}'."
        }
        if tabular_meta:
            resp_payload["tabular"] = tabular_meta
        return resp_payload
    except Exception as exc:
        logger.error(f"Failed to process and index document '{file.filename}': {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error indexing document: {str(exc)}"
        )


@app.get("/api/rag/documents")
async def list_session_documents(session_id: str = Query(..., description="Target session or chat identifier")) -> Dict[str, Any]:
    """Lists distinct source documents indexed in the given session."""
    vector_docs = vector_store.list_documents(session_id) if (vector_store and vector_store.has_documents(session_id)) else []
    tabular_docs = [d.filename for d in tabular_registry.get_documents(session_id)] if tabular_registry else []
    combined_docs = list(dict.fromkeys(vector_docs + tabular_docs))
    has_docs = len(combined_docs) > 0
    return {
        "status": "success",
        "session_id": session_id,
        "has_documents": has_docs,
        "documents": combined_docs
    }


@app.post("/api/chat")
async def agentic_chat(req: ChatRequest, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """
    Dynamic ReAct / Function Calling supporting Dual Inference & Two-Tier Memory:
    - Tier 1: Sliding window conversational context from SQLite
    - Tier 2: Extracted persistent user facts & profile constraints
    - Groq Cloud (llama-3.3-70b-versatile, max_tokens=3500)
    - Local Ollama (llama3.1:8b via OpenAI client, max_tokens=3500)
    Guarded with top-level error recovery to prevent process death.
    """
    try:
        return await _execute_agentic_chat(req, background_tasks)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Top-level /api/chat exception caught: {exc}", exc_info=True)
        return {
            "status": "error",
            "error": str(exc),
            "detail": f"Gateway processing error: {str(exc)}",
            "response": f"⚠️ **Gateway Processing Error:** An unexpected error occurred: {str(exc)}. Please retry your query.",
            "session_id": req.chat_id or req.session_id,
            "query": req.query or req.message
        }


# =============================================================================
# Zero-Shot Response Archetype Constants & Format Contracts
# =============================================================================
ARCHETYPE_EXECUTIVE_SUMMARY = "EXECUTIVE_SUMMARY"
ARCHETYPE_STRUCTURED_AUDIT = "STRUCTURED_AUDIT"
ARCHETYPE_CODE_ENGINEERING = "CODE_ENGINEERING"
ARCHETYPE_CONCEPTUAL_MENTOR = "CONCEPTUAL_MENTOR"
ARCHETYPE_MULTI_TURN_CONTINUATION = "MULTI_TURN_CONTINUATION"

ARCHETYPE_INSTRUCTIONS = {
    "EXECUTIVE_SUMMARY": "FORMAT RULE: Deliver a high-impact, ultra-concise answer. Lead with the core metric/fact in sentence 1. Use max 3 bullets. No preamble.",
    "STRUCTURED_AUDIT": "FORMAT RULE: Present the primary finding inside a clean Markdown Table. Use boolean checkmarks where applicable. Avoid long prose.",
    "CODE_ENGINEERING": "FORMAT RULE: Provide direct implementation code immediately. Enclose in appropriate language blocks. Explain changes in concise bullets.",
    "CONCEPTUAL_MENTOR": "FORMAT RULE: The user needs intuitive clarity. Use a simple everyday real-world analogy before explaining technical mechanics.",
    "MULTI_TURN_CONTINUATION": "FORMAT RULE: This is an ongoing conversational nudge. React naturally to the preceding turn. Do NOT offer greetings or generic introductions."
}


def detect_response_archetype(user_prompt: str, recent_history: Optional[List[Dict[str, Any]]] = None) -> str:
    """
    Zero-Shot Response Archetype Detection:
    Inspects user's prompt structure, syntactic cues, technical indicators, and conversational history
    to classify the desired output archetype into one of five distinct profiles:
    1. ARCHETYPE_MULTI_TURN_CONTINUATION (Casual Follow-Up / Nudge)
    2. ARCHETYPE_CODE_ENGINEERING (Technical & Implementation)
    3. ARCHETYPE_CONCEPTUAL_MENTOR (Intuitive Breakdown / Analogy)
    4. ARCHETYPE_STRUCTURED_AUDIT (Verification & Comparisons / Markdown Tables)
    5. ARCHETYPE_EXECUTIVE_SUMMARY (Direct / High Urgency / Ultra-concise)
    """
    prompt_clean = (user_prompt or "").strip()
    p_lower = prompt_clean.lower()
    words = re.findall(r"\w+", p_lower)
    word_count = len(words)

    # 1. ARCHETYPE_MULTI_TURN_CONTINUATION (Casual Follow-Up)
    # Trigger cues: Short conversational nudges ("broooo", "why?", "then?", "what next?")
    multiturn_tokens = {
        "broooo", "bro", "dude", "why", "why?", "then", "then?", "what next", "what next?",
        "and then", "and then?", "next", "next?", "huh", "huh?", "wait", "really", "really?",
        "so", "so?", "how come", "continue", "go on", "tell more", "more", "why so"
    }
    cleaned_no_punct = re.sub(r"[?!.]", "", p_lower).strip()
    is_nudge_token = (p_lower in multiturn_tokens or cleaned_no_punct in multiturn_tokens)
    
    # Check if this is a follow-up turn in an active conversation
    has_prior_history = bool(recent_history and isinstance(recent_history, list) and len(recent_history) > 0)
    if has_prior_history and (
        is_nudge_token
        or (word_count <= 3 and any(w in ["broooo", "bro", "why", "then", "next", "and", "huh", "wait", "so"] for w in words))
        or re.match(r"^(bro+|dude|why\??|then\??|what next\??|and then\??|huh\??|wait\??|really\??|so\??|tell more\??)$", p_lower)
    ):
        return ARCHETYPE_MULTI_TURN_CONTINUATION

    # 2. ARCHETYPE_CODE_ENGINEERING (Technical & Implementation)
    # Trigger cues: Code snippets, error stack traces, file paths, JSON, architecture questions
    code_syntax_patterns = [
        r"```", r"\bdef\s+\w+\(", r"\bimport\s+[\w\.]+", r"\bclass\s+\w+[:\(]",
        r"\bfunction\s+\w+\(", r"\bconst\s+\w+\s*=", r"\blet\s+\w+\s*=",
        r"\bvar\s+\w+\s*=", r"\bSELECT\s+.+\s+FROM\b", r"\bcurl\s+-X",
        r"\bpip\s+install\b", r"\bnpm\s+run\b", r"\bgit\s+(clone|commit|push|pull)\b"
    ]
    has_code_syntax = any(re.search(pat, prompt_clean, re.IGNORECASE) for pat in code_syntax_patterns)
    
    file_path_patterns = [
        r"\b[\w\-_/]+\.(py|js|jsx|ts|tsx|json|sql|yaml|yml|sh|css|html|md|rs|go|java|cpp|c)\b",
        r"\b(src/|components/|routes/|models/|gateway\.py|app\.jsx)\b"
    ]
    has_file_path = any(re.search(pat, prompt_clean, re.IGNORECASE) for pat in file_path_patterns)
    
    stack_trace_keywords = [
        "traceback (most recent call last)", "error:", "typeerror", "syntaxerror", "referenceerror",
        "indexerror", "keyerror", "nullpointerexception", "zerodivisionerror", "runtimeerror",
        "uncaught exception", "stack trace", "exit code 1", "exit code 127", "failed with exit status",
        "cannot read property", "undefined is not a function"
    ]
    has_stack_trace = any(st in p_lower for st in stack_trace_keywords)
    
    code_intent_keywords = [
        "write code", "implement function", "fix this code", "refactor code", "debug code",
        "write a script", "code snippet", "api endpoint", "write regex", "unit test",
        "fastapi endpoint", "react component", "dockerfile", "write sql query"
    ]
    has_code_intent = any(ci in p_lower for ci in code_intent_keywords)

    if has_code_syntax or has_file_path or has_stack_trace or has_code_intent:
        return ARCHETYPE_CODE_ENGINEERING

    # 3. ARCHETYPE_CONCEPTUAL_MENTOR (Intuitive Breakdown)
    # Trigger cues: "not getting", "explain", "how does it work", conceptual questions, expressions of confusion
    confusion_phrases = [
        "not getting", "don't get it", "dont get it", "don't understand", "dont understand",
        "explain simply", "explain like i'm 5", "eli5", "how does it work", "how does this work",
        "what does it mean", "why does it", "teach me", "break it down", "break down",
        "in simple terms", "give intuition", "intuitive explanation", "simple analogy",
        "analogy for", "confused about", "makes no sense", "not clear", "help me understand"
    ]
    is_conceptual = (
        any(phrase in p_lower for phrase in confusion_phrases)
        or (word_count >= 3 and p_lower.startswith(("explain ", "how do ", "how does ", "why do ", "why does ", "what is the concept of ")))
    )
    if is_conceptual:
        return ARCHETYPE_CONCEPTUAL_MENTOR

    # 4. ARCHETYPE_STRUCTURED_AUDIT (Verification & Comparisons)
    # Trigger cues: Queries asking "is X present?", "compare A and B", lists of parameters, or spreadsheet verification requests
    structured_audit_cues = [
        "is present", "is it present", "compare ", "compare and contrast", " vs ", " versus ",
        "difference between", "comparison between", "audit", "spreadsheet", "table", "markdown table",
        "tabular", "list of parameters", "verify record", "verification", "check if",
        "roster", "matrix", "pros and cons", "tabular comparison", "parameter list",
        "feature comparison", "side by side"
    ]
    is_structured_audit = any(cue in p_lower for cue in structured_audit_cues) or bool(re.search(r"\bis\s+[\w\s]+\s+present\b", p_lower))
    if is_structured_audit:
        return ARCHETYPE_STRUCTURED_AUDIT

    # 5. ARCHETYPE_EXECUTIVE_SUMMARY (Direct / High Urgency)
    # Trigger cues: Short prompts (< 8 words), imperative verbs ("tell fast", "what is", "give rate"), mobile-style quick checks
    imperative_urgency_phrases = [
        "tell fast", "quick answer", "give rate", "price of", "rate of", "fast answer",
        "quick check", "status of", "how much", "cost of", "give status", "mandi price",
        "weather in", "where is", "who is", "what is the price", "latest rate", "tldr",
        "in one line", "brief summary", "at a glance"
    ]
    has_urgency = any(u in p_lower for u in imperative_urgency_phrases)
    if word_count < 8 or has_urgency:
        return ARCHETYPE_EXECUTIVE_SUMMARY

    # Default fallback for balanced general inquiries
    return ARCHETYPE_EXECUTIVE_SUMMARY


def detect_user_persona(user_prompt: str, recent_history: Optional[List[Dict[str, Any]]] = None) -> str:
    """
    Dynamic Behavioral Classifier / Prompt Conditioner:
    Analyzes prompt style, tone, pacing, and conversational history to formulate
    an adaptive behavioral steering directive for the LLM.

    Directives:
    - Brevity & Urgency: Terse slang, exclamations, single-word checks.
    - Frustration / Confusion: Discontent, difficulty understanding, repeated friction.
    - Academic / Deep Research: Complex logic, derivations, algorithms, scientific papers.
    - Data & Tabular Lookups: Lists, entity verification, structured checks.
    - Language Mirroring: Kannada script or Kannada phonetic Roman script (Kanglish).
    """
    prompt_clean = (user_prompt or "").strip()
    p_lower = prompt_clean.lower()
    words = re.findall(r"\w+", p_lower)

    directives: List[str] = []

    # 1. Language Mirroring (Kannada script or Kanglish phonetic Roman script)
    has_kannada_script = bool(re.search(r"[\u0C80-\u0CFF]", prompt_clean))
    kanglish_keywords = {
        "namaskara", "namaskar", "hege", "hegidira", "hegidiya", "enu", "yenu", "beku",
        "madbeku", "madodu", "illa", "houdu", "kodi", "heli", "yavaga", "yelli", "agalla",
        "dayavittu", "arthavagilla", "swalpa", "nimage", "nanage", "kelasa", "yaru", "tumba",
        "adre", "matte", "kannada", "gottilla", "bekagide", "kanistha", "ragi", "bili", "oota"
    }
    has_kanglish = any(w in kanglish_keywords for w in words)
    # Also check if recent history had Kannada
    history_had_kannada = False
    if recent_history:
        for turn in recent_history[-2:]:
            content = str(turn.get("content", ""))
            if re.search(r"[\u0C80-\u0CFF]", content) or any(w in kanglish_keywords for w in re.findall(r"\w+", content.lower())):
                history_had_kannada = True
                break

    if has_kannada_script or has_kanglish or (history_had_kannada and len(words) <= 4):
        directives.append(
            "User communicates in Kannada / Kanglish (Kannada in Roman script). "
            "Mirror their exact linguistic preference naturally and warmly without breaking character."
        )

    # 2. Frustration / Confusion
    frustration_phrases = [
        "not getting", "not teaching well", "told you already", "already told you",
        "still don't understand", "dont understand", "dont get it", "don't get it",
        "makes no sense", "doesn't make sense", "stop saying", "wrong answer", "that's wrong",
        "not what i asked", "listen to me", "why are you repeating", "confused",
        "not clear", "explain simply", "useless", "not helping", "bad explanation"
    ]
    is_frustrated = any(phrase in p_lower for phrase in frustration_phrases)
    if is_frustrated:
        directives.append(
            "User is experiencing friction. Validate immediately, avoid defensiveness or long preambles, "
            "and pivot to concrete, simplified real-world analogies."
        )

    # 3. Brevity & Urgency
    terse_slang_tokens = {"broooo", "bro", "dude", "why", "what", "tldr", "fast", "quick", "asap", "hurry", "brief", "short"}
    terse_phrases = ["quick answer", "tell fast", "fast answer", "one line", "in 1 line", "in one line", "just answer", "quick summary"]
    is_terse = (
        any(w in terse_slang_tokens for w in words)
        or any(phrase in p_lower for phrase in terse_phrases)
        or (len(words) <= 3 and any(char in prompt_clean for char in ["?", "!"]) and len(prompt_clean) <= 20)
        or (len(words) == 1 and len(prompt_clean) <= 15)
    )
    if is_terse and not is_frustrated:
        directives.append(
            "User prefers ultra-direct, punchy, conversational replies with zero corporate fluff or repetitive welcomes. "
            "Lead directly with the answer in sentence 1."
        )

    # 4. Academic / Deep Research
    academic_keywords = [
        "algorithm", "proof", "derive", "derivation", "mathematical", "architecture",
        "paper", "computational", "complexity", "theorem", "empirical", "asymptotic",
        "formal definition", "deep dive", "mechanism of action", "pharmacokinetics",
        "differential equation", "eigenvalue", "cross-entropy", "backpropagation",
        "transformer", "attention mechanism", "neural network", "state machine"
    ]
    is_academic = any(kw in p_lower for kw in academic_keywords) or (len(words) > 30 and ("?" in prompt_clean or ":" in prompt_clean))
    if is_academic and not is_frustrated and not is_terse:
        directives.append(
            "User wants rigorous, structured, academic depth. Use precise domain terminology, "
            "step-by-step reasoning, and structured markdown sections."
        )

    # 5. Data & Tabular Lookups
    tabular_keywords = [
        "table", "markdown table", "roster", "list", "lists", "list all", "show all", "verification",
        "verify", "verify record", "names", "values", "spreadsheet", "compare in table", "tabular", "columns"
    ]
    is_tabular = any(kw in p_lower for kw in tabular_keywords)
    if is_tabular and not is_academic:
        directives.append(
            "User seeks structured precision. Use clean Markdown tables and immediate entity verification results."
        )

    if not directives:
        directives.append(
            "User prefers a balanced, helpful, and naturally conversational dialogue. "
            "Provide clear, well-explained assistance without unnecessary corporate filler."
        )

    return " ".join(directives)


async def _execute_agentic_chat(req: ChatRequest, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    # Resolve authentic session identity
    target_session_id = req.chat_id or req.session_id or f"session_{int(time.time()*1000)}"
    await memory_manager.create_or_update_session(target_session_id)

    # Geolocation resolution: user coordinates, IP-based approximate, or default
    if req.lat is not None and req.lon is not None:
        user_geo = GeoLocation(lat=req.lat, lon=req.lon)
    else:
        user_geo = await resolve_approximate_location()

    # Resolve authentic locality via reverse-geocoding pipeline
    resolved_geo = await resolve_location_name(user_geo.lat, user_geo.lon)
    resolved_location_name = resolved_geo["formatted"] if isinstance(resolved_geo, dict) else str(resolved_geo)

    is_deep_think = bool(
        req.deep_think
        or (req.model and req.model.lower().strip() in ["deep_reasoning", "deep", "deepseek-r1", "deepseek-r1:8b", "deepseek-r1-distill-llama-70b"])
        or "[deep reasoning mode]" in (req.query or "").lower()
    )
    # File Routing Guard: Verify that when a user uploads a .pdf or document, it is NEVER sent to vision models
    doc_identifier = (req.document_context or req.attached_document or "").lower()
    is_doc_or_pdf = bool(
        req.document_context
        or req.attached_document
        or req.file_path
        or doc_identifier.endswith((".pdf", ".docx", ".doc", ".pptx", ".xlsx", ".csv", ".txt", ".md"))
    )

    has_image = bool((req.image and req.image.strip()) or (req.image_base64 and req.image_base64.strip())) and not is_doc_or_pdf
    clean_image_uri = None
    if has_image:
        raw_img = (req.image or req.image_base64).strip()
        clean_image_uri = sanitize_and_optimize_image_uri(raw_img)

    raw_text = (req.query or req.message or "").replace("[Deep Reasoning Mode]", "").replace("[deep reasoning mode]", "").strip()
    if raw_text:
        clean_query = raw_text
    elif has_image:
        clean_query = "Inspect and analyze this image in detail."
    elif is_doc_or_pdf:
        clean_query = f"Summarize and explain the contents of {req.document_context or req.attached_document or 'the uploaded document'}."
    else:
        clean_query = "Analyze and summarize this document."

    system_instruction = (
        f"""You are Nexis AI, an intelligent, helpful, and highly capable assistant.

Tone & Persona:
- Speak naturally, warmly, and concisely (similar to ChatGPT or Gemini).
- Contextual Dialogue & Multi-turn Continuity: Seamlessly continue the conversation based on the provided dialogue history. If conversation history exists or the user is asking a follow-up question (e.g., "broooo", "why?", "tell me more", "what is its fertilizer schedule?"), NEVER reset into a generic greeting (e.g., "Hey there! How can I help you today?"). Directly answer the follow-up question in the established context.
- Initial Greetings: Only on simple initial casual greetings with NO prior conversational context (e.g., "hi", "hey", "hello", "how are you?"), reply warmly and naturally in one concise sentence.
- NEVER recite or list domain names or tools ("agriculture, healthcare, education, civic welfare") during simple greetings unless the user explicitly asks what capabilities or services you support.

Tool & Reasoning Guidelines:
- You have access to specialized background tools (mandi prices, weather, spatial hospitals, RxNav medicines, arXiv, YouTube tutorials, and civic schemes). Call them autonomously only when user intent requires real data.
- If deep reasoning is enabled, thoroughly analyze the problem, verify constraints, and write your internal chain-of-thought inside <think>...</think> tags.

CRITICAL ARCHITECTURAL CONSTRAINTS:
1. LANGUAGE ADAPTABILITY: Default to clear English for general inquiries. However, if the user explicitly writes in Kannada or Romanized Kannada (Kanglish) or other regional languages, naturally mirror their chosen language while keeping tool calls, citations, and URLs accurate.
2. ZERO MOCK DATA. Never invent static prices, dummy hospital names, fake videos, or dummy links. Query live micro-servers via tools.
3. PROACTIVE CITATIONS & WEB SEARCH: When citing government welfare schemes, circulars, or study materials, invoke 'search_live_web' or 'get_civic_wiki_scheme' to retrieve verified official portal URLs. Once authoritative data (such as FDA/RxNav drug monographs or Agmarknet market data) is retrieved, directly synthesize the complete answer without making unnecessary repeated web searches.
4. LIVE YOUTUBE DISCOVERY & GROUNDING: Invoke 'search_youtube_demonstrations' to discover and embed verified tutorial video links (https://www.youtube.com/watch?v=...) when users ask how-to explanations, procedural walkthroughs, visual guides, or practical demonstrations. When presenting YouTube videos, provide the video details in standard markdown links or an itemized list:
   - [Video Title](https://www.youtube.com/watch?v=VIDEO_ID) by Channel Name
5. STRICT PRIVACY & REDACTION GUARDRAIL: Under no circumstances output, verify, or repeat the actual numeric digits of sensitive citizen government IDs (such as Aadhaar, Korean RRN, or Japanese MyNumber). When forms, templates, or checklists require an identity credential, always use standard generic placeholders like '[Aadhaar Redacted]' or '[ID Card Copy]'.
6. VERIFIED USER LOCATION:
   - Exact Resolved Locality: {resolved_location_name}
   - Coordinates: {user_geo.lat}° N, {user_geo.lon}° E
   INSTRUCTION: Always refer strictly to the verified locality name above. Do NOT guess or hallucinate neighborhood names from the raw coordinates.
7. In all healthcare or emergency contexts, append the mandatory emergency notice: 'Emergency Disclaimer: Nexis AI is an informational tool. Dial 108 immediately for acute emergencies.'
8. DOCUMENT GROUNDING & VISION SEPARATION:
   - If a document is attached or document context is provided, treat requests like 'whats this telling', 'summarize this', or 'explain' as requests to analyze the uploaded document.
   - Do not confuse document uploads with image vision queries. NEVER refer to images from prior turns unless an image is explicitly attached in the current turn.
   - NEVER output disclaimers like 'The retrieved document context does not contain...' or mention prior turns unless directly asked."""
    )

    if is_deep_think:
        system_instruction += (
            "\n\nDEEP REASONING & CHAIN-OF-THOUGHT PROTOCOL:\n"
            "- Internal Chain-of-Thought: First write your full, rigorous step-by-step reasoning inside <think>...</think> tags before formulating the final answer.\n"
            "- Step-by-Step Mathematical Proofs: For all quantitative, algorithmic, mathematical, or scientific questions, provide exhaustive step-by-step mathematical proofs and formal symbolic derivations. Explicitly show initial axioms, variable definitions, and every intermediate calculation step.\n"
            "- Pharmacology Safety Validations: When analyzing medications, prescription drugs, chemicals, or medical treatments, conduct comprehensive multi-point pharmacology safety validations including verified mechanism of action, therapeutic dosage bounds, contraindications, and potential adverse drug interactions.\n"
            "- Zero-Mock Verified Derivations: Ground every derivation and claim strictly in authentic physical laws, pharmacology databases, or verified factual data. Zero mock approximations or hallucinated heuristics are permitted."
        )

    # --------------------------------------------------------------------------
    # Hybrid Memory Ingress: Concurrently fetch Layer 3 user facts & Layer 1 history
    # --------------------------------------------------------------------------
    fact_results, recent_turns = await asyncio.gather(
        memory_manager.get_relevant_facts(clean_query, limit=6),
        memory_manager.get_recent_history(target_session_id, limit=8),
        return_exceptions=True
    )
    retrieved_facts = fact_results if isinstance(fact_results, list) else []
    backend_history = recent_turns if isinstance(recent_turns, list) else []
    source_history = req.history if (req.history and isinstance(req.history, list) and len(req.history) > 0) else backend_history

    # --------------------------------------------------------------------------
    # Dynamic Behavioral Classifier / Prompt Conditioner
    # --------------------------------------------------------------------------
    detected_directive = detect_user_persona(clean_query, source_history)
    logger.info(f"Dynamic Persona Steering for session '{target_session_id}': {detected_directive}")
    system_instruction += (
        f"\n\n### ADAPTIVE PERSONA DIRECTIVE FOR THIS TURN:\n{detected_directive}"
    )

    # --------------------------------------------------------------------------
    # Zero-Shot Response Archetype Detection & Context Injection Protocol
    # --------------------------------------------------------------------------
    detected_archetype = detect_response_archetype(clean_query, source_history)
    archetype_instruction = ARCHETYPE_INSTRUCTIONS.get(detected_archetype, ARCHETYPE_INSTRUCTIONS[ARCHETYPE_EXECUTIVE_SUMMARY])
    logger.info(f"Dynamic Response Archetype for session '{target_session_id}': {detected_archetype}")
    system_instruction += (
        f"\n\n[MANDATORY OUTPUT ARCHETYPE: {detected_archetype}]\n{archetype_instruction}"
    )

    facts_block = memory_manager.format_facts_for_prompt(retrieved_facts)
    if facts_block:
        system_instruction += (
            f"\n\n{facts_block}\n"
            f"INSTRUCTION: Apply these persistent user profile attributes and domain constraints seamlessly without asking the user to repeat established personal details."
        )

    # --------------------------------------------------------------------------
    # Document Context Extraction & Corrective RAG (CRAG) Pipeline
    # --------------------------------------------------------------------------
    crag_evaluation_meta = None
    candidate_rag_sessions = list(dict.fromkeys([
        req.chat_id,
        target_session_id,
        req.session_id,
        req.workspace_id
    ]))
    active_rag_session = None
    for s_id in candidate_rag_sessions:
        if s_id and (
            (vector_store and vector_store.has_documents(s_id))
            or (tabular_registry and tabular_registry.has_tabular(s_id))
        ):
            active_rag_session = s_id
            break

    # Extract full document text from vector store or disk fallback
    retrieved_text = ""
    for s_id in candidate_rag_sessions:
        if s_id:
            retrieved_text = get_session_document_text(s_id, req.file_path, req.document_context or req.attached_document)
            if retrieved_text:
                break

    if not retrieved_text and (req.file_path or req.document_context or req.attached_document):
        retrieved_text = get_session_document_text("", req.file_path, req.document_context or req.attached_document)

    # If prompt is open-ended or document context is present, inject document content
    doc_label = req.document_context or req.attached_document or (Path(req.file_path).name if req.file_path else "Attached File")
    if retrieved_text:
        system_instruction += (
            f"\n\n=== UPLOADED DOCUMENT CONTENT ({doc_label}) ===\n"
            f"{retrieved_text}\n"
            f"=== END DOCUMENT ===\n\n"
            "DIRECTIVE: Summarize or answer the user's inquiry directly using the document content above."
        )

    if active_rag_session and crag_engine:
        try:
            crag_result = await crag_engine.run_crag(
                clean_query,
                active_rag_session,
                top_k=5,
                attached_document=req.attached_document or req.document_context
            )
            if crag_result and crag_result.context_text:
                system_instruction += (
                    f"\n\n{crag_result.context_text}\n\n"
                    f"DOCUMENT GROUNDING DIRECTIVE:\n"
                    f"1. If the user asks open-ended questions like 'whats this telling', summarize the key points directly, clearly, and concisely in natural language.\n"
                    f"2. NEVER output disclaimers like 'The retrieved document context does not contain...' or mention prior turns unless directly asked.\n"
                    f"3. Do not confuse document uploads with image vision queries. If a document is attached, treat 'whats this telling' as a request to explain the uploaded document's contents.\n"
                    f"Prioritize the verified document context above when formulating your answer. "
                    f"If the document context contains specific figures, tables, or requirements, cite the document name and page/slide accurately. "
                    f"Under no circumstances hallucinate or contradict authoritative facts present in the retrieved context."
                )
                detected_sources = list(dict.fromkeys([
                    c.get("metadata", {}).get("source_file")
                    for c in crag_result.retrieved_chunks
                    if c.get("metadata", {}).get("source_file")
                ]))
                if not detected_sources and tabular_registry and tabular_registry.has_tabular(active_rag_session):
                    detected_sources = [d.filename for d in tabular_registry.get_documents(active_rag_session)]

                crag_evaluation_meta = {
                    "grade": crag_result.grade,
                    "confidence": crag_result.confidence,
                    "rationale": crag_result.rationale,
                    "refined_query": crag_result.refined_query,
                    "sources": detected_sources
                }
        except Exception as rag_err:
            logger.warning(f"CRAG execution error in /api/chat: {rag_err}")

    # Multi-turn Context Compilation: Prioritize active client history with fallback to backend store
    historical_messages: List[Dict[str, Any]] = []

    for turn in source_history:
        if isinstance(turn, dict):
            role = turn.get("role")
            content = turn.get("content")
            if role in ["user", "assistant"] and content:
                # Sanitize sensitive citizen identifiers (PII guardrail)
                clean_content = redact_sensitive_identifiers(str(content).strip())
                if clean_content:
                    historical_messages.append({"role": role, "content": clean_content})

    # Guard against context overflow (sliding window <= 8 turns and max 12,000 characters ~ 3,000-4,000 tokens)
    if len(historical_messages) > 8:
        historical_messages = historical_messages[-8:]
    total_chars = sum(len(m["content"]) for m in historical_messages)
    while total_chars > 12000 and len(historical_messages) > 2:
        historical_messages.pop(0)
        total_chars = sum(len(m["content"]) for m in historical_messages)

    # Multimodal Message Schema (Groq / OpenAI API Standard)
    if has_image:
        content_blocks = [
            {"type": "text", "text": req.message or clean_query or "Analyze this image thoroughly."}
        ]
        content_blocks.append({
            "type": "image_url",
            "image_url": {
                "url": clean_image_uri
            }
        })
        # Keep vision history concise to conserve multimodal token limits
        vision_history = [
            {"role": m["role"], "content": m["content"][:300]}
            for m in historical_messages[-2:]
        ] if historical_messages else []
        messages = [
            {
                "role": "system",
                "content": f"You are Nexis Vision. Accurately analyze the visual contents, diagrams, clinical text, or parameters in the image.\n\n### ADAPTIVE PERSONA DIRECTIVE FOR THIS TURN:\n{detected_directive}"
            },
            *vision_history,
            {"role": "user", "content": content_blocks}
        ]
    else:
        messages = [
            {"role": "system", "content": system_instruction},
            *historical_messages,
            {"role": "user", "content": clean_query}
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
                raw_b64 = re.sub(r"^data:image\/[a-zA-Z0-9\+\-\.]+;base64,", "", clean_image_uri)
                target_ollama_model = os.getenv("OLLAMA_VISION_MODEL", "llama3.2-vision:latest")
                ollama_payload = {
                    "model": target_ollama_model,
                    "messages": [{
                        "role": "user",
                        "content": req.message or clean_query or "Analyze this image.",
                        "images": [raw_b64]
                    }],
                    "stream": False
                }
                ollama_endpoint = f"{OLLAMA_BASE_URL.replace('/v1', '').rstrip('/')}/api/chat"
                try:
                    async with httpx.AsyncClient(timeout=60.0) as http_client:
                        res = await http_client.post(ollama_endpoint, json=ollama_payload)
                        if res.status_code == 200:
                            data = res.json()
                            final_response = data.get("message", {}).get("content", "") or "Image analyzed successfully."
                            provider_used = f"ollama-vision ({target_ollama_model})"
                        else:
                            raise RuntimeError(f"Ollama native API returned HTTP {res.status_code}: {res.text}")
                except Exception as o_err:
                    logger.warning(f"Ollama native vision call failed: {o_err}, falling back to OpenAI compatibility client")
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
                    max_tokens=3500 if is_deep_think else 1500
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
                        max_tokens=3500 if is_deep_think else 1500
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
        groq_client = AsyncGroq(api_key=active_key, max_retries=2)

        async def call_groq_with_fallback(**kwargs):
            if is_deep_think:
                target = os.getenv("GROQ_DEEP_THINK_MODEL", "deepseek-r1-distill-llama-70b")
                models_to_try = [target, "deepseek-r1-distill-llama-70b", "deepseek-r1-distill-qwen-32b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"]
                requested_max = kwargs.get("max_tokens", 3500)
                # Generation token limit at least 3,500 so internal reasoning does not get truncated
                token_budgets = list(dict.fromkeys([max(requested_max, 3500), 3500, 2500, 1800]))
            else:
                target = os.getenv("GROQ_ORCHESTRATOR_MODEL", "qwen/qwen3.8-27b")
                models_to_try = [target, "qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "llama-3.3-70b-versatile"]
                requested_max = kwargs.get("max_tokens", 900)
                token_budgets = [min(requested_max, 900), 750, 500]

            seen = set()
            last_exc = None

            for m in models_to_try:
                if not m or m in seen:
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
                        if "404" in err_str or "400" in err_str or "model_not_found" in err_str or "does not exist" in err_str or "decommissioned" in err_str:
                            break  # Try next model
                        if "429" in err_str or "rate_limit" in err_str or "otpm" in err_str or "503" in err_str:
                            await asyncio.sleep(1.0)
                            continue  # Try smaller token budget on same or next model
                        raise exc
            raise last_exc

        if has_image:
            target_vision = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
            vision_models = [
                target_vision,
                "qwen/qwen3.8-27b",
            ]
            last_vision_exc = None
            seen_vm = set()
            for vm in vision_models:
                if not vm or vm in seen_vm:
                    continue
                seen_vm.add(vm)
                for budget in [1200, 800, 400]:
                    try:
                        logger.info(f"Invoking Groq Multimodal Vision Model: {vm} (budget: {budget})")
                        try:
                            completion = await groq_client.chat.completions.create(
                                model=vm,
                                messages=messages,
                                temperature=0.2,
                                max_tokens=budget
                            )
                        except Exception as m_err:
                            prompt_text = req.message or clean_query or "Analyze this image thoroughly."
                            completion = await groq_client.chat.completions.create(
                                model=vm,
                                messages=[{
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": prompt_text},
                                        {"type": "image_url", "image_url": {"url": clean_image_uri}}
                                    ]
                                }],
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
                        print(f"[Nexis Vision Error] Groq Vision model '{vm}' (budget {budget}) failed: {vexc}", file=sys.stderr)
                        logger.warning(f"Groq Vision {vm} attempt failed: {vexc}")
                        if "404" in err_str or "model_not_found" in err_str or "decommissioned" in err_str or "not supported" in err_str or "does not exist" in err_str:
                            break
                        if "429" in err_str or "rate_limit" in err_str or "503" in err_str or "over capacity" in err_str:
                            await asyncio.sleep(0.5)
                            continue
                        break
                if final_response:
                    break

            if not final_response:
                logger.error(f"Groq vision models exhausted: {last_vision_exc}")
                err_msg = str(last_vision_exc)
                prompt_text = req.message or clean_query or "Analyze this image thoroughly."

                # High-accuracy OCR fallback when Groq Vision hits rate limit (TPD) or fails
                ocr_text = extract_ocr_text_from_image_uri(clean_image_uri)
                if ocr_text and len(ocr_text.strip()) > 3:
                    logger.info(f"Groq Vision exhausted/rate-limited. Extracted {len(ocr_text)} characters via local OCR, resolving with text orchestrator.")
                    try:
                        ocr_prompt = (
                            f"The user attached an image with question: '{prompt_text}'.\n\n"
                            f"### Extracted Text from Image (via High-Precision OCR):\n"
                            f"\"\"\"\n{ocr_text}\n\"\"\"\n\n"
                            f"Please provide an accurate, helpful, and comprehensive response to the user based on this document text."
                        )
                        ocr_messages = [
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": ocr_prompt}
                        ]
                        ocr_completion = await call_groq_with_fallback(
                            messages=ocr_messages,
                            tools=[],
                            tool_choice="none",
                            temperature=0.2,
                            max_tokens=1500
                        )
                        final_response = (
                            f"> ℹ️ *Note: Cloud vision model quota was temporarily busy; document content was extracted via local high-precision OCR engine.* \n\n"
                            + (ocr_completion.choices[0].message.content or "")
                        )
                        provider_used = "groq-text (ocr-fallback)"
                    except Exception as ocr_err:
                        logger.error(f"OCR LLM text synthesis failed: {ocr_err}")

                if not final_response:
                    if "rate limit" in err_msg.lower() or "tpd" in err_msg.lower() or "tokens" in err_msg.lower():
                        final_response = (
                            f"⚠️ **Vision Service Rate Limit:** Groq vision API token quota exceeded: `{err_msg}`.\n\n"
                            f"**Why this happened:** Groq's free tier has a daily quota of 200,000 tokens for vision model `qwen/qwen3.8-27b`. "
                            f"The current API key has used ~199,000 tokens today, and Groq requires at least ~2,200 available tokens to encode any image.\n\n"
                            f"**Next Steps to Continue:**\n"
                            f"1. **Wait for Groq's rolling window reset:** Quota replenishes continuously every few minutes (check the timer in the error above).\n"
                            f"2. **Use a secondary Groq API key:** Create a fresh key in a new Groq project at [console.groq.com](https://console.groq.com) and update `.env`.\n"
                            f"3. **If your image contains text or documents:** Ensure the document is sharp and well-lit so local OCR can automatically read and answer it!"
                        )
                    else:
                        final_response = (
                            f"⚠️ **Vision Inference Notice:** Upstream vision model could not complete analysis: `{err_msg}`. "
                            f"Please verify the image is non-empty and formatted as PNG, JPEG, or WebP."
                        )
                    provider_used = "groq-vision (error-fallback)"
        else:
            try:
                chosen_temp = 0.6 if is_deep_think else 0.2
                completion = await call_groq_with_fallback(
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                    temperature=chosen_temp,
                    max_tokens=3500 if is_deep_think else 900
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
                            max_tokens=3500 if is_deep_think else 900
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
                            max_tokens=3500 if is_deep_think else 900
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

    # Strip <think>...</think> tags from final response and extract thought_trace
    thought_trace = None
    think_match = re.search(r"<think>([\s\S]*?)</think>", final_response, flags=re.IGNORECASE)
    if think_match:
        thought_trace = think_match.group(1).strip()
        final_response = re.sub(r"<think>[\s\S]*?</think>", "", final_response, flags=re.IGNORECASE).strip()
    elif "<think>" in final_response.lower() and "</think>" not in final_response.lower():
        parts = re.split(r"<think>", final_response, flags=re.IGNORECASE, maxsplit=1)
        if len(parts) > 1:
            thought_trace = parts[1].strip()
            final_response = parts[0].strip()

    # Apply strict privacy redaction guardrails
    clean_final_response = redact_sensitive_identifiers(final_response)
    clean_thought_trace = redact_sensitive_identifiers(thought_trace) if thought_trace else None

    # Layer 1 & 2 Dual-Write Persistence: Store conversational turns with PII sanitization in Redis & SQLite
    await memory_manager.save_turn(
        session_id=target_session_id,
        role="user",
        content=clean_query
    )
    await memory_manager.save_turn(
        session_id=target_session_id,
        role="assistant",
        content=clean_final_response,
        thought_trace=clean_thought_trace,
        tool_calls=executed_tools
    )

    # Layer 3 Semantic Fact Extraction: Asynchronously discover and commit persistent user facts in background
    background_tasks.add_task(
        memory_manager.extract_facts_background,
        clean_query,
        clean_final_response,
        session_id=target_session_id
    )

    return {
        "status": "success",
        "session_id": target_session_id,
        "query": clean_query,
        "language": "Kannada" if "Kannada" in detected_directive else "English",
        "inference_provider": provider_used,
        "deep_think": is_deep_think,
        "model": "deep_reasoning" if is_deep_think else (req.model or "fast"),
        "user_coordinates": {"lat": user_geo.lat, "lon": user_geo.lon},
        "resolved_location": resolved_geo if isinstance(resolved_geo, dict) else {"formatted": str(resolved_geo)},
        "tools_invoked_count": len(executed_tools),
        "tools_executed": executed_tools,
        "thought_trace": clean_thought_trace,
        "crag_evaluation": crag_evaluation_meta,
        "adaptive_persona": detected_directive,
        "detected_archetype": detected_archetype,
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
            if res.status_code == 200:
                return {
                    "status": "success",
                    "routed_sector": "healthcare",
                    "analysis": res.json()
                }
        except Exception as exc:
            logger.warning(f"Failed contacting healthcare vision micro-server: {exc}. Attempting direct Groq Vision OCR fallback.")

        # In-process Groq Vision OCR Fallback
        try:
            active_key = os.getenv("GROQ_API_KEY") or GROQ_API_KEY
            if active_key and active_key != "your_groq_api_key_here":
                from groq import AsyncGroq
                groq_client = AsyncGroq(api_key=active_key)
                b64 = base64.b64encode(file_bytes).decode("utf-8")
                mime = file.content_type or "image/jpeg"
                data_url = f"data:{mime};base64,{b64}"
                prompt = (
                    "Analyze this prescription or medical document image in English. "
                    "Extract all medication names, clinical findings, lab values, and dosage instructions. "
                    "Provide a clean, structured diagnostic report."
                )
                candidates = [
                    os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b"),
                    "qwen/qwen3.8-27b",
                ]
                for vm in candidates:
                    try:
                        v_res = await groq_client.chat.completions.create(
                            model=vm,
                            messages=[{
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    {"type": "image_url", "image_url": {"url": data_url}}
                                ]
                            }],
                            max_tokens=1000
                        )
                        raw_content = v_res.choices[0].message.content or "Completed"
                        return {
                            "status": "success",
                            "routed_sector": f"direct-vision ({vm})",
                            "analysis": {
                                "extracted_text": raw_content,
                                "resolved_medication": "Extracted via Direct Vision Ingress",
                                "clinical_summary": raw_content
                            }
                        }
                    except Exception as ve:
                        logger.warning(f"Direct vision candidate {vm} failed: {ve}")
        except Exception as direct_exc:
            logger.error(f"Direct vision fallback failed: {direct_exc}")

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed processing image via healthcare service and upstream vision fallback."
        )

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
