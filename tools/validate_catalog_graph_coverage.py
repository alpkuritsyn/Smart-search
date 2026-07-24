#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def pct(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 2) if denominator else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure real product and type coverage of the approved complement graph")
    parser.add_argument("catalog", type=Path)
    parser.add_argument("graph", type=Path)
    parser.add_argument("scope", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    catalog = load(args.catalog)
    graph = load(args.graph)
    scope = load(args.scope)
    scoped_ids = set(scope.get("product_type_ids") or [])
    nodes = graph.get("nodes") or []
    approved_edges = [edge for edge in graph.get("edges") or [] if edge.get("review_status") == "approved"]
    node_ids = {node.get("id") for node in nodes}
    outgoing_ids = {edge.get("from") for edge in approved_edges}
    type_counts = Counter(item.get("product_type_id") for item in catalog if item.get("product_type_id"))

    mapped_products = sum(type_counts.values())
    scoped_products = sum(type_counts[type_id] for type_id in scoped_ids)
    scoped_types_with_products = {type_id for type_id in scoped_ids if type_counts[type_id] > 0}
    covered_types = scoped_types_with_products & outgoing_ids
    covered_products = sum(type_counts[type_id] for type_id in covered_types)
    missing_nodes = sorted(scoped_types_with_products - node_ids)
    missing_outgoing = sorted(scoped_types_with_products - outgoing_ids)
    empty_targets = sorted(
        {
            edge.get("to")
            for edge in approved_edges
            if edge.get("from") in scoped_ids and type_counts[edge.get("to")] == 0
        }
    )

    metrics = {
        "catalog_products": len(catalog),
        "mapped_products": mapped_products,
        "catalog_mapping_pct": pct(mapped_products, len(catalog)),
        "scoped_products": scoped_products,
        "scoped_types_with_products": len(scoped_types_with_products),
        "scoped_types_with_outgoing_edges": len(covered_types),
        "scoped_type_outgoing_coverage_pct": pct(len(covered_types), len(scoped_types_with_products)),
        "scoped_products_with_outgoing_edges": covered_products,
        "scoped_product_outgoing_coverage_pct": pct(covered_products, scoped_products),
        "approved_edges": len(approved_edges),
        "missing_graph_nodes": missing_nodes,
        "missing_outgoing_types": missing_outgoing,
        "empty_edge_targets": empty_targets,
        "products_by_type": dict(sorted(type_counts.items())),
    }

    errors: list[str] = []
    if metrics["catalog_mapping_pct"] < float(scope.get("minimum_catalog_mapping_pct") or 0):
        errors.append(
            f"catalog mapping {metrics['catalog_mapping_pct']}% is below "
            f"{scope.get('minimum_catalog_mapping_pct')}%"
        )
    if metrics["scoped_type_outgoing_coverage_pct"] < float(
        scope.get("minimum_scoped_type_outgoing_coverage_pct") or 100
    ):
        errors.append(f"scoped types without outgoing edges: {missing_outgoing}")
    if metrics["scoped_product_outgoing_coverage_pct"] < float(
        scope.get("minimum_scoped_product_outgoing_coverage_pct") or 100
    ):
        errors.append("scoped product outgoing coverage is below threshold")
    if missing_nodes:
        errors.append(f"scoped types missing graph nodes: {missing_nodes}")
    if scope.get("require_all_edge_targets_materialized") and empty_targets:
        errors.append(f"approved edges target empty catalog types: {empty_targets}")

    metrics["status"] = "PASS" if not errors else "FAIL"
    metrics["errors"] = errors
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
