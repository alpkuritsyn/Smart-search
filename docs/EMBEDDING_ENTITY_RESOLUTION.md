# Embedding Entity Resolution V1.1

## Назначение

Этот контур исправляет названия брендов и товаров, если пользователь написал их неточно: например, `краска Тикула` должна распознать бренд `Tikkurila`, после чего обычный V1-поиск применит строгие фильтры и добавит комплементы.

Это не semantic product search. Фраза вида `чем защитить доски от дождя` остаётся за пределами V1.1.

## Архитектура

```text
query
  → deterministic normalization / exact aliases
  → unresolved brand or product-name span
  → local embedding resolver
      → Ollama qwen3-embedding:0.6b
      → canonical entity index
      → embedding + character + transliteration rerank
      → score + margin gate
  → exact/resolved: hard filter
  → suggestion/ambiguous/unavailable: прежний deterministic/legacy path
```

## Источники истины

- Бренды: canonical IDs и aliases из `config/search_aliases.json`.
- Названия товаров: `id` и `name` из `data/canonical/catalog.canonical.json`.
- Runtime index: `data/embeddings/entities.sqlite`, построенный только из этих двух версионированных входов.

Модель не создаёт новые бренды, товары или aliases. Перестроение индекса обязательно после изменения hash любого входа или model tag.

## Модель и локальный API

Точный production/demo tag: `qwen3-embedding:0.6b`. Доступ только через локальный Ollama `http://127.0.0.1:11434/api/embed`. Внешние embedding API запрещены.

Перед построением:

```powershell
python tools/check_embedding_model.py --model "qwen3-embedding:0.6b"
```

Если модель ещё не установлена, после разрешения пользователя:

```powershell
ollama pull qwen3-embedding:0.6b
```

## Разделение ответственности

- Agent 03 выделяет unresolved spans и сохраняет exact alias приоритетным.
- Agent 09 строит индекс, resolver и калибрует ML-gates.
- Agent 05 вызывает resolver за feature flag и применяет hard filter только для `exact|resolved`.
- Agent 06 владеет immutable golden/negative set и принимает precision/rollback gates.
- Frontend только показывает `resolved`, `suggestion` или `ambiguous`; он не принимает решение.

## Политика решения

1. Exact alias/canonical match всегда побеждает и не вызывает модель.
2. Для unresolved span вычисляется embedding.
3. Кандидаты rerank-ятся комбинацией cosine similarity, character similarity и транслитерационной близости.
4. Auto-resolution разрешён только если top-1 прошёл и `minimum_score`, и `minimum_margin_over_second` для своего entity type.
5. Brand и product-name thresholds калибруются отдельно.
6. Ошибка Ollama, model mismatch, stale/partial index и timeout не являются ошибкой всего поиска: resolver возвращает `unavailable`.

Пороговые значения в конфигурации — стартовая гипотеза. QA утверждает их по фактическому evaluation report. Если precision gate не закрывается, `product_name` переводится в suggestions-only, а остальной поиск выпускается без него.

## Runtime contract

См. `contracts/entity_resolution.schema.json`. В диагностике search response должны быть:

- статус;
- matched span;
- canonical entity ID/display только при безопасном решении;
- top candidates с разложением score;
- model и index version;
- причина fallback.

Сырые embedding-векторы в API не возвращаются.

## Индекс и воспроизводимость

```powershell
python tools/build_embedding_entity_index.py
python tools/validate_embedding_entity_index.py
```

Builder пишет checkpoint в `data/embeddings/entities.building.sqlite` и публикует `entities.sqlite` атомарно только после полного успешного прохода. `--limit` разрешён для smoke, но такой индекс получает `complete=false` и не закрывает release gate.

## Минимальный evaluation set

Обязательные positive cases: `Тикула`, `Тиккурилла`, `Tikkurilla`, регистр, `ё/е`, пропуск и перестановка букв. Обязательные negative/collision cases: `тик`, неизвестный бренд, два близких бренда, общие слова из названия товара и похожие SKU.

Release gate: ни одна negative/ambiguous строка не должна создавать ложный hard filter. Для product names дополнительно проверяется, что не выбран другой SKU из похожей линейки.

## Rollback

`SMART_SEARCH_EMBEDDING_RESOLUTION=0` полностью отключает ML-вызов. Exact aliases, deterministic parser, legacy fallback и граф комплементов продолжают работать без Ollama и без embedding index.
