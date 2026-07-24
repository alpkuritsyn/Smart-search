# Smart-search V1 — Always On Rule

- V1.1 — deterministic lexical/catalog search plus approved complementary-category graph и узкий local embedding entity resolver.
- Embeddings разрешены только для сопоставления опечаток с canonical brand/product IDs. RAG, общий semantic retrieval, vector DB, консультант и embedding-выбор комплементов запрещены.
- Exact aliases имеют приоритет; низкая confidence, timeout или stale index не создают hard filter и возвращают прежний путь.
- LLM не создаёт runtime-выдачу и не утверждает production graph edges.
- Не придумывать товарные поля. Неизвестное значение — `null` или issue.
- Сохранять provenance для новых товаров и графовых связей.
- Не редактировать source snapshots и generated snapshots вручную.
- Один production-файл имеет одного активного owner.
- Сохранять legacy fallback и проверять его regression-тестами.
- Не читать и не публиковать реальные `.env`/API keys.
- Frontend только визуализирует утверждённый response contract; search/ranking/relation logic на клиенте запрещена.
- Не commit/push/deploy без отдельного разрешения.
