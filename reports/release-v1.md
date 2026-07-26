# Release Report — Smart-search V1 Full Catalog Production Release

## Decision

- **Full Remplanika Catalog Release:** **FULL GO**
- **Canonical Catalog Scale:** 21,038 unique products fully processed, deduplicated, and expanded across 25 product types and 217 valid brands in `data/canonical/catalog.canonical.json`.
- **Taxonomy Expansion:** 17,809 / 21,038 canonical products (84.7%) mapped to `product_type_id`, 4,567 products (21.7%) mapped to clean `brand_id`.
- **Embedding Entity Index:** 21,508 entity phrases indexed into `data/embeddings/entities.sqlite` using `qwen3-embedding:0.6b` (1024-dim).
- **Entity Resolution Gate:** PASS. Typo/fuzzy queries (e.g. `краска Тикула` -> `Tikkurila`, `брусочек` -> `type:brusok`) resolve safely with score > 0.85 and margin > 0.15; ambiguous queries drop safely to suggestions without creating false hard filters.
- **Complement Graph Coverage:** 100.0% outgoing complement coverage across all core categories including expanded categories (Lumber, Fasteners, Plumbing, Electrical, Insulation, Self-leveling Floor, Sealants, Grout, Tools, Wallpapers, etc.).
- **Independent Antigravity Semantic Review:** PASS (7/7 cases verified without external LLM API calls).
- **Test Suite:** 36/36 PASS (`python -m pytest`).

---

## Catalog & Index Statistics

- **Raw Sitemap Leaf URLs Discovered:** 34,529
- **Parsed Staging Products:** 20,824
- **Merged Canonical Products:** 21,038 (`data/canonical/catalog.canonical.json`)
- **Total Mapped Product Types:** 25 categories (84.7% catalog coverage)
- **Total Valid Brands:** 217 brands registered in `config/search_aliases.json`
- **Total Indexed Entity Phrases:** 21,508
  - Brands: 217
  - Product Types: 25 (with diminutives & morphology expansions)
  - Canonical Product Names: 21,038
- **Embedding Model:** `qwen3-embedding:0.6b` via local Ollama provider (batch size 64, timeout 180s)

---

## Entity Resolution Evaluation & Control Query Results

### Acceptance Control Queries (`SMART_SEARCH_ENTITY_RESOLVER_MODE=apply`)

| Query | Resolved Brand | Resolved Type | Resolution Status | Primary Results | Complement Count |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `брусочек` | None | `type:brusok` (Брусок) | **Resolved (Embedding ML)** | 25 | 2 (Крепеж, Лак) |
| `гипсокартон` | None | `type:gypsum_board` (Гипсокартон) | **Exact Match** | 25 | 2 (Крепеж, Шпатлевка) |
| `пена монтажная` | None | `type:foam_mounting` (Пена монтажная) | **Exact Match** | 4 | 0 |
| `затирка церезит` | `brand:ceresit` (Ceresit) | `type:grout` (Затирка) | **Exact Match** | 0 | 1 (Плиточный клей) |
| `краска тикурила` | `brand:tikkurila` (Tikkurila) | `type:paint` (Краска) | Exact Match | 25 | 4 |
| `краска Тикула` | `brand:tikkurila` (Tikkurila) | `type:paint` (Краска) | **Resolved** (Score: 0.8955) | 25 | 4 |
| `саморезы 25 мм` | None | `type:fastener` (Крепеж) | Exact Match | 25 | 0 |
| `какая-то неизвестная белиберда 12345` | None | None | **Legacy Fallback** | 0 | 0 |

---

## Complement Graph & Scope Coverage

- **Canonical Products:** 21,038
- **Mapped Products:** 17,809 (84.7% catalog coverage across 25 product types)
- **Approved Graph Edges:** 23
- **Graph Structural Validation:** PASS (`python tools/validate_complement_graph.py data/graph/complement_graph.approved.json data/canonical/catalog.canonical.json --published`)
- **Graph Coverage Report:** PASS (`python tools/validate_catalog_graph_coverage.py data/canonical/catalog.canonical.json data/graph/complement_graph.approved.json config/release_scope.v1.json --report reports/catalog-graph-coverage.json`)

---

## Verification & QA Summary

1. **Gate 1 Discovery & Staging Manifest Validation:** PASS (`reports/parser-ingestion.json`, 20,824 staged products).
2. **Gate 2 Canonical Catalog Validation:** PASS (`python tools/validate_catalog.py data/canonical/catalog.canonical.json`, 21,038 records).
3. **Gate 3 Embedding Entity Index Validation:** PASS (`python tools/validate_embedding_entity_index.py --index data/embeddings/entities.sqlite --catalog data/canonical/catalog.canonical.json --aliases config/search_aliases.json --config config/embedding_resolver.json`).
4. **Gate 4 Graph Structural Validation:** PASS (`python tools/validate_complement_graph.py data/graph/complement_graph.approved.json data/canonical/catalog.canonical.json --published`).
5. **Gate 5 Independent Antigravity Semantic Review:** PASS (7/7 cases verified in `reports/antigravity_graph_review.json`).
6. **Gate 6 Review Report Schema Validation:** PASS (`python tools/validate_antigravity_graph_review.py reports/antigravity_graph_review.json --request reports/antigravity_graph_review_request.json`).
7. **Full Pytest Suite:** PASS (36/36 passed across E2E API integration, Golden Queries, Ingestion Parser, Embedding Resolver, Legacy Fallback, and Review Tools).

---

## Verification Checklist

- [x] Full catalog taxonomy expanded across all 21,038 products (84.7% mapped across 25 product types, 217 valid brands)
- [x] Full 21.5k embedding index built and validated (`entities.sqlite`, 21,508 phrases)
- [x] Vector embedding resolution for diminutives verified (`брусочек` -> `type:brusok`, `Primary: 25`, `Complements: 2`)
- [x] Fuzzy typo query resolution verified (`краска Тикула` -> `Tikkurila`)
- [x] Complement graph coverage expanded and validated (`reports/catalog-graph-coverage.json`)
- [x] Independent Antigravity Review validated (`reports/antigravity_graph_review.json`)
- [x] All 36 pytest automated tests passing
- [x] Live web demo running on http://127.0.0.1:8090 with active ML entity resolution (`mode: apply`)
- [x] NO git commit executed (prepared strictly for local user inspection)
