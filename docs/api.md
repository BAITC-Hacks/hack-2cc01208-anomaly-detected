# API контракт (frontend ↔ backend)

Базовый адрес: `http://localhost:8000`. CORS открыт (`allow_origins=["*"]`).

Запуск:
```powershell
pip install -r requirements.txt
uvicorn backend.main:app --reload
```
Swagger: `http://127.0.0.1:8000/docs`.

## Реализовано сейчас (v0.2)

### GET /health

```json
{"status": "ok", "contractors_loaded": 66}
```

### POST /match?limit=5

`limit` — необязательный, по умолчанию `5`, допустимо `1..20`.

Запрос (`MatchRequest`):

| поле | тип | обяз. | правило |
|---|---|---|---|
| `city` | str | да | жёсткий фильтр, без учёта регистра |
| `event_format` | str | да | жёсткий фильтр: `свадьба`, `корпоратив`, `юбилей`, `той`, `конференция`, `день рождения` |
| `event_date` | str | да | строго `YYYY-MM-DD`; подрядчик, у которого дата в `busy_dates`, **никогда** не возвращается |
| `budget_kzt` | int > 0 | нет | жёсткий фильтр `price_from_kzt <= budget_kzt` |
| `category` | str | нет | жёсткий фильтр, точное совпадение категории (`Ведущий` ≠ `Ведущий церемонии`) |
| `language` | str | нет | жёсткий фильтр |
| `duration_hours` | float > 0 | нет | жёсткий фильтр, если у подрядчика указан `max_hours` (пустой `max_hours` = неизвестно, не отсеивается) |
| `query` | str | нет | свободный текст потребности, влияет только на ранжирование |
| `services` | list[str] | нет | категории датасета, которые нужны (например, из AI-парсера); засчитываются как совпадение категории в релевантности, не фильтр |

```json
{
  "city": "Алматы",
  "event_format": "свадьба",
  "event_date": "2026-10-10",
  "budget_kzt": 500000,
  "query": "Нужен фотограф и видеограф на свадьбу"
}
```

Ответ (`POST /match?limit=1`, описание обрезано):

```json
{
  "request": {
    "city": "Алматы", "event_format": "свадьба", "event_date": "2026-10-10",
    "budget_kzt": 500000, "category": null, "language": null,
    "duration_hours": null, "query": "Нужен фотограф и видеограф на свадьбу"
  },
  "eligible_count": 10,
  "excluded": {"budget": 12, "busy_date": 19, "city": 16, "event_format": 9},
  "results": [
    {
      "contractor": {
        "id": "HK-30583",
        "name": "Леорио Паради",
        "categories": ["Фотограф"],
        "city": "Алматы",
        "price_from_kzt": 350000,
        "event_formats": ["свадьба", "корпоратив", "конференция"],
        "languages": ["русский", "английский"],
        "max_hours": 8.0,
        "synthetic": false,
        "price_imputed": false,
        "city_imputed": false,
        "description": "Всем привет. Меня зовут Леорио. Являюсь свадебным фотографом..."
      },
      "score": 0.775,
      "score_breakdown": {
        "mode": "relevance",
        "relevance": 0.9,
        "category_match": 1.0,
        "description_overlap": 0.5,
        "budget": 0.3,
        "confidence": 1.0,
        "specialization": 1.0,
        "total": 0.775,
        "matched_categories": ["Фотограф"],
        "matched_terms": ["фотограф"]
      }
    }
  ]
}
```

- `eligible_count` — сколько прошло все фильтры (может быть больше, чем `results`).
- `excluded` — сколько подрядчиков отсеял каждый фильтр (учитывается первое нарушенное правило):
  `city`, `event_format`, `busy_date`, `budget`, `category`, `language`, `duration`.
- 0 подходящих — это **не ошибка**: `200`, `"eligible_count": 0`, `"results": []`.
- Невалидный ввод (дата, бюджет ≤ 0, `duration_hours` ≤ 0, `limit` вне 1..20) → `422`.
- Одинаковый запрос → всегда одинаковый порядок и одинаковые баллы.

Ранжирование (детерминированное, без LLM), все компоненты 0..1:

- есть `query` или `category` → `mode: "relevance"`:
  `0.50·relevance + 0.25·budget + 0.15·confidence + 0.10·specialization`
- нет ни того, ни другого → `mode: "structured"`: `0.70·budget + 0.30·confidence`
- `relevance = 0.8·category_match + 0.2·description_overlap`
- `budget = max(0, 1 − price/budget)`; `confidence` = 0.4 (не synthetic) + 0.3 (цена не imputed) + 0.3 (город не imputed);
  `specialization` = доля категорий подрядчика, совпавших с запросом.
- Сортировка: `score` по убыванию, затем `id` по возрастанию.

Подробности — в `backend/matcher.py` и `backend/relevance.py`.

---

## Контракт фронта — POST /api/match (реализован)

> Адаптер (`backend/frontend_api.py`) над тем же движком, что и `/match`: только
> переименовывает поля и оформляет ответ. Для эквивалентных запросов `cards` —
> это ровно первые 3 результата `/match` в том же порядке (покрыто тестами).
>
> | фронт | `/match` |
> |---|---|
> | `date` | `event_date` |
> | `event_type` | `event_format` |
> | `hours` | `duration_hours` |
> | `city`, `category`, `budget_kzt`, `language` | те же |
>
> Уточнения к контракту ниже:
> - обязательны `city`, `date`, `event_type`; `category` и `budget_kzt` тоже можно не
>   передавать (тогда по ним нет фильтра);
> - необязательное расширение: `query` — свободный текст потребности (только ранжирование);
> - `excluded` считается среди кандидатов нужного города и категории — поэтому ключей
>   «не тот город/категория» в нём нет; если таких кандидатов 0 → `no_category`;
> - `explanation` — детерминированный текст только из данных датасета
>   (дата свободна, цена vs бюджет, формат, совпавшая категория/слова, язык, часы,
>   пометки «цена оценочная» / «профиль синтетический»);
> - если `ENABLE_LLM_EXPLANATIONS=true` и задан `GROQ_API_KEY` (`.env`, см. `.env.example`),
>   Groq переписывает **только текст** `explanation` для уже выбранных 3 карточек
>   (`backend/llm_explainer.py`). Состав, порядок и остальные поля карточек не меняются;
>   ответ LLM сопоставляется по `id` и проверяется (JSON, только known id, без дублей,
>   без чисел, которых нет в данных). Любая ошибка/таймаут → шаблонный текст.
>   Заголовок ответа `X-Explanations: llm | mixed | template` показывает, что использовано;
> - расширение «намерение услуги» (решает Python, не LLM; ранжирование не меняется):
>   если в `query` названа известная категория датасета («нужен ведущий», «фотограф и
>   видеограф»), ответ содержит
>   `"service_intent": {"requested": [...], "unavailable": [...], "not_in_top": [...]}`,
>   а каждая карточка — `"alternative": true|false` (true = не оказывает ни одну из
>   запрошенных услуг). Если ни одной запрошенной услуги среди подходящих нет,
>   `message` так и говорит, а `explanation` альтернатив начинается с
>   «Альтернатива (не «…»): ». `unavailable` — нет ни у одного подходящего подрядчика;
>   `not_in_top` — есть, но не в первой тройке. Без услуги в запросе или при явном
>   `category` (жёсткий фильтр) — `"service_intent": null`, все `alternative: false`;
> - расширение «понимание запроса» (`backend/intent_parser.py`, `ENABLE_LLM_INTENT`):
>   Groq извлекает из `query` только метки — услуги, язык (+ обязателен ли он), тип
>   события. Python оставляет только значения, которые есть в датасете, и применяет:
>   услуги → мягкий сигнал релевантности (не фильтр); язык → жёсткий фильтр **только**
>   если явно обязателен («обязательно», «должен») и поле `language` не прислано;
>   тип события — только для информации (`event_type` из формы главнее). При явном
>   `category` услуги из текста не применяются. Ответ содержит
>   `"interpreted_intent": {"services", "language", "language_required", "event_format",
>   "source": "llm"|"deterministic", "applied": [...]}` (`null`, если нет `query`).
>   Ошибка/таймаут/мусор от LLM → `source: "deterministic"`, поведение как без LLM.
>   Порядок карточек всегда совпадает с `POST /match` для итогового запроса
>   (у `/match` есть необязательное поле `services`);
> - невалидный ввод → `422`.

### POST /api/match

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

### GET /api/options (необязательно)

```json
{"cities":[...], "categories":[...], "event_formats":[...], "languages":[...]}
```
Если эндпоинта нет — фронт использует захардкоженные списки.
