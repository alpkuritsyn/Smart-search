import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.ml.embedding_resolver import EmbeddingEntityResolver, normalize_entity_text, transliterate


def write_fixture(tmp_path: Path):
    config = {
        "version": "test-index",
        "base_url": "http://127.0.0.1:1",
        "model": "qwen3-embedding:0.6b",
        "timeout_seconds": 1,
        "entity_types": ["brand", "product_type", "product_name"],
        "weights": {"embedding": 0.65, "character": 0.25, "transliteration": 0.10},
        "decision_policy": {
            "brand": {"minimum_score": 0.88, "minimum_margin_over_second": 0.08, "auto_resolve": True},
            "product_type": {"minimum_score": 0.82, "minimum_margin_over_second": 0.06, "auto_resolve": True},
            "product_name": {"minimum_score": 0.92, "minimum_margin_over_second": 0.10, "auto_resolve": True},
        },
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    index_path = tmp_path / "entities.sqlite"
    with closing(sqlite3.connect(index_path)) as connection:
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            [("status", "complete"), ("model", config["model"]), ("index_version", config["version"])],
        )
        connection.execute(
            """
            CREATE TABLE entity_phrases (
                entity_type TEXT, entity_id TEXT, display TEXT, normalized_phrase TEXT,
                trusted INTEGER, vector BLOB, dimension INTEGER
            )
            """
        )
        connection.execute(
            "INSERT INTO entity_phrases VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("brand", "brand:tikkurila", "Tikkurila", "тикурила", 1, b"", 0),
        )
        connection.execute(
            "INSERT INTO entity_phrases VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("product_type", "type:putty", "шпаклёвка", "шпаклевка", 1, b"", 0),
        )
        connection.commit()
    return config_path, index_path


class EmbeddingResolverTests(unittest.TestCase):
    def test_normalization_and_transliteration(self):
        self.assertEqual(normalize_entity_text("  ТИКУРИЛА! "), "тикурила")
        self.assertEqual(transliterate("Тикурила"), "tikurila")

    def test_exact_alias_does_not_call_ollama(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            config_path, index_path = write_fixture(tmp_path)
            resolver = EmbeddingEntityResolver(
                config_path,
                index_path,
                catalog_path=tmp_path / "catalog.missing.json",
                aliases_path=tmp_path / "aliases.missing.json",
            )
            result = resolver.resolve("ТИКУРИЛА", "brand")
            self.assertEqual(result["status"], "exact")
            self.assertEqual(result["entity_id"], "brand:tikkurila")

    def test_missing_index_is_safe_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            config_path, _ = write_fixture(tmp_path)
            resolver = EmbeddingEntityResolver(
                config_path,
                tmp_path / "missing.sqlite",
                catalog_path=tmp_path / "catalog.missing.json",
                aliases_path=tmp_path / "aliases.missing.json",
            )
            result = resolver.resolve("Тикула", "brand")
            self.assertEqual(result["status"], "unavailable")
            self.assertIsNone(result["entity_id"])

    def test_exact_product_type_alias_does_not_call_ollama(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            config_path, index_path = write_fixture(tmp_path)
            resolver = EmbeddingEntityResolver(
                config_path,
                index_path,
                catalog_path=tmp_path / "catalog.missing.json",
                aliases_path=tmp_path / "aliases.missing.json",
            )
            result = resolver.resolve("ШПАКЛЕВКА", "product_type")
            self.assertEqual(result["status"], "exact")
            self.assertEqual(result["entity_id"], "type:putty")
            self.assertEqual(result["display"], "шпаклёвка")


if __name__ == "__main__":
    unittest.main()
