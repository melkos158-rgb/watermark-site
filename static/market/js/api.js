// static/market/js/api.js
// Легкий клієнт для API маркету

export const API = {
  async get(url, params = {}) {
    const u = new URL(url, location.origin);
    Object.entries(params).forEach(([k, v]) =>
      v == null ? u.searchParams.delete(k) : u.searchParams.set(k, v)
    );
    const r = await fetch(u, { credentials: "same-origin" });
    if (!r.ok) throw new Error(await r.text());
    return r.json().catch(() => ({}));
  },

  async post(url, data) {
    const headers = { "X-Requested-With": "fetch" };
    let body, method = "POST";
    if (data instanceof FormData) {
      body = data;
    } else {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(data || {});
    }
    const r = await fetch(url, { method, headers, body, credentials: "same-origin" });
    if (!r.ok) throw new Error(await r.text());
    return r.json().catch(() => ({}));
  },
};

// Підказки пошуку
export const suggest     = (q)        => API.get("/api/market/suggest", { q });

// Обране
export const toggleFav   = (item_id)  => API.post("/api/market/fav", { item_id });

// Відгуки/рейтинг
export const postReview  = (payload)  => API.post("/api/market/review", payload);

// Аплоад
export const uploadModel = (formData) => API.post("/api/market/upload", formData);

// Checkout
export const createCheckout = (payload) => API.post("/api/market/checkout", payload);

// Аналітика (ігноруємо помилки)
export const track = (event, data = {}) =>
  API.post("/api/market/track", { event, ...data }).catch(() => {});

// ── Утиліта: нормалізація шляхів до медіа (єдина логіка для всього фронта)
export function assetUrl(src, placeholder = "/static/img/placeholder_stl.jpg") {
  if (!src) return placeholder;
  let s = String(src).trim();

  // Абсолютні/inline
  if (s.startsWith("http://") || s.startsWith("https://") || s.startsWith("data:")) return s;

  // Новий публічний роут
  if (s.startsWith("/media/")) return s;
  if (s.startsWith("media/")) return "/" + s;

  // Старі локальні шляхи -> /media/...
  if (s.startsWith("/static/market_uploads/"))  return s.replace("/static/market_uploads/", "/media/");
  if (s.startsWith("static/market_uploads/"))   return ("/" + s).replace("/static/market_uploads/", "/media/");
  if (s.startsWith("/static/market_uploads/media/")) return s.replace("/static/market_uploads", "");
  if (s.startsWith("static/market_uploads/media/"))  return ("/" + s).replace("/static/market_uploads", "");
  if (s.startsWith("/market_uploads/media/"))   return s.replace("/market_uploads", "");
  if (s.startsWith("market_uploads/media/"))    return "/" + s.replace("market_uploads", "");

  // Фолбек: гарантуємо початковий слеш
  if (s.startsWith("/static/")) return s;
  if (s.startsWith("static/"))  return "/" + s;

  return s.startsWith("/") ? s : "/" + s;
}
