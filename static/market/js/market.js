// static/market/js/market.js
// Головна логіка сторінки STL Market:
// - тягнемо список моделей з /api/market/items або /api/market/my
// - реагуємо на пошук, кнопки фільтрів, пагінацію
// - рендеримо грід карток + "мої оголошення"

import {
  fetchItems,
  fetchMyItems,
  toggleFavorite,
} from "./api.js";

/* ==============================
 * 0) КОНФІГ + СТАН
 * ============================== */

// якщо body не має data-market-page, пробуємо визначити по DOM
const PAGE_TYPE =
  document.body.dataset.marketPage ||
  (document.getElementById("my-grid") ? "my" : "list");

// кореневі елементи (якщо є)
const ROOT = document.querySelector("[data-market-root]") || document.body;
const NOTICE = document.querySelector("[data-market-notice]");

const state = {
  q: "",
  page: 1,
  per_page: 24,
  sort: "new",      // new | popular | top | price_asc | price_desc | prints | prints_7d | prints_30d
  mode: null,       // top | null
  category: null,   // slug категорії
  free: null,       // null / 1 / 0
  tag: null,        // швидкий тег із .mqf-chip (dragon / stand / toy / cosplay / other)
  author: null,     // filter by author username (clickable from creator stats)
  author_id: null,  // filter by author (from URL params)
  min_proof_score: null,  // minimum proof score filter
  auto_presets: null,     // auto presets filter (1 or null)
  saved: null,      // ❤️ Instagram-style saved filter (1 or null)
};

// id останнього запиту — щоб ігнорувати повільні старі респонси
let lastRequestId = 0;

/* ==============================
 * 1) ХЕЛПЕРИ
 * ============================== */

function setNotice(text, kind = "") {
  if (!NOTICE) return;
  if (!text) {
    NOTICE.style.display = "none";
    NOTICE.textContent = "";
    NOTICE.classList.remove("error");
    return;
  }
  NOTICE.style.display = "";
  NOTICE.textContent = text;
  NOTICE.classList.toggle("error", kind === "error");
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// Нормалізація ціни → центи
function normalizePriceCents(it) {
  if (typeof it.price_cents === "number") return it.price_cents;
  if (typeof it.price === "number") return Math.round(it.price * 100);
  return 0;
}

// debounce для пошуку, щоб не спамити API
function debounce(fn, delay = 300) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), delay);
  };
}

/* ==============================
 * 2) СТАН ІЗ DOM (фільтри)
 * ============================== */

function buildStateFromDOM() {
  // пошук
  const qInput =
    document.getElementById("q") || document.getElementById("my-search");
  if (qInput) state.q = qInput.value.trim();

  // селекти (якщо є)
  const sortSelect =
    document.querySelector("[data-filter-sort]") ||
    document.getElementById("my-sort");
  if (sortSelect && sortSelect.value) {
    state.sort = sortSelect.value;
  }

  const showSelect = document.querySelector("[data-filter-show]");
  if (showSelect && showSelect.value) {
    const v = showSelect.value;
    if (v === "free") state.free = 1;
    else if (v === "paid") state.free = 0;
    else state.free = null;
  }

  // Proof Score filter
  const proofScoreSelect = document.querySelector("[data-filter-proof-score]");
  if (proofScoreSelect && proofScoreSelect.value) {
    const v = parseInt(proofScoreSelect.value, 10) || 0;
    state.min_proof_score = v > 0 ? v : null;
  }

  // Auto Presets checkbox
  const autoPresetsCheckbox = document.querySelector("[data-filter-auto-presets]");
  if (autoPresetsCheckbox) {
    state.auto_presets = autoPresetsCheckbox.checked ? 1 : null;
  }

  // чіпси "усі / free / paid" на my.html
  const freeGroup = document.getElementById("my-free-filter");
  if (freeGroup) {
    const active = freeGroup.querySelector(".chip.active");
    if (active) {
      // у верстці data-show="all|free|paid"
      const v = active.dataset.show || active.dataset.free || "all";
      if (v === "free") state.free = 1;
      else if (v === "paid") state.free = 0;
      else state.free = null;
    }
  }

  // активна категорія (кнопки з data-filter-category)
  const activeCat = document.querySelector(
    "[data-filter-category].is-active, [data-filter-category].active"
  );
  state.category = activeCat
    ? (activeCat.dataset.slug || activeCat.dataset.category || null)
    : null;

  // активний швидкий тег (кнопки .mqf-chip[data-filter-tag])
  const activeTagChip = document.querySelector(
    "[data-filter-tag].is-active"
  );
  if (activeTagChip) {
    const tagSlug =
      activeTagChip.dataset.filterTag || activeTagChip.dataset.tag || "all";
    state.tag = tagSlug === "all" ? null : tagSlug.toLowerCase();
  } else {
    state.tag = null;
  }

  // Top Prints mode chip
  const activeModeChip = document.querySelector(
    "[data-mode].is-active"
  );
  if (activeModeChip && activeModeChip.dataset.mode === "top") {
    state.mode = "top";
  } else {
    state.mode = null;
  }
}

/* ==============================
 * 3) ДОДАТКОВИЙ ФРОНТ-ФІЛЬТР ПО ТЕГУ
 * ============================== */

function itemMatchesTag(it, tagSlug) {
  if (!tagSlug) return true; // нема тега — нічого не фільтруємо

  const rawTags = it.tags;
  if (!rawTags) return false;

  // якщо бекенд коли-небудь почне повертати масив тегів
  if (Array.isArray(rawTags)) {
    return rawTags
      .map((t) => String(t || "").toLowerCase())
      .some((t) => t.includes(tagSlug));
  }

  // поточний варіант — строка "dragon, stand, toy"
  const text = String(rawTags || "").toLowerCase();
  const parts = text.split(/[,\s]+/).filter(Boolean);
  return parts.some((p) => p.includes(tagSlug));
}

/* ==============================
 * 4) ГОЛОВНЕ ЗАВАНТАЖЕННЯ СТОРІНКИ
 * ============================== */

async function loadPage(page = 1) {
  const grid =
    document.querySelector("[data-market-grid]") ||
    document.getElementById("my-grid");
  const pag =
    document.querySelector("[data-market-pagination]") ||
    document.getElementById("my-pagination");

  if (!grid) return;

  const emptyBlock = document.getElementById("my-empty");
  const counterText = document.getElementById("my-counter-text");

  state.page = page;
  buildStateFromDOM();

  const reqId = ++lastRequestId; // ідентифікатор цього запиту

  setNotice("", "");
  grid.dataset.loading = "1";
  grid.innerHTML =
    `<div class="market-grid-loading">Завантаження моделей…</div>`;
  if (pag) pag.innerHTML = "";
  if (emptyBlock) emptyBlock.style.display = "none";

  const params = {
    q: state.q || undefined,
    page: state.page,
    per_page: state.per_page,
    sort: state.sort,
    mode: state.mode || undefined,
    category: state.category || undefined,
    free: state.free === null ? undefined : state.free ? 1 : 0,
    author: state.author || undefined,  // Author username filter
    author_id: state.author_id || undefined,
    min_proof_score: state.min_proof_score || undefined,
    auto_presets: state.auto_presets || undefined,
    saved: state.saved || undefined,  // ❤️ Instagram-style saved filter
    // tag спеціально не відправляємо — наразі фільтруємо на фронті
  };
  
  // 🔍 DEBUG: Log if saved filter is active
  if (state.saved === 1) {
    console.log('[market.js] 🔍 Loading saved items (state.saved=1, params.saved=1)');
  }

  let resp;
  try {
    if (PAGE_TYPE === "my") {
      resp = await fetchMyItems(params);
    } else {
      resp = await fetchItems(params);
    }
    // якщо за час очікування стартував інший запит — просто ігноруємо цей
    if (reqId !== lastRequestId) return;
  } catch (err) {
    console.error(err);
    if (reqId !== lastRequestId) return;

    grid.dataset.loading = "0";

    setNotice("Помилка завантаження маркету 😢", "error");
    grid.innerHTML =
      `<div class="market-grid-error">` +
      `Помилка завантаження маркету 😢<br>` +
      `<button type="button" class="btn" id="market-retry">Спробувати ще раз</button>` +
      `</div>`;
    // ✅ Перекладаємо повідомлення про помилку
    window.__i18nTranslate?.(grid);
    const retry = document.getElementById("market-retry");
    if (retry) {
      retry.addEventListener("click", () => loadPage(state.page));
    }
    return;
  }

  grid.dataset.loading = "0";

  // Show/hide Top badges based on mode
  const isTopMode = state.mode === "top";
  document.querySelectorAll("[data-top-badge]").forEach(badge => {
    badge.style.display = isTopMode ? "" : "none";
  });

  // 🔧 Підтримка двох форматів відповіді:
  //  1) { ok, items: [...], total, page, pages }
  //  2) просто масив: [...]
  let items;
  let total;
  let pageResp = state.page;
  let pagesResp = 1;

  if (Array.isArray(resp)) {
    items = resp;
    total = resp.length;
  } else {
    items = (resp && resp.items) || [];
    total =
      resp && typeof resp.total === "number" ? resp.total : items.length;
    pageResp = resp && resp.page ? resp.page : state.page;
    pagesResp = resp && resp.pages ? resp.pages : 1;
  }

  // застосовуємо швидкий тег (фронтовий фільтр)
  if (state.tag) {
    items = items.filter((it) => itemMatchesTag(it, state.tag));
    total = items.length;
  }

  if (!items.length) {
    grid.innerHTML =
      `<div class="market-grid-empty">` +
      `Поки що немає моделей за цим запитом.` +
      `</div>`;
    // ✅ Перекладаємо повідомлення про порожній результат
    window.__i18nTranslate?.(grid);
    setNotice("Поки що немає моделей за цим запитом.", "");
    if (PAGE_TYPE === "my" && emptyBlock) {
      emptyBlock.style.display = "";
    }
  } else {
    grid.innerHTML = items.map(renderItemCard).join("");
    // ✅ Перекладаємо динамічно вставлений DOM
    window.__i18nTranslate?.(grid);
    setNotice("", "");
    if (PAGE_TYPE === "my" && emptyBlock) {
      emptyBlock.style.display = "none";
    }
  }

  // текст лічильника на my.html
  if (PAGE_TYPE === "my" && counterText) {
    const t =
      total === 1 ? "Знайдено 1 оголошення" : `Знайдено ${total} оголошень`;
    counterText.textContent = t;
  }

  // bindFavButtons видалено — делегація в market_listeners.js

  if (pag && pagesResp > 1) {
    pag.innerHTML = renderPagination(pageResp, pagesResp);
    // ✅ Перекладаємо пагінацію
    window.__i18nTranslate?.(pag);
    pag.querySelectorAll("[data-page]").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        ev.preventDefault();
        const p = parseInt(btn.dataset.page || "1", 10) || 1;
        if (p !== state.page) {
          loadPage(p);
          window.scrollTo({ top: 0, behavior: "smooth" });
        }
      });
    });
  }
  
  // Batch load creator stats for all visible cards
  loadCreatorStatsBatch();
  
  // Render author filter chip
  renderAuthorChip();
}

/* ==============================
 * 4.6) RENDER AUTHOR FILTER CHIP
 * ============================== */

function renderAuthorChip() {
  const chip = document.getElementById('author-filter-chip');
  const nameEl = document.getElementById('author-filter-name');
  
  if (!chip || !nameEl) return;
  
  if (state.author) {
    nameEl.textContent = state.author;
    chip.style.display = 'block';
  } else {
    chip.style.display = 'none';
  }
}

/* ==============================
 * 4.5) BATCH LOAD CREATOR STATS
 * ============================== */

async function loadCreatorStatsBatch() {
  const statsEls = document.querySelectorAll('.creator-mini-stats[data-creator]');
  if (statsEls.length === 0) return;
  
  // Collect unique creator usernames
  const creators = new Set();
  statsEls.forEach(el => {
    const creator = el.dataset.creator;
    if (creator && creator.trim()) {
      creators.add(creator.trim());
    }
  });
  
  if (creators.size === 0) return;
  
  try {
    const usersParam = Array.from(creators).join(',');
    const res = await fetch(`/api/creators/stats?users=${encodeURIComponent(usersParam)}`);
    const data = await res.json();
    
    if (!data.ok || !data.stats) return;
    
    // Fill each placeholder
    statsEls.forEach(el => {
      const creator = el.dataset.creator;
      if (!creator) return;
      
      const stats = data.stats[creator];
      if (!stats) return;
      
      // Build mini-stats HTML
      const parts = [];
      
      if (stats.avg_proof_score && stats.avg_proof_score > 0) {
        parts.push(`<span class="creator-quality" title="Average Proof Score">⭐ ${stats.avg_proof_score}</span>`);
      }
      
      if (stats.presets_coverage_percent && stats.presets_coverage_percent > 0) {
        parts.push(`<span class="creator-presets" title="Auto Presets Coverage">🎯 ${stats.presets_coverage_percent}%</span>`);
      }
      
      if (parts.length > 0) {
        el.innerHTML = parts.join(' • ');
        el.style.display = 'block';
        el.classList.add('clickable');
        el.dataset.author = creator;
      }
    });
    
  } catch (err) {
    console.warn('Failed to load batch creator stats:', err);
  }
}

// Click handler for creator stats filter
document.addEventListener('click', (e) => {
  const statsEl = e.target.closest('.creator-mini-stats.clickable');
  if (statsEl && statsEl.dataset.author) {
    e.preventDefault();
    state.author = statsEl.dataset.author;
    state.page = 1;
    loadPage(1);
  }
});

/* ==============================
 * 5) РЕНДЕР КАРТОК
 * ============================== */

/**
 * Маленька плитка для сторінки "Мої оголошення" (my.html)
 */
function renderMyItemCard(it) {
  const id = it.id;

  const rawPriceCents = normalizePriceCents(it);
  const isFree = it.is_free || !rawPriceCents;
  const priceLabel = isFree
    ? "Безкоштовно"
    : (rawPriceCents / 100).toFixed(2) + " zł";

  const downloads = it.downloads || 0;

  // normalize cover (cover_url, cover, first gallery)
  const cover =
    it.cover_url ||
    it.cover ||
    (Array.isArray(it.gallery_urls) && it.gallery_urls[0]) ||
    null;

  return `
<article class="market-card my-card" data-item-id="${id}">
  <div class="market-card-img">
    ${
      cover
        ? `<img src="${cover}" loading="lazy" alt="${escapeHtml(it.title)}">`
        : `<img src="/static/img/placeholder_stl.jpg" loading="lazy" alt="${escapeHtml(it.title)}">`
    }
  </div>
  <div class="market-card-body">
    <div class="market-card-title">${escapeHtml(it.title)}</div>
    <div class="market-card-price">
      <span class="price-main">${priceLabel}</span>
      <span class="market-card-downloads">⬇ ${downloads}</span>
    </div>
  </div>
</article>`;
}

function renderItemCard(it) {
  // 🔥 окрема верстка для сторінки "Мої оголошення"
  if (PAGE_TYPE === "my") {
    return renderMyItemCard(it);
  }

  // детальна сторінка:
  // якщо бекенд дає slug — використовуємо його,
  // якщо ні — падаємо назад на id.
  const id = it.id;
  const slugOrId = it.slug || id;
  const detailBase = window.MARKET_DETAIL_BASE || "/item/"; // дефолт — /item/<id>
  const detailHref = detailBase + encodeURIComponent(slugOrId);

  const rawPriceCents = normalizePriceCents(it);
  const isFree = it.is_free || !rawPriceCents;
  const priceLabel = isFree
    ? "Безкоштовно"
    : (rawPriceCents / 100).toFixed(2) + " zł";

  const rating =
    typeof it.rating === "number" ? it.rating.toFixed(1) : "0.0";
  const downloads = it.downloads || 0;

  // normalize cover (cover_url, cover, first gallery)
  const cover =
    it.cover_url ||
    it.cover ||
    (Array.isArray(it.gallery_urls) && it.gallery_urls[0]) ||
    null;

  return `
<article class="model-card" data-item-id="${id}">
  <div class="card-preview">
    <a href="${detailHref}" class="preview-link">
      ${
        cover
          ? `<img src="${cover}" loading="lazy" alt="${escapeHtml(it.title)}">`
          : `<img src="/static/img/placeholder_stl.jpg" loading="lazy" alt="${escapeHtml(it.title)}">`
      }
    </a>
    <button type="button"
            class="card-like ${it.is_fav ? "is-active" : ""}"
            data-favorite-toggle
            data-item-id="${id}"
            aria-label="Save to favorites">
      <svg viewBox="0 0 24 24" class="heart" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
      </svg>
    </button>
  </div>
  <div class="card-bottom">
    <div class="card-meta">
      <a href="${detailHref}" class="card-title">${escapeHtml(it.title)}</a>
      <div class="card-row">
        <span class="card-price">${priceLabel}</span>
        <span class="card-rating">⭐ ${rating}</span>
      </div>
      <div class="card-row">
        <span class="card-downloads">⬇ ${downloads}</span>
        ${
          it.category_name
            ? `<span class="card-category">${escapeHtml(it.category_name)}</span>`
            : ""
        }
      </div>
    </div>
  </div>
</article>`;
}

/* ==============================
 * 6) ПАГІНАЦІЯ
 * ============================== */

function renderPagination(page, pages) {
  page = page || 1;
  pages = pages || 1;
  if (pages <= 1) return "";

  let html = `<div class="market-pagination-inner">`;

  const addBtn = (p, label, active = false) => {
    if (active) {
      html += `<span class="pg-btn is-active">${label}</span>`;
    } else {
      html += `<button class="pg-btn" type="button" data-page="${p}">${label}</button>`;
    }
  };

  if (page > 1) addBtn(page - 1, "‹");

  const start = Math.max(1, page - 2);
  const end = Math.min(pages, page + 2);
  for (let p = start; p <= end; p++) {
    addBtn(p, p, p === page);
  }

  if (page < pages) addBtn(page + 1, "›");

  html += `</div>`;
  return html;
}

/* ==============================
 * 7) ОБРАНЕ
 * ============================== */

// bindFavButtons видалено — обробка перенесена в market_listeners.js
// через делегований обробник [data-favorite-toggle]

/* ==============================
 * 8) UI БІНДИНГИ
 * ============================== */

function bindUI() {
  // глобальний пошук (index.html) або локальний (my.html)
  const searchInput =
    document.getElementById("q") || document.getElementById("my-search");
  const searchBtn =
    document.getElementById("btn-search") ||
    document.getElementById("my-refresh");

  const triggerSearch = () => loadPage(1);
  const debouncedSearch = debounce(triggerSearch, 350);

  if (searchInput) {
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        triggerSearch();
      }
    });
    // лайв-пошук по мірі вводу
    searchInput.addEventListener("input", () => {
      if (searchInput.value.trim().length === 0) {
        // якщо очистили — одразу перезавантажуємо першу сторінку
        triggerSearch();
      } else {
        debouncedSearch();
      }
    });
  }

  if (searchBtn) {
    searchBtn.addEventListener("click", (e) => {
      e.preventDefault();
      triggerSearch();
    });
  }

  // селект сортування на my.html
  const mySort = document.getElementById("my-sort");
  if (mySort) {
    mySort.addEventListener("change", () => {
      state.sort = mySort.value || "new";
      loadPage(1);
    });
  }

  // селекти на головній (data-filter-sort / data-filter-show)
  const sortSelect = document.querySelector("[data-filter-sort]");
  if (sortSelect) {
    sortSelect.addEventListener("change", () => {
      state.sort = sortSelect.value || "new";
      loadPage(1);
    });
  }

  const showSelect = document.querySelector("[data-filter-show]");
  if (showSelect) {
    showSelect.addEventListener("change", () => {
      const v = showSelect.value || "all";
      if (v === "free") state.free = 1;
      else if (v === "paid") state.free = 0;
      else state.free = null;
      loadPage(1);
    });
  }

  // Proof Score filter dropdown
  const proofScoreSelect = document.querySelector("[data-filter-proof-score]");
  if (proofScoreSelect) {
    proofScoreSelect.addEventListener("change", () => {
      const v = parseInt(proofScoreSelect.value, 10) || 0;
      state.min_proof_score = v > 0 ? v : null;
      loadPage(1);
    });
  }

  // Auto Presets checkbox
  const autoPresetsCheckbox = document.querySelector("[data-filter-auto-presets]");
  if (autoPresetsCheckbox) {
    autoPresetsCheckbox.addEventListener("change", () => {
      state.auto_presets = autoPresetsCheckbox.checked ? 1 : null;
      loadPage(1);
    });
  }

  // Clear author filter button
  const clearAuthorBtn = document.getElementById('clear-author-filter');
  if (clearAuthorBtn) {
    clearAuthorBtn.addEventListener('click', () => {
      state.author = null;
      state.page = 1;
      loadPage(1);
    });
  }

  // чіпси "усі / free / paid" на my.html
  const myFreeGroup = document.getElementById("my-free-filter");
  if (myFreeGroup) {
    myFreeGroup.addEventListener("click", (e) => {
      const chip = e.target.closest(".chip");
      if (!chip) return;
      myFreeGroup
        .querySelectorAll(".chip")
        .forEach((c) => c.classList.toggle("active", c === chip));
      loadPage(1);
    });
  }

  // кнопки сортування/фільтрів у сабхедері: data-sort / data-show
  document.addEventListener("click", (e) => {
    const sortBtn = e.target.closest("[data-sort]");
    if (sortBtn) {
      state.sort = sortBtn.dataset.sort || "new";
      document
        .querySelectorAll("[data-sort]")
        .forEach((b) => b.classList.toggle("is-active", b === sortBtn));
      loadPage(1);
      return;
    }

    const showBtn = e.target.closest("[data-show]");
    if (showBtn) {
      const v = showBtn.dataset.show || "all";
      if (v === "free") state.free = 1;
      else if (v === "paid") state.free = 0;
      else state.free = null;

      document
        .querySelectorAll("[data-show]")
        .forEach((b) => b.classList.toggle("is-active", b === showBtn));
      loadPage(1);
    }
  });

  // швидкі фільтри-теги (market/index.html)
  const tagContainer = document.querySelector(".market-quick-filters");
  if (tagContainer) {
    tagContainer.addEventListener("click", (e) => {
      const chip = e.target.closest(".mqf-chip");
      if (!chip) return;

      tagContainer
        .querySelectorAll(".mqf-chip")
        .forEach((c) => c.classList.toggle("is-active", c === chip));

      // Check if this is Top Prints mode chip
      if (chip.dataset.mode === "top") {
        state.mode = "top";
        state.tag = null;  // Clear tag filter when in top mode
        // Show helper text
        const hint = document.querySelector('.top-mode-hint');
        if (hint) hint.style.display = 'inline';
      } else if (chip.dataset.filterTag) {
        // This is a tag filter chip, clear mode
        state.mode = null;
        // Hide helper text
        const hint = document.querySelector('.top-mode-hint');
        if (hint) hint.style.display = 'none';
        // tag will be read from buildStateFromDOM
      }

      loadPage(1);
    });
  }
}

/* ==============================
 * 9) ІНІЦІАЛІЗАЦІЯ
 * ============================== */

// Read URL params on page load
function initFromURL() {
  const params = new URLSearchParams(window.location.search);
  
  const authorId = params.get('author_id');
  if (authorId) {
    state.author_id = parseInt(authorId, 10) || null;
  }
  
  const author = params.get('author');
  if (author) {
    state.author = author;
  }
  
  // ❤️ Instagram-style saved filter from URL
  const saved = params.get('saved');
  if (saved === '1') {
    state.saved = 1;
    console.log('[market.js] 🔍 URL param saved=1 detected, state.saved set to 1');
  }
  
  const mode = params.get('mode');
  if (mode === 'top') {
    state.mode = 'top';
    // Activate Top Prints chip visually
    const topChip = document.querySelector('[data-mode="top"]');
    if (topChip) {
      document.querySelectorAll('.mqf-chip').forEach(c => c.classList.remove('is-active'));
      topChip.classList.add('is-active');
    }
    // Show helper text
    const hint = document.querySelector('.top-mode-hint');
    if (hint) hint.style.display = 'inline';
  }
  
  const minProofScore = params.get('min_proof_score');
  if (minProofScore) {
    const val = parseInt(minProofScore, 10);
    state.min_proof_score = val > 0 ? val : null;
    // Set dropdown value
    const proofScoreSelect = document.querySelector("[data-filter-proof-score]");
    if (proofScoreSelect) {
      proofScoreSelect.value = minProofScore;
    }
  }
  
  const autoPresets = params.get('auto_presets');
  if (autoPresets === '1') {
    state.auto_presets = 1;
    // Set checkbox checked
    const autoPresetsCheckbox = document.querySelector("[data-filter-auto-presets]");
    if (autoPresetsCheckbox) {
      autoPresetsCheckbox.checked = true;
    }
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    initFromURL();
    bindUI();
    loadPage(1);
  });
} else {
  initFromURL();
  bindUI();
  loadPage(1);
}
