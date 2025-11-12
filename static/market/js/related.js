// static/market/js/related.js
// Відображення "Схожих моделей" на сторінці деталі STL

(function () {
  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }

  function qsa(sel, root) {
    return Array.from((root || document).querySelectorAll(sel));
  }

  function createEl(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text != null) el.textContent = text;
    return el;
  }

  async function getJSON(url) {
    const res = await fetch(url, { method: "GET" });
    if (!res.ok) {
      throw new Error("Bad status " + res.status);
    }
    return res.json();
  }

  function buildCard(item) {
    // Очікуємо формат:
    // {
    //   id, title, thumb_url, price, rating, downloads, slug, url
    // }
    const card = createEl("article", "related-card");

    const link = createEl("a", "related-link");
    link.href = item.url || (`/market/item/${item.id}`);
    link.setAttribute("aria-label", item.title || "Model");

    const img = createEl("img", "related-thumb");
    img.src = item.thumb_url || item.preview_url || "";
    img.alt = item.title || "Model preview";

    const body = createEl("div", "related-body");

    const title = createEl("div", "related-title", item.title || "Без назви");

    const meta = createEl("div", "related-meta");

    // Ціна
    const price = createEl(
      "span",
      "related-price",
      item.price && item.price > 0
        ? `${item.price.toFixed ? item.price.toFixed(2) : item.price} zł`
        : "Безкоштовно"
    );

    meta.appendChild(price);

    // Рейтинг
    if (item.rating) {
      const rating = createEl(
        "span",
        "related-rating",
        `⭐ ${item.rating.toFixed ? item.rating.toFixed(1) : item.rating}`
      );
      meta.appendChild(rating);
    }

    // Завантаження
    if (item.downloads != null) {
      const downloads = createEl(
        "span",
        "related-downloads",
        `${item.downloads} завантажень`
      );
      meta.appendChild(downloads);
    }

    body.appendChild(title);
    body.appendChild(meta);

    link.appendChild(img);
    link.appendChild(body);

    card.appendChild(link);
    return card;
  }

  async function loadRelated(container) {
    const endpoint =
      container.getAttribute("data-endpoint") || "/api/market/related";
    const itemId = container.getAttribute("data-item-id");
    if (!itemId) {
      container.textContent = "Не вказано модель для пошуку схожих.";
      return;
    }

    // Плейсхолдер
    container.innerHTML = "";
    const loading = createEl("div", "related-loading muted", "Завантаження схожих моделей…");
    container.appendChild(loading);

    try {
      const url = `${endpoint}?item_id=${encodeURIComponent(itemId)}`;
      const data = await getJSON(url);

      const items = Array.isArray(data) ? data : data.items || [];
      container.innerHTML = "";

      if (!items.length) {
        const empty = createEl(
          "div",
          "related-empty muted",
          "Поки що немає схожих моделей. Опублікуй більше STL — алгоритм навчиться краще 💡"
        );
        container.appendChild(empty);
        return;
      }

      const list = createEl("div", "related-list");
      items.forEach((item) => {
        list.appendChild(buildCard(item));
      });
      container.appendChild(list);
    } catch (err) {
      console.error("related: cannot load related items", err);
      container.innerHTML = "";
      const error = createEl(
        "div",
        "related-error muted",
        "Не вдалося завантажити схожі моделі. Спробуй пізніше."
      );
      container.appendChild(error);
    }
  }

  function init() {
    const containers = qsa("#related-items");
    if (!containers.length) return;

    containers.forEach((c) => loadRelated(c));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
