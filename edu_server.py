"""
Nexis AI - Education Micro-Server (Port 8003)
Queries arXiv and OpenLibrary APIs for genuine research papers and textbooks,
and generates structured Socratic pedagogical teaching modules via Groq LLM.
Strictly English only. Strictly zero mock / zero hardcoded data.
"""

import asyncio
import json
import logging
import os
import re
import sys
from typing import Any, Dict, List, Literal, Optional
import xml.etree.ElementTree as ET
import urllib.parse

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, status
import httpx
from pydantic import BaseModel, Field
import uvicorn

# Load environment configuration
load_dotenv()

OPENLIBRARY_API_URL = os.getenv("OPENLIBRARY_API_URL", "https://openlibrary.org/search.json")
ARXIV_API_URL = os.getenv("ARXIV_API_URL", "http://export.arxiv.org/api/query")
WIKI_SEARCH_API = "https://en.wikipedia.org/w/api.php"
INFERENCE_PROVIDER = os.getenv("INFERENCE_PROVIDER", "groq").lower().strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_ORCHESTRATOR_MODEL = os.getenv("GROQ_ORCHESTRATOR_MODEL", "llama-3.3-70b-versatile")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
OLLAMA_ORCHESTRATOR_MODEL = os.getenv("OLLAMA_ORCHESTRATOR_MODEL", "llama3.1:8b")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("EDU_PORT", "8003"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Edu-Server:8003] %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("edu_server")

app = FastAPI(
    title="Nexis AI - Education Micro-Server",
    description="Academic search engine querying arXiv and OpenLibrary APIs, with Socratic teaching agent.",
    version="1.0.0"
)

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


class TeachRequest(BaseModel):
    concept: str = Field(..., min_length=2, description="Academic concept or technical topic to teach in English")
    level: Literal["Beginner", "Undergraduate", "Advanced"] = Field("Undergraduate", description="Pedagogical depth level")


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> Dict[str, Any]:
    """Liveness probe."""
    return {
        "status": "healthy",
        "service": "edu_server",
        "port": PORT,
        "upstreams": {
            "openlibrary": OPENLIBRARY_API_URL,
            "arxiv": ARXIV_API_URL,
            "wikipedia": WIKI_SEARCH_API
        },
        "groq_configured": bool(GROQ_API_KEY and GROQ_API_KEY != "your_groq_api_key_here")
    }


@app.get("/tools/wiki-summary")
@app.post("/tools/wiki-summary")
async def get_wiki_summary(
    query: str = Query(..., description="Academic concept, theory, or historical topic to summarize from Wikipedia")
) -> Dict[str, Any]:
    """
    Calls Wikipedia Action API:
    https://en.wikipedia.org/w/api.php?action=query&format=json&prop=extracts&exintro=True&explaintext=True&titles={query}
    Extracts and returns the clean text summary and page URL.
    """
    clean_query = query.strip()
    if not clean_query:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Query parameter is required.")

    params = {
        "action": "query",
        "format": "json",
        "prop": "extracts",
        "exintro": "1",
        "explaintext": "1",
        "redirects": "1",
        "titles": clean_query
    }
    headers = {
        "User-Agent": "Nexis-AI/1.0 (Wikipedia Knowledge Tool; ops@nexis.gov.in)",
        "Accept": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(WIKI_SEARCH_API, params=params, headers=headers)
    except httpx.TimeoutException:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Wikipedia API timed out.")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed connecting to Wikipedia API: {str(exc)}")

    if res.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Wikipedia API returned an error.")

    data = res.json()
    pages = data.get("query", {}).get("pages", {})

    for page_id, page_data in pages.items():
        if str(page_id) == "-1" or "missing" in page_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"status": "not_found", "message": f"No Wikipedia article found for '{clean_query}'."}
            )

        title = page_data.get("title", clean_query)
        extract = page_data.get("extract", "").strip()
        encoded_slug = urllib.parse.quote(title.replace(" ", "_"))
        page_url = f"https://en.wikipedia.org/wiki/{encoded_slug}"

        return {
            "status": "success",
            "query": clean_query,
            "title": title,
            "summary": extract,
            "url": page_url
        }

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"status": "not_found", "message": f"No Wikipedia article found for '{clean_query}'."}
    )


def parse_arxiv_xml(xml_text: str) -> List[Dict[str, Any]]:
    """Parses Atom XML from arXiv export API into clean dictionaries."""
    results: List[Dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_text)
        entries = root.findall("atom:entry", ATOM_NS)
        for entry in entries:
            title_elem = entry.find("atom:title", ATOM_NS)
            summary_elem = entry.find("atom:summary", ATOM_NS)
            published_elem = entry.find("atom:published", ATOM_NS)
            id_elem = entry.find("atom:id", ATOM_NS)

            authors = [
                author.find("atom:name", ATOM_NS).text.strip()
                for author in entry.findall("atom:author", ATOM_NS)
                if author.find("atom:name", ATOM_NS) is not None
            ]

            pdf_link = None
            for link in entry.findall("atom:link", ATOM_NS):
                if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
                    pdf_link = link.attrib.get("href")
                    break

            results.append({
                "source": "arXiv Open Access Preprints",
                "title": title_elem.text.strip().replace("\n", " ") if title_elem is not None and title_elem.text else "Untitled Paper",
                "authors": authors,
                "publication_year": published_elem.text[:4] if published_elem is not None and published_elem.text else "N/A",
                "published_date": published_elem.text.strip() if published_elem is not None and published_elem.text else "N/A",
                "summary": summary_elem.text.strip().replace("\n", " ") if summary_elem is not None and summary_elem.text else "",
                "url": id_elem.text.strip() if id_elem is not None and id_elem.text else "",
                "pdf_download_url": pdf_link or (id_elem.text.replace("abs", "pdf") if id_elem is not None and id_elem.text else "")
            })
    except Exception as exc:
        logger.warning(f"Error parsing arXiv XML payload: {exc}")
    return results


@app.get("/api/v1/edu/search")
@app.get("/api/v1/academic-search")
async def academic_search(
    topic: Optional[str] = Query(None, description="Academic topic or subject (e.g., Quantum Computing, Calculus)"),
    subject: Optional[str] = Query(None, description="Alias for topic"),
    limit: int = Query(5, ge=1, le=25, description="Maximum items per catalog (default 5)")
) -> Dict[str, Any]:
    """
    Concurrently queries arXiv and OpenLibrary for authentic papers, textbooks, authors, and open access links.
    """
    query_term = (topic or subject or "").strip()
    if not query_term:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query parameter 'topic' is required."
        )

    headers = {
        "User-Agent": "Nexis-AI/1.0 (Education Assistant Engine; contact@nexis.gov.in)",
        "Accept": "application/json"
    }

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        openlib_task = client.get(
            OPENLIBRARY_API_URL,
            params={"q": query_term, "limit": limit},
            headers=headers
        )
        arxiv_task = client.get(
            ARXIV_API_URL,
            params={"search_query": f"all:{query_term}", "start": 0, "max_results": limit},
            headers={"User-Agent": headers["User-Agent"]}
        )

        try:
            openlib_res, arxiv_res = await asyncio.gather(openlib_task, arxiv_task, return_exceptions=True)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to query academic catalog upstreams: {str(exc)}"
            )

    textbooks: List[Dict[str, Any]] = []
    papers: List[Dict[str, Any]] = []

    # Parse OpenLibrary
    if isinstance(openlib_res, httpx.Response) and openlib_res.status_code == 200:
        try:
            ol_json = openlib_res.json()
            docs = ol_json.get("docs", [])
            for doc in docs:
                work_key = doc.get("key", "")
                textbooks.append({
                    "source": "OpenLibrary Academic Registry",
                    "title": doc.get("title", "Untitled Reference"),
                    "authors": doc.get("author_name", ["Unknown Author"]),
                    "first_publish_year": doc.get("first_publish_year"),
                    "subjects_covered": doc.get("subject", [])[:5],
                    "edition_count": doc.get("edition_count", 1),
                    "open_access_url": f"https://openlibrary.org{work_key}" if work_key else "https://openlibrary.org"
                })
        except Exception as exc:
            logger.warning(f"Error parsing OpenLibrary response: {exc}")

    # Parse arXiv
    if isinstance(arxiv_res, httpx.Response) and arxiv_res.status_code == 200:
        papers = parse_arxiv_xml(arxiv_res.text)

    total_count = len(textbooks) + len(papers)

    if total_count == 0:
        return {
            "status": "empty",
            "count": 0,
            "topic": query_term,
            "message": f"No academic publications or textbook records found for query '{query_term}'.",
            "textbooks": [],
            "research_papers": []
        }

    return {
        "status": "success",
        "topic": query_term,
        "total_results": total_count,
        "textbooks_count": len(textbooks),
        "research_papers_count": len(papers),
        "textbooks": textbooks,
        "research_papers": papers,
        "official_scholarship_portal": "https://scholarships.gov.in"
    }


@app.post("/api/v1/edu/teach")
async def teach_concept(req: TeachRequest) -> Dict[str, Any]:
    """
    Generates a 4-step Socratic teaching module:
    1. Core Intuition
    2. Technical Breakdown
    3. Worked Example
    4. Practice Check
    Supports both Groq Cloud and Local Ollama inference.
    """
    prompt = (
        f"You are a master academic professor. Create a structured 4-step teaching module in English "
        f"for the concept: '{req.concept}' calibrated for target level: '{req.level}'.\n\n"
        f"Strictly return valid JSON adhering to this exact schema:\n"
        f"{{\n"
        f'  "concept": "{req.concept}",\n'
        f'  "level": "{req.level}",\n'
        f'  "step_1_core_intuition": "High-level intuition and foundational mental model.",\n'
        f'  "step_2_technical_breakdown": "Rigorous mathematical, algorithmic, or architectural formulation.",\n'
        f'  "step_3_worked_example": "A concrete step-by-step example with intermediate calculations/steps.",\n'
        f'  "step_4_practice_check": {{\n'
        f'     "question": "Rigorous comprehension check question",\n'
        f'     "hint": "Pedagogical hint",\n'
        f'     "solution": "Verified step-by-step solution"\n'
        f'  }}\n'
        f"}}\n"
        f"Do NOT output markdown fences outside the JSON."
    )

    provider_used = INFERENCE_PROVIDER
    content = "{}"

    # 1. Ollama Execution
    if INFERENCE_PROVIDER == "ollama":
        try:
            from openai import AsyncOpenAI
            ollama_client = AsyncOpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")
            resp = await ollama_client.chat.completions.create(
                model=OLLAMA_ORCHESTRATOR_MODEL,
                messages=[
                    {"role": "system", "content": "You are a distinguished academic tutor. Output ONLY valid JSON in English."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1500
            )
            content = resp.choices[0].message.content or "{}"
            provider_used = f"ollama ({OLLAMA_ORCHESTRATOR_MODEL})"
        except Exception as exc:
            logger.warning(f"Ollama teaching generation failed: {exc}, falling back to Groq")
            active_key = os.getenv("GROQ_API_KEY") or GROQ_API_KEY
            if active_key and active_key != "your_groq_api_key_here":
                from groq import AsyncGroq
                client = AsyncGroq(api_key=active_key)
                target = os.getenv("GROQ_ORCHESTRATOR_MODEL", "llama-3.3-70b-versatile")
                models_to_try = [target, "qwen/qwen3.8-27b", "openai/gpt-oss-120b", "llama-3.3-70b-versatile"]
                for m in models_to_try:
                    try:
                        resp = await client.chat.completions.create(
                            model=m,
                            messages=[
                                {"role": "system", "content": "You are a distinguished academic tutor. Output ONLY valid JSON in English."},
                                {"role": "user", "content": prompt}
                            ],
                            temperature=0.3,
                            max_tokens=1500
                        )
                        content = resp.choices[0].message.content or "{}"
                        provider_used = f"groq ({m})"
                        break
                    except Exception:
                        continue
            else:
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Ollama generation failed: {str(exc)}")

    # 2. Groq Execution
    else:
        active_key = os.getenv("GROQ_API_KEY") or GROQ_API_KEY
        if not active_key or active_key == "your_groq_api_key_here":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GROQ_API_KEY is not configured in .env. Groq teaching generation requires a valid key."
            )

        from groq import AsyncGroq
        client = AsyncGroq(api_key=active_key, max_retries=0)
        target = os.getenv("GROQ_ORCHESTRATOR_MODEL", "llama-3.3-70b-versatile")
        models_to_try = [target, "openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b", "llama-3.3-70b-versatile"]
        token_budgets = [900, 750, 500]
        last_exc = None
        for m in models_to_try:
            for budget in token_budgets:
                try:
                    resp = await client.chat.completions.create(
                        model=m,
                        messages=[
                            {"role": "system", "content": "You are a distinguished academic tutor. Output ONLY valid JSON in English."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.3,
                        max_tokens=budget
                    )
                    content = resp.choices[0].message.content or "{}"
                    provider_used = f"groq ({m})"
                    break
                except Exception as exc:
                    last_exc = exc
                    err_str = str(exc).lower()
                    if "404" in err_str or "model_not_found" in err_str or "does not exist" in err_str:
                        break  # Try next model
                    if "429" in err_str or "rate_limit" in err_str or "otpm" in err_str:
                        continue  # Try lower budget
                    continue
            if content and content != "{}":
                break
        if not content or content == "{}":
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Groq teaching engine failed: {str(last_exc)}")

    clean_content = content.strip()
    if clean_content.startswith("```"):
        lines = clean_content.splitlines()
        clean_content = "\n".join([l for l in lines if not l.startswith("```")])

    try:
        teaching_module = json.loads(clean_content)
    except json.JSONDecodeError:
        teaching_module = {
            "concept": req.concept,
            "level": req.level,
            "lesson": content
        }

    return {
        "status": "success",
        "service": f"Nexis AI Socratic Teaching Engine ({provider_used})",
        "provider": provider_used,
        "teaching_module": teaching_module
    }


@app.get("/api/v1/edu/youtube")
async def search_youtube_videos(
    query: str = Query(..., min_length=1, description="Search query for visual tutorial or demonstration"),
    max_results: int = Query(3, ge=1, le=10, description="Maximum number of YouTube videos to return")
) -> Dict[str, Any]:
    """
    Queries YouTube Data API v3 or authentic live YouTube search / Invidious fallback.
    Returns authentic video titles, channel names, and direct watch links (https://www.youtube.com/watch?v={videoId}).
    Strictly zero mock / zero dummy video IDs.
    """
    clean_query = query.strip()
    if not clean_query:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Query parameter is required.")

    videos: List[Dict[str, Any]] = []
    source = "live_youtube"

    active_yt_key = os.getenv("YOUTUBE_API_KEY") or YOUTUBE_API_KEY
    if active_yt_key and active_yt_key != "your_youtube_v3_api_key_here":
        # 1. Attempt official Google YouTube Data API v3
        yt_endpoint = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "snippet",
            "type": "video",
            "q": clean_query,
            "maxResults": max_results,
            "key": active_yt_key
        }
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                res = await client.get(yt_endpoint, params=params)
                if res.status_code == 200:
                    data = res.json()
                    for item in data.get("items", []):
                        vid = item.get("id", {}).get("videoId")
                        if vid:
                            snippet = item.get("snippet", {})
                            videos.append({
                                "video_id": vid,
                                "title": snippet.get("title", "Educational Tutorial"),
                                "channel": snippet.get("channelTitle", "YouTube Creator"),
                                "url": f"https://www.youtube.com/watch?v={vid}",
                                "description": snippet.get("description", ""),
                                "published_at": snippet.get("publishedAt", "")
                            })
                    if videos:
                        source = "youtube_v3_api"
        except Exception as exc:
            logger.warning(f"YouTube Data API v3 request error: {exc}, falling back to live extraction")

    # 2. Live YouTube initial data parsing fallback (Zero mock, authentic watch URLs)
    if not videos:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
        encoded_query = urllib.parse.quote_plus(clean_query)
        search_url = f"https://www.youtube.com/results?search_query={encoded_query}"

        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                res = await client.get(search_url, headers=headers)
                if res.status_code == 200:
                    match = re.search(r"var ytInitialData = ({.*?});</script>", res.text)
                    if not match:
                        match = re.search(r"ytInitialData\s*=\s*({.*?});", res.text)
                    if match:
                        yt_data = json.loads(match.group(1))
                        sections = yt_data.get("contents", {}).get("twoColumnSearchResultsRenderer", {}).get("primaryContents", {}).get("sectionListRenderer", {}).get("contents", [])
                        for sec in sections:
                            items = sec.get("itemSectionRenderer", {}).get("contents", [])
                            for itm in items:
                                vr = itm.get("videoRenderer")
                                if vr and "videoId" in vr:
                                    vid = vr["videoId"]
                                    title = vr.get("title", {}).get("runs", [{}])[0].get("text", "Tutorial")
                                    channel = vr.get("ownerText", {}).get("runs", [{}])[0].get("text", "YouTube Channel")
                                    videos.append({
                                        "video_id": vid,
                                        "title": title,
                                        "channel": channel,
                                        "url": f"https://www.youtube.com/watch?v={vid}",
                                        "description": "",
                                        "published_at": ""
                                    })
                                    if len(videos) >= max_results:
                                        break
                            if len(videos) >= max_results:
                                break
                        if videos:
                            source = "live_youtube_discovery"
        except Exception as exc:
            logger.warning(f"Live YouTube discovery failed: {exc}")

    # 3. Public Invidious instance fallback
    if not videos:
        invidious_instances = ["https://invidious.nerdvpn.de", "https://invidious.drgns.space", "https://inv.tux.pizza"]
        for inst in invidious_instances:
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    inv_res = await client.get(f"{inst}/api/v1/search", params={"q": clean_query, "type": "video"})
                    if inv_res.status_code == 200:
                        inv_data = inv_res.json()
                        for itm in inv_data[:max_results]:
                            vid = itm.get("videoId")
                            if vid:
                                videos.append({
                                    "video_id": vid,
                                    "title": itm.get("title", "Tutorial Video"),
                                    "channel": itm.get("author", "Creator"),
                                    "url": f"https://www.youtube.com/watch?v={vid}",
                                    "description": itm.get("description", ""),
                                    "published_at": ""
                                })
                        if videos:
                            source = f"invidious_{inst}"
                            break
            except Exception:
                continue

    if not videos:
        return {
            "status": "empty",
            "query": clean_query,
            "total_results": 0,
            "message": f"No authentic tutorial videos discovered for '{clean_query}'.",
            "videos": []
        }

    return {
        "status": "success",
        "query": clean_query,
        "source": source,
        "total_results": len(videos),
        "videos": videos
    }


@app.get("/api/v1/edu/web-search")
async def live_web_search(
    query: str = Query(..., min_length=1, description="Topic or query for live web citations and documentation"),
    max_results: int = Query(4, ge=1, le=10, description="Maximum search results to return")
) -> Dict[str, Any]:
    """
    Queries Tavily API for pre-parsed markdown extracts and direct source links.
    Falls back to DuckDuckGo search (duckduckgo-search) when Tavily key is absent.
    Strictly zero mock / zero static links.
    """
    clean_query = query.strip()
    if not clean_query:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Query parameter is required.")

    results: List[Dict[str, Any]] = []
    provider = "unknown"

    active_tavily_key = os.getenv("TAVILY_API_KEY") or TAVILY_API_KEY
    if active_tavily_key and active_tavily_key != "your_tavily_search_key_here":
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": active_tavily_key,
                        "query": clean_query,
                        "max_results": max_results,
                        "search_depth": "basic",
                        "include_answer": False
                    }
                )
                if res.status_code == 200:
                    data = res.json()
                    for r in data.get("results", []):
                        results.append({
                            "title": r.get("title", "Web Resource"),
                            "url": r.get("url", ""),
                            "snippet": r.get("content", ""),
                            "score": r.get("score", 0.0)
                        })
                    if results:
                        provider = "tavily"
        except Exception as exc:
            logger.warning(f"Tavily search error: {exc}, falling back to DuckDuckGo")

    # Fallback to DuckDuckGo search / news
    if not results:
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                # Try news first as it reliably yields current authentic government and news links
                try:
                    news_items = list(ddgs.news(clean_query, max_results=max_results))
                    for item in news_items:
                        results.append({
                            "title": item.get("title", ""),
                            "url": item.get("url", ""),
                            "snippet": item.get("body", ""),
                            "source": item.get("source", "Web"),
                            "published_date": item.get("date", "")
                        })
                except Exception:
                    pass

                # If news had no items or failed, try web text search
                if not results:
                    try:
                        text_items = list(ddgs.text(clean_query, max_results=max_results))
                        for item in text_items:
                            results.append({
                                "title": item.get("title", ""),
                                "url": item.get("href", "") or item.get("url", ""),
                                "snippet": item.get("body", ""),
                                "source": "DuckDuckGo Web"
                            })
                    except Exception:
                        pass

            if results:
                provider = "duckduckgo"
        except Exception as exc:
            logger.warning(f"DuckDuckGo search error: {exc}")

    if not results:
        return {
            "status": "empty",
            "query": clean_query,
            "provider": provider,
            "total_results": 0,
            "message": f"No live search citations retrieved for query '{clean_query}'.",
            "results": []
        }

    return {
        "status": "success",
        "query": clean_query,
        "provider": provider,
        "total_results": len(results),
        "results": results
    }


if __name__ == "__main__":
    uvicorn.run("edu_server:app", host=HOST, port=PORT, reload=False, log_level="info")

