#!/usr/bin/env python3
"""
Canonical Catalog Builder for Smart-search V1.
Merges source catalog snapshot with staging records and assigns canonical IDs and attributes.
"""
import json
import re
import hashlib
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SOURCE_CATALOG_PATH = BASE_DIR / "data" / "source" / "catalog.snapshot.json"
STAGING_PATH = BASE_DIR / "data" / "staging" / "staged_products.json"
CANONICAL_OUTPUT_PATH = BASE_DIR / "data" / "canonical" / "catalog.canonical.json"
ALIASES_PATH = BASE_DIR / "config" / "search_aliases.json"

def load_aliases():
    if ALIASES_PATH.exists():
        with open(ALIASES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def resolve_brand_id(brand_str: str, aliases_cfg: dict) -> tuple[str, str]:
    if not brand_str:
        return None, None
    norm = brand_str.lower().replace("ё", "е").strip()
    for b in aliases_cfg.get("brands", []):
        if norm == b["catalog_value"].lower().replace("ё", "е").strip():
            return b["id"], b["display"]
        for alias in b["aliases"]:
            if norm == alias.lower().replace("ё", "е").strip():
                return b["id"], b["display"]
    return None, brand_str

def resolve_product_type_id(name: str, subcategory: str, aliases_cfg: dict) -> tuple[str, str]:
    text = (name + " " + (subcategory or "")).lower().replace("ё", "е")
    for pt in aliases_cfg.get("product_types", []):
        for alias in pt["aliases"]:
            alias_norm = alias.lower().replace("ё", "е")
            if re.search(r'\b' + re.escape(alias_norm) + r'\b', text):
                return pt["id"], pt["display"]
    return None, None

def extract_product_attributes(name: str) -> dict:
    attrs = {}
    if not name:
        return attrs
    text = name.lower().replace("ё", "е")
    # Weight: e.g. 20 кг, 20кг, 25 кг, 0,6 кг, 1.5 кг
    wm = re.search(r'(\d+(?:[\.,]\d+)?)\s*(кг|kg)\b', text)
    if wm:
        val_str = wm.group(1).replace(',', '.')
        val = float(val_str)
        attrs["weight_kg"] = int(val) if val.is_integer() else val
    # Volume: e.g. 9 л, 0,9 л, 2.7 л, 10л
    vm = re.search(r'(\d+(?:[\.,]\d+)?)\s*(л|l)\b', text)
    if vm:
        val_str = vm.group(1).replace(',', '.')
        val = float(val_str)
        attrs["volume_l"] = int(val) if val.is_integer() else val
    return attrs

def build_canonical_catalog():
    CANONICAL_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    aliases_cfg = load_aliases()

    canonical_products = []

    if SOURCE_CATALOG_PATH.exists():
        with open(SOURCE_CATALOG_PATH, "r", encoding="utf-8") as f:
            raw_catalog = json.load(f)
        for item in raw_catalog:
            b_id, b_disp = resolve_brand_id(item.get("brand"), aliases_cfg)
            pt_id, pt_disp = resolve_product_type_id(item.get("name", ""), item.get("subcategory", ""), aliases_cfg)
            attrs = extract_product_attributes(item.get("name", ""))

            canonical_products.append({
                "id": item.get("id"),
                "name": item.get("name"),
                "brand": item.get("brand"),
                "brand_id": b_id,
                "category": item.get("category"),
                "subcategory": item.get("subcategory"),
                "product_type_id": pt_id,
                "sku": item.get("sku"),
                "price": item.get("price"),
                "url": item.get("url"),
                "image": item.get("image"),
                "attributes": attrs,
                "provenance": {
                    "source": "source:catalog.snapshot.json",
                    "immutable": True
                }
            })

    existing_skus = {str(item.get("sku") or "").casefold() for item in canonical_products if item.get("sku")}
    existing_urls = {str(item.get("url") or "").rstrip("/").casefold() for item in canonical_products if item.get("url")}

    if STAGING_PATH.exists():
        with open(STAGING_PATH, "r", encoding="utf-8") as f:
            staging_records = json.load(f)
        for record in staging_records:
            raw = record.get("raw", {})
            src = record.get("source", {})
            sku_key = str(raw.get("sku") or "").casefold()
            url_key = str(raw.get("url") or "").rstrip("/").casefold()
            if (sku_key and sku_key in existing_skus) or (url_key and url_key in existing_urls):
                continue
            b_id, b_disp = resolve_brand_id(raw.get("brand"), aliases_cfg)
            pt_id, pt_disp = resolve_product_type_id(raw.get("name", ""), raw.get("subcategory", ""), aliases_cfg)
            attrs = extract_product_attributes(raw.get("name", ""))

            canonical_products.append({
                "id": "remplanika:" + hashlib.sha256(
                    str(record.get("source_product_key") or raw.get("url") or raw.get("sku")).encode("utf-8")
                ).hexdigest()[:20],
                "name": raw.get("name"),
                "brand": raw.get("brand"),
                "brand_id": b_id,
                "category": raw.get("category"),
                "subcategory": raw.get("subcategory"),
                "product_type_id": pt_id,
                "sku": raw.get("sku"),
                "price": raw.get("price"),
                "url": raw.get("url"),
                "image": raw.get("image"),
                "attributes": attrs,
                "provenance": {
                    "source": src.get("source_id"),
                    "source_product_key": record.get("source_product_key"),
                    "retrieved_at": src.get("retrieved_at"),
                    "content_sha256": src.get("content_sha256")
                }
            })
            if sku_key:
                existing_skus.add(sku_key)
            if url_key:
                existing_urls.add(url_key)

    with open(CANONICAL_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(canonical_products, f, ensure_ascii=False, indent=2)

    print(f"Built canonical catalog with {len(canonical_products)} items at {CANONICAL_OUTPUT_PATH}")
    return CANONICAL_OUTPUT_PATH

if __name__ == "__main__":
    build_canonical_catalog()
