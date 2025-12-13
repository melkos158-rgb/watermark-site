// static/market/js/my-ads.js
// Карусель + сітка "Мої оголошення"

// маленький ескейп, щоб не зламати HTML
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

document.addEventListener("DOMContentLoaded", function () {
  console.log("my-ads.js loaded");

  const carousel = document.getElementById("myAdsCarousel");
  const gridInner = document.querySelector(".my-ads-grid-inner");
  const emptyMsg = document.querySelector(".my-ads-empty");
  const leftBtn = document.querySelector(".my-ads-arrow.left");
  const rightBtn = document.querySelector(".my-ads-arrow.right");
  const addBtn = document.querySelector(".my-ads-add-btn");

  /** всі моделі користувача */
  let items = [];
  /** індекс поточно вибраної моделі */
  let currentIndex = 0;

  function getCover(it) {
    return (
      it.cover_url ||
      it.cover ||
      "/static/img/placeholder_stl.jpg"
    );
  }

  function isFree(it) {
    const raw = it.price;
    if (raw === null || raw === undefined) return true;
    const p = Number(raw);
    if (Number.isNaN(p)) return true;
    return p === 0;
  }

  function formatPrice(it) {
    if (isFree(it)) return "Безкоштовно";
    const p = Number(it.price);
    if (Number.isNaN(p)) return "—";
    return `${p.toFixed(2)} PLN`;
  }

  // ───────────────────── РЕНДЕР КАРУСЕЛІ ─────────────────────
  function renderCarousel() {
    if (!carousel) return;
    carousel.innerHTML = "";

    if (!items.length) return;

    const n = items.length;

    // щоб не вилізти за межі
    if (currentIndex < 0) currentIndex = 0;
    if (currentIndex > n - 1) currentIndex = n - 1;

    /** масив із максимум 3 елементів: лівий / центр / правий */
    const slots = [];

    if (n === 1) {
      slots.push({ idx: 0, pos: "center" });
    } else if (n === 2) {
      const leftIdx = (currentIndex + n - 1) % n;
      slots.push({ idx: leftIdx, pos: "left" });
      slots.push({ idx: currentIndex, pos: "center" });
    } else {
      const leftIdx = (currentIndex + n - 1) % n;
      const rightIdx = (currentIndex + 1) % n;
      slots.push({ idx: leftIdx, pos: "left" });
      slots.push({ idx: currentIndex, pos: "center" });
      slots.push({ idx: rightIdx, pos: "right" });
    }

    slots.forEach(function (slot) {
      const it = items[slot.idx];

      const card = document.createElement("div");
      card.className = "my-ads-carousel-item " + slot.pos;
      card.dataset.index = String(slot.idx);

      card.innerHTML = `
        <div class="my-ads-carousel-thumb"
             style="background-image:url('${escapeHtml(
               getCover(it)
             )}');"></div>
        <div class="my-ads-carousel-caption">
          <div class="my-ads-carousel-title">
            ${escapeHtml(it.title || "Без назви")}
          </div>
          <div class="my-ads-carousel-price">
            ${escapeHtml(formatPrice(it))}
          </div>
        </div>
      `;

      if (slot.pos === "center") {
        // клік по центру → перехід на сторінку моделі
        card.addEventListener("click", function () {
          if (it.id) {
            window.location.href = "/item/" + it.id;
          }
        });
      } else {
        // клік по боковій картці → зробити її центром
        card.addEventListener("click", function () {
          currentIndex = slot.idx;
          renderAll();
        });
      }

      carousel.appendChild(card);
    });
  }

  // ───────────────────── РЕНДЕР СІТКИ ─────────────────────
  function renderGrid() {
    if (!gridInner) return;
    gridInner.innerHTML = "";

    if (!items.length) return;

    items.forEach(function (it, idx) {
      const card = document.createElement("div");
      card.className = "my-ads-card";
      if (idx === currentIndex) {
        card.classList.add("active"); // підсвітка вибраного
      }
      card.dataset.index = String(idx);

      card.innerHTML = `
        <div class="my-ads-card-thumb"
             style="background-image:url('${escapeHtml(
               getCover(it)
             )}');"></div>
        <div class="my-ads-card-body">
          <div class="my-ads-card-title">
            ${escapeHtml(it.title || "Без назви")}
          </div>
          <div class="my-ads-card-price">
            ${escapeHtml(formatPrice(it))}
          </div>
        </div>
        <div class="my-ads-card-actions">
          <button type="button"
                  class="btn btn-sm my-ads-btn-view">
            Дивитися
          </button>
          <button type="button"
                  class="btn btn-sm my-ads-btn-edit">
            Редагувати
          </button>
        </div>
      `;

      // клік по картці → зробити її вибраною в каруселі
      card.addEventListener("click", function (e) {
        if (
          e.target.closest(".my-ads-btn-view") ||
          e.target.closest(".my-ads-btn-edit")
        ) {
          return;
        }
        currentIndex = idx;
        renderAll();
      });

      const btnView = card.querySelector(".my-ads-btn-view");
      const btnEdit = card.querySelector(".my-ads-btn-edit");

      if (btnView) {
        btnView.addEventListener("click", function () {
          if (it.id) {
            window.location.href = "/item/" + it.id;
          }
        });
      }

      if (btnEdit) {
        btnEdit.addEventListener("click", function () {
          if (it.id) {
            console.log("my-ads: edit click, id =", it.id);
            window.location.href = "/market/edit/" + it.id;
          }
        });
      }

      gridInner.appendChild(card);
    });
  }

  // ───────────────────── ЗАГАЛЬНИЙ РЕНДЕР ─────────────────────
  function renderAll() {
    renderCarousel();
    renderGrid();
  }

  // ───────────────────── КНОПКИ КЕРУВАННЯ ─────────────────────
  if (leftBtn) {
    leftBtn.addEventListener("click", function () {
      if (!items.length) return;
      const n = items.length;
      currentIndex = (currentIndex + n - 1) % n;
      renderAll();
    });
  }

  if (rightBtn) {
    rightBtn.addEventListener("click", function () {
      if (!items.length) return;
      const n = items.length;
      currentIndex = (currentIndex + 1) % n;
      renderAll();
    });
  }

  if (addBtn) {
    addBtn.addEventListener("click", function () {
      // якщо немає моделей → додаємо
      if (!items.length) {
        window.location.href = "/market/upload";
        return;
      }
      // якщо є — редагуємо поточну
      const current = items[currentIndex] || items[0];
      if (current && current.id) {
        console.log("my-ads: main edit/add button, goto edit", current.id);
        window.location.href = "/market/edit/" + current.id;
      } else {
        window.location.href = "/market/upload";
      }
    });
  }

  // ───────────────────── ЗАВАНТАЖЕННЯ ДАНИХ ─────────────────────
  function loadMyItems() {
    console.log("my-ads: fetching /api/my/items?page=1");
    fetch("/api/my/items?page=1", {
      credentials: "same-origin",
    })
      .then(function (res) {
        console.log("my-ads: status", res.status);
        if (res.status === 401) {
          if (emptyMsg) {
            emptyMsg.textContent =
              "Увійди в профіль, щоб побачити свої моделі.";
            emptyMsg.style.display = "block";
          }
          return null;
        }
        return res.json();
      })
      .then(function (data) {
        console.log("my-ads: data =", data);
        if (!data || !Array.isArray(data.items)) {
          if (emptyMsg) {
            emptyMsg.style.display = "block";
          }
          return;
        }

        items = data.items || [];
        console.log("my-ads: items length =", items.length);

        if (!items.length) {
          if (emptyMsg) {
            emptyMsg.style.display = "block";
          }
          return;
        }

        currentIndex = 0;
        if (emptyMsg) {
          emptyMsg.style.display = "none";
        }
        renderAll();
      })
      .catch(function (err) {
        console.error("my-ads: fetch error", err);
        if (emptyMsg) {
          emptyMsg.textContent = "Помилка завантаження оголошень.";
          emptyMsg.style.display = "block";
        }
      });
  }

  loadMyItems();
});
