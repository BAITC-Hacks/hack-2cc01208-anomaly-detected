# API контракт (frontend ↔ backend)

Базовый адрес: `http://localhost:8000`. Бэкенд должен разрешать CORS для фронта
(`http://localhost:5500` и `null` для открытия index.html как файла) — проще всего `allow_origins=["*"]`.

## POST /api/match

Запрос:
```json
{"city":"Алматы","date":"2026-11-14","event_type":"свадьба","category":"Ведущий",
 "budget_kzt":300000,"hours":5,"language":"казахский"}
```
`hours` и `language` — необязательные (поля может не быть).

Ответ:
```json
{"status":"found|no_category|none_fit","message":"...",
 "cards":[{"id":"c_012","name":"...","category":"...","city":"...","price_from_kzt":250000,
           "synthetic":false,"explanation":"..."}],
 "excluded":{"busy_on_date":4,"over_budget":2,"wrong_format":1,"wrong_language":0,"too_few_hours":0}}
```

- `found` — от 1 до 3 карточек; если меньше 3, `message` объясняет почему.
- `no_category` — такой категории в этом городе нет; `cards` пустой.
- `none_fit` — кандидаты есть, но никто не прошёл фильтры; `message` + `excluded`.
- `excluded` возвращается всегда (и при `found` тоже).
- Одинаковый запрос → всегда одинаковый порядок карточек.

## GET /api/options (необязательно)

```json
{"cities":[...], "categories":[...], "event_formats":[...], "languages":[...]}
```
Если эндпоинта нет — фронт использует захардкоженные списки.
