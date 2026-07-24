#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


CONTRACT_VERSION = "antigravity-graph-review-v1"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def edge_tuple(edge: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(edge.get("source", edge.get("from", ""))),
        str(edge.get("relation", "")),
        str(edge.get("target", edge.get("to", ""))),
    )


def relevant_neighborhood(graph: dict[str, Any], tokens: list[str]) -> dict[str, Any]:
    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
    edges = [edge for edge in (graph.get("links") or graph.get("edges") or []) if isinstance(edge, dict)]
    by_id = {str(node.get("id", "")): node for node in nodes}
    folded = [str(token).casefold() for token in tokens if str(token).strip()]
    selected = {
        node_id
        for node_id, node in by_id.items()
        if any(token in f"{node_id} {node.get('label', '')}".casefold() for token in folded)
    }
    selected_edges: list[dict[str, Any]] = []
    for edge in edges:
        source, relation, target = edge_tuple(edge)
        if source in selected or target in selected or any(token in relation.casefold() for token in folded):
            selected_edges.append(edge)
            selected.update((source, target))
    return {
        "nodes": [by_id[node_id] for node_id in sorted(selected) if node_id in by_id],
        "edges": sorted(selected_edges, key=edge_tuple),
    }


def deterministic_check(case: dict[str, Any], neighborhood: dict[str, Any]) -> dict[str, Any]:
    expected = case.get("expected") if isinstance(case.get("expected"), dict) else {}
    actual = {edge_tuple(edge) for edge in neighborhood.get("edges", [])}
    required = {tuple(map(str, edge)) for edge in expected.get("required_edges", [])}
    missing = sorted(required - actual)
    node_ids = {str(node.get("id", "")) for node in neighborhood.get("nodes", [])}
    prefixes = [str(prefix) for prefix in expected.get("forbidden_node_prefixes", [])]
    forbidden = sorted(node_id for node_id in node_ids if any(node_id.startswith(prefix) for prefix in prefixes))
    return {
        "status": "PASS" if not missing and not forbidden else "FAIL",
        "required_edges": [list(edge) for edge in sorted(required)],
        "missing_required_edges": [list(edge) for edge in missing],
        "forbidden_nodes_found": forbidden,
    }


def artifact(path: Path) -> dict[str, str]:
    return {"path": path.as_posix(), "sha256": sha256_file(path)}


def build_request(graph_path: Path, cases_path: Path, coverage_path: Path | None = None) -> dict[str, Any]:
    graph = load_json(graph_path)
    cases_doc = load_json(cases_path)
    coverage = load_json(coverage_path) if coverage_path else None
    packaged_cases = []
    for case in cases_doc.get("cases", []):
        if not isinstance(case, dict):
            raise ValueError("Each graph test case must be an object")
        neighborhood = relevant_neighborhood(graph, list(case.get("query_tokens") or []))
        packaged_cases.append(
            {
                "case": case,
                "deterministic_check": deterministic_check(case, neighborhood),
                "neighborhood": neighborhood,
            }
        )
    artifacts = {"graph": artifact(graph_path), "cases": artifact(cases_path)}
    if coverage_path:
        artifacts["coverage"] = artifact(coverage_path)
    return {
        "review_contract_version": CONTRACT_VERSION,
        "review_type": "independent-semantic-graph-review",
        "status": "READY_FOR_INDEPENDENT_REVIEW",
        "graph_version": graph.get("version"),
        "cases_version": cases_doc.get("version"),
        "source_artifacts": artifacts,
        "coverage_summary": coverage,
        "guardrails": [
            "review in a separate Antigravity subagent context",
            "do not call external LLM providers",
            "do not edit or approve graph edges",
            "do not infer SKU compatibility from category edges",
            "use only this packet as evidence; uncertainty becomes REVIEW",
        ],
        "required_report": {
            "path": "reports/antigravity_graph_review.json",
            "agent_definition": "agents/08_graph_semantic_reviewer.md",
            "decision_scope": "findings_only",
        },
        "cases": packaged_cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare an immutable packet for an independent Antigravity graph review.")
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--coverage", type=Path)
    parser.add_argument("--output", type=Path, default=Path("reports/antigravity_graph_review_request.json"))
    args = parser.parse_args()
    request = build_request(args.graph, args.cases, args.coverage)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"status={request['status']}")
    print(f"cases={len(request['cases'])}")
    print(f"request={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
