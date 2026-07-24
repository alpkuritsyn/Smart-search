# Acceptance Criteria

## Контрольные запросы

| Запрос | Обязательная проверка |
|---|---|
| `краска тикурила` | primary: тип краска, бренд Tikkurila |
| `краска tikkurila` | тот же canonical brand |
| `краска Тикула` | high-confidence entity resolution: canonical brand Tikkurila; primary не содержит другие бренды |
| `тикурила краска` | порядок слов не влияет на slots |
| `грунтовка dulux` | primary: грунтовка и Dulux |
| `лак для дерева` | primary не содержит очевидно нерелевантные типы |
| `шпаклевка 20 кг` | type и size являются hard filters при наличии структурированного веса |
| точный SKU | SKU находится не хуже legacy |
| неизвестный бренд | система не придумывает canonical brand |
| `тик` | остаётся unresolved/ambiguous и не создаёт brand hard filter |
| опечатка в названии товара | кандидат поднимается только при явном победителе и не нарушает уже распознанные brand/type/size filters |
| непонятый запрос | frozen legacy fallback |

## Primary invariants

- Все товары удовлетворяют распознанным brand/type hard filters.
- Не более одной карточки на product ID.
- Primary формируется до и независимо от complement traversal.
- Низкая confidence не превращается в hard filter.
- LLM API недоступен — primary всё равно работает.
- Exact alias не вызывает embedding provider и сохраняет прежний порядок выдачи.
- `off` и `shadow` режимы entity resolver не меняют ordered primary IDs.
- Timeout, отсутствующая модель или stale index возвращают прежний deterministic/legacy результат с HTTP 200.
- Product-name resolution в первом релизе не является самостоятельным hard filter: это только безопасный boost кандидатов после пересечения с hard filters.

## Entity resolution gates

- Точный model tag: `qwen3-embedding:0.6b`; молчаливая подмена запрещена.
- Индекс имеет `status=complete`, совпадающие catalog/aliases/config hashes и одну размерность vectors.
- Все authoritative brand aliases и все canonical product names присутствуют в индексе.
- Exact match всегда побеждает ML.
- Auto-accepted brand precision = 100% на immutable golden/negative set; false accepted hard filters = 0.
- Решение проходит одновременно `minimum_score` и `minimum_margin_over_second`.
- Сырые raw brands без canonical ID не получают право hard filter.
- Сырые embedding vectors не возвращаются в API.
- P95 exact-path измеряется отдельно и не ухудшается из-за запуска Ollama; typo-path latency публикуется отдельно.

## Complement invariants

- Комплементы находятся в отдельных группах.
- Primary brand не переносится на complements.
- Пустая категория не создаёт пустой product group.
- Ребро имеет relation, rationale, provenance и approved review status.
- UI не формулирует category edge как гарантию совместимости конкретных SKU.

## Parser gates

- Source manifest утверждён.
- Parser действительно выполняет HTTP-запросы к разрешённым публичным URL; массивы тестовых товаров в production-коде запрещены.
- Discovery выполняется из опубликованного sitemap, а не через запрещённую robots.txt query-пагинацию.
- `reports/parser-ingestion.json`: `fetched_pages > 0`, `parsed_products > 0`, а для первого запуска `new_unique_products > 0`.
- Полный gate требует `full_run=true`, попытку обработки всего selected manifest и parse success не ниже policy threshold; bounded smoke не закрывает gate.
- Discovery/staged/error counts сходятся, и каждый staged URL присутствовал в discovery manifest.
- 100% записей имеют provenance и content hash.
- 100% записей имеют `source_url` и существующий gzip raw snapshot фактически полученной HTML-страницы.
- Повторный запуск идемпотентен.
- Отсутствующие значения не сгенерированы.
- Отсутствие реальных карточек целевой категории — `NO-GO`, а не допустимый успешный release.

## Coverage gates

- Общая доля каталога с `product_type_id` публикуется числом; её нельзя называть полным покрытием.
- Для всех типов из `config/release_scope.v1.json`, у которых есть товары, существуют graph nodes и хотя бы одно approved исходящее ребро.
- Покрытие исходящими рёбрами: 100% типов и 100% товаров внутри заявленного V1 scope.
- Каждая target-категория опубликованного ребра разрешается хотя бы в один реальный canonical product.
- Проверка выполняется `tools/validate_catalog_graph_coverage.py`; наличие валидного JSON само по себе не считается покрытием.

## Frontend gates

- Есть поле запроса, submit по кнопке и Enter, примеры запросов и понятный loading state.
- Отдельно отображаются normalized query, распознанные brand/type/size и strategy/fallback.
- Primary grid визуально отделён от complement groups.
- У complement group видны relation и безопасный rationale без обещания совместимости SKU.
- Fixture Mode и API Mode используют один renderer; эквивалентные ответы выглядят одинаково.
- Empty/error/data-gap состояния не маскируются случайными товарами.
- Пустая complement group не отображается как ряд карточек.
- Товарная ссылка безопасно открывается только при наличии разрешённого URL.
- Интерфейс usable с клавиатуры и на ширине 360 px.

## Release gates

- Catalog schema: 100% pass.
- Alias collisions: 0 unresolved в published file.
- Graph dangling nodes: 0.
- Published graph edges without approval/provenance: 0.
- Parser live-ingestion gate: PASS.
- Scoped graph type/product outgoing coverage: 100%/100%.
- Empty approved edge targets: 0.
- Hard-filter precision на golden set: 100%.
- Legacy fallback regression: 100% frozen cases.
- Embedding entity index validation: PASS либо feature flag остаётся `off`; деградация не блокирует deterministic V1.
- False accepted entity hard filters: 0.
- Critical/High defects: 0.
- Feature-flag rollback проверен.
