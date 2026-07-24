#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
CATALOG_PATH = BASE_DIR / "data" / "canonical" / "catalog.canonical.json"
GRAPH_PATH = BASE_DIR / "data" / "graph" / "complement_graph.approved.json"
SCOPE_PATH = BASE_DIR / "config" / "release_scope.v1.json"
OUTPUT_DIR = BASE_DIR / "graph-corpus"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    catalog = load(CATALOG_PATH)
    graph = load(GRAPH_PATH)
    scope = load(SCOPE_PATH)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    by_type: dict[str, list[dict]] = defaultdict(list)
    for product in catalog:
        if product.get("product_type_id"):
            by_type[product["product_type_id"]].append(product)

    lines = ["# Canonical product types", ""]
    for type_id in scope.get("product_type_ids") or []:
        products = by_type.get(type_id, [])
        lines.extend([f"## {type_id}", f"Product count: {len(products)}", "Examples:"])
        lines.extend(f"- {item.get('name')} (SKU: {item.get('sku')})" for item in products[:8])
        lines.append("")
    (OUTPUT_DIR / "catalog_types.md").write_text("\n".join(lines), encoding="utf-8")

    edge_lines = ["# Approved complement rules", ""]
    for edge in graph.get("edges") or []:
        edge_lines.extend(
            [
                f"## {edge['from']} --{edge['relation']}--> {edge['to']}",
                f"Rationale: {edge['rationale']}",
                f"Provenance: {', '.join(edge.get('provenance') or [])}",
                f"Review status: {edge.get('review_status')}",
                "",
            ]
        )
    (OUTPUT_DIR / "approved_rules.md").write_text("\n".join(edge_lines), encoding="utf-8")

    outgoing = Counter(edge.get("from") for edge in graph.get("edges") or [] if edge.get("review_status") == "approved")
    gap_lines = ["# Coverage audit", ""]
    for type_id in scope.get("product_type_ids") or []:
        gap_lines.append(
            f"- {type_id}: products={len(by_type.get(type_id, []))}; approved_outgoing_edges={outgoing[type_id]}"
        )
    (OUTPUT_DIR / "coverage.md").write_text("\n".join(gap_lines) + "\n", encoding="utf-8")
    print(f"corpus={OUTPUT_DIR} files=3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
