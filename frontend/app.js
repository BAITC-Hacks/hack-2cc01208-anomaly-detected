const API_BASE = "http://localhost:8000";

const EXCLUDED_LABELS = {
  busy_on_date: "заняты на эту дату",
  over_budget: "дороже бюджета",
  wrong_format: "не берут этот формат",
  wrong_language: "не говорят на нужном языке",
  too_few_hours: "меньше нужной длительности",
};

const form = document.getElementById("match-form");
const resultsEl = document.getElementById("results");
const submitBtn = document.getElementById("submit-btn");

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function fillSelect(selectEl, values, { keepFirst = false } = {}) {
  const startIndex = keepFirst ? 1 : 0;
  while (selectEl.options.length > startIndex) selectEl.remove(startIndex);
  for (const value of values) {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = value;
    selectEl.appendChild(opt);
  }
}

async function loadOptions() {
  try {
    const res = await fetch(`${API_BASE}/api/options`);
    if (!res.ok) throw new Error(`options request failed: ${res.status}`);
    const opts = await res.json();
    fillSelect(document.getElementById("city"), opts.cities);
    fillSelect(document.getElementById("category"), opts.categories);
    fillSelect(document.getElementById("event_type"), opts.event_formats);
    fillSelect(document.getElementById("language"), opts.languages, { keepFirst: true });
  } catch (err) {
    // Contract explicitly allows this: "если эндпоинта нет — фронт использует
    // захардкоженные списки" — fall back to a minimal hardcoded set so the
    // form still works even if /api/options is down or not implemented.
    fillSelect(document.getElementById("city"), ["Алматы", "Астана"]);
    fillSelect(document.getElementById("category"), ["Ведущий", "Фотограф", "Банкетный зал"]);
    fillSelect(document.getElementById("event_type"), ["свадьба", "корпоратив", "той", "конференция"]);
    fillSelect(document.getElementById("language"), ["русский", "казахский", "английский"], { keepFirst: true });
  }
}

function renderExcluded(excluded) {
  const entries = Object.entries(excluded).filter(([, count]) => count > 0);
  if (entries.length === 0) return null;
  const wrap = el("div", "excluded");
  wrap.appendChild(el("h3", null, "Почему остальные не подошли"));
  const list = el("ul");
  for (const [reason, count] of entries) {
    list.appendChild(el("li", null, `${EXCLUDED_LABELS[reason] ?? reason}: ${count}`));
  }
  wrap.appendChild(list);
  return wrap;
}

function renderCard(card) {
  const node = el("article", "card");
  const header = el("div", "card-header");
  header.appendChild(el("span", "card-name", card.name));
  header.appendChild(el("span", "card-price", `от ${card.price_from_kzt.toLocaleString("ru-RU")} ₸`));
  node.appendChild(header);

  const meta = el("div", "card-meta", `${card.category} · ${card.city}`);
  node.appendChild(meta);

  node.appendChild(el("p", "card-explanation", card.explanation));

  if (card.synthetic) {
    node.appendChild(el("span", "badge-synthetic", "синтетический профиль"));
  }

  return node;
}

function renderResults(data) {
  resultsEl.innerHTML = "";

  const message = el("p", "message", data.message);
  resultsEl.appendChild(message);

  if (data.status === "no_category") {
    resultsEl.appendChild(el("p", "empty-note", "В этом городе такой категории подрядчиков нет."));
    return;
  }

  if (data.status === "none_fit") {
    resultsEl.appendChild(el("p", "empty-note", "Кандидаты есть, но никто не прошёл фильтры."));
    const excludedNode = renderExcluded(data.excluded);
    if (excludedNode) resultsEl.appendChild(excludedNode);
    return;
  }

  // status === "found"
  const cardsWrap = el("div", "cards");
  for (const card of data.cards) cardsWrap.appendChild(renderCard(card));
  resultsEl.appendChild(cardsWrap);

  const excludedNode = renderExcluded(data.excluded);
  if (excludedNode) resultsEl.appendChild(excludedNode);
}

function renderError(err) {
  resultsEl.innerHTML = "";
  const box = el("p", "error", `Не удалось получить ответ от сервера: ${err.message}. Проверьте, что backend запущен на ${API_BASE}.`);
  resultsEl.appendChild(box);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const payload = {
    city: document.getElementById("city").value,
    date: document.getElementById("date").value,
    event_type: document.getElementById("event_type").value,
    category: document.getElementById("category").value,
    budget_kzt: Number(document.getElementById("budget_kzt").value),
  };
  const hours = document.getElementById("hours").value;
  const language = document.getElementById("language").value;
  if (hours) payload.hours = Number(hours);
  if (language) payload.language = language;

  submitBtn.disabled = true;
  submitBtn.textContent = "Подбираем...";
  resultsEl.innerHTML = "";

  try {
    const res = await fetch(`${API_BASE}/api/match`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderResults(data);
  } catch (err) {
    renderError(err);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Подобрать подрядчиков";
  }
});

loadOptions();
