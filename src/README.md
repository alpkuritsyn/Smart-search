# Implementation ownership

- `ingestion/` — Product Parser Agent.
- `catalog/`, `normalization/` — Catalog Normalization Agent.
- `graph/` — Complement Graph Agent.
- `ml/` — Embedding Entity Resolution Agent; локальный exact-first hybrid resolver.
- `search/`, `backend/` — Backend Agent.

Lead управляет контрактами, QA владеет тестами и отчётами. До реализации каталоги намеренно пусты: Antigravity agents должны создавать код по фазам `WORKFLOW.md`, не смешивая ответственность в одном модуле.
