#!/usr/bin/env python3
"""Evaluate the live local resolver against an immutable JSON case set."""

import argparse
import json
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.ml.embedding_resolver import EmbeddingEntityResolver


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=BASE_DIR / "config/entity_resolution_cases.json")
    parser.add_argument("--config", type=Path, default=BASE_DIR / "config/embedding_resolver.json")
    parser.add_argument("--index", type=Path, default=BASE_DIR / "data/embeddings/entities.sqlite")
    parser.add_argument("--report", type=Path, default=BASE_DIR / "reports/evaluation/entity-resolution-calibration.json")
    args = parser.parse_args()

    case_set = json.loads(args.cases.read_text(encoding="utf-8"))
    resolver = EmbeddingEntityResolver(args.config, args.index)
    results = []
    false_hard_filters = 0
    passed = 0
    latencies = []

    for case in case_set["cases"]:
        started = time.perf_counter()
        result = resolver.resolve(case["text"], case["entity_type"])
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        latencies.append(latency_ms)
        accepted = result["status"] in {"exact", "resolved"} and result["entity_id"] is not None
        if accepted and not case.get("hard_filter_allowed", False):
            false_hard_filters += 1

        checks = [result["status"] in case["allowed_statuses"]]
        if "expected_entity_id" in case:
            checks.append(result["entity_id"] == case["expected_entity_id"])
        if case.get("expected_top_candidate_id"):
            top_id = result["candidates"][0]["entity_id"] if result.get("candidates") else None
            checks.append(top_id == case["expected_top_candidate_id"])
        case_passed = all(checks)
        passed += int(case_passed)
        results.append({"id": case["id"], "passed": case_passed, "latency_ms": latency_ms, "result": result})

    report = {
        "schema_version": "entity-resolution-evaluation-v1",
        "case_set_version": case_set["version"],
        "model": resolver.config["model"],
        "total": len(results),
        "passed": passed,
        "false_accepted_hard_filters": false_hard_filters,
        "max_latency_ms": max(latencies, default=0),
        "results": results,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.report.with_suffix(args.report.suffix + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(args.report)
    print(json.dumps({key: report[key] for key in ("total", "passed", "false_accepted_hard_filters", "max_latency_ms")}, ensure_ascii=False))
    return 0 if passed == len(results) and false_hard_filters == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
