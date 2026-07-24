#!/usr/bin/env python3
"""Build a resumable SQLite embedding index from accepted canonical artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sqlite3
import sys
from array import array
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.ml.embedding_resolver import OllamaEmbeddingClient, normalize_entity_text


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_vector(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    if not norm:
        raise ValueError("Ollama returned a zero embedding")
    return [value / norm for value in values]


def collect_entities(catalog: list[dict], aliases: dict) -> list[tuple[str, str, str, str, int]]:
    rows: set[tuple[str, str, str, str, int]] = set()
    for brand in aliases.get("brands", []):
        entity_id = str(brand["id"])
        display = str(brand["display"])
        phrases = set(brand.get("aliases", [])) | {display}
        if brand.get("catalog_value"):
            phrases.add(str(brand["catalog_value"]))
        for phrase in phrases:
            normalized = normalize_entity_text(str(phrase))
            if normalized:
                rows.add(("brand", entity_id, display, normalized, 1))

    for product_type in aliases.get("product_types", []):
        entity_id = str(product_type["id"])
        display = str(product_type["display"])
        phrases = set(product_type.get("aliases", [])) | {display}
        for phrase in phrases:
            normalized = normalize_entity_text(str(phrase))
            if normalized:
                rows.add(("product_type", entity_id, display, normalized, 1))

    for product in catalog:
        product_id = product.get("id")
        name = str(product.get("name") or "").strip()
        if product_id is None or not name:
            continue
        normalized = normalize_entity_text(name)
        if normalized:
            rows.add(("product_name", str(product_id), name, normalized, 1))
    return sorted(rows)


def reuse_existing_vectors(
    connection: sqlite3.Connection,
    reuse_path: Path | None,
    rows: list[tuple[str, str, str, str, int]],
    expected_model: str,
) -> int:
    """Copy vectors whose model, entity and normalized phrase are unchanged."""
    if reuse_path is None or not reuse_path.exists():
        return 0
    wanted = {(row[0], row[1], row[3]): row for row in rows}
    reused = 0
    with sqlite3.connect(reuse_path) as source:
        metadata = dict(source.execute("SELECT key, value FROM metadata"))
        if metadata.get("model") != expected_model or metadata.get("status") != "complete":
            return 0
        for entity_type, entity_id, _display, phrase, _trusted, vector, dimension in source.execute(
            """
            SELECT entity_type, entity_id, display, normalized_phrase, trusted, vector, dimension
            FROM entity_phrases
            """
        ):
            desired = wanted.get((entity_type, entity_id, phrase))
            if desired is None:
                continue
            _, _, display, _, trusted = desired
            connection.execute(
                """
                INSERT OR REPLACE INTO entity_phrases
                (entity_type, entity_id, display, normalized_phrase, trusted, vector, dimension)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (entity_type, entity_id, display, phrase, trusted, vector, dimension),
            )
            reused += 1
    connection.commit()
    return reused


def prepare_database(path: Path, expected: dict[str, str]) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS entity_phrases (
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            display TEXT NOT NULL,
            normalized_phrase TEXT NOT NULL,
            trusted INTEGER NOT NULL,
            vector BLOB NOT NULL,
            dimension INTEGER NOT NULL,
            PRIMARY KEY (entity_type, entity_id, normalized_phrase)
        )
        """
    )
    existing = dict(connection.execute("SELECT key, value FROM metadata"))
    identity_keys = {"model", "catalog_sha256", "aliases_sha256", "config_sha256"}
    if existing and any(existing.get(key) != expected[key] for key in identity_keys):
        connection.close()
        path.unlink()
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute(
            """
            CREATE TABLE entity_phrases (
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                display TEXT NOT NULL,
                normalized_phrase TEXT NOT NULL,
                trusted INTEGER NOT NULL,
                vector BLOB NOT NULL,
                dimension INTEGER NOT NULL,
                PRIMARY KEY (entity_type, entity_id, normalized_phrase)
            )
            """
        )
    for key, value in expected.items():
        connection.execute("INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)", (key, value))
    connection.execute("INSERT OR REPLACE INTO metadata(key, value) VALUES ('status', 'building')")
    connection.commit()
    return connection


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=BASE_DIR / "data/canonical/catalog.canonical.json")
    parser.add_argument("--aliases", type=Path, default=BASE_DIR / "config/search_aliases.json")
    parser.add_argument("--config", type=Path, default=BASE_DIR / "config/embedding_resolver.json")
    parser.add_argument("--output", type=Path, default=BASE_DIR / "data/embeddings/entities.sqlite")
    parser.add_argument(
        "--reuse-index",
        type=Path,
        help="Reuse compatible vectors from a complete index built with the same model",
    )
    parser.add_argument("--limit", type=int, help="Smoke only; resulting index is marked incomplete")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    aliases = json.loads(args.aliases.read_text(encoding="utf-8"))
    rows = collect_entities(catalog, aliases)
    total_rows = len(rows)
    if args.limit is not None:
        rows = rows[: max(0, args.limit)]

    expected = {
        "index_version": config["version"],
        "model": config["model"],
        "catalog_sha256": sha256(args.catalog),
        "aliases_sha256": sha256(args.aliases),
        "config_sha256": sha256(args.config),
        "expected_phrase_count": str(total_rows),
        "limited": "true" if args.limit is not None else "false",
    }
    building_path = args.output.with_name(args.output.stem + ".building" + args.output.suffix)
    connection = prepare_database(building_path, expected)
    reused = reuse_existing_vectors(connection, args.reuse_index, rows, config["model"])
    if reused:
        print(f"reused {reused}/{len(rows)} vectors from {args.reuse_index}")
    existing = {
        (row[0], row[1], row[2])
        for row in connection.execute("SELECT entity_type, entity_id, normalized_phrase FROM entity_phrases")
    }
    pending = [row for row in rows if (row[0], row[1], row[3]) not in existing]

    client = OllamaEmbeddingClient(
        config["base_url"], config["model"], int(config.get("timeout_seconds", 20))
    )
    installed = client.installed_models()
    if config["model"] not in installed:
        print(f"FAIL: exact model tag is not installed: {config['model']}")
        print(f"Install after user approval: ollama pull {config['model']}")
        connection.close()
        return 3

    batch_size = int(config.get("batch_size", 64))
    done = len(existing)
    for offset in range(0, len(pending), batch_size):
        batch = pending[offset : offset + batch_size]
        vectors = client.embed([row[3] for row in batch])
        if len(vectors) != len(batch):
            raise RuntimeError("Ollama returned a different number of vectors than inputs")
        for row, values in zip(batch, vectors):
            entity_type, entity_id, display, phrase, trusted = row
            vector = normalized_vector(values)
            vector_blob = array("f", vector).tobytes()
            connection.execute(
                """
                INSERT OR REPLACE INTO entity_phrases
                (entity_type, entity_id, display, normalized_phrase, trusted, vector, dimension)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (entity_type, entity_id, display, phrase, trusted, vector_blob, len(vector)),
            )
        done += len(batch)
        connection.execute("INSERT OR REPLACE INTO metadata(key, value) VALUES ('completed_phrase_count', ?)", (str(done),))
        connection.commit()
        print(f"embedded {done}/{len(rows)}")

    is_complete = args.limit is None and len(rows) == total_rows
    connection.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES ('status', ?)",
        ("complete" if is_complete else "smoke_incomplete",),
    )
    connection.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES ('completed_phrase_count', ?)",
        (str(len(rows)),),
    )
    connection.commit()
    connection.close()

    if is_complete:
        current_hashes = {
            "catalog_sha256": sha256(args.catalog),
            "aliases_sha256": sha256(args.aliases),
            "config_sha256": sha256(args.config),
        }
        if any(current_hashes[key] != expected[key] for key in current_hashes):
            print("FAIL: source artifacts changed during index build; checkpoint retained, index not published")
            return 4
        args.output.parent.mkdir(parents=True, exist_ok=True)
        os.replace(building_path, args.output)
        print(f"PASS published={args.output} phrases={len(rows)}")
    else:
        print(f"SMOKE checkpoint={building_path} phrases={len(rows)}/{total_rows}; release index not published")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
