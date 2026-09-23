// Mock-ответы для демо-режима (когда бэкенд недоступен).
// Готовые ответы для демо-запросов посчитаны вручную по data/hackathon-dataset-anonymized:
// кто занят на дату, кто дороже бюджета, кто не берёт формат.
// Для всех остальных запросов — простые правила, чтобы показать все 3 исхода.

const MOCK_RESPONSES = {
  // 1 · Ведущий, Алматы, 17.10, свадьба, 1 000 000 — плотная категория, ранжирование работает
  "Ведущий|Алматы|2026-10-17|1000000": {
    status: "found",
    message: "Подобрали 3 ведущих из 10 в Алматы.",
    cards: [
      { id: "HK-42352", name: "Эмилия", category: "Ведущий", city: "Алматы", price_from_kzt: 900000, synthetic: false,
        explanation: "Ведёт только свадьбы и тои: 13 лет опыта и 356 свадеб. Свободна 17.10, работает на русском и казахском, цена от 900 000 ₸ укладывается в бюджет с запасом 100 000 ₸." },
      { id: "HK-35215", name: "Кики", category: "Ведущий", city: "Алматы", price_from_kzt: 900000, synthetic: false,
        explanation: "Единственный из свободных ведёт на трёх языках (казахский, русский, английский), подходит для смешанных гостей. В описании отдельно указаны свадебные обряды: проводы невесты, первые шаги." },
      { id: "HK-77838", name: "Хаул", category: "Ведущий", city: "Алматы", price_from_kzt: 1000000, synthetic: false,
        explanation: "Актёр театра и телеведущий со спокойной интеллигентной подачей. Для свадеб подходит тем, кому не нужен шумный конкурсный формат. Цена от 1 000 000 ₸ ровно по верхней границе бюджета." }
    ],
    excluded: { busy_on_date: 5, over_budget: 1, wrong_format: 1, wrong_language: 0, too_few_hours: 0 },
    excluded_list: [{ name: "Куррапика", reason: "busy_on_date" }, { name: "Мицури Канроджи", reason: "busy_on_date" }, { name: "Сон Гоку", reason: "busy_on_date" }, { name: "Джинбей", reason: "busy_on_date" }, { name: "Аня Форджер", reason: "busy_on_date" }, { name: "Софи Хаттер", reason: "over_budget" }, { name: "Буллма", reason: "wrong_format" }]
  },

  // 2 · Флорист, Алматы, 17.10, свадьба, 300 000 — редкая категория, 1 карточка
  "Флорист|Алматы|2026-10-17|300000": {
    status: "found",
    message: "Нашёлся только 1 флорист: в Алматы их всего 2, второй занят 17.10.",
    cards: [
      { id: "HK-90001", name: "Тихиро Огино", category: "Флорист", city: "Алматы", price_from_kzt: 250000, synthetic: true,
        explanation: "Специализируется на свадьбах и собирает композиции под цветовую палитру: от букета невесты до стола молодожёнов. Свободна 17.10, цена от 250 000 ₸ в пределах бюджета." }
    ],
    excluded: { busy_on_date: 1, over_budget: 0, wrong_format: 0, wrong_language: 0, too_few_hours: 0 },
    excluded_list: [{ name: "Тони Тони Чоппер", reason: "busy_on_date" }]
  },

  // 3 · Тот же запрос, что №1, но 26.12 — видно, что всё решает занятость
  "Ведущий|Алматы|2026-12-26|1000000": {
    status: "found",
    message: "Нашёлся только 1 ведущий: 26.12 — пик сезона, 9 из 10 ведущих Алматы в эту дату заняты.",
    cards: [
      { id: "HK-44923", name: "Мицури Канроджи", category: "Ведущий", city: "Алматы", price_from_kzt: 650000, synthetic: false,
        explanation: "Единственный ведущий Алматы, свободный 26.12. Пишет сценарий под пару и сам привозит DJ и оборудование. Цена от 650 000 ₸, на 350 000 ₸ ниже бюджета." }
    ],
    excluded: { busy_on_date: 9, over_budget: 0, wrong_format: 0, wrong_language: 0, too_few_hours: 0 },
    excluded_list: [{ name: "Буллма", reason: "busy_on_date" }, { name: "Куррапика", reason: "busy_on_date" }, { name: "Эмилия", reason: "busy_on_date" }, { name: "Кики", reason: "busy_on_date" }, { name: "Хаул", reason: "busy_on_date" }, { name: "Софи Хаттер", reason: "busy_on_date" }, { name: "Сон Гоку", reason: "busy_on_date" }, { name: "Джинбей", reason: "busy_on_date" }, { name: "Аня Форджер", reason: "busy_on_date" }]
  },

  // 4 · Флорист, Алматы, 17.10, свадьба, 200 000 — кандидаты есть, никто не прошёл
  "Флорист|Алматы|2026-10-17|200000": {
    status: "none_fit",
    message: "В Алматы 2 флориста, но ни один не подходит: один занят 17.10, второй начинает от 250 000 ₸. Увеличьте бюджет до 250 000 ₸ или выберите другую дату.",
    cards: [],
    excluded: { busy_on_date: 1, over_budget: 1, wrong_format: 0, wrong_language: 0, too_few_hours: 0 },
    excluded_list: [{ name: "Тони Тони Чоппер", reason: "busy_on_date" }, { name: "Тихиро Огино", reason: "over_budget" }]
  },

  // 5 · Банкетный зал, Зарубежье — такой категории в городе нет
  "Банкетный зал|Зарубежье|2026-11-14|100000": {
    status: "no_category",
    message: "В каталоге «Зарубежье» нет банкетных залов. Там есть только фотографы.",
    cards: [],
    excluded: { busy_on_date: 0, over_budget: 0, wrong_format: 0, wrong_language: 0, too_few_hours: 0 }
  }
};

// Правила для запросов, которых нет в списке выше.
function mockMatch(req) {
  const key = [req.category, req.city, req.date, req.budget_kzt].join("|");
  if (MOCK_RESPONSES[key]) return MOCK_RESPONSES[key];

  if (req.city === "Зарубежье" && req.category !== "Фотограф") {
    return {
      status: "no_category",
      message: `В каталоге «Зарубежье» нет категории «${req.category}».`,
      cards: [],
      excluded: { busy_on_date: 0, over_budget: 0, wrong_format: 0, wrong_language: 0, too_few_hours: 0 }
    };
  }

  if (req.date >= "2026-12-15") {
    return {
      status: "none_fit",
      message: "Во второй половине декабря заняты почти все: это пик сезона. Попробуйте другую дату.",
      cards: [],
      excluded: { busy_on_date: 4, over_budget: 1, wrong_format: 0, wrong_language: 0, too_few_hours: 0 }
    };
  }

  return {
    status: "found",
    message: "Mock-ответ: подобрали 2 подрядчика, третий занят в эту дату.",
    cards: [
      { id: "mock_1", name: "Пример А", category: req.category, city: req.city, price_from_kzt: Math.round(req.budget_kzt * 0.8), synthetic: true,
        explanation: `Берёт формат «${req.event_type}» и свободен в выбранную дату. Цена на 20% ниже бюджета.` },
      { id: "mock_2", name: "Пример Б", category: req.category, city: req.city, price_from_kzt: req.budget_kzt, synthetic: true,
        explanation: "Цена ровно по бюджету. В описании указан опыт с такими мероприятиями." }
    ],
    excluded: { busy_on_date: 1, over_budget: 0, wrong_format: 0, wrong_language: 0, too_few_hours: 0 }
  };
}
