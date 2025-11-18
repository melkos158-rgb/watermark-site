// static/market/js/market.js
// Головна логіка сторінки STL Market:
// - тягнемо список моделей з /api/market/items або /api/market/my
// - реагуємо на пошук, кнопки фільтрів, пагінацію
// - рендеримо грід карток

import {
  fetchItems,
  fetchMyItems,
  toggleFavorite,
} from "./api.js";

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
  sort: "new",      // new | popular | top | price_asc | price_desc | free | paid
  category: null,   // slug категорії
  free: null,       // null / 1 / 0
};

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
      const v = active.dataset.free || "all";
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
}

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

  setNotice("", "");
  grid.dataset.loading = "1";
  grid.innerHTML = `<div class="market-grid-loading">Завантаження моделей…</div>`;
  if (pag) pag.innerHTML = "";
  if (emptyBlock) emptyBlock.style.display = "none";

  const params = {
    q: state.q || undefined,
    page: state.page,
    per_page: state.per_page,
    sort: state.sort,
    category: state.category || undefined,
    free: state.free === null ? undefined : state.free ? 1 : 0,
  };

  let resp;
  try {
    if (PAGE_TYPE === "my") {
      resp = await fetchMyItems(params);
    } else {
      resp = await fetchItems(params);
    }
  } catch (err) {
    console.error(err);
    grid.dataset.loading = "0";

    setNotice("Помилка завантаження маркету 😢", "error");
    grid.innerHTML =
      `<div class="market-grid-error">` +
      `Помилка завантаження маркету 😢<br>` +
      `<button type="button" class="btn" id="market-retry">Спробувати ще раз</button>` +
      `</div>`;
    const retry = document.getElementById("market-retry");
    if (retry) {
      retry.addEventListener("click", () => loadPage(state.page));
    }
    return;
  }

  grid.dataset.loading = "0";

  const items = (resp && resp.items) || [];
  const total = resp && typeof resp.total === "number" ? resp.total : items.length;

  if (!items.length) {
    grid.innerHTML =
      `<div class="market-grid-empty">` +
      `Поки що немає моделей за цим запитом.` +
      `</div>`;
    setNotice("Поки що немає моделей за цим запитом.", "");
    if (PAGE_TYPE === "my" && emptyBlock) {
      emptyBlock.style.display = "";
    }
  } else {
    grid.innerHTML = items.map(renderItemCard).join("");
    setNotice("", "");
    if (PAGE_TYPE === "my" && emptyBlock) {
      emptyBlock.style.display = "none";
    }
  }

  // текст лічильника на my.html
  if (PAGE_TYPE === "my" && counterText) {
    const t = total === 1 ? "Знайдено 1 оголошення" : `Знайдено ${total} оголошень`;
    counterText.textContent = t;
  }

  bindFavButtons(grid);

  if (pag && resp) {
    pag.innerHTML = renderPagination(resp.page, resp.pages);
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

function renderItemCard(it) {
  // 👇 Нормалізація шляху до детальної сторінки:
  // якщо бекенд дає slug — використовуємо його,
  // якщо ні — падаємо назад на id.
  const id = it.id;
  const slugOrId = it.slug || id;
  const detailBase = window.MARKET_DETAIL_BASE || "/item/"; // дефолт — /item/<id>
  const detailHref = detailBase + encodeURIComponent(slugOrId);

  // 👇 Нормалізація ціни:
  //  • якщо є price_cents — використовуємо
  //  • якщо є price (у PLN) — конвертуємо в центи
  let rawPriceCents;
  if (typeof it.price_cents === "number") {
    rawPriceCents = it.price_cents;
  } else if (typeof it.price === "number") {
    rawPriceCents = Math.round(it.price * 100);
  } else {
    rawPriceCents = 0;
  }

  const isFree = it.is_free || !rawPriceCents;

  const priceLabel = isFree
    ? "Безкоштовно"
    : (rawPriceCents / 100).toFixed(2) + " zł";

  const rating =
    typeof it.rating === "number" ? it.rating.toFixed(1) : "0.0";

  const downloads = it.downloads || 0;

  return `
<a class="market-item-card" href="${detailHref}" data-item-id="${id}">
  <div class="thumb">
    ${
      it.cover_url
        ? `<img src="${it.cover_url}" loading="lazy" alt="${escapeHtml(it.title)}">`
        : `<div class="thumb-placeholder">STL</div>`
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

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

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

function bindFavButtons(root) {
  root.querySelectorAll("[data-fav]").forEach((btn) => {
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

function bindUI() {
  // глобальний пошук (index.html) або локальний (my.html)
  const searchInput =
    document.getElementById("q") || document.getElementById("my-search");
  const searchBtn =
    document.getElementById("btn-search") || document.getElementById("my-refresh");

  if (searchInput) {
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        loadPage(1);
      }
    });
  }

  if (searchBtn) {
    searchBtn.addEventListener("click", (e) => {
      e.preventDefault();
      loadPage(1);
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
}

// ініціалізація
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    bindUI();
    loadPage(1);
  });
} else {
  bindUI();
  loadPage(1);
}
