import os
import sys
import json
from pathlib import Path
import pytest

os.environ["GEMINI_API_KEY"] = "mock_key_for_offline_retrieval"

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "baseline"))

import baseline.server as legacy_server

# Load catalog snapshot into baseline server CATALOG_DATABASE
catalog_path = BASE_DIR / "data" / "source" / "catalog.snapshot.json"
with open(catalog_path, "r", encoding="utf-8") as f:
    legacy_server.CATALOG_DATABASE = json.load(f)

def test_legacy_fallback_returns_results_for_complex_query():
    query = "краска тикурила"
    results = legacy_server.retrieve_relevant_products(query, top_k=5)
    assert len(results) > 0
    for item in results:
        assert "id" in item
        assert "name" in item

def test_legacy_fallback_empty_query():
    assert legacy_server.retrieve_relevant_products("") == []
    assert legacy_server.retrieve_relevant_products(None) == []
