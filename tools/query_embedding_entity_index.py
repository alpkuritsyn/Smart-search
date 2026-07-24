#!/usr/bin/env python3
"""Query a local Smart-search embedding entity index without exposing vectors."""

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.ml.embedding_resolver import EmbeddingEntityResolver


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("text", help="Brand or product-name span to resolve")
    parser.add_argument("--entity-type", choices=("brand", "product_name"), required=True)
    parser.add_argument(
        "--index",
        type=Path,
        default=BASE_DIR / "data/embeddings/entities.current-canonical.sqlite",
    )
    parser.add_argument("--config", type=Path, default=BASE_DIR / "config/embedding_resolver.json")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    resolver = EmbeddingEntityResolver(config_path=args.config, index_path=args.index)
    result = resolver.resolve(args.text, args.entity_type, top_k=max(1, args.top_k))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"status={result['status']} entity={result['entity_id']} "
            f"score={result['score']} margin={result['margin']}"
        )
        for number, candidate in enumerate(result.get("candidates", []), start=1):
            print(
                f"{number}. {candidate['display']} [{candidate['entity_id']}] "
                f"hybrid={candidate['score']} embedding={candidate['embedding_score']} "
                f"character={candidate['character_score']} "
                f"transliteration={candidate['transliteration_score']}"
            )
    return 0 if result["status"] != "unavailable" else 2


if __name__ == "__main__":
    raise SystemExit(main())
