"""
Nexis AI - Intelligent Tabular Parser & Schema Registry (Copilot-Style Spreadsheet Engine)
Supports .xlsx, .xls, and .csv files:
1. Ingests tabular data preserving schema, column relationships, and data types.
2. Identifies primary text/entity columns and extracts distinct entity indexes.
3. Computes summary statistics on numeric columns.
4. Generates row-wise structured Markdown representations:
   'Row {index} | Column1: Value1 | Column2: Value2 | ...'
5. Performs direct in-memory column aggregations (sum, average, count, min, max, with filtering).
"""

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger("NexisCRAG.TabularEngine")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


# Common patterns for entity/primary identifier columns
ENTITY_COLUMN_KEYWORDS = [
    "name", "farmer", "beneficiary", "citizen", "person", "student", "patient",
    "applicant", "vendor", "officer", "employee", "contact", "customer", "member",
    "id", "aadhaar", "voter", "district", "state", "village", "city", "taluk",
    "ward", "block", "panchayat", "department", "scheme", "crop", "item", "hospital",
    "school", "category", "status"
]

# Common patterns for aggregation metrics
NUMERIC_KEYWORDS = [
    "expenditure", "expense", "cost", "amount", "price", "budget", "salary",
    "income", "revenue", "acres", "area", "yield", "quantity", "weight",
    "production", "total", "fee", "fund", "balance", "score", "marks", "target",
    "rate", "water_req", "rainfall"
]


@dataclass
class TabularSheetMetadata:
    sheet_name: str
    total_rows: int
    columns: List[str]
    primary_text_columns: List[str]
    numeric_columns: List[str]
    column_types: Dict[str, str]
    summary_stats: Dict[str, Dict[str, Any]]
    distinct_entities: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class TabularDocument:
    filename: str
    session_id: str
    sheets: Dict[str, pd.DataFrame]
    sheet_metadata: Dict[str, TabularSheetMetadata]
    primary_sheet_name: str

    @property
    def primary_df(self) -> pd.DataFrame:
        return self.sheets.get(self.primary_sheet_name, pd.DataFrame())

    @property
    def primary_meta(self) -> Optional[TabularSheetMetadata]:
        return self.sheet_metadata.get(self.primary_sheet_name)


class TabularRegistry:
    """
    Session-scoped in-memory cache and registry for parsed spreadsheets.
    """

    def __init__(self):
        # session_id -> {filename: TabularDocument}
        self._session_cache: Dict[str, Dict[str, TabularDocument]] = {}

    def has_tabular(self, session_id: str) -> bool:
        return session_id in self._session_cache and len(self._session_cache[session_id]) > 0

    def get_documents(self, session_id: str) -> List[TabularDocument]:
        return list(self._session_cache.get(session_id, {}).values())

    def get_document(self, session_id: str, filename: Optional[str] = None) -> Optional[TabularDocument]:
        docs = self._session_cache.get(session_id, {})
        if not docs:
            return None
        if filename and filename in docs:
            return docs[filename]
        # Return the most recently registered document
        return list(docs.values())[-1]

    def clear_session(self, session_id: str) -> None:
        if session_id in self._session_cache:
            del self._session_cache[session_id]

    def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Cleans headers and removes completely empty rows/columns."""
        # Strip string whitespace in column names
        df.columns = [str(c).strip() for c in df.columns]
        # Remove unnamed index columns that are entirely NaN
        drop_cols = [c for c in df.columns if c.startswith("Unnamed:") and df[c].isna().all()]
        if drop_cols:
            df = df.drop(columns=drop_cols)
        # Drop rows where all values are NaN
        df = df.dropna(how="all").reset_index(drop=True)
        return df

    def _analyze_sheet_schema(self, sheet_name: str, df: pd.DataFrame) -> TabularSheetMetadata:
        """
        Analyzes DataFrame schema to identify entity columns, numeric columns,
        and computes summary statistics.
        """
        columns = [str(c) for c in df.columns]
        primary_text_cols: List[str] = []
        numeric_cols: List[str] = []
        col_types: Dict[str, str] = {}
        summary_stats: Dict[str, Dict[str, Any]] = {}
        distinct_entities: Dict[str, List[str]] = {}

        for col in columns:
            dtype_str = str(df[col].dtype)
            col_types[col] = dtype_str
            col_lower = col.lower()

            # Attempt numeric conversion for columns with numbers or currency
            is_numeric = False
            if pd.api.types.is_numeric_dtype(df[col]):
                is_numeric = True
            else:
                # Try numeric conversion if values look like numbers
                non_null = df[col].dropna()
                if len(non_null) > 0:
                    converted = pd.to_numeric(non_null.astype(str).str.replace(r"[$,₹\s]", "", regex=True), errors="coerce")
                    if converted.notna().sum() / len(non_null) > 0.8:
                        is_numeric = True

            if is_numeric:
                numeric_cols.append(col)
                series = pd.to_numeric(df[col].astype(str).str.replace(r"[$,₹\s]", "", regex=True), errors="coerce").dropna()
                if not series.empty:
                    summary_stats[col] = {
                        "count": int(series.count()),
                        "sum": float(round(series.sum(), 2)),
                        "mean": float(round(series.mean(), 2)),
                        "min": float(round(series.min(), 2)),
                        "max": float(round(series.max(), 2)),
                    }
            else:
                # Text / Entity column evaluation
                has_entity_keyword = any(kw in col_lower for kw in ENTITY_COLUMN_KEYWORDS)
                nunique = df[col].nunique(dropna=True)
                # Primary text column if keyword matches or reasonable cardinality
                if has_entity_keyword or (1 < nunique <= len(df)):
                    primary_text_cols.append(col)

                # Extract distinct entity values (limit to top 500 for token/memory safety)
                unique_vals = [
                    str(v).strip()
                    for v in df[col].dropna().unique()
                    if str(v).strip() and str(v).lower() not in ["nan", "none", "null", "-", ""]
                ]
                distinct_entities[col] = unique_vals[:500]

        # Prioritize columns with entity keywords first
        primary_text_cols.sort(
            key=lambda c: any(kw in c.lower() for kw in ENTITY_COLUMN_KEYWORDS),
            reverse=True
        )

        return TabularSheetMetadata(
            sheet_name=sheet_name,
            total_rows=len(df),
            columns=columns,
            primary_text_columns=primary_text_cols,
            numeric_columns=numeric_cols,
            column_types=col_types,
            summary_stats=summary_stats,
            distinct_entities=distinct_entities
        )

    def register_file(self, file_path: str, filename: str, session_id: str) -> TabularDocument:
        """
        Ingests .xlsx, .xls, or .csv using pandas and openpyxl, registers schema,
        and saves in the session cache.
        """
        ext = os.path.splitext(filename)[1].lower()
        sheets: Dict[str, pd.DataFrame] = {}
        sheet_metadata: Dict[str, TabularSheetMetadata] = {}

        try:
            if ext == ".csv":
                df = pd.read_csv(file_path)
                df = self._clean_dataframe(df)
                sheet_name = "Sheet1"
                sheets[sheet_name] = df
                sheet_metadata[sheet_name] = self._analyze_sheet_schema(sheet_name, df)
            else:
                excel_file = pd.ExcelFile(file_path, engine="openpyxl")
                for s_name in excel_file.sheet_names:
                    df = pd.read_excel(excel_file, sheet_name=s_name)
                    df = self._clean_dataframe(df)
                    if not df.empty:
                        sheets[s_name] = df
                        sheet_metadata[s_name] = self._analyze_sheet_schema(s_name, df)

            if not sheets:
                raise ValueError(f"Spreadsheet '{filename}' contains no readable data.")

            primary_sheet = list(sheets.keys())[0]

            tab_doc = TabularDocument(
                filename=filename,
                session_id=session_id,
                sheets=sheets,
                sheet_metadata=sheet_metadata,
                primary_sheet_name=primary_sheet
            )

            if session_id not in self._session_cache:
                self._session_cache[session_id] = {}
            self._session_cache[session_id][filename] = tab_doc

            logger.info(
                f"Registered tabular file '{filename}' for session '{session_id}': "
                f"{len(sheets)} sheets, primary='{primary_sheet}' ({len(tab_doc.primary_df)} rows, "
                f"{len(tab_doc.primary_meta.columns)} cols, "
                f"entity_cols={tab_doc.primary_meta.primary_text_columns})"
            )
            return tab_doc

        except Exception as exc:
            logger.error(f"Error reading and registering spreadsheet '{filename}': {exc}")
            raise ValueError(f"Failed to register spreadsheet: {str(exc)}")

    def to_markdown_row_chunks(
        self,
        file_path: str,
        filename: str,
        max_rows_per_sheet: int = 500
    ) -> List[Dict[str, Any]]:
        """
        Generates row-wise structured Markdown representations with full headers preserved:
        `Row {index} | Column1: Value1 | Column2: Value2 | ...`
        Groups rows into structured chunks for vector storage while preserving relational context.
        """
        ext = os.path.splitext(filename)[1].lower()
        sections: List[Dict[str, Any]] = []

        if ext == ".csv":
            df = pd.read_csv(file_path)
            sheets_data = {"Sheet1": self._clean_dataframe(df)}
        else:
            excel_file = pd.ExcelFile(file_path, engine="openpyxl")
            sheets_data = {
                s_name: self._clean_dataframe(pd.read_excel(excel_file, sheet_name=s_name))
                for s_name in excel_file.sheet_names
            }

        sheet_page = 1
        for sheet_name, df in sheets_data.items():
            if df.empty:
                continue

            columns = [str(c).strip() for c in df.columns]
            df_slice = df.head(max_rows_per_sheet)
            total_rows = len(df)

            # Generate row-wise Markdown strings with full column headers preserved
            row_markdown_lines: List[str] = []
            for r_idx, row in df_slice.iterrows():
                row_items = [
                    f"{col}: {row[col]}"
                    for col in columns
                    if pd.notna(row[col]) and str(row[col]).strip() not in ["", "nan", "None"]
                ]
                row_str = f"Row {r_idx + 1} | " + " | ".join(row_items)
                row_markdown_lines.append(row_str)

            # Group into chunks of ~20 rows per chunk so vector search retains accurate row context
            chunk_size_rows = 20
            for i in range(0, len(row_markdown_lines), chunk_size_rows):
                chunk_rows = row_markdown_lines[i : i + chunk_size_rows]
                header = (
                    f"### Spreadsheet: {filename} (Sheet: {sheet_name}, Total Rows: {total_rows})\n"
                    f"Columns: {', '.join(columns)}\n"
                    f"Displaying Rows {i + 1} to {min(i + len(chunk_rows), total_rows)}:\n"
                )
                chunk_text = header + "\n".join(chunk_rows)

                sections.append({
                    "page_or_slide": sheet_page,
                    "text": chunk_text,
                    "is_slide": False,
                    "is_tabular": True,
                    "sheet_name": sheet_name,
                    "row_range": f"{i + 1}-{min(i + len(chunk_rows), total_rows)}"
                })

            sheet_page += 1

        return sections

    def execute_aggregation(
        self,
        session_id: str,
        query: str,
        filename: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Executes Microsoft Copilot-style intelligent column aggregations directly
        on the underlying DataFrame without guessing via vector embeddings.
        Supports: sum, average/mean, count, min, max, with column and filter detection.
        Example queries:
        - 'What is the total expenditure for Ward 12?'
        - 'Find average yield for Rabi season'
        - 'Count of beneficiaries in Mandya district'
        """
        doc = self.get_document(session_id, filename)
        if not doc:
            return None

        df = doc.primary_df
        meta = doc.primary_meta
        if df.empty or not meta:
            return None

        q_lower = query.lower()

        # 1. Detect Aggregation Operation
        metric = None
        if any(w in q_lower for w in ["total", "sum", "overall", "aggregate", "combined"]):
            metric = "sum"
        elif any(w in q_lower for w in ["average", "avg", "mean"]):
            metric = "mean"
        elif any(w in q_lower for w in ["count", "how many", "number of", "total count", "total records"]):
            metric = "count"
        elif any(w in q_lower for w in ["minimum", "min", "lowest", "least", "smallest"]):
            metric = "min"
        elif any(w in q_lower for w in ["maximum", "max", "highest", "peak", "largest", "greatest", "most"]):
            metric = "max"

        if not metric:
            return None

        # 2. Detect Filter Conditions first (e.g., 'Ward 12', 'in Mandya', 'where status is Approved')
        filtered_df = df.copy()
        filter_criteria: List[Dict[str, str]] = []
        filtered_columns: set = set()

        # Check all columns for "ColName Value" patterns (e.g. "Ward 12", "District Mandya")
        for col in meta.columns:
            col_clean = col.lower().replace("_", " ").replace("-", " ")
            # Check pattern: "<col_clean>\s*(?:is|:|=)?\s*([a-zA-Z0-9_-]+)"
            match = re.search(r"\b" + re.escape(col_clean) + r"\s*(?:is|:|=)?\s*([a-zA-Z0-9_-]+)\b", q_lower)
            if match:
                candidate_val = match.group(1).strip()
                # Check if this candidate_val matches any value in the column
                matching_mask = filtered_df[col].astype(str).str.strip().str.lower() == candidate_val.lower()
                if matching_mask.any():
                    filtered_df = filtered_df[matching_mask]
                    filter_criteria.append({"column": col, "value": candidate_val})
                    filtered_columns.add(col)

        # Check distinct entity values in remaining non-filtered columns
        for col, unique_vals in meta.distinct_entities.items():
            if col in filtered_columns:
                continue
            for val in unique_vals:
                val_str = str(val).strip()
                if len(val_str) < 2:
                    continue
                pattern = r"\b" + re.escape(val_str.lower()) + r"\b"
                if re.search(pattern, q_lower):
                    filtered_df = filtered_df[
                        filtered_df[col].astype(str).str.strip().str.lower() == val_str.lower()
                    ]
                    filter_criteria.append({"column": col, "value": val_str})
                    filtered_columns.add(col)
                    break

        # 3. Identify Target Numeric Column (excluding any column already used as a filter!)
        candidate_num_cols = [c for c in meta.numeric_columns if c not in filtered_columns]

        # Categorical identifier blacklist for pure metrics (e.g. Ward, Year, ID shouldn't be summed unless explicitly requested)
        def is_identifier_col(col_name: str) -> bool:
            c_low = col_name.lower()
            return any(c_low == kw or c_low.endswith(f"_{kw}") or c_low.startswith(f"{kw}_") for kw in ["ward", "id", "code", "zip", "pin", "phone", "year", "no"])

        target_col = None

        # Check for direct phrase like "total expenditure", "sum of expenditure", "average yield"
        metric_words = ["total", "sum of", "sum", "average of", "average", "avg of", "avg", "mean of", "mean", "min of", "min", "max of", "max", "count of"]
        for m_word in metric_words:
            m_match = re.search(r"\b" + re.escape(m_word) + r"\s+([a-zA-Z0-9_-]+)", q_lower)
            if m_match:
                candidate_col_word = m_match.group(1).strip()
                for c in candidate_num_cols:
                    if candidate_col_word in c.lower().replace("_", " "):
                        target_col = c
                        break
            if target_col:
                break

        # If not found yet, check metric keyword matches in numeric columns
        if not target_col:
            # Score each candidate column
            best_score = -1
            for c in candidate_num_cols:
                c_low = c.lower().replace("_", " ")
                score = 0
                if c_low in q_lower:
                    score += 5
                for kw in NUMERIC_KEYWORDS:
                    if kw in c_low and kw in q_lower:
                        score += 8
                if is_identifier_col(c):
                    score -= 10
                if score > best_score and score > 0:
                    best_score = score
                    target_col = c

        # If metric is 'count' and no target column, default to first column or record count
        if metric == "count" and not target_col:
            target_col = meta.columns[0] if meta.columns else None

        if not target_col and candidate_num_cols and metric != "count":
            # Pick first non-identifier numeric column
            non_id_cols = [c for c in candidate_num_cols if not is_identifier_col(c)]
            if non_id_cols:
                target_col = non_id_cols[0]

        if not target_col and metric != "count":
            return None

        if filtered_df.empty:
            return {
                "status": "AGGREGATION_NO_MATCH",
                "metric": metric,
                "target_column": target_col,
                "filters": filter_criteria,
                "message": f"No records matched the filter criteria {filter_criteria} in sheet '{meta.sheet_name}'."
            }

        # 4. Perform Direct Numerical Calculation on Pandas Column
        try:
            if metric == "count":
                computed_value = int(len(filtered_df))
                formatted_value = f"{computed_value:,}"
            else:
                series = pd.to_numeric(
                    filtered_df[target_col].astype(str).str.replace(r"[$,₹\s]", "", regex=True),
                    errors="coerce"
                ).dropna()

                if series.empty:
                    return None

                if metric == "sum":
                    calc = float(series.sum())
                elif metric == "mean":
                    calc = float(series.mean())
                elif metric == "min":
                    calc = float(series.min())
                elif metric == "max":
                    calc = float(series.max())
                else:
                    calc = float(series.sum())

                computed_value = round(calc, 2)
                formatted_value = f"{computed_value:,.2f}"

            filter_desc = (
                " with filter: " + ", ".join([f"{f['column']} = '{f['value']}'" for f in filter_criteria])
                if filter_criteria else " across all records"
            )

            summary_statement = (
                f"Calculated {metric.upper()} of column '{target_col}': **{formatted_value}** "
                f"({len(filtered_df)} records evaluated{filter_desc})."
            )

            return {
                "status": "AGGREGATION_SUCCESS",
                "metric": metric,
                "target_column": target_col,
                "computed_value": computed_value,
                "formatted_value": formatted_value,
                "matching_rows_count": len(filtered_df),
                "total_rows_scanned": len(df),
                "filters_applied": filter_criteria,
                "summary": summary_statement,
                "sample_data": filtered_df.head(5).to_dict(orient="records"),
                "sheet_name": meta.sheet_name,
                "filename": doc.filename
            }
        except Exception as agg_err:
            logger.warning(f"Direct aggregation execution error: {agg_err}")
            return None

    def format_dataframe_as_markdown(self, df: pd.DataFrame, max_rows: int = 10) -> str:
        """
        Renders a clean GitHub-Flavored Markdown table with preserved headers.
        """
        if df.empty:
            return "*(No matching records)*"

        slice_df = df.head(max_rows).fillna("-")
        headers = [str(c).strip() for c in slice_df.columns]

        lines = [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |"
        ]
        for _, row in slice_df.iterrows():
            row_vals = [str(row[c]).replace("\n", " ").replace("|", "\\|") for c in headers]
            lines.append("| " + " | ".join(row_vals) + " |")

        return "\n".join(lines)

    def query_structured_table(
        self,
        session_id: str,
        query: str,
        filename: Optional[str] = None,
        similarity_threshold: int = 70,
        max_rows: int = 10
    ) -> Optional[Dict[str, Any]]:
        """
        High-Precision Entity & Structured Column Router:
        - Matches requested columns and entity values via rapidfuzz token-sort similarity.
        - Filters dataframe rows using matched structured filters.
        - Injects matched rows as clean Markdown tables with preserved headers.
        """
        doc = self.get_document(session_id, filename)
        if not doc or doc.primary_df.empty or not doc.primary_meta:
            return None

        df = doc.primary_df
        meta = doc.primary_meta
        q_lower = query.lower().strip()

        try:
            from rapidfuzz import fuzz, process
            use_rapidfuzz = True
        except ImportError:
            use_rapidfuzz = False

        matched_filters = []
        filtered_df = df.copy()

        # 1. Match columns via token_sort_ratio
        matched_columns = []
        for col in meta.columns:
            col_name = str(col).strip()
            if use_rapidfuzz:
                ratio = fuzz.partial_token_sort_ratio(col_name.lower(), q_lower)
            else:
                ratio = 100 if col_name.lower() in q_lower else 0

            if ratio >= similarity_threshold or col_name.lower() in q_lower:
                matched_columns.append(col)

        # 2. Match entities in entity columns via token_sort similarity
        entity_cols = meta.primary_text_columns or meta.columns
        for col in entity_cols:
            choices = df[col].dropna().astype(str).unique().tolist()
            if not choices:
                continue

            if use_rapidfuzz:
                candidates = process.extract(
                    query,
                    choices,
                    scorer=fuzz.token_sort_ratio,
                    limit=3
                )
                top_hits = [c for c in candidates if c[1] >= similarity_threshold]
            else:
                import difflib
                raw_hits = difflib.get_close_matches(query, choices, n=3, cutoff=similarity_threshold / 100.0)
                top_hits = [(h, 80) for h in raw_hits]

            if top_hits:
                best_match_val = top_hits[0][0]
                mask = filtered_df[col].astype(str).str.strip().str.lower() == str(best_match_val).strip().lower()
                if mask.any():
                    filtered_df = filtered_df[mask]
                    matched_filters.append({"column": col, "value": best_match_val, "score": top_hits[0][1]})

        if not matched_filters and filtered_df.equals(df):
            words = [w for w in re.findall(r"\w+", q_lower) if len(w) > 3]
            for w in words:
                for col in entity_cols:
                    mask = filtered_df[col].astype(str).str.lower().str.contains(re.escape(w), na=False)
                    if mask.any() and mask.sum() < len(filtered_df):
                        filtered_df = filtered_df[mask]
                        matched_filters.append({"column": col, "value": w, "score": 75})
                        break

        # Generate clean Markdown table with preserved headers
        table_markdown = self.format_dataframe_as_markdown(filtered_df, max_rows=max_rows)

        return {
            "status": "MATCHED" if matched_filters else "ALL_ROWS",
            "filename": doc.filename,
            "sheet_name": meta.sheet_name,
            "total_rows": len(df),
            "matched_rows_count": len(filtered_df),
            "matched_filters": matched_filters,
            "table_markdown": table_markdown,
            "columns": meta.columns
        }


# Global singleton instance
tabular_registry = TabularRegistry()
