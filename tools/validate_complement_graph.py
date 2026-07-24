#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ALLOWED_RELATIONS = {
    "PREPARE_WITH",
    "LEVEL_WITH",
    "APPLY_WITH",
    "PROTECT_WITH",
    "USE_WITH",
    "FINISH_WITH",
}
ALLOWED_STATUSES = {"candidate", "rejected", "approved"}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def selector_count(node: dict, catalog: list[dict]) -> int:
    selector = node.get("catalog_selector") or {}
    field = selector.get("field")
    needles = selector.get("contains_any") or []
    if not field or not needles:
        return 0
    normalized = [str(value).casefold() for value in needles]
    return sum(
        1
        for record in catalog
        if any(needle in str(record.get(field) or "").casefold() for needle in normalized)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("graph")
    parser.add_argument("catalog")
    parser.add_argument("--published", action="store_true")
    args = parser.parse_args()

    graph = load(Path(args.graph))
    catalog = load(Path(args.catalog))
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(graph, dict):
        errors.append("graph root must be an object")
        nodes, edges = [], []
    else:
        nodes = graph.get("nodes") or []
        edges = graph.get("edges") or []
    if not isinstance(catalog, list):
        errors.append("catalog root must be an array")
        catalog = []

    node_ids = [node.get("id") for node in nodes if isinstance(node, dict)]
    if len(node_ids) != len(set(node_ids)):
        errors.append("node ids are not unique")
    known = set(node_ids)

    for node in nodes:
        if not isinstance(node, dict) or not node.get("id") or not node.get("label"):
            errors.append(f"invalid node: {node!r}")
            continue
        count = selector_count(node, catalog)
        if count == 0:
            if node.get("allow_empty_until_parser") and not args.published:
                warnings.append(f"node {node['id']} has no products; parser gap explicitly allowed")
            else:
                errors.append(f"node {node['id']} selector resolves to zero products")

    edge_keys: set[tuple[str, str, str]] = set()
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append(f"edge[{index}] is not an object")
            continue
        source, target = edge.get("from"), edge.get("to")
        relation = edge.get("relation")
        if source not in known or target not in known:
            errors.append(f"edge[{index}] has dangling endpoint: {source} -> {target}")
        if relation not in ALLOWED_RELATIONS:
            errors.append(f"edge[{index}] has unsupported relation: {relation}")
        key = (str(source), str(relation), str(target))
        if key in edge_keys:
            errors.append(f"duplicate edge: {key}")
        edge_keys.add(key)
        if not str(edge.get("rationale") or "").strip():
            errors.append(f"edge[{index}] has no rationale")
        provenance = edge.get("provenance")
        if not isinstance(provenance, list) or not provenance:
            errors.append(f"edge[{index}] has no provenance")
        status = edge.get("review_status")
        if status not in ALLOWED_STATUSES:
            errors.append(f"edge[{index}] invalid review_status: {status}")
        if args.published and status != "approved":
            errors.append(f"published edge[{index}] is not approved")

    print(f"nodes={len(nodes)} edges={len(edges)} published_mode={args.published}")
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    print("status=PASS" if not errors else "status=FAIL")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
