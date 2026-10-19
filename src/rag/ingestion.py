"""
Nexis AI - Adaptive Document Ingestion & Parsing Engine
Supports: .pdf, .docx, .pptx, .xlsx, .csv, .txt, .md
Performs structure analysis, adaptive semantic chunking, metadata tagging,
and strict privacy/PII scrubbing before vectorization.
"""

import os
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple
import logging

logger = logging.getLogger("NexisCRAG.Ingestion")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# ==============================================================================
# 1. Privacy & Compliance Redaction Guardrail
# ==============================================================================

def redact_sensitive_identifiers(text: str) -> str:
    """
    Scrubs sensitive national IDs (Aadhaar, Korean RRN, Japanese MyNumber)
    before vector indexing and LLM prompt compilation.
    """
    if not text or not isinstance(text, str):
        return text or ""
    # 1. Japanese MyNumber / Generic national ID (e.g. MyNumber: 123456789012 or 12 continuous digits)
    text = re.sub(r"\b(MyNumber|National ID)[:\s]*\d{12}\b", r"\1: [ID Redacted]", text, flags=re.IGNORECASE)
    # 2. Korean RRN (6 digits - 7 digits)
    text = re.sub(r"\b\d{6}-[1-4]\d{6}\b", "[RRN Redacted]", text)
    # 3. Aadhaar (12 digits, continuous or 4-4-4 formatted)
    text = re.sub(r"\b\d{4}\s?\d{4}\s?\d{4}\b", "[Aadhaar Redacted]", text)
    return text


# ==============================================================================
# 2. Format-Specific Document Parsers
# ==============================================================================

def parse_pdf(file_path: str) -> List[Dict[str, Any]]:
    """
    Parses PDF documents page-by-page using pypdf.
    Returns a list of page dicts with text and page numbers.
    """
    import pypdf
    pages: List[Dict[str, Any]] = []
    try:
        reader = pypdf.PdfReader(file_path)
        total_pages = len(reader.pages)
        for idx, page in enumerate(reader.pages):
            extracted = page.extract_text() or ""
            extracted = extracted.strip()
            if extracted:
                pages.append({
                    "page_or_slide": idx + 1,
                    "text": extracted,
                    "is_slide": False,
                    "total_pages": total_pages
                })
    except Exception as exc:
        logger.error(f"Error parsing PDF '{file_path}': {exc}")
        raise ValueError(f"Failed to parse PDF document: {str(exc)}")
    return pages


def parse_docx(file_path: str) -> List[Dict[str, Any]]:
    """
    Parses Word documents using python-docx, preserving hierarchical headings and tables.
    """
    import docx
    pages: List[Dict[str, Any]] = []
    try:
        doc = docx.Document(file_path)
        content_parts: List[str] = []
        page_counter = 1

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            if para.style.name.startswith("Heading 1"):
                if content_parts:
                    pages.append({
                        "page_or_slide": page_counter,
                        "text": "\n\n".join(content_parts),
                        "is_slide": False
                    })
                    content_parts = []
                    page_counter += 1
                content_parts.append(f"# {text}")
            elif para.style.name.startswith("Heading 2"):
                content_parts.append(f"## {text}")
            elif para.style.name.startswith("Heading 3"):
                content_parts.append(f"### {text}")
            else:
                content_parts.append(text)

        # Parse tables into structured markdown
        for t_idx, table in enumerate(doc.tables):
            table_md: List[str] = [f"Table {t_idx + 1}:"]
            headers = [cell.text.strip().replace("\n", " ") for cell in table.rows[0].cells]
            table_md.append("| " + " | ".join(headers) + " |")
            table_md.append("| " + " | ".join(["---"] * len(headers)) + " |")
            for row in table.rows[1:]:
                row_cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                table_md.append("| " + " | ".join(row_cells) + " |")
            content_parts.append("\n".join(table_md))

        if content_parts:
            pages.append({
                "page_or_slide": page_counter,
                "text": "\n\n".join(content_parts),
                "is_slide": False
            })

    except Exception as exc:
        logger.error(f"Error parsing DOCX '{file_path}': {exc}")
        raise ValueError(f"Failed to parse DOCX document: {str(exc)}")
    return pages


def parse_pptx(file_path: str) -> List[Dict[str, Any]]:
    """
    Parses PowerPoint presentations (.pptx) strictly slide-by-slide:
    Format: 'Slide {N}: Title + bullet points'
    """
    from pptx import Presentation
    slides: List[Dict[str, Any]] = []
    try:
        prs = Presentation(file_path)
        for idx, slide in enumerate(prs.slides):
            slide_num = idx + 1
            slide_title = ""
            slide_bullets: List[str] = []

            for shape in slide.shapes:
                if shape.has_text_frame:
                    text_frame = shape.text_frame
                    for p_idx, paragraph in enumerate(text_frame.paragraphs):
                        text = paragraph.text.strip()
                        if not text:
                            continue
                        # Identify title if at top or title shape
                        if not slide_title and (shape == slide.shapes.title or p_idx == 0):
                            slide_title = text
                        else:
                            slide_bullets.append(f"- {text}")

            title_str = slide_title if slide_title else f"Slide {slide_num}"
            bullet_str = "\n".join(slide_bullets) if slide_bullets else "(Visual/Graphic content)"
            slide_text = f"Slide {slide_num}: {title_str}\n{bullet_str}"

            slides.append({
                "page_or_slide": slide_num,
                "text": slide_text,
                "is_slide": True,
                "total_pages": len(prs.slides)
            })
    except Exception as exc:
        logger.error(f"Error parsing PPTX '{file_path}': {exc}")
        raise ValueError(f"Failed to parse PPTX presentation: {str(exc)}")
    return slides


def parse_tabular(file_path: str, ext: str, original_filename: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Parses spreadsheets (.xlsx, .xls, .csv) with pandas/openpyxl via TabularRegistry.
    Converts tabular rows to structured representations with headers preserved:
    'Row {index} | Column1: Value1 | Column2: Value2 | ...'
    """
    from src.rag.tabular_engine import tabular_registry
    try:
        sections = tabular_registry.to_markdown_row_chunks(
            file_path=file_path,
            filename=original_filename or os.path.basename(file_path)
        )
        if not sections:
            raise ValueError("No non-empty spreadsheet sheets found.")
        return sections
    except Exception as exc:
        logger.error(f"Error parsing tabular data '{file_path}': {exc}")
        raise ValueError(f"Failed to parse spreadsheet file: {str(exc)}")


def parse_txt(file_path: str) -> List[Dict[str, Any]]:
    """
    Parses plain text / markdown files.
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read().strip()
        if not content:
            return []
        return [{
            "page_or_slide": 1,
            "text": content,
            "is_slide": False
        }]
    except Exception as exc:
        logger.error(f"Error reading text file '{file_path}': {exc}")
        raise ValueError(f"Failed to parse text document: {str(exc)}")


# ==============================================================================
# 3. Adaptive Chunking Strategy
# ==============================================================================

def recursive_character_split(
    text: str,
    chunk_size_chars: int,
    overlap_chars: int,
    separators: Optional[List[str]] = None
) -> List[str]:
    """
    Hierarchical recursive text splitter adhering to markdown headers, double newlines,
    and sentence boundaries without cutting words.
    """
    if separators is None:
        separators = ["\n# ", "\n## ", "\n### ", "\n\n", "\n", ". ", " "]

    if len(text) <= chunk_size_chars:
        return [text.strip()] if text.strip() else []

    # Find the highest priority separator present in the text
    chosen_sep = ""
    for sep in separators:
        if sep in text:
            chosen_sep = sep
            break

    if not chosen_sep:
        # Fallback character slice
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size_chars, len(text))
            chunks.append(text[start:end].strip())
            start += chunk_size_chars - overlap_chars
        return [c for c in chunks if c]

    splits = text.split(chosen_sep)
    chunks: List[str] = []
    current_chunk = ""

    for s in splits:
        piece = s if not chosen_sep.startswith("\n#") else (chosen_sep.strip() + " " + s)
        piece = piece.strip()
        if not piece:
            continue

        if not current_chunk:
            current_chunk = piece
        elif len(current_chunk) + len(piece) + len(chosen_sep) <= chunk_size_chars:
            current_chunk += chosen_sep + piece
        else:
            chunks.append(current_chunk.strip())
            # Maintain sliding overlap from tail of previous chunk
            if overlap_chars > 0 and len(current_chunk) > overlap_chars:
                overlap_seed = current_chunk[-overlap_chars:]
                current_chunk = overlap_seed + chosen_sep + piece
            else:
                current_chunk = piece

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return [c for c in chunks if c]


def adaptively_chunk_document(
    parsed_sections: List[Dict[str, Any]],
    source_filename: str,
    session_id: str
) -> List[Dict[str, Any]]:
    """
    Dynamically sizes chunk windows based on document structure:
    - Presentation slides: Strictly chunk per slide ('Slide {N}: Title + bullet points').
    - Small structured / Tabular files (< 5 pages / tabular sheets):
      Smaller semantic window (300-500 tokens ~ 1200-2000 chars, 50 token overlap ~ 200 chars).
    - Multi-page / Dense narrative (> 10 pages):
      Larger hierarchical recursive text splitting capped at 800-1000 tokens (~3200-4000 chars, 150 token overlap ~ 600 chars).
    - Standard documents (5-10 pages):
      Balanced window (600 tokens ~ 2400 chars, 100 token overlap ~ 400 chars).
    """
    total_sections = len(parsed_sections)
    is_slide_deck = any(s.get("is_slide", False) for s in parsed_sections)
    is_tabular = any(s.get("is_tabular", False) for s in parsed_sections)

    # 1. Slide Deck: 1 slide = 1 chunk
    if is_slide_deck:
        final_chunks: List[Dict[str, Any]] = []
        for s in parsed_sections:
            clean_text = redact_sensitive_identifiers(s["text"].strip())
            if not clean_text:
                continue
            chunk_id = f"chunk_{uuid.uuid4().hex[:12]}"
            final_chunks.append({
                "chunk_id": chunk_id,
                "text": clean_text,
                "metadata": {
                    "source_file": source_filename,
                    "page_or_slide": s.get("page_or_slide", 1),
                    "chunk_id": chunk_id,
                    "session_id": session_id,
                    "type": "presentation_slide"
                }
            })
        return final_chunks

    # 2. Determine chunk size & overlap based on page density & tabular nature
    if is_tabular or total_sections < 5:
        # Small structured files / spreadsheets: 300-500 tokens (1400 chars, 200 overlap)
        chunk_size_chars = 1500
        overlap_chars = 200
        chunk_type = "small_structured"
    elif total_sections > 10:
        # Multi-page / dense narrative: 800-1000 tokens (3600 chars, 600 overlap)
        chunk_size_chars = 3600
        overlap_chars = 600
        chunk_type = "dense_narrative"
    else:
        # Standard mid-length: 600 tokens (2400 chars, 400 overlap)
        chunk_size_chars = 2400
        overlap_chars = 400
        chunk_type = "standard_document"

    final_chunks: List[Dict[str, Any]] = []

    for section in parsed_sections:
        page_num = section.get("page_or_slide", 1)
        raw_text = section.get("text", "")
        # Apply strict PII redaction guardrail
        redacted_text = redact_sensitive_identifiers(raw_text)

        split_pieces = recursive_character_split(
            redacted_text,
            chunk_size_chars=chunk_size_chars,
            overlap_chars=overlap_chars
        )

        for p_idx, piece in enumerate(split_pieces):
            clean_piece = piece.strip()
            if not clean_piece:
                continue
            chunk_id = f"chunk_{uuid.uuid4().hex[:12]}"
            final_chunks.append({
                "chunk_id": chunk_id,
                "text": clean_piece,
                "metadata": {
                    "source_file": source_filename,
                    "page_or_slide": page_num,
                    "chunk_id": chunk_id,
                    "session_id": session_id,
                    "type": chunk_type,
                    "chunk_index": p_idx + 1
                }
            })

    return final_chunks


# ==============================================================================
# 4. Master Ingestion Entrypoint
# ==============================================================================

async def ingest_document(
    file_path: str,
    original_filename: str,
    session_id: str
) -> List[Dict[str, Any]]:
    """
    Ingests and adaptively chunks any supported document (.pdf, .docx, .pptx, .xlsx, .csv, .txt, .md).
    Returns a list of structured chunks with metadata ready for embedding and vector storage.
    """
    ext = os.path.splitext(original_filename)[1].lower()

    if ext == ".pdf":
        sections = parse_pdf(file_path)
    elif ext in [".docx", ".doc"]:
        sections = parse_docx(file_path)
    elif ext in [".pptx", ".ppt"]:
        sections = parse_pptx(file_path)
    elif ext in [".xlsx", ".xls", ".csv"]:
        from src.rag.tabular_engine import tabular_registry
        try:
            tabular_registry.register_file(file_path, original_filename, session_id)
        except Exception as reg_err:
            logger.warning(f"Could not register spreadsheet in tabular_registry: {reg_err}")
        sections = parse_tabular(file_path, ext, original_filename)
    elif ext in [".txt", ".md", ".json", ".log"]:
        sections = parse_txt(file_path)
    else:
        # Fallback to plain text reader
        sections = parse_txt(file_path)

    if not sections:
        raise ValueError(f"No extractable text found in file '{original_filename}'.")

    chunks = adaptively_chunk_document(
        parsed_sections=sections,
        source_filename=original_filename,
        session_id=session_id
    )

    logger.info(
        f"Ingested '{original_filename}' for session '{session_id}': "
        f"{len(sections)} sections parsed -> {len(chunks)} adaptive chunks generated."
    )
    return chunks


def ingest_file(file_path: str, session_id: str = "default") -> Dict[str, Any]:
    """
    Synchronous helper wrapper to ingest and index a file into vector store.
    """
    import asyncio
    filename = os.path.basename(file_path)

    def _run_in_new_loop():
        return asyncio.run(ingest_document(file_path, filename, session_id))

    try:
        chunks = _run_in_new_loop()
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(_run_in_new_loop)
            chunks = future.result()

    from src.rag.vector_store import vector_store
    indexed_count = vector_store.add_chunks(session_id, chunks) if vector_store else len(chunks)
    return {
        "status": "success",
        "filename": filename,
        "session_id": session_id,
        "chunks_count": indexed_count,
        "chunks_indexed": indexed_count
    }

