// static/js/recommend.js
// =====================================================
// Proofly Market — AI-рекомендації схожих моделей
// Використовує бекенд-роут /api/items/related?item_id=<id>
// або fallback: /api/items?tags=<tag> для ручного пошуку
// =====================================================

export async function loadRecommendations(itemId, tags = []) {
  const grid = document.getElementById("related-grid");
  if (!grid) return;

  grid.innerHTML = `<div class="muted">Завантаження схожих моделей...</div>`;

  try {
    let url = `/api/items/related?item_id=${itemId}`;
    if (tags && tags.length) {
      url += `&tags=${encodeURIComponent(tags.join(","))}`;
    }

    const r = await fetch(url);
    if (!r.ok) throw new Error("Bad response");
    const data = await r.json().catch(() => []);
    const items = Array.isArray(data) ? data : data.items || [];

    if (!items.length) {
      grid.innerHTML = `<div class="muted">Поки що немає схожих моделей 💤</div>`;
      return;
    }

    grid.innerHTML = items.map((it) => {
      const img = it.cover_url || it.cover || "/static/img/placeholder_stl.jpg";
      const title = escapeHtml(it.title || "Без назви");
      const price =
        !it.price_cents || it.is_free
          ? "Безкоштовно"
          : `${(it.price_cents / 100).toFixed(2)} PLN`;
      return `
        <a class="rec-card" href="/item/${it.slug || it.id}">
          <div class="thumb">
            <img src="${img}" alt="${title}" loading="lazy"
                 onerror="this.onerror=null;this.src='/static/img/placeholder_stl.jpg'">
          </div>
          <div class="meta">
            <div class="title">${title}</div>
            <div class="price">${price}</div>
          </div>
        </a>`;
    }).join("");
  } catch (err) {
    console.error("[recommend.js]", err);
    grid.innerHTML = `<div class="muted">Помилка при завантаженні рекомендацій 😢</div>`;
  }
}

// Допоміжна функція — захист від XSS
function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (m) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[m]));
}

// Автоматичний запуск на сторінці detail.html
document.addEventListener("DOMContentLoaded", () => {
  const el = document.querySelector("[data-item-id]");
  if (!el) return;
  const itemId = el.dataset.itemId;
  loadRecommendations(itemId);
});


// =====================================================
// CSS для карток рекомендацій — якщо не підключений окремо
// =====================================================
const css = `
.rec-card{
  display:flex;
  flex-direction:column;
  background:var(--card);
  border:1px solid var(--line);
  border-radius:10px;
  overflow:hidden;
  text-decoration:none;
  color:var(--text);
  transition:transform .15s, box-shadow .15s;
}
.rec-card:hover{
  transform:translateY(-3px);
  box-shadow:0 0 14px rgba(59,130,246,.25);
}
.rec-card .thumb{
  position:relative;
  width:100%;
  padding-top:70%;
  overflow:hidden;
}
.rec-card .thumb img{
  position:absolute;
  inset:0;
  width:100%;
  height:100%;
  object-fit:cover;
}
.rec-card .meta{
  padding:8px 10px;
  display:flex;
  flex-direction:column;
  gap:4px;
}
.rec-card .title{
  font-weight:600;
  font-size:14px;
  line-height:1.3;
}
.rec-card .price{
  font-size:13px;
  color:var(--muted);
}
`;

const style = document.createElement("style");
style.textContent = css;
document.head.appendChild(style);

