#!/usr/bin/env python3
"""Validate completeness and provenance of the published entity embedding index."""

import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, default=BASE_DIR / "data/embeddings/entities.sqlite")
    parser.add_argument("--catalog", type=Path, default=BASE_DIR / "data/canonical/catalog.canonical.json")
    parser.add_argument("--aliases", type=Path, default=BASE_DIR / "config/search_aliases.json")
    parser.add_argument("--config", type=Path, default=BASE_DIR / "config/embedding_resolver.json")
    args = parser.parse_args()

    if not args.index.exists():
        print(f"FAIL: missing index: {args.index}")
        return 2
    config = json.loads(args.config.read_text(encoding="utf-8"))
    with closing(sqlite3.connect(args.index)) as connection:
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        counts = dict(connection.execute("SELECT entity_type, COUNT(*) FROM entity_phrases GROUP BY entity_type"))
        dimensions = [row[0] for row in connection.execute("SELECT DISTINCT dimension FROM entity_phrases")]
        duplicates = connection.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT entity_type, entity_id, normalized_phrase, COUNT(*) AS n
              FROM entity_phrases GROUP BY entity_type, entity_id, normalized_phrase HAVING n > 1
            )
            """
        ).fetchone()[0]

    failures = []
    expected = {
        "status": "complete",
        "model": config["model"],
        "catalog_sha256": sha256(args.catalog),
        "aliases_sha256": sha256(args.aliases),
        "config_sha256": sha256(args.config),
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            failures.append(f"{key}: expected {value}, got {metadata.get(key)}")
    actual_count = sum(counts.values())
    if actual_count != int(metadata.get("expected_phrase_count", "-1")):
        failures.append("phrase count does not match expected_phrase_count")
    if not counts.get("brand") or not counts.get("product_type") or not counts.get("product_name"):
        failures.append("brand, product_type and product_name phrases are required")
    if len(dimensions) != 1 or dimensions[0] <= 0:
        failures.append(f"invalid dimensions: {dimensions}")
    if duplicates:
        failures.append(f"duplicate phrase rows: {duplicates}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(
        f"PASS model={metadata['model']} dimension={dimensions[0]} "
        f"brand_phrases={counts['brand']} product_type_phrases={counts['product_type']} "
        f"product_phrases={counts['product_name']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
