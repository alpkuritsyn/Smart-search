#!/usr/bin/env python3
"""
Deterministic Query Parser for Smart-search V1.
Extracts brand, product_type, weight/volume & characteristic attributes, and normalized query tokens.
"""
import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ALIASES_PATH = BASE_DIR / "config" / "search_aliases.json"
ATTRIBUTES_PATH = BASE_DIR / "config" / "attributes_taxonomy.json"

def load_aliases():
    if ALIASES_PATH.exists():
        with open(ALIASES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def load_attributes_taxonomy():
    if ATTRIBUTES_PATH.exists():
        with open(ATTRIBUTES_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("attributes", [])
    return []

_ALIASES_CONFIG = load_aliases()
_ATTRIBUTES_TAXONOMY = load_attributes_taxonomy()


class AliasTrie:
    """Trie structure for fast multi-token phrase matching."""

    def __init__(self):
        self.root = {}

    def insert(self, phrase_tokens: list[str], payload: dict):
        if not phrase_tokens:
            return
        node = self.root
        for tok in phrase_tokens:
            node = node.setdefault(tok, {})
        node["_payload"] = payload

    def match(self, tokens: list[str]) -> list[tuple[int, int, dict]]:
        matches = []
        n = len(tokens)
        for i in range(n):
            node = self.root
            j = i
            best_match = None
            while j < n and tokens[j] in node:
                node = node[tokens[j]]
                j += 1
                if "_payload" in node:
                    best_match = (i, j, node["_payload"])
            if best_match:
                matches.append(best_match)
        return matches


def build_alias_trie():
    trie = AliasTrie()
    aliases_config = load_aliases()
    attributes_taxonomy = load_attributes_taxonomy()

    # Product Types (Checked FIRST)
    for pt in aliases_config.get("product_types", []):
        for alias in sorted(pt.get("aliases", []), key=len, reverse=True):
            norm_alias = normalize_text(alias)
            if norm_alias:
                trie.insert(norm_alias.split(), {
                    "kind": "product_type",
                    "id": pt["id"],
                    "display": pt["display"]
                })

    # Brands (Checked SECOND)
    for b in aliases_config.get("brands", []):
        for alias in sorted(b.get("aliases", []), key=len, reverse=True):
            norm_alias = normalize_text(alias)
            if norm_alias:
                trie.insert(norm_alias.split(), {
                    "kind": "brand",
                    "id": b["id"],
                    "display": b["display"]
                })

    # Characteristic Attributes
    for attr_group in attributes_taxonomy:
        attr_key = attr_group["key"]
        for val_obj in attr_group.get("values", []):
            canonical_val = val_obj["value"]
            for alias in val_obj.get("aliases", []):
                norm_alias = normalize_text(alias)
                if norm_alias:
                    trie.insert(norm_alias.split(), {
                        "kind": "attribute",
                        "key": attr_key,
                        "value": canonical_val
                    })
    return trie

_ALIAS_TRIE = None

def get_alias_trie():
    global _ALIAS_TRIE
    if _ALIAS_TRIE is None:
        _ALIAS_TRIE = build_alias_trie()
    return _ALIAS_TRIE

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

    matched_tokens = set()
    trie = get_alias_trie()
    matches = trie.match(tokens)

    # 1. Product Types match
    for start_i, end_i, payload in matches:
        if payload["kind"] == "product_type" and not product_type_id:
            product_type_id = payload["id"]
            product_type_display = payload["display"]
            matched_tokens.update(tokens[start_i:end_i])
            break

    # 2. Brands match
    for start_i, end_i, payload in matches:
        if payload["kind"] == "brand" and not brand_id:
            brand_id = payload["id"]
            brand_display = payload["display"]
            matched_tokens.update(tokens[start_i:end_i])
            break

    # 3. Characteristic Attributes match
    for start_i, end_i, payload in matches:
        if payload["kind"] == "attribute":
            attr_k = payload["key"]
            if attr_k not in attributes:
                attributes[attr_k] = payload["value"]
                matched_tokens.update(tokens[start_i:end_i])

    # Numeric attributes: Weight (kg)
    weight_match = re.search(r'\b(\d+(?:[\.,]\d+)?)\s*(кг|kg)\b', normalized)
    if weight_match:
        val_str = weight_match.group(1).replace(',', '.')
        val = float(val_str)
        if val.is_integer():
            val = int(val)
        attributes["weight_kg"] = val
        matched_tokens.add(weight_match.group(1))
        matched_tokens.add(weight_match.group(2))

    # Numeric attributes: Volume (l)
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
