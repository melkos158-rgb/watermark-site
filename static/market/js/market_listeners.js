// static/js/market_listeners.js
// Єдиний "слухач" для STL-маркету Proofly.
//
// Завдання:
//   • клік по кнопках "Add to bundle", "Favorite", "Quick view" і т.п.
//   • надсилати події на бекенд (аналітика / трекінг / wishlist)
//   • кидати кастомні події, які ловлять інші скрипти (bundle_cart.js, suggest.js, тощо)
//   • мінімальні тости через window.ProoflyNotify.toast (якщо є)
//
// Очікувані (але не обовʼязкові) бекенд-ендпоінти:
//
//   POST /api/market/track_event
//     body: { action, item_id, payload }
//     -> { ok:true }
//
//   POST /api/market/favorite
//     body: { item_id, on:true/false }
//     -> { ok:true, on:true/false }
//
// HTML-атрибути, з якими ми працюємо:
//
//   data-market-card           – картка моделі (для impression-трекінгу)
//   data-item-id               – id моделі
//   data-add-to-bundle         – кнопка "в бандл" (іконка або текст)
//   data-add-to-cart           – якщо колись буде окремий кошик
//   data-favorite-toggle       – кнопка "додати в улюблене / забрати"
//   data-track-click           – довільна подія (наприклад, відкриття quick-view)
//   data-track-action          – назва події для track_click
//   data-track-payload         – JSON-строка з додатковими даними (опційно)
//
// Приклад у шаблоні картки:
//
//   <article class="market-card" data-market-card data-item-id="{{ item.id }}">
//     ...
//     <button class="btn-bundle" data-add-to-bundle data-item-id="{{ item.id }}">
//       ➕ До бандлу
//     </button>
//     <button class="btn-fav" data-favorite-toggle data-item-id="{{ item.id }}">
//       ❤
//     </button>
//   </article>
//
// Ініціалізація в templates/market/*.html:
//
//   <script type="module">
//     import { initMarketListeners } from "{{ url_for('static', filename='js/market_listeners.js') }}";
//     document.addEventListener("DOMContentLoaded", () => {
//       initMarketListeners();
//     });
//   </script>

export function initMarketListeners({
  root = document,
  impressionThreshold = 0.4, // частина картки, що має бути у вʼюпорті
} = {}) {
  const doc = root || document;

  // ========= УТИЛІТИ =========

  function apiFetch(url, options = {}) {
    const opts = {
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      credentials: "same-origin",
      ...options,
    };
    return fetch(url, opts).then(async (res) => {
      let data;
      try {
        data = await res.json();
      } catch (e) {
        throw new Error("Invalid JSON from server");
      }
      if (!res.ok || data.ok === false) {
        const msg = (data && data.error) || `HTTP ${res.status}`;
        throw new Error(msg);
      }
      return data;
    });
  }

  function safeJsonParse(str) {
    if (!str) return null;
    try {
      return JSON.parse(str);
    } catch (_) {
      return null;
    }
  }

  function toast(msg, level = "info") {
    if (window.ProoflyNotify && window.ProoflyNotify.toast) {
      window.ProoflyNotify.toast(msg, level);
    } else {
      // запасний варіант
      console.log("[Proofly toast]", level, msg);
    }
  }

  function trackEvent(action, payload = {}) {
    try {
      // Паралельно можна кинути глобальну подію, якщо іншим скриптам цікаво
      window.dispatchEvent(
        new CustomEvent("proofly:market_event", {
          detail: { action, payload },
        })
      );

      // Якщо бекенд не готовий — просто не робимо fetch
      if (!window.ProoflyConfig || !window.ProoflyConfig.enableMarketTracking) {
        return;
      }

      apiFetch("/api/market/track_event", {
        method: "POST",
        body: JSON.stringify({
          action,
          payload,
        }),
      }).catch((err) => {
        console.warn("[market_listeners] track_event error:", err);
      });
    } catch (e) {
      console.warn("[market_listeners] trackEvent failed:", e);
    }
  }

  // ========= IMPRESSIONS ДЛЯ КАРТОК =========

  const seenImpressions = new Set();

  function setupImpressionObserver() {
    if (!("IntersectionObserver" in window)) {
      console.warn("[market_listeners] IntersectionObserver not supported");
      return;
    }

    const cards = doc.querySelectorAll("[data-market-card]");
    if (!cards.length) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const el = entry.target;
          const ratio = entry.intersectionRatio || 0;
          if (ratio < impressionThreshold) return;

          const itemId = el.getAttribute("data-item-id");
          const key = itemId ? `item:${itemId}` : `el:${Date.now()}-${Math.random()}`;

          if (seenImpressions.has(key)) {
            return;
          }
          seenImpressions.add(key);

          if (itemId) {
            trackEvent("impression", {
              item_id: itemId,
              source: "market_card",
            });
          }

          // після першого разу цей елемент нам не потрібен
          observer.unobserve(el);
        });
      },
      {
        threshold: impressionThreshold,
      }
    );

    cards.forEach((card) => observer.observe(card));
  }

  // ========= WISHLIST / FAVORITES =========

  function handleFavoriteToggle(target) {
    const itemId = target.getAttribute("data-item-id");
    if (!itemId) return;

    const isActive = target.classList.contains("is-favorite");
    const nextState = !isActive;

    // Миттєво перемикаємо UI (optimistic)
    target.classList.toggle("is-favorite", nextState);
    const iconEl = target.querySelector("[data-fav-icon]") || target;
    iconEl.dataset.state = nextState ? "on" : "off";

    apiFetch("/api/market/favorite", {
      method: "POST",
      body: JSON.stringify({
        item_id: itemId,
        on: nextState,
      }),
    })
      .then((data) => {
        const serverOn =
          typeof data.on === "boolean" ? data.on : nextState;
        target.classList.toggle("is-favorite", serverOn);
        iconEl.dataset.state = serverOn ? "on" : "off";

        if (serverOn) {
          toast("Додано в улюблені.", "success");
          trackEvent("favorite_on", { item_id: itemId });
        } else {
          toast("Прибрано з улюблених.", "info");
          trackEvent("favorite_off", { item_id: itemId });
        }
      })
      .catch((err) => {
        console.error("[market_listeners] favorite error:", err);
        // відкотимо UI
        target.classList.toggle("is-favorite", isActive);
        iconEl.dataset.state = isActive ? "on" : "off";
        toast("Не вдалося оновити улюблене. Спробуй ще раз.", "error");
      });
  }

  // ========= BUNDLE / CART =========

  function handleAddToBundle(target) {
    const itemId = target.getAttribute("data-item-id");
    if (!itemId) return;

    // Шлемо подію, яку вже може слухати bundle_cart.js
    window.dispatchEvent(
      new CustomEvent("proofly:bundle_add", {
        detail: {
          itemId,
          source: "market_card",
        },
      })
    );

    toast("Додано в бандл. Відкрий панель бандлів, щоб переглянути.", "success");
    trackEvent("bundle_add", { item_id: itemId });
  }

  function handleAddToCart(target) {
    const itemId = target.getAttribute("data-item-id");
    if (!itemId) return;

    window.dispatchEvent(
      new CustomEvent("proofly:cart_add", {
        detail: {
          itemId,
          source: "market_card",
        },
      })
    );

    toast("Додано в кошик.", "success");
    trackEvent("cart_add", { item_id: itemId });
  }

  // ========= GENERIC CLICK TRACKING =========

  function handleTrackClick(target) {
    const action =
      target.getAttribute("data-track-action") || "click";
    const payloadStr = target.getAttribute("data-track-payload");
    const payload = safeJsonParse(payloadStr) || {};

    const itemId = target.getAttribute("data-item-id");
    if (itemId && !payload.item_id) {
      payload.item_id = itemId;
    }
    payload.source = payload.source || "market";

    trackEvent(action, payload);
  }

  // ========= DELEGATION: ОБРОБКА КЛІКІВ =========

  function onClick(e) {
    const target = e.target;
    if (!target || !(target instanceof HTMLElement)) return;

    // шукаємо найближчий елемент з потрібними data-атрибутами
    const favBtn = target.closest("[data-favorite-toggle]");
    if (favBtn) {
      e.preventDefault();
      handleFavoriteToggle(favBtn);
      return;
    }

    const bundleBtn = target.closest("[data-add-to-bundle]");
    if (bundleBtn) {
      e.preventDefault();
      handleAddToBundle(bundleBtn);
      return;
    }

    const cartBtn = target.closest("[data-add-to-cart]");
    if (cartBtn) {
      e.preventDefault();
      handleAddToCart(cartBtn);
      return;
    }

    const trackBtn = target.closest("[data-track-click]");
    if (trackBtn) {
      // не блокуємо default поведінку, тільки трекаєм
      handleTrackClick(trackBtn);
      return;
    }
  }

  doc.addEventListener("click", onClick, { passive: false });

  // ========= СТАРТ IMPRESSIONS =========

  setupImpressionObserver();

  // ========= ГЛОБАЛЬНИЙ API =========

  if (!window.ProoflyMarket) {
    window.ProoflyMarket = {};
  }

  window.ProoflyMarket.trackEvent = trackEvent;
  window.ProoflyMarket.initListeners = initMarketListeners;

  return {
    trackEvent,
    destroy() {
      doc.removeEventListener("click", onClick, { passive: false });
    },
  };
}
