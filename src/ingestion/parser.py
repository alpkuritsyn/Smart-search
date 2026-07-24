#!/usr/bin/env python3
"""Live, provenance-first ingestion for the public Remplanika catalog.

The parser discovers product candidates from the site's published sitemap,
checks robots.txt, downloads allowed public product pages, stores compressed raw
HTML and writes deterministic staging records. It deliberately has no embedded
product fixtures or guessed catalog values.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import hashlib
import html as html_module
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config" / "parser_sources.json"
STAGING_PATH = BASE_DIR / "data" / "staging" / "staged_products.json"
ERRORS_PATH = BASE_DIR / "data" / "staging" / "parser_errors.json"
MANIFEST_PATH = BASE_DIR / "data" / "staging" / "parser_discovery_manifest.json"
RAW_DIR = BASE_DIR / "data" / "raw" / "remplanika"
REPORT_PATH = BASE_DIR / "reports" / "parser-ingestion.json"
CHECKPOINT_REPORT_PATH = BASE_DIR / "reports" / "parser-ingestion.checkpoint.json"
LOCK_PATH = BASE_DIR / "data" / "staging" / ".parser.lock"


class IngestionError(RuntimeError):
    pass


class GlobalRateLimiter:
    """Spaces request starts across all worker threads."""

    def __init__(self, requests_per_second: float) -> None:
        if requests_per_second <= 0:
            raise IngestionError("requests_per_second must be positive")
        self._interval = 1 / requests_per_second
        self._next_request_at = 0.0
        self._lock = threading.Lock()

    def wait_for_turn(self) -> None:
        with self._lock:
            now = time.monotonic()
            request_at = max(now, self._next_request_at)
            self._next_request_at = request_at + self._interval
        wait_seconds = request_at - now
        if wait_seconds > 0:
            time.sleep(wait_seconds)


def ordered_parallel_map(executor, worker, values, max_in_flight: int):
    """Yield worker results in input order while keeping a bounded work queue."""
    value_iter = iter(values)
    pending: list[concurrent.futures.Future[Any]] = []
    for _ in range(max_in_flight):
        try:
            pending.append(executor.submit(worker, next(value_iter)))
        except StopIteration:
            break
    while pending:
        future = pending.pop(0)
        yield future.result()
        try:
            pending.append(executor.submit(worker, next(value_iter)))
        except StopIteration:
            pass


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def fetch_bytes(url: str, user_agent: str, timeout: float, retries: int) -> tuple[bytes, str, int]:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": user_agent,
                    "Accept": "text/html,application/xml;q=0.9,*/*;q=0.5",
                    "Accept-Encoding": "gzip",
                    "Connection": "close",
                },
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
                if response.headers.get("Content-Encoding", "").casefold() == "gzip":
                    body = gzip.decompress(body)
                return body, response.geturl(), int(response.status)
        except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(min(2**attempt, 4))
    raise IngestionError(f"fetch failed for {url}: {last_error}")


def build_robots_policy(base_url: str, user_agent: str, timeout: float, retries: int) -> urllib.robotparser.RobotFileParser:
    robots_url = urllib.parse.urljoin(base_url, "/robots.txt")
    body, _, status = fetch_bytes(robots_url, user_agent, timeout, retries)
    if status != 200:
        raise IngestionError(f"robots.txt returned HTTP {status}")
    parser = urllib.robotparser.RobotFileParser(robots_url)
    parser.parse(body.decode("utf-8", errors="replace").splitlines())
    return parser


def extract_sitemap_urls(payload: bytes) -> list[str]:
    """Tolerate the site's historically malformed XML while reading only loc tags."""
    text = payload.decode("utf-8", errors="replace")
    return [
        html_module.unescape(match.strip())
        for match in re.findall(r"<loc>(.*?)</loc>", text, flags=re.IGNORECASE | re.DOTALL)
        if match.strip()
    ]


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = re.sub(r"<[^>]+>", " ", value)
    value = html_module.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def extract_attribute(tag: str, attribute: str) -> str | None:
    match = re.search(
        rf"\b{re.escape(attribute)}\s*=\s*([\"'])(.*?)\1",
        tag,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return html_module.unescape(match.group(2)).strip() if match else None


def first_itemprop_content(page: str, prop: str) -> str | None:
    for tag in re.findall(r"<meta\b[^>]*>", page, flags=re.IGNORECASE | re.DOTALL):
        if (extract_attribute(tag, "itemprop") or "").casefold() == prop.casefold():
            return clean_text(extract_attribute(tag, "content"))
    return None


def first_itemprop_image(page: str, page_url: str) -> str | None:
    for tag in re.findall(r"<img\b[^>]*>", page, flags=re.IGNORECASE | re.DOTALL):
        if (extract_attribute(tag, "itemprop") or "").casefold() == "image":
            src = extract_attribute(tag, "src")
            return urllib.parse.urljoin(page_url, src) if src else None
    return None


def parse_product_page(page_bytes: bytes, page_url: str, path_metadata: dict[str, dict[str, str]]) -> dict[str, Any] | None:
    page = page_bytes.decode("utf-8", errors="replace")
    name = first_itemprop_content(page, "name")
    source_category = first_itemprop_content(page, "category")
    sku_match = re.search(
        r"<span\b[^>]*class\s*=\s*([\"'])[^\"']*\bvendorL\b[^\"']*\1[^>]*>(.*?)</span>",
        page,
        flags=re.IGNORECASE | re.DOTALL,
    )
    sku = clean_text(sku_match.group(2)) if sku_match else None
    if not name or not source_category or not sku:
        return None

    price_text = first_itemprop_content(page, "price")
    try:
        price: float | int | None = float(str(price_text).replace(",", ".")) if price_text else None
        if isinstance(price, float) and price.is_integer():
            price = int(price)
    except ValueError:
        price = None

    path = urllib.parse.urlsplit(page_url).path
    metadata: dict[str, str] = {}
    for prefix, candidate in path_metadata.items():
        if path.startswith(prefix):
            metadata = candidate
            break

    return {
        "name": name,
        "brand": None,
        "category": metadata.get("category") or source_category.split("/")[0].title(),
        "subcategory": metadata.get("subcategory") or source_category.split("/")[-1].title(),
        "sku": sku,
        "price": price,
        "url": page_url,
        "image": first_itemprop_image(page, page_url),
        "source_category": source_category,
    }


def normalized_allowed_paths(source: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for value in source.get("allowed_paths") or []:
        path = value.get("path") if isinstance(value, dict) else value
        if isinstance(path, str) and path.startswith("/"):
            paths.append(path)
    return paths


def select_leaf_urls(urls: list[str]) -> list[str]:
    """Keep sitemap leaves while preserving source order.

    A URL is a parent page when another sitemap URL has it as a path prefix.
    Product pages are expected to be leaves; the HTML parser remains the final
    authority, so an empty category leaf is safely rejected as a non-product.
    """
    normalized_paths = {
        urllib.parse.urlsplit(url).path.rstrip("/") + "/"
        for url in urls
    }
    parent_paths: set[str] = set()
    for path in normalized_paths:
        parts = path.strip("/").split("/")
        for index in range(1, len(parts)):
            parent_paths.add("/" + "/".join(parts[:index]) + "/")
    return [
        url
        for url in urls
        if urllib.parse.urlsplit(url).path.rstrip("/") + "/" not in parent_paths
    ]


def is_full_catalog_source(source: dict[str, Any]) -> bool:
    return (
        source.get("catalog_scope") == "full_catalog"
        and normalized_allowed_paths(source) == ["/catalog/"]
    )


def discover_candidates(
    source: dict[str, Any], user_agent: str, timeout: float, retries: int
) -> tuple[list[str], list[dict[str, Any]], dict[str, Any]]:
    base_url = source["base_url"]
    robots = build_robots_policy(base_url, user_agent, timeout, retries)
    allowed_paths = normalized_allowed_paths(source)
    if not allowed_paths:
        raise IngestionError("source has no allowed_paths")

    sitemap_urls = source.get("discovery", {}).get("sitemap_urls") or []
    if not sitemap_urls:
        raise IngestionError("source has no discovery.sitemap_urls")

    candidates: list[str] = []
    issues: list[dict[str, Any]] = []
    seen: set[str] = set()
    seed_candidates: list[str] = []
    sitemap_candidates: list[str] = []

    def normalize(candidate: str) -> str | None:
        parsed = urllib.parse.urlsplit(candidate)
        if parsed.netloc.casefold() != urllib.parse.urlsplit(base_url).netloc.casefold():
            return None
        if parsed.query or parsed.fragment:
            return None
        if not any(parsed.path.startswith(prefix) for prefix in allowed_paths):
            return None
        if not robots.can_fetch(user_agent, candidate):
            issues.append({"url": candidate, "code": "robots_disallowed"})
            return None
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))

    def append_unique(candidate: str) -> None:
        canonical = normalize(candidate)
        if canonical is None:
            return
        if canonical not in seen:
            seen.add(canonical)
            candidates.append(canonical)

    for seed_url in source.get("discovery", {}).get("seed_urls") or []:
        canonical = normalize(str(seed_url))
        if canonical:
            seed_candidates.append(canonical)

    for sitemap_url in sitemap_urls:
        if not robots.can_fetch(user_agent, sitemap_url):
            raise IngestionError(f"robots.txt disallows sitemap {sitemap_url}")
        payload, final_url, status = fetch_bytes(sitemap_url, user_agent, timeout, retries)
        if status != 200:
            raise IngestionError(f"sitemap returned HTTP {status}: {final_url}")
        sitemap_candidates.extend(extract_sitemap_urls(payload))

    allowed_sitemap_candidates: list[str] = []
    allowed_seen: set[str] = set()
    for candidate in sitemap_candidates:
        canonical = normalize(candidate)
        if canonical and canonical not in allowed_seen:
            allowed_seen.add(canonical)
            allowed_sitemap_candidates.append(canonical)

    discovery = source.get("discovery", {})
    selected_sitemap = (
        select_leaf_urls(allowed_sitemap_candidates)
        if discovery.get("leaf_only") is True
        else allowed_sitemap_candidates
    )
    product_slug_regex = discovery.get("product_slug_regex")
    if product_slug_regex:
        selected_sitemap = [
            candidate
            for candidate in selected_sitemap
            if re.search(
                str(product_slug_regex),
                urllib.parse.urlsplit(candidate).path.rstrip("/").rsplit("/", 1)[-1],
            )
        ]

    for candidate in [*seed_candidates, *selected_sitemap]:
        append_unique(candidate)
    stats = {
        "sitemap_urls_seen": len(sitemap_candidates),
        "allowed_unique_urls": len(allowed_sitemap_candidates),
        "leaf_only": discovery.get("leaf_only") is True,
        "leaf_candidates": len(select_leaf_urls(allowed_sitemap_candidates)),
        "slug_filter": product_slug_regex,
    }
    return candidates, issues, stats


def fetch_and_parse_candidate(
    candidate: str,
    *,
    user_agent: str,
    timeout: float,
    retries: int,
    path_metadata: dict[str, Any],
    rate_limiter: GlobalRateLimiter,
) -> dict[str, Any] | None:
    """Fetch one candidate and persist its raw response without shared state."""
    rate_limiter.wait_for_turn()
    page_bytes, final_url, status = fetch_bytes(candidate, user_agent, timeout, retries)
    if status != 200:
        raise IngestionError(f"HTTP {status}")
    product = parse_product_page(page_bytes, final_url, path_metadata)
    if product is None:
        return None

    content_sha256 = hashlib.sha256(page_bytes).hexdigest()
    safe_sku = re.sub(r"[^0-9A-Za-zРђ-РЇР°-СЏ._-]+", "_", str(product["sku"]))[:80]
    raw_path = RAW_DIR / f"{safe_sku}_{content_sha256[:12]}.html.gz"
    with gzip.open(raw_path, "wb", compresslevel=6) as raw_file:
        raw_file.write(page_bytes)
    raw_product = {key: value for key, value in product.items() if key != "source_category"}
    return {
        "source_product_key": f"remplanika:sku:{product['sku']}",
        "raw": raw_product,
        "source": {
            "source_id": "",
            "source_url": final_url,
            "retrieved_at": utc_now(),
            "locator": "html:microdata+span.vendorL",
            "content_sha256": content_sha256,
            "raw_snapshot": raw_path.relative_to(BASE_DIR).as_posix(),
        },
        "issues": ["brand_not_exposed"] if not product.get("brand") else [],
    }


def _generate_staging_batch(
    config_path: Path = DEFAULT_CONFIG_PATH,
    *,
    candidate_limit: int = 0,
    max_products: int = 0,
    delay_override: float | None = None,
    replace_source: bool = False,
    checkpoint_every: int | None = None,
    workers_override: int | None = None,
) -> Path:
    config = load_json(config_path, {})
    policy = config.get("policy") or {}
    user_agent = str(policy.get("user_agent") or "SmartSearchCatalogAudit/1.0")
    timeout = float(policy.get("timeout_seconds") or 30)
    retries = int(policy.get("retries") or 2)
    requests_per_second = float(policy.get("default_requests_per_second") or 0.5)
    if delay_override is not None:
        if delay_override < 0:
            raise IngestionError("delay must be zero or positive")
        requests_per_second = 1 / delay_override if delay_override else float("inf")
    # GlobalRateLimiter owns request pacing; retain this name for the legacy
    # sequential loop body below, where it intentionally causes no extra sleep.
    delay = 0.0
    workers = int(workers_override if workers_override is not None else policy.get("workers") or 4)
    if workers < 1:
        raise IngestionError("workers must be at least 1")
    checkpoint_size = (
        int(checkpoint_every)
        if checkpoint_every is not None
        else int(policy.get("checkpoint_every_products") or 100)
    )
    if checkpoint_size < 0:
        raise IngestionError("checkpoint_every must be zero or positive")

    sources = [
        source
        for source in config.get("sources") or []
        if source.get("enabled") and source.get("authorization_status") == "approved"
    ]
    if not sources:
        raise IngestionError("no enabled and approved sources")

    existing = load_json(STAGING_PATH, [])
    if not isinstance(existing, list):
        raise IngestionError("existing staging file is not an array")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    STAGING_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    verified_existing_by_url: dict[str, dict[str, Any]] = {}
    for record in existing:
        source_meta = record.get("source") if isinstance(record, dict) else None
        source_url = source_meta.get("source_url") if isinstance(source_meta, dict) else None
        raw_snapshot = source_meta.get("raw_snapshot") if isinstance(source_meta, dict) else None
        if source_url and raw_snapshot and (BASE_DIR / str(raw_snapshot)).is_file():
            verified_existing_by_url[str(source_url)] = record

    run_started = utc_now()
    resume_checkpoint = load_json(CHECKPOINT_REPORT_PATH, {})
    all_new_records: list[dict[str, Any]] = []
    all_errors: list[dict[str, Any]] = []
    source_reports: list[dict[str, Any]] = []
    manifest_sources: list[dict[str, Any]] = []
    processed_source_ids: set[str] = set()

    for source in sources:
        source_id = str(source["source_id"])
        processed_source_ids.add(source_id)
        candidates, discovery_issues, discovery_stats = discover_candidates(source, user_agent, timeout, retries)
        all_errors.extend({"source_id": source_id, **issue} for issue in discovery_issues)
        selected = candidates[:candidate_limit] if candidate_limit > 0 else candidates
        resume_from = 0
        if (
            isinstance(resume_checkpoint, dict)
            and resume_checkpoint.get("status") == "IN_PROGRESS"
            and resume_checkpoint.get("source_id") == source_id
            and int(resume_checkpoint.get("selected_candidates") or 0) == len(selected)
        ):
            resume_from = min(
                max(int(resume_checkpoint.get("attempted_candidates") or 0), 0),
                len(selected),
            )
        manifest_sources.append(
            {
                "source_id": source_id,
                "catalog_scope": source.get("catalog_scope"),
                "allowed_paths": normalized_allowed_paths(source),
                "discovery": discovery_stats,
                "bounded": candidate_limit > 0 or max_products > 0,
                "selected_urls": selected,
            }
        )
        atomic_write_json(
            MANIFEST_PATH,
            {
                "version": "parser-discovery-manifest-v1",
                "run_started_at": run_started,
                "sources": manifest_sources,
            },
        )
        path_metadata = source.get("path_metadata") or {}
        fetched = parsed_count = skipped_non_product = skipped_404 = reused_verified = 0
        attempted = resume_from
        requests_started = 0
        last_request_started_at: float | None = None
        errors_before_source = len(all_errors)

        effective_workers = 1 if max_products > 0 else workers
        rate_limiter = GlobalRateLimiter(requests_per_second)

        def fetch_candidate_task(candidate: str) -> tuple[str, Any]:
            if not replace_source and candidate in verified_existing_by_url:
                return "reused", None
            try:
                rate_limiter.wait_for_turn()
                return "fetched", fetch_bytes(candidate, user_agent, timeout, retries)
            except Exception as exc:
                return "error", exc

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=effective_workers)
        work_results = ordered_parallel_map(
            executor, fetch_candidate_task, selected[resume_from:], effective_workers
        )

        for index, (candidate, outcome, fetched_value) in enumerate(
            ((candidate, *result) for candidate, result in zip(selected[resume_from:], work_results)),
            start=resume_from,
        ):
            if max_products > 0 and parsed_count >= max_products:
                break
            attempted += 1
            if outcome == "reused":
                reused_verified += 1
                continue
            if last_request_started_at is not None and delay > 0:
                wait_seconds = delay - (time.monotonic() - last_request_started_at)
                if wait_seconds > 0:
                    time.sleep(wait_seconds)
            last_request_started_at = time.monotonic()
            requests_started += 1
            try:
                if outcome == "error":
                    raise fetched_value
                page_bytes, final_url, status = fetched_value
                fetched += 1
                if status != 200:
                    raise IngestionError(f"HTTP {status}")
                product = parse_product_page(page_bytes, final_url, path_metadata)
                if product is None:
                    skipped_non_product += 1
                    continue

                content_sha256 = hashlib.sha256(page_bytes).hexdigest()
                safe_sku = re.sub(r"[^0-9A-Za-zА-Яа-я._-]+", "_", str(product["sku"]))[:80]
                raw_path = RAW_DIR / f"{safe_sku}_{content_sha256[:12]}.html.gz"
                with gzip.open(raw_path, "wb", compresslevel=6) as raw_file:
                    raw_file.write(page_bytes)

                source_key = f"remplanika:sku:{product['sku']}"
                raw_product = {key: value for key, value in product.items() if key != "source_category"}
                all_new_records.append(
                    {
                        "source_product_key": source_key,
                        "raw": raw_product,
                        "source": {
                            "source_id": source_id,
                            "source_url": final_url,
                            "retrieved_at": utc_now(),
                            "locator": "html:microdata+span.vendorL",
                            "content_sha256": content_sha256,
                            "raw_snapshot": raw_path.relative_to(BASE_DIR).as_posix(),
                        },
                        "issues": ["brand_not_exposed"] if not product.get("brand") else [],
                    }
                )
                parsed_count += 1
                if checkpoint_size and len(all_new_records) % checkpoint_size == 0:
                    checkpoint_by_key: dict[str, dict[str, Any]] = {}
                    for checkpoint_record in [*existing, *all_new_records]:
                        if not isinstance(checkpoint_record, dict):
                            continue
                        checkpoint_key = str(checkpoint_record.get("source_product_key") or "")
                        if checkpoint_key:
                            checkpoint_by_key[checkpoint_key] = checkpoint_record
                    checkpoint_records = sorted(
                        checkpoint_by_key.values(),
                        key=lambda item: str(item.get("source_product_key") or ""),
                    )
                    atomic_write_json(STAGING_PATH, checkpoint_records)
                    atomic_write_json(
                        CHECKPOINT_REPORT_PATH,
                        {
                            "version": "parser-ingestion-v3-checkpoint",
                            "status": "IN_PROGRESS",
                            "run_started_at": run_started,
                            "source_id": source_id,
                            "catalog_scope": source.get("catalog_scope"),
                            "selected_candidates": len(selected),
                            "resumed_from_candidate": resume_from,
                            "attempted_candidates": attempted,
                            "parsed_products_this_run": len(all_new_records),
                            "reused_verified_products": reused_verified,
                            "staging_total": len(checkpoint_records),
                            "full_run": False,
                        },
                    )
            except Exception as exc:  # keep the issue queue complete for the handoff
                exc_str = str(exc)
                is_404 = "404" in exc_str or "410" in exc_str
                if is_404:
                    skipped_404 += 1
                code = "http_404_not_found" if is_404 else "fetch_or_parse_error"
                all_errors.append(
                    {"source_id": source_id, "url": candidate, "code": code, "detail": exc_str}
                )

        executor.shutdown(wait=True, cancel_futures=True)
        total_source_errors = len(all_errors) - errors_before_source
        active_parse_errors = total_source_errors - skipped_404
        parse_denominator = parsed_count + reused_verified + skipped_non_product + active_parse_errors
        parse_success_pct = (
            round(100 * (parsed_count + reused_verified) / parse_denominator, 2)
            if parse_denominator
            else 0.0
        )
        source_reports.append(
            {
                "source_id": source_id,
                "catalog_scope": source.get("catalog_scope"),
                "allowed_paths": normalized_allowed_paths(source),
                **discovery_stats,
                "discovered_candidates": len(candidates),
                "selected_candidates": len(selected),
                "fetched_pages": fetched,
                "attempted_candidates": attempted,
                "parsed_products": parsed_count,
                "reused_verified_products": reused_verified,
                "skipped_non_product_pages": skipped_non_product,
                "skipped_404_pages": skipped_404,
                "errors": total_source_errors,
                "parse_success_pct": parse_success_pct,
                "discovery_filter": source.get("discovery", {}).get("product_slug_regex"),
                "manifest_complete": attempted == len(selected),
            }
        )

    # Existing records from this source are trusted only if they carry a real URL
    # and a stored raw snapshot. This intentionally removes the old synthetic demo rows.
    retained: list[dict[str, Any]] = []
    verified_existing: list[dict[str, Any]] = []
    for record in existing:
        source = record.get("source") if isinstance(record, dict) else None
        source_id = source.get("source_id") if isinstance(source, dict) else None
        if source_id not in processed_source_ids:
            retained.append(record)
            continue
        snapshot = source.get("raw_snapshot") if isinstance(source, dict) else None
        source_url = source.get("source_url") if isinstance(source, dict) else None
        if not replace_source and snapshot and source_url and (BASE_DIR / snapshot).exists():
            verified_existing.append(record)

    merged_by_key: dict[str, dict[str, Any]] = {}
    for record in [*verified_existing, *all_new_records]:
        key = str(record.get("source_product_key") or "")
        if key:
            merged_by_key[key] = record
    output_records = retained + list(merged_by_key.values())
    output_records.sort(key=lambda item: str(item.get("source_product_key") or ""))

    if not all_new_records and not verified_existing:
        raise IngestionError("live ingestion parsed zero products; existing staging was not overwritten")

    previous_keys = {str(record.get("source_product_key")) for record in verified_existing}
    new_keys = {str(record.get("source_product_key")) for record in all_new_records}
    full_catalog = all(is_full_catalog_source(source) for source in sources)
    manifest_complete = all(item.get("manifest_complete") is True for item in source_reports)
    unbounded = candidate_limit == 0 and max_products == 0
    manifest_sha256 = hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest()
    report = {
        "version": "parser-ingestion-v3-full-catalog",
        "status": "PASS" if full_catalog and manifest_complete and unbounded else "PARTIAL",
        "run_started_at": run_started,
        "run_finished_at": utc_now(),
        "config": config_path.relative_to(BASE_DIR).as_posix(),
        "discovery_manifest": MANIFEST_PATH.relative_to(BASE_DIR).as_posix(),
        "discovery_manifest_sha256": manifest_sha256,
        "manifest_candidates": sum(len(item["selected_urls"]) for item in manifest_sources),
        "sources": source_reports,
        "fetched_pages": sum(item["fetched_pages"] for item in source_reports),
        "attempted_candidates": sum(item["attempted_candidates"] for item in source_reports),
        "parsed_products": len(all_new_records),
        "new_unique_products": len(new_keys - previous_keys),
        "verified_existing_products": len(verified_existing),
        "staging_total": len(output_records),
        "errors": len(all_errors),
        "catalog_scope": "full_catalog" if full_catalog else "partial_catalog",
        "catalog_scope_complete": full_catalog,
        "manifest_complete": manifest_complete,
        "full_run": full_catalog and manifest_complete and unbounded,
        "minimum_parse_success_pct": float(policy.get("minimum_parse_success_pct") or 95),
        "synthetic_rows_allowed": False,
    }
    atomic_write_json(ERRORS_PATH, all_errors)
    atomic_write_json(REPORT_PATH, report)
    atomic_write_json(STAGING_PATH, output_records)
    CHECKPOINT_REPORT_PATH.unlink(missing_ok=True)
    print(json.dumps(report, ensure_ascii=False))
    return STAGING_PATH


def generate_staging_batch(*args, **kwargs) -> Path:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        owner = LOCK_PATH.read_text(encoding="utf-8", errors="replace") if LOCK_PATH.exists() else "unknown"
        raise IngestionError(f"another parser run is active (lock owner: {owner})") from exc
    try:
        with os.fdopen(lock_fd, "w", encoding="utf-8") as lock_file:
            lock_file.write(f"pid={os.getpid()} started_at={utc_now()}\n")
        return _generate_staging_batch(*args, **kwargs)
    finally:
        LOCK_PATH.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--limit", type=int, default=0, help="maximum sitemap candidates to fetch; 0 means all")
    parser.add_argument("--max-products", type=int, default=0, help="stop after N parsed products; 0 means all")
    parser.add_argument("--delay", type=float, default=None, help="override delay between page requests")
    parser.add_argument("--replace-source", action="store_true", help="replace rather than incrementally merge source rows")
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="parallel fetch workers; defaults to policy.workers (4)",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=None,
        help="persist resumable staging after N newly parsed products; 0 disables checkpoints",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    generate_staging_batch(
        args.config,
        candidate_limit=args.limit,
        max_products=args.max_products,
        delay_override=args.delay,
        replace_source=args.replace_source,
        checkpoint_every=args.checkpoint_every,
        workers_override=args.workers,
    )
