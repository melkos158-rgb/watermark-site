// static/market/js/filters.js
// UX для фільтрів: збереження стану, автопідказки для пошуку

import { suggest } from "./api.js";

const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

const LS_KEY = "market:state";

/* =========================
 * 1) LOCALSTORAGE
 * ========================= */

function saveState() {
  try {
    const qInput   = $("#q");
    const catSel   = $("#cat");
    const sortSel  = $("#sort") || $("[data-filter-sort]");
    const showSel  = $("[data-filter-show]");

    const activeCatBtn = $(
      "[data-filter-category].is-active, [data-filter-category].active"
    );
    const activeTagChip = $(
      ".mqf-chip.is-active, [data-filter-tag].is-active"
    );
    const activeShowBtn = $("[data-show].is-active");

    const st = {
      q: qInput?.value || "",
      cat:
        catSel?.value ||
        activeCatBtn?.dataset.slug ||
        activeCatBtn?.dataset.category ||
        "",
      sort: sortSel?.value || "new",
      show:
        showSel?.value ||
        activeShowBtn?.dataset.show ||
        "",
      tag:
        activeTagChip?.dataset.filterTag ||
        activeTagChip?.dataset.tag ||
        "",
    };

    localStorage.setItem(LS_KEY, JSON.stringify(st));
  } catch {
    // ignore
  }
}

function restoreState() {
  let st;
  try {
    st = JSON.parse(localStorage.getItem(LS_KEY) || "{}");
  } catch {
    st = {};
  }
  if (!st || typeof st !== "object") st = {};

  const qInput   = $("#q");
  const catSel   = $("#cat");
  const sortSel  = $("#sort") || $("[data-filter-sort]");
  const showSel  = $("[data-filter-show]");

  // пошук
  if (qInput && !qInput.value && st.q) {
    qInput.value = st.q;
  }

  // категорія: select або кнопки
  if (catSel && !catSel.value && st.cat) {
    catSel.value = st.cat;
  } else if (!catSel && st.cat) {
    const btn = document.querySelector(
      `[data-filter-category][data-slug="${st.cat}"],` +
      `[data-filter-category][data-category="${st.cat}"]`
    );
    if (btn && !btn.classList.contains("is-active")) {
      $$("[data-filter-category]").forEach((b) =>
        b.classList.remove("is-active", "active")
      );
      btn.classList.add("is-active");
    }
  }

  // sort
  if (sortSel && !sortSel.value && st.sort) {
    sortSel.value = st.sort;
  }

  // free/paid (select або кнопки з data-show)
  if (showSel && !showSel.value && st.show) {
    showSel.value = st.show;
  } else if (!showSel && st.show) {
    const btn = document.querySelector(
      `[data-show="${st.show}"]`
    );
    if (btn) {
      $$("[data-show]").forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
    }
  }

  // швидкий тег
  if (st.tag) {
    const chip = document.querySelector(
      `.mqf-chip[data-filter-tag="${st.tag}"],` +
      `[data-filter-tag="${st.tag}"]`
    );
    if (chip) {
      $$(".mqf-chip, [data-filter-tag]").forEach((c) =>
        c.classList.remove("is-active")
      );
      chip.classList.add("is-active");
    }
  }
}

/* =========================
 * 2) SUGGEST DROPDOWN
 * ========================= */

let suggBox = null;
let suggItems = [];
let suggActiveIndex = -1;

function ensureSuggestBox(input) {
  if (suggBox) return suggBox;
  const wrap = document.createElement("div");
  wrap.className = "market-suggest-box";
  wrap.style.position = "absolute";
  wrap.style.zIndex = "40";
  wrap.style.minWidth = input.offsetWidth + "px";

  const pos = input.getBoundingClientRect();
  const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
  const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;

  wrap.style.left = pos.left + scrollLeft + "px";
  wrap.style.top = pos.bottom + scrollTop + "px";

  document.body.appendChild(wrap);
  suggBox = wrap;
  return wrap;
}

function positionSuggestBox(input) {
  if (!suggBox) return;
  const pos = input.getBoundingClientRect();
  const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
  const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
  suggBox.style.left = pos.left + scrollLeft + "px";
  suggBox.style.top = pos.bottom + scrollTop + "px";
  suggBox.style.minWidth = pos.width + "px";
}

function hideSuggest() {
  if (!suggBox) return;
  suggBox.style.display = "none";
  suggBox.innerHTML = "";
  suggItems = [];
  suggActiveIndex = -1;
}

function showSuggest(input, list) {
  if (!list || !list.length) {
    hideSuggest();
    return;
  }
  const box = ensureSuggestBox(input);
  positionSuggestBox(input);

  suggItems = list.slice(0, 8);
  suggActiveIndex = -1;

  box.innerHTML =
    '<ul class="market-suggest-list">' +
    suggItems
      .map(
        (it, i) =>
          `<li class="market-suggest-item" data-idx="${i}">` +
          `<span class="ttl">${escapeHtml(it.title || "")}</span>` +
          (it.slug ? `<span class="slug">${escapeHtml(it.slug)}</span>` : "") +
          `</li>`
      )
      .join("") +
    "</ul>";

  box.style.display = "block";

  box.querySelectorAll(".market-suggest-item").forEach((li) => {
    li.addEventListener("mousedown", (e) => {
      // mousedown, щоб не втратити фокус від blur
      e.preventDefault();
      const idx = Number(li.dataset.idx || 0);
      pickSuggestItem(input, idx);
    });
  });
}

function setActiveSuggest(idx) {
  if (!suggBox) return;
  const items = suggBox.querySelectorAll(".market-suggest-item");
  items.forEach((li) => li.classList.remove("is-active"));
  if (idx >= 0 && idx < items.length) {
    items[idx].classList.add("is-active");
    suggActiveIndex = idx;
  } else {
    suggActiveIndex = -1;
  }
}

function pickSuggestItem(input, idx) {
  if (!suggItems[idx]) return;
  const item = suggItems[idx];
  input.value = item.title || "";
  hideSuggest();

  // тригеримо пошук (market.js слухає input/keydown/кнопку)
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

/* =========================
 * 3) INIT
 * ========================= */

document.addEventListener("DOMContentLoaded", () => {
  restoreState();

  // збереження стану при змінах
  ["#q", "#cat", "#sort"].forEach((sel) => {
    $(sel)?.addEventListener("change", saveState);
  });

  // кнопки/селекти з data-атрибутами
  $("[data-filter-sort]")?.addEventListener("change", saveState);
  $("[data-filter-show]")?.addEventListener("change", saveState);

  const freeGroup = $("#my-free-filter");
  if (freeGroup) {
    freeGroup.addEventListener("click", (e) => {
      const chip = e.target.closest(".chip");
      if (!chip) return;
      saveState();
    });
  }

  const tagContainer = $(".market-quick-filters");
  if (tagContainer) {
    tagContainer.addEventListener("click", (e) => {
      const chip = e.target.closest(".mqf-chip,[data-filter-tag]");
      if (!chip) return;
      saveState();
    });
  }

  window.addEventListener("beforeunload", saveState);

  // автопідказки для #q
  const qInput = $("#q");
  if (!qInput) return;

  const doSuggest = debounce(async (e) => {
    const q = (e.target.value || "").trim();
    if (q.length < 2) {
      hideSuggest();
      return;
    }
    try {
      const items = await suggest(q);
      showSuggest(qInput, Array.isArray(items) ? items : []);
    } catch {
      hideSuggest();
    }
  }, 250);

  qInput.addEventListener("input", (e) => {
    doSuggest(e);
  });

  qInput.addEventListener("keydown", (e) => {
    if (!suggBox || suggBox.style.display === "none") return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      const next =
        suggActiveIndex + 1 >= suggItems.length ? 0 : suggActiveIndex + 1;
      setActiveSuggest(next);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      const prev =
        suggActiveIndex - 1 < 0
          ? suggItems.length - 1
          : suggActiveIndex - 1;
      setActiveSuggest(prev);
    } else if (e.key === "Enter") {
      if (suggActiveIndex >= 0) {
        e.preventDefault();
        pickSuggestItem(qInput, suggActiveIndex);
      } else {
        hideSuggest();
      }
    } else if (e.key === "Escape") {
      hideSuggest();
    }
  });

  qInput.addEventListener("blur", () => {
    // невелика затримка, щоб mousedown по елементу встиг спрацювати
    setTimeout(() => hideSuggest(), 150);
  });

  window.addEventListener("scroll", () => {
    if (qInput && suggBox && suggBox.style.display === "block") {
      positionSuggestBox(qInput);
    }
  });
});

/* =========================
 * 4) HELPERS
 * ========================= */

function debounce(fn, ms = 300) {
  let t;
  return (...a) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...a), ms);
  };
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
