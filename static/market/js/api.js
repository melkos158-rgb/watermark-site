// static/market/js/api.js
// ========================================================
// Легкий клієнт для API Proofly STL Market
// Уніфіковані методи get/post + допоміжні API-виклики
// ========================================================

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

// ========================================================
// API endpoints
// ========================================================
export const suggest         = (q)        => API.get("/api/market/suggest", { q });
export const toggleFav       = (item_id)  => API.post("/api/market/fav", { item_id });
export const postReview      = (payload)  => API.post("/api/market/review", payload);
export const uploadModel     = (formData) => API.post("/api/market/upload", formData);
export const createCheckout  = (payload)  => API.post("/api/market/checkout", payload);
export const track           = (event, data = {}) => API.post("/api/market/track", { event, ...data }).catch(() => {});

// ========================================================
// AI AutoTag — автоматичне визначення тегів за назвою
// ========================================================
export const autoTag = async (title) => {
  try {
    const r = await API.get("/api/autotag", { q: title });
    return Array.isArray(r) ? r : [];
  } catch {
    return [];
  }
};

// ========================================================
// Утиліта: нормалізація шляхів до медіа (єдина логіка для фронта)
// ========================================================
export function assetUrl(src, placeholder = "/static/img/placeholder_stl.jpg") {
  if (!src) return placeholder;
  let s = String(src).trim();

  if (s.startsWith("http://") || s.startsWith("https://") || s.startsWith("data:")) return s;
  if (s.startsWith("/media/")) return s;
  if (s.startsWith("media/")) return "/" + s;

  if (s.startsWith("/static/market_uploads/"))  return s.replace("/static/market_uploads/", "/media/");
  if (s.startsWith("static/market_uploads/"))   return ("/" + s).replace("/static/market_uploads/", "/media/");
  if (s.startsWith("/static/market_uploads/media/")) return s.replace("/static/market_uploads", "");
  if (s.startsWith("static/market_uploads/media/"))  return ("/" + s).replace("/static/market_uploads", "");
  if (s.startsWith("/market_uploads/media/"))   return s.replace("/market_uploads", "");
  if (s.startsWith("market_uploads/media/"))    return "/" + s.replace("market_uploads", "");

  if (s.startsWith("/static/")) return s;
  if (s.startsWith("static/"))  return "/" + s;

  return s.startsWith("/") ? s : "/" + s;
}

// ========================================================
// Глобальний error handler для фронтенду маркету
// ========================================================
window.addEventListener("unhandledrejection", (e) => {
  console.warn("[API Error]", e.reason);
  if (String(e.reason).includes("Unauthorized")) {
    alert("⛔ Потрібно увійти в акаунт, щоб виконати цю дію.");
  }
});
