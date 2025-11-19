// static/market/js/api.js
// Єдиний клієнт для API маркету STL.
// Використовується іншими модулями: market.js, favorites.js, reviews.js, checkout.js, uploader.js тощо.

const BASE = "/api/market";

/**
 * Формує query-string з обʼєкта.
 */
function buildQuery(params = {}) {
  const parts = [];
  for (const [key, val] of Object.entries(params)) {
    if (val === undefined || val === null || val === "") continue;
    parts.push(
      encodeURIComponent(key) + "=" + encodeURIComponent(String(val))
    );
  }
  return parts.length ? "?" + parts.join("&") : "";
}

/**
 * Базовий запит до API.
 * Повертає:
 *   - null, якщо статус 204
 *   - JSON-обʼєкт у всіх інших випадках
 * Кидає Error, якщо HTTP-статус ≥ 400 або { ok:false }.
 *
 * Підтримує два типи body:
 *   - FormData  → відправляється як multipart/form-data (Content-Type не чіпаємо)
 *   - будь-який інший → JSON
 */
async function apiRequest(path, { method = "GET", params, body } = {}) {
  const qs = buildQuery(params);
  const url = BASE + path + qs;

  const opts = {
    method,
    headers: {
      "X-Requested-With": "XMLHttpRequest",
    },
    credentials: "same-origin",
  };

  if (body instanceof FormData) {
    // multipart upload — не ставимо Content-Type
    opts.body = body;
  } else if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }

  const res = await fetch(url, opts);

  // no-content
  if (res.status === 204) return null;

  let data;
  try {
    data = await res.json();
  } catch (e) {
    throw new Error("Invalid JSON from API (" + res.status + ")");
  }

  if (!res.ok || (data && data.ok === false)) {
    const msg =
      (data && (data.error || data.message)) ||
      "API error (" + res.status + ")";
    const err = new Error(msg);
    err.status = res.status;
    err.payload = data;
    throw err;
  }

  return data;
}

/* ───────────────────── ПУБЛІЧНІ ФУНКЦІЇ ───────────────────── */

/**
 * Завантаження списку моделей для головної сторінки маркету.
 * params:
 *   q, page, per_page, sort, category, owner_id, free
 */
export function fetchItems(params = {}) {
  return apiRequest("/items", { method: "GET", params });
}

/**
 * Альяс, якщо десь у коді ще використовується /list.
 */
export function fetchItemsList(params = {}) {
  return apiRequest("/list", { method: "GET", params });
}

/**
 * Детальна інформація про модель.
 * @param {string} slug
 */
export function fetchItemDetail(slug) {
  if (!slug) throw new Error("slug is required");
  return apiRequest(`/item/${encodeURIComponent(slug)}`, { method: "GET" });
}

/**
 * Моделі поточного користувача ("Мої оголошення").
 */
export function fetchMyItems(params = {}) {
  // 🔧 тут була помилка: "/my" → правильно "/my-items",
  // бо бекенд дає /api/market/my-items (compat до /api/my/items)
  return apiRequest("/my-items", { method: "GET", params });
}

/**
 * Підказки для пошуку.
 * @param {string} q
 */
export function fetchSuggest(q) {
  return apiRequest("/suggest", {
    method: "GET",
    params: { q: q || "" },
  });
}

/**
 * Тогл фавориту.
 * @param {number} itemId
 */
export function toggleFavorite(itemId) {
  if (!itemId) throw new Error("itemId is required");
  return apiRequest("/fav", {
    method: "POST",
    body: { item_id: itemId },
  });
}

/**
 * Надіслати / оновити відгук.
 * payload: { item_id, rating, text }
 */
export function sendReview(payload) {
  if (!payload || !payload.item_id) {
    throw new Error("item_id is required");
  }
  return apiRequest("/review", {
    method: "POST",
    body: payload,
  });
}

/**
 * Створити чекаут (Stripe/BLIK або free-download).
 * @param {number} itemId
 */
export function createCheckout(itemId) {
  if (!itemId) throw new Error("itemId is required");
  return apiRequest("/checkout", {
    method: "POST",
    body: { item_id: itemId },
  });
}

/**
 * Трекінг подій маркету (view/click/download/scroll).
 * payload: { type, slug?, item_id? , ... }
 */
export function trackMarketEvent(payload = {}) {
  return apiRequest("/track", {
    method: "POST",
    body: payload,
  }).catch(() => {
    // трекінг не критичний — ковтаємо помилки
  });
}

/**
 * Завантаження / оновлення моделі (multipart/form-data).
 * formData:
 *   title, description, category_slug, is_free, price_cents, cover, file, ...
 */
export function uploadModel(formData) {
  if (!(formData instanceof FormData)) {
    throw new Error("formData must be instance of FormData");
  }
  return apiRequest("/upload", {
    method: "POST",
    body: formData,
  });
}

/* ───── АЛЬЯСИ ПІД СТАРІ НАЗВИ (щоб не було помилок import) ───── */

// старі назви, які могли використовуватись у favorites.js / reviews.js / analytics.js / search.js / uploader.js
export const toggleFav   = toggleFavorite;
export const postReview  = sendReview;
export const track       = trackMarketEvent;
export const suggest     = fetchSuggest;
export const listItems   = fetchItems;
export const getItem     = fetchItemDetail;
export const upload      = uploadModel;

// якщо хтось імпортує buildQuery / apiRequest напряму
export { buildQuery, apiRequest };

/**
 * Хелпер, щоб зручно використовувати у глобальному коді без import:
 *   window.MARKET_API.fetchItems(...)
 */
if (typeof window !== "undefined") {
  window.MARKET_API = {
    fetchItems,
    fetchItemsList,
    fetchItemDetail,
    fetchMyItems,
    fetchSuggest,
    toggleFavorite,
    sendReview,
    createCheckout,
    trackMarketEvent,
    uploadModel,

    // альяси
    toggleFav,
    postReview,
    track,
    suggest,
    listItems,
    getItem,
    upload,
  };
}
