// static/market/js/market_listeners.js
// =====================================================
// Глобальні слухачі подій для сторінок STL Market
// Реагують на зміни категорії, пошуку, сортування тощо
// =====================================================

import { API, assetUrl } from "./api.js";

document.addEventListener("DOMContentLoaded", () => {
  const grid = document.querySelector("#grid");
  if (!grid) return;

  const q = document.querySelector("#q");
  const sort = document.querySelector("#sort");
  const catSel = document.querySelector("#cat");
  const sentinel = document.querySelector("#sentinel");

  let page = 1;
  let hasMore = true;
  let loading = false;
  let currentCat = catSel?.value || "";
  let currentSort = sort?.value || "new";
  let currentQ = q?.value || "";

  // Основна функція: завантажує одну сторінку
  async function loadPage(reset = false) {
    if (loading || (!hasMore && !reset)) return;
    if (reset) {
      page = 1;
      grid.innerHTML = "";
      hasMore = true;
    }
    loading = true;

    const loadingEl = document.createElement("div");
    loadingEl.className = "empty";
    loadingEl.textContent = "Завантаження…";
    grid.appendChild(loadingEl);

    try {
      const data = await API.get("/api/items", {
        page,
        per_page: 24,
        q: currentQ,
        cat: currentCat,
        sort: currentSort,
      });

      const items = Array.isArray(data.items) ? data.items : [];
      const pages = Number(data.pages || 1);
      if (loadingEl.parentNode === grid) grid.removeChild(loadingEl);

      appendItems(items);
      page += 1;
      hasMore = page <= pages && items.length > 0;

      if (!grid.children.length) {
        grid.innerHTML = `<div class="empty">Нічого не знайдено 😿</div>`;
      }
    } catch (err) {
      console.error(err);
      grid.innerHTML = `<div class="empty">Помилка мережі.</div>`;
    } finally {
      loading = false;
    }
  }

  // Рендер карток
  function appendItems(items) {
    for (const it of items) {
      const el = document.createElement("div");
      el.className = "item";
      const cover = assetUrl(it.cover || it.cover_url);

      el.innerHTML = `
        <div class="thumb-wrap" data-open="${it.id}">
          <img src="${cover}" alt="${escapeHtml(it.title)}" class="thumb" loading="lazy">
        </div>
        <div class="meta">
          <div class="title">${escapeHtml(it.title || "Без назви")}</div>
          <div class="muted">★ ${it.rating ?? "—"} • ⬇️ ${it.downloads ?? 0}</div>
          <div class="price">${(+it.price || 0) === 0 ? "Безкоштовно" : it.price + " PLN"}</div>
        </div>`;
      grid.appendChild(el);
    }
  }

  // Обробка кліку по картці
  grid.addEventListener("click", (e) => {
    const openId = e.target.closest("[data-open]")?.dataset?.open;
    if (openId) window.location.href = `/item/${openId}`;
  });

  // Реакції на зміни UI
  if (q) q.addEventListener("keydown", (e) => e.key === "Enter" && updateSearch());
  if (sort) sort.addEventListener("change", updateSearch);
  if (catSel) catSel.addEventListener("change", updateSearch);

  document.addEventListener("marketCategoryChange", (ev) => {
    currentCat = ev.detail || "";
    updateSearch();
  });

  function updateSearch() {
    currentQ = q?.value || "";
    currentSort = sort?.value || "new";
    currentCat = catSel?.value || currentCat;
    loadPage(true);
  }

  // Infinite scroll
  if (sentinel) {
    const io = new IntersectionObserver((entries) => {
      for (const en of entries) {
        if (en.isIntersecting) loadPage();
      }
    }, { rootMargin: "600px 0px" });
    io.observe(sentinel);
  }

  // Початкове завантаження
  loadPage(true);
});

// Допоміжна функція
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (m) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]
  ));
}

// =====================================================
// CSS (мінімальний стиль для порожнього стану)
// =====================================================
const css = `
.empty{text-align:center;color:var(--muted);padding:20px;}
.thumb-wrap{cursor:pointer;}
`;
const style = document.createElement("style");
style.textContent = css;
document.head.appendChild(style);
