// Загальний ініт маркету: пошук, друга шапка, модалка
const $ = (s, r=document) => r.querySelector(s);

function goWithParams(next = {}) {
  const p = new URLSearchParams(location.search);
  Object.entries(next).forEach(([k, v]) => (v==null || v==="") ? p.delete(k) : p.set(k, v));
  p.set("page", "1");
  location.search = p.toString();
}

document.addEventListener("DOMContentLoaded", () => {
  const q     = $("#q");
  const cat   = $("#cat");
  const sort  = $("#sort");
  const btnS  = $("#btn-search");
  const modal = $("#upload-modal");

  // Пошук
  btnS?.addEventListener("click", () => goWithParams({ q: q?.value || "" }));
  q?.addEventListener("keydown", (e)=>{ if(e.key==="Enter") goWithParams({ q: q.value }); });

  // Фільтри
  cat?.addEventListener("change", ()=> goWithParams({ cat: cat.value }));
  sort?.addEventListener("change",()=> goWithParams({ sort: sort.value }));

  // Модалка «Додати модель»
  $("#btn-upload")?.addEventListener("click", (e)=>{ e.preventDefault(); modal.hidden = false; });
  modal?.querySelector("[data-close]")?.addEventListener("click", ()=> modal.hidden = true);
  modal?.querySelector(".modal-close")?.addEventListener("click", ()=> modal.hidden = true);

  // Ціна: показувати/ховати поле
  const free = modal?.querySelector('input[name="is_free"]');
  const priceRow = modal?.querySelector(".price-row");
  const syncPriceVis = ()=> priceRow && (priceRow.style.display = free?.checked ? "none" : "flex");
  free?.addEventListener("change", syncPriceVis); syncPriceVis();
});
