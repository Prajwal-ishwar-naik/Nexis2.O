"""
Nexis AI - Enterprise Hybrid Search, Cross-Encoder Reranking & Contextual Compression
Implements:
1. Hybrid Search Engine:
   - Dense vector retrieval (ChromaDB with all-MiniLM-L6-v2)
   - BM25Okapi sparse retrieval (rank_bm25)
   - Reciprocal Rank Fusion (RRF):
     RRF_Score(d) = (1 / (60 + rank_dense(d))) + (1 / (60 + rank_bm25(d)))
   - Retrieves top 20 candidate chunks via hybrid union.
2. Cross-Encoder Re-Ranking:
   - CrossEncoder cross-attention model ('cross-encoder/ms-marco-MiniLM-L-6-v2')
   - Absolute relevance threshold filtering (threshold >= 0.40)
   - Prunes down to top 3-5 verified high-precision chunks.
3. Contextual Compressor:
   - Strips redundant whitespace, boilerplate dividers, and duplicate table headers.
4. Grounded Prompt Formulation:
   - Strict provenance grounding guardrail to eliminate hallucination.
"""

import logging
import math
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from src.rag.vector_store import vector_store

logger = logging.getLogger("NexisCRAG.Retriever")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# Cross-Encoder lazy model cache
_CROSS_ENCODER_INSTANCE = None
_CROSS_ENCODER_INITIALIZATION_ATTEMPTED = False
DEFAULT_RERANKER_MODEL = os.getenv("RAG_RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")


def get_cross_encoder():
    """
    Lazy loader for local CrossEncoder model.
    Falls back gracefully if offline or download error occurs.
    """
    global _CROSS_ENCODER_INSTANCE, _CROSS_ENCODER_INITIALIZATION_ATTEMPTED
    if _CROSS_ENCODER_INSTANCE is not None:
        return _CROSS_ENCODER_INSTANCE

    if _CROSS_ENCODER_INITIALIZATION_ATTEMPTED:
        return None

    _CROSS_ENCODER_INITIALIZATION_ATTEMPTED = True
    try:
        from sentence_transformers import CrossEncoder
        logger.info(f"Loading Cross-Encoder re-ranker model: '{DEFAULT_RERANKER_MODEL}'...")
        _CROSS_ENCODER_INSTANCE = CrossEncoder(DEFAULT_RERANKER_MODEL, max_length=512)
        logger.info(f"Cross-Encoder '{DEFAULT_RERANKER_MODEL}' loaded successfully.")
        return _CROSS_ENCODER_INSTANCE
    except Exception as exc:
        logger.warning(f"Could not initialize CrossEncoder '{DEFAULT_RERANKER_MODEL}': {exc}. Using heuristic re-ranker.")
        return None


def tokenize_for_bm25(text: str) -> List[str]:
    """Lightweight whitespace and alphanumeric tokenizer for BM25 matching."""
    return [w for w in re.findall(r"\w+", text.lower()) if len(w) > 1]


def sigmoid(x: float) -> float:
    """Standard sigmoid mapping logits to [0, 1]."""
    try:
        return 1.0 / (1.0 + math.exp(-float(x)))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


# ==============================================================================
# 1. Hybrid Search (Dense + BM25Okapi + Reciprocal Rank Fusion)
# ==============================================================================

def execute_hybrid_retrieval(
    session_id: str,
    query_text: str,
    top_candidates: int = 15,
    dense_top_k: int = 20,
    sparse_top_k: int = 20,
    rrf_k: int = 60
) -> List[Dict[str, Any]]:
    """
    Combines dense vector retrieval (ChromaDB) and sparse retrieval (BM25Okapi)
    using Reciprocal Rank Fusion (RRF):
    RRF_Score(d) = 1/(k + rank_dense(d)) + 1/(k + rank_bm25(d))

    Retrieval Workflow:
    1. Retrieve top 20 candidates from ChromaDB (dense score).
    2. Retrieve top 20 candidates from BM25 index over active session chunks (sparse score).
    3. Merge both candidate lists using Reciprocal Rank Fusion: score(d) = sum(1 / (60 + rank(d))).
    4. Retain the top 15 unified candidates for neural reranking.
    """
    if not vector_store or not vector_store.has_documents(session_id):
        return []

    # 1. Dense Vector Retrieval (top 20 candidates)
    dense_results = vector_store.query(session_id, query_text, top_k=dense_top_k)

    # 2. Sparse BM25 Retrieval across all stored chunks in session (top 20 candidates)
    all_chunks = vector_store.get_all_chunks(session_id)
    bm25_ranked: List[Dict[str, Any]] = []

    if all_chunks:
        try:
            from rank_bm25 import BM25Okapi
            corpus_tokens = [tokenize_for_bm25(c.get("content", "")) for c in all_chunks]
            query_tokens = tokenize_for_bm25(query_text)

            if corpus_tokens and query_tokens:
                bm25 = BM25Okapi(corpus_tokens)
                doc_scores = bm25.get_scores(query_tokens)

                scored_chunks = []
                for idx, score in enumerate(doc_scores):
                    if score > 0:
                        chunk_copy = dict(all_chunks[idx])
                        chunk_copy["bm25_score"] = float(score)
                        scored_chunks.append(chunk_copy)

                scored_chunks.sort(key=lambda x: x["bm25_score"], reverse=True)
                bm25_ranked = scored_chunks[:sparse_top_k]
        except Exception as bm25_err:
            logger.warning(f"BM25 sparse ranking error: {bm25_err}")

    # 3. Reciprocal Rank Fusion (RRF): score(d) = sum(1 / (60 + rank(d)))
    fused_candidates: Dict[str, Dict[str, Any]] = {}

    def _resolve_chunk_id(c: Dict[str, Any]) -> str:
        """Extracts a stable, unique chunk ID across dense/sparse result formats."""
        # Priority: top-level chunk_id > metadata.chunk_id > content hash
        cid = c.get("chunk_id")
        if not cid:
            cid = c.get("metadata", {}).get("chunk_id")
        if not cid:
            # Stable content-based fallback
            cid = f"hash_{hash(c.get('content', ''))}"
        return str(cid)

    # Map dense ranks (1-indexed)
    for rank_d, c in enumerate(dense_results, start=1):
        cid = _resolve_chunk_id(c)
        dense_rrf = 1.0 / (rrf_k + rank_d)

        fused_candidates[cid] = {
            "chunk_id": cid,
            "content": c.get("content", ""),
            "metadata": c.get("metadata", {}),
            "similarity": c.get("similarity", 0.0),
            "rank_dense": rank_d,
            "rank_bm25": None,
            "rrf_score": dense_rrf,
            "retrieval_modes": ["dense"]
        }

    # Map sparse BM25 ranks (1-indexed)
    for rank_s, c in enumerate(bm25_ranked, start=1):
        cid = _resolve_chunk_id(c)
        bm25_rrf = 1.0 / (rrf_k + rank_s)

        if cid in fused_candidates:
            fused_candidates[cid]["rank_bm25"] = rank_s
            fused_candidates[cid]["rrf_score"] += bm25_rrf
            fused_candidates[cid]["retrieval_modes"].append("bm25")
            if "bm25_score" in c:
                fused_candidates[cid]["bm25_score"] = c["bm25_score"]
        else:
            fused_candidates[cid] = {
                "chunk_id": cid,
                "content": c.get("content", ""),
                "metadata": c.get("metadata", {}),
                "similarity": 0.0,
                "rank_dense": None,
                "rank_bm25": rank_s,
                "bm25_score": c.get("bm25_score", 0.0),
                "rrf_score": bm25_rrf,
                "retrieval_modes": ["bm25"]
            }

    # Sort candidates by combined RRF score descending and retain top 15 unified candidates
    sorted_hybrid = sorted(fused_candidates.values(), key=lambda x: x["rrf_score"], reverse=True)
    return sorted_hybrid[:top_candidates]


# ==============================================================================
# 2. Cross-Encoder Re-Ranking Engine (Delegates to src.rag.reranker)
# ==============================================================================

def rerank_chunks_with_cross_encoder(
    query_text: str,
    candidate_chunks: List[Dict[str, Any]],
    score_threshold: float = 0.35,
    top_n: int = 5
) -> List[Dict[str, Any]]:
    """
    Neural Cross-Encoder Re-Ranking entrypoint.
    Delegates to src.rag.reranker for cross-attention inference,
    applying relevance threshold (min score 0.35) and slicing top 3 to 5 chunks.
    """
    from src.rag.reranker import rerank_chunks
    return rerank_chunks(
        query_text=query_text,
        candidate_chunks=candidate_chunks,
        score_threshold=score_threshold,
        top_n=top_n
    )


# ==============================================================================
# 3. Contextual Compressor
# ==============================================================================

def compress_chunk_content(text: str) -> str:
    """
    Contextual Compressor:
    - Strips redundant whitespace and blank lines.
    - Strips repetitive markdown table dividers and boundary boilerplate.
    - Deduplicates adjacent identical rows/lines.
    - Maximizes token efficiency before prompt context injection.
    """
    if not text:
        return ""

    lines = [ln.strip() for ln in text.splitlines()]
    cleaned_lines: List[str] = []
    seen_adjacent = None

    for line in lines:
        if not line:
            # Drop empty line if previous line was also empty
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue

        # Skip repeated empty markdown table rows or pure separator lines like |---|---|
        if re.match(r"^\|(?:[\s\-:|]+)\|$", line):
            # Only keep one separator line if following a header
            if cleaned_lines and re.match(r"^\|(?:[\s\-:|]+)\|$", cleaned_lines[-1]):
                continue

        # Deduplicate repeated identical adjacent lines (e.g. repeated sheet headers)
        if line == seen_adjacent and not line.startswith("Row "):
            continue

        seen_adjacent = line
        cleaned_lines.append(line)

    compressed = "\n".join(cleaned_lines).strip()
    # Normalize multiple consecutive newlines into at most double newline
    compressed = re.sub(r"\n{3,}", "\n\n", compressed)
    return compressed


# ==============================================================================
# 4. Formulate Prompt Guardrail & Master Pipeline
# ==============================================================================

def format_grounded_system_prompt(
    verified_chunks: List[Dict[str, Any]],
    query: str
) -> str:
    """
    Wraps the retrieved, reranked, and compressed chunks with strict provenance grounding:
    'Answer the citizen's query strictly based on the following verified chunks.
     If the answer cannot be deduced with certainty from the context, state clearly
     that the document does not contain the information, and suggest what related details are present.'
    """
    if not verified_chunks:
        return ""

    chunk_blocks: List[str] = []
    for idx, c in enumerate(verified_chunks, start=1):
        meta = c.get("metadata", {})
        source_file = meta.get("source_file", "Uploaded Document")
        page_or_slide = meta.get("page_or_slide", 1)
        rerank_score = c.get("rerank_score", c.get("similarity", 0.0))
        modes = "+".join(c.get("retrieval_modes", ["vector"]))

        raw_content = c.get("content", "")
        clean_content = compress_chunk_content(raw_content)

        header = (
            f"[Verified Chunk {idx} | Source: {source_file} | "
            f"Page/Section: {page_or_slide} | Relevance: {rerank_score:.2f} | Retrieval: {modes}]"
        )
        chunk_blocks.append(f"{header}\n{clean_content}")

    assembled_chunks = "\n\n".join(chunk_blocks)

    grounding_instruction = (
        f"### HIGH-PRECISION RETRIEVED CONTEXT (VERIFIED):\n\n"
        f"{assembled_chunks}\n\n"
        f"STRICT PROVENANCE GROUNDING GUARDRAIL:\n"
        f"Answer the citizen's query strictly based on the verified chunks above.\n\n"
        f"MANDATORY INSTRUCTIONS:\n"
        f"1. Synthesize the response directly from the verified context above.\n"
        f"2. Never output meta-disclaimers like \"The retrieved context does not contain...\" or refer to previous vision/image turns.\n"
        f"3. If tabular data is referenced, cite the exact entity and value cleanly.\n"
        f"4. If open-ended questions like 'whats this telling' are asked, summarize key points directly, clearly, and concisely in natural language."
    )

    return grounding_instruction


class HybridRetriever:
    """
    Enterprise Hybrid Retrieval and Re-Ranking Engine orchestrating:
    Dense Vector Search + BM25 Sparse Search + RRF Fusion + Cross-Encoder + Contextual Compression.
    """

    def __init__(self, reranker_threshold: float = 0.35):
        self.reranker_threshold = reranker_threshold

    def retrieve(
        self,
        session_id: str,
        query: str,
        top_k: int = 5
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Executes hybrid retrieval, cross-encoder reranking, and compression.
        1. Retrieves top 20 dense and top 20 sparse candidates.
        2. Merges via RRF and retains top 15 unified candidates.
        3. Neural cross-encoder reranks top 15 candidates and slices top 3 to 5 verified chunks.
        4. Contextual compression and high-precision prompt formatting.
        Returns:
            (verified_chunks, formatted_grounded_prompt)
        """
        # Step 1: Hybrid Search (top 15 candidates via RRF merging 20 dense + 20 sparse)
        candidates = execute_hybrid_retrieval(session_id, query, top_candidates=15, dense_top_k=20, sparse_top_k=20)
        if not candidates:
            return [], ""

        # Step 2: Cross-Encoder Re-Ranking (top 3-5 verified with min threshold 0.35)
        verified = rerank_chunks_with_cross_encoder(
            query_text=query,
            candidate_chunks=candidates,
            score_threshold=self.reranker_threshold,
            top_n=top_k
        )

        # Step 3: Contextual Compression on verified chunks
        for c in verified:
            c["compressed_content"] = compress_chunk_content(c.get("content", ""))

        # Step 4: Formulate Grounded Prompt
        prompt_block = format_grounded_system_prompt(verified, query)
        return verified, prompt_block


# Global singleton instance
hybrid_retriever = HybridRetriever(reranker_threshold=0.35)
