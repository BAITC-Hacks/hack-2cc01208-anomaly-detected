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
const EXCLUDED_LABELS = {
  busy_on_date: "заняты в эту дату",
  over_budget: "дороже бюджета",
  wrong_format: "не берут этот формат",
  wrong_language: "не работают на этом языке",
  too_few_hours: "не могут работать столько часов"
};

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
  spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>'
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
}

// ---------- Отрисовка ----------

// Причины отсева с ненулевым количеством: [{key, count, label}]
function excludedItems(excluded) {
  return Object.keys(EXCLUDED_LABELS)
    .filter((k) => excluded && excluded[k] > 0)
    .map((k) => ({ key: k, count: excluded[k], label: EXCLUDED_LABELS[k] }));
}

// "1 кандидат" / "2 кандидата" / "5 кандидатов"
function candidatesWord(n) {
  const d = n % 10, dd = n % 100;
  if (d === 1 && dd !== 11) return "кандидат";
  if (d >= 2 && d <= 4 && (dd < 12 || dd > 14)) return "кандидата";
  return "кандидатов";
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
  who.appendChild(el("div", "where", `${card.category} · ${card.city}`));
  head.appendChild(who);
  const priceBox = el("div", "price-box");
  priceBox.appendChild(el("span", "price-label", "Стоимость"));
  priceBox.appendChild(el("span", "price", `от ${formatPrice(card.price_from_kzt)} ₸`));
  head.appendChild(priceBox);
  node.appendChild(head);

  // Главное на карточке — объяснение
  const why = el("div", "why");
  const label = el("div", "why-label");
  label.appendChild(icon("spark", 16));
  label.appendChild(document.createTextNode("Почему именно этот подрядчик"));
  why.appendChild(label);
  why.appendChild(el("p", "explanation", card.explanation));
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

// Блок «Прозрачность подбора»: сколько кандидатов отсеяно и по какой причине.
// Если бэкенд вернёт excluded_list [{name, reason}], покажем и имена.
function renderTransparency(data) {
  const items = excludedItems(data.excluded);
  if (!items.length) return null;
  const total = items.reduce((s, i) => s + i.count, 0);
  const names = {};
  (data.excluded_list || []).forEach((x) => {
    if (x && x.name && x.reason) (names[x.reason] = names[x.reason] || []).push(x.name);
  });

  const box = el("section", "transparency");
  const head = el("div", "transparency-head");
  head.appendChild(icon("funnel", 16));
  head.appendChild(document.createTextNode("Прозрачность подбора"));
  box.appendChild(head);
  box.appendChild(el("p", "transparency-total", `Отсеяно ${total} ${candidatesWord(total)}:`));

  const grid = el("div", "reasons");
  items.forEach((i) => {
    const r = el("div", `reason ${i.key}`);
    r.appendChild(el("span", "", i.label));
    r.appendChild(el("span", "count", String(i.count)));
    if (names[i.key]) {
      r.classList.add("has-names");
      r.appendChild(el("span", "reason-names", names[i.key].join(", ")));
    }
    grid.appendChild(r);
  });
  box.appendChild(grid);
  return box;
}

// Одна панель результата: баннер статуса, карточки, прозрачность отсева
function renderPanel(req, data, dateLabel) {
  const panel = el("section", "panel");
  if (dateLabel) panel.appendChild(el("div", "panel-date", formatDate(req.date)));

  const cards = data.cards || [];
  const title = STATUS_TITLES[data.status] || data.status;

  if (data.status === "found") {
    // 3 карточки — спокойный баннер; меньше 3 — янтарный, с объяснением «почему меньше»
    const full = cards.length >= 3;
    panel.appendChild(banner(full ? "success" : "warning", full ? "check" : "alert",
      `${title}: ${cards.length} из 3`, data.message));
  } else if (data.status === "no_category") {
    panel.appendChild(banner("info", "search", title, data.message, "Попробуйте другой город или похожую категорию."));
  } else {
    panel.appendChild(banner("warning", "alert", title, data.message));
  }

  if (cards.length) {
    const list = el("div", "cards");
    cards.forEach((c, i) => list.appendChild(renderCard(c, i + 1)));
    panel.appendChild(list);
  }

  const t = renderTransparency(data);
  if (t) panel.appendChild(t);

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
function renderSummary(req, comparing) {
  const bar = el("div", "summary");

  const parts = el("div", "summary-parts");
  const list = requestParts(req);
  if (comparing) list.splice(1, 1); // в режиме сравнения даты показаны над каждой колонкой
  list.forEach((p, i) => {
    if (i) parts.appendChild(el("span", "dot", "·"));
    parts.appendChild(el("span", p.startsWith("до ") ? "budget" : "", p));
  });
  bar.appendChild(parts);

  const compare = el("div", "compare");
  const input = el("input");
  input.type = "date";
  input.min = "2026-09-23";
  input.max = "2026-12-31";
  input.value = req.date < "2026-12-01" ? "2026-12-26" : "2026-10-17";
  input.setAttribute("aria-label", "Дата для сравнения");
  const btn = el("button", "secondary");
  btn.type = "button";
  btn.appendChild(icon("calendar", 18));
  btn.appendChild(document.createTextNode("Сравнить с другой датой"));
  btn.addEventListener("click", () => runCompare(req, input.value));
  compare.appendChild(input);
  compare.appendChild(btn);
  bar.appendChild(compare);
  return bar;
}

// ---------- Сценарии ----------

async function withLoading(fn) {
  errorEl.hidden = true;
  submitBtn.disabled = true;
  submitBtn.textContent = "Подбираем…";
  showLoading();
  try {
    await fn();
  } catch (e) {
    resultsEl.innerHTML = "";
    showError(e.message);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Подобрать";
  }
}

function runSearch() {
  const req = readForm();
  return withLoading(async () => {
    const data = await match(req);
    resultsEl.innerHTML = "";
    resultsEl.appendChild(renderSummary(req, false));
    const panels = el("div", "panels");
    panels.appendChild(renderPanel(req, data, false));
    resultsEl.appendChild(panels);
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

loadOptions().then(() => applyPreset(PRESETS.dense));
