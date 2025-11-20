// static/market/js/my_page_focus.js
// Логіка верхньої каруселі "prev / main / next" для сторінки Мої оголошення.
//
// Працює так:
//  - чекає поки market.js підгрузить оголошення в #my-grid
//  - читає картки .market-item-card з data-item-id
//  - по кліку на картку робить її "обраною":
//      • підсвічує картку
//      • показує її в центрі
//      • у лівому / правому превʼю показує сусідів
//  - кнопки ◀ ▶ листають між моделями
//  - кнопка "Редагувати" запамʼятовує id поточної моделі і
//    або тригерить кнопки редагування всередині картки, або
//    кидає кастомний івент "my-focus-edit" (щоб можна було підписатися з іншого JS)

(function () {
  "use strict";

  // Активуємо ТІЛЬКИ на сторінці "my"
  if (document.body.dataset.marketPage !== "my") return;

  const PLACEHOLDER_SRC = "/static/img/placeholder_stl.jpg";

  const els = {
    grid: document.getElementById("my-grid"),
    prevImg: document.getElementById("my-focus-prev"),
    mainImg: document.getElementById("my-focus-cover"),
    nextImg: document.getElementById("my-focus-next"),
    prevBtn: document.getElementById("my-prev"),
    nextBtn: document.getElementById("my-next"),
    editBtn: document.getElementById("my-focus-edit"),
  };

  if (!els.grid || !els.mainImg) {
    console.warn("[my_page_focus] grid or main image not found, abort");
    return;
  }

  const state = {
    items: [],       // [{ id, el, cover }]
    currentIndex: -1 // індекс обраної моделі в масиві items
  };

  // ===== Допоміжне: отримати src обкладинки з картки =====
  function getCoverFromCard(card) {
    // рендер з market.js: <a class="market-item-card"> <div class="thumb"><img ...> ...
    const img = card.querySelector("img");
    if (img && img.src) return img.src;
    // fallback
    const dataCover = card.getAttribute("data-cover");
    if (dataCover) return dataCover;
    return PLACEHOLDER_SRC;
  }

  // ===== Зчитати всі картки з гріда та зберегти у state.items =====
  function rebuildItems() {
    const cards = els.grid.querySelectorAll(".market-item-card, [data-item-id]");
    state.items = [];
    cards.forEach((card) => {
      const idStr = card.getAttribute("data-item-id") || "";
      const id = parseInt(idStr, 10) || idStr || null;
      const cover = getCoverFromCard(card);

      state.items.push({
        id,
        el: card,
        cover
      });
    });

    // Якщо нічого нема — скидаємо все
    if (!state.items.length) {
      state.currentIndex = -1;
      renderFocus();
      return;
    }

    // Якщо ще не було вибраної моделі — вибираємо першу
    if (state.currentIndex < 0 || state.currentIndex >= state.items.length) {
      state.currentIndex = 0;
    }

    renderFocus();
  }

  // ===== Відмалювати prev/main/next + підсвітити картку =====
  function renderFocus() {
    const { items, currentIndex } = state;

    if (!items.length || currentIndex < 0) {
      // нічого нема
      if (els.prevImg) els.prevImg.src = PLACEHOLDER_SRC;
      if (els.mainImg) els.mainImg.src = PLACEHOLDER_SRC;
      if (els.nextImg) els.nextImg.src = PLACEHOLDER_SRC;
      if (els.editBtn) els.editBtn.disabled = true;
      // зняти підсвітку з усіх карток
      els.grid.querySelectorAll(".market-item-card.is-selected").forEach((c) => {
        c.classList.remove("is-selected");
      });
      return;
    }

    const len = items.length;
    const cur = items[currentIndex];
    const prev = items[(currentIndex - 1 + len) % len];
    const next = items[(currentIndex + 1) % len];

    if (els.prevImg) els.prevImg.src = prev.cover || PLACEHOLDER_SRC;
    if (els.mainImg) els.mainImg.src = cur.cover || PLACEHOLDER_SRC;
    if (els.nextImg) els.nextImg.src = next.cover || PLACEHOLDER_SRC;

    if (els.editBtn) els.editBtn.disabled = !cur.id;

    // Підсвітити обрану картку
    els.grid.querySelectorAll(".market-item-card.is-selected").forEach((c) => {
      c.classList.remove("is-selected");
    });
    if (cur.el) {
      cur.el.classList.add("is-selected");
      // трішки прокрутимо, щоб видно було вибрану картку
      cur.el.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
    }
  }

  // ===== Вибрати картку по елементу =====
  function selectByCardElement(card) {
    const idx = state.items.findIndex((it) => it.el === card);
    if (idx === -1) return;
    state.currentIndex = idx;
    renderFocus();
  }

  // ===== Обробники подій =====
  function bindCardClicks() {
    els.grid.addEventListener("click", (ev) => {
      const card = ev.target.closest(".market-item-card, [data-item-id]");
      if (!card || !els.grid.contains(card)) return;

      // щоб не відкривалась сторінка моделі при кліку
      ev.preventDefault();

      selectByCardElement(card);
    });
  }

  function bindArrows() {
    if (els.prevBtn) {
      els.prevBtn.addEventListener("click", () => {
        if (!state.items.length) return;
        state.currentIndex =
          (state.currentIndex - 1 + state.items.length) % state.items.length;
        renderFocus();
      });
    }

    if (els.nextBtn) {
      els.nextBtn.addEventListener("click", () => {
        if (!state.items.length) return;
        state.currentIndex =
          (state.currentIndex + 1) % state.items.length;
        renderFocus();
      });
    }
  }

  function bindEditButton() {
    if (!els.editBtn) return;
    els.editBtn.addEventListener("click", (ev) => {
      ev.preventDefault();
      const { items, currentIndex } = state;
      if (!items.length || currentIndex < 0) return;
      const cur = items[currentIndex];

      // Якщо всередині картки є власна кнопка редагування — клікнемо по ній
      const internalEdit =
        cur.el.querySelector("[data-edit], [data-edit-item], .js-edit-item, .btn-edit");
      if (internalEdit) {
        internalEdit.click();
      } else {
        // Інакше кинемо кастомний івент, щоб інший JS міг підписатися
        const evt = new CustomEvent("my-focus-edit", {
          detail: {
            id: cur.id,
            card: cur.el
          }
        });
        document.dispatchEvent(evt);
      }
    });
  }

  // ===== Чекати, поки market.js намалює картки =====
  function waitGridReadyAndInit() {
    // якщо вже є елементи — просто будуємо
    if (els.grid.children.length) {
      rebuildItems();
    }

    // слухаємо зміни DOM у гріді (коли market.js оновить список)
    const obs = new MutationObserver((mut) => {
      // будемо перебудовувати items кожного разу, коли грід переписали
      let needRebuild = false;
      for (const m of mut) {
        if (m.type === "childList") {
          needRebuild = true;
          break;
        }
      }
      if (needRebuild) {
        rebuildItems();
      }
    });

    obs.observe(els.grid, {
      childList: true,
      subtree: false
    });
  }

  // ===== Старт =====
  function init() {
    bindCardClicks();
    bindArrows();
    bindEditButton();
    waitGridReadyAndInit();
    console.log("[my_page_focus] initialized");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
