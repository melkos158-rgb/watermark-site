// static/market/js/compare.js
// Логіка порівняння STL-моделей на Proofly

(function () {
  const STORAGE_KEY = "proofly_compare_items";

  /** ===================== УТИЛІТИ ===================== */

  function loadItems() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return [];
      const arr = JSON.parse(raw);
      if (!Array.isArray(arr)) return [];
      return arr;
    } catch (e) {
      console.warn("compare: cannot parse localStorage", e);
      return [];
    }
  }

  function saveItems(items) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
    } catch (e) {
      console.warn("compare: cannot save to localStorage", e);
    }
  }

  function hasItem(items, id) {
    return items.some((x) => String(x.id) === String(id));
  }

  function removeItem(items, id) {
    return items.filter((x) => String(x.id) !== String(id));
  }

  function upToMax(items, max) {
    if (!max || items.length <= max) return items;
    return items.slice(0, max);
  }

  function qs(selector) {
    return document.querySelector(selector);
  }

  function qsa(selector, root) {
    return Array.from((root || document).querySelectorAll(selector));
  }

  /** ===================== ПАНЕЛЬ ПОРІВНЯННЯ ===================== */

  function initComparePanel() {
    const panel = qs("#compare-panel");
    if (!panel) return; // на цій сторінці нема панелі — ок

    const maxItems = parseInt(panel.dataset.maxItems || "4", 10);
    const listEl = qs("#compare-list");
    const countEl = qs("#compare-count");
    const btnClear = qs("#compare-clear");
    const btnGo = qs("#compare-go");
    const tpl = qs("#compare-item-template");
    const checkboxSync = qs("#compare-sync-filters");

    let items = loadItems();
    items = upToMax(items, maxItems);
    saveItems(items);

    function render() {
      if (!listEl) return;

      listEl.innerHTML = "";
      if (!items.length) {
        const div = document.createElement("div");
        div.className = "compare-empty muted";
        div.textContent =
          "Додай до 4 моделей, щоб порівняти час друку, об’єм, ціну, полігони та інші параметри.";
        listEl.appendChild(div);
      } else {
        items.forEach((item) => {
          const node = tpl.content
            ? tpl.content.cloneNode(true)
            : document.importNode(tpl, true);

          const itemRoot = node.querySelector
            ? node.querySelector(".compare-item")
            : null;

          if (itemRoot) {
            itemRoot.dataset.id = item.id;
          }

          const thumb = node.querySelector(".compare-thumb");
          const title = node.querySelector(".compare-title");
          const tags = node.querySelector(".compare-tags");
          const btnRemove = node.querySelector(".compare-remove");

          if (thumb) {
            thumb.src = item.thumb || item.preview || "";
            thumb.alt = item.title || "";
          }
          if (title) {
            title.textContent = item.title || "Без назви";
          }
          if (tags) {
            tags.textContent = item.tags || "";
          }
          if (btnRemove) {
            btnRemove.addEventListener("click", () => {
              items = removeItem(items, item.id);
              saveItems(items);
              render();
              syncButtonsState();
            });
          }

          listEl.appendChild(node);
        });
      }

      if (countEl) {
        countEl.textContent = `${items.length} / ${maxItems}`;
      }
      if (btnGo) {
        btnGo.disabled = items.length < 2;
      }
      if (panel) {
        panel.classList.toggle("hidden", items.length === 0);
      }
    }

    function syncButtonsState() {
      // Кнопки на карточках моделей
      qsa("[data-action='compare-toggle']").forEach((btn) => {
        const id = btn.getAttribute("data-id");
        if (!id) return;
        if (hasItem(items, id)) {
          btn.classList.add("in-compare");
          btn.textContent = btn.getAttribute("data-label-remove") || "В порівнянні";
        } else {
          btn.classList.remove("in-compare");
          btn.textContent = btn.getAttribute("data-label-add") || "Порівняти";
        }
      });
    }

    // Обробка кліків по кнопках "Додати до порівняння"
    document.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-action='compare-toggle']");
      if (!btn) return;

      const id = btn.getAttribute("data-id");
      if (!id) return;

      const title = btn.getAttribute("data-title") || "";
      const thumb = btn.getAttribute("data-thumb") || "";
      const tags = btn.getAttribute("data-tags") || "";

      if (hasItem(items, id)) {
        // Прибрати
        items = removeItem(items, id);
      } else {
        // Додати
        if (items.length >= maxItems) {
          // можна зробити тост / алерт
          alert(`Максимум ${maxItems} моделей для порівняння.`);
          return;
        }
        items.push({
          id: id,
          title: title,
          thumb: thumb,
          tags: tags,
        });
      }

      saveItems(items);
      render();
      syncButtonsState();
    });

    // Очистити
    if (btnClear) {
      btnClear.addEventListener("click", () => {
        items = [];
        saveItems(items);
        render();
        syncButtonsState();
      });
    }

    // Перейти на сторінку порівняння
    if (btnGo) {
      btnGo.addEventListener("click", () => {
        if (items.length < 2) return;
        const ids = items.map((x) => x.id).join(",");
        const sync = checkboxSync && checkboxSync.checked ? "1" : "0";
        const base = panel.getAttribute("data-compare-url") || "/market/compare";
        const url = `${base}?items=${encodeURIComponent(ids)}&sync=${sync}`;
        window.location.href = url;
      });
    }

    // Початковий рендер
    render();
    syncButtonsState();
  }

  /** ===================== СТОРІНКА /market/compare ===================== */

  function initComparePage() {
    const wrapper = qs("#compare-table-wrapper");
    if (!wrapper) return; // ми не на сторінці compare.html

    const endpoint = wrapper.dataset.endpoint || "/api/market/compare";
    const table = qs("#compare-table");
    const btnRefresh = qs("#compare-refresh");

    // Прибрати модель зі сторінки порівняння
    document.addEventListener("click", (e) => {
      const btn = e.target.closest(".cmp-remove");
      if (!btn) return;

      const removeId = btn.getAttribute("data-remove-id");
      if (!removeId) return;

      // Оновлюємо localStorage
      let items = loadItems();
      items = removeItem(items, removeId);
      saveItems(items);

      // Переформувати URL із рештою id (із locals або з шапки таблиці)
      const remainingIds = qsa("th[data-item-id]", table).map((th) =>
        th.getAttribute("data-item-id")
      );
      const filtered = remainingIds.filter((id) => String(id) !== String(removeId));

      if (!filtered.length) {
        // Якщо нічого не лишилось — назад до каталогу
        window.location.href = "/market";
      } else {
        const url = `/market/compare?items=${encodeURIComponent(filtered.join(","))}`;
        window.location.href = url;
      }
    });

    async function fetchMetrics() {
      const idCells = qsa("[data-id]", table);
      if (!idCells.length) return;

      const idsSet = new Set();
      idCells.forEach((c) => {
        const id = c.getAttribute("data-id");
        if (id) idsSet.add(id);
      });
      const ids = Array.from(idsSet);

      try {
        const res = await fetch(endpoint, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ items: ids }),
        });

        if (!res.ok) throw new Error("Bad response: " + res.status);
        const data = await res.json();
        // Очікуваний формат:
        // { "1": { print_time_human: "...", volume_cm3: ..., weight_g: ..., polygons: ..., printer_match_label: "..." }, ... }

        ids.forEach((id) => {
          const m = data[id];
          if (!m) return;

          // Час друку
          qsa(`[data-metric="print_time"][data-id="${id}"]`, table).forEach((cell) => {
            cell.textContent = m.print_time_human || "—";
          });

          // Об'єм / вага
          qsa(`[data-metric="volume"][data-id="${id}"]`, table).forEach((cell) => {
            if (m.volume_cm3 != null) {
              let txt = `${m.volume_cm3.toFixed ? m.volume_cm3.toFixed(1) : m.volume_cm3} см³`;
              if (m.weight_g != null) {
                txt += ` (~${Math.round(m.weight_g)} г)`;
              }
              cell.textContent = txt;
            } else {
              cell.textContent = "—";
            }
          });

          // Габарити
          qsa(`[data-metric="bbox"][data-id="${id}"]`, table).forEach((cell) => {
            if (
              m.size_x != null &&
              m.size_y != null &&
              m.size_z != null
            ) {
              const txt = `${m.size_x.toFixed ? m.size_x.toFixed(1) : m.size_x} × ` +
                          `${m.size_y.toFixed ? m.size_y.toFixed(1) : m.size_y} × ` +
                          `${m.size_z.toFixed ? m.size_z.toFixed(1) : m.size_z} мм`;
              cell.textContent = txt;
            } else {
              cell.textContent = "—";
            }
          });

          // Полігони
          qsa(`[data-metric="polygons"][data-id="${id}"]`, table).forEach((cell) => {
            if (m.polygons != null) {
              cell.textContent = String(m.polygons);
            } else {
              cell.textContent = "—";
            }
          });

          // Сумісність з принтером
          qsa(`[data-metric="printer_match"][data-id="${id}"]`, table).forEach((cell) => {
            if (m.printer_match_label) {
              cell.textContent = m.printer_match_label;
            } else if (m.printer_match_score != null) {
              cell.textContent = `Сумісність: ${Math.round(m.printer_match_score * 100)}%`;
            } else {
              cell.textContent = "—";
            }
          });
        });
      } catch (err) {
        console.error("compare: cannot fetch metrics", err);
      }
    }

    if (btnRefresh) {
      btnRefresh.addEventListener("click", fetchMetrics);
    }

    // Авто-підтягування при загрузці
    fetchMetrics();
  }

  /** ===================== INIT ===================== */

  function init() {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", () => {
        initComparePanel();
        initComparePage();
      });
    } else {
      initComparePanel();
      initComparePage();
    }
  }

  init();
})();
