# Shared Contract — Smart-search V1

## Миссия команды

Построить воспроизводимый детерминированный поиск по товарному каталогу и отдельную выдачу проверенных комплементарных категорий. Основной результат не должен зависеть от LLM.

## Sources of truth

1. `docs/SCOPE_V1.md` — продуктовые границы.
2. `docs/ACCEPTANCE_CRITERIA.md` — release gates.
3. Утверждённые JSON Schema/API contracts.
4. Версионированные canonical catalog, aliases и approved complement graph.
5. Исходный snapshot — только вход, не место ручных исправлений.

## Общие правила

- Прочитать этот контракт и собственный agent-файл полностью до действий.
- Редактировать только owned paths. Для чужого файла отправлять Lead change request.
- Unknown is unknown: не достраивать факты по названию или правдоподобию.
- Raw и canonical значения связывать через стабильные IDs и provenance.
- Generated snapshots не редактировать вручную.
- Не смешивать аналог, комплемент и совместимость.
- LLM/Graphify могут предложить candidate edge, но production требует детерминированной проверки и review.
- Локальные embeddings разрешены только для сопоставления unresolved текста с уже существующим canonical brand/product ID. Exact aliases всегда приоритетнее; сомнительное решение не становится hard filter.
- Frontend визуализирует ответ и не реализует normalization, ranking, fallback или graph semantics на клиенте.
- Не использовать секреты в коде, логах, fixtures или отчётах.
- Не выполнять commit, push, deploy, массовое удаление или изменение внешних систем без разрешения.

## Handoff format

Каждый агент завершает фазу файлом отчёта со следующими разделами:

- role и phase;
- input artifact versions и SHA-256;
- созданные/изменённые файлы;
- команды воспроизведения;
- результаты проверок и KPI;
- unresolved issues и severity;
- допустимые следующие потребители;
- rollback/cleanup.

## Severity

- Critical: неправильный жёсткий фильтр, выдуманный товар/URL, непроверенное production-ребро, утечка секрета, невоспроизводимый snapshot.
- High: заметная потеря legacy результатов, массовая ошибка парсинга/склейки, dangling graph nodes.
- Medium: отдельный alias conflict, неполная категория, ухудшение ранжирования без hard-filter leak.
- Low: оформление, диагностическое сообщение, некритичный недостающий пример.

## Definition of Ready для Backend

Backend начинает интеграцию только после получения:

- canonical catalog version;
- aliases/taxonomy version;
- query parser contract;
- при включении resolver: validated entity index, model/config/catalog/aliases hashes, calibration report и mode `shadow|apply`;
- approved complement graph version;
- golden queries и frozen legacy baseline.

Если embedding handoff не готов, Backend обязан продолжить с resolver mode `off`; это не разрешает имитировать индекс или ослаблять deterministic gates.

Frontend начинает Mock Mode после утверждения `docs/FRONTEND_CONTRACT.md` и canonical fixtures; API Mode — только после backend contract handoff.
