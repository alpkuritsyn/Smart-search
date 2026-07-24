#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: validate_catalog.py <catalog.json>", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    raw = path.read_bytes()
    try:
        records = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"invalid UTF-8 JSON: {exc}")
        return 1

    if not isinstance(records, list):
        fail("catalog root must be a JSON array")
        return 1

    errors: list[str] = []
    warnings: list[str] = []
    ids: list[str] = []
    sku_counter: Counter[str] = Counter()
    url_counter: Counter[str] = Counter()
    missing = Counter()

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"record[{index}] is not an object")
            continue
        product_id = record.get("id")
        if product_id in (None, ""):
            errors.append(f"record[{index}] has no id")
        else:
            ids.append(str(product_id))
        for field in ("name", "category", "subcategory"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                errors.append(f"record[{index}] has empty {field}")
        for field in ("brand", "sku", "price", "url", "image"):
            if record.get(field) in (None, ""):
                missing[field] += 1
        sku = str(record.get("sku") or "").strip().casefold()
        url = str(record.get("url") or "").strip().casefold()
        if sku:
            sku_counter[sku] += 1
        if url:
            url_counter[url] += 1

    duplicate_ids = [value for value, count in Counter(ids).items() if count > 1]
    if duplicate_ids:
        errors.append(f"duplicate ids: {len(duplicate_ids)}")
    duplicate_skus = sum(1 for count in sku_counter.values() if count > 1)
    duplicate_urls = sum(1 for count in url_counter.values() if count > 1)
    if duplicate_skus:
        warnings.append(f"duplicate non-empty SKU groups: {duplicate_skus}")
    if duplicate_urls:
        warnings.append(f"duplicate non-empty URL groups: {duplicate_urls}")

    sha256 = hashlib.sha256(raw).hexdigest()
    print(f"records={len(records)}")
    print(f"sha256={sha256}")
    print(f"missing={dict(sorted(missing.items()))}")
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors[:50]:
        fail(error)
    if len(errors) > 50:
        fail(f"... and {len(errors) - 50} more")
    print("status=PASS" if not errors else "status=FAIL")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
