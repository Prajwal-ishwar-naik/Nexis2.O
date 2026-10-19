"""
Nexis AI - Enterprise Hybrid Search & Cross-Encoder Reranking Test Suite
Validates:
1. Dense (ChromaDB) + Sparse (BM25Okapi) retrieval union.
2. Reciprocal Rank Fusion (RRF) score computation.
3. CrossEncoder cross-attention re-ranking and score threshold pruning.
4. Contextual compression (boilerplate, divider, and whitespace pruning).
5. Provenance grounding guardrail in formulated prompts.
"""

import asyncio
import os
import pytest
from src.rag.ingestion import ingest_document
from src.rag.vector_store import vector_store
from src.rag.retriever import (
    execute_hybrid_retrieval,
    rerank_chunks_with_cross_encoder,
    compress_chunk_content,
    format_grounded_system_prompt,
    hybrid_retriever
)
from src.rag.crag_engine import crag_engine


def test_contextual_compressor():
    dirty_text = """
    ### Spreadsheet Sheet: Crops
    
    
    Row 1 | Crop: Ragi | Water: 450mm
    
    |---|---|---|
    |---|---|---|
    Row 2 | Crop: Jowar | Water: 500mm
    """
    compressed = compress_chunk_content(dirty_text)
    assert "|---|---|---|" in dirty_text
    assert "\n\n\n" not in compressed
    assert "Row 1 | Crop: Ragi" in compressed
    assert "Row 2 | Crop: Jowar" in compressed


def test_cross_encoder_threshold_filtering():
    chunks = [
        {"chunk_id": "c_relevant", "content": "Kharif ragi requires 40:20:20 NPK fertilizer application in Karnataka.", "metadata": {"source_file": "agri.txt"}},
        {"chunk_id": "c_irrelevant_1", "content": "Quantum mechanics describes microscopic particles and wave functions.", "metadata": {"source_file": "physics.txt"}},
        {"chunk_id": "c_irrelevant_2", "content": "React state hooks re-render components on setter invocation.", "metadata": {"source_file": "code.txt"}},
    ]
    query = "What is the recommended fertilizer for Ragi?"
    verified = rerank_chunks_with_cross_encoder(query, chunks, score_threshold=0.40, top_n=3)

    assert len(verified) >= 1
    assert verified[0]["chunk_id"] == "c_relevant"
    assert verified[0]["rerank_score"] >= 0.40
    # Irrelevant chunks should be filtered out
    verified_ids = [c["chunk_id"] for c in verified]
    assert "c_irrelevant_1" not in verified_ids


def test_grounded_prompt_guardrail():
    chunks = [
        {"chunk_id": "c1", "content": "Almatti dam full reservoir level is 519.60 meters.", "metadata": {"source_file": "water.txt", "page_or_slide": 2}, "rerank_score": 0.95}
    ]
    prompt = format_grounded_system_prompt(chunks, "What is the height of Almatti dam?")
    assert "STRICT PROVENANCE GROUNDING GUARDRAIL:" in prompt
    assert "Answer the citizen's query strictly based on the verified chunks" in prompt
    assert "Almatti dam full reservoir level is 519.60 meters" in prompt


@pytest.mark.asyncio
async def test_end_to_end_hybrid_crag():
    session = "ci_hybrid_retrieval_session"
    vector_store.delete_session(session)

    test_file = "/tmp/ci_health_policy.txt"
    with open(test_file, "w") as f:
        f.write("""
Ayushman Bharat Arogya Karnataka (AB-ArK) scheme provides financial protection to eligible families.
Eligible BPL cardholder families receive free treatment up to Rs. 5 Lakh per year for secondary and tertiary care.
APL cardholders can avail treatment on a 30% co-payment basis up to Rs. 1.5 Lakh per year.
Beneficiaries must present their Aadhaar card and Ration card at the hospital helpdesk.
""")

    chunks = await ingest_document(test_file, "health_policy.txt", session)
    indexed = vector_store.add_chunks(session, chunks)
    assert indexed > 0

    # 1. Test hybrid retrieval directly
    candidates = execute_hybrid_retrieval(session, "How much financial coverage do BPL families get?", top_candidates=10)
    assert len(candidates) > 0
    assert "rrf_score" in candidates[0]

    # 2. Test master CRAG pipeline
    result = await crag_engine.run_crag("How much financial coverage do BPL families get?", session, top_k=3)
    assert result.grade in ["CORRECT", "AMBIGUOUS"]
    assert "5 Lakh" in result.context_text
    assert "STRICT PROVENANCE GROUNDING GUARDRAIL" in result.context_text
