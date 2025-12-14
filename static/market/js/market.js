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
  sort: "new",      // new | popular | top | price_asc | price_desc
  category: null,   // slug категорії
  free: null,       // null / 1 / 0
  tag: null,        // швидкий тег із .mqf-chip (dragon / stand / toy / cosplay / other)
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
    category: state.category || undefined,
    free: state.free === null ? undefined : state.free ? 1 : 0,
    // tag спеціально не відправляємо — наразі фільтруємо на фронті
  };

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

  bindFavButtons(grid);

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
}

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
<a class="market-item-card" href="${detailHref}" data-item-id="${id}">
  <div class="thumb">
    ${
      cover
        ? `<img src="${cover}" loading="lazy" alt="${escapeHtml(it.title)}">`
        : `<img src="/static/img/placeholder_stl.jpg" loading="lazy" alt="${escapeHtml(it.title)}">`
    }
    <button type="button"
            class="fav ${it.is_fav ? "is-active" : ""}"
            data-fav="${id}">
      ${it.is_fav ? "★" : "☆"}
    </button>
  </div>
  <div class="meta">
    <div class="title">${escapeHtml(it.title)}</div>
    <div class="row">
      <span class="price">${priceLabel}</span>
      <span class="rating">⭐ ${rating}</span>
    </div>
    <div class="row">
      <span class="downloads">⬇ ${downloads}</span>
      ${
        it.category_name
          ? `<span class="category">${escapeHtml(it.category_name)}</span>`
          : ""
      }
    </div>
  </div>
</a>`;
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

function bindFavButtons(root) {
  root.querySelectorAll("[data-fav]").forEach((btn) => {
    // щоб не дублювати прослуховувачі при перерендері
    if (btn.dataset.favBound === "1") return;
    btn.dataset.favBound = "1";

    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const id = parseInt(btn.dataset.fav || "0", 10);
      if (!id) return;
      btn.disabled = true;
      try {
        const res = await toggleFavorite(id);
        btn.classList.toggle("is-active", !!res.fav);
        btn.textContent = res.fav ? "★" : "☆";
      } catch (err) {
        console.warn(err);
      } finally {
        btn.disabled = false;
      }
    });
  });
}

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

      loadPage(1);
    });
  }
}

/* ==============================
 * 9) ІНІЦІАЛІЗАЦІЯ
 * ============================== */

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    bindUI();
    loadPage(1);
  });
} else {
  bindUI();
  loadPage(1);
}
