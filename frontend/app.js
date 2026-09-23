// Фронтенд подбора подрядчиков. Без сборки и без библиотек.
// Поток: форма → POST /api/match (или mockMatch в демо-режиме) → renderPanel().

// Адрес бэкенда. Можно переопределить так: index.html?api=http://192.168.1.10:8000
const API_BASE = new URLSearchParams(location.search).get("api") || "http://localhost:8000";
const MATCH_TIMEOUT_MS = 15000;

// Запасные списки, если GET /api/options недоступен
const FALLBACK_OPTIONS = {
  cities: ["Алматы", "Астана", "Зарубежье"],
  event_formats: ["свадьба", "той", "корпоратив", "конференция", "юбилей", "день рождения"],
  categories: [
    "Ведущий", "Фотограф", "Банкетный зал", "Видеограф", "Лайв-бэнд", "Флорист", "Декоратор",
    "Подарки и сувениры", "Ведущий церемонии", "Фото и видеобудки", "Отель", "Инструменталист",
    "Ресторан", "Загородная площадка", "Национальный ансамбль", "Танцевальный коллектив", "Шоу-программа"
  ],
  languages: ["русский", "казахский", "английский"]
};

// Демо-запросы для жюри (см. docs/task.md, раздел Definition of Done)
const PRESETS = {
  dense:    { city: "Алматы",    date: "2026-10-17", event_type: "свадьба",    category: "Ведущий",       budget_kzt: 1000000 },
  rare:     { city: "Алматы",    date: "2026-10-17", event_type: "свадьба",    category: "Флорист",       budget_kzt: 300000 },
  december: { city: "Алматы",    date: "2026-12-26", event_type: "свадьба",    category: "Ведущий",       budget_kzt: 1000000 },
  nofit:    { city: "Алматы",    date: "2026-10-17", event_type: "свадьба",    category: "Флорист",       budget_kzt: 200000 },
  empty:    { city: "Зарубежье", date: "2026-11-14", event_type: "корпоратив", category: "Банкетный зал", budget_kzt: 100000 }
};

// Подписи для причин исключения (поле excluded в ответе)
// [форма для 1/21/31…, форма для остальных чисел] — глагол согласуется с числом
const EXCLUDED_LABELS = {
  busy_on_date: ["занят в эту дату", "заняты в эту дату"],
  over_budget: ["дороже бюджета", "дороже бюджета"],
  wrong_format: ["не берёт этот формат", "не берут этот формат"],
  wrong_language: ["не работает на этом языке", "не работают на этом языке"],
  too_few_hours: ["не может работать столько часов", "не могут работать столько часов"]
};

// Русское множественное число: plural(5, "подрядчик", "подрядчика", "подрядчиков") → "подрядчиков"
function plural(n, one, few, many) {
  const d = n % 10, dd = n % 100;
  if (d === 1 && dd !== 11) return one;
  if (d >= 2 && d <= 4 && (dd < 12 || dd > 14)) return few;
  return many;
}
function excludedLabel(key, n) {
  const [one, many] = EXCLUDED_LABELS[key];
  return n % 10 === 1 && n % 100 !== 11 ? one : many;
}

const STATUS_TITLES = {
  found: "Подобрали",
  no_category: "Такой категории в этом городе нет",
  none_fit: "Кандидаты есть, но ни один не подходит"
};

const $ = (id) => document.getElementById(id);
const form = $("form");
const submitBtn = $("submitBtn");
const resultsEl = $("results");
const errorEl = $("error");
const demoCheckbox = $("demoMode");

// ---------- Утилиты ----------

// Создать элемент. Текст ставим через textContent, чтобы не вставлять чужой HTML.
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// 250000 → "250 000"
function formatPrice(n) {
  return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

// "2026-10-17" → "17.10.2026"
function formatDate(iso) {
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

// ["Алматы", "17.10.2026", "свадьба", "Ведущий", "до 1 000 000 ₸", "5 ч", "казахский"]
function requestParts(req) {
  const parts = [req.city, formatDate(req.date), req.event_type, req.category, `до ${formatPrice(req.budget_kzt)} ₸`];
  if (req.hours) parts.push(`${req.hours} ч`);
  if (req.language) parts.push(req.language);
  return parts;
}

// Простые SVG-иконки (свои строки-константы, без внешних библиотек)
const ICONS = {
  check: '<path d="M20 6 9 17l-5-5"/>',
  alert: '<path d="M12 3 2 20h20L12 3z"/><path d="M12 10v4M12 17v.5"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.5v.5"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
  funnel: '<path d="M3 5h18l-7 8v6l-4 2v-8L3 5z"/>',
  spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
  trend: '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
  pin: '<path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
  chevron: '<path d="m6 9 6 6 6-6"/>',
  bulb: '<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z"/>',
  searchZoom: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5M8.5 11h5"/>',
  lock: '<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M3 9h18M8 2v4M16 2v4M9.5 13.5l5 5M14.5 13.5l-5 5"/>',
  wallet: '<rect x="2" y="6" width="20" height="13" rx="2"/><path d="M16 12.5h2M2 10h20"/>',
  tags: '<path d="M3 12V4h8l10 10-8 8L3 12z"/><circle cx="7.5" cy="8.5" r="1.5"/>',
  lang: '<path d="M4 5h9M8.5 3v2M6 5c0 4 3 7 6 8M11 5c0 4-3 7-7 8M13 21l4-9 4 9M14.5 18h5"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  sliders: '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
  building: '<path d="M4 21V5a1 1 0 0 1 1-1h9a1 1 0 0 1 1 1v16M15 9h4a1 1 0 0 1 1 1v11M3 21h18M8 8h3M8 12h3M8 16h3"/>'
};
function icon(name, size) {
  const s = size || 20;
  const span = el("span", "icon");
  span.innerHTML = `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name]}</svg>`;
  return span;
}

function fillSelect(select, values, emptyLabel) {
  select.innerHTML = "";
  if (emptyLabel) select.appendChild(new Option(emptyLabel, ""));
  values.forEach((v) => select.appendChild(new Option(v, v)));
}

// localStorage может быть недоступен (приватный режим, file://) — не падаем
function saveDemoFlag(on) {
  try { localStorage.setItem("demoMode", on ? "1" : "0"); } catch (e) { /* ignore */ }
}
function loadDemoFlag() {
  try { return localStorage.getItem("demoMode") === "1"; } catch (e) { return false; }
}

// ---------- Работа с API ----------

// Собрать запрос из формы. hours и language отправляем только если заполнены.
function readForm() {
  const req = {
    city: $("city").value,
    date: $("date").value,
    event_type: $("event_type").value,
    category: $("category").value,
    budget_kzt: Number($("budget_kzt").value)
  };
  const hours = Number($("hours").value);
  if (hours > 0) req.hours = hours;
  if ($("language").value) req.language = $("language").value;
  return req;
}

// Вызов бэкенда или mock. Бросает Error с понятным русским текстом.
async function match(req) {
  if (demoCheckbox.checked) {
    await new Promise((r) => setTimeout(r, 400)); // имитируем задержку сети
    return mockMatch(req);
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), MATCH_TIMEOUT_MS);
  let res;
  try {
    res = await fetch(`${API_BASE}/api/match`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
      signal: controller.signal
    });
  } catch (e) {
    if (e.name === "AbortError") throw new Error("Сервер не ответил за 15 секунд. Попробуйте ещё раз.");
    throw new Error(`Не удалось связаться с сервером (${API_BASE}). Запустите бэкенд или включите «Демо-режим» вверху справа.`);
  } finally {
    clearTimeout(timer);
  }

  if (!res.ok) throw new Error(`Сервер вернул ошибку (код ${res.status}). Проверьте параметры запроса.`);
  const data = await res.json().catch(() => null);
  if (!data || !data.status) throw new Error("Сервер вернул ответ в неожиданном формате.");
  return data;
}

// Списки для выпадающих полей: берём с бэкенда, если он есть, иначе запасные
async function loadOptions() {
  let opts = FALLBACK_OPTIONS;
  if (!demoCheckbox.checked) {
    try {
      const controller = new AbortController();
      setTimeout(() => controller.abort(), 3000);
      const res = await fetch(`${API_BASE}/api/options`, { signal: controller.signal });
      if (res.ok) opts = { ...FALLBACK_OPTIONS, ...(await res.json()) };
    } catch (e) { /* бэкенда нет — используем запасные списки */ }
  }
  fillSelect($("city"), opts.cities);
  fillSelect($("event_type"), opts.event_formats);
  fillSelect($("category"), opts.categories);
  fillSelect($("language"), opts.languages, "любой");
  renderLangChips(opts.languages);
}

// Чипы языка: одиночный выбор, значение пишем в скрытый select#language (его читает readForm)
function renderLangChips(languages) {
  const box = $("langChips");
  box.innerHTML = "";
  [""].concat(languages).forEach((lang) => {
    const b = el("button", "lang-chip", lang || "любой");
    b.type = "button";
    b.setAttribute("role", "radio");
    b.dataset.lang = lang;
    b.addEventListener("click", () => { $("language").value = lang; syncLangChips(); });
    box.appendChild(b);
  });
  syncLangChips();
}
function syncLangChips() {
  document.querySelectorAll(".lang-chip").forEach((b) => {
    const on = b.dataset.lang === $("language").value;
    b.classList.toggle("on", on);
    b.setAttribute("aria-checked", on ? "true" : "false");
  });
}

// Подсказка над полем бюджета: «до 400 000 ₸»
function syncBudgetHint() {
  const v = Number($("budget_kzt").value);
  $("budgetHint").textContent = v > 0 ? `до ${formatPrice(v)} ₸` : "";
}

// ---------- Отрисовка ----------

// Причины отсева с ненулевым количеством: [{key, count, label}]
function excludedItems(excluded) {
  return Object.keys(EXCLUDED_LABELS)
    .filter((k) => excluded && excluded[k] > 0)
    .map((k) => ({ key: k, count: excluded[k], label: excludedLabel(k, excluded[k]) }));
}

// "1 кандидат" / "2 кандидата" / "5 кандидатов"
function candidatesWord(n) {
  return plural(n, "кандидат", "кандидата", "кандидатов");
}

function renderCard(card, rank) {
  const node = el("article", "card");

  // Шапка: ранг · имя + категория/город · цена (на телефоне цена уходит под имя)
  const head = el("div", "card-head");
  head.appendChild(el("div", `rank rank-${rank}`, String(rank)));
  const who = el("div", "who");
  const nameLine = el("div", "name-line");
  nameLine.appendChild(el("h3", "name", card.name));
  if (card.synthetic) nameLine.appendChild(el("span", "badge", "синтетический профиль"));
  who.appendChild(nameLine);
  const where = el("div", "where");
  where.appendChild(document.createTextNode(`${card.category} · `));
  where.appendChild(icon("pin", 14));
  where.appendChild(document.createTextNode(card.city));
  who.appendChild(where);
  head.appendChild(who);
  const priceBox = el("div", "price-box");
  priceBox.appendChild(el("span", "price-label", "Стоимость"));
  priceBox.appendChild(el("span", "price", `от ${formatPrice(card.price_from_kzt)} ₸`));
  head.appendChild(priceBox);
  node.appendChild(head);

  // Главное на карточке — объяснение, крупно и в кавычках
  const why = el("blockquote", "why");
  why.setAttribute("aria-label", "Почему именно этот подрядчик");
  why.appendChild(icon("trend", 22));
  why.appendChild(el("p", "explanation", `«${card.explanation}»`));
  node.appendChild(why);
  return node;
}

// Баннер статуса: иконка + заголовок + сообщение (+ подсказка)
function banner(kind, iconName, title, message, hint) {
  const box = el("div", `banner ${kind}`);
  box.appendChild(icon(iconName, 22));
  const body = el("div", "banner-body");
  body.appendChild(el("span", "title", title));
  if (message) body.appendChild(el("p", "message", message));
  if (hint) body.appendChild(el("p", "hint", hint));
  box.appendChild(body);
  return box;
}

// Полоса «Отсеяно N кандидатов: …» под карточками.
// Если бэкенд вернул excluded_list [{name, reason}], по кнопке раскрываются имена по причинам.
function renderExcludedBar(data, openByDefault) {
  const items = excludedItems(data.excluded);
  if (!items.length) return null;
  const total = items.reduce((s, i) => s + i.count, 0);
  const names = {};
  (data.excluded_list || []).forEach((x) => {
    if (x && x.name && x.reason) (names[x.reason] = names[x.reason] || []).push(x.name);
  });
  const hasNames = Object.keys(names).length > 0;

  const line = el("div", "excluded-line");
  line.appendChild(icon("info", 18));
  const text = el("span", "excluded-text");
  text.appendChild(el("strong", "", `Отсеяно ${total} ${candidatesWord(total)}: `));
  text.appendChild(document.createTextNode(items.map((i) => `${i.count} ${i.label}`).join(" · ")));
  line.appendChild(text);

  if (!hasNames) {
    const box = el("section", "excluded-bar");
    box.appendChild(line);
    return box;
  }

  // <details> раскрывается без JS и доступен с клавиатуры
  const box = el("details", "excluded-bar");
  if (openByDefault) box.open = true;
  const summary = el("summary");
  summary.appendChild(line);
  const toggle = el("span", "excluded-toggle");
  toggle.appendChild(el("span", "t-show", "Показать детали отсева"));
  toggle.appendChild(el("span", "t-hide", "Скрыть детали"));
  toggle.appendChild(icon("chevron", 16));
  summary.appendChild(toggle);
  box.appendChild(summary);

  const grid = el("div", "reasons");
  items.forEach((i) => {
    const r = el("div", `reason ${i.key}`);
    const top = el("div", "reason-top");
    top.appendChild(el("span", "", i.label));
    top.appendChild(el("span", "count", String(i.count)));
    r.appendChild(top);
    if (names[i.key]) r.appendChild(el("div", "reason-names", names[i.key].join(", ")));
    grid.appendChild(r);
  });
  box.appendChild(grid);
  return box;
}

// Что писать под зачёркнутым именем: причина отсева своими словами
const REASON_SHORT = {
  busy_on_date: (req) => `занят ${formatDate(req.date)}`,
  over_budget: () => "дороже бюджета",
  wrong_format: () => "не берёт этот формат",
  wrong_language: () => "не работает на этом языке",
  too_few_hours: () => "не может работать столько часов"
};

// Карточка «Прозрачность алгоритма подбора»: итог фильтрации цифрами и тегами,
// а если бэкенд прислал excluded_list — зачёркнутые имена с причиной.
function renderTransparencyCard(req, data) {
  const ex = data.excluded || {};
  const shown = (data.cards || []).length;
  const excludedTotal = excludedItems(ex).reduce((s, i) => s + i.count, 0);
  const total = shown + excludedTotal;
  if (!total) return null;

  const box = el("section", "transparency-card");
  const head = el("div", "tc-head");
  const h = el("h3", "tc-title");
  h.appendChild(icon("funnel", 18));
  h.appendChild(document.createTextNode("Прозрачность алгоритма подбора"));
  head.appendChild(h);
  head.appendChild(el("span", "tc-total", `Всего проверено: ${total} ${candidatesWord(total)}`));
  box.appendChild(head);

  // Итог фильтрации: основные причины показываем и с нулём, язык/часы — если были в запросе
  const keys = ["busy_on_date", "over_budget", "wrong_format"];
  if (req.language || ex.wrong_language) keys.push("wrong_language");
  if (req.hours || ex.too_few_hours) keys.push("too_few_hours");
  const parts = keys.map((k) => {
    const txt = `${ex[k] || 0} ${excludedLabel(k, ex[k] || 0)}`;
    return k === "busy_on_date" ? `${txt} (${formatDate(req.date)})` : txt;
  });

  const result = el("div", "tc-result");
  const txt = el("div", "tc-result-text");
  txt.appendChild(el("div", "tc-label", "Результат фильтрации"));
  txt.appendChild(el("div", "", `Отсеяно: ${parts.join(" · ")}`));
  result.appendChild(txt);
  const tags = el("div", "tc-tags");
  excludedItems(ex).forEach((i) => tags.appendChild(el("span", `tag ${i.key}`, `${i.count} ${i.label}`)));
  result.appendChild(tags);
  box.appendChild(result);

  // Зачёркнутые имена — только если они реально пришли в ответе
  const list = (data.excluded_list || []).filter((x) => x && x.name && x.reason);
  if (list.length) {
    box.appendChild(el("div", "tc-label", "Подрядчики вне выборки"));
    const grid = el("div", "out-list");
    list.forEach((x) => {
      const item = el("div", `out ${x.reason}`);
      const main = el("div", "out-main");
      main.appendChild(el("s", "out-name", x.name));
      const why = REASON_SHORT[x.reason];
      main.appendChild(el("span", "out-reason", why ? why(req) : x.reason));
      item.appendChild(main);
      if (x.price_from_kzt) item.appendChild(el("span", "out-price", `${formatPrice(x.price_from_kzt)} ₸`));
      grid.appendChild(item);
    });
    box.appendChild(grid);
  }
  return box;
}

// Исход «категории нет в городе»: большая карточка с заголовком из запроса,
// причиной от API и кнопками «Искать в Алматы/Астане» (меняют город в форме и повторяют поиск).
function renderNoCategory(req, data, withActions) {
  const box = el("section", "nocat");
  const head = el("div", "nocat-head");
  const ic = icon("searchZoom", 28);
  ic.classList.add("nocat-icon");
  head.appendChild(ic);
  const titles = el("div");
  titles.appendChild(el("span", "nocat-label", "Нет категории в городе"));
  const where = req.city === "Зарубежье" ? "В локации" : "В городе";
  titles.appendChild(el("h2", "nocat-title", `${where} «${req.city}» нет подрядчиков категории «${req.category}»`));
  head.appendChild(titles);
  box.appendChild(head);

  const why = el("div", "nocat-why");
  const wh = el("div", "nocat-why-title");
  wh.appendChild(icon("bulb", 20));
  wh.appendChild(document.createTextNode("Почему это произошло?"));
  why.appendChild(wh);
  why.appendChild(el("p", "", data.message || "В каталоге этого города нет подрядчиков такой категории."));
  box.appendChild(why);

  // Только города, которые есть в форме и отличаются от текущего
  const cityOptions = Array.from($("city").options).map((o) => o.value);
  const targets = [["Алматы", "Искать в Алматы"], ["Астана", "Искать в Астане"]]
    .filter(([c]) => c !== req.city && cityOptions.includes(c));
  if (withActions && targets.length) {
    box.appendChild(el("div", "nocat-actions-label", "Что можно сделать"));
    const actions = el("div", "nocat-actions");
    targets.forEach(([c, label]) => {
      const b = el("button", "secondary");
      b.type = "button";
      b.appendChild(icon("building", 18));
      b.appendChild(document.createTextNode(label));
      b.addEventListener("click", () => {
        $("city").value = c;
        presetButtons.forEach((x) => x.classList.remove("active"));
        runSearch();
      });
      actions.appendChild(b);
    });
    box.appendChild(actions);
  }
  return box;
}

// ---------- Исход «кандидаты есть, но никто не подошёл» ----------

function renderNoneFitHero(data) {
  const box = el("section", "nf-hero");
  const ic = icon("alert", 26);
  ic.classList.add("nf-hero-icon");
  box.appendChild(ic);
  const body = el("div", "nf-body");
  body.appendChild(el("span", "nf-label", "Никто не подошёл"));
  body.appendChild(el("h2", "nf-title", "Кандидаты есть, но по вашим критериям никто не подошёл"));
  if (data.message) body.appendChild(el("p", "nf-message", data.message));
  box.appendChild(body);
  return box;
}

// Для каждой причины: иконка, заголовок и короткий факт — всё из запроса и excluded
const FUNNEL_REASONS = {
  busy_on_date: { icon: "lock", title: (r) => `Заняты на дату ${formatDate(r.date)}`, text: () => "У этих подрядчиков в календаре уже стоит бронь на выбранную дату." },
  over_budget: { icon: "wallet", title: (r) => `Дороже бюджета ${formatPrice(r.budget_kzt).replace(/ /g, "\u00a0")}\u00a0₸`, text: () => "Их минимальная цена («от») выше вашего бюджета." }, // сумма не рвётся переносом
  wrong_format: { icon: "tags", title: (r) => `Не берут формат «${r.event_type}»`, text: () => "Этот тип мероприятия не указан в их профиле." },
  wrong_language: { icon: "lang", title: (r) => `Не ведут на языке «${r.language}»`, text: () => "Этого языка нет в списке языков их работы." },
  too_few_hours: { icon: "clock", title: (r) => `Не работают ${r.hours} ч`, text: () => "Максимум часов на площадке у них меньше запрошенного." }
};

function countWord(n) {
  return plural(n, "подрядчик", "подрядчика", "подрядчиков");
}

// Воронка: полоса из реальных счётчиков excluded (ширина сегмента ∝ числу), легенда и строки причин
function renderFunnel(req, data) {
  const items = excludedItems(data.excluded);
  if (!items.length) return null;
  const total = items.reduce((s, i) => s + i.count, 0);
  const names = {};
  (data.excluded_list || []).forEach((x) => {
    if (x && x.name && x.reason) (names[x.reason] = names[x.reason] || []).push(x.name);
  });

  const box = el("section", "funnel");
  const head = el("div", "funnel-head");
  const ht = el("div");
  const h = el("h3", "funnel-title");
  h.appendChild(icon("funnel", 20));
  h.appendChild(document.createTextNode("Почему отсеялись кандидаты — прозрачность алгоритма"));
  ht.appendChild(h);
  ht.appendChild(el("p", "funnel-sub", `Разбор ${total} ${candidatesWord(total)} по причинам отсева`));
  head.appendChild(ht);
  head.appendChild(el("span", "funnel-chip", `Воронка: ${total} → 0`));
  box.appendChild(head);

  const barBox = el("div", "funnel-bar-box");
  const bar = el("div", "funnel-bar");
  bar.setAttribute("role", "img");
  bar.setAttribute("aria-label", items.map((i) => `${i.count} ${i.label}`).join(", "));
  items.forEach((i) => {
    const seg = el("span", `seg ${i.key}`);
    seg.style.flexGrow = String(i.count);
    bar.appendChild(seg);
  });
  barBox.appendChild(bar);
  const legend = el("div", "funnel-legend");
  items.forEach((i) => {
    const li = el("span", `lg ${i.key}`);
    li.appendChild(el("span", "dot"));
    li.appendChild(document.createTextNode(`${i.count} ${i.label} (${Math.round((i.count / total) * 100)}%)`));
    legend.appendChild(li);
  });
  barBox.appendChild(legend);
  box.appendChild(barBox);

  const rows = el("div", "funnel-rows");
  items.forEach((i) => {
    const cfg = FUNNEL_REASONS[i.key];
    const row = el("div", `frow ${i.key}`);
    const ic = icon(cfg ? cfg.icon : "info", 20);
    ic.classList.add("frow-icon");
    row.appendChild(ic);
    const body = el("div", "frow-body");
    const t = el("div", "frow-title");
    t.appendChild(el("span", "", cfg ? cfg.title(req) : i.label));
    t.appendChild(el("span", "frow-badge", `${i.count} ${countWord(i.count)}`));
    body.appendChild(t);
    body.appendChild(el("p", "frow-text", cfg ? cfg.text(req) : ""));
    if (names[i.key]) body.appendChild(el("p", "frow-names", `Кто: ${names[i.key].join(", ")}`));
    row.appendChild(body);
    rows.appendChild(row);
  });
  box.appendChild(rows);
  return box;
}

// Левая колонка при none_fit: форма сворачивается в сводку условий.
// Подсвечиваем только условия, по которым реально кто-то отсеялся.
function showQuerySummary(req, data) {
  const ex = data.excluded || {};
  const box = $("querySummary");
  box.innerHTML = "";
  const head = el("div", "qs-head");
  const h = el("h2", "qs-title");
  h.appendChild(icon("sliders", 18));
  h.appendChild(document.createTextNode("Заданные условия"));
  head.appendChild(h);
  head.appendChild(el("span", "qs-zero", "0 найдено"));
  box.appendChild(head);

  const rows = [
    ["Город", req.city, null],
    ["Дата", formatDate(req.date), "busy_on_date"],
    ["Формат", req.event_type, "wrong_format"],
    ["Категория", req.category, null],
    ["Бюджет", `до ${formatPrice(req.budget_kzt)} ₸`, "over_budget"]
  ];
  if (req.hours) rows.push(["Длительность", `${req.hours} ч`, "too_few_hours"]);
  rows.push(["Язык", req.language || "любой", "wrong_language"]);

  rows.forEach(([label, value, key]) => {
    const hit = key && ex[key] > 0;
    const r = el("div", hit ? "qs-row hit" : "qs-row");
    const top = el("div", "qs-row-top");
    top.appendChild(el("span", "qs-label", label));
    top.appendChild(el("span", "qs-value", value));
    r.appendChild(top);
    if (hit) r.appendChild(el("div", "qs-note", `отсеяно по этому условию: ${ex[key]}`));
    box.appendChild(r);
  });

  const btn = el("button", "primary");
  btn.type = "button";
  btn.appendChild(icon("sliders", 18));
  btn.appendChild(document.createTextNode("Изменить условия"));
  btn.addEventListener("click", () => { showForm(); $("budget_kzt").focus(); });
  box.appendChild(btn);

  form.hidden = true;
  box.hidden = false;
}

function showForm() {
  $("querySummary").hidden = true;
  form.hidden = false;
}

// Одна панель результата: баннер статуса, карточки, полоса отсева
function renderPanel(req, data, dateLabel) {
  const panel = el("section", "panel");
  if (dateLabel) panel.appendChild(el("div", "panel-date", formatDate(req.date)));

  const cards = data.cards || [];
  const title = STATUS_TITLES[data.status] || data.status;

  if (data.status === "found") {
    // 3 из 3 — без баннера (итог в сводке), сообщение бэкенда — тихой строкой.
    // Меньше 3 — янтарный баннер с объяснением «почему меньше».
    if (cards.length >= 3) {
      if (data.message) panel.appendChild(el("p", "found-note", data.message));
    } else {
      const n = cards.length;
      const b = banner("warning fewer", "alert",
        n === 1 ? "Подобран только 1 подрядчик" : `Подобрано только ${n} ${countWord(n)}`, data.message);
      panel.appendChild(b);
      if (!dateLabel) addCompareReveal(req, b.querySelector(".banner-body"), panel); // в режиме сравнения не нужно
    }
  } else if (data.status === "no_category") {
    panel.appendChild(renderNoCategory(req, data, !dateLabel));
  } else {
    const hero = renderNoneFitHero(data);
    panel.appendChild(hero);
    if (!dateLabel) addCompareReveal(req, hero.querySelector(".nf-body"), panel);
  }

  if (cards.length) {
    const list = el("div", "cards");
    cards.forEach((c, i) => list.appendChild(renderCard(c, i + 1)));
    panel.appendChild(list);
  }

  // Меньше 3 — развёрнутая карточка «Прозрачность алгоритма подбора», иначе компактная полоса
  const fewer = data.status === "found" && cards.length < 3;
  let bar = null;
  if (fewer) bar = renderTransparencyCard(req, data);
  else if (data.status === "none_fit") bar = renderFunnel(req, data);
  else bar = renderExcludedBar(data, false);
  if (bar) panel.appendChild(bar);

  if (demoCheckbox.checked) panel.appendChild(el("p", "mock-note", "Демо-режим: ответ из локальных mock-данных, не с сервера."));
  return panel;
}

// Загрузка: 3 карточки-скелетона с переливом
function showLoading() {
  resultsEl.innerHTML = "";
  resultsEl.appendChild(el("p", "loading-text", "Подбираем подрядчиков… это может занять до 10 секунд"));
  const list = el("div", "cards");
  for (let i = 0; i < 3; i++) list.appendChild(el("div", "skeleton"));
  resultsEl.appendChild(list);
}

function showError(message) {
  errorEl.textContent = message;
  errorEl.hidden = false;
}

// Сводка запроса + «Сравнить с другой датой» (тот же запрос, другая дата, результаты рядом)
function renderSummary(req, comparing, data) {
  const bar = el("div", "summary");

  const left = el("div", "summary-left");
  const parts = el("div", "summary-parts");
  const list = requestParts(req);
  if (comparing) list.splice(1, 1); // в режиме сравнения даты показаны над каждой колонкой
  list.forEach((p, i) => {
    if (i) parts.appendChild(el("span", "dot", "·"));
    parts.appendChild(el("span", p.startsWith("до ") ? "budget" : "", p));
  });
  left.appendChild(parts);
  // «3 из 10 кандидатов»: всего = карточки + все отсеянные (только если категория в городе есть)
  if (data && data.status !== "no_category") {
    const shown = (data.cards || []).length;
    const total = shown + excludedItems(data.excluded).reduce((s, i) => s + i.count, 0);
    if (total > 0) left.appendChild(el("span", "count-chip", `${shown} из ${total} ${plural(total, "кандидата", "кандидатов", "кандидатов")}`));
  }
  bar.appendChild(left);

  // Когда найдено меньше 3, кнопка сравнения стоит в янтарном баннере — здесь не дублируем
  const fewer = data && data.status === "found" && (data.cards || []).length < 3;
  const noCategory = data && data.status === "no_category"; // категории нет ни на какую дату
  const noneFit = data && data.status === "none_fit"; // кнопка сравнения — внизу панели
  if (!fewer && !noCategory && !noneFit) bar.appendChild(compareControls(req, "secondary"));
  return bar;
}

// Ссылка «Сравнить с другой датой →» внутри баннера; по клику под баннером
// раскрывается компактная строка: поле даты + кнопка «Сравнить».
function addCompareReveal(req, linkParent, panel) {
  const link = el("button", "link-btn", "Сравнить с другой датой →");
  link.type = "button";
  const row = el("div", "compare-inline");
  row.hidden = true;
  const input = el("input");
  input.type = "date";
  input.min = "2026-09-23";
  input.max = "2026-12-31";
  input.value = req.date < "2026-12-01" ? "2026-12-26" : "2026-10-17";
  input.setAttribute("aria-label", "Дата для сравнения");
  const go = el("button", "outline-sm", "Сравнить");
  go.type = "button";
  go.addEventListener("click", () => runCompare(req, input.value));
  row.appendChild(input);
  row.appendChild(go);
  link.setAttribute("aria-expanded", "false");
  link.addEventListener("click", () => {
    row.hidden = !row.hidden;
    link.setAttribute("aria-expanded", String(!row.hidden));
    if (!row.hidden) input.focus();
  });
  linkParent.appendChild(link);
  panel.appendChild(row);
}

// Поле даты + «Сравнить с другой датой»: тот же запрос на другую дату, результаты рядом
function compareControls(req, btnClass) {
  const compare = el("div", "compare");
  const input = el("input");
  input.type = "date";
  input.min = "2026-09-23";
  input.max = "2026-12-31";
  input.value = req.date < "2026-12-01" ? "2026-12-26" : "2026-10-17";
  input.setAttribute("aria-label", "Дата для сравнения");
  const btn = el("button", btnClass);
  btn.type = "button";
  btn.appendChild(icon("calendar", 18));
  btn.appendChild(document.createTextNode("Сравнить с другой датой"));
  btn.addEventListener("click", () => runCompare(req, input.value));
  compare.appendChild(input);
  compare.appendChild(btn);
  return compare;
}

// ---------- Сценарии ----------

async function withLoading(fn) {
  errorEl.hidden = true;
  submitBtn.disabled = true;
  $("submitText").textContent = "Подбираем…";
  showLoading();
  try {
    await fn();
  } catch (e) {
    resultsEl.innerHTML = "";
    showForm();
    showError(e.message);
  } finally {
    submitBtn.disabled = false;
    $("submitText").textContent = "Подобрать";
  }
}

function runSearch() {
  const req = readForm();
  return withLoading(async () => {
    const data = await match(req);
    resultsEl.innerHTML = "";
    resultsEl.appendChild(renderSummary(req, false, data));
    const panels = el("div", "panels");
    panels.appendChild(renderPanel(req, data, false));
    resultsEl.appendChild(panels);
    if (data.status === "none_fit") showQuerySummary(req, data);
    else showForm();
  });
}

function runCompare(req, otherDate) {
  if (!otherDate || otherDate === req.date) {
    showError("Выберите другую дату для сравнения.");
    return;
  }
  const req2 = { ...req, date: otherDate };
  return withLoading(async () => {
    const [a, b] = await Promise.all([match(req), match(req2)]);
    showForm();
    resultsEl.innerHTML = "";
    resultsEl.appendChild(renderSummary(req, true));
    const panels = el("div", "panels two");
    panels.appendChild(renderPanel(req, a, true));
    panels.appendChild(renderPanel(req2, b, true));
    resultsEl.appendChild(panels);
  });
}

function applyPreset(p) {
  $("city").value = p.city;
  $("date").value = p.date;
  $("event_type").value = p.event_type;
  $("category").value = p.category;
  $("budget_kzt").value = p.budget_kzt;
  $("hours").value = "";
  $("language").value = "";
  syncLangChips();
  syncBudgetHint();
}

// ---------- Старт ----------

demoCheckbox.checked = loadDemoFlag();
demoCheckbox.addEventListener("change", () => {
  saveDemoFlag(demoCheckbox.checked);
  errorEl.hidden = true;
});

form.addEventListener("submit", (e) => {
  e.preventDefault();
  runSearch();
});

// Демо-кнопки: подсвечиваем выбранную и запускаем поиск
const presetButtons = document.querySelectorAll("[data-preset]");
presetButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    presetButtons.forEach((b) => b.classList.toggle("active", b === btn));
    applyPreset(PRESETS[btn.dataset.preset]);
    runSearch();
  });
});

$("budget_kzt").addEventListener("input", syncBudgetHint);

loadOptions().then(() => applyPreset(PRESETS.dense));
