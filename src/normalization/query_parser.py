#!/usr/bin/env python3
"""
Deterministic Query Parser for Smart-search V1.
Extracts brand, product_type, weight/volume attributes, and normalized query tokens.
"""
import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ALIASES_PATH = BASE_DIR / "config" / "search_aliases.json"

def load_aliases():
    if ALIASES_PATH.exists():
        with open(ALIASES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

_ALIASES_CONFIG = load_aliases()


def contains_alias(normalized_text: str, alias: str) -> bool:
    """Match a normalized alias as a whole token/phrase, never as a substring."""
    if not alias:
        return False
    return re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized_text, flags=re.UNICODE) is not None

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = text.replace("ё", "е")
    # Split digits and units (e.g., 20кг -> 20 кг, 9л -> 9 л, 0,9л -> 0.9 л)
    text = re.sub(r'(\d+[\.,]?\d*)\s*(кг|kg|л|l)\b', lambda m: m.group(1).replace(',', '.') + ' ' + m.group(2), text)
    # Replace non-alphanumeric punctuation except whitespace and dots with spaces
    text = re.sub(r'[^\w\s\.]', ' ', text)
    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def parse_query(raw_query: str) -> dict:
    if not raw_query or not raw_query.strip():
        return {
            "raw": raw_query or "",
            "normalized": "",
            "brand_id": None,
            "brand_display": None,
            "product_type_id": None,
            "product_type_display": None,
            "attributes": {},
            "unparsed_tokens": []
        }

    normalized = normalize_text(raw_query)
    tokens = normalized.split()

    brand_id = None
    brand_display = None
    product_type_id = None
    product_type_display = None
    attributes = {}

    brands = _ALIASES_CONFIG.get("brands", [])
    product_types = _ALIASES_CONFIG.get("product_types", [])

    matched_tokens = set()

    for b in brands:
        for alias in sorted(b["aliases"], key=len, reverse=True):
            alias_norm = normalize_text(alias)
            if contains_alias(normalized, alias_norm):
                brand_id = b["id"]
                brand_display = b["display"]
                alias_parts = alias_norm.split()
                matched_tokens.update(alias_parts)
                break
        if brand_id:
            break

    for pt in product_types:
        for alias in sorted(pt["aliases"], key=len, reverse=True):
            alias_norm = normalize_text(alias)
            if contains_alias(normalized, alias_norm):
                product_type_id = pt["id"]
                product_type_display = pt["display"]
                alias_parts = alias_norm.split()
                matched_tokens.update(alias_parts)
                break
        if product_type_id:
            break

    weight_match = re.search(r'\b(\d+(?:[\.,]\d+)?)\s*(кг|kg)\b', normalized)
    if weight_match:
        val_str = weight_match.group(1).replace(',', '.')
        val = float(val_str)
        if val.is_integer():
            val = int(val)
        attributes["weight_kg"] = val
        matched_tokens.add(weight_match.group(1))
        matched_tokens.add(weight_match.group(2))

    volume_match = re.search(r'\b(\d+(?:[\.,]\d+)?)\s*(л|l)\b', normalized)
    if volume_match:
        val_str = volume_match.group(1).replace(',', '.')
        val = float(val_str)
        if val.is_integer():
            val = int(val)
        attributes["volume_l"] = val
        matched_tokens.add(volume_match.group(1))
        matched_tokens.add(volume_match.group(2))

    unparsed = [t for t in tokens if t not in matched_tokens]

    return {
        "raw": raw_query,
        "normalized": normalized,
        "brand_id": brand_id,
        "brand_display": brand_display,
        "product_type_id": product_type_id,
        "product_type_display": product_type_display,
        "attributes": attributes,
        "unparsed_tokens": unparsed
    }
