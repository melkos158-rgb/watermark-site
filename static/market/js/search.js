// static/market/js/search.js
// =====================================================
// Пошук + автопідказки для сторінок Market
// Працює з елементами: #q, #btn-search, #search-suggest (опц.)
// Використовує API.suggest()
// Якщо на сторінці немає SPA-обробника — робимо навігацію через URL
// =====================================================
import { suggest } from "./api.js";

document.addEventListener("DOMContentLoaded", () => {
  const qInput   = document.getElementById("q");
  const btn      = document.getElementById("btn-search") || document.getElementById("btnSearch");
  const suggestB = ensureSuggestBox();

  if (!qInput) return;

  // Ввід + дебаунс для підказок
  let tmr;
  qInput.addEventListener("input", () => {
    clearTimeout(tmr);
    const val = qInput.value.trim();
    if (!val) { hideSuggest(); return; }
    tmr = setTimeout(async () => {
      try {
        const arr = await suggest(val);
        if (!Array.isArray(arr) || !arr.length) { hideSuggest(); return; }
        fillSuggest(arr, val);
      } catch {
        hideSuggest();
      }
    }, 250);
  });

  // Enter -> пошук
  qInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      submitSearch();
    }
    // Стрілки по списку підказок
    if ((e.key === "ArrowDown" || e.key === "ArrowUp") && suggestB.style.display !== "none") {
      e.preventDefault();
      focusSuggestItem(e.key === "ArrowDown" ? 1 : -1);
    }
  });

  if (btn) btn.addEventListener("click", submitSearch);

  // Клік по підказці
  suggestB.addEventListener("click", (e) => {
    const it = e.target.closest(".suggest-item");
    if (!it) return;
    qInput.value = it.dataset.value || it.textContent.trim();
    hideSuggest();
    submitSearch();
  });

  // Закриття підказок при кліку поза блоком
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".search") && e.target !== qInput) hideSuggest();
  });

  // Реакція на категорії (з _filters.html або index.html explore-tags)
  document.addEventListener("marketCategoryChange", (ev) => {
    const cat = (ev.detail || "").trim();
    const params = collectParams({ cat });
    navigateWithParams("/market", params);
  });

  // ===== helpers =====
  function submitSearch() {
    const params = collectParams();
    // Якщо на сторінці є кастомна логіка — шлемо подію
    const dispatched = document.dispatchEvent(new CustomEvent("marketSearch", { detail: params }));
    // Все одно оновимо URL (щоб працювало скрізь)
    navigateWithParams("/market", params);
  }

  function collectParams(extra = {}) {
    const freeSel = document.getElementById("filterFree");
    const sortSel = document.getElementById("sort");
    const catSel  = document.getElementById("cat");

    const params = {
      q: qInput.value.trim() || "",
      free: freeSel ? freeSel.value : undefined,
      sort: sortSel ? sortSel.value : undefined,
      cat:  catSel ? catSel.value : undefined,
      ...extra,
    };
    // Прибираємо порожні
    Object.keys(params).forEach(k => (params[k] == null || params[k] === "") && delete params[k]);
    return params;
  }

  function navigateWithParams(path, params) {
    const u = new URL(path, location.origin);
    Object.entries(params).forEach(([k, v]) => u.searchParams.set(k, v));
    // Якщо вже на цій сторінці — замінимо історію (без перезавантаження, якщо є SPA handler)
    if (location.pathname === path) {
      history.pushState({}, "", u);
      // Дамо шанс SPA-логіці підхопити зміни
      document.dispatchEvent(new Event("marketParamsChanged"));
      // Якщо немає SPA-обробника — перезавантажимо (щоб точно)
      setTimeout(() => {
        // Перевірка: чи хтось слухає наш івент і виконав роботу (встановив data-market-loaded)
        if (!document.body.dataset.marketLoaded) location.href = u.toString();
      }, 50);
    } else {
      location.href = u.toString();
    }
  }

  function ensureSuggestBox() {
    let box = document.getElementById("search-suggest");
    if (!box) {
      // якщо не існує — створимо поруч з інпутом
      box = document.createElement("div");
      box.id = "search-suggest";
      box.className = "suggest-box";
      box.style.display = "none";
      const wrap = qInput.parentElement || document.body;
      wrap.appendChild(box);
      injectSuggestCss();
    }
    return box;
  }

  function fillSuggest(items, query) {
    suggestB.innerHTML = items
      .slice(0, 8)
      .map((t, i) => {
        const safe = escapeHtml(String(t));
        return `<div class="suggest-item" tabindex="0" data-idx="${i}" data-value="${safe}">${highlight(safe, query)}</div>`;
      })
      .join("");
    suggestB.style.display = "block";
    // фокус на перший елемент
    const first = suggestB.querySelector(".suggest-item");
    if (first) first.focus();
  }

  function hideSuggest() {
    suggestB.style.display = "none";
    suggestB.innerHTML = "";
  }

  function focusSuggestItem(dir) {
    const items = Array.from(suggestB.querySelectorAll(".suggest-item"));
    if (!items.length) return;
    let idx = items.findIndex((el) => el === document.activeElement);
    idx = (idx + dir + items.length) % items.length;
    items[idx].focus();
  }

  function highlight(text, q) {
    if (!q) return text;
    try {
      const re = new RegExp("(" + escapeRegExp(q) + ")", "ig");
      return text.replace(re, "<mark>$1</mark>");
    } catch {
      return text;
    }
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (m) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[m]));
  }
  function escapeRegExp(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }
});

// Інжект стилів для підказок (якщо їх ще нема)
function injectSuggestCss() {
  if (document.getElementById("search-suggest-css")) return;
  const css = `
  .suggest-box{
    position:absolute; top:110%; left:0; right:0;
    background:var(--card); border:1px solid var(--line);
    border-radius:8px; box-shadow:0 4px 12px rgba(0,0,0,.3); overflow:hidden; z-index:20;
  }
  .suggest-item{ padding:6px 10px; color:var(--text); cursor:pointer; outline:none; }
  .suggest-item:hover, .suggest-item:focus{ background:var(--accent); color:#fff; }
  mark{ background:rgba(59,130,246,.35); color:inherit; border-radius:2px; padding:0 1px; }
  `;
  const style = document.createElement("style");
  style.id = "search-suggest-css";
  style.textContent = css;
  document.head.appendChild(style);
}
