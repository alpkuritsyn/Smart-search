Сейчас полный парсер ещё работает, поэтому промпт создаёт отдельный предварительный индекс текущего canonical-каталога и не перезаписывает будущий production-индекс.

Ты — Lead/Orchestrator проекта Smart-search. Не ограничивайся планированием: выполни задачу до построенного и проверенного embedding-индекса текущих позиций каталога.

## Цель

Прямо сейчас построить embeddings для всех товаров, которые уже находятся в:

`data/canonical/catalog.canonical.json`

Также проиндексировать утверждённые названия и aliases брендов из:

`config/search_aliases.json`

Нужно продемонстрировать исправление ошибочных названий:

- `Тикула → Tikkurila`;
- `Тиккурилла → Tikkurila`;
- `Tikkurilla → Tikkurila`;
- `тик` не должен автоматически исправляться;
- неизвестный бренд не должен превращаться в существующий;
- ошибочно написанное название товара должно возвращать подходящие SKU-кандидаты.

## Важное состояние проекта

Полный Product Parser сейчас работает в фоне. Не останавливай его, не удаляй lock/checkpoints и не редактируй:

- `data/raw/**`;
- `data/staging/**`;
- `reports/parser-ingestion.json`;
- файлы работающего parser-процесса.

Текущий embedding-индекс является предварительным индексом существующего canonical snapshot. После завершения полного парсинга и повторной нормализации его потребуется перестроить.

Не перезаписывай будущий production-файл `data/embeddings/entities.sqlite`. Для текущего запуска используй:

`data/embeddings/entities.current-canonical.sqlite`

## Обязательные инструкции

Сначала полностью прочитай:

1. `agents/00_shared_contract.md`;
2. `agents/01_lead_orchestrator.md`;
3. `agents/03_catalog_normalization.md`;
4. `agents/09_embedding_entity_resolution.md`;
5. `docs/EMBEDDING_ENTITY_RESOLUTION.md`;
6. `docs/ACCEPTANCE_CRITERIA.md`;
7. `config/embedding_resolver.json`;
8. `config/entity_resolution_cases.json`;
9. `src/ml/embedding_resolver.py`;
10. `tools/check_embedding_model.py`;
11. `tools/build_embedding_entity_index.py`;
12. `tools/validate_embedding_entity_index.py`;
13. `tools/evaluate_entity_resolution.py`.

Создай отдельного субагента по роли `agents/09_embedding_entity_resolution.md`. Передай ему shared contract, эту задачу и ownership из agent-файла.

## Модель

Используй только локальный Ollama и точный тег:

`qwen3-embedding:0.6b`

Не используй:

- `gemma4:e2b`;
- внешние embedding API;
- Gemini;
- OpenAI API;
- другую модель под тем же индексом;
- автоматическую подмену model tag.

Сначала выполни:

```powershell
python tools/check_embedding_model.py --model "qwen3-embedding:0.6b"
```

Если команда `python` недоступна, найди доступный Python 3.11+ или используй `uv run --python 3.12`.

Продолжай только если точный тег найден и `/api/embed` возвращает валидные нормализованные векторы одинаковой размерности.

## Подготовка входов

Перед построением:

1. Посчитай SHA-256 текущих файлов:

   - `data/canonical/catalog.canonical.json`;
   - `config/search_aliases.json`;
   - `config/embedding_resolver.json`.

2. Зафиксируй:

   - количество товаров;
   - количество товаров с непустым `name`;
   - количество уникальных товарных названий;
   - количество canonical brands;
   - количество authoritative brand aliases;
   - текущую версию normalization/aliases.

3. Не индексируй raw brand, если у него нет утверждённого canonical brand ID.

4. Не создавай новые бренды, aliases или товары с помощью модели.

## Построение индекса

Запусти полный build без `--limit`:

```powershell
python tools/build_embedding_entity_index.py `
  --catalog data/canonical/catalog.canonical.json `
  --aliases config/search_aliases.json `
  --config config/embedding_resolver.json `
  --output data/embeddings/entities.current-canonical.sqlite
```

Builder должен:

- использовать batch-запросы к локальному `/api/embed`;
- сохранять checkpoint;
- продолжать сборку после безопасного перезапуска;
- хранить SHA-256 входов, model tag, dimension и количество записей;
- повторно проверить hashes перед публикацией;
- атомарно опубликовать индекс только после полного прохода;
- не публиковать partial/smoke index как готовый;
- не мешать работающему Product Parser.

Если каталог или конфигурация изменились во время сборки, не публикуй индекс: сохрани checkpoint и перестрой его с актуальными hashes.

## Логика resolver

Exact aliases всегда проверяются до embeddings и не должны вызывать Ollama.

Для unresolved текста используй гибридную оценку:

- embedding similarity;
- character similarity;
- транслитерационную близость;
- minimum score;
- minimum margin относительно второго кандидата.

Для Qwen добавь на query-side подходящую instruction, если текущая реализация её ещё не поддерживает:

```text
Given a misspelled or transliterated Russian catalog entity name, retrieve the matching canonical brand or product name.
```

Canonical brand aliases и product names индексируй без query instruction.

Не добавляй `Тикула` в exact aliases ради прохождения теста. Этот пример должен пройти именно через embedding/hybrid resolver.

## Политика безопасности

Бренд разрешается автоматически только если одновременно:

- top-1 является authoritative canonical brand;
- score выше откалиброванного порога;
- margin выше откалиброванного порога;
- negative/collision tests не показывают ложных hard filters.

Для `product_name` оставь:

```json
"auto_resolve": false
```

Названия товаров должны возвращаться как candidates/safe boost. Не превращай найденный SKU в самостоятельный hard filter и не обходи brand/type/weight/volume filters.

Статусы `suggestion`, `ambiguous`, `unavailable` и `stale` не должны менять обычную выдачу.

## Калибровка

После построения выполни:

```powershell
python tools/validate_embedding_entity_index.py `
  --index data/embeddings/entities.current-canonical.sqlite `
  --catalog data/canonical/catalog.canonical.json `
  --aliases config/search_aliases.json `
  --config config/embedding_resolver.json
```

Затем:

```powershell
python tools/evaluate_entity_resolution.py `
  --index data/embeddings/entities.current-canonical.sqlite `
  --cases config/entity_resolution_cases.json `
  --report reports/evaluation/entity-resolution-current-canonical.json
```

Если `Тикула → Tikkurila` не проходит:

1. выведи top-5 кандидатов и разложение embedding/character/transliteration score;
2. проверь query instruction;
3. откалибруй веса и thresholds на всём positive/negative set;
4. не снижай порог только ради одного positive case;
5. не добавляй hardcode или специальное условие для Tikkurila;
6. после изменения конфигурации полностью перестрой индекс, поскольку config hash изменился.

Обязательно расширь evaluation cases следующими примерами:

- `Тикула`;
- `Тиккурилла`;
- `Tikkurilla`;
- `тикурила`;
- `tikkurila`;
- `тик`;
- `неизвестныйбренд`;
- `латексная краска` — не должна распознаваться как бренд `ТЕКС`;
- опечатка в названии Valtti Terrace Oil;
- похожие названия одной линейки с разными фасовками.

Release-критерий текущей сборки:

- `false_accepted_hard_filters = 0`;
- `Тикула → brand:tikkurila`;
- `тик` и неизвестный бренд остаются без hard filter;
- product-name candidates не обходят фасовку и другие hard filters.

## Демонстрационный CLI

Если в проекте ещё нет удобного CLI для запроса к индексу, добавь:

`tools/query_embedding_entity_index.py`

Пример запуска:

```powershell
python tools/query_embedding_entity_index.py `
  "Тикула" `
  --entity-type brand `
  --index data/embeddings/entities.current-canonical.sqlite `
  --top-k 5 `
  --json
```

CLI должен показывать:

- status;
- canonical ID/display;
- hybrid score;
- margin;
- embedding score;
- character score;
- transliteration score;
- top-5 candidates;
- model/index version.

Сырые embedding vectors не выводи.

## Проверки

Запусти:

- unit-тесты resolver;
- index validation;
- полный evaluation set;
- проверку exact bypass;
- missing-model/timeout fallback;
- stale-index test;
- повторный build/resume test;
- полный существующий pytest-набор проекта.

Не меняй golden expectations только для получения зелёных тестов.

## Итоговый handoff

Не останавливайся на плане. В конце предоставь:

1. путь к готовому индексу;
2. SHA-256 индекса и всех входов;
3. model tag и размерность vectors;
4. количество проиндексированных брендов, aliases и названий товаров;
5. результат `Тикула → Tikkurila`;
6. результат negative/ambiguous cases;
7. thresholds и веса после калибровки;
8. latency первого и прогретого запроса;
9. результаты всех тестов;
10. список изменённых файлов;
11. точные команды повторного запуска;
12. предупреждение, что это provisional index текущего canonical snapshot;
13. команду перестроения production-индекса после завершения полного Product Parser workflow.

Не выполняй commit, push или deploy.