import asyncio
import pytest
from src.rag.crag_engine import (
    is_broad_or_summary_query,
    compile_full_document_context,
    DOCUMENT_GROUNDING_DIRECTIVE,
    CorrectiveRAGEngine
)
from src.rag.vector_store import vector_store


def test_is_broad_or_summary_query():
    # User's exact prompt from screenshot
    assert is_broad_or_summary_query("whats this telling") is True
    assert is_broad_or_summary_query("what is this telling") is True
    assert is_broad_or_summary_query("what does this tell") is True
    assert is_broad_or_summary_query("what is this") is True
    assert is_broad_or_summary_query("summarize this") is True
    assert is_broad_or_summary_query("summary") is True
    assert is_broad_or_summary_query("explain this document") is True
    assert is_broad_or_summary_query("what is this report about?") is True
    assert is_broad_or_summary_query("give me the key points") is True
    assert is_broad_or_summary_query("can you read this") is True
    assert is_broad_or_summary_query("what is in this") is True
    assert is_broad_or_summary_query("") is True

    # Specific factual queries should NOT trigger broad query
    assert is_broad_or_summary_query("What was the maximum mark allocated for the literature survey criterion?") is False
    assert is_broad_or_summary_query("Who is the external examiner mentioned in section 4?") is False


def test_compile_full_document_context():
    sample_chunks = [
        {
            "chunk_id": "chunk_2",
            "content": "Page 2 content: Evaluation Rubrics for CSE7000 Internship Review.",
            "metadata": {"source_file": "CSE7000.pdf", "page_or_slide": 2, "chunk_index": 2}
        },
        {
            "chunk_id": "chunk_1",
            "content": "Page 1 content: Project Guidelines and Review Dates.",
            "metadata": {"source_file": "CSE7000.pdf", "page_or_slide": 1, "chunk_index": 1}
        }
    ]

    sorted_chunks, assembled_context = compile_full_document_context(sample_chunks)
    assert len(sorted_chunks) == 2
    # Verify sorting by page/chunk_index: chunk_1 should come first
    assert sorted_chunks[0]["chunk_id"] == "chunk_1"
    assert sorted_chunks[1]["chunk_id"] == "chunk_2"

    # Context should contain both pages sequentially
    assert "Page 1 content" in assembled_context
    assert "Page 2 content" in assembled_context
    assert "DOCUMENT GROUNDING DIRECTIVE" in assembled_context
    assert "State clearly that the document does not contain" not in assembled_context
    assert "cross-encoder threshold 0.40" not in assembled_context


@pytest.mark.asyncio
async def test_crag_small_doc_aggregation(monkeypatch):
    crag = CorrectiveRAGEngine()
    session_id = "test_small_doc_session_99"

    # Seed 17 chunks (same as the user's CSE7000 PDF)
    fake_chunks = [
        {
            "chunk_id": f"c_{i}",
            "content": f"Section {i}: Academic and internship deliverables for phase {i}.",
            "metadata": {
                "source_file": "CSE7000-Internship_Review_Template.pdf",
                "page_or_slide": i,
                "chunk_index": i
            }
        }
        for i in range(1, 18)
    ]

    # Mock vector_store methods
    monkeypatch.setattr(vector_store, "has_documents", lambda s: True if s == session_id else False)
    monkeypatch.setattr(vector_store, "get_all_chunks", lambda s: fake_chunks if s == session_id else [])

    # Test broad inquiry: "whats this telling"
    result = await crag.run_crag("whats this telling", session_id)
    assert result.grade == "CORRECT"
    assert result.confidence >= 0.9
    assert len(result.retrieved_chunks) == 17
    assert "Section 1:" in result.context_text
    assert "Section 17:" in result.context_text
    assert "DOCUMENT GROUNDING DIRECTIVE" in result.context_text
    # Verify old guardrail is gone and clean directive is used
    assert "State clearly that the document does not contain" not in result.context_text
    assert "cross-encoder threshold" not in result.context_text.lower()
