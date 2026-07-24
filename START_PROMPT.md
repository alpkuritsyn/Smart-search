# Стартовый промпт для Antigravity

Ты — Lead/Orchestrator проекта Smart-search V1. У тебя есть доступ ко всем файлам текущего Project, терминалу, браузеру и субагентам. Не ограничивайся планом: организуй агентов, реализуй V1, проверь его и подготовь демонстрацию.

Перед любыми изменениями полностью прочитай:

1. `README.md`;
2. `docs/SCOPE_V1.md`;
3. `docs/ACCEPTANCE_CRITERIA.md`;
4. `WORKFLOW.md`;
5. `agents/00_shared_contract.md`;
6. файлы всех агентов, которых будешь запускать.

## Результат

Нужно получить детерминированный поиск:

- «краска тикурила» и «краска tikkurila» → краски Tikkurila;
- «краска Тикула» → high-confidence исправление бренда в Tikkurila локальным embedding resolver;
- «грунтовка dulux» → грунтовки Dulux;
- «лак для дерева» → лаки для дерева;
- «шпаклевка 20 кг» → шпатлёвки нужной фасовки;
- после основного блока показываются отдельные комплементы, например грунтовки, шпатлёвки и инструменты нанесения;
- если запрос не распознан, используется неизменённый legacy fallback.

## Жёсткие границы V1.1

Разрешены локальные embeddings только для entity resolution опечаток в canonical брендах и названиях существующих товаров. Используй точный тег Ollama `qwen3-embedding:0.6b`, exact-first и гибридный reranking; это не общий semantic search. Не добавляй vector DB, RAG, поиск по пользовательской задаче, консультанта, генерацию технологии ремонта или LLM-ранжирование. Embeddings не выбирают комплементы и не утверждают совместимость SKU. При недоступной модели, stale index, низком score или малом margin сохраняй прежний deterministic/legacy путь.

Не используй LLM для создания production-рёбер графа. Graphify/Ollama `gemma4:e2b` используются только в offline-процессе графа. Семантическую проверку выполняет отдельный субагент Antigravity своими силами по `agents/08_graph_semantic_reviewer.md`; внешние LLM API для этого gate запрещены.

## Команда агентов

Создай субагентов по определениям:

- `agents/02_product_parser.md` — все публичные товары Remplanika из полного `/catalog/`;
- `agents/03_catalog_normalization.md` — канонический каталог, aliases и deterministic NLP;
- `agents/09_embedding_entity_resolution.md` — локальный индекс и безопасное исправление брендов/названий;
- `agents/04_complement_graph.md` — граф комплементов и Graphify/Ollama;
- `agents/05_backend.md` — runtime-поиск и API;
- `agents/06_qa_verification.md` — независимая release-проверка;
- `agents/08_graph_semantic_reviewer.md` — независимая семантическая проверка графа силами Antigravity.
- `agents/07_frontend.md` — простой web UI, mock-first fixtures и интеграция с search API.

Сам действуй по `agents/01_lead_orchestrator.md`.

Не допускай одновременной записи двух агентов в один файл. Product Parser, Catalog Normalization, QA Early и Frontend Mock Mode могут начать параллельно. Frontend сначала работает только по `docs/FRONTEND_CONTRACT.md` и fixtures, не ожидая backend. После полного parser/canonical gate запусти Complement Graph и Embedding Entity Resolution параллельно: их owned paths не пересекаются. Backend ждёт оба handoff, если embedding feature включается. QA не исправляет production-код.

## Обязательный порядок

1. Зафиксируй baseline и список пользовательских изменений. Ничего не стирай и не коммить без разрешения.
2. Создай implementation plan и ownership matrix.
3. Выполни workflow из `WORKFLOW.md` с фазовыми воротами.
4. Для Graphify используй `tools/run_graphify_ollama.ps1` с моделью `gemma4:e2b`. Не заменяй модель молча. Если тег отсутствует, зафиксируй блокер и точную команду проверки.
5. После завершения полного parser run и выпуска нового canonical snapshot запусти Agent 09. Проверь точный embedding tag командой `python tools/check_embedding_model.py --model "qwen3-embedding:0.6b"`. Если модели нет, не скачивай и не подменяй её без разрешения; верни точную команду `ollama pull qwen3-embedding:0.6b`. Построй и проверь индекс, откалибруй score/margin на golden/negative set. Product names в первом релизе используют только safe boost/suggestions, не самостоятельный hard filter.
6. Проверь граф детерминированно, затем подготовь review-пакет через `tools/prepare_antigravity_graph_review.py` и запусти отдельного субагента Antigravity строго по `agents/08_graph_semantic_reviewer.md`. Не проси Gemini и не вызывай внешний LLM API. Рецензент работает в отдельном контексте от автора графа, пишет только findings и не имеет права автоматически утверждать или редактировать рёбра.
   После handoff проверь отчёт командой `tools/validate_antigravity_graph_review.py`. Если отдельный субагент не был реально запущен или его отчёт не прошёл контракт, результат `NOT_RUN`, production release — `NO-GO`; Lead не вправе имитировать независимую проверку в своём контексте.
7. Поручи Frontend Agent сделать и проверить mock-first интерфейс: поле запроса, normalized/debug chips, entity correction/ambiguity, primary cards, отдельные complement groups, relation/rationale, strategy/fallback indicator и loading/empty/error states. Он должен использовать один контракт для fixtures и реального API.
8. После backend handoff переключи UI из Mock Mode в API Mode без изменения компонентов выдачи.
9. Запусти unit, regression, contract и smoke tests, включая exact bypass, `Тикула`, `тик`, timeout/missing model/stale index и режимы `off|shadow|apply`.
10. Проведи браузерную проверку минимум на контрольных запросах из `docs/ACCEPTANCE_CRITERIA.md`.
11. Подготовь release report: файлы, версии данных/индекса/модели, тесты, метрики, ограничения, инструкция демонстрации и rollback.

## Политика источников парсинга

Парси только источники, на которые есть разрешение и которые перечислены в `config/parser_sources.json`. Соблюдай robots.txt, rate limits и условия источника; не обходи авторизацию, CAPTCHA и технические ограничения. Каждая новая карточка должна иметь source URL, дату получения, locator и content hash. Отсутствующие значения остаются `null`; запрещено достраивать их моделью.

Запрещено заменять парсер массивом правдоподобных товаров. Для Remplanika используй весь опубликованный `sitemap_iblock_7.xml`, `allowed_paths=["/catalog/"]` и все leaf URL без query-параметров, разрешённые robots.txt. Нельзя ограничивать импорт красками, ЛКМ, кистями, валиками, приоритетными категориями или regex по slug. Сохрани raw HTML, checkpoints и `reports/parser-ingestion.json`. На первом запуске `new_unique_products` обязан быть больше нуля; иначе workflow получает `NO-GO`.

## Definition of Done

Работа завершена только если:

- основной поиск не зависит от LLM API;
- `Тикула` безопасно сопоставляется с `Tikkurila` локальной embedding-моделью после QA-калибровки;
- exact aliases не вызывают модель, а `тик`/unknown/timeout/stale index не создают ложный hard filter;
- feature flag `off` полностью восстанавливает прежний порядок primary results;
- распознанные бренд и тип являются жёсткими фильтрами;
- комплементы не меняют основной блок;
- legacy fallback сохранён и покрыт regression-тестами;
- нет пустых и дублирующихся групп;
- все опубликованные рёбра графа проходят structural validation и имеют provenance/review status;
- новые карточки инструментов реально получены с Remplanika и подтверждены raw snapshots; data gap не считается выполнением parser-задачи;
- parser report подтверждает `catalog_scope_complete=true`, `manifest_complete=true` и обработку всего leaf manifest `/catalog/`, а не выбранного раздела;
- `reports/catalog-graph-coverage.json` показывает 100% outgoing coverage для типов и товаров заявленного V1 scope и 0 пустых targets;
- отдельно указана общая доля каталога с `product_type_id`; её нельзя выдавать за покрытие всего каталога;
- web/demo показывает primary и complement выдачу сначала на fixture, затем на том же backend contract;
- UI имеет loading, empty, data-gap, error и fallback states и не формулирует category relation как SKU compatibility;
- все тесты и демонстрационный сценарий воспроизводимы.

Не останавливайся после подготовки артефакта-плана. Продолжай до работающего проверенного результата либо до конкретного внешнего блокера, который нельзя устранить безопасно.
