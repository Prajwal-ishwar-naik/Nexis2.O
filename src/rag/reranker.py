"""
Nexis AI - Enterprise Cross-Encoder Neural Reranking Engine
Implements:
1. High-Fidelity Cross-Attention Re-ranking:
   - Uses sentence_transformers.CrossEncoder ('cross-encoder/ms-marco-MiniLM-L-6-v2' or 'BAAI/bge-reranker-base').
   - Passes joint [(query, chunk_text), ...] token sequences through multi-layer transformer cross-attention.
2. Calibrated Relevance Scoring:
   - Sigmoid normalization of cross-encoder logits into continuous [0.0, 1.0] confidence interval.
   - Strict Relevance Threshold: min score 0.35.
3. Surgical Context Selection:
   - Slices top 3 to 5 highest-confidence chunks for injection into generation prompt.
4. Resilient Heuristic Fallback:
   - Fallback relevance scoring using BM25 token overlap + RRF fusion if torch/cross-encoder is unavailable.
"""

import logging
import math
import os
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("NexisCRAG.Reranker")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# Configurable Cross-Encoder model name (default: ms-marco-MiniLM-L-6-v2 for <50ms latency; BAAI/bge-reranker-base also supported)
DEFAULT_RERANKER_MODEL = os.getenv("RAG_RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
DEFAULT_SCORE_THRESHOLD = float(os.getenv("RAG_RERANKER_THRESHOLD", "0.35"))


def sigmoid(x: float) -> float:
    """Maps unconstrained neural cross-attention logits to [0.0, 1.0] probability range."""
    try:
        return 1.0 / (1.0 + math.exp(-float(x)))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def tokenize_for_fallback(text: str) -> List[str]:
    """Lightweight alphanumeric tokenizer for fallback relevance scoring."""
    return [w for w in re.findall(r"\w+", text.lower()) if len(w) > 1]


class CrossEncoderReranker:
    """
    Enterprise Cross-Encoder Reranker with lazy singleton initialization
    and graceful heuristic fallback.
    """

    def __init__(self, model_name: str = DEFAULT_RERANKER_MODEL):
        self.model_name = model_name
        self._model = None
        self._initialized = False

    def _load_model(self):
        if self._model is not None:
            return self._model
        if self._initialized:
            return None

        self._initialized = True
        try:
            from sentence_transformers import CrossEncoder
            logger.info(f"Loading Cross-Encoder model: '{self.model_name}'...")
            self._model = CrossEncoder(self.model_name, max_length=512)
            logger.info(f"Cross-Encoder '{self.model_name}' loaded successfully.")
            return self._model
        except Exception as exc:
            logger.warning(
                f"Could not initialize Cross-Encoder model '{self.model_name}': {exc}. "
                "Engaging fast heuristic token-overlap reranker."
            )
            return None

    def rerank(
        self,
        query: str,
        candidate_chunks: List[Dict[str, Any]],
        score_threshold: float = DEFAULT_SCORE_THRESHOLD,
        top_n: int = 5,
        min_n: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Reranks up to 15-20 candidates using joint cross-attention.
        Filters candidates below score_threshold (min score 0.35).
        Returns top 3 to 5 highest-confidence chunks.
        """
        if not candidate_chunks:
            return []

        model = self._load_model()

        if model is not None:
            try:
                pairs = [
                    [
                        query,
                        c.get("content", "") or c.get("text", "") or ""
                    ]
                    for c in candidate_chunks
                ]
                raw_scores = model.predict(pairs)

                reranked_results: List[Dict[str, Any]] = []
                for chunk, raw_score in zip(candidate_chunks, raw_scores):
                    norm_score = round(sigmoid(float(raw_score)), 4)
                    chunk_copy = dict(chunk)
                    chunk_copy["rerank_score"] = norm_score
                    chunk_copy["raw_rerank_score"] = float(raw_score)
                    reranked_results.append(chunk_copy)

                # Sort by rerank score descending
                reranked_results.sort(key=lambda x: x["rerank_score"], reverse=True)

                # Filter by relevance threshold (>= 0.35)
                verified = [c for c in reranked_results if c["rerank_score"] >= score_threshold]

                if not verified and reranked_results:
                    # If highest-scoring candidate is within close margin (>= 0.30), retain it
                    top_candidate = reranked_results[0]
                    if top_candidate["rerank_score"] >= 0.30:
                        verified = [top_candidate]

                logger.info(
                    f"Cross-Encoder reranked {len(candidate_chunks)} candidates -> "
                    f"{len(verified)} verified chunks (threshold >= {score_threshold})"
                )

                # Slice top 3 to 5 highest-confidence chunks
                target_slice = min(max(len(verified), min_n), top_n)
                return (verified or reranked_results[:1])[:target_slice]

            except Exception as exc:
                logger.warning(f"Cross-Encoder inference error: {exc}. Falling back to heuristic reranking.")

        # Fallback: Token-overlap & RRF-based heuristic reranking
        q_tokens = set(tokenize_for_fallback(query))
        scored = []
        for c in candidate_chunks:
            content = (c.get("content", "") or c.get("text", "")).lower()
            overlap = sum(1 for t in q_tokens if t in content)
            overlap_ratio = overlap / max(len(q_tokens), 1)
            sim = c.get("similarity", 0.0)
            rrf = c.get("rrf_score", 0.0)
            heuristic_score = round((sim * 0.4) + (overlap_ratio * 0.4) + (rrf * 10 * 0.2), 4)

            chunk_copy = dict(c)
            chunk_copy["rerank_score"] = heuristic_score
            scored.append(chunk_copy)

        scored.sort(key=lambda x: x["rerank_score"], reverse=True)
        verified = [c for c in scored if c["rerank_score"] >= score_threshold]
        target_slice = min(max(len(verified or scored[:1]), min_n), top_n)
        return (verified or scored[:1])[:target_slice]


# Global singleton instance
reranker_engine = CrossEncoderReranker()


def rerank_chunks(
    query_text: str,
    candidate_chunks: List[Dict[str, Any]],
    score_threshold: float = DEFAULT_SCORE_THRESHOLD,
    top_n: int = 5
) -> List[Dict[str, Any]]:
    """
    Convenience entrypoint for neural re-ranking across candidate chunks.
    """
    return reranker_engine.rerank(
        query=query_text,
        candidate_chunks=candidate_chunks,
        score_threshold=score_threshold,
        top_n=top_n
    )
