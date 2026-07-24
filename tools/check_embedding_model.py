#!/usr/bin/env python3
"""Verify exact local Ollama embedding tag and perform a smoke embedding."""

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.ml.embedding_resolver import OllamaEmbeddingClient


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="qwen3-embedding:0.6b")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    client = OllamaEmbeddingClient(args.base_url, args.model, args.timeout)
    try:
        installed = client.installed_models()
    except Exception as exc:
        print(f"FAIL: Ollama API unavailable at {args.base_url}: {type(exc).__name__}: {exc}")
        return 2
    if args.model not in installed:
        print(f"FAIL: exact model tag is not installed: {args.model}")
        print(f"Install after user approval: ollama pull {args.model}")
        return 3

    try:
        vectors = client.embed(["Тикула", "Tikkurila"])
    except Exception as exc:
        print(f"FAIL: /api/embed smoke failed: {type(exc).__name__}: {exc}")
        return 4
    if len(vectors) != 2 or not vectors[0] or len(vectors[0]) != len(vectors[1]):
        print("FAIL: unexpected embedding response shape")
        return 5
    print(f"PASS model={args.model} vectors=2 dimension={len(vectors[0])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

