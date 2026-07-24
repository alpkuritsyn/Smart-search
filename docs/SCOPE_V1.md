# Scope Smart-search V1

## Пользовательская задача

Пользователь знает примерный тип товара и, возможно, бренд или простой параметр. Система должна исправить безопасные варианты написания, найти правильные товары и отдельно предложить комплементарные категории.

## In scope

- Unicode/lowercase, `ё/е`, пробелы, пунктуация.
- Brand aliases и транслитерация.
- Локальный embedding entity resolution для опечаток в брендах и названиях существующих товаров.
- Гибридный confidence gate: embeddings + символьная близость + транслитерация; exact aliases всегда приоритетнее.
- Product type synonyms.
- Простые параметры из текста: вес и объём, если они представлены в каталоге.
- Безопасная high-confidence коррекция опечаток.
- Deterministic primary retrieval с hard filters.
- Legacy fallback для непонятых запросов.
- Directed category/type complement graph.
- Парсинг всех публичных товарных карточек Remplanika из полного `/catalog/` утверждённого sitemap; category allowlist запрещён.
- Separate primary/complement response groups.
- Простой mock-first web UI для визуализации primary/complement pipeline и последующего подключения к тому же API contract.
- Offline Graphify/Ollama build и независимый semantic review отдельным субагентом Antigravity без внешнего LLM API.

## Out of scope

- Общий semantic retrieval по смыслу пользовательской задачи и отдельная vector DB.
- Использование embeddings для выбора комплементов, совместимости SKU или генерации технологии.
- RAG и поиск по инструкциям.
- ИИ-консультант и построение технологии работ.
- Автоматическая гарантия совместимости конкретных SKU.
- LLM ranking или LLM selection of cards.
- Автоматическое добавление graph edges моделью.
- Live stocks/ERP, checkout и production deployment.

## Термины

- Primary — товары, непосредственно соответствующие запросу.
- Complement — другая категория, полезная вместе или на соседнем этапе.
- Hard filter — распознанное ограничение, которое нельзя ослаблять для заполнения выдачи.
- Legacy fallback — существующий `retrieve_relevant_products()` без изменения поведения для непонятых запросов.
- Approved edge — ребро с provenance, review и допуском в runtime snapshot.
- Entity resolution — сопоставление ошибочного написания с уже существующим canonical brand/product ID; не поиск товара по задаче.

## Нефункциональные требования

- Один query + одинаковые версии данных → одинаковый primary result.
- Runtime поиск работает без LLM credentials.
- Все data/graph snapshots версионированы и воспроизводимы.
- Парсер инкрементальный, уважает источники и хранит provenance.
- Изменение графа не должно изменять primary ranking.
- Fixture mode и API mode должны использовать один renderer и один response contract.
- Ollama/embedding index могут быть отключены: exact aliases, deterministic retrieval и legacy fallback при этом сохраняются.
