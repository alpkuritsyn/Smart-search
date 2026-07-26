#!/usr/bin/env python3
"""
Deterministic Search Engine for Smart-search V1.
Implements hard-filtered primary retrieval, legacy fallback, complement traversal, and response formatting.
"""
import os
import sys
import json
import time
import copy
import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "baseline"))

from src.normalization.query_parser import parse_query
from src.ml.embedding_resolver import EmbeddingEntityResolver
from src.graph.traversal import get_complements_for_type
import baseline.server as legacy_server

CANONICAL_CATALOG_PATH = BASE_DIR / "data" / "canonical" / "catalog.canonical.json"
PRODUCTION_ENTITY_INDEX_PATH = BASE_DIR / "data" / "embeddings" / "entities.sqlite"
CURRENT_ENTITY_INDEX_PATH = BASE_DIR / "data" / "embeddings" / "entities.current-canonical.sqlite"

_CANONICAL_CATALOG_CACHE = None
_ENTITY_RESOLVER_CACHE = {}
_ENTITY_RESOLVER_LOCK = threading.Lock()


# Automatically load .env file if available
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    with open(_env_file, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _k, _v = _k.strip(), _v.strip()
                os.environ[_k] = _v

def entity_resolver_mode(explicit_mode=None):
    mode = (explicit_mode or os.environ.get("SMART_SEARCH_ENTITY_RESOLVER_MODE", "apply")).strip().lower()
    return mode if mode in {"off", "shadow", "apply"} else "apply"


def entity_resolver_policy(explicit_policy=None):
    policy = (explicit_policy or os.environ.get("SMART_SEARCH_ENTITY_RESOLVER_POLICY", "top1")).strip().lower()
    return policy if policy in {"strict", "top1"} else "top1"


def entity_index_path():
    configured = os.environ.get("SMART_SEARCH_ENTITY_INDEX")
    if configured:
        return Path(configured).expanduser().resolve()
    if PRODUCTION_ENTITY_INDEX_PATH.exists():
        return PRODUCTION_ENTITY_INDEX_PATH
    return CURRENT_ENTITY_INDEX_PATH


def get_entity_resolver():
    index_path = entity_index_path()
    cache_key = str(index_path)
    with _ENTITY_RESOLVER_LOCK:
        resolver = _ENTITY_RESOLVER_CACHE.get(cache_key)
        if resolver is None:
            resolver = EmbeddingEntityResolver(index_path=index_path)
            _ENTITY_RESOLVER_CACHE[cache_key] = resolver
        return resolver


def get_entity_resolver_health():
    mode = entity_resolver_mode()
    index_path = entity_index_path()
    return {
        "mode": mode,
        "policy": entity_resolver_policy(),
        "status": "off" if mode == "off" else ("ready" if index_path.exists() else "degraded"),
        "index_path": str(index_path),
        "index_exists": index_path.exists(),
        "model": "qwen3-embedding:0.6b",
    }


def apply_entity_resolution(parsed, resolver=None, mode=None, policy=None, catalog=None):
    """Route unresolved spans to brand, product type, or a concrete product."""
    active_mode = entity_resolver_mode(mode)
    active_policy = entity_resolver_policy(policy)
    parsed.setdefault("product_id", None)
    parsed.setdefault("product_display", None)
    parsed.setdefault("entity_resolutions", [])
    if active_mode == "off" or (parsed.get("brand_id") and parsed.get("product_type_id")):
        return parsed

    candidates = [
        token
        for token in parsed.get("unparsed_tokens", [])
        if len(token) >= 3 and any(character.isalpha() for character in token)
    ]
    if not candidates:
        return parsed

    try:
        active_resolver = resolver or get_entity_resolver()
    except Exception as exc:
        parsed["entity_resolution"] = {
            "status": "unavailable",
            "entity_type": "brand",
            "matched_text": " ".join(candidates),
            "entity_id": None,
            "display": None,
            "score": None,
            "margin": None,
            "reason": f"resolver_init_error:{type(exc).__name__}",
            "candidates": [],
            "model": None,
            "index_version": None,
        }
        return parsed

    catalog = catalog or []
    products_by_id = {str(product.get("id")): product for product in catalog}

    def candidate_is_available(entity_type, entity_id):
        if not catalog:
            return True
        if entity_type == "brand":
            if parsed.get("product_id") is not None:
                product = products_by_id.get(str(parsed["product_id"]))
                return bool(product and product.get("brand_id") == entity_id)
            return any(
                product.get("brand_id") == entity_id
                and (not parsed.get("product_type_id") or product.get("product_type_id") == parsed["product_type_id"])
                for product in catalog
            )
        if entity_type == "product_type":
            return any(
                product.get("product_type_id") == entity_id
                and (not parsed.get("brand_id") or product.get("brand_id") == parsed["brand_id"])
                for product in catalog
            )
        if entity_type == "product_name":
            product = products_by_id.get(str(entity_id))
            return bool(
                product
                and (not parsed.get("brand_id") or product.get("brand_id") == parsed["brand_id"])
                and (
                    not parsed.get("product_type_id")
                    or product.get("product_type_id") == parsed["product_type_id"]
                )
            )
        return False

    def materialize(result, entity_type):
        if result.get("status") in {"exact", "resolved"} and result.get("entity_id"):
            if candidate_is_available(entity_type, result["entity_id"]):
                return dict(result)
            return None
        ranked = result.get("candidates") or []
        candidate = next(
            (
                item
                for item in ranked
                if item.get("entity_id")
                and candidate_is_available(entity_type, item["entity_id"])
                and (item.get("score") or 0.0) >= (0.80 if entity_type == "brand" else 0.65)
                and (
                    item.get("character_score") is None
                    or item.get("character_score") >= (0.50 if entity_type in {"product_type", "brand"} else 0.40)
                    or (item.get("score") or 0.0) >= 0.75
                )
            ),
            None,
        )
        if candidate is None:
            return None
        original_status = result.get("status")
        materialized = dict(result)
        materialized.update({
            "status": "best_effort",
            "entity_id": candidate.get("entity_id"),
            "display": candidate.get("display"),
            "score": candidate.get("score"),
            "reason": f"top1_available_catalog_candidate_from_{original_status}",
            "original_status": original_status,
        })
        return materialized

    def apply_result(result, token):
        entity_type = result.get("entity_type")
        entity_id = result.get("entity_id")
        if entity_type == "brand":
            parsed["brand_id"] = entity_id
            parsed["brand_display"] = result.get("display")
        elif entity_type == "product_type":
            parsed["product_type_id"] = entity_id
            parsed["product_type_display"] = result.get("display")
        elif entity_type == "product_name":
            product = products_by_id.get(str(entity_id))
            if not product:
                return False
            parsed["product_id"] = product.get("id")
            parsed["product_display"] = product.get("name") or result.get("display")
            if product.get("brand_id") and not parsed.get("brand_id"):
                parsed["brand_id"] = product["brand_id"]
                parsed["brand_display"] = product.get("brand")
            if product.get("product_type_id") and not parsed.get("product_type_id"):
                parsed["product_type_id"] = product["product_type_id"]
                parsed["product_type_display"] = product.get("subcategory") or result.get("display")
        else:
            return False
        consumed_tokens = set(token.split())
        parsed["unparsed_tokens"] = [
            item for item in parsed.get("unparsed_tokens", []) if item not in consumed_tokens
        ]
        parsed["entity_resolutions"].append(result)
        parsed["entity_resolution"] = result
        return True

    best_nonresolved = None
    # A longer residual phrase is much more likely to be a concrete catalog
    # title than a brand or a generic product type. Resolve it before tokens so
    # queries such as "масло валти терас ойл" can select the actual SKU.
    if (
        active_mode == "apply"
        and not parsed.get("brand_id")
        and not parsed.get("product_type_id")
        and len(candidates) >= 3
    ):
        phrase = " ".join(candidates)
        phrase_result = active_resolver.resolve(phrase, "product_name")
        best_nonresolved = phrase_result
        ready_phrase = materialize(phrase_result, "product_name")
        if ready_phrase is not None and apply_result(ready_phrase, phrase):
            return parsed

    STOP_WORDS = {"для", "и", "в", "на", "с", "из", "под", "от", "по", "за", "со", "без"}
    valid_candidates = [t for t in candidates if len(t) >= 3 and t not in STOP_WORDS]
    for token in valid_candidates:
        options = []
        result_types = []
        if not parsed.get("brand_id"):
            result_types.append("brand")
        if not parsed.get("product_type_id") and not parsed.get("product_id"):
            result_types.extend(("product_type", "product_name"))

        for entity_type in result_types:
            result = active_resolver.resolve(token, entity_type)
            score = result.get("score")
            best_score = best_nonresolved.get("score") if best_nonresolved else None
            if best_nonresolved is None or (score is not None and (best_score is None or score > best_score)):
                best_nonresolved = result
            ready = materialize(result, entity_type)
            if ready is not None:
                options.append(ready)
            # A high-confidence taxonomy hit is enough for this one span. This
            # avoids turning a clear brand/type into a random concrete SKU.
            if result.get("status") in {"exact", "resolved"} and ready is not None:
                break

        if options:
            status_rank = {"exact": 3, "resolved": 2, "best_effort": 1}
            selected = max(
                options,
                key=lambda item: (status_rank.get(item.get("status"), 0), item.get("score") or 0.0),
            )
            if active_mode == "apply":
                apply_result(selected, token)
            else:
                parsed["entity_resolutions"].append(selected)
                parsed["entity_resolution"] = selected

        if parsed.get("brand_id") and (parsed.get("product_type_id") or parsed.get("product_id")):
            break

    if not parsed.get("entity_resolutions") and best_nonresolved is not None:
        parsed["entity_resolution"] = best_nonresolved
        parsed["entity_resolutions"] = [best_nonresolved]
    return parsed


def apply_brand_entity_resolution(parsed, resolver=None, mode=None, policy=None, catalog=None):
    """Backward-compatible entry point for callers created before V1.2."""
    return apply_entity_resolution(parsed, resolver, mode, policy, catalog)

def load_canonical_catalog(force_reload: bool = False):
    global _CANONICAL_CATALOG_CACHE
    if _CANONICAL_CATALOG_CACHE is not None and not force_reload:
        return _CANONICAL_CATALOG_CACHE
    if CANONICAL_CATALOG_PATH.exists():
        with open(CANONICAL_CATALOG_PATH, "r", encoding="utf-8") as f:
            _CANONICAL_CATALOG_CACHE = json.load(f)
            legacy_server.CATALOG_DATABASE = _CANONICAL_CATALOG_CACHE
            return _CANONICAL_CATALOG_CACHE
    return []

_SEARCH_RESULT_CACHE = {}

def search_catalog_v1(
    query_str: str,
    top_k: int = 25,
    use_legacy_force: bool = False,
    entity_resolver=None,
    resolver_mode=None,
    resolver_policy=None,
) -> dict:
    start_time = time.time()
    cache_key = (
        (query_str or "").strip().lower(),
        use_legacy_force,
        entity_resolver_mode(resolver_mode),
        entity_resolver_policy(resolver_policy),
        top_k,
    )
    if cache_key in _SEARCH_RESULT_CACHE:
        cached_res = copy.deepcopy(_SEARCH_RESULT_CACHE[cache_key])
        cached_res["meta"]["elapsed_ms"] = max(0, int((time.time() - start_time) * 1000))
        cached_res["meta"]["cached"] = True
        return cached_res

    catalog = load_canonical_catalog()

    if use_legacy_force:
        parsed_info = {
            "raw": query_str or "",
            "normalized": (query_str or "").lower(),
            "brand_id": None,
            "brand_display": None,
            "product_type_id": None,
            "product_type_display": None,
            "attributes": {},
            "unparsed_tokens": []
        }
        legacy_items = legacy_server.retrieve_relevant_products(query_str, top_k=top_k)
        elapsed_ms = int((time.time() - start_time) * 1000)
        return {
            "query": parsed_info,
            "primary": {
                "title": "Результаты поиска (Legacy Fallback)",
                "products": [legacy_server.serialize_product(p) for p in legacy_items]
            },
            "complements": [],
            "meta": {
                "strategy": "legacy_fallback",
                "fallback_used": True,
                "catalog_version": "canonical-v1",
                "aliases_version": "aliases-v1",
                "graph_version": "complement-graph-v1-approved",
                "elapsed_ms": elapsed_ms
            }
        }

    parsed = parse_query(query_str)
    parsed = apply_entity_resolution(
        parsed,
        resolver=entity_resolver,
        mode=resolver_mode,
        policy=resolver_policy,
        catalog=catalog,
    )
    brand_id = parsed.get("brand_id")
    product_type_id = parsed.get("product_type_id")
    attributes = parsed.get("attributes", {})
    product_id = parsed.get("product_id")

    fallback_used = False
    strategy = "deterministic_v1"

    # Strict hard filter evaluation
    if brand_id or product_type_id or product_id is not None:
        matched_products = []

        for p in catalog:
            if product_id is not None and str(p.get("id")) != str(product_id):
                continue
            if brand_id and p.get("brand_id") != brand_id:
                continue
            if product_type_id and p.get("product_type_id") != product_type_id:
                continue

            # Hard weight/volume filtering
            item_attrs = p.get("attributes", {})
            if "weight_kg" in attributes:
                item_weight = item_attrs.get("weight_kg")
                if item_weight is not None and item_weight != attributes["weight_kg"]:
                    continue
            if "volume_l" in attributes:
                item_volume = item_attrs.get("volume_l")
                if item_volume is not None and item_volume != attributes["volume_l"]:
                    continue

            matched_products.append(p)

        # If weight/volume specified, filter down to exact attribute matches if present
        if "weight_kg" in attributes:
            target_w = attributes["weight_kg"]
            exact_weight_matches = [p for p in matched_products if p.get("attributes", {}).get("weight_kg") == target_w]
            if exact_weight_matches:
                matched_products = exact_weight_matches

        if "volume_l" in attributes:
            target_v = attributes["volume_l"]
            exact_volume_matches = [p for p in matched_products if p.get("attributes", {}).get("volume_l") == target_v]
            if exact_volume_matches:
                matched_products = exact_volume_matches

        # Characteristic attribute scoring & sorting (surface, moisture, finish, properties, color)
        char_attributes = {k: v for k, v in attributes.items() if k not in ("weight_kg", "volume_l")}
        attribute_relaxed = False

        if matched_products:
            def rank_product(item):
                score = 100 if product_id is not None and str(item.get("id")) == str(product_id) else 0
                item_attrs = item.get("attributes", {})
                name_low = (item.get("name") or "").lower()

                # Characteristic attribute match
                for k, target_val in char_attributes.items():
                    if item_attrs.get(k) == target_val:
                        score += 50
                    elif target_val in name_low or (k == "surface" and target_val == "строганый" and ("строг" in name_low or "строган" in name_low)):
                        score += 30

                # Lexical unparsed token match
                unparsed = parsed.get("unparsed_tokens", [])
                for tok in unparsed:
                    if tok in name_low:
                        score += 5

                return score

            matched_products.sort(key=rank_product, reverse=True)

            if char_attributes:
                top_char_score = max((rank_product(p) for p in matched_products), default=0)
                if top_char_score < 30:
                    attribute_relaxed = True

        primary_products = matched_products[:top_k]

        title_parts = []
        if parsed.get("product_type_display"):
            pt_disp = parsed["product_type_display"].capitalize()
            if pt_disp.endswith("ок") or pt_disp.endswith("ик"):
                plural_pt = pt_disp[:-2] + "ки"
            elif pt_disp.endswith("к"):
                plural_pt = pt_disp + "и"
            elif pt_disp.endswith("а") or pt_disp.endswith("ь"):
                plural_pt = pt_disp[:-1] + "и"
            else:
                plural_pt = pt_disp + "ы"
            title_parts.append("Найденные " + plural_pt.lower())
        else:
            title_parts.append("Найденные товары")

        if parsed.get("brand_display"):
            title_parts.append(parsed["brand_display"])

        primary_title = f"{' '.join(title_parts)}"

    else:
        fallback_used = True
        strategy = "legacy_fallback"
        legacy_items = legacy_server.retrieve_relevant_products(query_str, top_k=top_k)
        primary_products = legacy_items
        primary_title = "Результаты поиска (Fallback)"

    complements = []
    if product_type_id:
        raw_complements = get_complements_for_type(product_type_id, canonical_catalog=catalog)
        for comp in raw_complements:
            serialized_comp_products = [legacy_server.serialize_product(p) for p in comp.get("products", [])]
            complements.append({
                "title": comp["title"],
                "relation": comp["relation"],
                "rationale": comp["rationale"],
                "data_gap": comp.get("data_gap", False),
                "data_gap_message": comp.get("data_gap_message"),
                "products": serialized_comp_products
            })

    elapsed_ms = int((time.time() - start_time) * 1000)

    resolutions = parsed.get("entity_resolutions") or []
    resolution = parsed.get("entity_resolution")
    res = {
        "query": parsed,
        "primary": {
            "title": primary_title,
            "products": [legacy_server.serialize_product(p) for p in primary_products]
        },
        "complements": complements,
        "meta": {
            "strategy": strategy,
            "fallback_used": fallback_used,
            "attribute_relaxed": attribute_relaxed if 'attribute_relaxed' in locals() else False,
            "catalog_version": "canonical-v1",
            "aliases_version": "aliases-v1",
            "graph_version": "complement-graph-v1-approved",
            "entity_resolver_mode": entity_resolver_mode(resolver_mode),
            "entity_resolver_policy": entity_resolver_policy(resolver_policy),
            "entity_resolver_status": (
                "+".join(item.get("status", "unknown") for item in resolutions)
                if resolutions else (resolution.get("status") if resolution else "not_needed")
            ),
            "entity_resolver_model": resolution.get("model") if resolution else None,
            "entity_resolver_index_version": resolution.get("index_version") if resolution else None,
            "elapsed_ms": elapsed_ms,
            "cached": False,
        }
    }
    if len(_SEARCH_RESULT_CACHE) > 4096:
        _SEARCH_RESULT_CACHE.clear()
    _SEARCH_RESULT_CACHE[cache_key] = copy.deepcopy(res)
    return res

if __name__ == "__main__":
    res = search_catalog_v1("краска тикурила")
    print(json.dumps(res, ensure_ascii=False, indent=2))
