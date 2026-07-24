#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def relevant_neighborhood(graph: dict, tokens: list[str]) -> dict:
    nodes = graph.get("nodes") or []
    links = graph.get("links") or graph.get("edges") or []
    by_id = {str(node.get("id")): node for node in nodes if isinstance(node, dict)}
    folded = [str(token).casefold() for token in tokens]
    selected = {
        node_id
        for node_id, node in by_id.items()
        if any(
            token in (node_id + " " + str(node.get("label") or "")).casefold()
            for token in folded
        )
    }
    neighbor_links = []
    for link in links:
        source = str(link.get("source", link.get("from", "")))
        target = str(link.get("target", link.get("to", "")))
        relation = str(link.get("relation") or "")
        if source in selected or target in selected or any(token in relation.casefold() for token in folded):
            neighbor_links.append(link)
            selected.update((source, target))
    selected_nodes = [by_id[node_id] for node_id in selected if node_id in by_id]
    return {"nodes": selected_nodes[:60], "links": neighbor_links[:100]}


def extract_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def call_gemini(api_key: str, model: str, prompt: str) -> dict:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    body = json.dumps(
        {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8"))
    text = payload["candidates"][0]["content"]["parts"][0]["text"]
    return extract_json(text)


def mock_offline_review(case: dict, context: dict) -> dict:
    case_id = case.get("id")
    links = context.get("links", [])
    expected = case.get("expected", {})
    actual_edges = {
        (
            str(link.get("source", link.get("from", ""))),
            str(link.get("relation") or ""),
            str(link.get("target", link.get("to", ""))),
        )
        for link in links
    }
    required = {tuple(edge) for edge in expected.get("required_edges", [])}
    missing = sorted(required - actual_edges)
    node_ids = {str(node.get("id") or "") for node in context.get("nodes", [])}
    forbidden_prefixes = expected.get("forbidden_node_prefixes", [])
    forbidden = sorted(
        node_id for node_id in node_ids if any(node_id.startswith(prefix) for prefix in forbidden_prefixes)
    )
    if not missing and not forbidden:
        return {
            "verdict": "PASS",
            "reason": f"Offline structural review for {case_id}: all explicit expectations satisfied",
            "evidence": [f"required edge present: {edge}" for edge in sorted(required)],
            "missing_evidence": [],
            "risky_claims": []
        }
    return {
        "verdict": "FAIL",
        "reason": f"Offline structural review for {case_id}: explicit expectations failed",
        "evidence": [],
        "missing_evidence": [f"missing edge: {edge}" for edge in missing],
        "risky_claims": [f"forbidden node: {node_id}" for node_id in forbidden]
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--output", default="reports/gemini_graph_review.json")
    parser.add_argument("--model", default=os.environ.get("GEMINI_TEST_MODEL", "gemini-3.1-flash-lite"))
    parser.add_argument("--offline", action="store_true", help="run explicit deterministic structural checks without Gemini")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    if not args.offline and (not api_key or api_key.startswith("mock_")):
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                {
                    "cases_version": load(Path(args.cases)).get("version"),
                    "status": "NOT_RUN",
                    "reason": "GEMINI_API_KEY is missing; offline checks must use --offline and cannot be labelled Gemini review",
                    "results": [],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print("ERROR: GEMINI_API_KEY is required for Gemini review; use --offline only for structural checks", file=sys.stderr)
        return 2

    graph = load(Path(args.graph))
    cases_doc = load(Path(args.cases))
    results = []
    for case in cases_doc.get("cases", []):
        context = relevant_neighborhood(graph, case.get("query_tokens") or [])
        if not args.offline:
            prompt = (
                "Ты независимый ревьюер графа комплементарных товарных категорий V1. "
                "Оцени только предоставленные nodes/links; не добавляй знания из памяти. "
                "Верни JSON: verdict PASS|FAIL|REVIEW, reason, evidence (array), "
                "missing_evidence (array), risky_claims (array).\n\n"
                f"CASE:\n{json.dumps(case, ensure_ascii=False, indent=2)}\n\n"
                f"GRAPH NEIGHBORHOOD:\n{json.dumps(context, ensure_ascii=False, indent=2)}"
            )
            try:
                verdict = call_gemini(api_key, args.model, prompt)
                results.append({"case_id": case.get("id"), "model": args.model, "review": verdict})
                print(f"{case.get('id')}: {verdict.get('verdict', 'UNKNOWN')}")
            except Exception as exc:
                verdict = {
                    "verdict": "REVIEW",
                    "reason": f"Gemini call failed: {exc}",
                    "evidence": [],
                    "missing_evidence": ["external Gemini review did not complete"],
                    "risky_claims": [],
                }
                results.append({"case_id": case.get("id"), "model": args.model, "review": verdict})
                print(f"{case.get('id')}: REVIEW (Gemini call failed)")
        else:
            verdict = mock_offline_review(case, context)
            results.append({"case_id": case.get("id"), "model": "offline-structural", "review": verdict})
            print(f"{case.get('id')}: {verdict.get('verdict')}")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "cases_version": cases_doc.get("version"),
                "status": "PASS" if all(item["review"].get("verdict") == "PASS" for item in results) else "REVIEW",
                "mode": "offline-structural" if args.offline else "gemini",
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"report={output}")
    return 0 if all(item["review"].get("verdict") == "PASS" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
