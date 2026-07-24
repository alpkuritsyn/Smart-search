const form = document.querySelector('#search-form');
const queryInput = document.querySelector('#query-input');
const modeSelect = document.querySelector('#mode-select');
const submitButton = form.querySelector('button[type="submit"]');
const results = document.querySelector('#results');
const statusPanel = document.querySelector('#status-panel');
const messagePanel = document.querySelector('#message-panel');
const debugPanel = document.querySelector('#debug-panel');
const debugJson = document.querySelector('#debug-json');
const cardTemplate = document.querySelector('#product-card-template');

const FIXTURES = {
  'краска тикурила': 'fixtures/paint-tikkurila.json',
  'неизвестный запрос': 'fixtures/empty.json',
  'старый поиск': 'fixtures/fallback.json'
};

let activeController = null;
let requestSequence = 0;

function setMessage(text = '', type = '') {
  messagePanel.hidden = !text;
  messagePanel.className = `message-panel ${type}`.trim();
  messagePanel.textContent = text;
}

function setLoading(isLoading) {
  submitButton.disabled = isLoading;
  submitButton.textContent = isLoading ? 'Ищем…' : 'Найти';
  if (isLoading) setMessage('Нормализуем запрос и собираем товарные группы…', 'loading');
}

function formatPrice(value) {
  if (typeof value !== 'number') return 'Цена не указана';
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(value);
}

function safeUrl(value) {
  if (!value) return null;
  try {
    const parsed = new URL(value, window.location.href);
    return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : null;
  } catch {
    return null;
  }
}

function createChip(label, value, className = '') {
  const chip = document.createElement('span');
  chip.className = `status-chip ${className}`.trim();
  const strong = document.createElement('strong');
  strong.textContent = label;
  chip.append(strong, document.createTextNode(` ${value}`));
  return chip;
}

function renderStatus(data) {
  statusPanel.replaceChildren();
  const query = data.query || {};
  const meta = data.meta || {};
  statusPanel.append(
    createChip('Нормализовано:', query.normalized || query.raw || '—'),
    createChip('Тип:', query.product_type_display || 'не распознан'),
    createChip('Бренд:', query.brand_display || 'не распознан'),
    createChip('Стратегия:', meta.strategy || '—', 'strategy')
  );
  if (meta.fallback_used) statusPanel.append(createChip('Fallback:', 'старый поиск', 'fallback'));
  const resolutions = Array.isArray(query.entity_resolutions) && query.entity_resolutions.length
    ? query.entity_resolutions
    : (query.entity_resolution ? [query.entity_resolution] : []);
  resolutions.forEach((resolution) => {
    const entityLabel = resolution.entity_type === 'brand'
      ? 'бренд'
      : (resolution.entity_type === 'product_type' ? 'тип товара' : 'товар');
    if (resolution?.status === 'resolved' || resolution?.status === 'exact') {
      statusPanel.append(createChip('Исправлено:', `${resolution.matched_text} → ${resolution.display} (${entityLabel})`, 'strategy'));
    } else if (resolution?.status === 'best_effort') {
      statusPanel.append(createChip('Предположение:', `${resolution.matched_text} → ${resolution.display} (${entityLabel})`, 'fallback'));
    } else if (resolution?.status === 'ambiguous') {
      statusPanel.append(createChip('Уточнение:', `${resolution.matched_text}: название неоднозначно`, 'fallback'));
    }
  });
  statusPanel.hidden = false;
}

function createProductCard(product) {
  const card = cardTemplate.content.firstElementChild.cloneNode(true);
  card.querySelector('.product-media span').textContent = (product.brand || product.name || '?').trim().slice(0, 1).toUpperCase();
  card.querySelector('.product-price').textContent = formatPrice(product.price);
  card.querySelector('.product-name').textContent = product.name || 'Без названия';
  card.querySelector('.product-meta').textContent = [product.brand, product.subcategory].filter(Boolean).join(' · ');
  const link = card.querySelector('.product-link');
  const url = safeUrl(product.url);
  if (url) {
    link.href = url;
  } else {
    link.remove();
  }
  return card;
}

function createSection(group, kind) {
  const section = document.createElement('section');
  section.className = 'result-section';
  const heading = document.createElement('div');
  heading.className = 'section-heading';
  const copy = document.createElement('div');
  const kicker = document.createElement('p');
  kicker.className = 'section-kicker';
  kicker.textContent = kind === 'primary' ? 'Основная выдача' : 'Может понадобиться';
  const title = document.createElement('h2');
  title.textContent = group.title || (kind === 'primary' ? 'Найденные товары' : 'Комплементы');
  copy.append(kicker, title);
  const count = document.createElement('div');
  count.className = 'result-count';
  count.textContent = `${(group.products || []).length} товар(а)`;
  heading.append(copy, count);
  section.append(heading);

  if (kind === 'complement' && group.rationale) {
    const note = document.createElement('p');
    note.className = 'relation-note';
    const badge = document.createElement('span');
    badge.className = 'relation-badge';
    badge.textContent = group.relation || 'COMPLEMENT';
    note.append(badge, document.createTextNode(group.rationale));
    section.append(note);
  }

  const products = Array.isArray(group.products) ? group.products : [];
  if (products.length) {
    const grid = document.createElement('div');
    grid.className = 'product-grid';
    products.forEach(product => grid.append(createProductCard(product)));
    section.append(grid);
  } else if (group.data_gap) {
    const gap = document.createElement('div');
    gap.className = 'data-gap';
    const strong = document.createElement('strong');
    strong.textContent = 'Данные по категории ещё загружаются';
    gap.append(strong, document.createTextNode(group.data_gap_message || 'Product Parser Agent должен добавить реальные карточки.'));
    section.append(gap);
  } else if (kind === 'primary') {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = 'Товары не найдены. Поиск не подставляет случайные карточки.';
    section.append(empty);
  } else {
    return null;
  }
  return section;
}

function render(data) {
  results.replaceChildren();
  renderStatus(data);
  const primary = createSection(data.primary || { products: [] }, 'primary');
  if (primary) results.append(primary);
  (Array.isArray(data.complements) ? data.complements : []).forEach(group => {
    const section = createSection(group, 'complement');
    if (section) results.append(section);
  });
  debugJson.textContent = JSON.stringify(data, null, 2);
  debugPanel.hidden = false;
}

async function loadData(query, mode, signal) {
  if (mode === 'api') {
    const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`, { headers: { Accept: 'application/json' }, signal });
    if (!response.ok) throw new Error(`Backend вернул HTTP ${response.status}`);
    return response.json();
  }
  const fixture = FIXTURES[query.toLocaleLowerCase('ru-RU')];
  if (!fixture) throw new Error('Для этого запроса ещё нет demo fixture. Выберите один из примеров или включите Backend API.');
  const response = await fetch(fixture, { cache: 'no-store', signal });
  if (!response.ok) throw new Error('Не удалось загрузить demo fixture');
  return response.json();
}

async function runSearch(query) {
  if (activeController) activeController.abort();
  activeController = new AbortController();
  const sequence = ++requestSequence;
  setLoading(true);
  results.replaceChildren();
  statusPanel.hidden = true;
  debugPanel.hidden = true;
  try {
    const data = await loadData(query, modeSelect.value, activeController.signal);
    if (sequence !== requestSequence) return;
    setMessage();
    render(data);
  } catch (error) {
    if (error.name === 'AbortError' || sequence !== requestSequence) return;
    setMessage(error.message || 'Не удалось выполнить поиск', 'error');
  } finally {
    if (sequence === requestSequence) setLoading(false);
  }
}

form.addEventListener('submit', event => {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (query) runSearch(query);
});

document.querySelectorAll('[data-query]').forEach(button => {
  button.addEventListener('click', () => {
    queryInput.value = button.dataset.query;
    queryInput.focus();
    runSearch(button.dataset.query);
  });
});

runSearch(queryInput.value.trim());
