# Release Report — Smart-search V1 Full Orchestration Run

## Decision

- **Scoped V1 Demo & API Release:** CONDITIONAL GO; the search demo works, but catalog ingestion must be rerun.
- **Full Remplanika Catalog Ingestion:** NO-GO. The previous source manifest allowed only brushes and rollers, so its `full_run=true` was not catalog-wide.
- **Production Scope:** Explicitly restricted to 8 validated product types (Paint, Primer, Putty, Varnish, Brush, Roller, Plaster, Tile Glue).
- **Claim “covered the whole catalog”:** NO-GO.
- **Reason:** 1,546 of 5,341 canonical products are mapped to the eight declared V1 product types (28.95%). Outgoing complement coverage inside that explicit scope is 100% (1,546/1,546), while 3,795 products remain outside the V1 taxonomy.

## Live Ingestion Evidence

- **Source:** Public Remplanika catalog discovered via `sitemap_iblock_7.xml`.
- **Historical Partial-Scope Run:** 513 candidate URLs were discovered only under brush and roller paths. Its evidence was archived and no longer satisfies Gate 1.
- **Current Catalog-wide Discovery:** 37,675 sitemap URLs and 34,529 leaf candidates under the full `/catalog/`; product-page ingestion has not yet completed.
- **Historical Parse Success Rate:** 98.25% inside the two old paths; this does not establish catalog-wide precision.
- **Existing Partial Staging:** 334 records remain reusable because they have raw compressed HTML snapshots.
- **Active Evidence Artifact:** `reports/parser-ingestion.json` is deliberately `NOT_RUN` until the full manifest completes.

## Complement Graph & Coverage

- **Canonical Products:** 5,341.
- **Mapped Scoped Products:** 1,546 (28.95% of catalog).
- **Declared V1 Types with Products:** 8/8 (100%).
- **Scoped Types with Outgoing Edges:** 8/8 (100%).
- **Scoped Products Inheriting Outgoing Edges:** 1,546/1,546 (100%).
- **Approved Graph:** 8 nodes, 17 edges.
- **Graphify Ollama Extraction:** Extracted corpus using `gemma4:e2b` into 8 nodes, 12 edges, and 3 communities.
- **Evidence Artifacts:** `data/graph/complement_graph.approved.json`, `reports/catalog-graph-coverage.json`.

## Verification & Independent QA

- **Gate 1 Staging Validation:** NOT RUN for the new full-catalog manifest. A category-filtered report may not close this gate.
- **Gate 2 Canonical Catalog Validation:** PASS (`python tools/validate_catalog.py data/canonical/catalog.canonical.json`).
- **Gate 3 Graph Structural Validation:** PASS (`python tools/validate_complement_graph.py data/graph/complement_graph.approved.json data/canonical/catalog.canonical.json --published`).
- **Independent Antigravity Semantic Review:** PASS (7/7 test cases verified by Agent 08 without external LLM API calls, reported in `reports/antigravity_graph_review.json`).
- **Review Report Validation:** PASS (`python tools/validate_antigravity_graph_review.py reports/antigravity_graph_review.json --request reports/antigravity_graph_review_request.json`).
- **Test Suite:** 21/21 PASS (`python -m pytest`).

## Remaining Work Before Catalog-wide GO

1. Run `python src/ingestion/parser.py` to completion; resume with the same command after interruption.
2. Validate the immutable discovery manifest and all staged provenance.
3. Rebuild canonical catalog and taxonomy from the complete batch.
4. Extend and approve complement graph edges for newly admitted product categories.
5. Re-run independent graph review, backend/frontend tests and release QA.
