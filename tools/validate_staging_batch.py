#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit


BASE_DIR = Path(__file__).resolve().parent.parent
REQUIRED_SOURCE_FIELDS = (
    "source_id",
    "source_url",
    "retrieved_at",
    "locator",
    "content_sha256",
    "raw_snapshot",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--require-new", action="store_true")
    parser.add_argument("--require-complete", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = json.loads(args.batch.read_text(encoding="utf-8-sig"))
    if not isinstance(records, list):
        print("ERROR: staging batch must be an array", file=sys.stderr)
        return 1

    errors: list[str] = []
    keys: list[str] = []
    urls: list[str] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"record[{index}] is not an object")
            continue
        key = record.get("source_product_key")
        if not isinstance(key, str) or not key.strip():
            errors.append(f"record[{index}] missing source_product_key")
        else:
            keys.append(key)
        raw = record.get("raw")
        if not isinstance(raw, dict):
            errors.append(f"record[{index}] missing raw object")
        source = record.get("source")
        if not isinstance(source, dict):
            errors.append(f"record[{index}] missing source object")
            continue
        for field in REQUIRED_SOURCE_FIELDS:
            if not isinstance(source.get(field), str) or not source[field].strip():
                errors.append(f"record[{index}] source missing {field}")

        source_url = str(source.get("source_url") or "")
        parsed_url = urlsplit(source_url)
        if parsed_url.scheme != "https" or parsed_url.netloc.casefold() != "remplanika.ru":
            errors.append(f"record[{index}] source_url is not a public Remplanika URL")
        else:
            urls.append(source_url)
        snapshot = str(source.get("raw_snapshot") or "")
        snapshot_path = (BASE_DIR / snapshot).resolve()
        try:
            snapshot_path.relative_to(BASE_DIR.resolve())
        except ValueError:
            errors.append(f"record[{index}] raw_snapshot escapes project root")
        else:
            if not snapshot_path.is_file():
                errors.append(f"record[{index}] raw_snapshot does not exist: {snapshot}")

    duplicate_keys = [key for key, count in Counter(keys).items() if count > 1]
    duplicate_urls = [url for url, count in Counter(urls).items() if count > 1]
    if duplicate_keys:
        errors.append(f"duplicate source_product_key values: {len(duplicate_keys)}")
    if duplicate_urls:
        errors.append(f"duplicate source_url values: {len(duplicate_urls)}")

    report = None
    if args.report:
        if not args.report.is_file():
            errors.append(f"ingestion report not found: {args.report}")
        else:
            report = json.loads(args.report.read_text(encoding="utf-8-sig"))
            if report.get("synthetic_rows_allowed") is not False:
                errors.append("ingestion report does not prohibit synthetic rows")
            if int(report.get("fetched_pages") or 0) <= 0:
                errors.append("ingestion report has no fetched pages")
            if int(report.get("parsed_products") or 0) <= 0:
                errors.append("ingestion report has no parsed products")
            if args.require_new and int(report.get("new_unique_products") or 0) <= 0:
                errors.append("ingestion produced zero new unique products")
            if int(report.get("staging_total") or -1) != len(records):
                errors.append("ingestion report staging_total does not match batch length")
            if args.require_complete:
                if report.get("full_run") is not True:
                    errors.append("ingestion report is a bounded run, not a complete discovery run")
                if report.get("catalog_scope") != "full_catalog" or report.get("catalog_scope_complete") is not True:
                    errors.append("ingestion report does not cover the full /catalog/ source scope")
                if report.get("manifest_complete") is not True:
                    errors.append("ingestion report has an incomplete catalog manifest")
                manifest_relative = report.get("discovery_manifest")
                if not isinstance(manifest_relative, str) or not manifest_relative:
                    errors.append("ingestion report does not reference a discovery manifest")
                else:
                    manifest_path = (BASE_DIR / manifest_relative).resolve()
                    try:
                        manifest_path.relative_to(BASE_DIR.resolve())
                    except ValueError:
                        errors.append("discovery manifest escapes project root")
                    else:
                        if not manifest_path.is_file():
                            errors.append("discovery manifest file does not exist")
                        else:
                            manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
                            if report.get("discovery_manifest_sha256") != manifest_hash:
                                errors.append("discovery manifest SHA-256 does not match report")
                            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
                            manifest_count = sum(
                                len(source.get("selected_urls") or [])
                                for source in manifest.get("sources") or []
                            )
                            if int(report.get("manifest_candidates") or -1) != manifest_count:
                                errors.append("discovery manifest candidate count does not match report")
                threshold = float(report.get("minimum_parse_success_pct") or 95)
                for source_report in report.get("sources") or []:
                    if source_report.get("catalog_scope") != "full_catalog":
                        errors.append(f"source {source_report.get('source_id')} is not marked full_catalog")
                    if source_report.get("allowed_paths") != ["/catalog/"]:
                        errors.append(f"source {source_report.get('source_id')} does not cover exactly /catalog/")
                    if source_report.get("manifest_complete") is not True:
                        errors.append(f"source {source_report.get('source_id')} manifest is incomplete")
                    if int(source_report.get("attempted_candidates") or -1) != int(
                        source_report.get("selected_candidates") or -2
                    ):
                        errors.append(f"source {source_report.get('source_id')} did not attempt the full selected manifest")
                    if int(source_report.get("sitemap_urls_seen") or 0) <= 0:
                        errors.append(f"source {source_report.get('source_id')} did not read sitemap URLs")
                    if int(source_report.get("selected_candidates") or 0) <= 0:
                        errors.append(f"source {source_report.get('source_id')} selected zero catalog candidates")
                    if float(source_report.get("parse_success_pct") or 0) < threshold:
                        errors.append(
                            f"source {source_report.get('source_id')} parse success "
                            f"{source_report.get('parse_success_pct')}% is below {threshold}%"
                        )

    for error in errors[:50]:
        print(f"ERROR: {error}", file=sys.stderr)
    print(f"records={len(records)}")
    if report:
        print(
            f"fetched={report.get('fetched_pages', 0)} "
            f"parsed={report.get('parsed_products', 0)} "
            f"new_unique={report.get('new_unique_products', 0)}"
        )
    print("status=PASS" if not errors else "status=FAIL")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
