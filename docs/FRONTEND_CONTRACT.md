# Frontend Contract V1

Frontend работает с одним JSON-форматом в Fixture Mode и API Mode.

Машиночитаемая схема: `contracts/search_response.schema.json`. Владельцем схемы является Lead/Integration; Frontend и Backend предлагают изменения через contract change request.

## Request

```http
GET /api/search?q=%D0%BA%D1%80%D0%B0%D1%81%D0%BA%D0%B0%20%D1%82%D0%B8%D0%BA%D1%83%D1%80%D0%B8%D0%BB%D0%B0
```

## Response

```json
{
  "query": {
    "raw": "краска тикурила",
    "normalized": "краска tikkurila",
    "brand_id": "brand:tikkurila",
    "brand_display": "Tikkurila",
    "product_type_id": "type:paint",
    "product_type_display": "Краска",
    "attributes": {},
    "unparsed_tokens": []
  },
  "primary": {
    "title": "Найденные краски Tikkurila",
    "products": []
  },
  "complements": [
    {
      "title": "Для подготовки: грунтовки",
      "relation": "PREPARE_WITH",
      "rationale": "Категория подготовки поверхности перед окрашиванием",
      "products": [],
      "data_gap": false
    }
  ],
  "meta": {
    "strategy": "deterministic_v1",
    "fallback_used": false,
    "catalog_version": "...",
    "aliases_version": "...",
    "graph_version": "...",
    "elapsed_ms": 12
  }
}
```

## Product

Обязательны `id`, `name`, `brand`, `price`, `category`, `subcategory`. `url` и `image` могут быть пустыми. Frontend не создаёт URL самостоятельно.

## States

- HTTP 200 + `primary.products=[]` → honest empty state.
- `fallback_used=true` → заметный, но нейтральный fallback badge.
- Complement `products=[]` + `data_gap=true` → data-gap notice, не пустой product row.
- Network/HTTP/schema error → error state с retry; предыдущие результаты не выдаются как новые.
- `meta` и debug details не влияют на пользовательское ранжирование.

## Contract ownership

Lead утверждает контракт, Backend реализует producer, Frontend реализует consumer, QA владеет parity/contract tests.
