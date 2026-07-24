# Graphify product-corpus smoke test

- Runtime: local Ollama `gemma4:e2b`.
- Input: `graph-corpus/*.md`.
- Result: 8 nodes, 12 extracted semantic edges.
- Query expansion: `paint, primer, putty, brush, roller`.
- BFS reached all eight V1 product types.

The semantic extraction reversed or rephrased several directed rules (for example it emitted `Brush --APPLY_WITH--> Primer`). Therefore this graph is audit/candidate evidence only and is never used as the runtime approved graph. Production recommendations come from `data/graph/complement_graph.approved.json`, structural validation, coverage validation and human approval.

