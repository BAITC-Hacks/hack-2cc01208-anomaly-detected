// Переводы интерфейса: RU / KZ / EN. Без библиотек.
// t("key", ...args) — строка на текущем языке; значение словаря может быть функцией (числа, падежи).
// vl(value) — подпись для значения из API (город, формат, категория, язык).
// В API всегда уходят русские значения — переводятся только подписи.

// Русское множественное число: ruPlural(5, "подрядчик", "подрядчика", "подрядчиков") → "подрядчиков"
function ruPlural(n, one, few, many) {
  const d = n % 10, dd = n % 100;
  if (d === 1 && dd !== 11) return one;
  if (d >= 2 && d <= 4 && (dd < 12 || dd > 14)) return few;
  return many;
}
const ruOne = (n) => n % 10 === 1 && n % 100 !== 11;
// Английский: 1 — единственное, остальное — множественное
const enPl = (n, one, other) => (n === 1 ? one : other);
// Казахский: после числа существительное не меняется («5 мердігер»)

const I18N = {
  ru: {
    title: "Подбор подрядчиков",
    subtitle: "До 3 подрядчиков из каталога города и объяснение, почему каждый подходит",
    demoMode: "Демо-режим",
    demoHint: "Работать без бэкенда, на локальных примерах",
    uiLang: "Язык интерфейса",

    formTitle: "Параметры ивента",
    formSub: "Алгоритм выберет максимум 3 лучших совпадения",
    city: "Город проведения",
    date: "Дата события",
    eventType: "Формат события",
    category: "Категория специалиста",
    budget: "Максимальный бюджет",
    budgetPh: "например, 500000",
    upTo: (x) => `до ${x} ₸`,
    hours: "Длительность программы, ч",
    hoursPh: "например, 6",
    optional: "необяз.",
    language: "Язык ведения",
    anyLang: "любой",
    submit: "Подобрать",
    submitting: "Подбираем…",

    shortcuts: "Быстрые демо-запросы",
    preset1: "1 · Популярная категория, осень",
    preset2: "2 · Редкая категория",
    preset3: "3 · То же, что №1, но в декабре",
    preset4: "4 · Кандидаты есть, но не подходят",
    preset5: "5 · Категории нет в городе",
    empty: "Заполните параметры заказа или выберите демо-запрос",
    loading: "Подбираем подрядчиков… это может занять до 10 секунд",
    mockNote: "Демо-режим: ответ из локальных mock-данных, не с сервера.",

    errTimeout: "Сервер не ответил за 15 секунд. Попробуйте ещё раз.",
    errNetwork: (api) => `Не удалось связаться с сервером (${api}). Запустите бэкенд или включите «Демо-режим» вверху справа.`,
    errStatus: (code) => `Сервер вернул ошибку (код ${code}). Проверьте параметры запроса.`,
    errFormat: "Сервер вернул ответ в неожиданном формате.",
    errSameDate: "Выберите другую дату для сравнения.",
    // Проверка полей формы (вместо встроенных подсказок браузера — они на языке браузера)
    vRequired: "Заполните это поле.",
    vMin: (v) => `Значение должно быть не меньше ${v}.`,
    vMax: (v) => `Значение должно быть не больше ${v}.`,
    vNumber: "Введите число.",
    vWhole: "Введите целое число.",

    synthetic: "синтетический профиль",
    price: "Стоимость",
    priceFrom: (x) => `от ${x} ₸`,
    whyAria: "Почему именно этот подрядчик",
    explNote: "",
    hoursShort: (h) => `${h} ч`,

    excludedLabel: (key, n) => ({
      busy_on_date: ruOne(n) ? "занят в эту дату" : "заняты в эту дату",
      over_budget: "дороже бюджета",
      wrong_format: ruOne(n) ? "не берёт этот формат" : "не берут этот формат",
      wrong_language: ruOne(n) ? "не работает на этом языке" : "не работают на этом языке",
      too_few_hours: ruOne(n) ? "не может работать столько часов" : "не могут работать столько часов"
    })[key],
    reasonShort: (key, date) => (key === "busy_on_date" ? `занят ${date}` : I18N.ru.excludedLabel(key, 1)),
    countChip: (shown, total) => `${shown} из ${total} ${ruPlural(total, "кандидата", "кандидатов", "кандидатов")}`,
    excludedTotal: (n) => `Отсеяно ${n} ${ruPlural(n, "кандидат", "кандидата", "кандидатов")}: `,
    showDetails: "Показать детали отсева",
    hideDetails: "Скрыть детали",

    fewerTitle: (n) => (n === 1 ? "Подобран только 1 подрядчик" : `Подобрано только ${n} ${ruPlural(n, "подрядчик", "подрядчика", "подрядчиков")}`),
    compareLink: "Сравнить с другой датой →",
    compareBtn: "Сравнить с другой датой",
    compareGo: "Сравнить",
    compareAria: "Дата для сравнения",

    tcTitle: "Прозрачность алгоритма подбора",
    tcTotal: (n) => `Всего проверено: ${n} ${ruPlural(n, "кандидат", "кандидата", "кандидатов")}`,
    tcResult: "Результат фильтрации",
    tcExcluded: (parts) => `Отсеяно: ${parts}`,
    tcOut: "Подрядчики вне выборки",

    nocatLabel: "Нет категории в городе",
    nocatTitle: (city, cat, abroad) => `${abroad ? "В локации" : "В городе"} «${city}» нет подрядчиков категории «${cat}»`,
    nocatWhy: "Почему это произошло?",
    nocatFallback: "В каталоге этого города нет подрядчиков такой категории.",
    nocatActions: "Что можно сделать",
    searchAlmaty: "Искать в Алматы",
    searchAstana: "Искать в Астане",

    nfLabel: "Никто не подошёл",
    nfTitle: "Кандидаты есть, но по вашим критериям никто не подошёл",
    funnelTitle: "Почему отсеялись кандидаты — прозрачность алгоритма",
    funnelSub: (n) => `Разбор ${n} ${ruPlural(n, "кандидата", "кандидатов", "кандидатов")} по причинам отсева`,
    funnelChip: (n) => `Воронка: ${n} → 0`,
    contractors: (n) => `${n} ${ruPlural(n, "подрядчик", "подрядчика", "подрядчиков")}`,
    who: "Кто: ",
    reason: {
      busy_on_date: [(r) => `Заняты на дату ${r.date}`, "У этих подрядчиков в календаре уже стоит бронь на выбранную дату."],
      over_budget: [(r) => `Дороже бюджета ${r.budget}`, "Их минимальная цена («от») выше вашего бюджета."],
      wrong_format: [(r) => `Не берут формат «${r.format}»`, "Этот тип мероприятия не указан в их профиле."],
      wrong_language: [(r) => `Не ведут на языке «${r.language}»`, "Этого языка нет в списке языков их работы."],
      too_few_hours: [(r) => `Не работают ${r.hours} ч`, "Максимум часов на площадке у них меньше запрошенного."]
    },

    qsTitle: "Заданные условия",
    qsZero: "0 найдено",
    qsCity: "Город",
    qsDate: "Дата",
    qsFormat: "Формат",
    qsCategory: "Категория",
    qsBudget: "Бюджет",
    qsHours: "Длительность",
    qsLanguage: "Язык",
    qsNote: (n) => `отсеяно по этому условию: ${n}`,
    qsEdit: "Изменить условия"
  },

  kk: {
    title: "Мердігерлерді іріктеу",
    subtitle: "Қала каталогынан 3 мердігерге дейін және әрқайсысы неге сай келетіні",
    demoMode: "Демо режимі",
    demoHint: "Серверсіз, жергілікті мысалдармен жұмыс істеу",
    uiLang: "Интерфейс тілі",

    formTitle: "Іс-шара параметрлері",
    formSub: "Алгоритм ең сәйкес 3 нұсқаны таңдайды",
    city: "Өтетін қала",
    date: "Іс-шара күні",
    eventType: "Іс-шара түрі",
    category: "Маман санаты",
    budget: "Бюджет шегі",
    budgetPh: "мысалы, 500000",
    upTo: (x) => `${x} ₸ дейін`,
    hours: "Бағдарлама ұзақтығы, сағ",
    hoursPh: "мысалы, 6",
    optional: "міндетті емес",
    language: "Жүргізу тілі",
    anyLang: "кез келген",
    submit: "Іріктеу",
    submitting: "Іріктеп жатырмыз…",

    shortcuts: "Жылдам демо-сұраулар",
    preset1: "1 · Танымал санат, күз",
    preset2: "2 · Сирек санат",
    preset3: "3 · №1 сұрау, бірақ желтоқсанда",
    preset4: "4 · Үміткерлер бар, бірақ сай емес",
    preset5: "5 · Қалада мұндай санат жоқ",
    empty: "Тапсырыс параметрлерін толтырыңыз немесе демо-сұрауды таңдаңыз",
    loading: "Мердігерлерді іріктеп жатырмыз… 10 секундқа дейін созылуы мүмкін",
    mockNote: "Демо режимі: жауап серверден емес, жергілікті mock-деректерден алынды.",

    errTimeout: "Сервер 15 секунд ішінде жауап бермеді. Қайта көріңіз.",
    errNetwork: (api) => `Сервермен байланыс орнамады (${api}). Бэкендті іске қосыңыз немесе жоғарғы оң жақтағы «Демо режимін» қосыңыз.`,
    errStatus: (code) => `Сервер қате қайтарды (код ${code}). Сұрау параметрлерін тексеріңіз.`,
    errFormat: "Сервер күтпеген форматта жауап қайтарды.",
    errSameDate: "Салыстыру үшін басқа күнді таңдаңыз.",
    vRequired: "Бұл өрісті толтырыңыз.",
    vMin: (v) => `Мән кемінде ${v} болуы керек.`,
    vMax: (v) => `Мән ең көбі ${v} болуы керек.`,
    vNumber: "Сан енгізіңіз.",
    vWhole: "Бүтін сан енгізіңіз.",

    synthetic: "синтетикалық профиль",
    price: "Бағасы",
    priceFrom: (x) => `${x} ₸ бастап`,
    whyAria: "Неліктен дәл осы мердігер",
    explNote: "Түсіндірме орыс тілінде",
    hoursShort: (h) => `${h} сағ`,

    excludedLabel: (key) => ({
      busy_on_date: "осы күні бос емес",
      over_budget: "бюджеттен қымбат",
      wrong_format: "бұл түрмен жұмыс істемейді",
      wrong_language: "бұл тілде жұмыс істемейді",
      too_few_hours: "мұнша сағат жұмыс істей алмайды"
    })[key],
    reasonShort: (key, date) => (key === "busy_on_date" ? `${date} бос емес` : I18N.kk.excludedLabel(key)),
    countChip: (shown, total) => `${shown} / ${total} үміткер`,
    excludedTotal: (n) => `Сүзгіден өтпеді — ${n} үміткер: `,
    showDetails: "Толығырақ көрсету",
    hideDetails: "Жасыру",

    fewerTitle: (n) => `Тек ${n} мердігер табылды`,
    compareLink: "Басқа күнмен салыстыру →",
    compareBtn: "Басқа күнмен салыстыру",
    compareGo: "Салыстыру",
    compareAria: "Салыстыру күні",

    tcTitle: "Іріктеу алгоритмінің ашықтығы",
    tcTotal: (n) => `Барлығы тексерілді: ${n} үміткер`,
    tcResult: "Сүзгі нәтижесі",
    tcExcluded: (parts) => `Сүзгіден өтпеді: ${parts}`,
    tcOut: "Іріктеуге кірмегендер",

    nocatLabel: "Қалада санат жоқ",
    nocatTitle: (city, cat, abroad) => `«${city}» ${abroad ? "бағытында" : "қаласында"} «${cat}» санатындағы мердігерлер жоқ`,
    nocatWhy: "Неліктен бұлай болды?",
    nocatFallback: "Бұл қаланың каталогында мұндай санаттағы мердігерлер жоқ.",
    nocatActions: "Не істеуге болады",
    searchAlmaty: "Алматыдан іздеу",
    searchAstana: "Астанадан іздеу",

    nfLabel: "Ешкім сай келмеді",
    nfTitle: "Үміткерлер бар, бірақ сіздің шарттарыңызға ешкім сай келмеді",
    funnelTitle: "Үміткерлер неге өтпеді — алгоритм ашықтығы",
    funnelSub: (n) => `${n} үміткердің сүзгіден өтпеу себептері`,
    funnelChip: (n) => `Сүзгі: ${n} → 0`,
    contractors: (n) => `${n} мердігер`,
    who: "Кімдер: ",
    reason: {
      busy_on_date: [(r) => `${r.date} күні бос емес`, "Бұл мердігерлердің күнтізбесінде таңдалған күнге бронь бар."],
      over_budget: [(r) => `${r.budget} бюджеттен қымбат`, "Олардың ең төмен бағасы («бастап») бюджетіңізден жоғары."],
      wrong_format: [(r) => `«${r.format}» түрімен жұмыс істемейді`, "Бұл іс-шара түрі олардың профилінде көрсетілмеген."],
      wrong_language: [(r) => `«${r.language}» тілінде жүргізбейді`, "Бұл тіл олардың жұмыс тілдерінің тізімінде жоқ."],
      too_few_hours: [(r) => `${r.hours} сағат жұмыс істей алмайды`, "Олардың алаңдағы ең көп уақыты сұралғаннан аз."]
    },

    qsTitle: "Берілген шарттар",
    qsZero: "0 табылды",
    qsCity: "Қала",
    qsDate: "Күні",
    qsFormat: "Түрі",
    qsCategory: "Санат",
    qsBudget: "Бюджет",
    qsHours: "Ұзақтығы",
    qsLanguage: "Тілі",
    qsNote: (n) => `осы шарт бойынша өтпеді: ${n}`,
    qsEdit: "Шарттарды өзгерту"
  },

  en: {
    title: "Contractor matching",
    subtitle: "Up to 3 contractors from the city catalog, with a reason why each one fits",
    demoMode: "Demo mode",
    demoHint: "Work without the backend, using local examples",
    uiLang: "Interface language",

    formTitle: "Event details",
    formSub: "The algorithm picks up to 3 best matches",
    city: "City",
    date: "Event date",
    eventType: "Event type",
    category: "Contractor category",
    budget: "Maximum budget",
    budgetPh: "e.g. 500000",
    upTo: (x) => `up to ${x} ₸`,
    hours: "Duration, hours",
    hoursPh: "e.g. 6",
    optional: "optional",
    language: "Language",
    anyLang: "any",
    submit: "Find contractors",
    submitting: "Searching…",

    shortcuts: "Quick demo queries",
    preset1: "1 · Popular category, autumn",
    preset2: "2 · Rare category",
    preset3: "3 · Same as #1, in December",
    preset4: "4 · Candidates exist, none fit",
    preset5: "5 · Category not in this city",
    empty: "Fill in the event details or pick a demo query",
    loading: "Finding contractors… this may take up to 10 seconds",
    mockNote: "Demo mode: response from local mock data, not from the server.",

    errTimeout: "The server did not respond within 15 seconds. Please try again.",
    errNetwork: (api) => `Could not reach the server (${api}). Start the backend or turn on “Demo mode” at the top right.`,
    errStatus: (code) => `The server returned an error (code ${code}). Check the query parameters.`,
    errFormat: "The server returned an unexpected response.",
    errSameDate: "Pick a different date to compare.",
    vRequired: "Please fill in this field.",
    vMin: (v) => `Value must be at least ${v}.`,
    vMax: (v) => `Value must be at most ${v}.`,
    vNumber: "Please enter a number.",
    vWhole: "Please enter a whole number.",

    synthetic: "synthetic profile",
    price: "Price",
    priceFrom: (x) => `from ${x} ₸`,
    whyAria: "Why this contractor",
    explNote: "Explanation in Russian",
    hoursShort: (h) => `${h} h`,

    excludedLabel: (key, n) => ({
      busy_on_date: "busy on this date",
      over_budget: "over budget",
      wrong_format: enPl(n, "doesn't take this event type", "don't take this event type"),
      wrong_language: enPl(n, "doesn't work in this language", "don't work in this language"),
      too_few_hours: "can't work that many hours"
    })[key],
    reasonShort: (key, date) => (key === "busy_on_date" ? `busy on ${date}` : I18N.en.excludedLabel(key, 1)),
    countChip: (shown, total) => `${shown} of ${total} ${enPl(total, "candidate", "candidates")}`,
    excludedTotal: (n) => `${n} ${enPl(n, "candidate", "candidates")} filtered out: `,
    showDetails: "Show details",
    hideDetails: "Hide details",

    fewerTitle: (n) => `Only ${n} ${enPl(n, "contractor", "contractors")} found`,
    compareLink: "Compare with another date →",
    compareBtn: "Compare with another date",
    compareGo: "Compare",
    compareAria: "Date to compare",

    tcTitle: "How the selection worked",
    tcTotal: (n) => `Checked: ${n} ${enPl(n, "candidate", "candidates")}`,
    tcResult: "Filtering result",
    tcExcluded: (parts) => `Filtered out: ${parts}`,
    tcOut: "Not selected",

    nocatLabel: "Category not in city",
    nocatTitle: (city, cat, abroad) => `There are no “${cat}” contractors ${abroad ? "for" : "in"} ${city}`,
    nocatWhy: "Why did this happen?",
    nocatFallback: "This city's catalog has no contractors in this category.",
    nocatActions: "What you can do",
    searchAlmaty: "Search in Almaty",
    searchAstana: "Search in Astana",

    nfLabel: "No match",
    nfTitle: "There are candidates, but none meet your criteria",
    funnelTitle: "Why candidates were filtered out",
    funnelSub: (n) => `${n} ${enPl(n, "candidate", "candidates")}, broken down by reason`,
    funnelChip: (n) => `Funnel: ${n} → 0`,
    contractors: (n) => `${n} ${enPl(n, "contractor", "contractors")}`,
    who: "Who: ",
    reason: {
      busy_on_date: [(r) => `Busy on ${r.date}`, "These contractors already have a booking on the chosen date."],
      over_budget: [(r) => `Over the ${r.budget} budget`, "Their starting price is above your budget."],
      wrong_format: [(r) => `Don't take “${r.format}”`, "This event type is not listed in their profile."],
      wrong_language: [(r) => `Don't work in ${r.language}`, "This language is not among their working languages."],
      too_few_hours: [(r) => `Can't work ${r.hours} h`, "Their maximum hours on site are fewer than requested."]
    },

    qsTitle: "Your criteria",
    qsZero: "0 found",
    qsCity: "City",
    qsDate: "Date",
    qsFormat: "Event type",
    qsCategory: "Category",
    qsBudget: "Budget",
    qsHours: "Duration",
    qsLanguage: "Language",
    qsNote: (n) => `filtered out by this: ${n}`,
    qsEdit: "Edit criteria"
  }
};

// Подписи для значений из API. Ключ — русское значение, которое уходит в запрос.
const VALUE_LABELS = {
  kk: {
    "Алматы": "Алматы", "Астана": "Астана", "Зарубежье": "Шетел",
    "свадьба": "үйлену тойы", "той": "той", "корпоратив": "корпоратив", "конференция": "конференция",
    "юбилей": "мерейтой", "день рождения": "туған күн",
    "Ведущий": "Жүргізуші", "Фотограф": "Фотограф", "Банкетный зал": "Банкет залы", "Видеограф": "Видеограф",
    "Лайв-бэнд": "Лайв-бэнд", "Флорист": "Флорист", "Декоратор": "Декоратор",
    "Подарки и сувениры": "Сыйлықтар мен кәдесыйлар", "Ведущий церемонии": "Рәсім жүргізушісі",
    "Фото и видеобудки": "Фото және видео будкалар", "Отель": "Қонақүй", "Инструменталист": "Аспапшы",
    "Ресторан": "Мейрамхана", "Загородная площадка": "Қала сыртындағы алаң",
    "Национальный ансамбль": "Ұлттық ансамбль", "Танцевальный коллектив": "Би ұжымы", "Шоу-программа": "Шоу-бағдарлама",
    "русский": "орыс", "казахский": "қазақ", "английский": "ағылшын"
  },
  en: {
    "Алматы": "Almaty", "Астана": "Astana", "Зарубежье": "Abroad",
    "свадьба": "wedding", "той": "toi", "корпоратив": "corporate event", "конференция": "conference",
    "юбилей": "anniversary", "день рождения": "birthday",
    "Ведущий": "Host", "Фотограф": "Photographer", "Банкетный зал": "Banquet hall", "Видеограф": "Videographer",
    "Лайв-бэнд": "Live band", "Флорист": "Florist", "Декоратор": "Decorator",
    "Подарки и сувениры": "Gifts & souvenirs", "Ведущий церемонии": "Ceremony host",
    "Фото и видеобудки": "Photo & video booths", "Отель": "Hotel", "Инструменталист": "Instrumentalist",
    "Ресторан": "Restaurant", "Загородная площадка": "Country venue",
    "Национальный ансамбль": "National ensemble", "Танцевальный коллектив": "Dance group", "Шоу-программа": "Show program",
    "русский": "Russian", "казахский": "Kazakh", "английский": "English"
  }
};

const UI_LANGS = ["ru", "kk", "en"];
let UI_LANG = "ru";

// Текущая строка; ключа нет в переводе — берём русский вариант
function t(key, ...args) {
  const dict = I18N[UI_LANG];
  const v = key in dict ? dict[key] : I18N.ru[key];
  return typeof v === "function" ? v(...args) : v;
}

// Подпись для значения из API (неизвестное значение показываем как есть)
function vl(value) {
  if (UI_LANG === "ru" || value == null) return value;
  const map = VALUE_LABELS[UI_LANG] || {};
  return map[value] || value;
}

function loadUiLang() {
  try {
    const saved = localStorage.getItem("uiLang");
    if (UI_LANGS.includes(saved)) UI_LANG = saved;
  } catch (e) { /* localStorage недоступен — остаёмся на RU */ }
}
function saveUiLang() {
  try { localStorage.setItem("uiLang", UI_LANG); } catch (e) { /* ignore */ }
}
