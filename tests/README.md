# Test ownership

- `golden/`, `regression/`, `e2e/` — QA Agent.
- `fixtures/parser/` — Product Parser Agent.
- `fixtures/normalization/` — Catalog Normalization Agent.
- `fixtures/graph/` — Complement Graph Agent.
- `frontend/` — Frontend Agent; contract parity, renderer states, keyboard/mobile checks.

Backend может добавлять unit/contract tests своей реализации, но не меняет frozen golden expectations.
