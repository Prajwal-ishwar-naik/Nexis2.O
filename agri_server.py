"""
Nexis AI - Agriculture Micro-Server (Port 8001)
Queries official Data.gov.in Agmarknet API for live mandi prices and arrivals,
and Open-Meteo for real agro-meteorological metrics and agricultural advisories.
Strictly English only. Strictly zero mock / zero hardcoded data.
"""

import logging
import os
import sys
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, status
import httpx
import uvicorn

# Load environment variables
load_dotenv()

DATA_GOV_API_KEY = os.getenv("DATA_GOV_API_KEY", "")
AGMARKNET_RESOURCE_ID = os.getenv("AGMARKNET_RESOURCE_ID", "9ef84268-d588-465a-a308-a864a43d0070")
OPEN_METEO_BASE_URL = os.getenv("OPEN_METEO_BASE_URL", "https://api.open-meteo.com/v1/forecast")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("AGRI_PORT", "8001"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Agri-Server:8001] %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("agri_server")

app = FastAPI(
    title="Nexis AI - Agri Micro-Server",
    description="Live Agmarknet commodity market price engine and Open-Meteo agricultural advisory service.",
    version="1.0.0"
)


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> Dict[str, Any]:
    """Liveness and configuration probe."""
    return {
        "status": "healthy",
        "service": "agri_server",
        "port": PORT,
        "upstream_configured": bool(DATA_GOV_API_KEY and AGMARKNET_RESOURCE_ID),
        "data_gov_resource_id": AGMARKNET_RESOURCE_ID
    }


def calculate_mandi_statistics(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Computes runtime statistics (min, max, average modal price) across returned records."""
    prices: List[float] = []
    markets = set()

    for item in records:
        raw_price = item.get("modal_price")
        if raw_price is not None:
            try:
                val = float(str(raw_price).replace(",", "").strip())
                if val > 0:
                    prices.append(val)
            except (ValueError, TypeError):
                pass
        market_name = item.get("market")
        if market_name:
            markets.add(str(market_name).strip())

    if not prices:
        return {
            "min_modal_price": None,
            "max_modal_price": None,
            "average_modal_price": None,
            "market_count": len(markets),
            "currency": "INR / Quintal"
        }

    return {
        "min_modal_price": round(min(prices), 2),
        "max_modal_price": round(max(prices), 2),
        "average_modal_price": round(sum(prices) / len(prices), 2),
        "market_count": len(markets),
        "records_sampled": len(prices),
        "currency": "INR / Quintal"
    }


@app.get("/api/v1/agri/mandi")
@app.get("/api/v1/mandi")
async def get_mandi_prices(
    commodity: str = Query(..., description="Commodity name (e.g. Tomato, Onion, Potato, Rice, Wheat)"),
    state: Optional[str] = Query("Karnataka", description="Indian state name"),
    limit: int = Query(10, ge=1, le=100, description="Max records to retrieve")
) -> Dict[str, Any]:
    """
    Asynchronously queries official Agmarknet public API on Data.gov.in for live commodity arrivals.
    Computes dynamic runtime statistics (min, max, average modal price) over the returned records.
    """
    if not DATA_GOV_API_KEY:
        logger.error("DATA_GOV_API_KEY is not configured in .env.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Upstream API configuration error: DATA_GOV_API_KEY is missing."
        )

    base_url = f"https://api.data.gov.in/resource/{AGMARKNET_RESOURCE_ID}"
    params: Dict[str, Any] = {
        "api-key": DATA_GOV_API_KEY,
        "format": "json",
        "limit": limit,
        "filters[commodity]": commodity.strip()
    }
    if state and state.strip():
        params["filters[state]"] = state.strip()

    headers = {
        "User-Agent": "Nexis-AI/1.0 (Agriculture Assistant Engine; contact@nexis.gov.in)",
        "Accept": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            logger.info(f"Querying Agmarknet API for commodity='{commodity}', state='{state}', limit={limit}")
            response = await client.get(base_url, params=params, headers=headers)
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Official Data.gov.in Agmarknet API timed out."
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Network connectivity failure to Data.gov.in: {str(exc)}"
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "upstream_status_code": response.status_code,
                "error": "Official Data.gov.in API returned an error.",
                "upstream_response": response.text[:300]
            }
        )

    try:
        payload = response.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Data.gov.in returned invalid JSON payload: {str(exc)}"
        )

    raw_records: List[Dict[str, Any]] = payload.get("records", [])

    if not raw_records:
        return {
            "status": "empty",
            "count": 0,
            "commodity": commodity,
            "state": state,
            "message": f"No live market arrivals recorded for '{commodity}' in '{state}' on Agmarknet today.",
            "statistics": {
                "min_modal_price": None,
                "max_modal_price": None,
                "average_modal_price": None,
                "market_count": 0
            },
            "records": []
        }

    parsed_records: List[Dict[str, Any]] = []
    for item in raw_records:
        parsed_records.append({
            "state": item.get("state"),
            "district": item.get("district"),
            "market": item.get("market"),
            "commodity": item.get("commodity"),
            "variety": item.get("variety"),
            "arrival_date": item.get("arrival_date"),
            "min_price": item.get("min_price"),
            "max_price": item.get("max_price"),
            "modal_price": item.get("modal_price")
        })

    statistics = calculate_mandi_statistics(parsed_records)

    return {
        "status": "success",
        "source": "Agmarknet (Data.gov.in Official API)",
        "count": len(parsed_records),
        "commodity": commodity,
        "state": state,
        "statistics": statistics,
        "records": parsed_records
    }


@app.get("/api/v1/agri/weather")
@app.get("/api/v1/weather")
async def get_agri_weather(
    lat: float = Query(..., description="Farmland latitude coordinate"),
    lon: float = Query(..., description="Farmland longitude coordinate")
) -> Dict[str, Any]:
    """
    Calls Open-Meteo for authentic temperature, relative humidity, rainfall, and wind speed,
    then computes actionable agricultural advisories for irrigation and spraying windows.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,rain,wind_speed_10m"
    }
    headers = {
        "User-Agent": "Nexis-AI/1.0 (AgriWeather-Engine; ops@nexis.gov.in)",
        "Accept": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            logger.info(f"Querying Open-Meteo for lat={lat}, lon={lon}")
            response = await client.get(OPEN_METEO_BASE_URL, params=params, headers=headers)
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Open-Meteo weather API timed out."
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed connecting to Open-Meteo endpoint: {str(exc)}"
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "upstream_status_code": response.status_code,
                "error": "Open-Meteo API rejected request or returned an error.",
                "upstream_response": response.text[:300]
            }
        )

    data = response.json()
    current = data.get("current", {})

    temp = current.get("temperature_2m")
    humidity = current.get("relative_humidity_2m")
    rain = current.get("rain")
    wind_speed = current.get("wind_speed_10m")

    # Agricultural advisory evaluation
    if rain is not None and rain > 1.0:
        irrigation_advisory = "Active rainfall detected (>1.0 mm). Suspend irrigation to prevent waterlogging and root rot."
        irrigation_status = "HALT"
    elif humidity is not None and humidity > 85.0:
        irrigation_advisory = f"High relative humidity ({humidity}%). Reduce irrigation frequency to minimize fungal disease spread."
        irrigation_status = "REDUCE"
    elif humidity is not None and humidity < 40.0 and (rain or 0.0) == 0.0:
        irrigation_advisory = f"Low humidity ({humidity}%) and dry soil conditions. Schedule field irrigation in the early morning or evening."
        irrigation_status = "REQUIRED"
    else:
        irrigation_advisory = "Moderate atmospheric moisture. Maintain standard scheduled crop irrigation."
        irrigation_status = "NORMAL"

    if (wind_speed is not None and wind_speed > 15.0) or (rain is not None and rain > 0.1):
        spray_advisory = f"Unfavorable spraying window. High wind speed ({wind_speed} km/h) causes droplet drift; rainfall ({rain} mm) causes chemical wash-off."
        spray_status = "UNFAVORABLE"
    elif wind_speed is not None and wind_speed <= 12.0 and (rain or 0.0) == 0.0:
        spray_advisory = f"Optimal spraying conditions: low wind ({wind_speed} km/h) and clear conditions ensure maximum foliar uptake."
        spray_status = "OPTIMAL"
    else:
        spray_advisory = f"Marginal spraying conditions with wind at {wind_speed} km/h. Exercise caution with fine spray nozzles."
        spray_status = "MARGINAL"

    return {
        "status": "success",
        "source": "Open-Meteo Live Agrometeorological Engine",
        "coordinates": {"latitude": lat, "longitude": lon},
        "elevation": data.get("elevation"),
        "current_weather": {
            "temperature_celsius": temp,
            "relative_humidity_percent": humidity,
            "precipitation_rain_mm": rain,
            "wind_speed_kmh": wind_speed,
            "timestamp": current.get("time")
        },
        "agricultural_advisories": {
            "irrigation": {
                "status": irrigation_status,
                "advisory": irrigation_advisory
            },
            "chemical_spraying_window": {
                "status": spray_status,
                "advisory": spray_advisory
            }
        }
    }


if __name__ == "__main__":
    uvicorn.run("agri_server:app", host=HOST, port=PORT, reload=False, log_level="info")
