# Baseline Report — Smart-search V1

## Summary

- **Date:** 2026-07-21
- **Catalog Snapshot:** `data/source/catalog.snapshot.json`
- **Catalog Metadata:** `data/source/catalog.snapshot.meta.json`
- **Catalog Record Count:** 5007
- **Catalog SHA-256:** `258daf8dba484910b6a89d50e6cfaca41e62eb1f9215c9ca51415e78a554866b`
- **Validation Status:** `PASS` (`tools/validate_catalog.py`)

## Known Data Gaps

- Missing application tools (brushes, rollers) in initial catalog snapshot (`category: Инструменты` / `subcategory: Кисти` has 0 products).
- Missing images (`image`: 4968 nulls), missing product URLs (`url`: 507 nulls).
- 20 duplicate SKU groups across non-empty fields in raw catalog.

## Baseline Legacy Retrieval Results (`retrieve_relevant_products`)

| Query | Legacy Top Results Count | Sample Top Matches |
|---|---|---|
| `краска тикурила` | 25 | Matches items containing "краска" (507 total matching items in catalog) |
| `краска tikkurila` | 25 | Matches items containing "краска" or "tikkurila" |
| `грунтовка dulux` | 25 | Matches items containing "грунтовка" or "dulux" |
| `лак для дерева` | 25 | Matches items containing "лак", "дерева" |
| `шпаклевка 20 кг` | 25 | Matches items containing "шпаклевка", "20", "кг" |

## Verification Command

```powershell
python tools/validate_catalog.py data/source/catalog.snapshot.json
```
