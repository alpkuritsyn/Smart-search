import os
import sys
from pathlib import Path
import pytest

os.environ["GEMINI_API_KEY"] = "mock_key_for_offline_retrieval"

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "baseline"))

from src.search.engine import apply_brand_entity_resolution, search_catalog_v1


class StubBrandResolver:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def resolve(self, text, entity_type):
        self.calls.append((text, entity_type))
        return dict(self.result, matched_text=text, entity_type=entity_type)


class StubRoutingResolver:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def resolve(self, text, entity_type):
        self.calls.append((text, entity_type))
        result = self.results[(text, entity_type)]
        return dict(result, matched_text=text, entity_type=entity_type)


def resolved_tikkurila():
    return {
        "status": "resolved",
        "entity_id": "brand:tikkurila",
        "display": "Tikkurila",
        "score": 0.895547,
        "margin": 0.287263,
        "reason": "score_and_margin_passed",
        "candidates": [],
        "model": "qwen3-embedding:0.6b",
        "index_version": "embedding-resolver-v1.1",
    }


def resolved_putty():
    return {
        "status": "resolved",
        "entity_id": "type:putty",
        "display": "шпаклёвка",
        "score": 0.91,
        "margin": 0.18,
        "reason": "score_and_margin_passed",
        "candidates": [],
        "model": "qwen3-embedding:0.6b",
        "index_version": "embedding-resolver-v1.2",
    }


def unresolved(entity_id, display, score):
    return {
        "status": "suggestion",
        "entity_id": None,
        "display": None,
        "score": score,
        "margin": 0.01,
        "reason": "auto_resolution_gate_not_passed",
        "candidates": [{
            "entity_id": entity_id,
            "display": display,
            "score": score,
            "embedding_score": score,
            "character_score": score,
            "transliteration_score": score,
        }],
        "model": "qwen3-embedding:0.6b",
        "index_version": "embedding-resolver-v1.2",
    }

def test_paint_tikkurila_primary_and_complements():
    res = search_catalog_v1("краска тикурила")
    assert res["query"]["brand_id"] == "brand:tikkurila"
    assert res["query"]["product_type_id"] == "type:paint"
    assert res["meta"]["fallback_used"] == False
    assert len(res["primary"]["products"]) > 0
    for p in res["primary"]["products"]:
        assert "ТИККУРИЛА" in p["brand"].upper() or "TIKKURILA" in p["brand"].upper()

    assert len(res["complements"]) > 0
    rel_types = [c["relation"] for c in res["complements"]]
    assert "PREPARE_WITH" in rel_types
    assert "LEVEL_WITH" in rel_types
    assert "APPLY_WITH" in rel_types

def test_paint_tikkurila_latin_parity():
    res_cyr = search_catalog_v1("краска тикурила")
    res_lat = search_catalog_v1("краска tikkurila")
    assert res_cyr["query"]["brand_id"] == res_lat["query"]["brand_id"]
    assert res_cyr["query"]["product_type_id"] == res_lat["query"]["product_type_id"]

def test_primer_dulux_honest_empty_primary():
    res = search_catalog_v1("грунтовка dulux")
    assert res["query"]["brand_id"] == "brand:dulux"
    assert res["query"]["product_type_id"] == "type:primer"
    # Dulux has 0 primers in catalog -> honest empty state for primary
    assert len(res["primary"]["products"]) == 0
    # But complements (putties, tools) are suggested
    assert len(res["complements"]) > 0

def test_wood_varnish():
    res = search_catalog_v1("лак для дерева")
    assert res["query"]["product_type_id"] == "type:varnish"
    assert len(res["primary"]["products"]) > 0

def test_putty_20kg_hard_filter():
    res = search_catalog_v1("шпаклевка 20 кг")
    assert res["query"]["product_type_id"] == "type:putty"
    assert res["query"]["attributes"].get("weight_kg") == 20
    assert len(res["primary"]["products"]) > 0
    for p in res["primary"]["products"]:
        assert "20" in p["name"]

def test_unrecognized_query_legacy_fallback():
    res = search_catalog_v1("какая-то неизвестная белиберда 12345")
    assert res["meta"]["fallback_used"] == True
    assert res["meta"]["strategy"] == "legacy_fallback"


def test_embedding_brand_resolution_becomes_hard_filter_in_apply_mode():
    resolver = StubBrandResolver(resolved_tikkurila())
    res = search_catalog_v1("Тикула", entity_resolver=resolver, resolver_mode="apply")
    assert resolver.calls == [("тикула", "brand")]
    assert res["query"]["brand_id"] == "brand:tikkurila"
    assert res["query"]["entity_resolution"]["status"] == "resolved"
    assert res["meta"]["fallback_used"] is False
    assert len(res["primary"]["products"]) > 0
    assert all("ТИККУРИЛА" in item["brand"].upper() or "TIKKURILA" in item["brand"].upper() for item in res["primary"]["products"])


def test_embedding_routes_shpaklya_to_product_type_not_brand():
    resolver = StubRoutingResolver({
        ("шпакля", "brand"): unresolved("brand:parade", "Parade", 0.55),
        ("шпакля", "product_type"): resolved_putty(),
    })
    res = search_catalog_v1("шпакля", entity_resolver=resolver, resolver_mode="apply", resolver_policy="top1")
    assert resolver.calls == [("шпакля", "brand"), ("шпакля", "product_type")]
    assert res["query"]["brand_id"] is None
    assert res["query"]["product_type_id"] == "type:putty"
    assert res["query"]["product_type_display"] == "шпаклёвка"
    assert res["query"]["entity_resolution"]["entity_type"] == "product_type"
    assert res["meta"]["fallback_used"] is False
    assert res["primary"]["products"]


def test_distinct_spans_can_resolve_brand_and_product_type():
    resolver = StubRoutingResolver({
        ("тикула", "brand"): resolved_tikkurila(),
        ("шпакля", "product_type"): resolved_putty(),
    })
    parsed = {
        "brand_id": None,
        "brand_display": None,
        "product_type_id": None,
        "product_type_display": None,
        "unparsed_tokens": ["тикула", "шпакля"],
    }
    result = apply_brand_entity_resolution(
        parsed,
        resolver=resolver,
        mode="apply",
        policy="top1",
        catalog=[{"id": 1, "brand_id": "brand:tikkurila", "product_type_id": "type:putty"}],
    )
    assert result["brand_id"] == "brand:tikkurila"
    assert result["product_type_id"] == "type:putty"
    assert [item["entity_type"] for item in result["entity_resolutions"]] == ["brand", "product_type"]


def test_exact_alias_bypasses_embedding_resolver():
    resolver = StubBrandResolver(resolved_tikkurila())
    res = search_catalog_v1("краска тикурила", entity_resolver=resolver, resolver_mode="apply")
    assert resolver.calls == []
    assert res["query"]["brand_id"] == "brand:tikkurila"


def test_suggestion_never_becomes_hard_filter():
    suggestion = resolved_tikkurila()
    suggestion.update({"status": "suggestion", "entity_id": None, "display": None, "score": 0.68, "margin": 0.01})
    resolver = StubBrandResolver(suggestion)
    res = search_catalog_v1("тикк", entity_resolver=resolver, resolver_mode="apply")
    assert res["query"]["brand_id"] is None
    assert res["query"]["entity_resolution"]["status"] == "suggestion"
    assert res["meta"]["fallback_used"] is True


def test_top1_policy_applies_best_candidate_when_strict_gate_rejects():
    suggestion = resolved_tikkurila()
    suggestion.update({
        "status": "suggestion",
        "entity_id": None,
        "display": None,
        "score": 0.68,
        "margin": 0.01,
        "candidates": [{
            "entity_id": "brand:tikkurila",
            "display": "Tikkurila",
            "score": 0.68,
            "embedding_score": 0.72,
            "character_score": 0.55,
            "transliteration_score": 0.55,
        }],
    })
    resolver = StubBrandResolver(suggestion)
    res = search_catalog_v1(
        "тикк",
        entity_resolver=resolver,
        resolver_mode="apply",
        resolver_policy="top1",
    )
    assert res["query"]["brand_id"] == "brand:tikkurila"
    assert res["query"]["entity_resolution"]["status"] == "best_effort"
    assert res["query"]["entity_resolution"]["original_status"] == "suggestion"
    assert res["meta"]["fallback_used"] is False
    assert len(res["primary"]["products"]) > 0


def test_top1_policy_skips_candidate_without_catalog_products():
    suggestion = resolved_tikkurila()
    suggestion.update({
        "status": "suggestion",
        "entity_id": None,
        "display": None,
        "score": 0.70,
        "margin": 0.01,
        "candidates": [
            {
                "entity_id": "brand:empty",
                "display": "Empty Brand",
                "score": 0.70,
                "embedding_score": 0.75,
                "character_score": 0.50,
                "transliteration_score": 0.50,
            },
            {
                "entity_id": "brand:tikkurila",
                "display": "Tikkurila",
                "score": 0.66,
                "embedding_score": 0.70,
                "character_score": 0.48,
                "transliteration_score": 0.48,
            },
        ],
    })
    parsed = {
        "brand_id": None,
        "brand_display": None,
        "product_type_id": "type:paint",
        "unparsed_tokens": ["тикк"],
    }
    result = apply_brand_entity_resolution(
        parsed,
        resolver=StubBrandResolver(suggestion),
        mode="apply",
        policy="top1",
        catalog=[{"brand_id": "brand:tikkurila", "product_type_id": "type:paint"}],
    )
    assert result["brand_id"] == "brand:tikkurila"
    assert result["entity_resolution"]["display"] == "Tikkurila"
    assert result["entity_resolution"]["score"] == 0.66
