#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: validate_frontend_fixture.py <fixture.json> [...]", file=sys.stderr)
        return 2
    errors: list[str] = []
    for raw_path in sys.argv[1:]:
        path = Path(raw_path)
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        query = data.get("query")
        primary = data.get("primary")
        meta = data.get("meta")
        if not isinstance(query, dict) or not query.get("raw") or not query.get("normalized"):
            errors.append(f"{path}: invalid query")
        if not isinstance(primary, dict) or not isinstance(primary.get("products"), list):
            errors.append(f"{path}: invalid primary")
        if not isinstance(meta, dict) or not meta.get("strategy"):
            errors.append(f"{path}: invalid meta")

        seen: set[str] = set()
        groups = [primary] + list(data.get("complements") or []) if isinstance(primary, dict) else []
        for group_index, group in enumerate(groups):
            products = group.get("products") if isinstance(group, dict) else None
            if not isinstance(products, list):
                errors.append(f"{path}: group[{group_index}] products is not an array")
                continue
            if group_index > 0:
                if not group.get("relation") or not group.get("rationale"):
                    errors.append(f"{path}: complement[{group_index - 1}] misses relation/rationale")
                if not products and not group.get("data_gap"):
                    errors.append(f"{path}: empty complement must be omitted or marked data_gap")
            for product in products:
                product_id = str(product.get("id", ""))
                if not product_id or not product.get("name"):
                    errors.append(f"{path}: product without id/name")
                if product_id in seen:
                    errors.append(f"{path}: duplicate product id {product_id}")
                seen.add(product_id)
        print(f"{path}: products={len(seen)}")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    print("status=PASS" if not errors else "status=FAIL")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
