"""
Nexis AI - Intelligent Tabular Entity Matcher & Fuzzy Resolver
Supports Microsoft 365 Copilot-style spreadsheet search:
1. Exact match check against primary text/entity columns.
2. RapidFuzz (with difflib fallback) token sort fuzzy candidate extraction.
3. Rejection of blind hallucination: when exact match is missing, returns formal
   citizen-service suggestions with matched candidate rows.
4. Prompt & context generator formatting EXACT, FUZZY_SUGGESTION, NOT_FOUND, and AGGREGATION contexts.
"""

import difflib
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from src.rag.tabular_engine import TabularDocument, tabular_registry

logger = logging.getLogger("NexisCRAG.EntityMatcher")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# Attempt to load RapidFuzz for high-speed C-optimized Levenshtein/TokenSort matching
try:
    from rapidfuzz import fuzz, process
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    logger.warning("rapidfuzz not installed; using standard library difflib as fallback.")


def search_tabular_entity(
    df: pd.DataFrame,
    column_name: str,
    query_value: str,
    threshold: int = 70
) -> Dict[str, Any]:
    """
    Core entity search on a specific DataFrame column:
    - Performs case-insensitive exact check.
    - If no exact match, performs token-ratio fuzzy candidate matching (threshold >= 70).
    - Returns structured status: EXACT, FUZZY_SUGGESTION, or NOT_FOUND.
    """
    if df.empty or column_name not in df.columns:
        return {"status": "NOT_FOUND", "data": [], "column": column_name, "query": query_value}

    clean_query = str(query_value).strip()
    if not clean_query:
        return {"status": "NOT_FOUND", "data": [], "column": column_name, "query": query_value}

    choices = df[column_name].dropna().astype(str).tolist()
    if not choices:
        return {"status": "NOT_FOUND", "data": [], "column": column_name, "query": clean_query}

    # 1. Exact case-insensitive check
    exact_matches = df[df[column_name].astype(str).str.strip().str.lower() == clean_query.lower()]
    if not exact_matches.empty:
        return {
            "status": "EXACT",
            "column": column_name,
            "query": clean_query,
            "matched_term": exact_matches[column_name].iloc[0],
            "data": exact_matches.to_dict(orient="records"),
            "total_matches": len(exact_matches)
        }

    # 2. Fuzzy candidate extraction
    matched_names: List[str] = []
    if RAPIDFUZZ_AVAILABLE:
        # RapidFuzz token_sort_ratio handles reordered name parts (e.g., 'Prajwal Ishwar' vs 'Ishwar Prajwal')
        candidates = process.extract(
            clean_query,
            choices,
            scorer=fuzz.token_sort_ratio,
            limit=4
        )
        relevant_candidates = [c for c in candidates if c[1] >= threshold]

        # Check WRatio as complementary scorer for prefix/suffix variations (e.g. 'Prajwal Nai' vs 'Prajwal Shetty')
        w_candidates = process.extract(
            clean_query,
            choices,
            scorer=fuzz.WRatio,
            limit=4
        )
        for wc in w_candidates:
            if wc[1] >= threshold and wc[0] not in [rc[0] for rc in relevant_candidates]:
                relevant_candidates.append(wc)

        # Preserve order while deduplicating
        seen = set()
        for c in relevant_candidates:
            term = str(c[0]).strip()
            if term and term.lower() not in seen:
                seen.add(term.lower())
                matched_names.append(term)
    else:
        # Standard library difflib fallback
        close_matches = difflib.get_close_matches(clean_query, choices, n=4, cutoff=threshold / 100.0)
        seen = set()
        for term in close_matches:
            term = str(term).strip()
            if term and term.lower() not in seen:
                seen.add(term.lower())
                matched_names.append(term)

    if matched_names:
        matched_rows = df[df[column_name].astype(str).isin(matched_names)]
        return {
            "status": "FUZZY_SUGGESTION",
            "column": column_name,
            "query": clean_query,
            "suggested_terms": matched_names,
            "data": matched_rows.to_dict(orient="records"),
            "total_suggestions": len(matched_names)
        }

    return {
        "status": "NOT_FOUND",
        "column": column_name,
        "query": clean_query,
        "data": [],
        "total_scanned": len(df)
    }


def extract_entity_search_term(query: str) -> str:
    """
    Extracts potential entity search term from conversational / natural language queries.
    Strips common search preambles and stop phrases.
    Examples:
    - 'Who is Prajwal Nai?' -> 'Prajwal Nai'
    - 'Show me the record for Prajwal Nai' -> 'Prajwal Nai'
    - 'Find details for Ramesh Kumar' -> 'Ramesh Kumar'
    - 'Find beneficiary Sunita' -> 'Sunita'
    """
    q = query.strip().rstrip("?").rstrip(".").strip()

    # Strip conversational query prefixes
    q = re.sub(r"^(?:please\s+)?(?:can\s+you\s+)?(?:what\s+is\s+)?(?:the\s+)?(?:record|details|information|info|profile|data|entry|status)\s+(?:of|for)\s+", "", q, flags=re.IGNORECASE)
    q = re.sub(r"^(?:please\s+)?(?:can\s+you\s+)?(?:show(?:\s+me)?|find(?:\s+me)?|search(?:\s+for)?|look\s+up|check|tell\s+me\s+about|get)\s+", "", q, flags=re.IGNORECASE)
    q = re.sub(r"^(?:the\s+)?(?:record|details|information|info|profile|data|entry|status)\s+(?:of|for)\s+", "", q, flags=re.IGNORECASE)
    q = re.sub(r"^(?:the\s+)?(?:record|details|information|info|profile|data|entry|status)\s+", "", q, flags=re.IGNORECASE)
    q = re.sub(r"^(?:for|of)\s+", "", q, flags=re.IGNORECASE)
    q = re.sub(r"^(?:who\s+(?:is|was|are))\s+", "", q, flags=re.IGNORECASE)
    q = re.sub(r"^(?:is\s+there\s+(?:a\s+record|anyone\s+named)\s+(?:for|of)?)\s+", "", q, flags=re.IGNORECASE)
    q = re.sub(r"\s+in\s+the\s+(?:roster|file|sheet|spreadsheet|table|document|list).*$", "", q, flags=re.IGNORECASE).strip()

    return q or query.strip()


def search_all_tabular_entities(
    df: pd.DataFrame,
    primary_columns: List[str],
    query_term: str,
    threshold: int = 70
) -> Dict[str, Any]:
    """
    Searches across all detected entity columns in the DataFrame.
    Prioritizes exact match; if none found, collects the strongest fuzzy suggestions.
    """
    if df.empty or not primary_columns:
        return {"status": "NOT_FOUND", "data": [], "query": query_term}

    best_fuzzy: Optional[Dict[str, Any]] = None

    for col in primary_columns:
        if col not in df.columns:
            continue
        res = search_tabular_entity(df, col, query_term, threshold=threshold)
        if res["status"] == "EXACT":
            return res
        if res["status"] == "FUZZY_SUGGESTION" and not best_fuzzy:
            best_fuzzy = res

    if best_fuzzy:
        return best_fuzzy

    return {
        "status": "NOT_FOUND",
        "columns_searched": primary_columns,
        "query": query_term,
        "data": [],
        "total_scanned": len(df)
    }


def format_records_as_markdown_table(records: List[Dict[str, Any]], max_rows: int = 6) -> str:
    """Formats a list of row dictionaries into a clean GitHub Flavored Markdown table."""
    if not records:
        return "*(No records)*"

    df_sample = pd.DataFrame(records).head(max_rows)
    # Convert all columns to strings, replacing NaN with empty
    df_sample = df_sample.fillna("-")
    headers = [str(c) for c in df_sample.columns]

    lines: List[str] = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |"
    ]

    for _, row in df_sample.iterrows():
        row_vals = [str(row[c]).replace("\n", " ").replace("|", "\\|") for c in headers]
        lines.append("| " + " | ".join(row_vals) + " |")

    return "\n".join(lines)


def format_tabular_prompt_context(
    result: Dict[str, Any],
    query: str,
    doc_filename: str,
    sheet_name: str,
    total_rows: int,
    available_columns: List[str]
) -> str:
    """
    Builds the CRAG context block adhering strictly to the user prompt blueprint:
    - EXACT: Polite, professional confirmation with complete Markdown table of attributes.
    - FUZZY_SUGGESTION: Formal citizen-service phrasing:
      'The exact record for '{Query}' was not found in the uploaded document. However, the system identified the following similar entries that may match your intent:'
      Followed by concise comparison table showing candidate names and relevant columns.
    - NOT_FOUND: States clearly that no records matched criteria, listing total count of scanned records and columns available.
    - AGGREGATION: Directly cites calculated column figures, formula, filters, and row count.
    """
    status = result.get("status")

    if status == "AGGREGATION_SUCCESS":
        metric = result.get("metric", "").upper()
        target_col = result.get("target_column", "")
        formatted_val = result.get("formatted_value", "")
        matching_count = result.get("matching_rows_count", 0)
        filters = result.get("filters_applied", [])
        sample_data = result.get("sample_data", [])

        filter_desc = (
            " with condition " + ", ".join([f"{f['column']} = '{f['value']}'" for f in filters])
            if filters else " across all rows"
        )

        table_md = format_records_as_markdown_table(sample_data, max_rows=5)

        return (
            f"### AUTHORITATIVE SPREADSHEET COMPUTATION ({doc_filename} | Sheet: {sheet_name}):\n"
            f"- Status: COMPUTED_COLUMN_AGGREGATION\n"
            f"- Calculated Metric: {metric} of '{target_col}' = **{formatted_val}**\n"
            f"- Scope: {matching_count} matching records ({filter_desc})\n"
            f"- Total Document Rows: {total_rows}\n\n"
            f"**INSTRUCTION FOR RESPONSE:**\n"
            f"Report this exact calculated figure (**{formatted_val}**) with zero estimation or guessing. "
            f"Explain clearly that this was computed directly from column '{target_col}' for the requested criteria.\n\n"
            f"Supporting Data Sample:\n{table_md}"
        )

    elif status == "EXACT":
        matched_term = result.get("matched_term", "")
        records = result.get("data", [])
        table_md = format_records_as_markdown_table(records)

        return (
            f"### AUTHORITATIVE SPREADSHEET RECORD LOCATED ({doc_filename} | Sheet: {sheet_name}):\n"
            f"- Retrieval Status: EXACT_RECORD_MATCH\n"
            f"- Matched Entity: '{matched_term}' (Column: {result.get('column')})\n"
            f"- Records Located: {len(records)}\n\n"
            f"**INSTRUCTION FOR RESPONSE:**\n"
            f"Provide a polite, professional confirmation that the exact record for '{matched_term}' was successfully located. "
            f"Present all attributes and columns in a complete, beautifully structured Markdown table.\n\n"
            f"{table_md}"
        )

    elif status == "FUZZY_SUGGESTION":
        suggested_terms = result.get("suggested_terms", [])
        terms_str = ", ".join([f"'{t}'" for t in suggested_terms])
        records = result.get("data", [])
        table_md = format_records_as_markdown_table(records)

        return (
            f"### SPREADSHEET ENTITY RESOLUTION ADVISORY ({doc_filename} | Sheet: {sheet_name}):\n"
            f"- Retrieval Status: FUZZY_SUGGESTION\n"
            f"- Searched Term: '{query}'\n"
            f"- Closest Identified Matches: {terms_str}\n\n"
            f"**MANDATORY CITIZEN-SERVICE PHRASING:**\n"
            f"Respond using the exact formal phrasing:\n"
            f"> \"The exact record for '{query}' was not found in the uploaded document. However, the system identified the following similar entries that may match your intent:\"\n\n"
            f"Follow this statement with the comparison table below showing the candidate records and relevant columns. "
            f"Do NOT invent fictional attributes or say a blind 'Not found'.\n\n"
            f"{table_md}"
        )

    else:  # NOT_FOUND or AGGREGATION_NO_MATCH
        columns_str = ", ".join(available_columns)
        return (
            f"### SPREADSHEET SEARCH NOTICE ({doc_filename} | Sheet: {sheet_name}):\n"
            f"- Retrieval Status: RECORD_NOT_FOUND\n"
            f"- Scanned Query: '{query}'\n"
            f"- Records Scanned: {total_rows} total rows\n"
            f"- Available Columns: {columns_str}\n\n"
            f"**INSTRUCTION FOR RESPONSE:**\n"
            f"State clearly that no records matching '{query}' were found in the uploaded document '{doc_filename}'. "
            f"Specify that all {total_rows} records were scanned across available columns ({columns_str}). "
            f"Offer to search using an alternative identifier, registration number, or category."
        )


def resolve_tabular_query(
    session_id: str,
    query: str,
    filename: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Master resolution pipeline for tabular sessions:
    1. Checks if session contains registered spreadsheets.
    2. Runs direct aggregation engine (sum, average, count, etc.).
    3. Runs entity lookup (exact -> fuzzy -> not-found).
    4. Returns structured resolution dictionary with rendered prompt context.
    """
    if not tabular_registry.has_tabular(session_id):
        return None

    doc = tabular_registry.get_document(session_id, filename)
    if not doc or doc.primary_df.empty or not doc.primary_meta:
        return None

    df = doc.primary_df
    meta = doc.primary_meta

    # 1. Check for numerical aggregation intent
    agg_result = tabular_registry.execute_aggregation(session_id, query, filename)
    if agg_result and agg_result.get("status") == "AGGREGATION_SUCCESS":
        context_md = format_tabular_prompt_context(
            result=agg_result,
            query=query,
            doc_filename=doc.filename,
            sheet_name=meta.sheet_name,
            total_rows=meta.total_rows,
            available_columns=meta.columns
        )
        return {
            "type": "aggregation",
            "resolution": agg_result,
            "context_prompt": context_md,
            "filename": doc.filename,
            "sheet_name": meta.sheet_name
        }

    # 2. Extract potential entity term from query
    search_term = extract_entity_search_term(query)

    # 3. Search entity columns
    entity_result = search_all_tabular_entities(
        df=df,
        primary_columns=meta.primary_text_columns or meta.columns,
        query_term=search_term,
        threshold=70
    )

    # If the extracted search term didn't match and was different from full query, try full query
    if entity_result["status"] == "NOT_FOUND" and search_term.lower() != query.lower().strip():
        # Check if any words in the query match an entity
        for token in query.split():
            if len(token) > 3 and token.lower() not in ["show", "find", "search", "what", "where", "tell", "record"]:
                candidate_sub = search_all_tabular_entities(
                    df=df,
                    primary_columns=meta.primary_text_columns or meta.columns,
                    query_term=token,
                    threshold=75
                )
                if candidate_sub["status"] in ["EXACT", "FUZZY_SUGGESTION"]:
                    entity_result = candidate_sub
                    search_term = token
                    break

    context_md = format_tabular_prompt_context(
        result=entity_result,
        query=search_term,
        doc_filename=doc.filename,
        sheet_name=meta.sheet_name,
        total_rows=meta.total_rows,
        available_columns=meta.columns
    )

    return {
        "type": "entity_search",
        "resolution": entity_result,
        "context_prompt": context_md,
        "filename": doc.filename,
        "sheet_name": meta.sheet_name,
        "status": entity_result.get("status")
    }
