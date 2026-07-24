#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


CONTRACT_VERSION = "antigravity-graph-review-v1"
VERDICTS = {"PASS", "REVIEW", "FAIL"}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_report(report: dict[str, Any], request: dict[str, Any], request_sha256: str) -> list[str]:
    errors: list[str] = []
    if report.get("review_contract_version") != CONTRACT_VERSION:
        errors.append("unexpected review_contract_version")
    if report.get("review_type") != "independent-semantic-graph-review":
        errors.append("unexpected review_type")
    if report.get("decision_scope") != "findings_only":
        errors.append("decision_scope must be findings_only")
    if report.get("source_request_sha256") != request_sha256:
        errors.append("source_request_sha256 does not match request bytes")

    reviewer = report.get("reviewer")
    if not isinstance(reviewer, dict):
        errors.append("reviewer must be an object")
        reviewer = {}
    expected_reviewer = {
        "agent_definition": "agents/08_graph_semantic_reviewer.md",
        "execution_context": "separate-antigravity-subagent",
        "independent_from_graph_author": True,
        "is_graph_author": False,
        "external_provider_used": False,
    }
    for key, expected in expected_reviewer.items():
        if reviewer.get(key) != expected:
            errors.append(f"reviewer.{key} must equal {expected!r}")

    status = report.get("status")
    if status not in VERDICTS:
        errors.append("status must be PASS, REVIEW or FAIL")

    expected_ids = []
    for item in request.get("cases", []):
        if isinstance(item, dict) and isinstance(item.get("case"), dict):
            expected_ids.append(str(item["case"].get("id", "")))
    results = report.get("results")
    if not isinstance(results, list):
        errors.append("results must be an array")
        results = []
    actual_ids = [str(item.get("case_id", "")) for item in results if isinstance(item, dict)]
    if sorted(actual_ids) != sorted(expected_ids):
        errors.append(f"results case IDs must match request exactly: expected={sorted(expected_ids)} actual={sorted(actual_ids)}")
    if len(actual_ids) != len(set(actual_ids)):
        errors.append("duplicate case IDs in results")

    verdicts: list[str] = []
    for index, item in enumerate(results):
        if not isinstance(item, dict):
            errors.append(f"results[{index}] must be an object")
            continue
        prefix = f"results[{index}]"
        verdict = item.get("verdict")
        if verdict not in VERDICTS:
            errors.append(f"{prefix}.verdict must be PASS, REVIEW or FAIL")
        else:
            verdicts.append(verdict)
        if not isinstance(item.get("summary"), str) or not item.get("summary", "").strip():
            errors.append(f"{prefix}.summary must be non-empty")
        evidence = item.get("evidence")
        if not isinstance(evidence, list):
            errors.append(f"{prefix}.evidence must be an array")
            evidence = []
        if verdict == "PASS" and not evidence:
            errors.append(f"{prefix}.evidence must be non-empty for PASS")
        for evidence_index, entry in enumerate(evidence):
            if not isinstance(entry, dict) or not str(entry.get("source", "")).strip() or not str(entry.get("claim", "")).strip():
                errors.append(f"{prefix}.evidence[{evidence_index}] must contain source and claim")
        for field in ("missing_evidence", "risky_claims", "required_changes"):
            if not isinstance(item.get(field), list):
                errors.append(f"{prefix}.{field} must be an array")

    expected_status = "FAIL" if "FAIL" in verdicts else "REVIEW" if "REVIEW" in verdicts else "PASS"
    if verdicts and status != expected_status:
        errors.append(f"status must aggregate verdicts as {expected_status}")
    if not re.fullmatch(r"[0-9a-f]{64}", str(report.get("source_request_sha256", ""))):
        errors.append("source_request_sha256 must be 64 lowercase hex characters")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an independent Antigravity graph-review handoff.")
    parser.add_argument("report", type=Path)
    parser.add_argument("--request", type=Path, default=Path("reports/antigravity_graph_review_request.json"))
    args = parser.parse_args()
    try:
        report = load_json(args.report)
        request = load_json(args.request)
        errors = validate_report(report, request, sha256_file(args.request))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(f"INVALID: {error}", file=sys.stderr)
        return 2
    status = str(report["status"])
    print(f"status={status}")
    print(f"cases={len(report['results'])}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
