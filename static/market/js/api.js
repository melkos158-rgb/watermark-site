// static/market/js/api.js
// Єдиний API-модуль для всіх скриптів маркету

const JSON_HEADERS = {
  "Content-Type": "application/json",
};

function buildUrl(path, params = {}) {
  const url = new URL(path, window.location.origin);
  Object.entries(params).forEach(([key, val]) => {
    if (val === undefined || val === null || val === "") return;
    url.searchParams.set(key, String(val));
  });
  return url.toString();
}

// ───── МОДЕЛІ / СПИСКИ ─────

async function fetchItems(params = {}) {
  // головний список моделей
  const url = buildUrl("/api/items", params);
  const res = await fetch(url, { credentials: "same-origin" });
  if (!res.ok) {
    console.error("fetchItems error", res.status);
    throw new Error("Failed to fetch items");
  }
  return res.json();
}

async function fetchMyItems(params = {}) {
  // мої моделі (для /market?owner=me, my-ads.js тощо)
  const url = buildUrl("/api/my/items", params);
  const res = await fetch(url, { credentials: "same-origin" });
  if (!res.ok) {
    console.error("fetchMyItems error", res.status);
    throw new Error("Failed to fetch my items");
  }
  return res.json();
}

// ───── ПОШУК / SUGGEST ─────

async function suggest(q) {
  if (!q) return [];
  const url = buildUrl("/api/search/suggest", { q });
  try {
    const res = await fetch(url, { credentials: "same-origin" });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch (e) {
    console.error("suggest error", e);
    return [];
  }
}

// ───── ЗАВАНТАЖЕННЯ / РЕДАГУВАННЯ МОДЕЛІ ─────

async function uploadModel(formData) {
  const res = await fetch("/api/market/upload", {
    method: "POST",
    credentials: "same-origin",
    body: formData,
  });
  if (!res.ok) {
    console.error("uploadModel error", res.status);
    throw new Error("Upload failed");
  }
  return res.json();
}

// ───── ОБРАНЕ ─────

async function toggleFav(itemId) {
  const res = await fetch("/api/market/fav", {
    method: "POST",
    credentials: "same-origin",
    headers: JSON_HEADERS,
    body: JSON.stringify({ item_id: itemId }),
  });
  if (!res.ok) {
    console.error("toggleFav error", res.status);
    throw new Error("Fav failed");
  }
  return res.json();
}

// синонім, якщо десь імпортується toggleFavorite
async function toggleFavorite(itemId) {
  return toggleFav(itemId);
}

// ───── ВІДГУКИ ─────

async function postReview(itemId, rating, text) {
  const payload = { item_id: itemId, rating, text };
  const res = await fetch("/api/market/review", {
    method: "POST",
    credentials: "same-origin",
    headers: JSON_HEADERS,
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    console.error("postReview error", res.status);
    throw new Error("Review failed");
  }
  return res.json();
}

// ───── ОПЛАТА ─────

async function createCheckout(itemId) {
  const res = await fetch("/api/market/checkout", {
    method: "POST",
    credentials: "same-origin",
    headers: JSON_HEADERS,
    body: JSON.stringify({ item_id: itemId }),
  });
  if (!res.ok) {
    console.error("createCheckout error", res.status);
    throw new Error("Checkout failed");
  }
  return res.json();
}

// ───── АНАЛІТИКА ─────

async function track(name, payload = {}) {
  try {
    await fetch("/api/visit", {
      method: "POST",
      credentials: "same-origin",
      headers: JSON_HEADERS,
      body: JSON.stringify({ name, ...payload }),
    });
  } catch (e) {
    console.error("track error", e);
  }
}

// ───── API-ОБ’ЄКТ ─────

const api = {
  fetchItems,
  fetchMyItems,
  suggest,
  uploadModel,
  toggleFav,
  toggleFavorite,
  postReview,
  createCheckout,
  track,
};

// default-експорт — для `import api from "./api.js"`
export default api;

// named-експорти — для `import { suggest } from "./api.js"` і т.п.
export {
  fetchItems,
  fetchMyItems,
  suggest,
  uploadModel,
  toggleFav,
  toggleFavorite,
  postReview,
  createCheckout,
  track,
};
