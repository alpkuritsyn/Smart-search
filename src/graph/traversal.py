#!/usr/bin/env python3
"""
Complement Graph Traversal Module for Smart-search V1.
Retrieves complement categories, relations, and rationale for a given product_type_id.
"""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
APPROVED_GRAPH_PATH = BASE_DIR / "data" / "graph" / "complement_graph.approved.json"
CANONICAL_CATALOG_PATH = BASE_DIR / "data" / "canonical" / "catalog.canonical.json"

def load_approved_graph():
    if APPROVED_GRAPH_PATH.exists():
        with open(APPROVED_GRAPH_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"nodes": [], "edges": []}

def pluralize_label(label: str) -> str:
    lbl = label.lower()
    if lbl.endswith("к"):
        return lbl + "и"
    elif lbl.endswith("а") or lbl.endswith("ь"):
        return lbl[:-1] + "и"
    elif lbl.endswith("ка"):
        return lbl[:-2] + "ки"
    else:
        return lbl + "ы"

def get_complements_for_type(product_type_id: str, canonical_catalog: list = None) -> list:
    graph = load_approved_graph()
    edges = graph.get("edges", [])
    nodes_by_id = {node["id"]: node for node in graph.get("nodes", [])}

    if canonical_catalog is None and CANONICAL_CATALOG_PATH.exists():
        with open(CANONICAL_CATALOG_PATH, "r", encoding="utf-8") as f:
            canonical_catalog = json.load(f)
    elif canonical_catalog is None:
        canonical_catalog = []

    complements = []
    if not product_type_id:
        return complements

    for edge in edges:
        if edge.get("from") == product_type_id and edge.get("review_status") == "approved":
            target_node_id = edge.get("to")
            target_node = nodes_by_id.get(target_node_id, {})
            relation = edge.get("relation")
            rationale = edge.get("rationale")

            matching_products = []
            for item in canonical_catalog:
                if item.get("product_type_id") == target_node_id:
                    matching_products.append(item)
                elif not item.get("product_type_id"):
                    selector = target_node.get("catalog_selector", {})
                    subcat = item.get("subcategory", "") or ""
                    contains_any = selector.get("contains_any", [])
                    if any(kw.lower() in subcat.lower() for kw in contains_any):
                        matching_products.append(item)

            data_gap = False
            data_gap_message = None
            if not matching_products:
                data_gap = True
                data_gap_message = f"В каталоге пока нет карточек для категории '{target_node.get('label', target_node_id)}'."

            title_prefix = {
                "PREPARE_WITH": "Для подготовки",
                "LEVEL_WITH": "Для выравнивания",
                "APPLY_WITH": "Для нанесения",
                "PROTECT_WITH": "Для защиты",
                "USE_WITH": "Используется с",
                "FINISH_WITH": "Для финишного слоя"
            }.get(relation, "Рекомендуется")

            plural_label = pluralize_label(target_node.get("label", target_node_id))
            title = f"{title_prefix}: {plural_label}"

            complements.append({
                "target_type_id": target_node_id,
                "title": title,
                "relation": relation,
                "rationale": rationale,
                "data_gap": data_gap,
                "data_gap_message": data_gap_message,
                "products": matching_products[:4]
            })

    return complements

if __name__ == "__main__":
    comps = get_complements_for_type("type:paint")
    for c in comps:
        print(" -", c["title"], "| relation:", c["relation"], "| products count:", len(c["products"]))
