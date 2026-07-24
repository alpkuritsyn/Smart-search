# Независимая проверка графа силами Antigravity

Этот контур заменяет внешний model-review. Семантическую проверку выполняет новый субагент Antigravity в отдельном контексте от Graph Agent и Lead.

## Зачем два шага

`prepare_antigravity_graph_review.py` детерминированно фиксирует входы и отбирает релевантные neighborhoods. Субагент оценивает их смысл. `validate_antigravity_graph_review.py` проверяет независимость, полноту cases, hashes и JSON-контракт. Ни один из шагов не утверждает рёбра автоматически.

## Запуск

```powershell
python tools/prepare_antigravity_graph_review.py `
  --graph data/graph/complement_graph.approved.json `
  --cases config/graph_test_cases.json `
  --coverage reports/catalog-graph-coverage.json
```

Затем Lead создаёт отдельного субагента и передаёт ему `agents/08_graph_semantic_reviewer.md` и путь к request. После его handoff:

```powershell
python tools/validate_antigravity_graph_review.py `
  reports/antigravity_graph_review.json `
  --request reports/antigravity_graph_review_request.json
```

## Готовый промпт рецензенту

```text
Ты — новый независимый Graph Semantic Reviewer. Полностью прочитай agents/08_graph_semantic_reviewer.md и выполни его без расширения полномочий. Проверь reports/antigravity_graph_review_request.json собственными возможностями текущего субагента Antigravity. Не вызывай Gemini или другие внешние LLM API, не редактируй граф и не используй знания из памяти как доказательства. Запиши только reports/antigravity_graph_review.json, проверь его tools/validate_antigravity_graph_review.py и верни краткий handoff со статусом и blocking case IDs.
```

Если создать отдельного субагента невозможно, review имеет статус `NOT_RUN`, а production gate остаётся закрытым.
