// static/market/js/categories.js
// =====================================================
// Інтерактивні категорії для STL Market
// Використовується у _filters.html, _subheader.html або будь-якому списку тегів
// =====================================================

document.addEventListener("DOMContentLoaded", () => {
  const catBtns = document.querySelectorAll("[data-cat], .tag-btn");
  if (!catBtns.length) return;

  let active = null;

  catBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const slug = btn.dataset.cat || "";
      if (active === slug) {
        // повторне натискання — скидає фільтр
        active = null;
        clearActive();
        dispatchCategory("");
        return;
      }
      active = slug;
      clearActive();
      btn.classList.add("active");
      dispatchCategory(slug);
    });
  });

  function clearActive() {
    catBtns.forEach((b) => b.classList.remove("active"));
  }

  function dispatchCategory(slug) {
    document.dispatchEvent(
      new CustomEvent("marketCategoryChange", { detail: slug })
    );
  }
});

// =====================================================
// CSS для кнопок категорій
// =====================================================
const css = `
.tag-btn, [data-cat]{
  background:var(--card);
  border:1px solid var(--line);
  color:var(--text);
  border-radius:999px;
  padding:5px 12px;
  font-size:13px;
  cursor:pointer;
  transition:all .15s;
}
.tag-btn:hover,[data-cat]:hover{
  background:var(--accent);
  color:#fff;
  border-color:var(--accent);
}
.tag-btn.active,[data-cat].active{
  background:var(--accent);
  color:#fff;
  border-color:var(--accent);
  box-shadow:0 0 10px rgba(59,130,246,.4);
}
.cat-tags{
  display:flex;
  flex-wrap:wrap;
  gap:8px;
  margin-bottom:8px;
}
`;
const style = document.createElement("style");
style.textContent = css;
document.head.appendChild(style);
