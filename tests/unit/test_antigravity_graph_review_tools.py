from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


prepare = load_module("prepare_review", ROOT / "tools" / "prepare_antigravity_graph_review.py")
validate = load_module("validate_review", ROOT / "tools" / "validate_antigravity_graph_review.py")


def sample_files(tmp_path: Path) -> tuple[Path, Path]:
    graph = {
        "version": "g1",
        "nodes": [{"id": "type:paint", "label": "Краска"}, {"id": "type:brush", "label": "Кисть"}],
        "edges": [{"from": "type:paint", "relation": "APPLY_WITH", "to": "type:brush", "rationale": "Инструмент нанесения"}],
    }
    cases = {
        "version": "c1",
        "cases": [{"id": "paint-tools", "query_tokens": ["paint", "brush"], "expected": {"required_edges": [["type:paint", "APPLY_WITH", "type:brush"]]}}],
    }
    graph_path = tmp_path / "graph.json"
    cases_path = tmp_path / "cases.json"
    graph_path.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
    cases_path.write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
    return graph_path, cases_path


def test_prepare_packet_contains_hashes_and_deterministic_result(tmp_path: Path):
    graph_path, cases_path = sample_files(tmp_path)
    packet = prepare.build_request(graph_path, cases_path)
    assert packet["status"] == "READY_FOR_INDEPENDENT_REVIEW"
    assert packet["source_artifacts"]["graph"]["sha256"] == hashlib.sha256(graph_path.read_bytes()).hexdigest()
    assert packet["cases"][0]["deterministic_check"]["status"] == "PASS"


def test_validator_accepts_independent_complete_report(tmp_path: Path):
    graph_path, cases_path = sample_files(tmp_path)
    request = prepare.build_request(graph_path, cases_path)
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    request_hash = hashlib.sha256(request_path.read_bytes()).hexdigest()
    report = {
        "review_contract_version": "antigravity-graph-review-v1",
        "review_type": "independent-semantic-graph-review",
        "source_request_sha256": request_hash,
        "decision_scope": "findings_only",
        "reviewer": {
            "agent_definition": "agents/08_graph_semantic_reviewer.md",
            "execution_context": "separate-antigravity-subagent",
            "independent_from_graph_author": True,
            "is_graph_author": False,
            "external_provider_used": False,
        },
        "status": "PASS",
        "results": [{
            "case_id": "paint-tools",
            "verdict": "PASS",
            "summary": "Связь корректна.",
            "evidence": [{"source": "request.cases[paint-tools]", "claim": "Ожидаемое ребро присутствует"}],
            "missing_evidence": [],
            "risky_claims": [],
            "required_changes": [],
        }],
    }
    assert validate.validate_report(report, request, request_hash) == []


def test_validator_rejects_self_review_and_external_provider(tmp_path: Path):
    graph_path, cases_path = sample_files(tmp_path)
    request = prepare.build_request(graph_path, cases_path)
    bad = {
        "review_contract_version": "antigravity-graph-review-v1",
        "review_type": "independent-semantic-graph-review",
        "source_request_sha256": "0" * 64,
        "decision_scope": "findings_only",
        "reviewer": {
            "agent_definition": "agents/08_graph_semantic_reviewer.md",
            "execution_context": "lead-context",
            "independent_from_graph_author": False,
            "is_graph_author": True,
            "external_provider_used": True,
        },
        "status": "PASS",
        "results": [],
    }
    errors = validate.validate_report(bad, request, "0" * 64)
    assert any("independent_from_graph_author" in error for error in errors)
    assert any("external_provider_used" in error for error in errors)
    assert any("case IDs" in error for error in errors)
