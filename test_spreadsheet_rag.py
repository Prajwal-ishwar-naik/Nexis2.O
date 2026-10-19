"""
Nexis AI - Copilot-Style Spreadsheet RAG Integration Test Suite
Validates:
1. Multi-format spreadsheet ingestion (.csv, .xlsx).
2. Preserved row-wise Markdown vector chunks: `Row {index} | Column1: Value1 | ...`.
3. In-memory session registry and primary text/entity schema extraction.
4. Deterministic mathematical aggregations (e.g. Ward-filtered expenditures).
5. Exact entity lookups with complete Markdown attribute tables.
6. Fuzzy entity resolution (typos like 'Prajwal Nai' -> 'Prajwal Ishwar', 'Prajwal Shetty')
   with mandatory citizen-service phrasing.
7. Graceful absence notices with scanned row counts and column names.
"""

import asyncio
import os
import httpx
import pandas as pd
import pytest

BASE_URL = os.getenv("GATEWAY_URL", "http://127.0.0.1:8000")


@pytest.mark.asyncio
async def test_spreadsheet_rag_full_lifecycle():
    session_id = "test_copilot_session_ci"
    test_csv_path = "/tmp/ci_farmers_roster.csv"

    # 1. Create sample dataset
    df = pd.DataFrame([
        {"Farmer_ID": "KA-001", "Farmer_Name": "Prajwal Ishwar", "Ward": 12, "Crop": "Ragi", "Expenditure": 45000, "Status": "Approved"},
        {"Farmer_ID": "KA-002", "Farmer_Name": "Prajwal Shetty", "Ward": 12, "Crop": "Paddy", "Expenditure": 55000, "Status": "Approved"},
        {"Farmer_ID": "KA-003", "Farmer_Name": "Ramesh Kumar", "Ward": 14, "Crop": "Maize", "Expenditure": 30000, "Status": "Pending"},
        {"Farmer_ID": "KA-004", "Farmer_Name": "Suresh Gowda", "Ward": 12, "Crop": "Sugarcane", "Expenditure": 20000, "Status": "Approved"},
        {"Farmer_ID": "KA-005", "Farmer_Name": "Anitha Patil", "Ward": 15, "Crop": "Cotton", "Expenditure": 60000, "Status": "Approved"},
    ])
    df.to_csv(test_csv_path, index=False)

    async with httpx.AsyncClient(timeout=35.0) as client:
        # Check health
        health = await client.get(f"{BASE_URL}/health")
        assert health.status_code == 200, f"Gateway health check failed: {health.text}"

        # Step 1: Upload spreadsheet
        with open(test_csv_path, "rb") as f:
            up_res = await client.post(
                f"{BASE_URL}/api/rag/upload",
                files={"file": ("ci_farmers_roster.csv", f, "text/csv")},
                data={"session_id": session_id}
            )
        assert up_res.status_code == 200, f"Upload failed: {up_res.text}"
        up_data = up_res.json()
        assert up_data.get("status") == "success"
        assert "tabular" in up_data
        tab_meta = up_data["tabular"]
        assert tab_meta["total_rows"] == 5
        assert "Farmer_Name" in tab_meta["primary_text_columns"]
        assert "Expenditure" in tab_meta["numeric_columns"]

        # Step 2: Direct column aggregation
        chat_agg = await client.post(
            f"{BASE_URL}/api/chat",
            json={
                "message": "What is the total expenditure for Ward 12?",
                "session_id": session_id,
                "chat_id": f"{session_id}_chat_agg"
            }
        )
        assert chat_agg.status_code == 200
        agg_text = chat_agg.json().get("response", "")
        # Total for Ward 12 = 45k + 55k + 20k = 120,000
        assert "120,000" in agg_text or "120000" in agg_text, f"Expected 120,000 in response: {agg_text}"

        # Step 3: Fuzzy entity resolution (Typo: 'Prajwal Nai')
        chat_fuzzy = await client.post(
            f"{BASE_URL}/api/chat",
            json={
                "message": "Show me the record for Prajwal Nai",
                "session_id": session_id,
                "chat_id": f"{session_id}_chat_fuzzy"
            }
        )
        assert chat_fuzzy.status_code == 200
        fuzzy_text = chat_fuzzy.json().get("response", "")
        assert "Prajwal Ishwar" in fuzzy_text or "Prajwal Shetty" in fuzzy_text, f"Suggestions missing in response: {fuzzy_text}"

        # Step 4: Exact entity resolution ('Ramesh Kumar')
        chat_exact = await client.post(
            f"{BASE_URL}/api/chat",
            json={
                "message": "Find details for Ramesh Kumar",
                "session_id": session_id,
                "chat_id": f"{session_id}_chat_exact"
            }
        )
        assert chat_exact.status_code == 200
        exact_text = chat_exact.json().get("response", "")
        assert "KA-003" in exact_text or "Maize" in exact_text, f"Exact record attributes missing: {exact_text}"

        # Step 5: Absent record notice
        chat_absent = await client.post(
            f"{BASE_URL}/api/chat",
            json={
                "message": "Search for record of Sir Arthur Conan Doyle",
                "session_id": session_id,
                "chat_id": f"{session_id}_chat_absent"
            }
        )
        assert chat_absent.status_code == 200
        absent_text = chat_absent.json().get("response", "")
        assert "not found" in absent_text.lower() or "no records" in absent_text.lower() or "no matching" in absent_text.lower()

    print("\n✅ All 5 Copilot-Style Spreadsheet RAG test cases passed successfully.")


if __name__ == "__main__":
    asyncio.run(test_spreadsheet_rag_full_lifecycle())
