# Workflow Smart-search V1

## Принцип исполнения

Lead управляет фазами и handoff. Одновременно работают не более трёх пишущих агентов, причём их owned paths не пересекаются. Любое изменение контракта сначала принимает Lead, затем владельцы адаптируют свои артефакты.

## Фаза 0. Bootstrap и baseline — последовательно

Владелец: Lead.

1. Прочитать scope, shared contract и состояние файлов.
2. Посчитать SHA-256 стартового каталога и сверить с `data/source/catalog.snapshot.meta.json`.
3. Запустить `tools/validate_catalog.py`.
4. Зафиксировать поведение legacy retrieval на golden queries.
5. Создать `reports/baseline.md` с версиями, командами запуска и известными data gaps.

Gate 0: baseline воспроизводится; source snapshot не изменён; секреты отсутствуют.

## Фаза 1. Параллельная подготовка данных

Lead запускает одновременно четыре независимые ветки. При ограничении concurrency сначала запускаются Parser, Normalization и Frontend, а QA Early стартует сразу после освобождения слота.

### 1A. Product Parser Agent

- читает `agents/02_product_parser.md`;
- утверждает source manifest;
- получает весь публичный товарный каталог, не ограничиваясь красками или инструментами;
- сохраняет raw/staging/provenance;
- передаёт staged manifest агенту нормализации.
- запускает реальный `src/ingestion/parser.py`, а не создаёт карточки из констант;
- сохраняет gzip raw HTML и `reports/parser-ingestion.json`;
- проходит `validate_staging_batch.py --report ... --require-new --require-complete` на первом полном запуске.

### 1B. Catalog Normalization Agent

- читает `agents/03_catalog_normalization.md`;
- профилирует стартовый snapshot;
- создаёт taxonomy, aliases и deterministic query parser;
- публикует версионированный canonical snapshot;
- не создаёт комплементарные связи.

### 1C. QA Agent, ранний режим

- читает `agents/06_qa_verification.md`;
- создаёт immutable golden queries и negative cases;
- фиксирует legacy outputs;
- не смотрит на будущую реализацию при формировании ожидаемых hard constraints.

### 1D. Frontend Agent, Mock Mode

- читает `agents/07_frontend.md` и `docs/FRONTEND_CONTRACT.md`;
- работает только в `web/**` и frontend fixtures/tests;
- использует fixture `web/demo/fixtures/paint-tikkurila.json`;
- реализует query input, normalized/debug chips, primary grid, complement groups, relation/rationale и состояния loading/empty/error/data-gap;
- не вызывает LLM и не создаёт товарные связи;
- готовит адаптер, который позже меняет fixture transport на `GET /api/search?q=...` без изменения renderer.

Gate 1: parser staging валиден; report содержит `catalog_scope=full_catalog`, `catalog_scope_complete=true`, `manifest_complete=true` и `full_run=true`; source разрешает ровно `/catalog/`; весь leaf manifest sitemap attempted или переиспользован из проверенного raw snapshot; parse success не ниже policy threshold; `fetched_pages > 0`, `parsed_products > 0`, `new_unique_products > 0` на первом импорте. Category allowlist, slug regex и bounded run никогда не закрывают Gate 1.

## Фаза 2. Нормализация новых товаров — последовательно

Catalog Normalization Agent принимает staged records Product Parser Agent, разрешает сущности и выпускает новый canonical snapshot. Product Parser не редактирует canonical data.

Gate 2: schema validation 100%; все добавления имеют provenance; дубликаты и конфликты вынесены в queue.

## Фаза 2E. Embedding Entity Resolution — параллельно с графом после Gate 2

Владелец: Embedding Entity Resolution Agent, файл `agents/09_embedding_entity_resolution.md`.

Эта ветка стартует только после завершения полного parser run и публикации нового canonical/aliases snapshot. Индекс, собранный во время продолжающегося импорта, считается stale и не публикуется.

1. Получить canonical catalog, authoritative brand aliases, normalization contract и SHA-256 от Agent 03.
2. Проверить локальный Ollama и точный model tag:

```powershell
python tools/check_embedding_model.py --model "qwen3-embedding:0.6b"
```

Если тег отсутствует, Agent 09 не заменяет его другой моделью и не скачивает без разрешения пользователя. Остальные ветки продолжают работу; release может идти с resolver mode `off`.

3. Построить индекс с checkpoint/resume и атомарной публикацией:

```powershell
python tools/build_embedding_entity_index.py
python tools/validate_embedding_entity_index.py
python tools/evaluate_entity_resolution.py
```

4. Индексировать бренды только из authoritative aliases/canonical IDs. Raw brand без canonical ID запрещён для auto-resolution. Названия товаров берутся из принятого canonical snapshot.
5. Откалибровать hybrid score и margin отдельно для brand/product_name. Exact aliases всегда имеют приоритет и не вызывают Ollama.
6. Выпустить evaluation report. В первом release brand может стать hard filter только при `resolved`; product_name остаётся safe boost/suggestion и пересекается с уже распознанными hard filters.
7. Передать Backend resolver API, mode `off|shadow|apply`, model/index/config hashes, thresholds, latency и unavailable behavior. Передать QA immutable evaluation set и false-positive list.

Gate 2E: index validator PASS; catalog/aliases/config hashes совпадают; точный model tag зафиксирован; false accepted brand hard filters = 0; `Тикула → brand:tikkurila`; `тик` unresolved/ambiguous; missing model/timeout/stale index дают прежний deterministic/legacy путь. Если gate не закрыт, resolver остаётся `off`, но deterministic V1 не блокируется.

## Фаза 3. Граф комплементов — отдельный агент

Владелец: Complement Graph Agent, файл `agents/04_complement_graph.md`.

1. Получить утверждённую taxonomy version.
2. Подготовить typed edge candidates и provenance.
3. Запустить Graphify локально через Ollama:

```powershell
python tools/build_graphify_corpus.py
powershell -ExecutionPolicy Bypass -File tools/run_graphify_ollama.ps1 -CorpusPath graph-corpus -Model "gemma4:e2b"
```

4. Не публиковать автоматически рёбра, предложенные LLM.
5. Запустить structural validation:

```powershell
python tools/validate_complement_graph.py data/graph/complement_graph.approved.json data/canonical/catalog.canonical.json --published
```

6. Подготовить минимальный review-пакет из утверждённого графа, test cases и coverage:

```powershell
python tools/prepare_antigravity_graph_review.py `
  --graph data/graph/complement_graph.approved.json `
  --cases config/graph_test_cases.json `
  --coverage reports/catalog-graph-coverage.json `
  --output reports/antigravity_graph_review_request.json
```

7. Lead запускает **нового отдельного субагента Antigravity** и передаёт ему полный текст `agents/08_graph_semantic_reviewer.md` плюс путь `reports/antigravity_graph_review_request.json`. Это отдельный контекст: автор графа, Lead и обычный QA не могут выдать себя за независимого рецензента. Субагент не вызывает внешний LLM API, работает собственными возможностями Antigravity и пишет только `reports/antigravity_graph_review.json`.

Готовая задача субагенту:

> Выполни независимую семантическую проверку графа строго по `agents/08_graph_semantic_reviewer.md`. Прочитай `reports/antigravity_graph_review_request.json`, проверь каждое ребро и каждый кейс только по приложенным артефактам, не редактируй граф и не вызывай внешние LLM API. Запиши результат в `reports/antigravity_graph_review.json`, затем верни краткий handoff со статусом и блокирующими findings.

После handoff Lead проверяет контракт отчёта:

```powershell
python tools/validate_antigravity_graph_review.py `
  reports/antigravity_graph_review.json `
  --request reports/antigravity_graph_review_request.json
```

Если отдельный reviewer не запущен, нарушена независимость или отчёт невалиден, review получает `NOT_RUN`, а release gate остаётся закрытым. Lead не должен подменять этот шаг самостоятельным ответом.

8. Измерить фактическое покрытие:

```powershell
python tools/validate_catalog_graph_coverage.py data/canonical/catalog.canonical.json `
  data/graph/complement_graph.approved.json config/release_scope.v1.json `
  --report reports/catalog-graph-coverage.json
```

9. Разобрать missing types/empty targets и findings независимого рецензента, получить review Lead/эксперта и только затем выпустить approved snapshot.

Gate 3: нет dangling nodes; нет production-рёбер без provenance и `approved`; 100% типов и товаров заявленного V1 scope имеют исходящие связи; target-категории непустые; валидатор подтвердил `independent_from_graph_author=true`, `external_provider_used=false`, все review cases рассмотрены, а findings разобраны человеком.

## Фаза 4. Backend — один владелец runtime-файлов

Владелец: Backend Agent.

1. Реализовать deterministic normalization pipeline и exact aliases.
2. Извлечь бренд, тип товара и простые параметры.
3. Только для unresolved span вызвать injectable entity resolver за mode `off|shadow|apply`; exact path не вызывает Ollama.
4. Применить brand hard filter только для `exact|resolved`. Product-name candidates в V1.1 лишь поднимают SKU после пересечения с brand/type/size filters.
5. При timeout/missing model/stale index/ambiguous/suggestion продолжить прежний путь без HTTP 500.
6. Выполнить strict primary retrieval.
7. Дополнить недостающие результаты legacy retrieval только без нарушения hard filters.
8. Получить комплементы из approved graph snapshot.
9. Вернуть primary и complement groups в существующем `product_group` формате и optional entity-resolution diagnostics без vectors.
10. Не отправлять выбор карточек в LLM.
11. Добавить feature flag и rollback на legacy/entity resolver off.

Gate 4: unit/contract tests проходят; exact bypass доказан; `off` и `shadow` сохраняют ordered product IDs; search работает без LLM API; недоступность Ollama не ломает запрос; legacy fallback идентичен baseline для непонятых запросов.

## Фаза 4B. Frontend API Integration — после Gate 4

Владелец: Frontend Agent.

1. Подключить `GET /api/search?q=...` по `docs/FRONTEND_CONTRACT.md`.
2. Сохранить Mock/API switch для автономной демонстрации.
3. Не менять компоненты карточек и групп при смене transport.
4. Показывать strategy, fallback, подтверждённую коррекцию/неоднозначность и artifact versions только в компактном debug/status блоке.
5. Не отображать пустую complement group; `data_gap` показывать отдельным нейтральным уведомлением.
6. Добавить frontend contract tests и keyboard/mobile checks.

Gate 4B: один fixture и эквивалентный API response дают одинаковую DOM-структуру результатов; loading/empty/error/fallback/data-gap проверены.

## Фаза 5. Независимая QA — последовательно после интеграции

Владелец: QA Agent.

1. Проверить catalog, aliases, entity index и graph schemas.
2. Запустить golden и regression suites.
3. Проверить отсутствие brand/type leaks.
4. Проверить пустые группы, дубликаты и zero-result.
5. Проверить наличие и валидность независимого Antigravity graph review; QA не переигрывает роль рецензента и не редактирует его выводы.
6. Выполнить browser smoke-test UI в Mock Mode и API Mode.
7. Проверить query submission мышью и Enter, фокус, mobile layout и безопасные внешние ссылки.
8. Проверить `Тикула`, exact bypass, `тик`, unknown, похожие SKU, timeout/missing model/stale index и parity `off|shadow`.
9. Выпустить `reports/release-v1.md` с go/no-go.

Gate 5: выполнены все критерии `docs/ACCEPTANCE_CRITERIA.md`; parser live report и graph coverage report приложены; critical defects отсутствуют. Отчёт без этих двух артефактов автоматически `NO-GO`.

## Фаза 6. Приёмка Lead

Lead сверяет версии catalog/aliases/graph/backend, команды воспроизведения, отчёт QA и rollback. Commit, push и публикация выполняются только по отдельному разрешению пользователя.

## Матрица handoff

| Откуда | Куда | Артефакт |
|---|---|---|
| Parser | Normalization | raw/staging records, source manifest, issues |
| Normalization | Graph | canonical taxonomy, category IDs, version |
| Normalization | Backend | canonical catalog, aliases, parser contract |
| Graph | Backend | approved graph snapshot, provenance manifest |
| Graph | Graph Semantic Reviewer | immutable review request с hashes и neighborhoods |
| Graph Semantic Reviewer | QA, Lead | независимые findings, PASS/REVIEW/FAIL, required changes |
| Backend | QA | runtime build, API contract, rollback command |
| Backend | Frontend | API endpoint, example response, error contract |
| Frontend | QA | mock/API demo, frontend tests, accessibility notes |
| QA | Lead | metrics, defects, Antigravity graph findings, go/no-go |

## Перезапуск

- Новые товары: повторить 1A → 2 → 3 при изменении taxonomy → 4 indexes → 5.
- Изменение aliases: повторить 1B → 4 → 5.
- Изменение только комплементов: повторить 3 → 4 snapshot reload → 5 graph tests.
- Изменение backend contract: повторить 4 → 4B → 5, не перестраивая данные без необходимости.
- Изменение только UI: повторить 1D/4B → 5 browser/frontend checks.
