#!/usr/bin/env python3
"""Exact-first hybrid resolver over a locally built Ollama embedding index."""

from __future__ import annotations

import json
import hashlib
import math
import os
import re
import sqlite3
import unicodedata
import urllib.error
import urllib.request
import threading
from urllib.parse import urlparse
from array import array
from contextlib import closing
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config" / "embedding_resolver.json"
DEFAULT_INDEX_PATH = BASE_DIR / "data" / "embeddings" / "entities.sqlite"
DEFAULT_CATALOG_PATH = BASE_DIR / "data" / "canonical" / "catalog.canonical.json"
DEFAULT_ALIASES_PATH = BASE_DIR / "config" / "search_aliases.json"

_CYRILLIC_TO_LATIN = str.maketrans(
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l",
        "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s",
        "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch",
        "ш": "sh", "щ": "shch", "ы": "y", "э": "e", "ю": "yu", "я": "ya",
        "ь": "", "ъ": "",
    }
)


def normalize_entity_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").lower().replace("ё", "е")
    text = re.sub(r"[^\w\s-]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def transliterate(value: str) -> str:
    return normalize_entity_text(value).translate(_CYRILLIC_TO_LATIN)


def _ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _normalize_vector(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    if not norm:
        return values
    return [value / norm for value in values]


def _dot(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError(f"Embedding dimension mismatch: {len(left)} != {len(right)}")
    return sum(a * b for a, b in zip(left, right))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class OllamaEmbeddingClient:
    def __init__(self, base_url: str, model: str, timeout_seconds: int = 20, keep_alive: int | str = -1):
        self.base_url = base_url.rstrip("/")
        hostname = (urlparse(self.base_url).hostname or "").lower()
        if hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Embedding provider must be a loopback Ollama endpoint")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.keep_alive = keep_alive

    def installed_models(self) -> set[str]:
        request = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.load(response)
        names: set[str] = set()
        for item in payload.get("models", []):
            if item.get("name"):
                names.add(item["name"])
            if item.get("model"):
                names.add(item["model"])
        return names

    def embed(self, inputs: str | list[str]) -> list[list[float]]:
        body = json.dumps({"model": self.model, "input": inputs}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/embed",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.load(response)
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list) or not embeddings:
            raise RuntimeError("Ollama /api/embed returned no embeddings")
        return [[float(value) for value in vector] for vector in embeddings]


class EmbeddingEntityResolver:
    """Resolve one already-extracted span; caller owns span extraction and hard filters."""

    def __init__(
        self,
        config_path: Path | str = DEFAULT_CONFIG_PATH,
        index_path: Path | str = DEFAULT_INDEX_PATH,
        catalog_path: Path | str = DEFAULT_CATALOG_PATH,
        aliases_path: Path | str = DEFAULT_ALIASES_PATH,
    ):
        self.config_path = Path(config_path)
        self.index_path = Path(index_path)
        self.catalog_path = Path(catalog_path)
        self.aliases_path = Path(aliases_path)
        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        keep_alive_val = os.environ.get(
            "ENTITY_EMBEDDING_KEEP_ALIVE",
            self.config.get("keep_alive", "5m"),
        )
        self.client = OllamaEmbeddingClient(
            self.config["base_url"],
            self.config["model"],
            int(self.config.get("timeout_seconds", 20)),
            keep_alive_val,
        )
        self._embedding_cache: dict[str, list[float]] = {}
        self._embedding_cache_lock = threading.Lock()

    def _embed_once(self, normalized: str) -> list[float]:
        """Reuse one query vector when the same span is compared across entity types."""
        with self._embedding_cache_lock:
            cached = self._embedding_cache.get(normalized)
        if cached is not None:
            return cached
        vector = _normalize_vector(self.client.embed(normalized)[0])
        with self._embedding_cache_lock:
            if len(self._embedding_cache) >= 128:
                self._embedding_cache.clear()
            self._embedding_cache[normalized] = vector
        return vector

    def _unavailable(self, text: str, entity_type: str, reason: str) -> dict[str, Any]:
        return {
            "status": "unavailable",
            "entity_type": entity_type,
            "matched_text": text,
            "entity_id": None,
            "display": None,
            "score": None,
            "margin": None,
            "reason": reason,
            "candidates": [],
            "model": self.config.get("model"),
            "index_version": None,
        }

    def resolve(self, text: str, entity_type: str, top_k: int = 5) -> dict[str, Any]:
        if entity_type not in set(self.config.get("entity_types", [])):
            raise ValueError(f"Unsupported entity_type: {entity_type}")
        if os.getenv("SMART_SEARCH_EMBEDDING_RESOLUTION", "1").strip().lower() in {"0", "false", "off"}:
            return self._unavailable(text, entity_type, "feature_disabled")
        if not self.index_path.exists():
            return self._unavailable(text, entity_type, "index_missing")

        normalized = normalize_entity_text(text)
        if not normalized:
            return self._unavailable(text, entity_type, "empty_span")

        try:
            with closing(sqlite3.connect(self.index_path)) as connection:
                metadata = dict(connection.execute("SELECT key, value FROM metadata"))
                if metadata.get("status") != "complete":
                    return self._unavailable(text, entity_type, "index_incomplete")
                if metadata.get("model") != self.config.get("model"):
                    return self._unavailable(text, entity_type, "model_index_mismatch")
                if self.catalog_path.exists() and metadata.get("catalog_sha256") != _sha256(self.catalog_path):
                    return self._unavailable(text, entity_type, "stale_catalog_index")
                if self.aliases_path.exists() and metadata.get("aliases_sha256") != _sha256(self.aliases_path):
                    return self._unavailable(text, entity_type, "stale_aliases_index")
                if metadata.get("config_sha256") and metadata.get("config_sha256") != _sha256(self.config_path):
                    return self._unavailable(text, entity_type, "stale_config_index")

                exact = connection.execute(
                    """
                    SELECT entity_id, display
                    FROM entity_phrases
                    WHERE entity_type = ? AND normalized_phrase = ?
                    ORDER BY trusted DESC, entity_id
                    LIMIT 2
                    """,
                    (entity_type, normalized),
                ).fetchall()
                unique_exact = {(row[0], row[1]) for row in exact}
                if len(unique_exact) == 1:
                    entity_id, display = next(iter(unique_exact))
                    return {
                        "status": "exact",
                        "entity_type": entity_type,
                        "matched_text": text,
                        "entity_id": entity_id,
                        "display": display,
                        "score": 1.0,
                        "margin": 1.0,
                        "reason": "exact_canonical_or_alias_match",
                        "candidates": [],
                        "model": self.config.get("model"),
                        "index_version": metadata.get("index_version"),
                    }

                rows = connection.execute(
                    """
                    SELECT entity_id, display, normalized_phrase, vector, dimension, trusted
                    FROM entity_phrases
                    WHERE entity_type = ?
                    """,
                    (entity_type,),
                ).fetchall()
        except (sqlite3.Error, OSError) as exc:
            return self._unavailable(text, entity_type, f"index_error:{type(exc).__name__}")

        try:
            query_vector = self._embed_once(normalized)
        except (OSError, RuntimeError, ValueError, urllib.error.URLError) as exc:
            return self._unavailable(text, entity_type, f"ollama_error:{type(exc).__name__}")

        weights = self.config["weights"]
        aggregate: dict[str, dict[str, Any]] = {}
        transliterated_query = transliterate(normalized)
        for entity_id, display, phrase, vector_blob, dimension, trusted in rows:
            vector_array = array("f")
            vector_array.frombytes(vector_blob)
            vector = list(vector_array)
            if len(vector) != dimension or len(vector) != len(query_vector):
                continue
            embedding_score = max(0.0, min(1.0, _dot(query_vector, vector)))
            character_score = _ratio(normalized, phrase)
            transliteration_score = _ratio(transliterated_query, transliterate(phrase))
            score = (
                float(weights["embedding"]) * embedding_score
                + float(weights["character"]) * character_score
                + float(weights["transliteration"]) * transliteration_score
            )
            candidate = {
                "entity_id": entity_id,
                "display": display,
                "score": round(max(0.0, min(1.0, score)), 6),
                "embedding_score": round(embedding_score, 6),
                "character_score": round(character_score, 6),
                "transliteration_score": round(transliteration_score, 6),
                "trusted": bool(trusted),
            }
            previous = aggregate.get(entity_id)
            if previous is None or candidate["score"] > previous["score"]:
                aggregate[entity_id] = candidate

        ranked = sorted(aggregate.values(), key=lambda item: (-item["score"], item["entity_id"]))
        ranked = ranked[: max(2, top_k)]
        if not ranked:
            return self._unavailable(text, entity_type, "no_compatible_vectors")

        best = ranked[0]
        second_score = ranked[1]["score"] if len(ranked) > 1 else 0.0
        margin = round(max(0.0, best["score"] - second_score), 6)
        policy = self.config["decision_policy"][entity_type]
        passes_score = best["score"] >= float(policy["minimum_score"])
        passes_margin = margin >= float(policy["minimum_margin_over_second"])
        can_resolve = bool(policy.get("auto_resolve", False)) and bool(best["trusted"])

        if passes_score and passes_margin and can_resolve:
            status = "resolved"
            entity_id = best["entity_id"]
            display = best["display"]
            reason = "score_and_margin_passed"
        elif passes_score and not passes_margin:
            status = "ambiguous"
            entity_id = None
            display = None
            reason = "margin_below_threshold"
        else:
            status = "suggestion"
            entity_id = None
            display = None
            reason = "auto_resolution_gate_not_passed"

        public_candidates = [
            {key: value for key, value in candidate.items() if key != "trusted"}
            for candidate in ranked[:top_k]
        ]
        return {
            "status": status,
            "entity_type": entity_type,
            "matched_text": text,
            "entity_id": entity_id,
            "display": display,
            "score": best["score"],
            "margin": margin,
            "reason": reason,
            "candidates": public_candidates,
            "model": self.config.get("model"),
            "index_version": metadata.get("index_version"),
        }
