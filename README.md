# Smart-search V1

## Обязательные доказательства результата

Workflow не считается выполненным только потому, что JSON и тестовые запросы валидны. Перед `GO` должны существовать два машинно проверяемых отчёта:

- `reports/parser-ingestion.json` — полный `/catalog/` sitemap manifest, реальные HTTP fetches Remplanika и число новых уникальных товаров;
- `reports/catalog-graph-coverage.json` — общая catalog mapping coverage и 100% outgoing coverage внутри явно заявленного V1 scope.

Synthetic product rows и `allow_empty_until_parser` запрещены в published release.

Отдельный рабочий пакет для детерминированного товарного поиска и рекомендаций комплементарных категорий.

## Цель V1

Пользователь примерно знает, какой товар ищет: «краска тикурила», «грунтовка dulux», «лак для дерева», «шпаклевка 20 кг». Система нормализует запрос, находит товары по жёстким ограничениям и добавляет отдельные группы комплементов.

V1.1 разрешает локальные embeddings только для узкого entity resolution: исправления брендов и названий уже существующих товаров (`Тикула → Tikkurila`). Общий semantic retrieval по пользовательской задаче, RAG, консультант, LLM-ранжирование, автоматическое построение технологии ремонта и графовая БД не входят в scope. LLM не является runtime-источником товарных связей.

## С чего начать в Antigravity

1. Откройте эту папку как отдельный Project в Local Mode.
2. Передайте содержимое `START_PROMPT.md` в главный чат.
3. Главный агент должен прочитать `WORKFLOW.md`, `agents/00_shared_contract.md` и файлы назначаемых агентов.
4. Запустите workspace workflow `/smart-search-v1` либо попросите Lead выполнить `WORKFLOW.md`.

## Состав

- `agents/` — подробные роли и контракты девяти агентов, включая отдельного Embedding Entity Resolution Agent, Frontend Agent и независимого Graph Semantic Reviewer.
- `.agents/workflows/` — запускаемый workflow Antigravity.
- `.agents/rules/` — постоянные ограничения V1.
- `baseline/` — компактная копия текущего MVP для анализа и переноса логики.
- `data/source/catalog.snapshot.json` — неизменяемый стартовый каталог.
- `config/` — примеры словарей, графа, источников парсинга и тест-кейсов.
- `tools/` — проверки каталога и графа, запуск Graphify через Ollama, подготовка и валидация независимого Antigravity review.
- `docs/` — scope и критерии приёмки.
- `web/demo/` — mock-first интерфейс визуализации primary и complement выдачи.
- `contracts/` — общий JSON Schema для Backend и Frontend.

## Важные ограничения

- `baseline/` и `data/source/catalog.snapshot.json` нельзя редактировать вручную.
- Секреты не хранятся в проекте. Используйте `.env`, который исключён из Git.
- Тег Ollama `gemma4:e2b` передаётся без исправлений. Скрипт останавливается, если такого тега нет в локальном Ollama.
- Локальный Ollama API проверен: точный тег `gemma4:e2b` установлен и генерирует валидный JSON. CLI может отсутствовать в `PATH`, поэтому Graphify-runner проверяет API напрямую.
- Product Parser не имеет категорийного allowlist: он обрабатывает все leaf URL публичного `/catalog/`. Checkpoint позволяет продолжить длинный импорт без повторной загрузки уже подтверждённых raw snapshots.
- Embedding resolver использует только локальный Ollama и точный тег `qwen3-embedding:0.6b`. Exact aliases всегда приоритетнее ML; недоступность модели не ломает обычный поиск.

## Быстрые проверки

```powershell
python tools/validate_catalog.py data/source/catalog.snapshot.json
python tools/check_embedding_model.py --model "qwen3-embedding:0.6b"
python tools/build_embedding_entity_index.py
python tools/validate_embedding_entity_index.py
python tools/validate_complement_graph.py config/complement_graph.seed.json data/source/catalog.snapshot.json
powershell -ExecutionPolicy Bypass -File tools/run_graphify_ollama.ps1 -CorpusPath . -Model "gemma4:e2b"
python tools/prepare_antigravity_graph_review.py --graph data/graph/complement_graph.approved.json --cases config/graph_test_cases.json
# Затем запустите отдельного субагента по agents/08_graph_semantic_reviewer.md
python tools/validate_antigravity_graph_review.py reports/antigravity_graph_review.json
python tools/serve_demo.py
```

Если `python` отсутствует, используйте доступный Python 3.11+ или `uv run --python 3.12 python ...`.
