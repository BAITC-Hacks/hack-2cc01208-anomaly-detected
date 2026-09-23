// Фронтенд подбора подрядчиков. Без сборки и без библиотек.
// Поток: форма → POST /api/match (или mockMatch в демо-режиме) → renderView().
// Тексты интерфейса — в i18n.js: t("ключ") и vl(значение из API).

// Адрес бэкенда. Можно переопределить так: index.html?api=http://192.168.1.10:8000
const API_BASE = new URLSearchParams(location.search).get("api") || "http://localhost:8000";
const MATCH_TIMEOUT_MS = 15000;

// Запасные списки, если GET /api/options недоступен (значения — как в API, на русском)
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

// Причины исключения (поле excluded в ответе); подписи — t("excludedLabel", key, n)
const EXCLUDED_KEYS = ["busy_on_date", "over_budget", "wrong_format", "wrong_language", "too_few_hours"];

const $ = (id) => document.getElementById(id);
const form = $("form");
const submitBtn = $("submitBtn");
const resultsEl = $("results");
const errorEl = $("error");
const demoCheckbox = $("demoMode");

let formLanguages = FALLBACK_OPTIONS.languages; // языки для чипов формы
let lastView = null;  // последний показанный результат — перерисовываем его при смене языка
let lastError = null; // последняя ошибка — тоже переводим при смене языка
let loading = false;

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

// Части запроса для сводки: [{text, cls}]
function requestParts(req) {
  const parts = [
    { text: vl(req.city) },
    { text: formatDate(req.date), cls: "date" },
    { text: vl(req.event_type) },
    { text: vl(req.category) },
    { text: t("upTo", formatPrice(req.budget_kzt)), cls: "budget" }
  ];
  if (req.hours) parts.push({ text: t("hoursShort", req.hours) });
  if (req.language) parts.push({ text: vl(req.language) });
  return parts;
}

// Ошибка с ключом перевода: текст подставится на текущем языке
function i18nError(key, ...args) {
  const e = new Error(key);
  e.i18n = { key, args };
  return e;
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

// В option.value — русское значение для API, в тексте — перевод
function fillSelect(select, values, withEmpty) {
  select.innerHTML = "";
  if (withEmpty) select.appendChild(new Option(t("anyLang"), ""));
  values.forEach((v) => select.appendChild(new Option(vl(v), v)));
}
function relabelSelects() {
  ["city", "event_type", "category", "language"].forEach((id) => {
    Array.from($(id).options).forEach((o) => { o.text = o.value ? vl(o.value) : t("anyLang"); });
  });
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

// Вызов бэкенда или mock. Бросает ошибку с ключом перевода.
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
    if (e.name === "AbortError") throw i18nError("errTimeout");
    throw i18nError("errNetwork", API_BASE);
  } finally {
    clearTimeout(timer);
  }

  if (!res.ok) throw i18nError("errStatus", res.status);
  const data = await res.json().catch(() => null);
  if (!data || !data.status) throw i18nError("errFormat");
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
  fillSelect($("language"), opts.languages, true);
  formLanguages = opts.languages;
  renderLangChips();
}

// Чипы языка: одиночный выбор, значение пишем в скрытый select#language (его читает readForm)
function renderLangChips() {
  const box = $("langChips");
  box.innerHTML = "";
  [""].concat(formLanguages).forEach((lang) => {
    const b = el("button", "lang-chip", lang ? vl(lang) : t("anyLang"));
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
  $("budgetHint").textContent = v > 0 ? t("upTo", formatPrice(v)) : "";
}

// ---------- Отрисовка ----------

// Причины отсева с ненулевым количеством: [{key, count, label}]
function excludedItems(excluded) {
  return EXCLUDED_KEYS
    .filter((k) => excluded && excluded[k] > 0)
    .map((k) => ({ key: k, count: excluded[k], label: t("excludedLabel", k, excluded[k]) }));
}

function renderCard(card, rank) {
  const node = el("article", "card");

  // Шапка: ранг · имя + категория/город · цена (на телефоне цена уходит под имя)
  const head = el("div", "card-head");
  head.appendChild(el("div", `rank rank-${rank}`, String(rank)));
  const who = el("div", "who");
  const nameLine = el("div", "name-line");
  nameLine.appendChild(el("h3", "name", card.name));
  if (card.synthetic) nameLine.appendChild(el("span", "badge", t("synthetic")));
  who.appendChild(nameLine);
  const where = el("div", "where");
  where.appendChild(document.createTextNode(`${vl(card.category)} · `));
  where.appendChild(icon("pin", 14));
  where.appendChild(document.createTextNode(vl(card.city)));
  who.appendChild(where);
  head.appendChild(who);
  const priceBox = el("div", "price-box");
  priceBox.appendChild(el("span", "price-label", t("price")));
  priceBox.appendChild(el("span", "price", t("priceFrom", formatPrice(card.price_from_kzt))));
  head.appendChild(priceBox);
  node.appendChild(head);

  // Главное на карточке — объяснение, крупно и в кавычках. Текст от бэкенда — как есть.
  const why = el("blockquote", "why");
  why.setAttribute("aria-label", t("whyAria"));
  why.appendChild(icon("trend", 22));
  const txt = el("div", "why-text");
  txt.appendChild(el("p", "explanation", `«${card.explanation}»`));
  if (t("explNote")) txt.appendChild(el("p", "expl-note", t("explNote"))); // «объяснение на русском» для KZ/EN
  why.appendChild(txt);
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

// Имена из excluded_list, сгруппированные по причине
function namesByReason(data) {
  const names = {};
  (data.excluded_list || []).forEach((x) => {
    if (x && x.name && x.reason) (names[x.reason] = names[x.reason] || []).push(x.name);
  });
  return names;
}

// Полоса «Отсеяно N кандидатов: …» под карточками.
// Если бэкенд вернул excluded_list [{name, reason}], по кнопке раскрываются имена по причинам.
function renderExcludedBar(data, openByDefault) {
  const items = excludedItems(data.excluded);
  if (!items.length) return null;
  const total = items.reduce((s, i) => s + i.count, 0);
  const names = namesByReason(data);
  const hasNames = Object.keys(names).length > 0;

  const line = el("div", "excluded-line");
  line.appendChild(icon("info", 18));
  const text = el("span", "excluded-text");
  text.appendChild(el("strong", "", t("excludedTotal", total)));
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
  toggle.appendChild(el("span", "t-show", t("showDetails")));
  toggle.appendChild(el("span", "t-hide", t("hideDetails")));
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
  h.appendChild(document.createTextNode(t("tcTitle")));
  head.appendChild(h);
  head.appendChild(el("span", "tc-total", t("tcTotal", total)));
  box.appendChild(head);

  // Итог фильтрации: основные причины показываем и с нулём, язык/часы — если были в запросе
  const keys = ["busy_on_date", "over_budget", "wrong_format"];
  if (req.language || ex.wrong_language) keys.push("wrong_language");
  if (req.hours || ex.too_few_hours) keys.push("too_few_hours");
  const parts = keys.map((k) => {
    const txt = `${ex[k] || 0} ${t("excludedLabel", k, ex[k] || 0)}`;
    return k === "busy_on_date" ? `${txt} (${formatDate(req.date)})` : txt;
  });

  const result = el("div", "tc-result");
  const txt = el("div", "tc-result-text");
  txt.appendChild(el("div", "tc-label", t("tcResult")));
  txt.appendChild(el("div", "", t("tcExcluded", parts.join(" · "))));
  result.appendChild(txt);
  const tags = el("div", "tc-tags");
  excludedItems(ex).forEach((i) => tags.appendChild(el("span", `tag ${i.key}`, `${i.count} ${i.label}`)));
  result.appendChild(tags);
  box.appendChild(result);

  // Зачёркнутые имена — только если они реально пришли в ответе
  const list = (data.excluded_list || []).filter((x) => x && x.name && x.reason);
  if (list.length) {
    box.appendChild(el("div", "tc-label", t("tcOut")));
    const grid = el("div", "out-list");
    list.forEach((x) => {
      const item = el("div", `out ${x.reason}`);
      const main = el("div", "out-main");
      main.appendChild(el("s", "out-name", x.name));
      const why = EXCLUDED_KEYS.includes(x.reason) ? t("reasonShort", x.reason, formatDate(req.date)) : x.reason;
      main.appendChild(el("span", "out-reason", why));
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
  titles.appendChild(el("span", "nocat-label", t("nocatLabel")));
  titles.appendChild(el("h2", "nocat-title", t("nocatTitle", vl(req.city), vl(req.category), req.city === "Зарубежье")));
  head.appendChild(titles);
  box.appendChild(head);

  const why = el("div", "nocat-why");
  const wh = el("div", "nocat-why-title");
  wh.appendChild(icon("bulb", 20));
  wh.appendChild(document.createTextNode(t("nocatWhy")));
  why.appendChild(wh);
  why.appendChild(el("p", "", data.message || t("nocatFallback")));
  box.appendChild(why);

  // Только города, которые есть в форме и отличаются от текущего
  const cityOptions = Array.from($("city").options).map((o) => o.value);
  const targets = [["Алматы", "searchAlmaty"], ["Астана", "searchAstana"]]
    .filter(([c]) => c !== req.city && cityOptions.includes(c));
  if (withActions && targets.length) {
    box.appendChild(el("div", "nocat-actions-label", t("nocatActions")));
    const actions = el("div", "nocat-actions");
    targets.forEach(([c, key]) => {
      const b = el("button", "secondary");
      b.type = "button";
      b.appendChild(icon("building", 18));
      b.appendChild(document.createTextNode(t(key)));
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
  body.appendChild(el("span", "nf-label", t("nfLabel")));
  body.appendChild(el("h2", "nf-title", t("nfTitle")));
  if (data.message) body.appendChild(el("p", "nf-message", data.message));
  box.appendChild(body);
  return box;
}

// Иконки причин; заголовок и текст — из i18n (t("reason")[key])
const REASON_ICONS = { busy_on_date: "lock", over_budget: "wallet", wrong_format: "tags", wrong_language: "lang", too_few_hours: "clock" };

// Воронка: полоса из реальных счётчиков excluded (ширина сегмента ∝ числу), легенда и строки причин
function renderFunnel(req, data) {
  const items = excludedItems(data.excluded);
  if (!items.length) return null;
  const total = items.reduce((s, i) => s + i.count, 0);
  const names = namesByReason(data);

  const box = el("section", "funnel");
  const head = el("div", "funnel-head");
  const ht = el("div");
  const h = el("h3", "funnel-title");
  h.appendChild(icon("funnel", 20));
  h.appendChild(document.createTextNode(t("funnelTitle")));
  ht.appendChild(h);
  ht.appendChild(el("p", "funnel-sub", t("funnelSub", total)));
  head.appendChild(ht);
  head.appendChild(el("span", "funnel-chip", t("funnelChip", total)));
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

  // Данные для заголовков причин: всё из запроса пользователя
  const facts = {
    date: formatDate(req.date),
    budget: `${formatPrice(req.budget_kzt).replace(/ /g, " ")} ₸`, // сумма не рвётся переносом
    format: vl(req.event_type),
    language: vl(req.language),
    hours: req.hours
  };
  const rows = el("div", "funnel-rows");
  items.forEach((i) => {
    const [titleFn, text] = t("reason")[i.key];
    const row = el("div", `frow ${i.key}`);
    const ic = icon(REASON_ICONS[i.key] || "info", 20);
    ic.classList.add("frow-icon");
    row.appendChild(ic);
    const body = el("div", "frow-body");
    const tt = el("div", "frow-title");
    tt.appendChild(el("span", "", titleFn(facts)));
    tt.appendChild(el("span", "frow-badge", t("contractors", i.count)));
    body.appendChild(tt);
    body.appendChild(el("p", "frow-text", text));
    if (names[i.key]) body.appendChild(el("p", "frow-names", t("who") + names[i.key].join(", ")));
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
  h.appendChild(document.createTextNode(t("qsTitle")));
  head.appendChild(h);
  head.appendChild(el("span", "qs-zero", t("qsZero")));
  box.appendChild(head);

  const rows = [
    [t("qsCity"), vl(req.city), null],
    [t("qsDate"), formatDate(req.date), "busy_on_date"],
    [t("qsFormat"), vl(req.event_type), "wrong_format"],
    [t("qsCategory"), vl(req.category), null],
    [t("qsBudget"), t("upTo", formatPrice(req.budget_kzt)), "over_budget"]
  ];
  if (req.hours) rows.push([t("qsHours"), t("hoursShort", req.hours), "too_few_hours"]);
  rows.push([t("qsLanguage"), req.language ? vl(req.language) : t("anyLang"), "wrong_language"]);

  rows.forEach(([label, value, key]) => {
    const hit = key && ex[key] > 0;
    const r = el("div", hit ? "qs-row hit" : "qs-row");
    const top = el("div", "qs-row-top");
    top.appendChild(el("span", "qs-label", label));
    top.appendChild(el("span", "qs-value", value));
    r.appendChild(top);
    if (hit) r.appendChild(el("div", "qs-note", t("qsNote", ex[key])));
    box.appendChild(r);
  });

  const btn = el("button", "primary");
  btn.type = "button";
  btn.appendChild(icon("sliders", 18));
  btn.appendChild(document.createTextNode(t("qsEdit")));
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

  if (data.status === "found") {
    // 3 из 3 — без баннера (итог в сводке), сообщение бэкенда — тихой строкой.
    // Меньше 3 — янтарный баннер с объяснением «почему меньше».
    if (cards.length >= 3) {
      if (data.message) panel.appendChild(el("p", "found-note", data.message));
    } else {
      const b = banner("warning fewer", "alert", t("fewerTitle", cards.length), data.message);
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

  if (demoCheckbox.checked) panel.appendChild(el("p", "mock-note", t("mockNote")));
  return panel;
}

// Загрузка: 3 карточки-скелетона с переливом
function showLoading() {
  resultsEl.innerHTML = "";
  resultsEl.appendChild(el("p", "loading-text", t("loading")));
  const list = el("div", "cards");
  for (let i = 0; i < 3; i++) list.appendChild(el("div", "skeleton"));
  resultsEl.appendChild(list);
}

// Ошибку запоминаем, чтобы перевести её при смене языка
function showError(e) {
  lastError = e;
  errorEl.textContent = e.i18n ? t(e.i18n.key, ...e.i18n.args) : e.message;
  errorEl.hidden = false;
}
function hideError() {
  lastError = null;
  errorEl.hidden = true;
}

// Сводка запроса + «Сравнить с другой датой» (тот же запрос, другая дата, результаты рядом)
function renderSummary(req, comparing, data) {
  const bar = el("div", "summary");

  const left = el("div", "summary-left");
  const parts = el("div", "summary-parts");
  let list = requestParts(req);
  if (comparing) list = list.filter((p) => p.cls !== "date"); // в режиме сравнения даты показаны над каждой колонкой
  list.forEach((p, i) => {
    if (i) parts.appendChild(el("span", "dot", "·"));
    parts.appendChild(el("span", p.cls === "budget" ? "budget" : "", p.text));
  });
  left.appendChild(parts);
  // «3 из 10 кандидатов»: всего = карточки + все отсеянные (только если категория в городе есть)
  if (data && data.status !== "no_category") {
    const shown = (data.cards || []).length;
    const total = shown + excludedItems(data.excluded).reduce((s, i) => s + i.count, 0);
    if (total > 0) left.appendChild(el("span", "count-chip", t("countChip", shown, total)));
  }
  bar.appendChild(left);

  // Когда найдено меньше 3 или никто не подошёл, сравнение — ссылкой в баннере; здесь не дублируем
  const fewer = data && data.status === "found" && (data.cards || []).length < 3;
  const noCategory = data && data.status === "no_category"; // категории нет ни на какую дату
  const noneFit = data && data.status === "none_fit";
  if (!fewer && !noCategory && !noneFit) bar.appendChild(compareControls(req, "secondary"));
  return bar;
}

function compareDateInput(req) {
  const input = el("input");
  input.type = "date";
  input.min = "2026-09-23";
  input.max = "2026-12-31";
  input.value = req.date < "2026-12-01" ? "2026-12-26" : "2026-10-17";
  input.setAttribute("aria-label", t("compareAria"));
  return input;
}

// Ссылка «Сравнить с другой датой →» внутри баннера; по клику под баннером
// раскрывается компактная строка: поле даты + кнопка «Сравнить».
function addCompareReveal(req, linkParent, panel) {
  const link = el("button", "link-btn", t("compareLink"));
  link.type = "button";
  const row = el("div", "compare-inline");
  row.hidden = true;
  const input = compareDateInput(req);
  const go = el("button", "outline-sm", t("compareGo"));
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
  const input = compareDateInput(req);
  const btn = el("button", btnClass);
  btn.type = "button";
  btn.appendChild(icon("calendar", 18));
  btn.appendChild(document.createTextNode(t("compareBtn")));
  btn.addEventListener("click", () => runCompare(req, input.value));
  compare.appendChild(input);
  compare.appendChild(btn);
  return compare;
}

// Нарисовать последний результат (после запроса или при смене языка — без нового запроса)
function renderView(onLangSwitch) {
  if (!lastView) return;
  resultsEl.innerHTML = "";
  if (lastView.mode === "search") {
    const { req, data } = lastView;
    resultsEl.appendChild(renderSummary(req, false, data));
    const panels = el("div", "panels");
    panels.appendChild(renderPanel(req, data, false));
    resultsEl.appendChild(panels);
    // При смене языка не сворачиваем форму, если пользователь уже нажал «Изменить условия»
    const summaryOpen = !$("querySummary").hidden;
    if (data.status === "none_fit" && (!onLangSwitch || summaryOpen)) showQuerySummary(req, data);
    else if (data.status !== "none_fit") showForm();
  } else {
    const { req, req2, a, b } = lastView;
    showForm();
    resultsEl.appendChild(renderSummary(req, true));
    const panels = el("div", "panels two");
    panels.appendChild(renderPanel(req, a, true));
    panels.appendChild(renderPanel(req2, b, true));
    resultsEl.appendChild(panels);
  }
}

// ---------- Сценарии ----------

async function withLoading(fn) {
  hideError();
  loading = true;
  submitBtn.disabled = true;
  $("submitText").textContent = t("submitting");
  showLoading();
  try {
    await fn();
  } catch (e) {
    lastView = null;
    resultsEl.innerHTML = "";
    showForm();
    showError(e);
  } finally {
    loading = false;
    submitBtn.disabled = false;
    $("submitText").textContent = t("submit");
  }
}

function runSearch() {
  const req = readForm();
  return withLoading(async () => {
    const data = await match(req);
    lastView = { mode: "search", req, data };
    renderView(false);
  });
}

function runCompare(req, otherDate) {
  if (!otherDate || otherDate === req.date) {
    showError(i18nError("errSameDate"));
    return;
  }
  const req2 = { ...req, date: otherDate };
  return withLoading(async () => {
    const [a, b] = await Promise.all([match(req), match(req2)]);
    lastView = { mode: "compare", req, req2, a, b };
    renderView(false);
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

// ---------- Язык интерфейса ----------

// Статичные тексты из index.html: data-i18n (текст), data-i18n-ph (placeholder),
// data-i18n-title (подсказка), data-i18n-aria (aria-label)
function applyStaticTexts() {
  document.documentElement.lang = UI_LANG;
  document.title = t("title");
  document.querySelectorAll("[data-i18n]").forEach((n) => { n.textContent = t(n.dataset.i18n); });
  document.querySelectorAll("[data-i18n-ph]").forEach((n) => { n.placeholder = t(n.dataset.i18nPh); });
  document.querySelectorAll("[data-i18n-title]").forEach((n) => { n.title = t(n.dataset.i18nTitle); });
  document.querySelectorAll("[data-i18n-aria]").forEach((n) => { n.setAttribute("aria-label", t(n.dataset.i18nAria)); });
  if (loading) $("submitText").textContent = t("submitting");
  document.querySelectorAll("[data-ui-lang]").forEach((b) => {
    const on = b.dataset.uiLang === UI_LANG;
    b.classList.toggle("on", on);
    b.setAttribute("aria-pressed", on ? "true" : "false");
  });
}

function setUiLang(code) {
  UI_LANG = code;
  saveUiLang();
  applyStaticTexts();
  relabelSelects();
  renderLangChips();
  syncBudgetHint();
  if (!loading) renderView(true);
  if (lastError) showError(lastError);
}

// ---------- Старт ----------

loadUiLang();
applyStaticTexts();
document.querySelectorAll("[data-ui-lang]").forEach((b) => {
  b.addEventListener("click", () => setUiLang(b.dataset.uiLang));
});

demoCheckbox.checked = loadDemoFlag();
demoCheckbox.addEventListener("change", () => {
  saveDemoFlag(demoCheckbox.checked);
  hideError();
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
