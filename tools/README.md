# Tools

Все Python-скрипты используют только стандартную библиотеку.

## Проверка source catalog

```powershell
python tools/validate_catalog.py data/source/catalog.snapshot.json
```

## Проверка parser staging batch

```powershell
python src/ingestion/parser.py
python tools/validate_staging_batch.py data/staging/staged_products.json `
  --report reports/parser-ingestion.json --require-new --require-complete
```

Парсер читает `robots.txt`, весь `sitemap_iblock_7.xml`, выбирает leaf URL во всём `/catalog/`, получает публичные карточки с ограничением 0.5 запроса/с и сохраняет gzip raw HTML. Фильтра по краскам, кистям или цифрам в slug нет. Checkpoint сохраняется каждые 100 новых товаров; прерванный запуск продолжайте той же командой без `--replace-source`. Для короткого smoke-run: `--limit 40 --max-products 10`; такой запуск нельзя называть полным импортом.

## Локальный embedding entity resolution

Exact tag и smoke-вызов Ollama:

```powershell
python tools/check_embedding_model.py --model "qwen3-embedding:0.6b"
```

Production index строится только после полного parser run и нового canonical snapshot:

```powershell
python tools/build_embedding_entity_index.py
python tools/validate_embedding_entity_index.py
python tools/evaluate_entity_resolution.py
```

Ручная проверка опубликованного provisional-индекса:

```powershell
python tools/query_embedding_entity_index.py "Тикула" `
  --entity-type brand `
  --index data/embeddings/entities.current-canonical.sqlite `
  --json
```

Builder продолжает `data/embeddings/entities.building.sqlite` после прерывания и публикует `entities.sqlite` только после полного прохода. `--limit` создаёт лишь smoke checkpoint и не закрывает release gate. Индекс содержит authoritative aliases брендов и названия canonical товаров; raw brand без canonical ID не получает право hard filter.

Resolver использует hybrid score (embedding + character + transliteration), exact aliases всегда проверяются первыми. Неуверенность или недоступность Ollama возвращают прежний deterministic/legacy path.

## Проверка complement graph

Seed/candidate mode:

```powershell
python tools/validate_complement_graph.py config/complement_graph.seed.json data/source/catalog.snapshot.json
```

Published mode требует только approved edges:

```powershell
python tools/validate_complement_graph.py data/graph/complement_graph.approved.json data/canonical/catalog.canonical.json --published
```

## Проверка фактического покрытия графа

```powershell
python tools/validate_catalog_graph_coverage.py data/canonical/catalog.canonical.json `
  data/graph/complement_graph.approved.json config/release_scope.v1.json `
  --report reports/catalog-graph-coverage.json
```

## Graphify через Ollama

Проверьте, что Ollama запущен и точный тег существует. CLI необязателен: раннер использует локальный API `/api/tags` и `/api/chat`.

```powershell
ollama list
```

Затем:

```powershell
python tools/build_graphify_corpus.py
powershell -ExecutionPolicy Bypass -File tools/run_graphify_ollama.ps1 -CorpusPath graph-corpus -Model "gemma4:e2b"
```

Graphify 0.8.40 поддерживает native `--backend ollama`. Для backend требуется пакет `openai` в окружении Graphify. Если Graphify сообщает, что он отсутствует:

```powershell
uv tool install "graphifyy[ollama]" --force
```

Раннер проверяет API, точный model tag и реальную JSON-генерацию, затем запускает extraction последовательно. Локальный end-to-end smoke-test `gemma4:e2b` успешно построил граф из двух документов; подробности — в `docs/OLLAMA_STATUS.md`.

## Локальный web demo

```powershell
python tools/serve_demo.py
```

Откройте `http://127.0.0.1:8090/`. По умолчанию используется Fixture Mode; после готовности backend выберите `Backend API`.

## Независимый semantic review силами Antigravity

Сначала создайте компактный, воспроизводимый пакет с hashes, test cases и релевантными neighborhoods:

```powershell
python tools/prepare_antigravity_graph_review.py `
  --graph data/graph/complement_graph.approved.json `
  --cases config/graph_test_cases.json `
  --coverage reports/catalog-graph-coverage.json `
  --output reports/antigravity_graph_review_request.json
```

Затем Lead обязан запустить **отдельного** субагента по `agents/08_graph_semantic_reviewer.md`. Он работает собственными возможностями Antigravity, не вызывает внешний LLM API, не меняет граф и сохраняет findings в `reports/antigravity_graph_review.json`.

Проверьте handoff:

```powershell
python tools/validate_antigravity_graph_review.py `
  reports/antigravity_graph_review.json `
  --request reports/antigravity_graph_review_request.json
```

Невалидный, неполный или созданный автором графа отчёт не закрывает gate. Semantic review создаёт findings, но не переводит candidate edges в approved.
