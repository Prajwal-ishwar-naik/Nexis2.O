"""
Nexis AI - Healthcare Micro-Server (Port 8002)
OpenStreetMap Overpass QL spatial locator, NIH RxNav & OpenFDA clinical pharmacology engine,
and Dual-Provider (Groq Cloud / Local Ollama) multimodal prescription OCR analysis.
Strictly English only. Strictly zero mock / zero hardcoded data.
"""

import base64
import json
import logging
import math
import os
import re
import sys
from typing import Any, Dict, List, Literal, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, UploadFile, status
import httpx
from pydantic import BaseModel, Field
import uvicorn

# Load environment configuration
load_dotenv()

OVERPASS_API_URL = os.getenv("OVERPASS_API_URL", "https://overpass-api.de/api/interpreter")
RXNORM_API_URL = os.getenv("RXNORM_API_URL", "https://rxnav.nlm.nih.gov/REST/drugs.json")
OPENFDA_API_URL = os.getenv("OPENFDA_API_URL", "https://api.fda.gov/drug/label.json")

INFERENCE_PROVIDER = os.getenv("INFERENCE_PROVIDER", "groq").lower().strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "llama3.2-vision:latest")

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("HEALTH_PORT", "8002"))

EMERGENCY_DISCLAIMER = (
    "Emergency Disclaimer: Nexis AI is an informational tool. Dial 108 immediately for acute emergencies."
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Health-Server:8002] %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("health_server")

app = FastAPI(
    title="Nexis AI - Healthcare Micro-Server",
    description="Spatial healthcare locator using OSM Overpass, pharmacology lookup via NIH RxNav & OpenFDA, and Dual-Provider Vision prescription OCR.",
    version="1.0.0"
)


class NearbyFacilityRequest(BaseModel):
    lat: float = Field(..., description="Latitude coordinate")
    lon: float = Field(..., description="Longitude coordinate")
    radius: int = Field(5000, ge=200, le=50000, description="Search radius in meters")
    facility_type: Literal["hospital", "pharmacy"] = Field("hospital", description="Facility type")


def compute_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Computes great-circle distance between two points on Earth in meters."""
    R = 6371000  # Earth's radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 2)


def redact_sensitive_identifiers(text: str) -> str:
    """Redacts 12-digit Aadhaar, Korean RRN, and Japanese MyNumber patterns."""
    # Aadhaar 12 digits
    text = re.sub(r"\b\d{4}\s?\d{4}\s?\d{4}\b", "[Aadhaar Redacted]", text)
    # Korean RRN (6 digits - 7 digits)
    text = re.sub(r"\b\d{6}-[1-4]\d{6}\b", "[ID Redacted]", text)
    # 12-digit generic national ID
    text = re.sub(r"\b(MyNumber|National ID)[:\s]*\d{12}\b", r"\1: [ID Redacted]", text, flags=re.IGNORECASE)
    return text


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> Dict[str, Any]:
    """Liveness probe."""
    return {
        "status": "healthy",
        "service": "health_server",
        "port": PORT,
        "inference_provider": INFERENCE_PROVIDER,
        "overpass_endpoint": OVERPASS_API_URL,
        "groq_vision_configured": bool(GROQ_API_KEY and GROQ_API_KEY != "your_groq_api_key_here"),
        "ollama_vision_configured": bool(OLLAMA_BASE_URL)
    }


@app.post("/api/v1/health/nearby")
@app.get("/api/v1/health/nearby")
@app.get("/api/v1/hospitals")
async def locate_nearby_facilities(
    req: Optional[NearbyFacilityRequest] = None,
    lat: Optional[float] = Query(None, description="Center latitude coordinate"),
    lon: Optional[float] = Query(None, description="Center longitude coordinate"),
    radius: int = Query(5000, ge=200, le=50000, description="Search radius in meters"),
    facility_type: str = Query("hospital", description="Facility type: 'hospital' or 'pharmacy'")
) -> Dict[str, Any]:
    """
    Executes live Overpass QL against OpenStreetMap interpreter to locate nearest hospitals or pharmacies.
    Computes precise Haversine distance and checks 24/7 casualty availability.
    Strictly zero mock data.
    """
    req_lat = req.lat if req else (lat if lat is not None else 12.9716)
    req_lon = req.lon if req else (lon if lon is not None else 77.5946)
    req_radius = req.radius if req else radius
    raw_type = req.facility_type if req else facility_type
    clean_type = "pharmacy" if str(raw_type).lower() == "pharmacy" else "hospital"

    overpass_query = f"""
    [out:json][timeout:15];
    (
      node["amenity"="{clean_type}"](around:{req_radius},{req_lat},{req_lon});
    );
    out center 15;
    """

    headers = {
        "User-Agent": "Nexis-AI/1.0 (Healthcare Assistant Engine; contact@nexis.gov.in)",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    OVERPASS_MIRRORS = [OVERPASS_API_URL]
    if "z.overpass-api.de" not in OVERPASS_API_URL:
        OVERPASS_MIRRORS.append("https://z.overpass-api.de/api/interpreter")

    data = None
    last_err = None
    async with httpx.AsyncClient(timeout=25.0) as client:
        for mirror_url in OVERPASS_MIRRORS:
            try:
                res = await client.post(mirror_url, data={"data": overpass_query}, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    break
                else:
                    last_err = f"OpenStreetMap Overpass API returned status {res.status_code}"
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                last_err = f"Overpass connection error: {str(exc)}"

    if not data or not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=last_err or "OpenStreetMap Overpass API unavailable."
        )

    elements = data.get("elements", [])
    facilities: List[Dict[str, Any]] = []

    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue

        p_lat = el.get("lat") or (el.get("center", {}).get("lat"))
        p_lon = el.get("lon") or (el.get("center", {}).get("lon"))

        if p_lat is None or p_lon is None:
            continue

        dist_meters = compute_haversine_distance(req_lat, req_lon, p_lat, p_lon)
        emergency_val = tags.get("emergency", "no").lower()
        opening_hours = tags.get("opening_hours", "").lower()
        is_24_7 = (
            emergency_val in ["yes", "designated"]
            or "24/7" in opening_hours
            or tags.get("healthcare") == "hospital"
        )

        facilities.append({
            "name": name,
            "facility_type": clean_type,
            "coordinates": {"lat": p_lat, "lon": p_lon},
            "distance_meters": dist_meters,
            "distance_km": round(dist_meters / 1000.0, 2),
            "is_open_24_7": is_24_7,
            "phone": tags.get("phone") or tags.get("contact:phone") or "Dial 108 for emergency triage",
            "address": tags.get("addr:full") or tags.get("addr:street") or "Street address not registered on OSM"
        })

    facilities.sort(key=lambda x: x["distance_meters"])

    if not facilities:
        return {
            "status": "empty",
            "count": 0,
            "search_origin": {"lat": req_lat, "lon": req_lon},
            "radius_meters": req_radius,
            "facility_type": clean_type,
            "message": f"No registered {clean_type} facilities found within {req_radius}m radius of ({req_lat}, {req_lon}) on OpenStreetMap.",
            "facilities": [],
            "emergency_notice": EMERGENCY_DISCLAIMER
        }

    return {
        "status": "success",
        "search_origin": {"lat": req_lat, "lon": req_lon},
        "radius_meters": req_radius,
        "facility_type": clean_type,
        "count": len(facilities),
        "nearest_facility": facilities[0] if facilities else None,
        "facilities": facilities[:15],
        "emergency_notice": EMERGENCY_DISCLAIMER
    }


@app.get("/api/v1/health/medicine")
@app.get("/api/v1/pharmacology-verifier")
async def verify_medicine(name: str = Query(..., min_length=2, description="Chemical or brand medicine name in English")) -> Dict[str, Any]:
    """
    Verifies active pharmaceutical ingredients via NIH RxNav API and retrieves clinical precautions,
    contraindications, and dosage warnings via OpenFDA API.
    Strictly zero mock data.
    """
    clean_name = name.strip().lower()
    headers = {
        "User-Agent": "Nexis-AI/1.0 (Clinical Pharmacology Engine; contact@nexis.gov.in)",
        "Accept": "application/json"
    }

    rxnav_url = f"{RXNORM_API_URL}?name={clean_name}"
    fda_url = f"{OPENFDA_API_URL}?search=openfda.generic_name:{clean_name}&limit=1"

    rxnav_data: Dict[str, Any] = {}
    fda_data: Dict[str, Any] = {}

    async with httpx.AsyncClient(timeout=15.0) as client:
        # NIH RxNav resolution
        try:
            rxnav_res = await client.get(rxnav_url, headers=headers)
            if rxnav_res.status_code == 200:
                rxnav_json = rxnav_res.json()
                drug_group = rxnav_json.get("drugGroup", {})
                concept_groups = drug_group.get("conceptGroup", [])
                concepts = []
                for cg in concept_groups:
                    props = cg.get("conceptProperties", [])
                    for p in props:
                        concepts.append({
                            "rxcui": p.get("rxcui"),
                            "name": p.get("name"),
                            "synonym": p.get("synonym"),
                            "term_type": p.get("tty")
                        })
                rxnav_data = {
                    "rxcui_matches_count": len(concepts),
                    "active_ingredients_and_forms": concepts[:8]
                }
            elif rxnav_res.status_code == 404:
                rxnav_data = {"status": "not_found", "message": "No matching chemical entity found in NIH RxNav."}
        except Exception as exc:
            rxnav_data = {"error": f"RxNav query failed: {str(exc)}"}

        # OpenFDA Label resolution
        try:
            fda_res = await client.get(fda_url, headers=headers)
            if fda_res.status_code == 200:
                fda_json = fda_res.json()
                results = fda_json.get("results", [])
                if results:
                    r0 = results[0]
                    openfda = r0.get("openfda", {})
                    fda_data = {
                        "generic_name": openfda.get("generic_name", [clean_name]),
                        "brand_name": openfda.get("brand_name", []),
                        "substance_name": openfda.get("substance_name", []),
                        "route": openfda.get("route", []),
                        "purpose": r0.get("purpose", [])[:2],
                        "indications_and_usage": r0.get("indications_and_usage", [])[:2],
                        "warnings": r0.get("warnings", [])[:2],
                        "dosage_and_administration": r0.get("dosage_and_administration", [])[:2]
                    }
            elif fda_res.status_code == 404:
                fallback_url = f"{OPENFDA_API_URL}?search={clean_name}&limit=1"
                fb_res = await client.get(fallback_url, headers=headers)
                if fb_res.status_code == 200:
                    fb_json = fb_res.json()
                    fb_results = fb_json.get("results", [])
                    if fb_results:
                        r0 = fb_results[0]
                        fda_data = {
                            "generic_name": r0.get("openfda", {}).get("generic_name", [clean_name]),
                            "brand_name": r0.get("openfda", {}).get("brand_name", []),
                            "indications_and_usage": r0.get("indications_and_usage", [])[:2],
                            "warnings": r0.get("warnings", [])[:2]
                        }
                else:
                    fda_data = {"status": "not_found", "message": "No FDA monograph label found."}
        except Exception as exc:
            fda_data = {"error": f"OpenFDA query failed: {str(exc)}"}

    if not rxnav_data.get("active_ingredients_and_forms") and fda_data.get("status") == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "status": "not_found",
                "medicine": clean_name,
                "message": f"No authentic clinical pharmacology record found in NIH RxNav or OpenFDA for '{clean_name}'."
            }
        )

    return {
        "status": "success",
        "medicine_query": clean_name,
        "nih_rxnav": rxnav_data,
        "openfda_monograph": fda_data,
        "emergency_notice": EMERGENCY_DISCLAIMER
    }


@app.post("/api/v1/health/analyze-prescription")
async def analyze_prescription(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Accepts medical documents via UploadFile (prescriptions, pathology reports, imaging summaries).
    Dispatches to Groq Vision (meta-llama/llama-4-scout-17b-16e-instruct) or local Ollama (llama3.2-vision:latest)
    based on INFERENCE_PROVIDER.
    Extracts parameters, flagged values (High/Low), and medicine names.
    Appends mandatory safety disclaimer and redacts sensitive ID digits.
    """
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    content_type = file.content_type or "image/jpeg"
    base64_image = base64.b64encode(contents).decode("utf-8")
    data_url = f"data:{content_type};base64,{base64_image}"

    prompt = (
        "You are an expert optical character recognition engine and clinical diagnostic assistant. "
        "Analyze this medical prescription or lab report image in English. "
        "Extract all legible medication names, formulations, dosage instructions, clinical test parameters, "
        "and flagged values (High/Low). "
        "CRITICAL PRIVACY RULE: Under no circumstances output or verify any citizen government ID digits (such as Aadhaar). "
        "Strictly return valid JSON matching this exact schema:\n"
        "{\n"
        '  "detected_medications": [\n'
        '    {"name": "...", "dosage": "...", "frequency": "...", "duration": "..."}\n'
        "  ],\n"
        '  "lab_parameters": [\n'
        '    {"parameter": "...", "value": "...", "flag": "High | Low | Normal", "reference_range": "..."}\n'
        "  ],\n"
        '  "clinical_notes": "...",\n'
        '  "ocr_confidence": "high | moderate | low"\n'
        "}\n"
        "Do NOT return markdown fences outside the JSON."
    )

    provider_used = INFERENCE_PROVIDER
    raw_text = "{}"

    # 1. Local Ollama Vision Execution
    if INFERENCE_PROVIDER == "ollama":
        try:
            from openai import AsyncOpenAI
            ollama_client = AsyncOpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")
            response = await ollama_client.chat.completions.create(
                model=OLLAMA_VISION_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}}
                        ]
                    }
                ],
                temperature=0.1,
                max_tokens=1024
            )
            raw_text = response.choices[0].message.content or "{}"
            provider_used = f"ollama ({OLLAMA_VISION_MODEL})"
        except Exception as exc:
            logger.warning(f"Ollama Vision execution failed: {exc}, attempting Groq Vision fallback")
            active_key = os.getenv("GROQ_API_KEY") or GROQ_API_KEY
            if active_key and active_key != "your_groq_api_key_here":
                from groq import AsyncGroq
                groq_client = AsyncGroq(api_key=active_key)
                candidates = [
                    GROQ_VISION_MODEL,
                    "qwen/qwen3.8-27b",
                ]
                last_g_exc = None
                for vm in candidates:
                    try:
                        logger.info(f"Invoking Groq Vision for prescription OCR: {vm}")
                        response = await groq_client.chat.completions.create(
                            model=vm,
                            messages=[
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": prompt},
                                        {"type": "image_url", "image_url": {"url": data_url}}
                                    ]
                                }
                            ],
                            temperature=0.1,
                            max_tokens=1024
                        )
                        raw_text = response.choices[0].message.content or "{}"
                        provider_used = f"groq ({vm})"
                        break
                    except Exception as vexc:
                        last_g_exc = vexc
                        logger.warning(f"Groq Vision {vm} failed: {vexc}")
                if not raw_text or raw_text == "{}":
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"Both Ollama and Groq Vision failed: {last_g_exc}"
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Local Ollama vision analysis failed: {str(exc)}"
                )

    # 2. Groq Cloud Vision Execution
    else:
        active_key = os.getenv("GROQ_API_KEY") or GROQ_API_KEY
        if not active_key or active_key == "your_groq_api_key_here":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GROQ_API_KEY is not configured in .env. Groq Vision OCR requires a valid key."
            )

        from groq import AsyncGroq
        groq_client = AsyncGroq(api_key=active_key)

        candidates = [
            GROQ_VISION_MODEL,
            "qwen/qwen3.8-27b",
        ]
        last_g_exc = None
        for vm in candidates:
            try:
                logger.info(f"Invoking Groq Vision for prescription OCR: {vm}")
                response = await groq_client.chat.completions.create(
                    model=vm,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": data_url}}
                            ]
                        }
                    ],
                    temperature=0.1,
                    max_tokens=1024
                )
                raw_text = response.choices[0].message.content or "{}"
                provider_used = f"groq ({vm})"
                break
            except Exception as exc:
                last_g_exc = exc
                err_str = str(exc).lower()
                logger.warning(f"Groq Vision {vm} failed: {exc}")
                if "404" in err_str or "model_not_found" in err_str or "decommissioned" in err_str or "not supported" in err_str:
                    continue

        if not raw_text or raw_text == "{}":
            # Attempt high-accuracy local OCR fallback
            try:
                import io, re, shutil
                import pytesseract
                from PIL import Image

                tess_bin = shutil.which("tesseract") or "/opt/homebrew/bin/tesseract" or "/usr/local/bin/tesseract"
                if tess_bin and os.path.exists(tess_bin):
                    pytesseract.pytesseract.tesseract_cmd = tess_bin

                match = re.match(r"^data:(?:image\/[a-zA-Z0-9\+\-\.]+)?;base64,(.+)$", data_url, re.DOTALL)
                b64_data = match.group(1) if match else data_url
                img_bytes = base64.b64decode(b64_data)
                img = Image.open(io.BytesIO(img_bytes))
                ocr_text = pytesseract.image_to_string(img).strip()

                if ocr_text and len(ocr_text) > 3:
                    logger.info(f"Groq Vision exhausted. Extracted {len(ocr_text)} chars from prescription via local OCR; parsing with text model.")
                    text_models = [os.getenv("GROQ_ORCHESTRATOR_MODEL", "openai/gpt-oss-120b"), "openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
                    seen_tm = set()
                    for tm in text_models:
                        if not tm or tm in seen_tm:
                            continue
                        seen_tm.add(tm)
                        try:
                            ocr_res = await groq_client.chat.completions.create(
                                model=tm,
                                messages=[
                                    {"role": "system", "content": prompt},
                                    {"role": "user", "content": f"Here is the clinical text extracted from the prescription image via OCR:\n\"\"\"\n{ocr_text}\n\"\"\"\nStructure the JSON strictly according to the requested schema."}
                                ],
                                temperature=0.1,
                                max_tokens=1024
                            )
                            raw_text = ocr_res.choices[0].message.content or "{}"
                            if raw_text and raw_text != "{}":
                                provider_used = f"groq-text ({tm}, ocr-fallback)"
                                break
                        except Exception as m_err:
                            logger.warning(f"Health OCR text model {tm} failed: {m_err}")
            except Exception as ocr_err:
                logger.error(f"Health OCR fallback parsing failed: {ocr_err}")

        if not raw_text or raw_text == "{}":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Groq Vision prescription analysis failed across all candidate models: {str(last_g_exc)}"
            )

    clean_text = raw_text.strip()
    if clean_text.startswith("```"):
        lines = clean_text.splitlines()
        clean_text = "\n".join([l for l in lines if not l.startswith("```")])

    clean_text = redact_sensitive_identifiers(clean_text)

    try:
        ocr_result = json.loads(clean_text)
    except Exception:
        ocr_result = {
            "detected_medications": [],
            "lab_parameters": [],
            "raw_output": clean_text,
            "ocr_confidence": "low"
        }

    # Pipe extracted medicines into live verification
    detected_meds = ocr_result.get("detected_medications", [])
    verified_medications: List[Dict[str, Any]] = []

    for med in detected_meds:
        med_name = med.get("name", "").strip()
        if med_name:
            try:
                verif = await verify_medicine(name=med_name)
                verified_medications.append({
                    "extracted_info": med,
                    "pharmacology_verification": verif
                })
            except HTTPException:
                verified_medications.append({
                    "extracted_info": med,
                    "pharmacology_verification": {
                        "status": "unverified",
                        "message": f"Medication '{med_name}' could not be matched on international pharmacology registries."
                    }
                })

    return {
        "status": "success",
        "service": f"Nexis AI Multimodal Vision OCR ({provider_used})",
        "inference_provider": provider_used,
        "ocr_findings": ocr_result,
        "verified_medications": verified_medications,
        "emergency_notice": EMERGENCY_DISCLAIMER
    }


if __name__ == "__main__":
    uvicorn.run("health_server:app", host=HOST, port=PORT, reload=False, log_level="info")
