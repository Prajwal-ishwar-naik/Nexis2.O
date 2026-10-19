"""
Nexis AI - Corrective RAG (CRAG) Orchestration Engine
Implements:
1. Cosine similarity retrieval from local ChromaDB.
2. Retrieval Evaluator / Grader: grades candidate chunks as CORRECT, AMBIGUOUS, or INCORRECT.
3. Corrective Action Branching:
   - CORRECT: Passes verified document chunks directly into the prompt.
   - AMBIGUOUS: Refines query, triggers live external web search, and combines document chunks with external facts.
   - INCORRECT: Refines query, triggers live external search, and replaces irrelevant chunks with authoritative web sources.
4. Privacy & Compliance Redaction: scrubs sensitive government identifiers.
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import httpx
from groq import AsyncGroq
from src.rag.ingestion import redact_sensitive_identifiers
from src.rag.vector_store import vector_store
from src.rag.tabular_engine import tabular_registry

logger = logging.getLogger("NexisCRAG.Engine")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


@dataclass
class CRAGResult:
    grade: str  # "CORRECT" | "AMBIGUOUS" | "INCORRECT"
    confidence: float
    retrieved_chunks: List[Dict[str, Any]] = field(default_factory=list)
    refined_query: Optional[str] = None
    fallback_results: List[Dict[str, Any]] = field(default_factory=list)
    context_text: str = ""
    rationale: str = ""


MANDATORY_INSTRUCTIONS = (
    "STRICT PROVENANCE GROUNDING GUARDRAIL:\n"
    "Answer the citizen's query strictly based on the verified chunks above.\n\n"
    "MANDATORY INSTRUCTIONS:\n"
    "1. Synthesize the response directly from the verified context above.\n"
    "2. Never output meta-disclaimers like \"The retrieved context does not contain...\" or refer to previous vision/image turns.\n"
    "3. If tabular data is referenced, cite the exact entity and value cleanly.\n"
    "4. If open-ended questions like 'whats this telling' are asked, summarize key points directly, clearly, and concisely in natural language."
)

DOCUMENT_GROUNDING_DIRECTIVE = MANDATORY_INSTRUCTIONS


def is_broad_or_summary_query(query: str) -> bool:
    """
    Detects whether a user query is broad, open-ended, or seeking a general summary/overview
    of an attached document rather than targeting a specific narrow entity.
    """
    if not query:
        return True
    q = query.strip().lower()
    q_clean = re.sub(r"[^\w\s]", " ", q).strip()
    words = q_clean.split()
    if not words:
        return True

    broad_patterns = [
        r"\b(whats?|what is) (this|it|the document|the file) telling\b",
        r"\bwhat (does|do) (this|it|the doc|the document|the file) (tell|say|contain|mean|cover|show|state)\b",
        r"\b(summarize|summarise|summary|overview|explain|brief|digest|synthesize|breakdown)\b",
        r"\b(what is|whats) (this|it|the doc|the document|the paper|the report|the file|the text)\b",
        r"\b(tell me|what can you tell me) about (this|it|the doc|the document|the file)\b",
        r"\b(key points|key takeaways|key findings|highlights|main ideas?)\b",
        r"\b(analyze|review|examine|inspect|understand|read) (this|the doc|the document|the file)\b",
        r"\bwhat (is in|is inside|are the contents of) (this|it|the doc|the document|the file)\b",
        r"\b(what is|whats) (this|it) about\b",
        r"\bwalk me through (this|the document|the file)\b",
        r"\bcan you (read|check|explain|summarize) this\b",
        r"\bwhats going on here\b",
    ]
    for pattern in broad_patterns:
        if re.search(pattern, q_clean):
            return True

    # Very short conversational prompts on an attached doc (e.g. <= 4 words)
    if len(words) <= 4:
        summary_tokens = {
            "what", "whats", "explain", "summary", "summarize", "tell",
            "describe", "about", "this", "help", "meaning", "review",
            "details", "doc", "document", "pdf", "file"
        }
        if any(w in summary_tokens for w in words):
            return True

    return False


def compile_full_document_context(chunks: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
    """
    Compiles all chunks of a small document (< 20 chunks) into a unified, coherent context block.
    Sorts chunks by document and page/index so the model receives full sequential text.
    """
    from src.rag.retriever import compress_chunk_content

    def _chunk_sort_key(c):
        meta = c.get("metadata", {})
        source = meta.get("source_file", "")
        try:
            c_idx = int(meta.get("chunk_index", 0))
        except (ValueError, TypeError):
            c_idx = 0
        try:
            pg = int(meta.get("page_or_slide", 0))
        except (ValueError, TypeError):
            pg = 0
        return (source, pg, c_idx)

    sorted_chunks = sorted(chunks, key=_chunk_sort_key)
    assembled_sections = []
    current_source = None
    for idx, c in enumerate(sorted_chunks, start=1):
        meta = c.get("metadata", {})
        source_file = meta.get("source_file", "Uploaded Document")
        page_or_slide = meta.get("page_or_slide", idx)
        if source_file != current_source:
            current_source = source_file
            assembled_sections.append(f"--- Document: {source_file} ---")
        content = compress_chunk_content(c.get("content", ""))
        assembled_sections.append(f"[Section / Page {page_or_slide}]\n{content}")

    full_doc_text = "\n\n".join(assembled_sections).strip()
    assembled_context = (
        f"### HIGH-PRECISION RETRIEVED CONTEXT (VERIFIED):\n\n"
        f"{full_doc_text}\n\n"
        f"{MANDATORY_INSTRUCTIONS}"
    )
    return sorted_chunks, assembled_context


class CorrectiveRAGEngine:
    """
    Self-correcting RAG engine with automated evaluation and web fallback.
    """

    def __init__(self):
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")

    async def _get_groq_client(self) -> Optional[AsyncGroq]:
        key = os.getenv("GROQ_API_KEY") or self.groq_api_key
        if key and key != "your_groq_api_key_here":
            return AsyncGroq(api_key=key, max_retries=1)
        return None

    # ==========================================================================
    # 1. Retrieval Evaluator / Grader
    # ==========================================================================
    async def evaluate_retrieval(
        self,
        query: str,
        chunks: List[Dict[str, Any]]
    ) -> Tuple[str, float, str]:
        """
        Grades retrieval quality against user query.
        Returns (grade, confidence, rationale)
        grade is one of: CORRECT, AMBIGUOUS, INCORRECT.
        """
        if not chunks:
            return "INCORRECT", 0.0, "No document chunks retrieved."

        top_similarity = chunks[0].get("similarity", 0.0)

        # Check via LLM Grader if Groq is available
        client = await self._get_groq_client()
        if client:
            try:
                chunks_summary = "\n\n".join([
                    f"Chunk {i+1} (Source: {c['metadata'].get('source_file')}, Score: {c.get('similarity', 0)}):\n{c['content'][:400]}"
                    for i, c in enumerate(chunks[:3])
                ])

                prompt = (
                    f"You are a Retrieval Evaluator for an AI assistant. "
                    f"Assess whether the retrieved document chunks contain the necessary information to answer the user query.\n\n"
                    f"User Query: \"{query}\"\n\n"
                    f"Retrieved Chunks:\n{chunks_summary}\n\n"
                    f"Instructions:\n"
                    f"- Grade as 'CORRECT' if the chunks directly provide the specific facts, data, or context needed to answer the query.\n"
                    f"- Grade as 'AMBIGUOUS' if the chunks are somewhat related or only answer part of the question, requiring external search for completeness.\n"
                    f"- Grade as 'INCORRECT' if the chunks are completely irrelevant, off-topic, or cannot answer the question.\n\n"
                    f"Respond ONLY with a valid JSON object: {{\"grade\": \"CORRECT\" | \"AMBIGUOUS\" | \"INCORRECT\", \"confidence\": 0.0-1.0, \"reason\": \"one concise sentence\"}}"
                )

                resp = await client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=150,
                    response_format={"type": "json_object"}
                )

                content = resp.choices[0].message.content or "{}"
                data = json.loads(content)
                grade = data.get("grade", "AMBIGUOUS").upper().strip()
                if grade not in ["CORRECT", "AMBIGUOUS", "INCORRECT"]:
                    grade = "AMBIGUOUS"
                confidence = float(data.get("confidence", 0.8))
                reason = data.get("reason", "")
                logger.info(f"CRAG LLM Grader: grade={grade}, confidence={confidence}, reason={reason}")
                return grade, confidence, reason

            except Exception as exc:
                logger.warning(f"CRAG LLM grading error, falling back to similarity heuristic: {exc}")

        # Fallback Semantic Similarity Heuristic
        # Vector similarity (cosine) with all-MiniLM-L6-v2:
        # > 0.65 indicates strong topical match
        # 0.45 - 0.65 indicates ambiguous / partial match
        # < 0.45 indicates incorrect / irrelevant
        query_words = set(re.findall(r"\w+", query.lower()))
        combined_text = " ".join([c["content"].lower() for c in chunks])
        overlap_count = sum(1 for w in query_words if len(w) > 3 and w in combined_text)

        if top_similarity >= 0.68 or (top_similarity >= 0.58 and overlap_count >= 2):
            return "CORRECT", round(top_similarity, 2), "Strong semantic match to document content."
        elif top_similarity >= 0.42 or overlap_count >= 1:
            return "AMBIGUOUS", round(top_similarity, 2), "Partial topical overlap; supplementary facts recommended."
        else:
            return "INCORRECT", round(top_similarity, 2), "Low semantic relevance to active documents."

    # ==========================================================================
    # 2. Query Refinement & Rewriting
    # ==========================================================================
    async def refine_query(self, query: str, chunks: List[Dict[str, Any]]) -> str:
        """
        Rewrites the query into a high-precision search query for web search fallback.
        """
        client = await self._get_groq_client()
        if client:
            try:
                resp = await client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{
                        "role": "user",
                        "content": (
                            f"Generate an optimized, concise web search query (3-6 keywords) "
                            f"to find authentic facts answering: \"{query}\". "
                            f"Return ONLY the refined query string without quotes or preamble."
                        )
                    }],
                    temperature=0.1,
                    max_tokens=30
                )
                refined = resp.choices[0].message.content or ""
                clean_ref = refined.strip().strip('"').strip("'")
                if clean_ref:
                    return clean_ref
            except Exception as exc:
                logger.warning(f"Error refining query with LLM: {exc}")

        # Fallback query cleaner
        tokens = [w for w in re.findall(r"\w+", query) if len(w) > 2]
        return " ".join(tokens[:6]) or query

    # ==========================================================================
    # 3. External Web Search Fallback
    # ==========================================================================
    async def fallback_web_search(self, refined_query: str, max_results: int = 3) -> List[Dict[str, Any]]:
        """
        Queries DuckDuckGo search or live web search microservice to augment facts.
        """
        results: List[Dict[str, Any]] = []

        # 1. Try DuckDuckGo in-process via duckduckgo_search
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                ddg_gen = ddgs.text(refined_query, max_results=max_results)
                for item in ddg_gen:
                    snippet = item.get("body") or item.get("snippet") or ""
                    clean_snippet = redact_sensitive_identifiers(snippet.strip())
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("href") or item.get("url", ""),
                        "snippet": clean_snippet,
                        "source": "DuckDuckGo Web Search"
                    })
            if results:
                logger.info(f"CRAG DDGS fallback retrieved {len(results)} search results for '{refined_query}'")
                return results
        except Exception as exc:
            logger.warning(f"DuckDuckGo in-process search failed: {exc}")

        # 2. Try Education microservice web search endpoint
        try:
            edu_url = os.getenv("EDU_SERVICE_URL", "http://127.0.0.1:8003/api/v1/edu/web-search")
            async with httpx.AsyncClient(timeout=8.0) as http_client:
                res = await http_client.get(edu_url, params={"query": refined_query, "max_results": max_results})
                if res.status_code == 200:
                    data = res.json()
                    raw_items = data.get("results", []) or []
                    for it in raw_items:
                        snippet = redact_sensitive_identifiers(it.get("snippet", "") or it.get("extract", ""))
                        results.append({
                            "title": it.get("title", ""),
                            "url": it.get("url", ""),
                            "snippet": snippet,
                            "source": "Live Web Search"
                        })
                    if results:
                        return results
        except Exception as exc:
            logger.warning(f"Microservice web search fallback error: {exc}")

        return results

    # ==========================================================================
    # 4. Master CRAG Orchestration Pipeline
    # ==========================================================================
    async def run_crag(
        self,
        query: str,
        session_id: str,
        top_k: int = 5,
        attached_document: Optional[str] = None
    ) -> CRAGResult:
        """
        Executes the full Corrective RAG pipeline:
        Retrieve -> Grade -> Branch (Pass / Augment / Replace) -> Assemble Context Block.
        """
        clean_user_query = redact_sensitive_identifiers(query.strip())
        is_broad = is_broad_or_summary_query(clean_user_query)
        has_vector_docs = vector_store.has_documents(session_id) if vector_store else False
        has_tabular_docs = tabular_registry.has_tabular(session_id) if tabular_registry else False

        # Step 0: Document Content Aggregation for Broad/General Inquiries or Attached Documents
        if has_vector_docs and (is_broad or attached_document):
            all_stored = vector_store.get_all_chunks(session_id)
            if attached_document:
                doc_specific = [c for c in all_stored if c.get("metadata", {}).get("source_file") == attached_document]
                if doc_specific:
                    all_stored = doc_specific

            total_chunks = len(all_stored)
            if 0 < total_chunks <= 40:
                logger.info(
                    f"CRAG Document Aggregation triggered: {total_chunks} chunks aggregated "
                    f"for query '{clean_user_query}' in session '{session_id}'"
                )
                sorted_chunks, agg_context = compile_full_document_context(all_stored)
                return CRAGResult(
                    grade="CORRECT",
                    confidence=1.0,
                    retrieved_chunks=sorted_chunks,
                    context_text=redact_sensitive_identifiers(agg_context),
                    rationale=f"Document full content aggregation ({total_chunks} chunks) for query."
                )
            elif total_chunks > 40:
                logger.info(
                    f"CRAG Leading Sections Aggregation triggered for large document ({total_chunks} chunks)"
                )
                sorted_chunks, agg_context = compile_full_document_context(all_stored[:25])
                return CRAGResult(
                    grade="CORRECT",
                    confidence=0.95,
                    retrieved_chunks=sorted_chunks,
                    context_text=redact_sensitive_identifiers(agg_context),
                    rationale=f"Document overview aggregation (25 of {total_chunks} chunks) for query."
                )

        # Step 0.5: Check for Copilot-Style Tabular Processing (.xlsx, .csv)
        if has_tabular_docs:
            try:
                from src.rag.entity_matcher import resolve_tabular_query

                tab_res = resolve_tabular_query(session_id, clean_user_query)
                if tab_res:
                    status = tab_res.get("status") or tab_res.get("resolution", {}).get("status")
                    # Only accept tabular match if an authentic match was found OR no vector documents exist
                    if status in ["AGGREGATION_SUCCESS", "EXACT", "FUZZY_SUGGESTION"] or not has_vector_docs:
                        logger.info(
                            f"CRAG Tabular Resolver matched: type={tab_res.get('type')}, "
                            f"status={status}, file={tab_res.get('filename')}"
                        )
                        clean_tab_context = redact_sensitive_identifiers(tab_res["context_prompt"])
                        supp_chunks = vector_store.query(session_id, clean_user_query, top_k=2) if vector_store else []
                        return CRAGResult(
                            grade="CORRECT",
                            confidence=1.0 if status in ["AGGREGATION_SUCCESS", "EXACT"] else 0.9,
                            retrieved_chunks=supp_chunks,
                            context_text=clean_tab_context,
                            rationale=f"Authoritative spreadsheet resolution ({status}) from {tab_res.get('filename')}"
                        )
            except Exception as tab_err:
                logger.warning(f"Error executing tabular resolver in CRAG: {tab_err}")

        # Step 1: Enterprise Hybrid Retrieval + Cross-Encoder Reranking + Contextual Compression
        from src.rag.retriever import hybrid_retriever
        candidate_chunks, grounded_prompt_block = hybrid_retriever.retrieve(
            session_id=session_id,
            query=clean_user_query,
            top_k=top_k
        )

        if not candidate_chunks:
            # Check if any documents exist in session
            if not has_vector_docs:
                return CRAGResult(
                    grade="INCORRECT",
                    confidence=0.0,
                    retrieved_chunks=[],
                    context_text="",
                    rationale="No documents indexed in this session."
                )

            # Documents exist! Fallback to compiling sequential document context instead of dropping to web search
            all_stored = vector_store.get_all_chunks(session_id)
            if attached_document:
                doc_specific = [c for c in all_stored if c.get("metadata", {}).get("source_file") == attached_document]
                if doc_specific:
                    all_stored = doc_specific

            total_chunks = len(all_stored)
            take_chunks = all_stored[:30] if total_chunks > 30 else all_stored
            logger.info(
                f"CRAG Document Fallback: Cross-encoder yielded no high-threshold snippets, "
                f"compiling document context ({len(take_chunks)} chunks) for query '{clean_user_query}'"
            )
            sorted_chunks, agg_context = compile_full_document_context(take_chunks)
            return CRAGResult(
                grade="CORRECT",
                confidence=0.95,
                retrieved_chunks=sorted_chunks,
                context_text=redact_sensitive_identifiers(agg_context),
                rationale=f"Document fallback aggregation ({len(sorted_chunks)} chunks)."
            )

        # Step 2: Retrieval Evaluator / Grader on the verified reranked chunks
        grade, confidence, rationale = await self.evaluate_retrieval(clean_user_query, candidate_chunks)

        refined_q = None
        fallback_hits: List[Dict[str, Any]] = []

        # Step 3: Corrective Action Branching
        if grade == "CORRECT":
            # Direct injection of the cross-encoder verified and compressed context with strict provenance guardrail
            assembled_context = grounded_prompt_block

        elif grade == "AMBIGUOUS":
            # Partial topical overlap: hybrid fusion with live web augmentation
            refined_q = await self.refine_query(clean_user_query, candidate_chunks)
            fallback_hits = await self.fallback_web_search(refined_q, max_results=3)

            amb_sections = [
                grounded_prompt_block,
                f"\n#### External Web Augmentation (Live Supplementary Fallback for \"{refined_q}\"):"
            ]
            for hit in fallback_hits:
                amb_sections.append(f"\n- **{hit['title']}** ({hit.get('url', '')})\n  {hit['snippet']}")
            assembled_context = "\n".join(amb_sections)

        else:  # INCORRECT
            # If it's a small document (< 20 chunks), compile full document text directly
            if vector_store and vector_store.has_documents(session_id):
                all_stored = vector_store.get_all_chunks(session_id)
                if 0 < len(all_stored) <= 20:
                    sorted_chunks, agg_context = compile_full_document_context(all_stored)
                    return CRAGResult(
                        grade="CORRECT",
                        confidence=0.9,
                        retrieved_chunks=sorted_chunks,
                        context_text=redact_sensitive_identifiers(agg_context),
                        rationale=f"Small document fallback aggregation ({len(all_stored)} chunks)."
                    )

            refined_q = await self.refine_query(clean_user_query, candidate_chunks)
            fallback_hits = await self.fallback_web_search(refined_q, max_results=4)
            assembled_context = (
                f"### RETRIEVED CONTEXT (Web Augmentation):\n"
                f"- Refined Search Query: \"{refined_q}\"\n\n"
                f"{DOCUMENT_GROUNDING_DIRECTIVE}\n"
            )
            if fallback_hits:
                assembled_context += "\n#### Authoritative External Search Findings:\n" + "\n".join([
                    f"\n- **{hit['title']}** ({hit.get('url', '')})\n  {hit['snippet']}"
                    for hit in fallback_hits
                ])

        # Apply final privacy scrubbing on all assembled text
        clean_context = redact_sensitive_identifiers(assembled_context)

        return CRAGResult(
            grade=grade,
            confidence=confidence,
            retrieved_chunks=candidate_chunks,
            refined_query=refined_q,
            fallback_results=fallback_hits,
            context_text=clean_context,
            rationale=rationale
        )


# Global singleton instance
crag_engine = CorrectiveRAGEngine()
